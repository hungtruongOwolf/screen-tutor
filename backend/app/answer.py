"""Turns a model reply (JSON text) into a ModelDecision: validated, with ids made
unique and everything resolved against the regions. Nothing here talks to a model."""

from __future__ import annotations

import json
import math
import re
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

from .aids import AIDS, PythagoreanProof
from .contract import Anchor, BBox, Canvas, Operation, Point, Region, Shape, Style
from .geometry import outward_side, peer_lines
from .layout import Rect, equation_size, fit_square_scale, place_box, place_equation, square_box
from .proof import ProofError
from .model_adapter import ModelDecision, StepDecision

# Shape kinds the model may draw ("connector" is not offered to it).
KINDS = (
    "arrow", "box", "ellipse", "highlight", "label", "step_number",
    "square_on_line", "polygon", "equation",
)
# Squares built on lines are true to size (a square on a side of length 12 has sides
# of the same length on screen, so areas can be compared by eye). They share one
# scale, chosen from the whole figure up front (so steps can be built one at a time),
# which only drops below 1 when a square would run far off the screen: one that
# overhangs an edge by a little is left true to size (the edge cuts it off).
AUTO_SCALE_MAX = 1.0
SHRINK_ONLY_BELOW = 0.75
SIDES_IN_A_GROUP = 3
# Marks that point at things go when the next step draws something (unless kept), so
# every step stands on its own; squares, polygons and equations build up.
POINTER_KINDS = ("box", "ellipse", "arrow", "highlight", "label", "step_number")
MAX_FOLLOW_UPS = 3


class ModelOutputError(ValueError):
    """The model did not return something we can use."""


