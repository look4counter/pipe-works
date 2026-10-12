import builtins
import sys
import tempfile
import unittest
from pathlib import Path
from queue import Queue
from unittest.mock import Mock, patch

import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from pipeworks import Backend
from pipeworks.embedded import YoloInference
from pipeworks.models import PipelineContext


class BackendConfigTests(unittest.TestCase):
    def test_torchscript_is_library_independent_and_yaml_overrides(self):
        from types import SimpleNamespace

        step = YoloInference("model.pt", backend=Backend.TORCHSCRIPT)
        self.assertEqual(step.backend, "torchscript")
        step.configure(SimpleNamespace(backend="ultralytics"))
        self.assertEqual(step.backend, "ultralytics")
        step.configure(SimpleNamespace())
        self.assertEqual(step.backend, "torchscript")

    def test_invalid_backend_names(self):
        for value in (None, "", " ", "auto", 4, "module:", ":Class"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                YoloInference("model.pt", backend=value)

    def test_cpu_and_missing_cuda_fail_before_loading(self):
        from pipeworks.yolo_backend import load_backend

        with (
            patch("torch.cuda.is_available", return_value=False),
            self.assertRaisesRegex(RuntimeError, "CUDA"),
        ):
            load_backend("missing.pt", 0, "torchscript")
        item = PipelineContext(model_input={"images": torch.zeros(1, 3)})
        with self.assertRaisesRegex(ValueError, "GPU"):
            YoloInference("missing.pt", backend=Backend.TORCHSCRIPT)._prepare_inputs(item)

    def test_caches_are_separated_by_backend(self):
        from pipeworks import local_yolo_inference as shared

        with tempfile.TemporaryDirectory() as directory:
            model = Path(directory) / "model.pt"
            model.touch()
            with patch.object(shared, "_ModelWorker") as create:
                create.side_effect = lambda p, backend: Mock(backend=backend)
                first = shared._worker(model, "torchscript")
                second = shared._worker(model, "ultralytics")
                again = shared._worker(model, "torchscript")
                self.assertIs(first, again)
                self.assertIsNot(first, second)
                self.assertEqual(create.call_count, 2)


@unittest.skipUnless(torch.cuda.is_available(), "CUDA가 필요합니다.")
class GpuBackendTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.model_path = Path(self.directory.name) / "model.pt"
        self.stream = torch.cuda.Stream(device=0)

    def save(self, module, inputs):
        torch.jit.trace(module.cuda().eval(), inputs, strict=False).save(
            str(self.model_path)
        )

    def execute(self, inputs, **kwargs):
        item = PipelineContext(model_input=inputs, cuda_stream=self.stream)
        return next(YoloInference(self.model_path, backend=kwargs.pop("backend", Backend.TORCHSCRIPT), **kwargs).process(iter([item])))

    def test_multichannel_named_multi_input_and_output_without_ultralytics(self):
        class Model(torch.nn.Module):
            def forward(self, image, offsets):
                return {"scores": image + offsets, "features": image * 2}

        with torch.cuda.stream(self.stream):
            image = torch.ones(1, 5, 4, device="cuda")
            offsets = torch.full((1, 5, 4), 3.0, device="cuda")
            self.save(Model(), (image, offsets))
        original_import = builtins.__import__

        def guarded_import(name, *args, **kwargs):
            if name == "ultralytics" or name.startswith("ultralytics."):
                raise AssertionError("특정 YOLO 라이브러리를 가져왔습니다.")
            return original_import(name, *args, **kwargs)

        with (
            patch("builtins.__import__", side_effect=guarded_import),
            patch.object(torch.Tensor, "cpu", side_effect=AssertionError("CPU 복사")),
        ):
            output = self.execute({"image": image, "offsets": offsets}).model_output
        self.assertEqual(set(output), {"scores", "features"})
        self.assertTrue(torch.all(output["scores"] == 4))
        self.assertTrue(torch.all(output["features"] == 2))
        self.assertTrue(all(t.device == image.device for t in output.values()))

    def test_integer_input_and_non_image_shape(self):
        class Model(torch.nn.Module):
            def forward(self, tokens):
                return tokens + 1

        with torch.cuda.stream(self.stream):
            tokens = torch.ones((1, 6), dtype=torch.int64, device="cuda")
            self.save(Model(), tokens)
        output = self.execute(tokens).model_output["output0"]
        self.assertEqual(output.dtype, torch.int64)
        self.assertTrue(torch.all(output == 2))

    def test_cpu_transition_is_rejected_even_if_output_returns_to_gpu(self):
        class Model(torch.nn.Module):
            def forward(self, image):
                return image.cpu().cuda()

        with torch.cuda.stream(self.stream):
            image = torch.ones(1, 5, device="cuda")
            self.save(Model(), image)
        with self.assertRaisesRegex((ValueError, RuntimeError), "GPU|CPU"):
            self.execute(image)

    def session(self, output):
        from pipeworks.embedded.yolo_inference import _Session

        session = object.__new__(_Session)
        session.gpu_id = 0
        session.backend = Mock()
        session.backend.infer.return_value = output
        return session

    def test_all_nested_outputs_are_preserved_and_owned(self):
        with torch.cuda.stream(self.stream):
            image = torch.ones(1, 5, device="cuda")
            prediction = image * 2
            outputs = (prediction, {"features": [image, image + 1]})
            session = self.session(outputs)
            result = session.infer(image, self.stream)
            prediction.zero_()
            image.zero_()
        self.stream.synchronize()
        self.assertEqual(
            set(result),
            {"output0", "output1/features/output0", "output1/features/output1"},
        )
        self.assertTrue(torch.all(result["output0"] == 2))
        self.assertTrue(torch.all(result["output1/features/output0"] == 1))

    def test_invalid_outputs_and_name_collision(self):
        with torch.cuda.stream(self.stream):
            image = torch.ones(1, 5, device="cuda")
        for output in (
            None,
            [],
            {"empty": []},
            {"bad": 3},
            torch.ones(1),
            {"a/b": image, "a": {"b": image}},
        ):
            with self.subTest(output=output), self.assertRaises(ValueError):
                self.session(output).infer(image, self.stream)

    def test_single_scalar_output_is_valid(self):
        with torch.cuda.stream(self.stream):
            image = torch.ones(1, 5, device="cuda")
            scalar = image.sum()
            output = self.session({"total": scalar}).infer(image, self.stream)
        self.assertEqual(output["total"].ndim, 0)

    def test_custom_backend_does_not_silently_copy_cpu_results(self):
        from pipeworks.yolo_backend import GpuOnly

        image = torch.ones(1, device="cuda")
        with GpuOnly(0), self.assertRaisesRegex(ValueError, "GPU|CPU"):
            image.to("cpu")
        with GpuOnly(0), self.assertRaisesRegex(ValueError, "GPU|CPU"):
            torch.ones(1)

    def test_custom_backend_factory_and_cpu_scalar_read_rejection(self):
        from types import ModuleType

        module = ModuleType("test_custom_gpu_backend")

        class Backend:
            def __init__(self, model_path, gpu_id):
                self.gpu_id = gpu_id

            def infer(self, inputs):
                return {"custom": inputs["left"] + inputs["right"]}

        module.Backend = Backend
        self.model_path.touch()
        with torch.cuda.stream(self.stream):
            left = torch.ones(1, 5, device="cuda")
            right = torch.ones(1, 5, device="cuda")
        with patch.dict(sys.modules, {"test_custom_gpu_backend": module}):
            output = self.execute(
                {"left": left, "right": right},
                backend="test_custom_gpu_backend:Backend",
            ).model_output
        self.assertTrue(torch.all(output["custom"] == 2))
        from pipeworks.yolo_backend import GpuOnly

        with GpuOnly(0), self.assertRaisesRegex(ValueError, "CPU"):
            left.sum().item()

    def test_shared_torchscript_model_runs_without_library(self):
        class Model(torch.nn.Module):
            def forward(self, left, right):
                return {"scores": left + right, "features": left * 2}

        with torch.cuda.stream(self.stream):
            inputs = torch.ones(1, 5, device="cuda")
            self.save(Model(), (inputs, inputs))
        result = self.execute(
            {"left": inputs, "right": inputs}, batch=True
        ).model_output
        self.assertEqual(set(result), {"scores", "features"})
        self.assertTrue(torch.all(result["scores"] == 2))

    def requests(self):
        from pipeworks.local_yolo_inference import _Request

        requests = []
        with torch.cuda.stream(self.stream):
            for value in (1, 2):
                inputs = {
                    "image": torch.full((1, 5), float(value), device="cuda"),
                    "offsets": torch.ones(1, 5, device="cuda"),
                }
                ready = torch.cuda.Event()
                ready.record(self.stream)
                requests.append(_Request(inputs, 0, (), ready, backend="torchscript"))
        return requests

    def worker(self):
        from pipeworks.local_yolo_inference import _ModelWorker

        worker = object.__new__(_ModelWorker)
        worker.path, worker.backend, worker.size, worker.timeout = (
            self.model_path,
            "torchscript",
            4,
            0,
        )
        worker.requests = Queue()
        return worker

    def test_shared_multi_input_splits_all_outputs(self):
        from pipeworks import local_yolo_inference as shared

        requests = self.requests()
        backend = Mock()
        backend.infer.side_effect = lambda inputs, stream: {
            "scores": inputs["image"] + inputs["offsets"],
            "features": inputs["image"] * 2,
        }
        with (
            patch.object(
                shared, "collect_batch", side_effect=[requests, StopIteration]
            ),
            patch.object(shared, "_Session", return_value=backend),
            self.assertRaises(StopIteration),
        ):
            self.worker()._run()
        for request, value in zip(requests, (1, 2)):
            self.assertTrue(request.done.is_set())
            self.assertIsNone(request.error)
            self.assertTrue(torch.all(request.result["scores"] == value + 1))
            self.assertTrue(torch.all(request.result["features"] == value * 2))
        self.assertNotEqual(
            requests[0].result["features"].data_ptr(),
            requests[1].result["features"].data_ptr(),
        )

    def test_shared_invalid_output_axis_wakes_every_request(self):
        from pipeworks import local_yolo_inference as shared

        for shape in ((), (1, 4)):
            requests = self.requests()
            backend = Mock()
            backend.infer.return_value = {"wrong": torch.ones(shape, device="cuda")}
            with (
                patch.object(
                    shared, "collect_batch", side_effect=[requests, StopIteration]
                ),
                patch.object(shared, "_Session", return_value=backend),
                self.assertRaises(StopIteration),
            ):
                self.worker()._run()
            for request in requests:
                self.assertTrue(request.done.is_set())
                self.assertIsNone(request.result)
                self.assertIn("배치", request.error)


if __name__ == "__main__":
    unittest.main()
