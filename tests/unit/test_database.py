from conductor.repository.database import Database
from pipeline.arguments import PipelineArguments


def test_database_persists_parameters_and_process_settings(tmp_path) -> None:
    arguments = PipelineArguments(
        "rtsp://in", "tcp", "rtsp://out", "udp", "nvidia", 1,
        True, "metadata.py", True, "inference.py", 10, "pytorch", True, "postprocess.py",
    )
    database = Database(tmp_path / "pipe-works.sqlite3")
    database.save_process("camera-001", True, arguments)

    record = database.get_process("camera-001")
    assert record is not None
    assert record["process_id"] == "camera-001"
    assert record["auto_start"] is True
    assert record["input_rtsp_url"] == "rtsp://in"
    assert record["inference_frame"] == "pytorch"
    assert record["postprocess_path"] == "postprocess.py"
    assert record["fps"] == 30
    assert record["gpu_id"] == 1
