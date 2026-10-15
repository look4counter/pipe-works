import json
import os
import sys
import time
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock, Thread, current_thread
import unittest
from unittest.mock import patch

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from pipeworks import Backend, Pipeline
from pipeworks.embedded import CudaAsync, YoloInference, YoloReport
from pipeworks.models import PipelineContext, Step
from pipeworks.hotswap import Hotswap


def _observe_worker(backend, model, log_path):
    if backend == Backend.TENSORRT:
        from pipeworks import local_yolo_inference as workers
        from pipeworks.yolo_backends.tensorrt import _EngineSession as session_type
        thread_name = f"pipeworks-yolo-inference-{model.stem}"
    else:
        from pipeworks import local_yolo_inference as workers
        from pipeworks.embedded.yolo_inference import _Session as session_type
        thread_name = f"pipeworks-yolo-inference-{model.stem}"
    with workers._workers_lock:
        registry = getattr(session_type, "_central_batch_test_probes", None)
        if registry is None:
            registry = {}
            log_lock = Lock()
            original = session_type.infer

            def observed(session, inputs, stream, *args):
                outputs = original(session, inputs, stream, *args)
                destination = registry.get(current_thread().name)
                if destination is not None:
                    tensors = list(inputs.values()) if isinstance(inputs, dict) else [inputs]
                    record = {
                        "pid": os.getpid(),
                        "thread": current_thread().name,
                        "batch_size": tensors[0].shape[0],
                        "session_id": id(session),
                        "inputs_cuda": all(t.is_cuda for t in tensors),
                        "outputs_cuda": all(t.is_cuda for t in outputs.values()),
                        "gpu": tensors[0].device.index,
                    }
                    with log_lock, Path(destination).open("a", encoding="utf-8") as output:
                        output.write(json.dumps(record) + "\n")
                return outputs

            session_type.infer = observed
            session_type._central_batch_test_probes = registry
        registry[thread_name] = str(log_path)
        if not hasattr(session_type, "_central_batch_reference_lock"):
            session_type._central_batch_reference_lock = Lock()
        return session_type._central_batch_reference_lock


class BatchGpuSource(Step):
    def __init__(self, directory, model, backend, tag):
        self.directory = Path(directory)
        self.model = Path(model)
        self.backend = backend
        self.tag = tag

    def configure(self, config):
        pass

    def process(self, inputs):
        from pipeworks.embedded.stream_report import report_scope

        reference_lock = _observe_worker(self.backend, self.model, self.directory / "worker.jsonl")
        stream = torch.cuda.Stream(device=0)
        reference_items = []
        for round_index in range(2):
            value = (0.2 if self.tag == "first" else 0.7) + round_index * 0.1
            with torch.cuda.stream(stream):
                tensor = torch.full((1, 3, 32, 32), value, device="cuda")
            reference_items.append(PipelineContext(model_input=tensor, cuda_stream=stream))
        with reference_lock, report_scope():
            reference = YoloInference(self.model, backend=self.backend).process(iter(reference_items))
            try:
                expected_outputs = [next(reference).model_output for _ in reference_items]
            finally:
                reference.close()
        for round_index, reference_item in enumerate(reference_items):
            tensor = reference_item.model_input
            expected = expected_outputs[round_index]
            (self.directory / f"{self.tag}-{round_index}.ready").touch()
            deadline = time.monotonic() + 45
            ready = [self.directory / f"{tag}-{round_index}.ready" for tag in ("first", "second")]
            while not all(file.is_file() for file in ready):
                if time.monotonic() >= deadline:
                    raise TimeoutError("두 중앙 파이프라인의 GPU 입력 준비가 완료되지 않았습니다.")
                time.sleep(0.01)
            yield PipelineContext(
                model_input=tensor,
                expected_output=expected,
                cuda_stream=stream,
                producer_pid=os.getpid(),
                round_index=round_index,
                tag=self.tag,
            )


