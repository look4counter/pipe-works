from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import torch
from pipeworks import local_tensor_rt as batch


@unittest.skipUnless(torch.cuda.is_available(), "CUDA가 필요합니다.")
class BatchTests(unittest.TestCase):
    def test_collects_and_splits_gpu_requests(self):
        calls = []

        class Session:
            def __init__(self, *args):
                pass

            def infer(self, inputs, stream, context):
                calls.append(tuple(inputs.shape))
                return {"output": inputs * 2}

            def close(self):
                pass

        with TemporaryDirectory() as directory:
            path = Path(directory) / "model.plan"
            path.write_bytes(b"test")
            path.with_suffix(".yml").write_text("max_batch_size: 2\ntimeout: 1000", encoding="utf-8")
            a, b = torch.ones((1, 3), device="cuda"), torch.full((1, 3), 2., device="cuda")
            torch.cuda.synchronize()
            with patch.object(batch, "_EngineSession", Session), ThreadPoolExecutor(2) as executor:
                futures = [executor.submit(batch.infer, path, value) for value in (a, b)]
                outputs = [f.result(timeout=5) for f in futures]
            self.assertEqual(calls, [(2, 3)])
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
                    batch.infer(path, value)
                broken[0] = False
                result = batch.infer(path, value)
            torch.testing.assert_close(result["output"], value + 1)


class SettingsTests(unittest.TestCase):
    def test_settings(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "model.plan"
            self.assertEqual(batch._settings(path), (1, 0., ()))
            for text in ("max_batch_size: 0", "timeout: -1", "plugins: wrong", "[]"):
                path.with_suffix(".yml").write_text(text, encoding="utf-8")
                with self.assertRaises(ValueError):
                    batch._settings(path)
