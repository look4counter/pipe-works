
from contextlib import contextmanager
from contextvars import ContextVar
import logging
from threading import Lock, get_ident


_route = ContextVar("pipeworks_log_route", default=None)
_forwarding = ContextVar("pipeworks_log_forwarding", default=False)
_install_lock = Lock()
_relay = None


def current_route():
    return _route.get()


@contextmanager
def use_route(route):
    token = _route.set(route)
    try:
        yield
    finally:
        _route.reset(token)


def capture_settings():
    return {
        "root": logging.getLogger().level,
        "disable": logging.root.manager.disable,
        "root_disabled": logging.getLogger().disabled,
        "loggers": {
            name: {"level": value.level, "disabled": value.disabled}
            for name, value in logging.root.manager.loggerDict.copy().items()
            if isinstance(value, logging.Logger) and (value.level or value.disabled)
        },
    }


def _enabled(settings, name, level):
    if settings.get("disable", 0) >= level:
        return False
    loggers = settings.get("loggers", {})
    if loggers.get(name, {}).get("disabled", False):
        return False
    if name == "root" and settings.get("root_disabled", False):
        return False
    candidate = name
    while candidate:
        configured = loggers.get(candidate, {}).get("level", 0)
        if configured:
            return level >= configured
        candidate = candidate.rpartition(".")[0]
    return level >= settings["root"]


def _safe_value(value, depth=0):
    if value is None or type(value) in (str, int, float, bool, bytes):
        return value
    if depth < 4:
        if type(value) is dict:
            return {str(_safe_value(key, 4)): _safe_value(item, depth + 1)
                    for key, item in value.items()}
        if type(value) in (tuple, list):
            return [_safe_value(item, depth + 1) for item in value]
    try:
        return repr(value)
    except Exception:
        return f"<{type(value).__name__}>"


def _record_payload(record):
    data = {key: _safe_value(value) for key, value in record.__dict__.items()
            if key not in ("args", "msg", "exc_info", "_pipeworks_relayed")}
    try:
        data["msg"] = record.getMessage()
    except Exception:
        data["msg"] = str(_safe_value(record.msg))
    data["args"] = ()
    data["exc_info"] = None
    if record.exc_info:
        data["exc_text"] = logging.Formatter().formatException(record.exc_info)
    return data


class LogRoute:
    def __init__(self, send, stop, settings, pipeline_name, execution_id):
        self.send, self.stop, self.settings = send, stop, settings
        self.pipeline_name, self.execution_id = pipeline_name, execution_id
        self.active = True
        self.lock = Lock()

    def emit(self, record):
        if _forwarding.get() or getattr(record, "pipeworks_remote", False):
            return
        if not _enabled(self.settings, record.name, record.levelno):
            return
        token = _forwarding.set(True)
        try:
            with self.lock:
                if not self.active or getattr(record, "_pipeworks_relayed", None) == self.execution_id:
                    return
                record._pipeworks_relayed = self.execution_id
                data = _record_payload(record)
                data["pipeworks_pipeline"] = self.pipeline_name
                data["pipeworks_execution_id"] = self.execution_id
                try:
                    self.send(("log", data))
                except (EOFError, OSError):
                    # 전송 실패를 로깅하면 같은 경로로 재귀 진입할 수 있다.
                    self.active = False
                    self.stop.set()
        finally:
            _forwarding.reset(token)

    def close(self):
        with self.lock:
            self.active = False


class RelayHandler(logging.Handler):
    def __init__(self, fallback_level=logging.WARNING):
        super().__init__(logging.NOTSET)
        self.fallback_level = fallback_level

    def emit(self, record):
        route = current_route()
        if route is not None:
            route.emit(record)
        elif not getattr(record, "pipeworks_remote", False):
            root = logging.getLogger()
            fallback = logging.lastResort
            if (fallback is not None and not any(h is not self for h in root.handlers)
                    and record.levelno >= max(self.fallback_level, fallback.level)):
                fallback.handle(record)


class _OutsideRoute(logging.Filter):
    def filter(self, record):
        return current_route() is None


def install_relay(settings):
    global _relay
    with _install_lock:
        root = logging.getLogger()
        if _relay is None:
            _relay = RelayHandler(root.level)
        for name in settings.get("loggers", {}):
            logging.getLogger(name)
        loggers = [root] + [value for value in logging.root.manager.loggerDict.copy().values()
                            if isinstance(value, logging.Logger)]
        for logger in loggers:
            if logger.level:
                logger.setLevel(logging.NOTSET)
            logger.disabled = False
            for handler in logger.handlers:
                if handler is not _relay and not any(isinstance(f, _OutsideRoute) for f in handler.filters):
                    handler.addFilter(_OutsideRoute())
            if (logger is root or not logger.propagate) and _relay not in logger.handlers:
                logger.addHandler(_relay)
        if logging.root.manager.disable:
            logging.disable(logging.NOTSET)


def dispatch_record(data):
    record = logging.makeLogRecord(data)
    record.pipeworks_remote = True
    logger = logging.getLogger(record.name)
    if logger.isEnabledFor(record.levelno):
        logger.handle(record)


class PrintAdapter:
    limit = 64 * 1024

    def __init__(self, route):
        self.route = route
        self.buffers = {}
        self.lock = Lock()
        self.closed = False

    def _chunks(self, text):
        while len(text.encode("utf-8", errors="replace")) > self.limit:
            chunk = text.encode("utf-8", errors="replace")[:self.limit].decode("utf-8", errors="ignore")
            yield chunk
            text = text[len(chunk):]
        yield text

    def _emit(self, lines):
        for line in lines:
            record = logging.LogRecord("pipeworks.user_output", logging.DEBUG,
                                       __file__, 0, line, (), None)
            record.pipeworks_stream = "stdout"
            self.route.emit(record)

    def __call__(self, value):
        lines = []
        with self.lock:
            if self.closed or not self.route.active:
                return len(value)
            key = get_ident()
            text = self.buffers.pop(key, "") + value
            while "\n" in text:
                line, _, text = text.partition("\n")
                lines.extend(self._chunks(line))
            chunks = list(self._chunks(text))
            lines.extend(chunks[:-1])
            if chunks[-1]:
                self.buffers[key] = chunks[-1]
        self._emit(lines)
        return len(value)

    def flush(self):
        with self.lock:
            value = self.buffers.pop(get_ident(), "")
        if value:
            self._emit([value])

    def close(self):
        with self.lock:
            self.closed = True
            values = list(self.buffers.values())
            self.buffers.clear()
        self._emit(values)
