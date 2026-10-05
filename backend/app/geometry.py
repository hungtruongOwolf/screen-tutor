"""Geometry shared by the backend and its tools.

Screen coordinates: x grows to the right, y grows downwards. "Left" and "right"
of a line are as seen when looking along it from its first end to its second.
"""

from __future__ import annotations

import math

from .contract import Region

Side = str  # "left" or "right"


def left_normal(line: list[int]) -> tuple[float, float]:
    """Unit vector pointing to the left of the line (on screen)."""
    dx, dy = line[2] - line[0], line[3] - line[1]
    length = math.hypot(dx, dy) or 1.0
    return dy / length, -dx / length


def side_normal(line: list[int], side: Side) -> tuple[float, float]:
    nx, ny = left_normal(line)
    return (nx, ny) if side == "left" else (-nx, -ny)


def square_corners(line: list[int], side: Side, scale: float = 1.0) -> list[tuple[float, float]]:
    """The four corners of the square built on the line, on the given side. The
    side of the square is the line's length times `scale`."""
    x1, y1, x2, y2 = line
    length = math.hypot(x2 - x1, y2 - y1) * scale
    nx, ny = side_normal(line, side)
    ux, uy = (x2 - x1), (y2 - y1)
    norm = math.hypot(ux, uy) or 1.0
    ux, uy = ux / norm * length, uy / norm * length
    return [
        (x1, y1),
        (x1 + ux, y1 + uy),
        (x1 + ux + nx * length, y1 + uy + ny * length),
        (x1 + nx * length, y1 + ny * length),
    ]


def peer_lines(line_region: Region, regions: list[Region]) -> list[Region]:
    """The line regions that belong to the same figure as `line_region` (all lines
    when it is in no figure), the line itself included."""
    box = line_region.bbox

    def holds(outer: Region, inner_box) -> bool:
        return (
            outer.bbox.x <= inner_box.x
            and outer.bbox.y <= inner_box.y
            and outer.bbox.x + outer.bbox.w >= inner_box.x + inner_box.w
            and outer.bbox.y + outer.bbox.h >= inner_box.y + inner_box.h
        )

    figure = next((r for r in regions if r.kind == "figure" and holds(r, box)), None)
    return [
        r
        for r in regions
        if r.kind == "line" and r.line and (figure is None or holds(figure, r.bbox))
    ]


def outward_side(line_region: Region, regions: list[Region]) -> Side:
    """The side of a line that faces away from the rest of its figure.

    Takes the other lines inside the same figure (or all lines when there is no
    figure), finds the centre of their end points and picks the side opposite to it.
    """
    assert line_region.line is not None
    peers = peer_lines(line_region, regions)
    points = [(r.line[0], r.line[1]) for r in peers] + [(r.line[2], r.line[3]) for r in peers]
    if not points:
        return "left"
    cx = sum(p[0] for p in points) / len(points)
    cy = sum(p[1] for p in points) / len(points)
    x1, y1, x2, y2 = line_region.line
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    nx, ny = left_normal(line_region.line)
    return "left" if nx * (cx - mx) + ny * (cy - my) < 0 else "right"
