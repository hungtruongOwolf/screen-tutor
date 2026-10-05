"""Run the evaluation cases against one or more models and write a report.

    python -m evaluation.run --models deepseek-ai/DeepSeek-V4.1-Flash,google/gemma-3-27b-it
    python -m evaluation.run --models <id> --limit 6        (a quick try)

Calls live models (a few cents). Needs NEBIUS_API_KEY in .env. Writes
evaluation/report.md and evaluation/results.json.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.contract import CaptureMeta, ExplainTurnRequest  # noqa: E402
from app.env import load_env_file  # noqa: E402
from app.explain import explain_turn  # noqa: E402
from app.openai_adapter import DEFAULT_BASE_URL, MODEL_EXTRA_BODY, ModelOutputError, OpenAICompatibleAdapter  # noqa: E402

from .cases import Case, build_cases  # noqa: E402
from .scoring import score_answer  # noqa: E402

HERE = Path(__file__).resolve().parent


def run_case(model: str, case: Case) -> dict:
    adapter = OpenAICompatibleAdapter(
        base_url=os.environ.get("MODEL_BASE_URL", DEFAULT_BASE_URL),
        api_key=os.environ.get("MODEL_API_KEY") or os.environ["NEBIUS_API_KEY"],
        model=model,
        extra_body=MODEL_EXTRA_BODY.get(model, {}),
        timeout=120,
    )
    ok, jpeg = cv2.imencode(".jpg", case.image, [cv2.IMWRITE_JPEG_QUALITY, 92])
    height, width = case.image.shape[:2]
    request = ExplainTurnRequest(
        session_id=case.name,
        question=case.question,
        image_base64=base64.b64encode(jpeg.tobytes()).decode(),
        capture=CaptureMeta(width=width, height=height),
    )
    started = time.perf_counter()
    try:
        response = explain_turn(request, adapter=adapter)
    except ModelOutputError as error:
        return {"case": case.name, "kind": case.kind, "failed": True, "error": str(error)[:160], "seconds": time.perf_counter() - started}
    score = score_answer(case, response)
    return {
        "case": case.name,
        "kind": case.kind,
        "failed": False,
        "pointed": score.pointed,
        "keyword": score.keyword,
        "attempts": response.trace.attempts,
        "seconds": time.perf_counter() - started,
        "explanation": response.explanation[:160],
    }


def summarise(results: list[dict]) -> dict:
    def rate(rows: list[dict], key: str) -> str:
        counted = [r[key] for r in rows if not r["failed"] and r.get(key) is not None]
        return f"{sum(counted)}/{len(counted)}" if counted else "-"

    kinds = sorted({r["kind"] for r in results})
    return {
        "cases": len(results),
        "failed": sum(r["failed"] for r in results),
        "pointed": rate(results, "pointed"),
        "keyword": rate(results, "keyword"),
        "median_seconds": round(statistics.median(r["seconds"] for r in results), 1),
        "by_kind": {k: rate([r for r in results if r["kind"] == k], "pointed") for k in kinds},
        "retried": sum(1 for r in results if not r["failed"] and r["attempts"] > 1),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", required=True, help="comma separated model ids")
    parser.add_argument("--limit", type=int, default=0, help="only the first N cases")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    load_env_file()

    cases = build_cases()
    if args.limit:
        cases = cases[: args.limit]
    models = [m.strip() for m in args.models.split(",") if m.strip()]

    all_results: dict[str, list[dict]] = {}
    for model in models:
        print(f"running {len(cases)} cases on {model} ...", flush=True)
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            all_results[model] = list(pool.map(lambda c: run_case(model, c), cases))
        print("  ", json.dumps(summarise(all_results[model]), ensure_ascii=False), flush=True)

    (HERE / "results.json").write_text(json.dumps(all_results, ensure_ascii=False, indent=1), encoding="utf-8")

    lines = [
        "# Region-pick evaluation",
        "",
        f"{len(cases)} synthetic cases (right triangles, toolbars, bullet slides). **Pointed** = a shape sits on the region the answer must point at; **keyword** = the explanation contains the expected fact (where one is expected).",
        "",
        "| Model | Cases | Pointed correctly | Keyword correct | Failed | Retried | Median seconds | Pointed by kind |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for model, results in all_results.items():
        s = summarise(results)
        kinds = ", ".join(f"{k} {v}" for k, v in s["by_kind"].items())
        lines.append(f"| {model} | {s['cases']} | {s['pointed']} | {s['keyword']} | {s['failed']} | {s['retried']} | {s['median_seconds']} | {kinds} |")
    (HERE / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
