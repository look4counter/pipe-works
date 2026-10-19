import sys
import unittest
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from pipeworks import Backend
from pipeworks.embedded import YoloInference
from pipeworks.embedded.yolo_inference import _Session, _validate_input
from pipeworks.models import PipelineContext, Step


def gpu_tensor(shape=(1, 3, 32, 32), dtype=torch.float32, gpu=0):
    tensor = Mock(spec=torch.Tensor)
    tensor.is_cuda = True
    tensor.device = torch.device("cuda", gpu)
    tensor.dtype = dtype
    tensor.layout = torch.strided
    tensor.ndim = len(shape)
    tensor.shape = shape
    tensor.contiguous.return_value = tensor
    tensor.clone.return_value = tensor
    return tensor


class ConfigurationTests(unittest.TestCase):
    def test_backend_is_required(self):
        with self.assertRaises(TypeError):
            YoloInference("model.pt")

    def test_public_backend_enum_and_yaml_reset(self):
        from pipeworks import Backend
        from pipeworks.embedded import Backend as EmbeddedBackend

        self.assertIs(Backend, EmbeddedBackend)
        self.assertEqual(Backend.TORCHSCRIPT.value, "torchscript")
        self.assertEqual(Backend.ULTRALYTICS.value, "ultralytics")
        step = YoloInference("model.pt", backend=Backend.TORCHSCRIPT)
        self.assertIs(step.backend, Backend.TORCHSCRIPT)
        step.configure(SimpleNamespace(backend="ultralytics"))
        self.assertIs(step.backend, Backend.ULTRALYTICS)
        step.configure(SimpleNamespace())
        self.assertIs(step.backend, Backend.TORCHSCRIPT)
        step.configure(SimpleNamespace(backend="custom.runner:Runner"))
        self.assertEqual(step.backend, "custom.runner:Runner")


    def test_public_step_and_defaults(self):
        step = YoloInference("models/yolo.pt", backend=Backend.TORCHSCRIPT)
        self.assertEqual(type(step).__bases__, (Step,))
        self.assertFalse(step.batch)
        self.assertEqual(step.id, "yolo.pt")
        self.assertEqual(step.gpu_id, 0)
        self.assertFalse(hasattr(step, "inference_interval_frame"))
        self.assertFalse(hasattr(step, "confidence"))

    def test_config_overrides_and_reset(self):
        step = YoloInference(
            "model.pt", backend=Backend.TORCHSCRIPT, gpu_id=2, id="vehicle"
        )
        step.configure(SimpleNamespace(gpu_id=1, id=None))
        self.assertEqual((step.gpu_id, step.id), (1, "model.pt"))
        step.configure(SimpleNamespace())
        self.assertEqual(
            (step.gpu_id, step.id), (2, "vehicle")
        )

    def test_invalid_config(self):
        for options in (
            {"batch": 1},
            {"gpu_id": True},
            {"gpu_id": -1},
            {"id": ""},
            {"id": "  "},
            {"id": 5},
        ):
            with self.subTest(options=options), self.assertRaises(ValueError):
                YoloInference("model.pt", backend=Backend.TORCHSCRIPT, **options)

    def test_pipeline_yaml_selects_new_step_section(self):
        import tempfile

        from pipeworks import Pipeline

        step = YoloInference("model.pt", backend=Backend.TORCHSCRIPT, gpu_id=2, id="original")
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "stream.yml"
            config.write_text(
                "YoloInference:\n  gpu_id: 1\n  id: person\n", encoding="utf-8"
            )
            Pipeline("inference-config", config=config).step(step)
        self.assertEqual((step.gpu_id, step.id), (1, "person"))


