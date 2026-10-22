import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pipeworks import Backend
from pipeworks.embedded import YoloInference
from pipeworks.models import PipelineContext
from pipeworks.yolo_backends.patchcore import PatchCoreBackend, _PatchCore


class CheckpointTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "result.pt"
        model = _PatchCore(32)
        model.memory_bank = torch.rand(17, 384)
        self.payload = {
            "format": "patchcore-v1",
            "backbone": "resnet18",
            "imgsz": 32,
            "state_dict": model.state_dict(),
            "threshold": 1.5,
            "metadata": {"source": "test"},
        }

    def save(self):
        torch.save(self.payload, self.path)

    def test_invalid_checkpoints(self):
        for key, value in (
            ("format", "other"),
            ("backbone", "resnet50"),
            ("imgsz", True),
            ("imgsz", 0),
            ("threshold", float("nan")),
            ("metadata", []),
            ("state_dict", {}),
        ):
            with self.subTest(key=key):
                payload = dict(self.payload, **{key: value})
                torch.save(payload, self.path)
                with self.assertRaises(ValueError):
                    PatchCoreBackend(self.path, 0)
        for memory in (
            torch.empty(0, 384),
            torch.empty(2, 12),
            torch.full((2, 384), float("nan")),
            torch.ones(2, 384).half(),
        ):
            with self.subTest(shape=memory.shape):
                payload = dict(
                    self.payload,
                    state_dict=dict(self.payload["state_dict"], memory_bank=memory),
                )
                torch.save(payload, self.path)
                with self.assertRaises(ValueError):
                    PatchCoreBackend(self.path, 0)

    def test_missing_weights(self):
        del self.payload["state_dict"]["backbone.conv1.weight"]
        self.save()
        with self.assertRaisesRegex(ValueError, "가중치"):
            PatchCoreBackend(self.path, 0)

    def test_backend_selection(self):
        self.assertEqual(Backend.PATCHCORE, "patchcore")
        self.assertEqual(
            YoloInference(self.path, backend="patchcore").backend, Backend.PATCHCORE
        )


