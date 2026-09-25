import pytest

from pipeline.arguments import parse_arguments


def valid_args() -> list[str]:
    return ["--input-rtsp-url", "rtsp://camera/input", "--input-rtsp-transport", "tcp",
            "--output-rtsp-url", "rtsp://server/output", "--output-rtsp-transport", "udp",
            "--pipe-type", "nvidia", "--gpuid", "0", "--metadata-enabled", "true",
            "--metadata-path", "metadata.py", "--inference-enabled", "true",
            "--inference-path", "inference.py", "--inference-interval", "15",
            "--inference-frame", "pytorch", "--postprocess-enabled", "true",
            "--postprocess-path", "postprocess.py"]


def test_parses_rtsp_pipeline_configuration() -> None:
    result = parse_arguments(valid_args())
    assert result.pipe_type == "nvidia"
    assert result.gpu_id == 0
    assert result.inference_interval == 15


@pytest.mark.parametrize("flag,value", [("--input-rtsp-url", "https://camera"), ("--inference-interval", "0")])
def test_rejects_invalid_values(flag: str, value: str) -> None:
    args = valid_args()
    args[args.index(flag) + 1] = value
    with pytest.raises(SystemExit):
        parse_arguments(args)


def test_requires_path_when_stage_is_enabled() -> None:
    args = valid_args()
    index = args.index("--metadata-path")
    del args[index:index + 2]
    with pytest.raises(ValueError, match="metadata-enabled"):
        parse_arguments(args)


def test_rejects_removed_onnx_inference_frame() -> None:
    args = valid_args()
    args[args.index("--inference-frame") + 1] = "onnx"

    with pytest.raises(SystemExit):
        parse_arguments(args)
