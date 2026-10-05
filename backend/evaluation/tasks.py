"""Task effectiveness: does the tutor get a learner through a task of several screens?

The region-pick cases (`evaluation.run`) score one answer on one picture. This scores the loop the desktop
app runs: a question on the first screen, then an automatic turn each time the screen changes (trigger
"screen_changed", with the goal, the conversation, the drawings and the regions of the last capture), the
way `desktop/src/main.ts` does it. The screens are the made-up Acme Cloud console of the web playground
(three pages of "create a new user with programmatic access"; the task is worded so that there is one right way (there is an existing user, ci-bot, as a distractor)).

Per turn:
  pointed   a pointing mark (box, highlight, arrow ...) sits on the control the learner has to use next
  progress  the answer's verdict on how the learner is doing is the expected one
            (continue = on the way, off_track = went the wrong way)
  goal      the first answer states the goal of the task (so later turns keep it)
A task succeeds when every one of its turns is pointed and has the expected verdict.

    python -m evaluation.tasks --model deepseek-ai/DeepSeek-V4.1-Flash --repeat 3

Calls a live model (a few cents). Needs NEBIUS_API_KEY in .env. Writes evaluation/tasks_report_<model>.md and
evaluation/tasks_results_<model>.json (tasks_report.md is the written summary of both models).
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
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.contract import CaptureMeta, ChatTurn, ExplainTurnRequest  # noqa: E402
from app.env import load_env_file  # noqa: E402
from app.explain import explain_turn  # noqa: E402
from app.openai_adapter import DEFAULT_BASE_URL, MODEL_EXTRA_BODY, OpenAICompatibleAdapter  # noqa: E402

from .scoring import drawn_shapes, region_hits  # noqa: E402

HERE = Path(__file__).resolve().parent
SAMPLES = HERE.parent / "app" / "static" / "samples"

# Where the controls are on the three pages (1280 x 720 pixels): x, y, w, h.
NAV_ACCESS = (0, 291, 219, 40)  # "Access & Identity" in the left menu (dashboard)
CREATE_USER = (1144, 209, 106, 37)  # the "Create user" button (user list)
NAME_FIELD = (273, 267, 380, 40)  # "User name" (form)
PROGRAMMATIC = (273, 390, 420, 22)  # "Programmatic access" (form)

POINTERS = {"box", "ellipse", "highlight", "arrow", "label", "step_number"}


@dataclass
class TurnSpec:
    frame: str  # file in the samples folder
    question: str  # what the learner says (first turn) or "" for an automatic turn
    targets: list[tuple[int, int, int, int]]
    progress: set[str] | None = None  # accepted verdicts; None = not checked
    note: str = ""


@dataclass
class Scenario:
    name: str
    about: str
    turns: list[TurnSpec]
    repeat: int = 1


SCENARIOS = [
    Scenario(
        "from-the-dashboard",
        "A newcomer on the dashboard asks for an access key; the tutor guides click by click through three pages.",
        [
            TurnSpec("console1.png", "I am new here. I need a new user for my app that can use an access key (programmatic access). Where do I start?", [NAV_ACCESS]),
            TurnSpec("console2.png", "", [CREATE_USER], {"continue"}),
            TurnSpec("console3.png", "", [NAME_FIELD, PROGRAMMATIC], {"continue"}),
        ],
    ),
    Scenario(
        "starts-on-the-user-list",
        "The learner is already on the user list when asking.",
        [
            TurnSpec("console2.png", "I need a new user for my app that can use an access key (programmatic access). What do I do now?", [CREATE_USER]),
            TurnSpec("console3.png", "", [NAME_FIELD, PROGRAMMATIC], {"continue"}),
        ],
    ),
    Scenario(
        "goes-back",
        "The learner clicks the wrong way (back to the dashboard): the tutor must say so and lead back.",
        [
            TurnSpec("console2.png", "I need a new user for my app that can use an access key (programmatic access). What do I do now?", [CREATE_USER]),
            TurnSpec("console1.png", "", [NAV_ACCESS], {"off_track"}),
        ],
    ),
]


def make_adapter(model: str) -> OpenAICompatibleAdapter:
    return OpenAICompatibleAdapter(
        base_url=os.environ.get("MODEL_BASE_URL", DEFAULT_BASE_URL),
        api_key=os.environ.get("MODEL_API_KEY") or os.environ["NEBIUS_API_KEY"],
        model=model,
        extra_body=MODEL_EXTRA_BODY.get(model, {}),
        timeout=120,
    )


def run_scenario(model: str, scenario: Scenario, repeat_index: int) -> dict:
    adapter = make_adapter(model)
    history: list[ChatTurn] = []
    canvas = None
    previous = []
    goal = None
    results = []
    for number, spec in enumerate(scenario.turns):
        image = cv2.imdecode(np.fromfile(str(SAMPLES / spec.frame), dtype="uint8"), cv2.IMREAD_COLOR)
        height, width = image.shape[:2]
        ok, jpeg = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 92])
        trigger = "user" if spec.question else "screen_changed"
        text = spec.question or "(the screen changed)"
        extra = {"canvas": canvas, "previous_regions": previous} if canvas is not None else {}
        request = ExplainTurnRequest(
            session_id=f"{scenario.name}-{repeat_index}",
            question=text,
            image_base64=base64.b64encode(jpeg.tobytes()).decode(),
            capture=CaptureMeta(width=width, height=height),
            turn=number,
            history=list(history),
            goal=goal,
            trigger=trigger,
            **extra,
        )
        started = time.perf_counter()
        try:
            response = explain_turn(request, adapter=adapter)
        except Exception as error:  # a turn that fails counts as a failed turn
            results.append({"turn": number + 1, "error": f"{type(error).__name__}: {error}", "pointed": False, "progress_ok": False})
            break
        seconds = time.perf_counter() - started

        by_id = {r.id: r for r in response.regions}
        pointed = False
        for shape in drawn_shapes(response):
            if shape.kind not in POINTERS:
                continue
            region_id = shape.target_region_id if shape.kind == "arrow" and shape.target_region_id is not None else shape.anchor.region_id
            region = by_id.get(region_id)
            if region is not None and any(region_hits(region, target) for target in spec.targets):
                pointed = True
        progress_ok = spec.progress is None or (response.progress in spec.progress)
        results.append(
            {
                "turn": number + 1,
                "frame": spec.frame,
                "pointed": pointed,
                "progress": response.progress,
                "progress_ok": progress_ok,
                "goal": response.goal,
                "goal_stated": bool(response.goal) if number == 0 else None,
                "steps": len(response.steps),
                "seconds": round(seconds, 2),
                "caption": response.steps[0].caption if response.steps else "",
            }
        )
        goal = response.goal or goal
        history.append(ChatTurn(role="user", text=text))
        history.append(ChatTurn(role="assistant", text=" ".join(s.caption for s in response.steps)))
        canvas, previous = response.canvas, response.regions
    expected = len(scenario.turns)
    success = len(results) == expected and all(r["pointed"] and r["progress_ok"] for r in results)
    return {"scenario": scenario.name, "repeat": repeat_index, "success": success, "turns": results}


def report(model: str, runs: list[dict]) -> str:
    lines = [
        "# Task effectiveness",
        "",
        f"Model: `{model}`. Live runs of the guide loop on the made-up Acme Cloud console (three pages). "
        "A task succeeds when every turn points at the control the learner needs next and gives the expected verdict "
        "(`evaluation/tasks.py` has the definitions; the screens are in `backend/app/static/samples`).",
        "",
        "| Task | Runs | Succeeded | Turns pointed | Verdict right | Median s per turn |",
        "|---|---|---|---|---|---|",
    ]
    total_ok = total = 0
    for scenario in SCENARIOS:
        mine = [r for r in runs if r["scenario"] == scenario.name]
        turns = [t for r in mine for t in r["turns"]]
        checked = [t for t in turns if "progress_ok" in t]
        seconds = [t["seconds"] for t in turns if "seconds" in t]
        ok = sum(r["success"] for r in mine)
        total_ok += ok
        total += len(mine)
        lines.append(
            f"| {scenario.name} | {len(mine)} | {ok}/{len(mine)} | {sum(t['pointed'] for t in turns)}/{len(turns)} "
            f"| {sum(t['progress_ok'] for t in checked)}/{len(checked)} | {statistics.median(seconds) if seconds else 0:.1f} |"
        )
    lines += ["", f"**Overall: {total_ok}/{total} tasks completed.**", ""]
    failures = [(r, t) for r in runs for t in r["turns"] if not (t["pointed"] and t["progress_ok"])]
    if failures:
        lines += ["Turns that went wrong:", ""]
        for run, turn in failures:
            why = turn.get("error") or f"pointed={turn['pointed']}, verdict={turn.get('progress')}"
            lines.append(f"- {run['scenario']} (run {run['repeat'] + 1}), turn {turn['turn']}: {why}. {turn.get('caption', '')[:140]}")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=os.environ.get("MODEL_NAME", "deepseek-ai/DeepSeek-V4.1-Flash"))
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    load_env_file(HERE.parents[1] / ".env")
    jobs = [(scenario, i) for scenario in SCENARIOS for i in range(args.repeat)]
    with ThreadPoolExecutor(args.workers) as pool:
        runs = list(pool.map(lambda job: run_scenario(args.model, *job), jobs))
    slug = args.model.split("/")[-1].lower()
    (HERE / f"tasks_results_{slug}.json").write_text(json.dumps(runs, indent=2), encoding="utf-8")
    text = report(args.model, runs)
    (HERE / f"tasks_report_{slug}.md").write_text(text, encoding="utf-8")  # tasks_report.md is the written summary
    print(text)


if __name__ == "__main__":
    main()