class InputTests(unittest.TestCase):
    def test_valid_input(self):
        for dtype in (torch.float16, torch.float32, torch.int64, torch.uint8):
            _validate_input(gpu_tensor(dtype=dtype), 0)

    def test_invalid_inputs(self):
        for tensor in (
            None,
            {},
            torch.zeros(1, 3, 32, 32),
            gpu_tensor(gpu=1),
            gpu_tensor(()),
            gpu_tensor((0, 3, 32, 32)),
            gpu_tensor((1, 3, 0, 32)),
        ):
            with self.subTest(tensor=tensor), self.assertRaises(ValueError):
                _validate_input(tensor, 0)

    def test_shared_input_must_be_batch_one(self):
        with self.assertRaises(ValueError):
            _validate_input(gpu_tensor((2, 3, 32, 32)), 0, batch=True)

    def test_producer_stream_event_and_fallback(self):
        tensor, stream, event = gpu_tensor(), Mock(), Mock()
        stream.device = tensor.device
        item = PipelineContext(model_input=tensor)
        with (
            patch("torch.cuda.current_stream", return_value=stream),
            patch("torch.cuda.Event", return_value=event),
        ):
            result, ready = YoloInference("model.pt", backend=Backend.TORCHSCRIPT)._prepare_inputs(item)
        self.assertIs(result, tensor)
        self.assertIs(ready, event)
        self.assertIs(item.cuda_stream, stream)
        event.record.assert_called_once_with(stream)

    def test_wrong_stream_gpu(self):
        item = PipelineContext(
            model_input=gpu_tensor(),
            cuda_stream=SimpleNamespace(device=torch.device("cuda", 1)),
        )
        with self.assertRaises(ValueError):
            YoloInference("model.pt", backend=Backend.TORCHSCRIPT)._prepare_inputs(item)


class ProcessTests(unittest.TestCase):
    def stream(self):
        stream = Mock()
        stream.device = torch.device("cuda", 0)
        return stream

    def test_single_raw_output_preserves_context_and_reuses_model(self):
        step, stream = YoloInference("model.pt", backend=Backend.TORCHSCRIPT, id="vehicle"), self.stream()
        tensor, output = gpu_tensor(), {"output0": gpu_tensor((1, 84, 10))}
        detections, frame = {"other": object()}, object()
        items = [
            PipelineContext(frame=frame, detections=detections, cuda_stream=stream)
            for _ in range(2)
        ]
        with (
            patch.object(step, "_prepare_inputs", return_value=(tensor, object())),
            patch("pipeworks.embedded.yolo_inference._Session") as session,
            patch("torch.cuda.stream", side_effect=lambda s: nullcontext()),
        ):
            session.return_value.infer.return_value = output
            self.assertEqual(list(step.process(iter(items))), items)
        self.assertEqual(session.call_count, 1)
        self.assertEqual(session.return_value.infer.call_count, 2)
        for item in items:
            self.assertIs(item.model_output, output)
            self.assertEqual(item.model_id, "vehicle")
            self.assertIs(item.frame, frame)
            self.assertIs(item.detections, detections)
        self.assertGreaterEqual(stream.synchronize.call_count, 2)

    def test_every_input_is_inferred_in_both_modes(self):
        for batch in (False, True):
            step, stream = (
                YoloInference("model.pt", backend=Backend.TORCHSCRIPT, batch=batch),
                self.stream(),
            )
            items = [
                PipelineContext(cuda_stream=stream, model_output="stale")
                for _ in range(3)
            ]
            tensor, output = gpu_tensor(), {"output0": gpu_tensor((1, 84, 10))}
            with (
                patch.object(
                    step, "_prepare_inputs", return_value=(tensor, object())
                ) as prepare,
                patch("pipeworks.embedded.yolo_inference._Session") as session,
                patch("pipeworks.local_yolo_inference.infer", return_value=output),
                patch("torch.cuda.stream", side_effect=lambda s: nullcontext()),
            ):
                session.return_value.infer.return_value = output
                self.assertEqual(list(step.process(iter(items))), items)
            self.assertEqual(prepare.call_count, 3)
            self.assertIs(items[1].model_output, output)
            self.assertEqual(items[1].model_id, "model.pt")

    def test_failure_passes_original_and_clears_stale_output(self):
        for batch in (False, True):
            step, stream = YoloInference("model.pt", backend=Backend.TORCHSCRIPT, batch=batch), self.stream()
            item = PipelineContext(cuda_stream=stream, model_output="stale")
            with (
                patch.object(
                    step, "_prepare_inputs", return_value=(gpu_tensor(), object())
                ),
                patch("pipeworks.embedded.yolo_inference._Session") as session,
                patch(
                    "pipeworks.local_yolo_inference.infer",
                    side_effect=RuntimeError("failed"),
                ),
                patch("torch.cuda.stream", side_effect=lambda s: nullcontext()),
            ):
                session.return_value.infer.side_effect = RuntimeError("failed")
                self.assertEqual(list(step.process(iter([item]))), [item])
            self.assertIsNone(item.model_output)

    def test_empty_input_does_not_load_model(self):
        with patch("pipeworks.embedded.yolo_inference._Session") as session:
            self.assertEqual(list(YoloInference("missing.pt", backend=Backend.TORCHSCRIPT).process(iter([]))), [])
        session.assert_not_called()