@unittest.skipUnless(torch.cuda.is_available(), "CUDA가 필요합니다.")
class GpuTests(CheckpointTests):
    def setUp(self):
        super().setUp()
        self.save()

    def test_gpu_guard_and_reference(self):
        from pipeworks.embedded.yolo_inference import _Session

        backend = PatchCoreBackend(self.path, 0)
        self.assertEqual(backend.threshold, 1.5)
        self.assertEqual(backend.metadata, {"source": "test"})
        images = torch.rand(2, 3, 35, 41, device="cuda")
        # 청크를 사용하지 않는 전체 거리 계산과 비교한다.
        with torch.no_grad():
            embeddings = backend.model.embedding(images)
            patches = embeddings.permute(0, 2, 3, 1).reshape(-1, 384)
            bank = backend.model.memory_bank
            squared = (
                patches.square().sum(1, keepdim=True)
                + bank.square().sum(1)[None]
                - 2 * patches @ bank.T
            )
            maps = (
                squared.clamp_min(0)
                .amin(1)
                .sqrt()
                .reshape(2, 1, *embeddings.shape[-2:])
            )
            scores = maps.flatten(1).amax(1)
            maps = torch.nn.functional.interpolate(
                maps, images.shape[-2:], mode="bilinear", align_corners=False
            )[:, 0]
        stream = torch.cuda.current_stream()
        result = _Session(self.path, 0, "patchcore").infer(images, stream)
        torch.testing.assert_close(result["pred_score"], scores, rtol=1e-4, atol=1e-5)
        torch.testing.assert_close(result["anomaly_map"], maps, rtol=1e-4, atol=1e-5)
        self.assertEqual(tuple(result["anomaly_map"].shape), (2, 35, 41))
        self.assertTrue(all(value.is_cuda for value in result.values()))

    def test_input_errors(self):
        backend = PatchCoreBackend(self.path, 0)
        for images in (
            torch.rand(1, 3, 32, 32),
            {},
            torch.rand(1, 4, 32, 32, device="cuda"),
            torch.rand(1, 3, 32, 32, device="cuda").half(),
            torch.rand(3, 32, 32, device="cuda"),
            torch.empty(1, 3, 0, 32, device="cuda"),
        ):
            with (
                self.subTest(shape=getattr(images, "shape", None)),
                self.assertRaises(ValueError),
            ):
                backend.infer(images)

    def test_single_and_shared_batch(self):
        from pipeworks.embedded.yolo_inference import _Session
        from pipeworks.local_yolo_inference import infer

        self.path.with_suffix(".yml").write_text(
            "max_batch_size: 2\nmax_batch_wait_ms: 100\n", encoding="utf-8"
        )
        images = torch.rand(2, 3, 32, 40, device="cuda")
        expected = PatchCoreBackend(self.path, 0).infer(images)
        step = YoloInference(self.path, backend=Backend.PATCHCORE)
        result = next(
            step.process(iter([PipelineContext(model_input=images)]))
        ).model_output
        torch.testing.assert_close(
            result["pred_score"], expected["pred_score"], rtol=1e-4, atol=1e-5
        )
        from concurrent.futures import ThreadPoolExecutor

        torch.cuda.synchronize()
        sizes = []
        original = _Session.infer

        def tracked(session, inputs, stream):
            sizes.append(inputs.shape[0])
            return original(session, inputs, stream)

        with patch.object(_Session, "infer", tracked), ThreadPoolExecutor(2) as pool:
            futures = [
                pool.submit(infer, self.path, images[i : i + 1], 0, backend="patchcore")
                for i in range(2)
            ]
            results = [future.result(timeout=30) for future in futures]
        self.assertEqual(sizes, [2])
        for index, result in enumerate(results):
            for name in expected:
                torch.testing.assert_close(
                    result[name],
                    expected[name][index : index + 1],
                    rtol=1e-4,
                    atol=1e-5,
                )

    def test_distance_chunk_boundaries(self):
        from pipeworks.embedded.yolo_inference import _Session

        # 9*8*8=576개 패치와 1025개 메모리로 양쪽 청크 경계를 넘긴다.
        self.payload["imgsz"] = 64
        self.payload["state_dict"]["memory_bank"] = torch.rand(1025, 384)
        self.save()
        images = torch.rand(9, 3, 64, 64, device="cuda")
        session = _Session(self.path, 0, "patchcore")
        embeddings = session.backend.model.embedding(images)
        patches = embeddings.permute(0, 2, 3, 1).reshape(-1, 384)
        bank = session.backend.model.memory_bank
        with torch.no_grad():
            squared = (
                patches.square().sum(1, keepdim=True)
                + bank.square().sum(1)[None]
                - 2 * patches @ bank.T
            )
            maps = squared.clamp_min(0).amin(1).sqrt().reshape(9, 1, 8, 8)
            scores = maps.flatten(1).amax(1)
            maps = torch.nn.functional.interpolate(
                maps, (64, 64), mode="bilinear", align_corners=False
            )[:, 0]
        result = session.infer(images, torch.cuda.current_stream())
        torch.testing.assert_close(result["pred_score"], scores, rtol=1e-4, atol=1e-5)
        torch.testing.assert_close(result["anomaly_map"], maps, rtol=1e-4, atol=1e-5)

    def test_trainer_checkpoint_compatibility(self):
        trainer_path = Path("D:/Projects/yolo-trainer/src/yolo_trainer/patchcore.py")
        if not trainer_path.is_file():
            self.skipTest("학습 프로젝트 기준 구현이 없습니다.")
        spec = importlib.util.spec_from_file_location(
            "trainer_patchcore_reference", trainer_path
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        reference = module.PatchCore(32, pretrained=False)
        reference.memory_bank = self.payload["state_dict"]["memory_bank"].clone()
        reference.load_state_dict(self.payload["state_dict"])
        reference.threshold = 1.5
        reference.save(self.path, {"source": "trainer"})
        reference = reference.cuda().eval()
        images = torch.rand(2, 3, 35, 41, device="cuda")
        scores, maps = reference(images)
        result = PatchCoreBackend(self.path, 0).infer(images)
        torch.testing.assert_close(result["pred_score"], scores, rtol=1e-4, atol=1e-5)
        torch.testing.assert_close(result["anomaly_map"], maps, rtol=1e-4, atol=1e-5)


if __name__ == "__main__":
    unittest.main()
