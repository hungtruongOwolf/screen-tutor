"""Operational logs and metrics.

Each turn writes one JSON line to stdout in CloudWatch's embedded metric format:
on AWS Lambda it becomes metrics (latency, failures, attempts) with no extra
code. Nothing about the content of a turn is logged: no image, no question, no
answer.
"""

from __future__ import annotations

import json
import time

NAMESPACE = "Sherpa"


def _emit(dimensions: dict[str, str], metrics: dict[str, tuple[float, str]], properties: dict) -> None:
    record = {
        "_aws": {
            "Timestamp": int(time.time() * 1000),
            "CloudWatchMetrics": [
                {
                    "Namespace": NAMESPACE,
                    "Dimensions": [list(dimensions)],
                    "Metrics": [{"Name": name, "Unit": unit} for name, (_, unit) in metrics.items()],
                }
            ],
        },
        **dimensions,
        **{name: value for name, (value, _) in metrics.items()},
        **properties,
    }
    print(json.dumps(record), flush=True)


def log_turn_ok(model: str, trace, steps: int, total_ms: float) -> None:
    timings = trace.timings_ms
    _emit(
        {"Model": model},
        {
            "TurnLatencyMs": (round(total_ms, 1), "Milliseconds"),
            "ModelLatencyMs": (round(timings.get("model", 0), 1), "Milliseconds"),
            "RegionsLatencyMs": (round(timings.get("regions", 0), 1), "Milliseconds"),
            "Attempts": (trace.attempts, "Count"),
            "Lookups": (trace.lookups, "Count"),
            "Regions": (trace.regions_proposed, "Count"),
            "Steps": (steps, "Count"),
            "DroppedShapes": (len(trace.dropped_shape_ids), "Count"),
            "TurnFailures": (0, "Count"),
        },
        {"Status": 200},
    )


def log_turn_failed(model: str, status: int, kind: str, total_ms: float) -> None:
    _emit(
        {"Model": model},
        {
            "TurnLatencyMs": (round(total_ms, 1), "Milliseconds"),
            "TurnFailures": (1, "Count"),
        },
        {"Status": status, "FailureKind": kind},
    )


def log_narration(model: str, total_ms: float, rewritten: bool) -> None:
    _emit(
        {"Model": model},
        {
            "NarrationLatencyMs": (round(total_ms, 1), "Milliseconds"),
            "NarrationRewritten": (1 if rewritten else 0, "Count"),
        },
        {},
    )
