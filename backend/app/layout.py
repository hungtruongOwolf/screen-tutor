"""Automatic placement and fitting, so the model does not have to guess free space.

- equations are put in empty space near the thing they talk about
- squares built on lines are shrunk (all by the same factor, so areas stay
  proportional) until they fit on the screen
"""

from __future__ import annotations

import math

from .contract import Region
from .geometry import square_corners

EQUATION_FONT_SIZE = 26
EQUATION_HEIGHT = EQUATION_FONT_SIZE + 18
GRID_STEP = 24
MARGIN = 8


def plain_math(text: str) -> str:
    """The text as it reads without ^ and braces (used to size the box)."""
    return text.replace("^", "").replace("{", "").replace("}", "")


def equation_size(text: str) -> tuple[int, int]:
    """Width and height in pixels of the box the overlay draws around an equation.
    Must match the overlay renderer."""
    width = math.ceil(len(plain_math(text)) * EQUATION_FONT_SIZE * 0.6) + 24
    return width, EQUATION_HEIGHT


Rect = tuple[float, float, float, float]  # x, y, width, height


def _intersects(a: Rect, b: Rect, slack: float = 4) -> bool:
    return not (
        a[0] + a[2] <= b[0] + slack
        or b[0] + b[2] <= a[0] + slack
        or a[1] + a[3] <= b[1] + slack
        or b[1] + b[3] <= a[1] + slack
    )


def square_box(line: list[int], side: str, scale: float) -> Rect:
    """The bounding box (x, y, width, height) of the square built on a line."""
    corners = square_corners(line, side, scale)
    xs = [c[0] for c in corners]
    ys = [c[1] for c in corners]
    return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)


def boxes_hit(a: Rect, others: list[Rect], slack: float = 2) -> bool:
    return any(_intersects(a, other, slack) for other in others)


def place_box(
    width: float,
    height: float,
    near: Region | None,
    regions: list[Region],
    taken: list[Rect],
    screen: tuple[int, int],
) -> tuple[float, float] | None:
    """Top-left corner (capture pixels) of the free spot closest to `near` that fits
    a box of this size without covering any detected region or any rectangle in
    `taken`; None when there is none."""
    screen_w, screen_h = screen
    obstacles: list[Rect] = [
        (r.bbox.x, r.bbox.y, r.bbox.w, r.bbox.h) for r in regions if r.kind != "screen"
    ] + list(taken)

    if near and near.kind != "screen":
        centre = (near.bbox.x + near.bbox.w / 2, near.bbox.y + near.bbox.h / 2)
    else:
        centre = (screen_w / 2, screen_h / 2)

    best: tuple[float, float] | None = None
    best_distance = math.inf
    y = MARGIN
    while y + height <= screen_h - MARGIN:
        x = MARGIN
        while x + width <= screen_w - MARGIN:
            rect: Rect = (x, y, width, height)
            # Keep 8 px clear of everything.
            if not any(_intersects(rect, o, -8) for o in obstacles):
                distance = math.hypot(x + width / 2 - centre[0], y + height / 2 - centre[1])
                if distance < best_distance:
                    best, best_distance = (x, y), distance
            x += GRID_STEP
        y += GRID_STEP

    return best


def place_equation(
    text: str,
    near: Region | None,
    regions: list[Region],
    taken: list[Rect],
    screen: tuple[int, int],
) -> tuple[float, float]:
    """Top-left corner (capture pixels) for an equation: the free spot closest to
    `near`, not covering any detected region or any rectangle in `taken`."""
    width, height = equation_size(text)
    best = place_box(width, height, near, regions, taken, screen)
    if best is not None:
        return best
    # No free spot at all: the bottom left corner.
    return float(MARGIN), float(max(MARGIN, screen[1] - height - MARGIN))


def fit_square_scale(line: list[int], side: str, scale: float, screen: tuple[int, int]) -> float:
    """The largest scale not above `scale` at which the square built on the line stays
    inside the screen."""
    screen_w, screen_h = screen
    low, high = 0.05, scale
    if _inside(square_corners(line, side, high), screen_w, screen_h):
        return high
    for _ in range(24):
        middle = (low + high) / 2
        if _inside(square_corners(line, side, middle), screen_w, screen_h):
            low = middle
        else:
            high = middle
    # Round down, never up, so the result still fits.
    return math.floor(low * 1000) / 1000


def _inside(corners: list[tuple[float, float]], width: int, height: int) -> bool:
    return all(0 <= x <= width and 0 <= y <= height for x, y in corners)
