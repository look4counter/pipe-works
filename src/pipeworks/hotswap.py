"""Reload a Step implementation between finite input epochs."""

from collections.abc import Callable, Iterator
import _imp
from hashlib import sha256
import inspect
import logging
from pathlib import Path
import sys
from threading import Lock
from time import monotonic, sleep
from types import ModuleType, SimpleNamespace
from uuid import uuid4

from pipeworks.models import PipelineContext, Step


logger = logging.getLogger(__name__)
_MISSING = object()
_EPOCH_ATTRIBUTE = "_pipeworks_hotswap_epoch"
_IMPORT_LOCK = Lock()


def is_embedded_step(step: Step) -> bool:
    try:
        filename = inspect.getsourcefile(type(step)) or inspect.getfile(type(step))
        if filename is None:
            return False
        embedded_dir = Path(__file__).resolve().parent / "embedded"
        return Path(filename).resolve().is_relative_to(embedded_dir)
    except (OSError, TypeError):
        return False


class _Cursor:
    def __init__(self, inputs: Iterator[PipelineContext]) -> None:
        self.inputs = iter(inputs)
        self.pending: object = _MISSING

    def take(self) -> PipelineContext:
        if self.pending is not _MISSING:
            item = self.pending
            self.pending = _MISSING
            return item
        return next(self.inputs)

    def put_back(self, item: PipelineContext) -> None:
        if self.pending is not _MISSING:
            raise RuntimeError("핫스왑 경계에 이미 보관된 입력이 있습니다.")
        self.pending = item

    def close(self) -> None:
        close = getattr(self.inputs, "close", None)
        if callable(close):
            close()


class _InputEpoch:
    def __init__(self, cursor: _Cursor, owner: "Hotswap", epoch: tuple) -> None:
        self.cursor = cursor
        self.owner = owner
        self.epoch = epoch
        self.reason: str | None = None
        self.next_epoch: tuple | None = None
        self.unacknowledged: list[tuple[PipelineContext, dict[str, object]]] = []
        self.upstream_error: Exception | None = None

    def __iter__(self) -> "_InputEpoch":
        return self

    def __next__(self) -> PipelineContext:
        if self.reason is not None:
            raise StopIteration
        if self.owner._check_for_update():
            self.reason = "code"
            raise StopIteration

        try:
            item = self.cursor.take()
        except StopIteration:
            self.reason = "end"
            raise
        except Exception as error:
            self.upstream_error = error
            raise

        item_epoch = getattr(item, _EPOCH_ATTRIBUTE, ())
        if item_epoch != self.epoch:
            self.cursor.put_back(item)
            self.next_epoch = item_epoch
            self.reason = "upstream"
            raise StopIteration

        # The upstream iterator may block while a source reconnects. Check
        # again before handing the newly obtained item to the old Step.
        if self.owner._check_for_update():
            self.cursor.put_back(item)
            self.reason = "code"
            raise StopIteration
        if self.owner.recover_errors:
            self.unacknowledged.append((item, vars(item).copy()))
        return item

    def acknowledge(self) -> None:
        self.unacknowledged.clear()

    def close(self) -> None:
        self.cursor.close()


