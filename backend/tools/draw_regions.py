"""Debug helper: run the region proposer on an image and save a picture with
the numbered regions drawn on it.

    python tools/draw_regions.py <input.png | fixture-name> <output.png>

Fixture names: lecture, lecture_changed, app.
"""

from __future__ import annotations

import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))

from app.contract import CaptureMeta  # noqa: E402
from app.regions import decode_image, propose_regions  # noqa: E402
import fixtures  # noqa: E402

COLORS = {
    "text": (200, 80, 0),
    "figure": (0, 140, 0),
    "control": (0, 0, 220),
    "changed": (180, 0, 180),
    "line": (0, 128, 255),
    "label": (200, 0, 200),
}


def main() -> None:
    source, target = sys.argv[1], sys.argv[2]
    previous = None
    if source == "lecture":
        png = fixtures.to_png(fixtures.lecture_frame()[0])
    elif source == "lecture_changed":
        png = fixtures.to_png(fixtures.lecture_frame_with_change()[0])
        previous = fixtures.to_png(fixtures.lecture_frame()[0])
    elif source == "app":
        png = fixtures.to_png(fixtures.app_window()[0])
    else:
        png = Path(source).read_bytes()

    image = decode_image(png)
    height, width = image.shape[:2]
    regions = propose_regions(png, CaptureMeta(width=width, height=height), previous_png=previous)
    for region in regions:
        if region.kind == "screen":
            continue
        b = region.bbox
        color = COLORS.get(region.kind, (0, 0, 0))
        if region.kind == "line" and region.line:
            cv2.line(image, (region.line[0], region.line[1]), (region.line[2], region.line[3]), color, 3)
        else:
            cv2.rectangle(image, (b.x, b.y), (b.x + b.w, b.y + b.h), color, 2)
        label = f"{region.id} {region.kind}"
        cv2.putText(image, label, (b.x + 3, b.y + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2, cv2.LINE_AA)
    cv2.imwrite(target, image)
    print(f"{len(regions) - 1} regions")
    for region in regions[1:]:
        print(region.id, region.kind, region.bbox.model_dump())


if __name__ == "__main__":
    main()
