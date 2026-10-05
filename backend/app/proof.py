"""A visual aid: the rearrangement proof of the Pythagorean theorem.

Pure geometry (no model, no regions). A square of side a + b holds four copies of
a right triangle with legs a and b. Arranged one way they leave a tilted square of
side c uncovered; slid into the other arrangement they leave a square of side a
and a square of side b uncovered. The same four triangles cover the same area, so
c^2 = a^2 + b^2. The overlay shows the first picture, then slides the triangles.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass

Point = tuple[float, float]


@dataclass(frozen=True)
class Slide:
    """How a piece moves from where it was to where it ends: it starts displaced by
    (dx, dy) and turned by `rotate` degrees about `pivot` (its final centre) and
    ends at rest. Same convention as the overlay's CSS transform."""

    dx: float
    dy: float
    rotate: float
    pivot: Point


@dataclass(frozen=True)
class Arrangement:
    frame: list[Point]  # the big square
    first: list[list[Point]]  # four triangles, first arrangement
    hole: list[Point]  # the tilted square of side c they leave
    second: list[list[Point]]  # the same four triangles, second arrangement
    slides: list[Slide]  # slides[i]: how triangle i goes from `first` to `second`
    square_a: list[Point]  # what the second arrangement leaves: a square of side a ...
    square_b: list[Point]  # ... and one of side b


class ProofError(ValueError):
    pass


def _centroid(points: list[Point]) -> Point:
    return sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points)


def _rotate(p: Point, about: Point, quarter_turns: int) -> Point:
    angle = math.radians(90 * quarter_turns)
    cos, sin = round(math.cos(angle)), round(math.sin(angle))
    x, y = p[0] - about[0], p[1] - about[1]
    return about[0] + x * cos - y * sin, about[1] + x * sin + y * cos


def _same_corners(a: list[Point], b: list[Point]) -> bool:
    key = lambda pts: sorted((round(x, 3), round(y, 3)) for x, y in pts)  # noqa: E731
    return key(a) == key(b)


def _rect_triangles(x: float, y: float, w: float, h: float, diagonal: int) -> list[list[Point]]:
    if diagonal == 0:
        return [[(x, y), (x + w, y), (x, y + h)], [(x + w, y + h), (x + w, y), (x, y + h)]]
    return [[(x, y), (x + w, y), (x + w, y + h)], [(x, y), (x, y + h), (x + w, y + h)]]


def _slide(start: list[Point], end: list[Point]) -> tuple[int, Slide] | None:
    """The quarter turns that carry `start` onto `end` (a rigid motion, no flip)."""
    c_start, c_end = _centroid(start), _centroid(end)
    for turns in range(4):
        moved = [_rotate(p, c_start, turns) for p in start]
        moved = [(x - c_start[0] + c_end[0], y - c_start[1] + c_end[1]) for x, y in moved]
        if _same_corners(moved, end):
            # Seen from the end: undo the turn about the final centre, then shift back.
            # The short way round: a turn of 270 degrees is a turn of 90 the other way.
            rotate = -90.0 * turns
            if rotate < -180:
                rotate += 360
            return turns, Slide(dx=c_start[0] - c_end[0], dy=c_start[1] - c_end[1], rotate=rotate, pivot=c_end)
    return None


def arrange(a: float, b: float, origin: Point, size: float) -> Arrangement:
    """The proof drawn in a square of `size` pixels with its top left corner at
    `origin`; a and b are the lengths of the legs (only their ratio matters)."""
    if a <= 0 or b <= 0:
        raise ProofError("the legs must be positive")
    if max(a, b) / min(a, b) > 12:
        raise ProofError("the legs are too different in length to draw the proof")
    k = size / (a + b)
    la, lb = a * k, b * k
    s = la + lb
    ox, oy = origin

    first = [
        [(ox, oy), (ox + la, oy), (ox, oy + lb)],
        [(ox + s, oy), (ox + s, oy + la), (ox + la, oy)],
        [(ox + s, oy + s), (ox + lb, oy + s), (ox + s, oy + la)],
        [(ox, oy + s), (ox, oy + lb), (ox + lb, oy + s)],
    ]
    hole = [(ox + la, oy), (ox + s, oy + la), (ox + lb, oy + s), (ox, oy + lb)]
    square_a = [(ox, oy), (ox + la, oy), (ox + la, oy + la), (ox, oy + la)]
    square_b = [(ox + la, oy + la), (ox + s, oy + la), (ox + s, oy + s), (ox + la, oy + s)]

    for d1, d2 in itertools.product((0, 1), repeat=2):
        targets = _rect_triangles(ox + la, oy, lb, la, d1) + _rect_triangles(ox, oy + la, la, lb, d2)
        for order in itertools.permutations(range(4)):
            moves = [_slide(first[i], targets[order[i]]) for i in range(4)]
            if all(moves):
                return Arrangement(
                    frame=[(ox, oy), (ox + s, oy), (ox + s, oy + s), (ox, oy + s)],
                    first=first,
                    hole=hole,
                    second=[targets[order[i]] for i in range(4)],
                    slides=[m[1] for m in moves if m],
                    square_a=square_a,
                    square_b=square_b,
                )
    raise ProofError("no way to rearrange the triangles")  # not reachable for right triangles