class PointDraft(BaseModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


class ShapeDraft(BaseModel):
    kind: str  # one of KINDS, or an aid (AIDS)
    region_id: int
    # A name the model gives the shape so a later step can remove it ("remove": ["eq1"]).
    name: str | None = None
    x: float = Field(default=0, ge=0, le=1)
    y: float = Field(default=0, ge=0, le=1)
    w: float = Field(default=0, ge=0, le=1)
    h: float = Field(default=0, ge=0, le=1)
    x2: float | None = Field(default=None, ge=0, le=1)
    y2: float | None = Field(default=None, ge=0, le=1)
    target_region_id: int | None = None
    points: list[PointDraft] | None = None
    side: Literal["left", "right", "outward", "inward"] | None = None
    scale: float | None = None
    text: str | None = None
    color: str | None = None
    keep: bool = False
    # Aids only: pythagoras_proof takes the lengths of the legs and a stage (1 or 2).
    a: float | None = None
    b: float | None = None
    stage: int | None = None
    # The learner's own letter for the hypotenuse (for example "x"), written in the hole.
    c_name: str | None = None

    @field_validator("kind")
    @classmethod
    def only_drawable(cls, value: str) -> str:
        if value not in KINDS and value not in AIDS:
            raise ValueError(f"kind {value!r} is not allowed here")
        return value


class StepDraft(BaseModel):
    caption: str = ""
    shapes: list[ShapeDraft] = Field(default_factory=list)
    remove: list[str] = Field(default_factory=list)


class ModelAnswer(BaseModel):
    analysis: str = ""
    # A web search the model wants before answering (the answer is then asked for again).
    search: str | None = None
    explanation: str = ""
    region_ids: list[int] = Field(default_factory=list)
    # Either a flat list of shapes (one step) ...
    shapes: list[ShapeDraft] = Field(default_factory=list)
    remove: list[str] = Field(default_factory=list)
    # ... or several steps.
    steps: list[StepDraft] = Field(default_factory=list)
    # What the learner might ask next (shown as quick replies).
    follow_ups: list[str] = Field(default_factory=list)
    # A task over several screens: the learner's goal in a few words, and how it is going.
    goal: str = ""
    progress: Literal["continue", "off_track", "waiting", "done"] | None = None


def extract_json(text: str) -> Any:
    """Pull the first JSON object out of a model reply (tolerates fences and
    reasoning blocks)."""
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", cleaned, flags=re.DOTALL)
    candidate = fenced.group(1) if fenced else cleaned
    start = candidate.find("{")
    if start == -1:
        raise ModelOutputError("the model reply has no JSON object")
    decoder = json.JSONDecoder()
    try:
        value, _ = decoder.raw_decode(candidate[start:])
    except json.JSONDecodeError as error:
        raise ModelOutputError(f"the model reply is not valid JSON: {error}") from error
    return value


def _regions_mentioned(draft: ShapeDraft) -> set[int]:
    ids = {draft.region_id}
    if draft.target_region_id is not None:
        ids.add(draft.target_region_id)
    return ids


class _Layout:
    """What is already on screen, so new equations avoid it."""

    def __init__(self, regions: list[Region], canvas: Canvas | None) -> None:
        self.regions = regions
        screen = next((r for r in regions if r.kind == "screen"), None)
        self.screen = (screen.bbox.w, screen.bbox.h) if screen else (1920, 1080)
        self.equations: dict[str, Rect] = {}
        self.squares: list[Rect] = []  # squares, drawn or reserved, that equations must not cover
        by_id = {r.id: r for r in regions}
        for shape in (canvas.shapes if canvas else []):
            region = by_id.get(shape.anchor.region_id)
            if shape.kind == "square_on_line" and region and region.line:
                self.squares.append(square_box(region.line, shape.side or "left", shape.scale))
            if shape.kind == "equation" and shape.text and region:
                width, height = equation_size(shape.text)
                self.equations[shape.id] = (
                    region.bbox.x + shape.anchor.x * region.bbox.w,
                    region.bbox.y + shape.anchor.y * region.bbox.h,
                    width,
                    height,
                )

    def place(self, text: str, shape_id: str, near: Region | None) -> tuple[float, float]:
        taken = list(self.equations.values()) + self.squares
        x, y = place_equation(text, near, self.regions, taken, self.screen)
        width, height = equation_size(text)
        self.equations[shape_id] = (x, y, width, height)
        return x, y

    def forget(self, shape_id: str) -> None:
        self.equations.pop(shape_id, None)


def _without_redundant_arrows(shapes: list[ShapeDraft]) -> list[ShapeDraft]:
    """An arrow at something a box, an ellipse or a highlight already marks adds nothing
    but clutter, so it is left out."""
    marked = {s.region_id for s in shapes if s.kind in ("box", "ellipse", "highlight")}
    return [s for s in shapes if not (s.kind == "arrow" and s.target_region_id is not None and s.target_region_id in marked)]


class DecisionBuilder:
    """Turns step drafts into steps one at a time, in order.

    The same builder serves a finished answer and a streamed one: a step can be
    built as soon as the model has written it. Ids are unique across the canvas
    and earlier steps; equations are placed in free space; squares share one scale.
    """

    def __init__(self, regions: list[Region], turn: int, canvas: Canvas | None = None) -> None:
        self.regions = regions
        self.turn = turn
        self.by_id = {r.id: r for r in regions}
        self.existing = {s.id for s in canvas.shapes} if canvas else set()
        self.names: dict[str, str] = {}  # the model's name for a shape -> its id
        self.layout = _Layout(regions, canvas)
        self.steps: list[StepDecision] = []
        self._counter = 0
        self._groups: dict[tuple[int, ...], float] = {}
        self._proofs: dict[tuple[float, float], PythagoreanProof] = {}
        # Pointing marks on screen that the next drawing step takes off.
        self._pointers: list[str] = [
            s.id for s in (canvas.shapes if canvas else []) if s.kind in POINTER_KINDS and not s.keep
        ]

    # -- ids and region checks -------------------------------------------------

    def _next_id(self) -> str:
        while True:
            self._counter += 1
            candidate = f"t{self.turn}-{self._counter}"
            if candidate not in self.existing:
                self.existing.add(candidate)
                return candidate

    def _check_regions(self, draft: StepDraft) -> None:
        mentioned: set[int] = set()
        for shape in draft.shapes:
            mentioned |= _regions_mentioned(shape)
        unknown = sorted(mentioned - set(self.by_id))
        if unknown:
            raise ModelOutputError(f"the model used region numbers that do not exist: {unknown}")

    # -- squares: one scale for the whole figure ---------------------------------

    def _square_group(self, region: Region) -> float:
        """The scale shared by squares built on the sides of this region's figure,
        computed once; every square it could contain is reserved so equations keep
        clear of them."""
        peers = sorted(
            peer_lines(region, self.regions),
            key=lambda r: -((r.line[2] - r.line[0]) ** 2 + (r.line[3] - r.line[1]) ** 2),
        )[:SIDES_IN_A_GROUP]
        if all(p.id != region.id for p in peers):
            peers = [region, *peers[: SIDES_IN_A_GROUP - 1]]
        key = tuple(sorted(p.id for p in peers))
        if key in self._groups:
            return self._groups[key]

        screen = self.layout.screen
        sides = {p.id: outward_side(p, self.regions) for p in peers}
        scale = AUTO_SCALE_MAX
        for p in peers:
            fitting = fit_square_scale(p.line, sides[p.id], scale, screen)
            if fitting < SHRINK_ONLY_BELOW * scale:
                scale = min(scale, fitting)
        scale = math.floor(scale * 1000) / 1000
        self._groups[key] = scale
        self.layout.squares += [square_box(p.line, sides[p.id], scale) for p in peers]
        return scale

    # -- shapes ---------------------------------------------------------------------

    def _make_shape(self, draft: ShapeDraft, shape_id: str) -> Shape:
        region = self.by_id[draft.region_id]
        style = Style(color=draft.color) if draft.color else None
        common = {
            "id": shape_id,
            "kind": draft.kind,
            "text": draft.text,
            "style": style,
            "keep": draft.keep,
            "turn": self.turn,
        }

        if draft.kind == "square_on_line":
            if not region.line:
                raise ModelOutputError(
                    f"square_on_line needs a line region, but region {draft.region_id} is {region.kind}"
                )
            side = draft.side
            if side in (None, "outward"):
                side = outward_side(region, self.regions)
            elif side == "inward":
                side = "right" if outward_side(region, self.regions) == "left" else "left"
            scale = self._square_group(region)
            return Shape(
                **common, anchor=Anchor(region_id=draft.region_id, x=0, y=0, w=1, h=1), side=side, scale=scale
            )

        if draft.kind == "polygon":
            if not draft.points or len(draft.points) < 3:
                raise ModelOutputError("a polygon needs at least three points")
            return Shape(
                **common,
                anchor=Anchor(region_id=draft.region_id, x=0, y=0, w=1, h=1),
                points=[Point(x=p.x, y=p.y) for p in draft.points],
            )

        if draft.kind == "equation":
            if not draft.text:
                raise ModelOutputError("an equation needs text")
            if "x" in draft.model_fields_set and "y" in draft.model_fields_set:
                return Shape(**common, anchor=Anchor(region_id=draft.region_id, x=draft.x, y=draft.y, w=0, h=0))
            # No position given: free space near the region it talks about, anchored
            # to the whole screen so it stays put.
            near = region if region.kind != "screen" else None
            px, py = self.layout.place(draft.text, shape_id, near)
            screen_w, screen_h = self.layout.screen
            return Shape(
                **common,
                anchor=Anchor(
                    region_id=0,
                    x=min(1.0, max(0.0, px / screen_w)),
                    y=min(1.0, max(0.0, py / screen_h)),
                    w=0,
                    h=0,
                ),
            )

        w, h = draft.w, draft.h
        if draft.kind in ("box", "ellipse", "highlight") and w == 0 and h == 0:
            # No size given: take the whole region.
            draft = draft.model_copy(update={"x": 0, "y": 0})
            w = h = 1
        end = None
        if draft.kind == "arrow":
            # Without an explicit head, fall back to the rectangle's far corner.
            end = Point(
                x=draft.x2 if draft.x2 is not None else min(1.0, draft.x + w),
                y=draft.y2 if draft.y2 is not None else min(1.0, draft.y + h),
            )
        return Shape(
            **common,
            anchor=Anchor(region_id=draft.region_id, x=draft.x, y=draft.y, w=w, h=h),
            end=end,
            target_region_id=draft.target_region_id if draft.kind == "arrow" else None,
        )

    # -- steps ----------------------------------------------------------------------

    def _referenced(self, reference: str) -> list[str]:
        """The shape ids a name in "remove" stands for ("proof" is every piece of the
        proof diagram)."""
        if reference == "proof" and self._proofs:
            return list(next(reversed(self._proofs.values())).ids.values())
        return [self.names.get(reference, reference)]

    def _aid(self, draft: ShapeDraft) -> list[Operation]:
        if draft.a is None or draft.b is None:
            raise ModelOutputError("pythagoras_proof needs a and b, the lengths of the two legs")
        key = (draft.a, draft.b)
        proof = self._proofs.get(key)
        stage = draft.stage or 1
        try:
            if proof is None:
                proof = self._place_proof(draft)
                self._proofs[key] = proof
            operations = proof.second() if stage >= 2 else proof.first()
        except ProofError as error:
            raise ModelOutputError(str(error)) from error
        for operation in operations:
            if operation.op == "add":
                self.existing.add(operation.shape_id)
        return operations

    def _place_proof(self, draft: ShapeDraft) -> PythagoreanProof:
        """Pick free space for the diagram, as big as fits, and reserve it."""
        screen_w, screen_h = self.layout.screen
        figure = self.by_id.get(draft.region_id)
        figure = figure if figure and figure.kind != "screen" else None
        taken = list(self.layout.equations.values()) + self.layout.squares
        if figure is not None:
            # Room around the picture itself: its numbers and letters sit just outside its box.
            b = figure.bbox
            taken.append((b.x - 70, b.y - 70, b.w + 140, b.h + 140))
        chosen: tuple[int, tuple[float, float]] | None = None
        fallback: tuple[float, int, tuple[float, float]] | None = None
        for size in (340, 300, 260, 220, 180):
            # The best place is beside the figure, level with its top: the learner looks
            # from one to the other without the diagram sliding off to a far corner.
            near = None
            if figure is not None:
                near = Region(
                    id=-1,
                    kind="text",
                    bbox=BBox(x=figure.bbox.x + figure.bbox.w + 24, y=figure.bbox.y, w=size, h=size + 30),
                )
            spot = place_box(size, size + 30, near, self.regions, taken, (screen_w, screen_h))
            if spot is None:
                continue
            if near is None:
                chosen = (size, spot)
                break
            distance = math.hypot(spot[0] - near.bbox.x, spot[1] - near.bbox.y)
            # A big diagram far away is worse than a smaller one close by.
            if distance <= max(480, 1.5 * size):
                chosen = (size, spot)
                break
            if fallback is None or distance < fallback[0]:
                fallback = (distance, size, spot)
        if chosen is None and fallback is not None:
            chosen = (fallback[1], fallback[2])
        if chosen is None:
            chosen = (180, (float(screen_w - 200), 16.0))
        size, spot = chosen
        proof = PythagoreanProof(
            draft.a,
            draft.b,
            (spot[0], spot[1] + 30),
            size,
            (screen_w, screen_h),
            self._next_id,
            self.turn,
            (draft.c_name or "c").strip()[:6] or "c",
        )
        self.layout.squares.append(proof.box)
        return proof

    def add_step(self, draft: StepDraft, default_caption: str = "") -> StepDecision:
        """Build the next step. Raises ModelOutputError if the draft cannot be used."""
        self._check_regions(draft)
        operations: list[Operation] = []
        for reference in draft.remove:
            # Remove by the model's own name or by id. Something that is not there
            # is ignored, not an error.
            for shape_id in self._referenced(reference):
                if shape_id in self.existing:
                    self.existing.discard(shape_id)
                    self.layout.forget(shape_id)
                    operations.append(Operation(op="remove", shape_id=shape_id))
        if draft.shapes:
            # Pointers of earlier steps make way for this step's drawing.
            for shape_id in self._pointers:
                if shape_id in self.existing and not any(op.shape_id == shape_id for op in operations):
                    self.existing.discard(shape_id)
                    operations.append(Operation(op="remove", shape_id=shape_id))
            self._pointers = []
        for shape_draft in _without_redundant_arrows(draft.shapes):
            if shape_draft.kind in AIDS:
                operations += self._aid(shape_draft)
                continue
            shape = self._make_shape(shape_draft, self._next_id())
            if shape_draft.name:
                self.names[shape_draft.name] = shape.id
            operations.append(Operation(op="add", shape_id=shape.id, shape=shape))
            if shape.kind in POINTER_KINDS and not shape.keep:
                self._pointers.append(shape.id)
        step = StepDecision(caption=draft.caption.strip() or default_caption.strip(), operations=operations)
        self.steps.append(step)
        return step

    def finish(self, answer: ModelAnswer) -> tuple[ModelDecision, list[StepDecision]]:
        """The decision for a complete answer, and the steps that were not built yet
        (all of them for a non-streamed answer; none if every step was streamed)."""
        silent = answer.progress == "waiting" and not answer.steps and not answer.explanation.strip()
        if not answer.explanation.strip() and not answer.steps and not silent:
            raise ModelOutputError("the model reply has no explanation")
        fresh: list[StepDecision] = []
        if answer.steps:
            for draft in answer.steps[len(self.steps) :]:
                fresh.append(self.add_step(draft, answer.explanation))
        elif silent:
            pass  # the screen changed but there is nothing to say yet: no step at all
        elif not self.steps:
            fresh.append(
                self.add_step(StepDraft(caption=answer.explanation, shapes=answer.shapes, remove=answer.remove))
            )
        decision = self._decision(answer.explanation, answer.region_ids)
        decision.follow_ups = [t.strip() for t in answer.follow_ups if t.strip()][:MAX_FOLLOW_UPS]
        decision.goal = answer.goal.strip()[:300]
        decision.progress = answer.progress
        return decision, fresh

    def partial_decision(self) -> ModelDecision:
        """What can be kept when the answer broke off after some steps were built."""
        return self._decision("", [])

    def _decision(self, explanation: str, region_ids: list[int]) -> ModelDecision:
        known = set(self.by_id)
        flat = [op for step in self.steps for op in step.operations]
        text = explanation.strip() or (self.steps[0].caption if self.steps else "")
        return ModelDecision(
            explanation=text,
            chosen_region_ids=[r for r in region_ids if r in known],
            operations=flat,
            steps=list(self.steps),
        )


def parse_answer(reply: str) -> ModelAnswer:
    try:
        return ModelAnswer.model_validate(extract_json(reply))
    except ValidationError as error:
        raise ModelOutputError(f"the model reply does not match the format: {error}") from error


def build_decision(
    reply: str, regions: list[Region], turn: int, canvas: Canvas | None = None
) -> ModelDecision:
    """A whole reply into a decision (the non-streaming path)."""
    builder = DecisionBuilder(regions, turn, canvas)
    decision, _ = builder.finish(parse_answer(reply))
    return decision
