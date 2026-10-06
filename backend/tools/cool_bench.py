"""Time the region proposer (the OpenCV work of one Sherpa turn) with whichever OpenCV is installed.

    python tools/cool_bench.py --label cool --out cool.json

Run it once with the Cloud-Optimized OpenCV Library (COOL) and once with the stock OpenCV wheel, on the same
instance, then compare the two files with tools/cool_compare.py. Same frames as tools/benchmark.py: the six
sample screens scaled to 1920 x 1080 and JPEG-encoded at quality 85. One warm-up round, then --runs rounds.
It also times three operations COOL names (resize, adaptive Gaussian threshold, contours) on a 1080p frame.
"""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.contract import CaptureMeta  # noqa: E402
from app.regions import propose_regions  # noqa: E402

SAMPLES = Path(__file__).resolve().parents[1] / "app" / "static" / "samples"


def pct(values: list[float], p: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(p * (len(ordered) - 1))))]


def summary(values: list[float]) -> dict:
    return {"mean": round(statistics.mean(values), 2), "p50": round(pct(values, 0.5), 2), "p95": round(pct(values, 0.95), 2), "n": len(values)}


def timed(fn, repeat: int) -> list[float]:
    fn()
    out = []
    for _ in range(repeat):
        started = time.perf_counter()
        fn()
        out.append((time.perf_counter() - started) * 1000)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--runs", type=int, default=15)
    args = parser.parse_args()

    frames = []
    for path in sorted(SAMPLES.glob("*.png")):
        image = cv2.imdecode(np.fromfile(str(path), dtype="uint8"), cv2.IMREAD_COLOR)
        image = cv2.resize(image, (1920, 1080), interpolation=cv2.INTER_AREA)
        _, jpeg = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 85])
        frames.append((path.name, image, jpeg.tobytes()))
    capture = CaptureMeta(width=1920, height=1080)

    counts = {}
    for name, _, jpeg in frames:  # warm-up round, also records how many regions each frame gives
        counts[name] = len(propose_regions(jpeg, capture))
    times = []
    for _ in range(args.runs):
        for name, _, jpeg in frames:
            started = time.perf_counter()
            propose_regions(jpeg, capture)
            times.append((time.perf_counter() - started) * 1000)

    gray = cv2.cvtColor(frames[1][1], cv2.COLOR_BGR2GRAY)
    big = frames[1][1]
    edges = cv2.Canny(gray, 60, 160)
    ops = {
        "resize 1920x1080 to 960x540 (INTER_AREA)": timed(lambda: cv2.resize(big, (960, 540), interpolation=cv2.INTER_AREA), 200),
        "resize 1920x1080 to 1280x720 (INTER_LINEAR)": timed(lambda: cv2.resize(big, (1280, 720), interpolation=cv2.INTER_LINEAR), 200),
        "adaptiveThreshold gaussian 1080p": timed(lambda: cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 25, 10), 100),
        "findContours 1080p edges": timed(lambda: cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE), 100),
        "GaussianBlur 5x5 1080p": timed(lambda: cv2.GaussianBlur(gray, (5, 5), 0), 200),
    }
    result = {
        "label": args.label,
        "opencv": cv2.__version__,
        "opencv_file": cv2.__file__,
        "machine": platform.machine(),
        "python": platform.python_version(),
        "threads": cv2.getNumThreads(),
        "region_counts": counts,
        "region_proposer_ms": summary(times),
        "ops_ms": {name: summary(values) for name, values in ops.items()},
    }
    Path(args.out).write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(args.label, cv2.__version__, "region proposer mean", result["region_proposer_ms"]["mean"], "ms over", len(times), "calls")


if __name__ == "__main__":
    main()
