"""Developer tool: ask the real model about an image and draw its answer.

    python tools/ask_model.py <image.png> "<question>" <output.png> [model]

Uses MODEL_NAME / MODEL_BASE_URL / MODEL_API_KEY / NEBIUS_API_KEY from .env.
Prints the explanation, the trace and the shapes, and saves the image with the
regions and the model's shapes drawn on it. Calls the live model (costs a little).
"""

from __future__ import annotations

import base64
import os
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.contract import CaptureMeta, ExplainTurnRequest  # noqa: E402
from app.env import load_env_file  # noqa: E402
from app.explain import explain_turn  # noqa: E402
from app.geometry import square_corners  # noqa: E402
from app.openai_adapter import DEFAULT_BASE_URL, MODEL_EXTRA_BODY, OpenAICompatibleAdapter  # noqa: E402
from app.regions import decode_image  # noqa: E402
from app.tavily import TavilySearch  # noqa: E402

COLOR = (40, 40, 255)


def nearest(region, px, py):
    if region.line:
        x1, y1, x2, y2 = region.line
        dx, dy = x2 - x1, y2 - y1
        t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / ((dx * dx + dy * dy) or 1)))
        return int(x1 + t * dx), int(y1 + t * dy)
    b = region.bbox
    return int(max(b.x, min(px, b.x + b.w))), int(max(b.y, min(py, b.y + b.h)))


def fill_polygon(image, corners, color, alpha=0.25) -> None:
    overlay = image.copy()
    points = np.array([[int(x), int(y)] for x, y in corners], np.int32)
    cv2.fillPoly(overlay, [points], color)
    cv2.addWeighted(overlay, alpha, image, 1 - alpha, 0, image)
    cv2.polylines(image, [points], True, color, 3, cv2.LINE_AA)


def plain(text):
    return text.replace("^", "").replace("sqrt(", "sqrt(")


def draw_shapes(image, regions_list, canvas) -> None:
    regions = {r.id: r for r in regions_list}
    for shape in canvas.shapes:
        region = regions[shape.anchor.region_id]
        if shape.kind == "square_on_line":
            corners = square_corners(region.line, shape.side or "left", shape.scale)
            fill_polygon(image, corners, COLOR)
            cx = int(sum(c[0] for c in corners) / 4)
            cy = int(sum(c[1] for c in corners) / 4)
            if shape.text:
                cv2.putText(image, plain(shape.text), (cx - 50, cy), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA)
            continue
        if shape.kind == "polygon":
            b = region.bbox
            fill_polygon(image, [(b.x + p.x * b.w, b.y + p.y * b.h) for p in shape.points], COLOR)
            continue
        if shape.kind == "equation":
            b = region.bbox
            ex, ey = int(b.x + shape.anchor.x * b.w), int(b.y + shape.anchor.y * b.h)
            cv2.rectangle(image, (ex, ey - 28), (ex + 14 * len(plain(shape.text)) + 16, ey + 10), (30, 30, 30), -1)
            cv2.putText(image, plain(shape.text), (ex + 8, ey), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA)
            continue
        box = region.bbox
        a = shape.anchor
        x, y = int(box.x + a.x * box.w), int(box.y + a.y * box.h)
        w, h = int(a.w * box.w), int(a.h * box.h)
        if region.kind == "label" and shape.kind in ("box", "ellipse"):
            x, y, w, h = x - 6, y - 6, w + 12, h + 12
        if shape.kind == "highlight" and region.line:
            overlay = image.copy()
            cv2.line(overlay, (region.line[0], region.line[1]), (region.line[2], region.line[3]), COLOR, 14)
            cv2.addWeighted(overlay, 0.5, image, 0.5, 0, image)
        elif shape.kind in ("box", "highlight"):
            cv2.rectangle(image, (x, y), (x + w, y + h), COLOR, 3)
        elif shape.kind == "ellipse":
            cv2.ellipse(image, (x + w // 2, y + h // 2), (max(w // 2, 1), max(h // 2, 1)), 0, 0, 360, COLOR, 3)
        elif shape.kind == "arrow":
            if shape.target_region_id is not None:
                ex, ey = nearest(regions[shape.target_region_id], x, y)
            else:
                ex = int(box.x + (shape.end.x if shape.end else a.x) * box.w)
                ey = int(box.y + (shape.end.y if shape.end else a.y) * box.h)
            cv2.arrowedLine(image, (x, y), (ex, ey), COLOR, 3, tipLength=0.15)
        elif shape.kind == "step_number":
            cv2.circle(image, (x + 16, y + 16), 16, COLOR, -1)
            cv2.putText(image, shape.text or "", (x + 9, y + 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        if shape.text and shape.kind != "step_number":
            cv2.putText(image, shape.text, (x, max(y - 8, 16)), cv2.FONT_HERSHEY_SIMPLEX, 0.8, COLOR, 2, cv2.LINE_AA)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    source, question, target = sys.argv[1], sys.argv[2], sys.argv[3]
    load_env_file()
    model = sys.argv[4] if len(sys.argv) > 4 else os.environ.get("MODEL_NAME", "deepseek-ai/DeepSeek-V4.1-Flash")
    adapter = OpenAICompatibleAdapter(
        base_url=os.environ.get("MODEL_BASE_URL", DEFAULT_BASE_URL),
        api_key=os.environ.get("MODEL_API_KEY") or os.environ["NEBIUS_API_KEY"],
        model=model,
        extra_body=MODEL_EXTRA_BODY.get(model, {}),
        search=TavilySearch(os.environ["TAVILY_API_KEY"]) if os.environ.get("TAVILY_API_KEY") else None,
    )
    png = Path(source).read_bytes()
    image = decode_image(png)
    height, width = image.shape[:2]
    request = ExplainTurnRequest(
        session_id="tool",
        question=question,
        image_base64=base64.b64encode(png).decode(),
        capture=CaptureMeta(width=width, height=height),
    )
    response = explain_turn(request, adapter=adapter)

    print("model:", model)
    print("explanation:", response.explanation)
    print("chosen regions:", response.chosen_region_ids)
    print("web searches:", response.trace.lookups, "| sources:", [x.url for x in response.sources])
    for shape in response.canvas.shapes:
        print(" ", shape.id, shape.kind, shape.anchor.model_dump(), shape.text)
    print("timings_ms:", {k: round(v) for k, v in response.trace.timings_ms.items()})
    base = image.copy()
    stem, dot, extension = target.rpartition(".")
    for number, step in enumerate(response.steps, start=1):
        frame = base.copy()
        draw_shapes(frame, response.regions, step.canvas)
        path = f"{stem}_step{number}.{extension}" if len(response.steps) > 1 else target
        cv2.imwrite(path, frame)
        print(f"step {number}: {step.caption}")


if __name__ == "__main__":
    main()
