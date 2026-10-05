"""The Explain Turn contract (see CONTEXT.md for the vocabulary).

One turn: a capture, the learner's question, the current canvas and the regions
of the previous capture go in; the explanation, the steps (each with the canvas
as it should look at that step), the regions and a trace come out. The model
never returns pixel coordinates: shapes anchor to a region id plus a rectangle
relative to that region (0..1).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ShapeKind = Literal[
    "arrow",
    "box",
    "ellipse",
    "highlight",
    "label",
    "step_number",
    "connector",
    "square_on_line",
    "polygon",
    "equation",
]


class BBox(BaseModel):
    x: int
    y: int
    w: int
    h: int


class Region(BaseModel):
    id: int
    bbox: BBox  # in capture pixels
    kind: str
    # Only for kind "line": the segment's end points (x1, y1, x2, y2) in capture pixels.
    line: list[int] | None = None
    # A 64-bit perceptual hash (hex) of the region's pixels. Lets a later turn tell
    # whether the content under a shape is still the same, without keeping images.
    signature: str | None = None


class Anchor(BaseModel):
    region_id: int
    # Rectangle relative to the region: 0..1 on both axes.
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    w: float = Field(ge=0, le=1)
    h: float = Field(ge=0, le=1)


class Point(BaseModel):
    # A point relative to the shape's region: 0..1 on both axes.
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


class Style(BaseModel):
    color: str = "#ff3b30"
    stroke_width: float = 4


class Motion(BaseModel):
    """A shape that arrives by sliding: it starts displaced by (dx, dy) pixels and
    turned by `rotate` degrees about the pivot, and ends where it is drawn. Only
    the animation uses it."""

    dx: float
    dy: float
    rotate: float
    pivot_x: float
    pivot_y: float


class Shape(BaseModel):
    id: str
    kind: ShapeKind
    anchor: Anchor
    text: str | None = None
    style: Style | None = None
    # Arrows only: where the arrowhead is. The anchor's x and y are the tail.
    end: Point | None = None
    # Arrows only: when set, the head lands on this region (the nearest point of
    # its box, or the line itself) instead of at `end`. This is how to point at a
    # small thing exactly.
    target_region_id: int | None = None
    # Polygons only: the corners, relative to the anchor's region.
    points: list[Point] | None = None
    # Squares on a line only: which side of the line (looking from its first end
    # to its second, on a screen where y grows downwards) the square is built on,
    # and its size as a fraction of the line's length.
    side: Literal["left", "right"] | None = None
    scale: float = 1.0
    # Pointing marks (boxes, arrows, highlights ...) are taken off when the next step draws
    # something; a shape with keep set stays.
    keep: bool = False
    # Set on the step in which the shape was moved (an update operation).
    motion: Motion | None = None
    turn: int = 0
    # Only used by connectors: ids of the shapes joined.
    from_id: str | None = None
    to_id: str | None = None


class Operation(BaseModel):
    op: Literal["add", "update", "remove"]
    shape_id: str
    shape: Shape | None = None  # required for add and update


class Canvas(BaseModel):
    shapes: list[Shape] = Field(default_factory=list)


class CaptureMeta(BaseModel):
    width: int = Field(gt=0)  # capture size in pixels
    height: int = Field(gt=0)
    scale: float = 1.0  # display scale factor at capture time
    mode: Literal["full_screen", "active_window"] = "full_screen"
    excluded: list[BBox] = Field(default_factory=list)


class ChatTurn(BaseModel):
    """One earlier message of the conversation: what the learner asked, or what the
    tutor said (its captions, joined)."""

    role: Literal["user", "assistant"]
    text: str = Field(max_length=2000)


class ExplainTurnRequest(BaseModel):
    session_id: str
    question: str
    image_base64: str
    capture: CaptureMeta
    canvas: Canvas = Field(default_factory=Canvas)
    # The regions the previous response returned. The service keeps nothing between
    # turns, so the client sends them back; they let drawings from earlier turns be
    # moved onto the new capture's regions (or dropped if their content changed).
    previous_regions: list[Region] = Field(default_factory=list)
    turn: int = 0
    # The conversation so far, oldest first (the service keeps nothing between turns).
    history: list[ChatTurn] = Field(default_factory=list, max_length=40)
    # What the learner is trying to get done (a task over several screens), as the tutor
    # last stated it, and what started this turn: a message from the learner, or the
    # app noticing that the screen changed after the last step.
    goal: str | None = Field(default=None, max_length=300)
    trigger: Literal["user", "screen_changed"] = "user"


class Source(BaseModel):
    title: str
    url: str


class Trace(BaseModel):
    regions_proposed: int
    attempts: int
    # How many web searches the turn made (0 or 1).
    lookups: int = 0
    model: str
    timings_ms: dict[str, float]
    region_counts: dict[str, int] = Field(default_factory=dict)
    # Shapes from earlier turns that no longer match anything on screen.
    dropped_shape_ids: list[str] = Field(default_factory=list)


class Step(BaseModel):
    caption: str
    operations: list[Operation]
    # The whole canvas as it should look once this step is shown.
    canvas: Canvas


class ExplainTurnResponse(BaseModel):
    explanation: str
    operations: list[Operation]
    canvas: Canvas  # the canvas after the last step
    steps: list[Step]
    # Web pages the answer relied on (when the model asked for a search).
    sources: list[Source] = Field(default_factory=list)
    # Short things the learner might ask next.
    follow_ups: list[str] = Field(default_factory=list)
    # The task the learner is on and how it is going (see the prompt).
    goal: str = ""
    progress: Literal["continue", "off_track", "waiting", "done"] | None = None
    regions: list[Region]
    chosen_region_ids: list[int]
    trace: Trace


class NarrateRequest(BaseModel):
    """One step's caption to be said aloud, with the question and what was said just before."""

    caption: str = Field(min_length=1, max_length=1500)
    question: str = Field(default="", max_length=1000)
    earlier: list[str] = Field(default_factory=list, max_length=6)


class NarrateResponse(BaseModel):
    spoken: str
    # "nemotron" (rewritten by the NVIDIA model), "model" (another model) or "caption" (read as it is).
    source: str
    model: str
