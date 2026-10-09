"""Collect compatible requests without model or GPU dependencies."""

from collections import deque
from collections.abc import Callable
from queue import Empty, Queue
import time
from typing import TypeVar


Request = TypeVar("Request")


def collect_batch(
    requests: Queue[Request],
    deferred: deque[Request],
    max_batch_size: int,
    timeout: float,
    *,
    key: Callable[[Request], object],
    received_at: Callable[[Request], float],
) -> list[Request]:
    """Wait from the oldest request's arrival; defer incompatible requests.

    timeout is in seconds. Queue ownership and result delivery stay with callers.
    """
    first = deferred.popleft() if deferred else requests.get()
    batch = [first]
    first_key = key(first)
    deadline = received_at(first) + timeout
    while len(batch) < max_batch_size:
        try:
            request = requests.get(timeout=max(0, deadline - time.monotonic()))
        except Empty:
            break
        if key(request) != first_key:
            deferred.append(request)
            continue
        batch.append(request)
    return batch
