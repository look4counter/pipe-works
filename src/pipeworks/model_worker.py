"""Resolve model paths only when connecting to a shared worker for the first time."""

from pathlib import Path


def get_model_worker(model_path, workers, paths, lock, create):
    path = Path(model_path)
    cwd = None if path.is_absolute() else Path.cwd()
    alias = path, cwd
    with lock:
        canonical = paths.get(alias)
        worker = workers.get(canonical) if canonical is not None else None
        if worker is not None:
            return worker
        canonical = (cwd / path if cwd is not None else path).resolve()
        worker = workers.get(canonical)
        if worker is None:
            if not canonical.is_file():
                raise FileNotFoundError(canonical)
            worker = create(canonical)
            workers[canonical] = worker
        paths[alias] = canonical
        return worker
