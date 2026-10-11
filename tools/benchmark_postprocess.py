"""Compare complete old and optimized postprocessing on identical CUDA predictions."""

import argparse
import statistics
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "examples")]
from pipeworks.models import PipelineContext
from pipeworks.image_transform import ImageTransform
from step.tensor_rt_post_process import TensorRTPostProcess


def run(step, prediction, stream):
    item = PipelineContext(cuda_stream=stream)
    item.model_output = {"output0": prediction}
    item.model_id = "benchmark"
    item.tensor_rt_transform = ImageTransform(
        shape=(1080, 1920), ratio_xy=(1 / 3, 1 / 3), left=0, top=140,
        output_shape=(640, 640), resize_mode="letterbox")
    next(step.process(iter([item])))
    result = item.detections["benchmark"] if isinstance(item.detections, dict) else item.detections
    return result.boxes.data


def measure(step, source, stream, iterations):
    times, gpu_times = [], []
    for _ in range(10):
        with torch.cuda.stream(stream):
            run(step, source.clone(), stream)
    for _ in range(iterations):
        with torch.cuda.stream(stream):
            prediction = source.clone()
            stream.synchronize()  # Exclude the input reset from both timings.
            start, end = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
            start.record(stream)
            began = time.perf_counter()
            result = run(step, prediction, stream)
            times.append((time.perf_counter() - began) * 1000)
            end.record(stream)
            end.synchronize()
            gpu_times.append(start.elapsed_time(end))
    return result, statistics.median(times), statistics.median(gpu_times)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", default="HEAD", help="Git revision before optimization")
    parser.add_argument("--iterations", type=int, default=100)
    args = parser.parse_args()
    if args.iterations < 1 or not torch.cuda.is_available():
        parser.error("Positive iterations and CUDA are required")
    revision = subprocess.check_output(["git", "rev-parse", args.baseline], cwd=ROOT).decode().strip()
    source = subprocess.check_output(["git", "show", f"{revision}:examples/step/tensor_rt_post_process.py"], cwd=ROOT).decode("utf-8")
    scope = {"__name__": "postprocess_baseline"}
    exec(compile(source, "postprocess_baseline", "exec"), scope)
    stream = torch.cuda.Stream()
    print(f"GPU: {torch.cuda.get_device_name()}; baseline: {revision}")
    torch.manual_seed(42)
    for dense in (False, True):
        prediction = torch.rand((1, 84, 8400), device="cuda")
        prediction[:, :4] *= 640
        if not dense:
            prediction[:, 4:] *= .01
            prediction[:, 6, :100] = torch.linspace(.3, .99, 100, device="cuda")
        torch.cuda.synchronize()
        for classes in ([2], None):
            old, new = scope["TensorRTPostProcess"](), TensorRTPostProcess()
            for step in (old, new):
                step.configure(SimpleNamespace(classes=classes))
            rounds = []
            for round_index in range(3):
                order = (old, new) if round_index % 2 == 0 else (new, old)
                measured = {id(step): measure(step, prediction, stream, args.iterations) for step in order}
                reference, old_ms, old_gpu = measured[id(old)]
                output, new_ms, new_gpu = measured[id(new)]
                torch.testing.assert_close(output, reference, rtol=1e-5, atol=1e-5)
                rounds.append((old_ms, new_ms, old_gpu, new_gpu))
            medians = [statistics.median(values) for values in zip(*rounds)]
            print(f"dense={dense}, classes={classes}: wall {medians[0]:.3f} -> {medians[1]:.3f} ms; event {medians[2]:.3f} -> {medians[3]:.3f} ms")


if __name__ == "__main__":
    main()
