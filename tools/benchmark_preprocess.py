"""Compare the checked-in baseline and optimized generic preprocessing on CUDA."""

import argparse
import subprocess
import sys
import time
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from pipeworks.embedded.tensor_rt_preprocess import TensorRTPreProcess


def measure(step, frame, iterations, pixel_format):
    def run():
        pixels = step._pixels(frame, pixel_format)
        resized, _ = step._resize(pixels)
        return step._normalize(resized)

    for _ in range(20):
        run()
    torch.cuda.synchronize()
    start, end = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
    wall = time.perf_counter()
    start.record()
    for _ in range(iterations):
        output = run()
    end.record()
    end.synchronize()
    return output, start.elapsed_time(end) / iterations, (time.perf_counter() - wall) * 1000 / iterations


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=200)
    args = parser.parse_args()
    if args.iterations < 1:
        parser.error("iterations must be positive")
    if not torch.cuda.is_available():
        parser.error("CUDA is required")
    # Preserve the exact pre-change implementation as the independent baseline.
    source = subprocess.check_output(["git", "show", "HEAD:src/pipeworks/embedded/tensor_rt_preprocess.py"], cwd=ROOT).decode("utf-8")
    scope = {"__name__": "preprocess_baseline"}
    exec(compile(source, "preprocess_baseline", "exec"), scope)
    baseline_type = scope["TensorRTPreProcess"]
    print(torch.cuda.get_device_name())
    for pixel_format in ("RGB", "NV12"):
        for options in ({}, {"mean": (1, 2, 3), "std": (2, 3, 4)}, {"layout": "nhwc", "dtype": "float16"}):
            shape = (1080, 1920, 3) if pixel_format == "RGB" else (1620, 1920)
            frame = torch.randint(0, 256, shape, device="cuda", dtype=torch.uint8)
            old, old_gpu, old_wall = measure(baseline_type(**options), frame, args.iterations, pixel_format)
            new, new_gpu, new_wall = measure(TensorRTPreProcess(**options), frame, args.iterations, pixel_format)
            torch.testing.assert_close(new, old, rtol=1e-5, atol=1e-5)
            print(f"{pixel_format} {options or 'default'}: GPU {old_gpu:.3f} -> {new_gpu:.3f} ms; wall {old_wall:.3f} -> {new_wall:.3f} ms")


if __name__ == "__main__":
    main()
