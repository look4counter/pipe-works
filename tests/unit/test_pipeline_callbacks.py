from contextlib import nullcontext
from types import ModuleType
from unittest.mock import Mock

from pipeline.arguments import PipelineArguments
from pipeline.cli import run_inference, run_postprocess
from pipeline.context import FrameContext


def parameters() -> PipelineArguments:
    return PipelineArguments(
        "rtsp://in", "tcp", "rtsp://out", "tcp", "nvidia", 0,
        False, None, True, "inference.py", 1, "pytorch", True, "postprocess.py",
    )


def test_inference_callback_exception_passes_through_original_frame(monkeypatch) -> None:
    monkeypatch.setattr("pipeline.cli.torch.cuda.stream", lambda _: nullcontext())
    monkeypatch.setattr("pipeline.cli.torch.from_dlpack", lambda data: data)
    increment = Mock()
    monkeypatch.setattr("pipeline.cli.PIPELINE_STATISTICS.increment", increment)
    inference_module = ModuleType("inference")

    def fail(_infer, _parameters, _frame):
        raise ValueError("inference failed")

    inference_module.on_frame = fail
    frame = FrameContext(object(), object(), cuda_stream=object())

    result = next(
        run_inference(parameters(), [frame], {"inference": inference_module})
    )

    assert result is frame
    increment.assert_called_once_with("inferenceFailed")


def test_postprocess_callback_exception_passes_through_original_frame(monkeypatch) -> None:
    increment = Mock()
    monkeypatch.setattr("pipeline.cli.PIPELINE_STATISTICS.increment", increment)
    postprocess_module = ModuleType("postprocess")

    def fail(_parameters, _frame):
        raise ValueError("postprocess failed")

    postprocess_module.on_frame = fail
    frame = FrameContext(object(), object())

    result = next(
        run_postprocess(parameters(), [frame], {"postprocess": postprocess_module})
    )

    assert result is frame
    increment.assert_called_once_with("postprocessFailed")
