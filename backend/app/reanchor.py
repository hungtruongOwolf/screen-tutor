"""Moves drawings from earlier turns onto a new capture.

Region numbers are only valid for the capture that produced them: a tick of the
taskbar clock is enough to renumber everything. So each old shape's regions are
matched to the new regions by kind, position and a perceptual hash of their
pixels. A shape whose regions have no match (the content moved on) is dropped.
The service keeps no images: the client sends back the previous regions.
"""

from __future__ import annotations

from .contract import Canvas, Region, Shape
from .regions import Box, iou

MIN_OVERLAP = 0.6  # how much two boxes must overlap to be the same region
MAX_HASH_DISTANCE = 12  # of 64 bits
MAX_LINE_DRIFT = 15  # pixels, per end point


def hamming(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def _box(region: Region) -> Box:
    b = region.bbox
    return Box(b.x, b.y, b.w, b.h, region.kind)


def _same_region(old: Region, new: Region) -> float:
    """A score above zero when `new` is the same thing as `old`; zero when not."""
    if old.kind != new.kind:
        return 0.0
    overlap = iou(_box(old), _box(new))
    if overlap < MIN_OVERLAP:
        return 0.0
    if old.line and new.line:
        drift = max(abs(a - b) for a, b in zip(old.line, new.line))
        if drift > MAX_LINE_DRIFT:
            return 0.0
    if old.signature and new.signature and hamming(old.signature, new.signature) > MAX_HASH_DISTANCE:
        return 0.0
    return overlap


def match_region(old: Region, candidates: list[Region]) -> Region | None:
    best, best_score = None, 0.0
    for candidate in candidates:
        score = _same_region(old, candidate)
        if score > best_score:
            best, best_score = candidate, score
    return best


def _referenced_regions(shape: Shape) -> set[int]:
    ids = {shape.anchor.region_id}
    if shape.target_region_id is not None:
        ids.add(shape.target_region_id)
    return ids


def reanchor_canvas(
    canvas: Canvas, previous_regions: list[Region], regions: list[Region]
) -> tuple[Canvas, list[str]]:
    """Return the canvas with every shape moved onto `regions`, and the ids of the
    shapes that had to be dropped.

    Without `previous_regions` a shape is kept only if its region number still
    exists. Region 0 (the whole screen) always matches.
    """
    previous = {region.id: region for region in previous_regions}
    new_by_id = {region.id: region for region in regions}
    mapping: dict[int, int | None] = {0: 0}

    def target_of(region_id: int) -> int | None:
        if region_id in mapping:
            return mapping[region_id]
        if previous_regions:
            old = previous.get(region_id)
            match = match_region(old, regions) if old else None
            mapped = match.id if match else None
        else:
            mapped = region_id if region_id in new_by_id else None
        mapping[region_id] = mapped
        return mapped

    kept: list[Shape] = []
    dropped: list[str] = []
    for shape in canvas.shapes:
        moved = {rid: target_of(rid) for rid in _referenced_regions(shape)}
        if any(new is None for new in moved.values()):
            dropped.append(shape.id)
            continue
        anchor = shape.anchor.model_copy(update={"region_id": moved[shape.anchor.region_id]})
        update: dict = {"anchor": anchor}
        if shape.target_region_id is not None:
            update["target_region_id"] = moved[shape.target_region_id]
        kept.append(shape.model_copy(update=update))

    # A connector that lost an end goes with it.
    changed = True
    while changed:
        changed = False
        ids = {s.id for s in kept}
        survivors = []
        for shape in kept:
            ends = [e for e in (shape.from_id, shape.to_id) if e is not None]
            if any(e not in ids for e in ends):
                dropped.append(shape.id)
                changed = True
            else:
                survivors.append(shape)
        kept = survivors

    return Canvas(shapes=kept), dropped
