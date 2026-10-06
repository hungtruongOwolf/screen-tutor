"""Write a decision trace of the guide loop: what OpenCV found, what the model chose, what it did next.

    python tools/trace.py --model deepseek-ai/DeepSeek-V4.1-Flash

Runs two scenarios of evaluation/tasks.py with a live model (a few cents; needs NEBIUS_API_KEY in .env) and
writes evaluation/trace.md. For every turn it lists the regions OpenCV proposed, how many of the previous
turn's regions are still on the new screen (compared by perceptual hash, no image kept), the region the
answer points at, the verdict and the caption, so a reader can see that the OpenCV output of the new screen
is what changes the next decision.
"""

from __future__ import annotations

import argparse
import base64
import collections
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.contract import CaptureMeta, ChatTurn, ExplainTurnRequest  # noqa: E402
from app.env import load_env_file  # noqa: E402
from app.explain import explain_turn  # noqa: E402
from evaluation.scoring import drawn_shapes  # noqa: E402
from evaluation.tasks import POINTERS, SAMPLES, SCENARIOS, make_adapter  # noqa: E402

HERE = Path(__file__).resolve().parents[1] / "evaluation"
SHOWN = {"scenario": ("from-the-dashboard", "goes-back")}


def trace_scenario(model: str, scenario) -> list[str]:
    adapter = make_adapter(model)
    history: list[ChatTurn] = []
    canvas = None
    previous = []
    goal = None
    out = [f"### {scenario.name}", "", scenario.about, ""]
    for number, spec in enumerate(scenario.turns):
        image = cv2.imdecode(np.fromfile(str(SAMPLES / spec.frame), dtype="uint8"), cv2.IMREAD_COLOR)
        height, width = image.shape[:2]
        _, jpeg = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 92])
        trigger = "user" if spec.question else "screen_changed"
        extra = {"canvas": canvas, "previous_regions": previous} if canvas is not None else {}
        request = ExplainTurnRequest(
            session_id=f"trace-{scenario.name}",
            question=spec.question or "(the screen changed)",
            image_base64=base64.b64encode(jpeg.tobytes()).decode(),
            capture=CaptureMeta(width=width, height=height),
            turn=number,
            history=list(history),
            goal=goal,
            trigger=trigger,
            **extra,
        )
        response = explain_turn(request, adapter=adapter)
        kinds = collections.Counter(r.kind for r in response.regions)
        old = {r.signature for r in previous if r.signature}
        new = {r.signature for r in response.regions if r.signature}
        kept = len(old & new)
        by_id = {r.id: r for r in response.regions}
        pointed = []
        for shape in drawn_shapes(response):
            if shape.kind in POINTERS:
                rid = shape.target_region_id if shape.kind == "arrow" and shape.target_region_id is not None else shape.anchor.region_id
                r = by_id.get(rid)
                if r is not None:
                    pointed.append(f"{shape.kind} on region {r.id} ({r.kind}, box {r.bbox.x},{r.bbox.y} {r.bbox.w}x{r.bbox.h})")
        out += [
            f"**Turn {number + 1}** ({'the learner asks' if trigger == 'user' else 'automatic, the screen changed'}; frame `{spec.frame}`)",
            "",
            f"- OpenCV 5 proposed {len(response.regions)} regions: " + ", ".join(f"{n} {k}" for k, n in kinds.most_common()) + ".",
        ]
        if previous:
            out.append(f"- Of the {len(old)} regions of the previous screen, {kept} are still here (same perceptual hash): "
                       + ("the page is largely the same." if kept > len(old) / 2 else "the page is a different one."))
        out += [
            "- The answer points at: " + ("; ".join(pointed) if pointed else "nothing") + ".",
            f"- Verdict: `{response.progress}`. Goal kept: {response.goal or goal or '-'}",
            f"- Said: \"{response.steps[0].caption if response.steps else ''}\"",
            "",
        ]
        goal = response.goal or goal
        history.append(ChatTurn(role="user", text=request.question))
        history.append(ChatTurn(role="assistant", text=" ".join(s.caption for s in response.steps)))
        canvas, previous = response.canvas, response.regions
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="deepseek-ai/DeepSeek-V4.1-Flash")
    args = parser.parse_args()
    load_env_file(Path(__file__).resolve().parents[2] / ".env")
    lines = [
        "# Decision trace",
        "",
        f"Model `{args.model}`; live run of the guide loop on the made-up Acme Cloud console (`tools/trace.py`).",
        "Each turn shows what OpenCV 5 found on the new screen and what the agent decided because of it.",
        "",
    ]
    for scenario in SCENARIOS:
        if scenario.name in SHOWN["scenario"]:
            lines += trace_scenario(args.model, scenario)
    (HERE / "trace.md").write_text("\n".join(lines), encoding="utf-8")
    print("wrote evaluation/trace.md")


if __name__ == "__main__":
    main()
