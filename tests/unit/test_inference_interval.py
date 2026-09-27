from contextlib import nullcontext
from types import ModuleType, SimpleNamespace

import pytest

from pipeline.arguments import PipelineArguments
from pipeline.cli import run_inference
from pipeline.context import FrameContext


def parameters(interval: int) -> PipelineArguments:
    return PipelineArguments(
        "rtsp://in", "tcp", "rtsp://out", "tcp", "nvidia", 0,
        False, None, True, "inference.py", interval, "pytorch", False, None,
    )


@pytest.mark.parametrize(
    "interval, expected_indexes",
    [(1, [0, 1, 2, 3, 4]), (3, [0, 3])],
)
def test_inference_interval_calls_hook_for_every_frame_with_infer_flag(
    monkeypatch, interval: int, expected_indexes: list[int]
) -> None:
    frames = [
        FrameContext(object(), object(), cuda_stream=object()) for _ in range(5)
    ]
    calls = []
    inference_module = ModuleType("inference")

    def on_frame(infer, _parameters, frame):
        calls.append((infer, frame))
        if infer:
            frame.inference_result = "inferred"
        return frame

    inference_module.on_frame = on_frame
    monkeypatch.setattr("pipeline.cli.torch.cuda.stream", lambda _: nullcontext())
    monkeypatch.setattr("pipeline.cli.torch.from_dlpack", lambda data: data)

    output = list(
        run_inference(parameters(interval), iter(frames), {"inference": inference_module})
    )

    assert output == frames
    assert calls == [
        (index in expected_indexes, frame) for index, frame in enumerate(frames)
    ]
    assert [frame.inference_result for frame in frames] == [
        "inferred" if index in expected_indexes else None
        for index in range(len(frames))
    ]


def test_inference_interval_rejects_missing_inference_module(monkeypatch) -> None:
    monkeypatch.setattr("pipeline.cli.torch.cuda.stream", lambda _: nullcontext())
    frame = FrameContext(object(), object(), cuda_stream=SimpleNamespace())

    with pytest.raises(RuntimeError, match="inference"):
        next(run_inference(parameters(1), iter([frame]), {}))
