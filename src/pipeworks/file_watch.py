"""Share OS notifications and immutable file snapshots within one process."""

import atexit
from dataclasses import dataclass
from hashlib import sha256
import logging
import os
from pathlib import Path
from threading import Lock, RLock
from time import monotonic
import weakref

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FileSnapshot:
    source: bytes
    digest: str


@dataclass
class _Entry:
    users: int = 0
    dirty: bool = True
    checked: float = float("-inf")
    snapshot: FileSnapshot | None = None


class _Events(FileSystemEventHandler):
    def __init__(self, service):
        self.service = service

    def on_any_event(self, event):
        if event.event_type not in {"modified", "created", "deleted", "moved"}:
            return
        if event.is_directory and event.event_type not in {"deleted", "moved"}:
            return
        self.service.mark_changed(event.src_path, directory=event.is_directory)
        destination = getattr(event, "dest_path", None)
        if destination:
            self.service.mark_changed(destination, directory=event.is_directory)


class _WatchService:
    def __init__(self, *, observer_factory=Observer):
        self.observer_factory = observer_factory
        self.observer = None
        self.entries: dict[Path, _Entry] = {}
        self.directories: dict[Path, object] = {}
        self.lock = RLock()
        self.handler = _Events(self)
        self.retry_at = float("-inf")
        self.retired = []
        self.notification_lock = Lock()
        self.changed = set()
        self.targets = frozenset()

    def _healthy(self):
        return (self.observer is not None and self.observer.is_alive()
                and all(emitter.is_alive() for emitter in self.observer.emitters))

    def _ensure_observer(self, now):
        parents = {path.parent for path in self.entries}
        if self._healthy() and parents.issubset(self.directories):
            return True
        if self.observer is None and now < self.retry_at:
            return False
        self.retry_at = now + 0.5
        # Stop is nonblocking: joining here would deadlock an event callback
        # waiting for our lock. Retired observers are joined outside the lock.
        old = self.observer
        if old is not None:
            old.stop()
            self.retired.append(old)
        self.observer = None
        self.directories.clear()
        for entry in self.entries.values():
            entry.dirty = True
        observer = None
        try:
            observer = self.observer_factory()
            for directory in parents:
                self.directories[directory] = observer.schedule(
                    self.handler, str(directory), recursive=False)
            observer.start()
        except Exception:
            if observer is not None:
                observer.stop()
                self.retired.append(observer)
            self.directories.clear()
            logger.warning("OS 파일 감시를 시작하지 못해 재검사로 전환합니다.", exc_info=True)
            return False
        self.observer = observer
        return True

    def acquire(self, path):
        with self.lock:
            entry = self.entries.setdefault(path, _Entry())
            entry.users += 1
            self.targets = frozenset(self.entries)
            # Existing observer can add a directory without rebuilding others.
            if self._healthy() and path.parent not in self.directories:
                try:
                    self.directories[path.parent] = self.observer.schedule(
                        self.handler, str(path.parent), recursive=False)
                except Exception:
                    logger.warning("디렉터리 감시 등록 실패: %s", path.parent, exc_info=True)
            self._ensure_observer(monotonic())

    def mark_changed(self, path, *, directory=False):
        path = Path(os.path.abspath(path))
        targets = self.targets
        affected = ({watched for watched in targets if watched.is_relative_to(path)}
                    if directory else ({path} if path in targets else set()))
        # Watchdog dispatch holds its own observer lock. Never acquire our
        # service lock here: stop/unschedule acquire the locks in reverse order.
        with self.notification_lock:
            self.changed.update(affected)

    def snapshot(self, path, *, force=False):
        try:
            return self._snapshot(path, force=force)
        finally:
            with self.lock:
                retired, self.retired = self.retired, []
            self._join(retired)

    def _snapshot(self, path, *, force=False):
        with self.lock:
            now = monotonic()
            with self.notification_lock:
                changed, self.changed = self.changed, set()
            for changed_path in changed:
                if changed_path in self.entries:
                    self.entries[changed_path].dirty = True
            healthy = self._ensure_observer(now)
            entry = self.entries[path]
            interval = 30.0 if healthy else 0.5
            if force or entry.dirty or now - entry.checked >= interval:
                # Keep dirty on read failure so creation/restoration is retried.
                entry.dirty = True
                source = path.read_bytes()
                entry.snapshot = FileSnapshot(source, sha256(source).hexdigest())
                entry.checked = now
                entry.dirty = False
            return entry.snapshot

    def release(self, path):
        observers = []
        with self.lock:
            entry = self.entries.get(path)
            if entry is None:
                return
            entry.users -= 1
            if entry.users:
                return
            del self.entries[path]
            self.targets = frozenset(self.entries)
            if not any(other.parent == path.parent for other in self.entries):
                watch = self.directories.pop(path.parent, None)
                if watch is not None and self.observer is not None:
                    self.observer.unschedule(watch)
            if not self.entries:
                if self.observer is not None:
                    self.observer.stop()
                    observers.append(self.observer)
                    self.observer = None
                self.directories.clear()
                self.retry_at = float("-inf")
            observers.extend(self.retired)
            self.retired.clear()
        self._join(observers)

    @staticmethod
    def _join(observers):
        for observer in observers:
            if not hasattr(observer, "ident") or observer.ident is not None:
                observer.join(timeout=2)

    def close(self):
        with self.lock:
            observers = list(getattr(self, "retired", ()))
            if self.observer is not None:
                self.observer.stop()
                observers.append(self.observer)
            self.observer = None
            self.entries.clear()
            self.targets = frozenset()
            self.directories.clear()
            self.retired = []
            with self.notification_lock:
                self.changed.clear()
        self._join(observers)


_service = None
_service_pid = None
_service_lock = RLock()


def _shared_service():
    global _service, _service_pid
    with _service_lock:
        if _service is None or _service_pid != os.getpid():
            _service = _WatchService()
            _service_pid = os.getpid()
            atexit.register(_service.close)
        return _service


class FileSubscription:
    """A lazy subscription; only its path crosses a process boundary."""

    def __init__(self, path, *, service=None):
        self.path = Path(path).resolve()
        self._service = service
        self._finalizer = None
        self._pid = None

    def snapshot(self, *, force=False):
        if self._finalizer is None or self._pid != os.getpid():
            if self._pid is not None and self._pid != os.getpid():
                self._finalizer.detach()
                self._service = None
            if self._service is None:
                self._service = _shared_service()
            self._service.acquire(self.path)
            self._pid = os.getpid()
            self._finalizer = weakref.finalize(self, self._service.release, self.path)
        return self._service.snapshot(self.path, force=force)

    def close(self):
        if self._finalizer is not None:
            self._finalizer()
            self._finalizer = None

    def __getstate__(self):
        return {"path": self.path}

    def __setstate__(self, state):
        self.__init__(state["path"])