class BatchGpuRecorder(Step):
    def __init__(self, path, backend):
        self.path = Path(path)
        self.backend = backend

    def configure(self, config):
        pass

    def process(self, inputs):
        from pipeworks.embedded.yolo_report import backend_kind, store

        for item in inputs:
            outputs = item.model_output
            if set(outputs) != set(item.expected_output):
                raise AssertionError("공유 배치 출력 이름이 개별 참조와 다릅니다.")
            with torch.cuda.stream(item.cuda_stream):
                for name, tensor in outputs.items():
                    if not tensor.is_cuda or tensor.device != item.model_input.device or tensor.shape[0] != 1:
                        raise AssertionError("요청별 출력은 동일 GPU의 배치 1 텐서여야 합니다.")
                    torch.testing.assert_close(tensor, item.expected_output[name], rtol=1e-4, atol=1e-5)
                shapes = {name: list(t.shape) for name, t in outputs.items()}
                for tensor in outputs.values():
                    tensor.zero_()
                item.cuda_stream.synchronize()
            snapshot = store().snapshot(backend_kind(self.backend), 0)
            record = {
                "producer_pid": item.producer_pid,
                "consumer_pid": os.getpid(),
                "tag": item.tag,
                "round_index": item.round_index,
                "model_id": item.model_id,
                "outputs": shapes,
                "gpu": item.model_input.device.index,
                "matched_single": True,
                "completed": snapshot["states"]["completed"],
                "stages": {name: row[1] for name, row in snapshot["recent"].items()},
            }
            with self.path.open("a", encoding="utf-8") as output:
                output.write(json.dumps(record) + "\n")
            yield item


def _build_tensor_rt(path):
    import numpy as np
    import tensorrt as trt

    logger = trt.Logger(trt.Logger.WARNING)
    builder = trt.Builder(logger)
    network = builder.create_network(1 << int(trt.NetworkDefinitionCreationFlag.EXPLICIT_BATCH))
    config = builder.create_builder_config()
    config.set_memory_pool_limit(trt.MemoryPoolType.WORKSPACE, 64 << 20)
    images = network.add_input("images", trt.float32, (-1, 3, 32, 32))
    one = network.add_constant((1, 1, 1, 1), np.ones((1, 1, 1, 1), dtype=np.float32)).get_output(0)
    two = network.add_constant((1, 1, 1, 1), np.full((1, 1, 1, 1), 2, dtype=np.float32)).get_output(0)
    for name, other, operation in (
        ("scores", one, trt.ElementWiseOperation.SUM),
        ("features", two, trt.ElementWiseOperation.PROD),
    ):
        output = network.add_elementwise(images, other, operation).get_output(0)
        output.name = name
        network.mark_output(output)
    profile = builder.create_optimization_profile()
    profile.set_shape("images", (1, 3, 32, 32), (2, 3, 32, 32), (4, 3, 32, 32))
    config.add_optimization_profile(profile)
    payload = builder.build_serialized_network(network, config)
    if payload is None:
        raise RuntimeError("중앙 배치 검증용 TensorRT 엔진을 생성하지 못했습니다.")
    path.write_bytes(bytes(payload))


