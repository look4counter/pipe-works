"""Conductor 프로세스 정의를 저장하는 SQLite 저장소."""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from typing import Generator

from pipeline.arguments import PipelineArguments


class Database:
    def __init__(self, database_path: Path | str | None = None) -> None:
        self._database_path = (
            Path(database_path) if database_path else self._default_path()
        )
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS processes (
                    process_id TEXT PRIMARY KEY NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    display_order INTEGER NOT NULL DEFAULT 0,
                    auto_start INTEGER NOT NULL CHECK (auto_start IN (0, 1)),
                    input_rtsp_url TEXT NOT NULL, input_rtsp_transport TEXT NOT NULL,
                    output_rtsp_url TEXT NOT NULL, output_rtsp_transport TEXT NOT NULL,
                    pipe_type TEXT NOT NULL CHECK (pipe_type IN ('nvidia', 'bypass')),
                    gpu_id INTEGER NOT NULL DEFAULT 0, fps INTEGER NOT NULL DEFAULT 30,
                    metadata_enabled INTEGER NOT NULL CHECK (metadata_enabled IN (0, 1)), metadata_path TEXT,
                    inference_enabled INTEGER NOT NULL CHECK (inference_enabled IN (0, 1)), inference_path TEXT,
                    inference_interval INTEGER NOT NULL DEFAULT 3, inference_frame TEXT CHECK (inference_frame IN ('pytorch')),
                    postprocess_enabled INTEGER NOT NULL CHECK (postprocess_enabled IN (0, 1)), postprocess_path TEXT,
                    log_level TEXT NOT NULL DEFAULT 'INFO' CHECK (log_level IN ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'))
                )
            """)
            legacy_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(processes)").fetchall()
            }
            table_sql = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'processes'"
            ).fetchone()["sql"]
            if "bypass" not in table_sql.lower():
                connection.execute("ALTER TABLE processes RENAME TO processes_legacy")
                connection.execute("""CREATE TABLE processes (
                    process_id TEXT PRIMARY KEY NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    display_order INTEGER NOT NULL DEFAULT 0,
                    auto_start INTEGER NOT NULL CHECK (auto_start IN (0, 1)),
                    input_rtsp_url TEXT NOT NULL, input_rtsp_transport TEXT NOT NULL,
                    output_rtsp_url TEXT NOT NULL, output_rtsp_transport TEXT NOT NULL,
                    pipe_type TEXT NOT NULL CHECK (pipe_type IN ('nvidia', 'bypass')),
                    gpu_id INTEGER NOT NULL DEFAULT 0, fps INTEGER NOT NULL DEFAULT 30,
                    metadata_enabled INTEGER NOT NULL CHECK (metadata_enabled IN (0, 1)), metadata_path TEXT,
                    inference_enabled INTEGER NOT NULL CHECK (inference_enabled IN (0, 1)), inference_path TEXT,
                    inference_interval INTEGER NOT NULL DEFAULT 3, inference_frame TEXT CHECK (inference_frame IN ('pytorch')),
                    postprocess_enabled INTEGER NOT NULL CHECK (postprocess_enabled IN (0, 1)), postprocess_path TEXT,
                    log_level TEXT NOT NULL DEFAULT 'INFO' CHECK (log_level IN ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'))
                )""")
                old_columns = {
                    row["name"] for row in connection.execute(
                        "PRAGMA table_info(processes_legacy)"
                    ).fetchall()
                }
                new_columns = [
                    "process_id", "description", "display_order", "auto_start", "input_rtsp_url", "input_rtsp_transport",
                    "output_rtsp_url", "output_rtsp_transport", "pipe_type", "gpu_id", "fps",
                    "metadata_enabled", "metadata_path", "inference_enabled", "inference_path",
                    "inference_interval", "inference_frame", "postprocess_enabled", "postprocess_path",
                    "log_level",
                ]
                shared_columns = [name for name in new_columns if name in old_columns]
                columns_sql = ", ".join(shared_columns)
                legacy_expressions = {
                    "pipe_type": (
                        "CASE WHEN pipe_type IN ('nvidia', 'bypass') "
                        "THEN pipe_type ELSE 'nvidia' END"
                    ),
                    "gpu_id": "COALESCE(gpu_id, 0)",
                    "fps": "COALESCE(fps, 30)",
                    "inference_interval": "COALESCE(inference_interval, 3)",
                    "inference_frame": (
                        "CASE WHEN inference_frame = 'onnx' "
                        "THEN 'pytorch' ELSE inference_frame END"
                    ),
                    "log_level": (
                        "CASE WHEN log_level IN ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL') "
                        "THEN log_level ELSE 'INFO' END"
                    ),
                }
                select_sql = ", ".join(
                    legacy_expressions.get(name, name)
                    for name in shared_columns
                )
                connection.execute(
                    f"INSERT INTO processes ({columns_sql}) "
                    f"SELECT {select_sql} FROM processes_legacy"
                )
                connection.execute("DROP TABLE processes_legacy")
                if "display_order" not in old_columns:
                    self._initialize_display_order(connection)
                legacy_columns = set(new_columns)
                if "runtime_pid" in old_columns:
                    connection.execute(
                        "ALTER TABLE processes ADD COLUMN runtime_pid INTEGER"
                    )
                    legacy_columns.add("runtime_pid")
            if "runtime_pid" in legacy_columns:
                connection.execute("UPDATE processes SET runtime_pid = NULL")
            if "description" not in legacy_columns:
                connection.execute(
                    "ALTER TABLE processes ADD COLUMN description TEXT NOT NULL DEFAULT ''"
                )
            if "display_order" not in legacy_columns:
                connection.execute(
                    "ALTER TABLE processes ADD COLUMN display_order INTEGER NOT NULL DEFAULT 0"
                )
                self._initialize_display_order(connection)
            if "fps" not in legacy_columns:
                connection.execute(
                    "ALTER TABLE processes ADD COLUMN fps INTEGER NOT NULL DEFAULT 30"
                )
            if "log_level" not in legacy_columns:
                connection.execute(
                    "ALTER TABLE processes ADD COLUMN log_level TEXT NOT NULL DEFAULT 'INFO' "
                    "CHECK (log_level IN ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'))"
                )
            connection.execute("UPDATE processes SET fps = 30 WHERE fps IS NULL")
            connection.execute(
                "UPDATE processes SET log_level = 'INFO' "
                "WHERE log_level NOT IN ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL') "
                "OR log_level IS NULL"
            )
            connection.execute(
                "UPDATE processes SET inference_interval = 3 WHERE inference_interval IS NULL"
            )
            # Keep existing process configurations compatible with the NVIDIA default.
            connection.execute(
                "UPDATE processes SET gpu_id = COALESCE(gpu_id, 0)"
            )
            # Normalize historical unsupported pipe types to the NVIDIA default.
            connection.execute(
                "UPDATE processes SET pipe_type = 'nvidia' "
                "WHERE pipe_type NOT IN ('nvidia', 'bypass')"
            )
            # ONNX inference is not supported; normalize saved selections to
            # the only supported frame type.
            connection.execute(
                "UPDATE processes SET inference_frame = 'pytorch' "
                "WHERE inference_frame = 'onnx'"
            )

    @staticmethod
    def _default_path() -> Path:
        configured = os.environ.get("PIPE_WORKS_DB_PATH")
        if configured:
            return Path(configured)
        return Path(__file__).resolve().parents[3] / "pipe-works.db"

    @staticmethod
    def _initialize_display_order(connection: sqlite3.Connection) -> None:
        process_ids = connection.execute(
            "SELECT process_id FROM processes ORDER BY process_id"
        ).fetchall()
        connection.executemany(
            "UPDATE processes SET display_order = ? WHERE process_id = ?",
            ((order, row["process_id"]) for order, row in enumerate(process_ids)),
        )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def _connection(self) -> Generator[sqlite3.Connection]:
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def save_process(
        self,
        process_id: str,
        auto_start: bool,
        parameters: PipelineArguments,
        description: str = "",
    ) -> None:
        if not process_id.strip():
            raise ValueError("process_id는 비어 있을 수 없습니다.")
        values = {
            "process_id": process_id,
            "description": description,
            "auto_start": int(auto_start),
            "input_rtsp_url": parameters.input_rtsp_url,
            "input_rtsp_transport": parameters.input_rtsp_transport,
            "output_rtsp_url": parameters.output_rtsp_url,
            "output_rtsp_transport": parameters.output_rtsp_transport,
            "pipe_type": parameters.pipe_type,
            "gpu_id": parameters.gpu_id,
            "fps": parameters.fps,
            "metadata_enabled": int(parameters.metadata_enabled),
            "metadata_path": parameters.metadata_path,
            "inference_enabled": int(parameters.inference_enabled),
            "inference_path": parameters.inference_path,
            "inference_interval": parameters.inference_interval,
            "inference_frame": parameters.inference_frame,
            "postprocess_enabled": int(parameters.postprocess_enabled),
            "postprocess_path": parameters.postprocess_path,
            "log_level": parameters.log_level,
        }
        columns = ", ".join(values)
        placeholders = ", ".join(f":{field}" for field in values)
        updates = ", ".join(
            f"{field} = excluded.{field}"
            for field in values
            if field != "process_id"
        )
        with self._connection() as connection:
            connection.execute(
                f"INSERT INTO processes ({columns}, display_order) "
                f"VALUES ({placeholders}, "
                "(SELECT COALESCE(MAX(display_order), -1) + 1 FROM processes)) "
                f"ON CONFLICT(process_id) DO UPDATE SET {updates}",
                values,
            )

    def get_process(self, process_id: str) -> dict[str, object] | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM processes WHERE process_id = ?", (process_id,)
            ).fetchone()
        return self._to_record(row) if row else None

    def list_processes(self) -> list[dict[str, object]]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM processes ORDER BY display_order, process_id"
            ).fetchall()
        return [self._to_record(row) for row in rows]

    def reorder_processes(self, process_ids: list[str]) -> None:
        if len(process_ids) != len(set(process_ids)):
            raise ValueError("Process order contains duplicate IDs.")

        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current_ids = {
                row["process_id"]
                for row in connection.execute(
                    "SELECT process_id FROM processes"
                ).fetchall()
            }
            if set(process_ids) != current_ids:
                raise ValueError("Process order does not match the current process list.")
            connection.executemany(
                "UPDATE processes SET display_order = ? WHERE process_id = ?",
                ((order, process_id) for order, process_id in enumerate(process_ids)),
            )

    def delete_process(self, process_id: str) -> bool:
        with self._connection() as connection:
            result = connection.execute(
                "DELETE FROM processes WHERE process_id = ?", (process_id,)
            )
        return result.rowcount == 1

    @staticmethod
    def _to_record(row: sqlite3.Row) -> dict[str, object]:
        record = dict(row)
        for field in (
            "auto_start",
            "metadata_enabled",
            "inference_enabled",
            "postprocess_enabled",
        ):
            record[field] = bool(record[field])
        return record
