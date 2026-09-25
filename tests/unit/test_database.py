import sqlite3

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


def test_database_migrates_legacy_cpu_record_and_missing_fps(tmp_path) -> None:
    database_path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.execute("""
            CREATE TABLE processes (
                process_id TEXT PRIMARY KEY, auto_start INTEGER,
                input_rtsp_url TEXT, input_rtsp_transport TEXT,
                output_rtsp_url TEXT, output_rtsp_transport TEXT,
                pipe_type TEXT, gpu_id INTEGER, runtime_pid INTEGER,
                metadata_enabled INTEGER, metadata_path TEXT,
                inference_enabled INTEGER, inference_path TEXT,
                inference_interval INTEGER, inference_frame TEXT,
                postprocess_enabled INTEGER, postprocess_path TEXT
            )
        """)
        connection.execute("""
            INSERT INTO processes VALUES (
                'legacy-camera', 0, 'rtsp://in', 'tcp', 'rtsp://out', 'tcp',
                'cpu', NULL, 4321, 0, NULL, 0, NULL, NULL, 'onnx', 0, NULL
            )
        """)

    Database(database_path)

    with sqlite3.connect(database_path) as connection:
        record = connection.execute(
            "SELECT pipe_type, gpu_id, fps, inference_interval, inference_frame, runtime_pid "
            "FROM processes WHERE process_id = ?",
            ("legacy-camera",),
        ).fetchone()

    assert record == ("nvidia", 0, 30, 3, "pytorch", None)
