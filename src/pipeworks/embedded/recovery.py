"""내장 단계의 실행 오류 분류와 반복자 복구."""

import logging

import torch


logger = logging.getLogger(__name__)


class ResourceSafetyError(RuntimeError):
    """GPU 자원의 안전한 사용 종료를 확인할 수 없는 상태."""


def is_fatal(error):
    seen = set()
    pending = [error]
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, (ResourceSafetyError, MemoryError, torch.cuda.OutOfMemoryError)):
            return True
        message = str(current).lower()
        if any(part in message for part in (
            "cuda error:", "cuda out of memory", "device-side assert",
            "illegal memory access", "device lost", "driver shutting down",
            "gpu unavailable", "cuda scope failed", "context is destroyed",
            "cublas_status_alloc_failed", "cudnn_status_alloc_failed",
            "cuda driver", "cuda initialization", "no cuda-capable device",
            "nvidia driver", "cuda-capable devices are busy",
        )):
            return True
        pending.extend(e for e in (current.__cause__, current.__context__) if e is not None)
    return False


def gpu_call(method, *args, **kwargs):
    try:
        return method(*args, **kwargs)
    except Exception as error:
        raise ResourceSafetyError(f"GPU 자원 작업에 실패했습니다: {error}") from error


def report_call(method, *args):
    try:
        return method(*args)
    except Exception as error:
        if is_fatal(error):
            raise
        logger.warning("부가 통계 보고를 생략합니다: %s", error)


def close(iterator):
    method = getattr(iterator, "close", None)
    if callable(method):
        try:
            method()
        except Exception as error:
            if is_fatal(error):
                raise
            logger.warning("실패한 처리 반복자 정리 중 오류: %s", error)


class _Inputs:
    def __init__(self, inputs):
        self.inputs = iter(inputs)
        self.item = None
        self.upstream_error = None

    def __iter__(self):
        return self

    def __next__(self):
        try:
            self.item = next(self.inputs)
            return self.item
        except StopIteration:
            raise
        except Exception as error:
            self.upstream_error = error
            raise


def inference_outputs(process, inputs):
    """정상 세션은 유지하고 실패한 세션만 다음 입력에서 다시 만든다."""
    tracked = _Inputs(inputs)
    outputs = None
    item = result = None
    try:
        while True:
            tracked.item = None
            try:
                if outputs is None:
                    outputs = iter(process(tracked))
                result = next(outputs)
            except StopIteration:
                return
            except Exception as error:
                if is_fatal(error) or tracked.upstream_error is not None:
                    raise
                logger.warning("추론 실패로 원본 영상을 전달하고 세션을 재생성합니다: %s", error)
                close(outputs)
                outputs = None
                item = tracked.item
                if item is None:
                    try:
                        item = next(tracked)
                    except StopIteration:
                        return
                item.model_output = None
                for name in ("_inference_profile", "_tensor_rt_profile", "_yolo_profile"):
                    profile = getattr(item, name, None)
                    if profile is not None and not profile.finished:
                        profile.finish("error")
                yield item
            else:
                yield result
            finally:
                tracked.item = None
                item = result = None
    finally:
        close(outputs)