class Hotswap(Step):
    def __init__(
        self,
        step: Step,
        *,
        check_interval: float = 0.5,
        source: bool = False,
        watch_code: bool = True,
        recover_errors: bool = True,
    ) -> None:
        if check_interval < 0:
            raise ValueError("파일 확인 간격은 음수일 수 없습니다.")
        self.wrapped_step = step
        self._config = SimpleNamespace()
        self.check_interval = check_interval
        self.source = source
        self.recover_errors = recover_errors
        self._config_provider: Callable[[], SimpleNamespace] | None = None
        self._failed_config: dict | None = None
        self._class_name = type(step).__name__
        self._package = getattr(sys.modules.get(type(step).__module__), "__package__", "") or ""
        try:
            filename = inspect.getsourcefile(type(step)) or inspect.getfile(type(step))
        except (OSError, TypeError):
            filename = None
        self._path = Path(filename).resolve() if filename and watch_code else None
        self._active_digest = self._file_digest()
        self._failed_digest: str | None = None
        self._last_check = float("-inf")
        self._candidate: tuple[type[Step], str, str] | None = None
        self._owned_module: str | None = None
        self._revision = 0
        self._slot_id = id(self)

    def configure(self, config) -> None:
        self.wrapped_step.configure(config)
        self._config = config

    def _file_digest(self) -> str | None:
        if self._path is None:
            return None
        try:
            return sha256(self._path.read_bytes()).hexdigest()
        except OSError:
            return None

    def _apply_config(self, config: SimpleNamespace) -> None:
        step = self.wrapped_step
        if not hasattr(step, "__dict__"):
            self._failed_config = vars(config).copy()
            logger.error("Step 설정 변경을 위해 속성 사전이 필요합니다: %s", self._class_name)
            return
        previous_fields = vars(step).copy()
        try:
            step.configure(config)
        except Exception:
            vars(step).clear()
            vars(step).update(previous_fields)
            self._failed_config = vars(config).copy()
            logger.exception("변경된 Step 설정을 적용하지 못해 이전 설정을 유지합니다: %s", self._class_name)
            return
        self._config = config
        self._failed_config = None

    def _check_for_update(self, *, force: bool = False) -> bool:
        now = monotonic()
        if not force and now - self._last_check < self.check_interval:
            return self._candidate is not None
        self._last_check = now
        if self._config_provider is not None:
            try:
                updated_config = self._config_provider()
                fields = vars(updated_config)
                if fields == vars(self._config):
                    self._failed_config = None
                elif fields != self._failed_config:
                    self._apply_config(updated_config)
            except Exception:
                logger.exception("Step 설정 변경을 확인하지 못했습니다: %s", self._class_name)
        if self._path is None:
            return False
        try:
            source = self._path.read_bytes()
        except OSError:
            logger.exception("Step 파일을 읽지 못했습니다: %s", self._path)
            return self._candidate is not None
        digest = sha256(source).hexdigest()
        if digest == self._active_digest:
            if self._candidate is not None:
                sys.modules.pop(self._candidate[1], None)
                self._candidate = None
            return False
        if self._candidate is not None and digest == self._candidate[2]:
            return True
        if digest == self._failed_digest:
            return self._candidate is not None

        module_name = f"{self._package + '.' if self._package else ''}_pipeworks_hotswap_{uuid4().hex}"
        module = ModuleType(module_name)
        module.__file__ = str(self._path)
        module.__package__ = self._package
        sys.modules[module_name] = module
        try:
            import_root = self._path.parent
            for _ in self._package.split(".") if self._package else ():
                import_root = import_root.parent
            with _IMPORT_LOCK:
                _imp.acquire_lock()
                try:
                    sys.path.insert(0, str(import_root))
                    try:
                        exec(compile(source, str(self._path), "exec"), module.__dict__)
                    finally:
                        sys.path.remove(str(import_root))
                finally:
                    _imp.release_lock()
            step_type = getattr(module, self._class_name)
            if not isinstance(step_type, type) or not issubclass(step_type, Step):
                raise TypeError(f"{self._class_name}은 Step 클래스여야 합니다.")
        except Exception:
            sys.modules.pop(module_name, None)
            self._failed_digest = digest
            logger.exception("변경된 Step을 준비하지 못해 이전 구현을 유지합니다: %s", self._path)
            return self._candidate is not None
        if self._candidate is not None:
            sys.modules.pop(self._candidate[1], None)
        self._candidate = (step_type, module_name, digest)
        self._failed_digest = None
        return True

    def _new_step(self, step_type: type[Step], *, preserve_state: bool, config=None) -> Step:
        previous = self.wrapped_step
        if preserve_state:
            fresh = step_type.__new__(step_type)
            if not hasattr(fresh, "__dict__") or not hasattr(previous, "__dict__"):
                raise TypeError("상태 이전을 위해 Step에 속성 사전이 필요합니다.")
            fresh.__dict__.update(previous.__dict__)
        else:
            try:
                signature = inspect.signature(step_type)
                arguments = {
                    name: getattr(previous, name)
                    for name, parameter in signature.parameters.items()
                    if parameter.kind
                    in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
                    and hasattr(previous, name)
                }
                signature.bind(**arguments)
            except TypeError:
                fresh = step_type.__new__(step_type)
                if not hasattr(fresh, "__dict__") or not hasattr(previous, "__dict__"):
                    raise TypeError("생성자 인자가 있는 Step은 속성 사전이 필요합니다.")
                fresh.__dict__.update(previous.__dict__)
            else:
                fresh = step_type(**arguments)
        if hasattr(previous, "_pipeworks_stop_event"):
            fresh._pipeworks_stop_event = previous._pipeworks_stop_event
        fresh.configure(self._config if config is None else config)
        return fresh

    def _commit_update(self) -> bool:
        self._check_for_update(force=True)
        candidate = self._candidate
        if candidate is None:
            return False
        step_type, module_name, digest = candidate
        try:
            fresh = self._new_step(step_type, preserve_state=True)
        except Exception:
            sys.modules.pop(module_name, None)
            self._candidate = None
            self._failed_digest = digest
            logger.exception("변경된 Step을 생성하지 못해 이전 구현을 유지합니다: %s", self._path)
            return False
        previous_module = self._owned_module
        self.wrapped_step = fresh
        self._candidate = None
        self._owned_module = module_name
        self._active_digest = digest
        self._revision += 1
        if previous_module is not None:
            sys.modules.pop(previous_module, None)
        logger.info("Step 구현을 교체했습니다: %s", self._path)
        return True

    def _restart_step(self) -> None:
        self.wrapped_step = self._new_step(type(self.wrapped_step), preserve_state=False)

    def _output_epoch(self, upstream_epoch: tuple) -> tuple:
        if not self._revision:
            return upstream_epoch
        return upstream_epoch + ((self._slot_id, self._revision),)

    def process(self, inputs: Iterator[PipelineContext]) -> Iterator[PipelineContext]:
        if self.source:
            yield from self._process_source()
            return

        cursor = _Cursor(inputs)
        upstream_epoch: tuple = ()
        try:
            while True:
                segment = _InputEpoch(cursor, self, upstream_epoch)
                outputs = None
                failed = False
                try:
                    outputs = iter(self.wrapped_step.process(segment))
                    for item in outputs:
                        segment.acknowledge()
                        setattr(item, _EPOCH_ATTRIBUTE, self._output_epoch(upstream_epoch))
                        yield item
                        del item
                except Exception:
                    if segment.upstream_error is not None:
                        raise
                    if not self.recover_errors:
                        raise
                    failed = True
                    logger.exception("사용자 Step 실행 오류로 원본 입력을 전달합니다: %s", self._class_name)
                finally:
                    if outputs is not None:
                        close = getattr(outputs, "close", None)
                        if callable(close):
                            try:
                                close()
                            except Exception:
                                if not self.recover_errors:
                                    raise
                                if segment.upstream_error is not None:
                                    logger.exception("상류 오류 이후 사용자 Step 반복자 정리에 실패했습니다: %s", self._class_name)
                                else:
                                    failed = True
                                    logger.exception("사용자 Step 반복자 정리에 실패해 원본 입력을 전달합니다: %s", self._class_name)

                if failed:
                    if not segment.unacknowledged and segment.reason is None:
                        try:
                            next(segment)
                        except StopIteration:
                            pass
                    for item, original_fields in segment.unacknowledged:
                        fields = vars(item)
                        fields.clear()
                        fields.update(original_fields)
                        setattr(item, _EPOCH_ATTRIBUTE, self._output_epoch(upstream_epoch))
                        yield item
                    segment.acknowledge()
                    if segment.reason is None:
                        try:
                            self._restart_step()
                        except Exception:
                            logger.exception("사용자 Step을 다시 만들지 못해 기존 인스턴스로 재시도합니다: %s", self._class_name)
                        continue

                if segment.reason == "code":
                    self._commit_update()
                elif segment.reason == "upstream":
                    self._restart_step()
                    upstream_epoch = segment.next_epoch
                else:
                    return
        finally:
            cursor.close()

    def _process_source(self) -> Iterator[PipelineContext]:
        while True:
            outputs = None
            failed = False
            try:
                outputs = iter(self.wrapped_step.process(iter(())))
                for item in outputs:
                    setattr(item, _EPOCH_ATTRIBUTE, self._output_epoch(()))
                    yield item
                    if self._check_for_update():
                        break
                else:
                    return
            except Exception:
                if not self.recover_errors:
                    raise
                failed = True
                logger.exception("사용자 소스 Step 실행 오류로 재시도합니다: %s", self._class_name)
            finally:
                if outputs is not None:
                    close = getattr(outputs, "close", None)
                    if callable(close):
                        try:
                            close()
                        except Exception:
                            if not self.recover_errors:
                                raise
                            failed = True
                            logger.exception("사용자 소스 Step 반복자 정리에 실패해 재시도합니다: %s", self._class_name)
            if failed:
                try:
                    self._restart_step()
                except Exception:
                    logger.exception("사용자 소스 Step을 다시 만들지 못해 기존 인스턴스로 재시도합니다: %s", self._class_name)
                sleep(0.1)
                continue
            self._commit_update()