@unittest.skipUnless(os.name == "nt" and torch.cuda.is_available(), "Windows CUDA가 필요합니다.")
class CentralYoloBatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = TemporaryDirectory(prefix="central-yolo-batch-", dir=ROOT)
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.directory = Path(cls.temporary.name)
        cls.models = {}
        token = uuid.uuid4().hex[:8]
        previous_threads = torch.get_num_threads()
        torch.set_num_threads(1)
        cls.addClassCleanup(torch.set_num_threads, previous_threads)
        torch.manual_seed(0)
        import ultralytics
        from ultralytics import YOLO

        weights = cls.directory / f"ultralytics-{token}.pt"
        model_config = Path(ultralytics.__file__).parent / "cfg/models/11/yolo11.yaml"
        YOLO(str(model_config), task="detect", verbose=False).save(weights)
        cls.models[Backend.ULTRALYTICS] = weights

        class Model(torch.nn.Module):
            def forward(self, images):
                return {"scores": images.neg(), "features": images * images}

        script = cls.directory / f"torchscript-{token}.pt"
        torch.jit.trace(Model().cuda().eval(), torch.zeros(1, 3, 32, 32, device="cuda"), strict=False).save(str(script))
        cls.models[Backend.TORCHSCRIPT] = script
        engine = cls.directory / f"tensorrt-{token}.plan"
        _build_tensor_rt(engine)
        cls.models[Backend.TENSORRT] = engine
        for path in cls.models.values():
            path.with_suffix(".yml").write_text("max_batch_size: 2\ntimeout_ms: 5000\n", encoding="utf-8")

    def _verify_backend(self, backend):
        from pipeworks import main
        from pipeworks.embedded.yolo_report import backend_kind

        directory = self.directory / backend.value
        directory.mkdir()
        model = self.models[backend]
        group = f"batch-test-{uuid.uuid4().hex}"
        original_connect, original_start = main._connect, main._start_server
        servers, failures = {}, []

        def start(_group):
            original_start(group)
            for process in main._launched_servers:
                if group in process.args:
                    servers[process.pid] = process

        pipelines = []
        for tag in ("first", "second"):
            config = directory / f"{tag}.yml"
            config.write_text("{}", encoding="utf-8")
            pipelines.append(
                Pipeline(f"batch-{backend.value}-{tag}", config=config)
                .step(Hotswap(BatchGpuSource(directory, model, backend, tag), source=True, watch_code=False, recover_errors=False))
                .step(CudaAsync(YoloInference(model, backend=backend, batch=True, id=tag), timeout_ms=30000))
                .step(Hotswap(BatchGpuRecorder(directory / f"{tag}.jsonl", backend), watch_code=False, recover_errors=False))
                .step(YoloReport())
            )

        def execute(pipeline):
            try:
                pipeline.run()
            except Exception as error:
                failures.append(error)

        threads = [Thread(target=execute, args=(pipeline,), daemon=True) for pipeline in pipelines]
        try:
            with (
                patch.object(main, "_connect", side_effect=lambda _group="production": original_connect(group)),
                patch.object(main, "_start_server", side_effect=start),
                self.assertLogs("pipeworks.embedded.yolo_report", level="DEBUG") as report_logs,
            ):
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join(timeout=90)
                    self.assertFalse(thread.is_alive(), "중앙 배치 실행이 종료되지 않았습니다.")
            self.assertEqual(failures, [], str(failures))
            self.assertIn(f"YoloReport | {backend_kind(backend)}", "\n".join(record.getMessage() for record in report_logs.records))
            records = [json.loads(line) for line in (directory / "worker.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(records), 2)
            self.assertEqual([record["batch_size"] for record in records], [2, 2])
            self.assertEqual(len({record["session_id"] for record in records}), 1)
            pids = {record["pid"] for record in records}
            self.assertEqual(len(pids), 1)
            self.assertNotIn(os.getpid(), pids)
            with original_connect(group) as connection:
                connection.send_bytes(b"ping")
                status, central_pid = connection.recv()
            self.assertEqual(status, "pong")
            self.assertEqual(pids, {central_pid})
            self.assertTrue(all(record["inputs_cuda"] and record["outputs_cuda"] and record["gpu"] == 0 for record in records))
            worker_prefix = "pipeworks-yolo-inference-"
            self.assertTrue(all(record["thread"].startswith(worker_prefix) for record in records))
            for tag in ("first", "second"):
                rows = [json.loads(line) for line in (directory / f"{tag}.jsonl").read_text(encoding="utf-8").splitlines()]
                self.assertEqual(len(rows), 2)
                self.assertEqual([row["round_index"] for row in rows], [0, 1])
                self.assertEqual([row["completed"] for row in rows], [1, 2])
                for row in rows:
                    self.assertIn(row["producer_pid"], pids)
                    self.assertIn(row["consumer_pid"], pids)
                    self.assertEqual(row["tag"], tag)
                    self.assertEqual(row["model_id"], tag)
                    self.assertEqual(row["gpu"], 0)
                    self.assertTrue(row["matched_single"])
                    self.assertTrue(all(shape[0] == 1 for shape in row["outputs"].values()))
                    for stage in ("queue", "input_copy", "inference", "output_copy", "total"):
                        self.assertEqual(row["stages"][stage], row["round_index"] + 1)
            print(f"{backend.name}: central_pid={next(iter(pids))}, batches=[2,2], shared_session=True, gpu_outputs=4, reports=2+2", flush=True)
        finally:
            for process in servers.values():
                try:
                    process.wait(timeout=5)
                except Exception:
                    process.terminate()
                    process.wait(timeout=5)
                if process.stderr is not None:
                    process.stderr.close()
            for thread in threads:
                thread.join(timeout=5)

    def test_ultralytics_batch_in_central_process(self):
        self._verify_backend(Backend.ULTRALYTICS)

    def test_torchscript_batch_in_central_process(self):
        self._verify_backend(Backend.TORCHSCRIPT)

    def test_tensor_rt_batch_in_central_process(self):
        self._verify_backend(Backend.TENSORRT)


if __name__ == "__main__":
    unittest.main(verbosity=2)
