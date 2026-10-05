"""Graviton (arm64) versus x86_64: speed and cost of the part of a turn that runs on our compute.

Two copies of the backend run on AWS Lambda with the same image code, the same memory and the canned
model (so no model call is in the measurement): `cdk deploy ScreenTutorBenchmark -c benchmark=true`
in infra/ prints their URLs. This script sends the same screenshots to both and compares

  * regions   OpenCV region proposing, from the service's own timer (ms)
  * total     everything the service does for a turn (ms), from the service's own timer
  * wall      what the client sees, including the network (ms)

and turns `total` into the compute cost of a turn with the Lambda price list (duration x memory,
plus the request charge). Lambda bills per millisecond, so `total` is a close stand-in for the billed
duration (the real bill adds a few ms of runtime overhead, the same on both).

  python tools/benchmark.py --arm URL --x86 URL --token TOKEN [--runs 15] [--memory 2048] [--out FILE]

The frames are the sample screens of the repository, scaled to 1920 x 1080 and sent as JPEG, the way the
desktop app sends a capture.
"""

from __future__ import annotations

import argparse
import base64
import json
import statistics
import sys
import time
import urllib.request
from pathlib import Path

import cv2
import numpy as np

SAMPLES = Path(__file__).resolve().parent.parent / "app" / "static" / "samples"

# US East (N. Virginia) price list for Lambda: dollars per GB-second and per request.
PRICE_PER_GB_SECOND = {"arm64": 0.0000133334, "x86": 0.0000166667}
PRICE_PER_REQUEST = 0.20 / 1_000_000


def frames() -> list[tuple[str, str]]:
    out = []
    for path in sorted(SAMPLES.glob("*.png")):
        image = cv2.imdecode(np.fromfile(str(path), dtype="uint8"), cv2.IMREAD_COLOR)  # not imread: accented paths
        image = cv2.resize(image, (1920, 1080), interpolation=cv2.INTER_AREA)
        ok, jpeg = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 85])
        out.append((path.stem, base64.b64encode(jpeg.tobytes()).decode()))
    return out


def turn(url: str, token: str, image: str) -> tuple[float, dict]:
    body = json.dumps(
        {
            "session_id": "benchmark",
            "question": "What is on this screen?",
            "image_base64": image,
            "capture": {"width": 1920, "height": 1080},
        }
    ).encode()
    request = urllib.request.Request(
        url.rstrip("/") + "/explain-turn",
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
    )
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=90) as response:
        data = json.loads(response.read())
    return (time.perf_counter() - started) * 1000, data["trace"]["timings_ms"]


def percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(p * (len(ordered) - 1)))]


def measure(arch: str, url: str, token: str, runs: int, memory_mb: int) -> dict:
    shots = frames()
    cold_wall, cold = turn(url, token, shots[0][1])  # the first call after a deploy starts the container
    for _, image in shots:  # warm up every code path
        turn(url, token, image)
    regions, total, wall = [], [], []
    for _ in range(runs):
        for _, image in shots:
            w, timings = turn(url, token, image)
            wall.append(w)
            regions.append(timings["regions"])
            total.append(timings["total"])
    gb = memory_mb / 1024
    cost = statistics.mean(total) / 1000 * gb * PRICE_PER_GB_SECOND[arch] + PRICE_PER_REQUEST
    return {
        "arch": arch,
        "frames": len(shots),
        "samples": len(total),
        "memory_mb": memory_mb,
        "cold_wall_ms": round(cold_wall),
        "regions_ms": {"mean": statistics.mean(regions), "p50": percentile(regions, 0.5), "p95": percentile(regions, 0.95)},
        "total_ms": {"mean": statistics.mean(total), "p50": percentile(total, 0.5), "p95": percentile(total, 0.95)},
        "wall_ms": {"mean": statistics.mean(wall), "p50": percentile(wall, 0.5), "p95": percentile(wall, 0.95)},
        "cost_per_turn_usd": cost,
        "cost_per_1000_turns_usd": cost * 1000,
    }


def report(results: list[dict]) -> str:
    by = {r["arch"]: r for r in results}
    lines = [
        "| | " + " | ".join(r["arch"] for r in results) + " |",
        "|---|" + "---|" * len(results),
    ]
    for label, key, sub in (
        ("Region proposer, mean (ms)", "regions_ms", "mean"),
        ("Region proposer, p95 (ms)", "regions_ms", "p95"),
        ("Service time per turn, mean (ms)", "total_ms", "mean"),
        ("Service time per turn, p95 (ms)", "total_ms", "p95"),
        ("Client wall time, p50 (ms)", "wall_ms", "p50"),
    ):
        lines.append(f"| {label} | " + " | ".join(f"{r[key][sub]:.0f}" for r in results) + " |")
    lines.append("| First call after deploy (ms) | " + " | ".join(str(r["cold_wall_ms"]) for r in results) + " |")
    lines.append("| Compute cost per 1000 turns (USD) | " + " | ".join(f"{r['cost_per_1000_turns_usd']:.4f}" for r in results) + " |")
    if "arm64" in by and "x86" in by:
        a, x = by["arm64"], by["x86"]
        faster = 1 - a["total_ms"]["mean"] / x["total_ms"]["mean"]
        cheaper = 1 - a["cost_per_turn_usd"] / x["cost_per_turn_usd"]
        lines.append("")
        lines.append(
            f"Graviton is {faster:+.0%} in service time and {cheaper:.0%} cheaper per turn "
            f"(price {PRICE_PER_GB_SECOND['arm64']} against {PRICE_PER_GB_SECOND['x86']} per GB-second, "
            f"{a['memory_mb']} MB)."
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arm", required=True)
    parser.add_argument("--x86", required=True)
    parser.add_argument("--token", default="")
    parser.add_argument("--runs", type=int, default=15)
    parser.add_argument("--memory", type=int, default=2048)
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    results = []
    for arch, url in (("arm64", args.arm), ("x86", args.x86)):
        print(f"measuring {arch} ...", flush=True)
        results.append(measure(arch, url, args.token, args.runs, args.memory))
    if args.out:
        Path(args.out).write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(report(results))


if __name__ == "__main__":
    main()
