import logging
import time
from concurrent.futures import ThreadPoolExecutor
from itertools import count
from threading import BoundedSemaphore

from pipeline.arguments import PipelineArguments
from pipeline.context import FrameContext

logger = logging.getLogger(__name__)

_WORKER = ThreadPoolExecutor(
    max_workers=1, thread_name_prefix="postprocess-worker"
)
_SLOT = BoundedSemaphore(1)


def _runnable(frame: FrameContext) -> None:
    try:
        time.sleep(5)
    except Exception as error:
        logger.exception(error)
    finally:
        _SLOT.release()


def on_frame(parameters: PipelineArguments, frame: FrameContext) -> FrameContext:
    if not _SLOT.acquire(blocking=False):
        return frame
    
    try:
        _WORKER.submit(_runnable, frame)
    except Exception as error:
        _SLOT.release()
        logger.exception(error)
    return frame
