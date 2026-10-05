"""Scoring one answer against a case.

pointed:  at least one shape sits on a region that overlaps the target box, or, for
          a target segment, on a line region with the same end points or on a label
          right next to the segment
keyword:  the explanation or a caption contains one of the expected words
"""

from __future__ import annotations

from dataclasses import dataclass

from app.contract import ExplainTurnResponse, Region
from app.regions import Box, contained_fraction, iou

from .cases import Case


@dataclass
class Score:
    pointed: bool | None  # None when the case has no target
    keyword: bool | None  # None when the case has no keywords


def _box(region: Region) -> Box:
    b = region.bbox
    return Box(b.x, b.y, b.w, b.h, region.kind)


def region_hits(region: Region, target: Box) -> bool:
    """A region is on the target when they overlap clearly, or the region is a small
    part of the target (a label or a line inside it) or the target is a small part of
    the region."""
    if region.kind == "screen":
        return False
    region_box = _box(region)
    target_box = Box(*target, "target")
    if iou(region_box, target_box) >= 0.3:
        return True
    if contained_fraction(region_box, target_box) >= 0.7 and region_box.area >= 0.1 * target_box.area:
        return True
    return False


def _distance_to_segment(px: float, py: float, seg: tuple[int, int, int, int]) -> float:
    x1, y1, x2, y2 = seg
    dx, dy = x2 - x1, y2 - y1
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / ((dx * dx + dy * dy) or 1)))
    return ((px - (x1 + t * dx)) ** 2 + (py - (y1 + t * dy)) ** 2) ** 0.5


def segment_hit(region: Region, seg: tuple[int, int, int, int]) -> bool:
    """A line region with (about) the same end points, or a label right beside the segment."""
    if region.line:
        near = lambda a, b: max(abs(a[0] - b[0]), abs(a[1] - b[1])) <= 30  # noqa: E731
        ends = ((region.line[0], region.line[1]), (region.line[2], region.line[3]))
        want = ((seg[0], seg[1]), (seg[2], seg[3]))
        return (near(ends[0], want[0]) and near(ends[1], want[1])) or (near(ends[0], want[1]) and near(ends[1], want[0]))
    if region.kind == "label":
        b = region.bbox
        return _distance_to_segment(b.x + b.w / 2, b.y + b.h / 2, seg) <= 55
    return False


def drawn_shapes(response: ExplainTurnResponse):
    """Every shape the answer drew at any step: pointing marks are taken off when a later
    step draws, so the final canvas alone would miss them."""
    return [op.shape for step in response.steps for op in step.operations if op.shape is not None]


def score_answer(case: Case, response: ExplainTurnResponse) -> Score:
    pointed: bool | None = None
    by_id = {r.id: r for r in response.regions}
    if case.target is not None or case.segment is not None:

        def hits(region: Region) -> bool:
            if case.segment is not None:
                return segment_hit(region, case.segment)
            return region_hits(region, case.target)

        pointed = any(
            hits(by_id[shape.anchor.region_id])
            or (shape.target_region_id is not None and shape.target_region_id in by_id and hits(by_id[shape.target_region_id]))
            for shape in drawn_shapes(response)
            if shape.anchor.region_id in by_id
        )
    keyword: bool | None = None
    if case.keywords:
        text = " ".join([response.explanation] + [s.caption for s in response.steps]).lower()
        keyword = any(word.lower() in text for word in case.keywords)
    return Score(pointed, keyword)