class SessionTests(unittest.TestCase):
    def session(self, result):
        session = object.__new__(_Session)
        session.gpu_id = 0
        session.backend = Mock()
        session.backend.infer.return_value = result
        return session

    def test_all_prediction_outputs_are_preserved(self):
        input_tensor, prediction = gpu_tensor(), gpu_tensor((1, 84, 10))
        session = self.session((prediction, [prediction]))
        output = session.infer(input_tensor, Mock())
        self.assertEqual(output, {"output0": prediction, "output1/output0": prediction})
        session.backend.infer.assert_called_once_with(input_tensor)

    def test_invalid_outputs(self):
        for result in (
            None,
            [],
            ([],),
            torch.zeros(1, 84, 10),
            gpu_tensor((1, 84, 10), gpu=1),
        ):
            with self.subTest(result=result), self.assertRaises(ValueError):
                self.session(result).infer(gpu_tensor(), Mock())


class SharedRequestTests(unittest.TestCase):
    def test_shared_request_key_callbacks_and_result(self):
        from pipeworks import local_yolo_inference as shared

        observed = []
        output = {"output0": object()}
        worker, callback, profile_callback = Mock(), Mock(), Mock()

        def complete(request):
            observed.append(request)
            request.result = output
            request.inference_seconds = 0.25
            request.profile = object()
            request.done.set()

        worker.requests.put.side_effect = complete
        with patch.object(shared, "get_model_worker", return_value=worker):
            result = shared.infer(
                "model.pt",
                gpu_tensor(),
                ready_event=object(),
                on_inference_complete=callback,
                on_profile_complete=profile_callback,
            )
        self.assertIs(result, output)
        self.assertEqual(
            observed[0].key, ("torchscript", 0, 0, (None, torch.float32, (3, 32, 32)))
        )
        callback.assert_called_once_with(0.25)
        profile_callback.assert_called_once_with(observed[0].profile)

    def test_shared_request_errors_propagate(self):
        from pipeworks import local_yolo_inference as shared

        worker, callback = Mock(), Mock()

        def fail(request):
            request.error = "model failed"
            request.done.set()

        worker.requests.put.side_effect = fail
        with (
            patch.object(shared, "get_model_worker", return_value=worker),
            self.assertRaisesRegex(RuntimeError, "model failed"),
        ):
            shared.infer(
                "model.pt",
                gpu_tensor(),
                ready_event=object(),
                on_inference_complete=callback,
            )
        callback.assert_not_called()

    def test_shared_validation_precedes_worker_lookup(self):
        from pipeworks import local_yolo_inference as shared

        with patch.object(shared, "get_model_worker") as lookup:
            for tensor, gpu in (
                (gpu_tensor(), True),
                (gpu_tensor(), -1),
                (gpu_tensor((2, 3, 32, 32)), 0),
                (None, 0),
            ):
                with self.assertRaises(ValueError):
                    shared.infer("model.pt", tensor, gpu, ready_event=object())
        lookup.assert_not_called()

    def test_cuda_async_recognizes_yolo_inference_timeout_and_busy(self):
        from threading import Event

        from pipeworks.embedded import CudaAsync
        from pipeworks.embedded.stream_report import report_scope
        from pipeworks.embedded.yolo_report import begin, store
        from pipeworks.execution import release_frame

        entered, unblock = Event(), Event()

        class SlowInference(YoloInference):
            def process(self, inputs):
                for item in inputs:
                    profile = begin("TORCHSCRIPT")
                    release_frame()
                    entered.set()
                    unblock.wait(3)
                    profile.finish()
                    yield item

        wrapper = CudaAsync(SlowInference("model.pt", backend=Backend.TORCHSCRIPT), timeout_ms=100)
        with report_scope():
            stats = store()
            stats.activate("TORCHSCRIPT")
            items = [PipelineContext(), PipelineContext()]
            try:
                self.assertEqual(list(wrapper.process(iter(items))), items)
                self.assertTrue(entered.is_set())
            finally:
                unblock.set()
                self.assertTrue(wrapper._session_lock.acquire(timeout=3))
                wrapper._session_lock.release()
            self.assertEqual(
                stats.snapshot("TORCHSCRIPT", 0)["states"],
                {"completed": 1, "timeout": 1, "busy": 1},
            )


