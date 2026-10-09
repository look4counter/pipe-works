from pathlib import Path
from hashlib import sha256
import logging
from threading import Lock
from time import monotonic
from types import SimpleNamespace

import yaml

from pipeworks.hotswap import Hotswap, is_embedded_step
from pipeworks.models import Step


logger = logging.getLogger(__name__)


def _configure_async_children(step, sections):
    from pipeworks.embedded.cuda_async import CudaAsync

    original = step.wrapped_step if isinstance(step, Hotswap) else step
    if isinstance(original, CudaAsync):
        for inner in original._hot_steps:
            child = inner.wrapped_step if isinstance(inner, Hotswap) else inner
            inner.configure(SimpleNamespace(**sections.get(type(child).__name__, {})))
            _configure_async_children(inner, sections)


def _watch_async_children(step, watcher, sections):
    from pipeworks.embedded.cuda_async import CudaAsync

    original = step.wrapped_step if isinstance(step, Hotswap) else step
    if isinstance(original, CudaAsync):
        running = []
        for inner in original._hot_steps:
            child = inner.wrapped_step if isinstance(inner, Hotswap) else inner
            section = type(child).__name__
            if not isinstance(inner, Hotswap):
                inner = Hotswap(inner, watch_code=False, recover_errors=False)
                inner._config = SimpleNamespace(**sections.get(section, {}))
            inner._config_provider = lambda name=section: watcher.section(name)
            _watch_async_children(inner, watcher, sections)
            running.append(inner)
        original._hot_steps = tuple(running)


def _load_config(source: bytes) -> dict:
    loaded = yaml.safe_load(source)
    if loaded is None:
        loaded = {}
    if not isinstance(loaded, dict):
        raise ValueError("파이프라인 설정의 최상위 값은 매핑이어야 합니다.")
    for section, section_config in loaded.items():
        if not isinstance(section_config, dict):
            raise ValueError(f"{section} 설정은 매핑이어야 합니다.")
    return loaded


class _LiveConfig:
    def __init__(self, path: Path, initial: dict, digest: str) -> None:
        self.path = path
        self.data = initial
        self.digest = digest
        self.failed_digest: str | None = None
        self.last_check = float("-inf")
        self.lock = Lock()

    def section(self, name: str) -> SimpleNamespace:
        with self.lock:
            now = monotonic()
            if now - self.last_check >= 0.5:
                self.last_check = now
                digest = None
                try:
                    source = self.path.read_bytes()
                    digest = sha256(source).hexdigest()
                    if digest != self.digest and digest != self.failed_digest:
                        self.data = _load_config(source)
                        self.digest = digest
                        self.failed_digest = None
                except Exception:
                    if digest is not None:
                        self.failed_digest = digest
                    logger.exception("변경된 파이프라인 설정을 적용하지 못했습니다: %s", self.path)
            return SimpleNamespace(**self.data.get(name, {}))


class Pipeline:

    def __init__(self, name: str, *, config: Path):
        self.name = name
        self.config_path = config.resolve()
        source = config.read_bytes()
        loaded_config = _load_config(source)
        self._config_digest = sha256(source).hexdigest()
        self.config = SimpleNamespace(**loaded_config)
        self.steps: list[Step] = []

    def step(self, step: Step):
        registered = step if isinstance(step, Hotswap) or is_embedded_step(step) else Hotswap(step)
        original = registered.wrapped_step if isinstance(registered, Hotswap) else registered
        section = type(original).__name__
        step_config = getattr(self.config, section, {})
        if not isinstance(step_config, dict):
            raise ValueError(f"{section} 설정은 매핑이어야 합니다.")
        registered.configure(SimpleNamespace(**step_config))
        _configure_async_children(registered, vars(self.config))
        if not self.steps and isinstance(registered, Hotswap):
            registered.source = True
        self.steps.append(registered)
        return self

    def run(self):
        from pipeworks.main import run_remote

        return run_remote(self)

    def _run_local(self, stop_event=None):
        from pipeworks.embedded.stream_report import report_scope
        from pipeworks.embedded.tap import Tap

        with report_scope():
            watcher = _LiveConfig(self.config_path, vars(self.config), self._config_digest)
            inputs = iter(())
            for index, step in enumerate(self.steps):
                _watch_async_children(step, watcher, vars(self.config))
                if stop_event is not None:
                    setattr(step, "_pipeworks_stop_event", stop_event)
                section = type(step.wrapped_step).__name__ if isinstance(step, Hotswap) else type(step).__name__
                provider = lambda name=section: watcher.section(name)
                if isinstance(step, Tap):
                    inner = step.step
                    if not isinstance(inner, Hotswap):
                        inner = Hotswap(inner, watch_code=False, recover_errors=False)
                        inner._config = SimpleNamespace(**vars(self.config).get(section, {}))
                        step.step = inner
                    inner._config_provider = provider
                    running_step = step
                else:
                    if isinstance(step, Hotswap):
                        running_step = step
                    else:
                        running_step = Hotswap(step, source=index == 0, watch_code=False, recover_errors=False)
                        running_step._config = SimpleNamespace(**vars(self.config).get(section, {}))
                    running_step._config_provider = provider
                    if stop_event is not None:
                        setattr(running_step.wrapped_step, "_pipeworks_stop_event", stop_event)
                inputs = running_step.process(inputs)

            try:
                for _ in inputs:
                    if stop_event is not None and stop_event.is_set():
                        break
            finally:
                close = getattr(inputs, "close", None)
                if callable(close):
                    close()
