from functools import partial
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import torch
from pipeworks import local_yolo_inference as batch
infer = partial(batch.infer, backend="tensorrt")


@unittest.skipUnless(torch.cuda.is_available(), "CUDA가 필요합니다.")
class BatchTests(unittest.TestCase):
    def test_delayed_producers_without_cpu_event_wait(self):
        class Session:
            def __init__(self, *args):
                pass

            def infer(self, inputs, stream, context):
                return {"output": inputs * 2}

            def close(self):
                pass

        with TemporaryDirectory() as directory:
            path = Path(directory) / "delayed.plan"
            path.write_bytes(b"test")
            path.with_suffix(".yml").write_text(
                "max_batch_size: 2\nmax_batch_wait_ms: 1000", encoding="utf-8"
            )
            requests = []
            for number in (3, 7):
                producer = torch.cuda.Stream()
                with torch.cuda.stream(producer):
                    value = torch.zeros((1, 3), device="cuda")
                producer.synchronize()
                with torch.cuda.stream(producer):
                    torch.cuda._sleep(20_000_000)
                    value.fill_(number)
                    ready = torch.cuda.Event()
                    ready.record(producer)
                requests.append((value, ready))
            with (
                patch(
                    "torch.cuda.Event.synchronize",
                    side_effect=AssertionError("CPU input wait"),
                ),
                patch.object(batch, "_EngineSession", Session),
                ThreadPoolExecutor(2) as executor,
            ):
                futures = [
                    executor.submit(infer, path, value, ready_event=ready)
                    for value, ready in requests
                ]
                outputs = [future.result(timeout=5)["output"] for future in futures]
            for number, output in zip((3, 7), outputs):
                torch.testing.assert_close(
                    output, torch.full((1, 3), number * 2.0, device="cuda")
                )

    def test_loaded_session_survives_file_deletion_but_reload_checks_file(self):
        loaded, broken = [], [False]

        class Session:
            def __init__(self, path, *args):
                path.read_bytes()
                loaded.append(path)

            def infer(self, inputs, stream, context):
                if broken[0]:
                    raise RuntimeError("engine failed")
                return {"output": inputs + 1}

            def close(self):
                pass

        with TemporaryDirectory() as directory:
            path = Path(directory) / "cached.plan"
            path.write_bytes(b"engine")
            value = torch.ones((1, 3), device="cuda")
            with patch.object(batch, "_EngineSession", Session):
                first = infer(path, value)
                path.unlink()
                with (
                    patch.object(
                        Path, "resolve", side_effect=AssertionError("resolve")
                    ),
                    patch.object(
                        Path, "is_file", side_effect=AssertionError("is_file")
                    ),
                ):
                    second = infer(path, value)
                torch.testing.assert_close(first["output"], second["output"])
                self.assertEqual(loaded, [path])
                broken[0] = True
                with self.assertRaisesRegex(RuntimeError, "engine failed"):
                    infer(path, value)
                broken[0] = False
                with self.assertRaisesRegex(RuntimeError, "FileNotFoundError"):
                    infer(path, value)
                path.write_bytes(b"restored")
                torch.testing.assert_close(
                    infer(path, value)["output"], value + 1
                )
                self.assertEqual(loaded, [path, path])

    def test_profiles_are_not_mixed_and_failed_session_is_isolated(self):
        created, calls = [], []
        broken = [False]

        class Session:
            def __init__(self, path, profile_index):
                self.profile_index = profile_index
                created.append(profile_index)

            def infer(self, inputs, stream, context):
                calls.append((self.profile_index, inputs.shape[0]))
                if broken[0] and self.profile_index == 1:
                    raise RuntimeError("profile one failed")
                return {"output": inputs + self.profile_index}

            def close(self):
                pass

        with TemporaryDirectory() as directory:
            path = Path(directory) / "profiles.plan"
            path.write_bytes(b"test")
            path.with_suffix(".yml").write_text(
                "max_batch_size: 2\nmax_batch_wait_ms: 50", encoding="utf-8"
            )
            value = torch.ones((1, 3), device="cuda")
            torch.cuda.synchronize()
            with patch.object(batch, "_EngineSession", Session):
                with ThreadPoolExecutor(2) as executor:
                    futures = [
                        executor.submit(infer, path, value, profile_index=index)
                        for index in (0, 1)
                    ]
                    results = [future.result(timeout=5) for future in futures]
                torch.testing.assert_close(results[0]["output"], value)
                torch.testing.assert_close(results[1]["output"], value + 1)
                self.assertEqual(sorted(calls), [(0, 1), (1, 1)])
                broken[0] = True
                with self.assertRaisesRegex(RuntimeError, "profile one failed"):
                    infer(path, value, profile_index=1)
                infer(path, value, profile_index=0)
                self.assertEqual(sorted(created), [0, 1])
                broken[0] = False
                infer(path, value, profile_index=1)
                self.assertEqual(sorted(created), [0, 1, 1])
                for invalid in (-1, True, 1.5, "1", None):
                    with self.assertRaisesRegex(ValueError, "profile_index"):
                        infer(path, value, profile_index=invalid)

    def test_collects_and_splits_gpu_requests(self):
        calls = []
        settings = []

        class Session:
            def __init__(self, *args):
                settings.append(args)

            def infer(self, inputs, stream, context):
                calls.append(tuple(inputs.shape))
                return {"output": inputs * 2}

            def close(self):
                pass

        with TemporaryDirectory() as directory:
            path = Path(directory) / "model.plan"
            path.write_bytes(b"test")
            path.with_suffix(".yml").write_text(
                "max_batch_size: 2\nmax_batch_wait_ms: 1000",
                encoding="utf-8",
            )
            a, b = (
                torch.ones((1, 3), device="cuda"),
                torch.full((1, 3), 2.0, device="cuda"),
            )
            torch.cuda.synchronize()
            with (
                patch.object(batch, "_EngineSession", Session),
                ThreadPoolExecutor(2) as executor,
            ):
                futures = [
                    executor.submit(infer, path, value, profile_index=1)
                    for value in (a, b)
                ]
                outputs = [f.result(timeout=5) for f in futures]
            self.assertEqual(calls, [(2, 3)])
            self.assertEqual(
                settings, [(path.resolve(), 1)]
            )
            torch.testing.assert_close(outputs[0]["output"], a * 2)
            torch.testing.assert_close(outputs[1]["output"], b * 2)
            self.assertEqual(tuple(outputs[0]["output"].shape), (1, 3))

    def test_invalid_output_recovers_for_next_request(self):
        broken = [True]

        class Session:
            def __init__(self, *args):
                pass

            def infer(self, inputs, stream, context):
                return {"output": inputs[:0] if broken[0] else inputs + 1}

            def close(self):
                pass

        with TemporaryDirectory() as directory:
            path = Path(directory) / "model.plan"
            path.write_bytes(b"test")
            value = torch.ones((1, 3), device="cuda")
            with patch.object(batch, "_EngineSession", Session):
                with self.assertRaisesRegex(RuntimeError, "batch axis"):
                    infer(path, value)
                broken[0] = False
                result = infer(path, value)
            torch.testing.assert_close(result["output"], value + 1)


class SettingsTests(unittest.TestCase):
    def test_settings(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "model.plan"
            self.assertEqual(batch._settings(path), (1, 0.0))
            path.with_suffix(".yml").write_text(
                "max_batch_wait_ms: 25", encoding="utf-8"
            )
            self.assertEqual(
                batch._settings(path), (1, 0.025)
            )
            for text in (
                "max_batch_size: 0",
                "max_batch_wait_ms: -1",
                "[]",
                "timeout: 20",
                "profile_index: 0",
                "max_batch_wait_ms: true",
                "max_batch_wait_ms: .inf",
                'max_batch_wait_ms: "1"',
                "max_batch_wait_ms: null",
            ):
                path.with_suffix(".yml").write_text(text, encoding="utf-8")
                with self.assertRaises(ValueError):
                    batch._settings(path)