@unittest.skipUnless(torch.cuda.is_available(), "CUDA가 필요합니다.")
class CudaTests(unittest.TestCase):
    def test_actual_yolo_backend_returns_raw_predictions(self):
        import tempfile

        import ultralytics
        from ultralytics import YOLO

        config = Path(ultralytics.__file__).parent / "cfg/models/11/yolo11.yaml"
        with tempfile.TemporaryDirectory() as directory:
            weights = Path(directory) / "test.pt"
            YOLO(str(config), task="detect", verbose=False).save(weights)
            stream = torch.cuda.Stream()
            with torch.cuda.stream(stream):
                tensor = torch.zeros(2, 3, 32, 32, device="cuda")
            item = PipelineContext(model_input=tensor, cuda_stream=stream)
            result = next(
                YoloInference(weights, backend=Backend.ULTRALYTICS).process(iter([item]))
            )
            prediction = result.model_output["output0"]
            self.assertEqual(prediction.shape[:2], (2, 84))
            self.assertTrue(prediction.is_cuda)
            self.assertIs(result.model_input, tensor)
            self.assertFalse(hasattr(result, "detections"))
            sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))
            from step.yolo_post_process import YoloPostProcess
            from step.yolo_pre_process import YoloPreProcess

            with torch.cuda.stream(stream):
                frame = torch.full((6, 8), 128, dtype=torch.uint8, device="cuda")
                frame[:4] = 16
            context = PipelineContext(
                frame=frame,
                pixel_format="NV12",
                cuda_stream=stream,
                video_stream=SimpleNamespace(
                    codec_context=SimpleNamespace(height=4, width=8)
                ),
            )
            prepared = YoloPreProcess(size=(32, 32)).process(iter([context]))
            predictions = YoloInference(
                weights, backend=Backend.ULTRALYTICS, id="vehicle"
            ).process(prepared)
            processed = next(YoloPostProcess().process(predictions))
            self.assertIs(processed.frame, frame)
            self.assertIn("vehicle", processed.detections)
            self.assertEqual(processed.detections["vehicle"].orig_shape, (4, 8))
            self.assertFalse(hasattr(processed, "model_input"))
            self.assertFalse(hasattr(processed, "model_output"))

    def test_ultralytics_precision_changes_remain_on_gpu(self):
        import tempfile

        import ultralytics
        from ultralytics import YOLO

        config = Path(ultralytics.__file__).parent / "cfg/models/11/yolo11.yaml"
        with tempfile.TemporaryDirectory() as directory:
            weights = Path(directory) / "test.pt"
            YOLO(str(config), task="detect", verbose=False).save(weights)
            stream = torch.cuda.Stream()
            dtypes = (torch.float32, torch.float16, torch.float32)
            with torch.cuda.stream(stream):
                items = [
                    PipelineContext(
                        model_input=torch.zeros(
                            1, 3, 32, 32, device="cuda", dtype=dtype
                        ),
                        cuda_stream=stream,
                    )
                    for dtype in dtypes
                ]
            output = list(
                YoloInference(weights, backend=Backend.ULTRALYTICS).process(iter(items))
            )
            self.assertEqual(len(output), 3)
            for item, dtype in zip(output, dtypes):
                self.assertEqual(item.model_output["output0"].dtype, dtype)
                self.assertTrue(
                    all(tensor.is_cuda for tensor in item.model_output.values())
                )

    def test_raw_session_without_preprocessing_or_cpu_copy(self):
        stream = torch.cuda.Stream()
        with torch.cuda.stream(stream):
            tensor = torch.rand(2, 3, 32, 32, device="cuda")
        item = PipelineContext(model_input=tensor, cuda_stream=stream)
        backend = Mock(return_value=tensor[:, :, :2, :2])
        with (
            patch(
                "pipeworks.embedded.yolo_inference.load_backend",
                return_value=SimpleNamespace(infer=backend),
            ),
            patch("pipeworks.embedded.yolo_inference.Path.is_file", return_value=True),
            patch.object(torch.Tensor, "cpu", side_effect=AssertionError("CPU copy")),
        ):
            result = next(YoloInference("model.pt", backend=Backend.TORCHSCRIPT).process(iter([item])))
        self.assertIs(result.model_input, tensor)
        self.assertEqual(result.model_output["output0"].shape, (2, 3, 2, 2))
        backend.assert_called_once_with(tensor)

    def requests(self, count):
        from pipeworks.local_yolo_inference import _Request

        stream = torch.cuda.Stream()
        requests = []
        with torch.cuda.stream(stream):
            for index in range(count):
                tensor = torch.full((1, 3, 32, 32), float(index + 1), device="cuda")
                event = torch.cuda.Event()
                event.record(stream)
                requests.append(
                    _Request(tensor, 0, (0, tensor.dtype, (3, 32, 32)), event)
                )
        return requests

    def worker(self):
        from queue import Queue

        from pipeworks.local_yolo_inference import _ModelWorker

        worker = object.__new__(_ModelWorker)
        worker.path, worker.size, worker.timeout = Path("model.pt"), 4, 0
        worker.backend = "torchscript"
        worker.requests = Queue()
        return worker

    def test_shared_worker_splits_independent_batch_one_outputs(self):
        from pipeworks import local_yolo_inference as shared

        requests, worker = self.requests(2), self.worker()
        session = Mock()
        session.infer.side_effect = lambda tensor, stream: {
            "output0": tensor[:, :, :2, :2]
        }
        with (
            patch.object(
                shared, "collect_batch", side_effect=[requests, StopIteration]
            ),
            patch.object(shared, "_Session", return_value=session),
            patch.object(torch.Tensor, "cpu", side_effect=AssertionError("CPU copy")),
            self.assertRaises(StopIteration),
        ):
            worker._run()
        first, second = (request.result["output0"] for request in requests)
        self.assertEqual(first.shape, (1, 3, 2, 2))
        self.assertTrue(torch.all(first == 1))
        self.assertTrue(torch.all(second == 2))
        self.assertNotEqual(first.data_ptr(), second.data_ptr())
        first.zero_()
        self.assertTrue(torch.all(second == 2))
        for request in requests:
            self.assertTrue(request.done.is_set())
            self.assertIsNone(request.inputs)
            self.assertIsNone(request.ready_event)
            self.assertIsNone(request.error)
            self.assertIsNotNone(request.inference_seconds)

    def test_shared_worker_failure_wakes_all_and_reloads_model(self):
        from pipeworks import local_yolo_inference as shared

        failed, recovered, worker = self.requests(2), self.requests(1), self.worker()
        bad, good = Mock(), Mock()
        bad.infer.side_effect = RuntimeError("execution failed")
        good.infer.side_effect = lambda tensor, stream: {"output0": tensor.clone()}
        with (
            patch.object(
                shared, "collect_batch", side_effect=[failed, recovered, StopIteration]
            ),
            patch.object(shared, "_Session", side_effect=[bad, good]) as load,
            self.assertRaises(StopIteration),
        ):
            worker._run()
        self.assertEqual(load.call_count, 2)
        for request in failed:
            self.assertTrue(request.done.is_set())
            self.assertIsNone(request.result)
            self.assertIn("execution failed", request.error)
        self.assertTrue(recovered[0].done.is_set())
        self.assertIsNone(recovered[0].error)
        self.assertTrue(torch.all(recovered[0].result["output0"] == 1))

    def test_session_output_survives_reused_backend_buffer(self):
        stream = torch.cuda.Stream()
        with torch.cuda.stream(stream):
            tensor = torch.ones(1, 3, 32, 32, device="cuda")
            prediction = torch.ones(1, 84, 10, device="cuda")
            session = object.__new__(_Session)
            session.gpu_id = 0
            session.backend = Mock()
            session.backend.infer.return_value = prediction
            output = session.infer(tensor, stream)["output0"]
            prediction.zero_()
        stream.synchronize()
        self.assertTrue(torch.all(output == 1))


if __name__ == "__main__":
    unittest.main()
