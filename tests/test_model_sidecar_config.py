from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch
import yaml

from pipeworks import Backend
from pipeworks.embedded import YoloInference
from pipeworks import local_yolo_inference as shared
from pipeworks.models import PipelineContext
from pipeworks.yolo_backend import batch_settings
from pipeworks.yolo_backends.tensorrt import _load_model_config


class ModelSidecarConfigTests(unittest.TestCase):
    def test_missing_sidecar_uses_defaults_and_ignores_yaml_extension(self):
        with TemporaryDirectory() as directory:
            model = Path(directory) / "model.plan"
            model.with_suffix(".yaml").write_text("[invalid", encoding="utf-8")
            self.assertEqual(batch_settings(model), (1, 0.0))
            self.assertEqual(shared._settings(model), (1, 0.0))
            self.assertEqual(_load_model_config(model), {})

    def test_sidecar_uses_model_name_and_directory(self):
        with TemporaryDirectory() as directory:
            model = Path(directory) / "model.plan"
            model.with_suffix(".yml").write_text(
                "max_batch_size: 4\nmax_batch_wait_ms: 25\n", encoding="utf-8"
            )
            for load in (batch_settings, shared._settings):
                self.assertEqual(load(model), (4, 0.025))
            self.assertEqual(_load_model_config(model)["max_batch_size"], 4)
            self.assertEqual(list(YoloInference(model, backend=Backend.TENSORRT).process(iter(()))), [])

    def test_removed_config_path_is_rejected(self):
        with self.assertRaises(TypeError):
            YoloInference("model.pt", backend=Backend.TORCHSCRIPT, config_path="other.yml")
        with self.assertRaises(TypeError):
            shared.infer("model.pt", object(), config_path="other.yml")

    def test_batch_wait_validation_and_old_names(self):
        with TemporaryDirectory() as directory:
            model = Path(directory) / "model.plan"
            config = model.with_suffix(".yml")
            for load in (batch_settings, shared._settings):
                for key in ("timeout", "timeout_ms", "batch_timeout_ms"):
                    config.write_text(f"max_batch_size: 2\n{key}: 25\n", encoding="utf-8")
                    with self.subTest(load=load, key=key), self.assertRaisesRegex(ValueError, "max_batch_wait_ms"):
                        load(model)
                for value in ("-1", "true", ".inf", ".nan", "null", "'25'"):
                    config.write_text(f"max_batch_size: 2\nmax_batch_wait_ms: {value}\n", encoding="utf-8")
                    with self.subTest(load=load, value=value), self.assertRaises(ValueError):
                        load(model)
                for value in (0, 25, 0.5):
                    config.write_text(f"max_batch_size: 2\nmax_batch_wait_ms: {value}\n", encoding="utf-8")
                    self.assertEqual(load(model), (2, value / 1000))

    def test_invalid_sidecar_is_an_error(self):
        with TemporaryDirectory() as directory:
            model = Path(directory) / "model.plan"
            for text in ("[invalid", "[]", ""):
                model.with_suffix(".yml").write_text(text, encoding="utf-8")
                for load in (batch_settings, shared._settings):
                    with self.subTest(load=load, text=text), self.assertRaises((ValueError, yaml.YAMLError)):
                        load(model)

    def test_workers_reuse_model_aliases_and_separate_backends(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "sub").mkdir()
            model = root / "model.pt"
            model.touch()
            with (
                patch.dict(shared._workers, {}, clear=True),
                patch.dict(shared._worker_paths, {}, clear=True),
                patch.object(shared, "_ModelWorker", side_effect=lambda *a: Mock()) as create,
            ):
                first = shared._worker(model, "torchscript")
                self.assertIs(first, shared._worker(root / "sub/../model.pt", "torchscript"))
                self.assertIsNot(first, shared._worker(model, "ultralytics"))
                self.assertEqual(create.call_count, 2)

    def test_batch_step_only_forwards_model_path(self):
        for backend in (Backend.TORCHSCRIPT, Backend.TENSORRT):
            with self.subTest(backend=backend):
                step = YoloInference("model.pt", backend=backend, batch=True)
                item = PipelineContext()
                with (
                    patch.object(step, "_prepare_inputs", return_value=(Mock(), Mock())),
                    patch.object(shared, "infer", return_value={}) as infer,
                ):
                    self.assertEqual(list(step.process(iter([item]))), [item])
                self.assertEqual(infer.call_args.args[0], Path("model.pt"))
                self.assertNotIn("config_path", infer.call_args.kwargs)
