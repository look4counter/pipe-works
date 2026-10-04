from collections import deque
from pathlib import Path
from queue import Queue
from tempfile import TemporaryDirectory
from threading import Barrier, Thread
import time
import unittest
from unittest.mock import patch

import torch

from pipeworks.local_yolo import _InferenceRequest, _batch_settings, _next_batch, infer


def gpu_nv12(height: int, width: int) -> torch.Tensor:
    image = torch.full((height * 3 // 2, width), 128, dtype=torch.uint8, device="cuda")
    image[:height] = 80
    return image


class LocalYoloTests(unittest.TestCase):
    @unittest.skipUnless(torch.cuda.is_available(), "CUDA가 필요합니다.")
    def test_reported_inference_excludes_model_loading(self):
        with TemporaryDirectory() as temporary:
            model_path = Path(temporary) / "timing.pt"
            model_path.write_bytes(b"placeholder")
            durations = []

            class Model:
                def __init__(self, path):
                    time.sleep(0.15)

                def predict(self, images, **options):
                    from ultralytics.engine.results import Results

                    return [Results(image.permute(1, 2, 0), path="image", names={},
                                    boxes=torch.empty((0, 6), device="cuda")) for image in images]

            with patch("ultralytics.YOLO", Model):
                result = infer(model_path, gpu_nv12(64, 64), None, 0.25, 0,
                               on_inference_complete=durations.append)

            self.assertEqual(tuple(result.orig_shape), (64, 64))
            self.assertEqual(len(durations), 1)
            self.assertLess(durations[0], 0.15)

    @unittest.skipUnless(torch.cuda.is_available(), "CUDA가 필요합니다.")
    def test_infer_waits_for_output_gpu_event_before_returning(self):
        with TemporaryDirectory() as temporary:
            model_path = Path(temporary) / "output_event.pt"
            model_path.write_bytes(b"placeholder")
            events = []

            class CompletionEvent:
                def __init__(self):
                    self.recorded = False
                    self.synchronized = False
                    events.append(self)

                def record(self, stream):
                    self.recorded = stream.device.type == "cuda"

                def synchronize(self):
                    assert self.recorded
                    self.synchronized = True

            class Model:
                def __init__(self, path):
                    pass

                def predict(self, images, **options):
                    from ultralytics.engine.results import Results

                    return [Results(image.permute(1, 2, 0), path="image", names={},
                                    boxes=torch.tensor([[100., 200., 300., 400., 0.9, 2.]], device="cuda"))
                            for image in images]

            with patch("ultralytics.YOLO", Model), patch("pipeworks.local_yolo.torch.cuda.Event", CompletionEvent):
                result = infer(model_path, gpu_nv12(64, 96), None, 0.25, 0)

            self.assertEqual(len(events), 2)
            self.assertTrue(all(event.synchronized for event in events))
            self.assertEqual(tuple(result.orig_shape), (64, 96))
            self.assertTrue(result.boxes.data.is_cuda)

    @unittest.skipUnless(torch.cuda.is_available(), "CUDA가 필요합니다.")
    def test_worker_waits_for_gpu_copy_event(self):
        with TemporaryDirectory() as temporary:
            model_path = Path(temporary) / "event.pt"
            model_path.write_bytes(b"placeholder")

            class Ready:
                waited = False

                def wait(self, stream):
                    assert stream.device.type == "cuda"
                    self.waited = True

            ready = Ready()

            class Model:
                def __init__(self, path):
                    pass

                def predict(self, images, **options):
                    from ultralytics.engine.results import Results

                    if not ready.waited:
                        raise AssertionError("GPU 복제 완료를 기다리지 않았습니다.")
                    return [Results(image.permute(1, 2, 0), path="image", names={},
                                    boxes=torch.empty((0, 6), device="cuda")) for image in images]

            with patch("ultralytics.YOLO", Model):
                result = infer(model_path, gpu_nv12(64, 64), None, 0.25, 0, ready_event=ready)
            self.assertTrue(ready.waited)
            self.assertEqual(tuple(result.orig_shape), (64, 64))

    @unittest.skipUnless(torch.cuda.is_available(), "CUDA가 필요합니다.")
    def test_real_models_keep_input_and_results_on_gpu(self):
        for suffix in ("pt", "engine"):
            with self.subTest(suffix=suffix):
                model = Path(__file__).resolve().parents[1] / "examples" / "model" / f"yolo11n.{suffix}"
                if not model.is_file():
                    self.skipTest(f"모델 파일이 없습니다: {model}")
                image = gpu_nv12(64, 96)
                result = infer(model, image, [2], 0.25, 0)
                self.assertTrue(image.is_cuda)
                self.assertEqual(tuple(result.orig_shape), (64, 96))
                self.assertTrue(result.orig_img.is_cuda)
                self.assertTrue(result.boxes.data.is_cuda)

    @unittest.skipUnless(torch.cuda.is_available(), "CUDA가 필요합니다.")
    def test_concurrent_requests_share_model_and_batch(self):
        with TemporaryDirectory() as temporary:
            model_path = Path(temporary) / "model.pt"
            model_path.write_bytes(b"placeholder")
            model_path.with_suffix(".yml").write_text("max_batch_size: 2\ntimeout: 500\n", encoding="utf-8")
            calls = []

            class Model:
                def __init__(self, path):
                    calls.append(("load", path))

                def predict(self, images, **options):
                    from ultralytics.engine.results import Results

                    calls.append(("predict", tuple(images.shape), options["device"]))
                    return [Results(image.permute(1, 2, 0), path="image", names={},
                                    boxes=torch.empty((0, 6), device="cuda")) for image in images]

            barrier = Barrier(2)
            results = []
            durations = []

            def request(height, width):
                barrier.wait()
                results.append(infer(model_path, gpu_nv12(height, width), [2], 0.5, 0,
                                     on_inference_complete=durations.append))

            with patch("ultralytics.YOLO", Model):
                threads = [Thread(target=request, args=(64, 64)), Thread(target=request, args=(64, 96))]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join(timeout=5)
                    self.assertFalse(thread.is_alive())

            self.assertEqual({tuple(result.orig_shape) for result in results}, {(64, 64), (64, 96)})
            self.assertEqual(len([call for call in calls if call[0] == "load"]), 1)
            self.assertIn(("predict", (2, 3, 640, 640), 0), calls)
            self.assertTrue(all(result.boxes.data.is_cuda for result in results))
            self.assertEqual(len(durations), 2)
            self.assertEqual(durations[0], durations[1])

    def test_batch_settings_and_option_grouping(self):
        with TemporaryDirectory() as temporary:
            model = Path(temporary) / "model.pt"
            self.assertEqual(_batch_settings(model), (1, 0.0))
            model.with_suffix(".yml").write_text("max_batch_size: 4\ntimeout: 10\n", encoding="utf-8")
            self.assertEqual(_batch_settings(model), (4, 0.01))
            requests = Queue()
            deferred = deque()
            first = _InferenceRequest(None, [2], 0.25, 0)
            second = _InferenceRequest(None, [2], 0.25, 0)
            different = _InferenceRequest(None, [3], 0.25, 0)
            for request in (first, second, different):
                requests.put(request)
            self.assertEqual(_next_batch(requests, deferred, 4, 0.01), [first, second])
            self.assertEqual(_next_batch(requests, deferred, 4, 0.01), [different])
