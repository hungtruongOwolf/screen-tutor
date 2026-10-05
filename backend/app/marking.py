"""Pictures for the vision model.

`clean_image` is the capture as it is, shrunk. `mark_regions` is the same
picture with the detected regions outlined and labelled R1, R2, ... so the model
can refer to them by number ("set-of-marks" prompting). The model reads content
from the clean picture and uses the marked one only to find labels, because
marks drawn over small details (digits, thin lines) make them hard to read.
"""

from __future__ import annotations

import cv2
import numpy as np

from .contract import Region
from .regions import HIDDEN_KINDS
from .regions import decode_image

# BGR colours per region kind.
COLORS = {
    "text": (200, 80, 0),
    "figure": (0, 150, 0),
    "control": (0, 0, 220),
    "changed": (180, 0, 180),
    "line": (0, 128, 255),
    "label": (200, 0, 200),
}
MAX_WIDTH = 1600
FONT = cv2.FONT_HERSHEY_SIMPLEX
FONT_SCALE = 0.5
BADGE_PAD = 3


def _shrunk(image_png: bytes) -> tuple[np.ndarray, int, int]:
    image = decode_image(image_png)
    if image is None:
        raise ValueError("cannot decode the capture")
    height, width = image.shape[:2]
    scale = min(1.0, MAX_WIDTH / width)
    if scale < 1.0:
        image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    return image, width, height


def _encode(image: np.ndarray, quality: int) -> bytes:
    ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise ValueError("cannot encode the image")
    return encoded.tobytes()


def clean_image(image_png: bytes, *, quality: int = 90) -> bytes:
    """The capture without any marks (shrunk to a reasonable width)."""
    image, _, _ = _shrunk(image_png)
    return _encode(image, quality)


def _overlaps(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def _place_badge(
    anchor: tuple[int, int, int, int],
    size: tuple[int, int],
    taken: list[tuple[int, int, int, int]],
    bounds: tuple[int, int],
) -> tuple[int, int, int, int]:
    """Choose a spot for a badge next to `anchor` (x1, y1, x2, y2) that stays inside
    the picture and does not cover another badge. Prefers outside the box."""
    x1, y1, x2, y2 = anchor
    bw, bh = size
    width, height = bounds
    candidates = [
        (x1, y1 - bh),  # above, left aligned
        (x2 - bw, y1 - bh),  # above, right aligned
        (x1, y2),  # below, left aligned
        (x2 - bw, y2),  # below, right aligned
        (x1 - bw, y1),  # left
        (x2, y1),  # right
        (x1, y1),  # inside, top left (last resort)
    ]
    fallback = None
    for cx, cy in candidates:
        cx = max(0, min(cx, width - bw))
        cy = max(0, min(cy, height - bh))
        box = (cx, cy, cx + bw, cy + bh)
        fallback = fallback or box
        if not any(_overlaps(box, other) for other in taken):
            return box
    return fallback  # type: ignore[return-value]


def mark_regions(image_png: bytes, regions: list[Region], *, quality: int = 90) -> bytes:
    """Return a JPEG of the capture with each detected region outlined with a thin
    line and labelled with a small badge placed beside it. The whole-capture
    region (kind "screen") is not drawn."""
    image, width, height = _shrunk(image_png)
    # Region boxes are in capture pixels. The whole-capture region tells us the
    # capture size, which may differ from the decoded image size.
    screen = next((r for r in regions if r.kind == "screen"), None)
    capture_width = screen.bbox.w if screen else width
    capture_height = screen.bbox.h if screen else height
    sx = image.shape[1] / capture_width
    sy = image.shape[0] / capture_height
    bounds = (image.shape[1], image.shape[0])

    taken: list[tuple[int, int, int, int]] = []
    # Draw big regions first so small ones (and their badges) end up on top.
    ordered = sorted(
        (r for r in regions if r.kind != "screen" and r.kind not in HIDDEN_KINDS),
        key=lambda r: r.bbox.w * r.bbox.h,
        reverse=True,
    )
    for region in ordered:
        color = COLORS.get(region.kind, (60, 60, 60))
        x1, y1 = int(region.bbox.x * sx), int(region.bbox.y * sy)
        x2, y2 = int((region.bbox.x + region.bbox.w) * sx), int((region.bbox.y + region.bbox.h) * sy)
        if region.kind == "line" and region.line:
            lx1, ly1 = int(region.line[0] * sx), int(region.line[1] * sy)
            lx2, ly2 = int(region.line[2] * sx), int(region.line[3] * sy)
            # A thin line right on the original one.
            cv2.line(image, (lx1, ly1), (lx2, ly2), color, 1, cv2.LINE_AA)
            # The badge sits a quarter of the way along, not in the middle where
            # labels such as the name of a side usually are.
            px, py = lx1 + (lx2 - lx1) // 4, ly1 + (ly2 - ly1) // 4
            anchor = (px - 2, py - 2, px + 2, py + 2)
        else:
            cv2.rectangle(image, (x1, y1), (x2, y2), color, 1)
            anchor = (x1, y1, x2, y2)

        text = f"R{region.id}"
        (tw, th), baseline = cv2.getTextSize(text, FONT, FONT_SCALE, 1)
        size = (tw + 2 * BADGE_PAD, th + baseline + 2 * BADGE_PAD - 2)
        bx1, by1, bx2, by2 = _place_badge(anchor, size, taken, bounds)
        taken.append((bx1, by1, bx2, by2))
        cv2.rectangle(image, (bx1, by1), (bx2, by2), color, -1)
        cv2.putText(
            image, text, (bx1 + BADGE_PAD, by2 - BADGE_PAD - baseline + 1), FONT, FONT_SCALE,
            (255, 255, 255), 1, cv2.LINE_AA,
        )

    return _encode(image, quality)
