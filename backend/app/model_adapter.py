"""Model adapter: the single place where tests substitute a model.

The real adapter (Nebius, an NVIDIA vision model chosen by configuration)
arrives in ticket 04. Until then a recorded-response adapter returns a
canned decision so the whole path can be exercised without any network call.
"""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, Field

from .contract import Anchor, Canvas, ChatTurn, Operation, Region, Shape


class StepDecision(BaseModel):
    caption: str
    operations: list[Operation] = Field(default_factory=list)


class ModelDecision(BaseModel):
    explanation: str
    chosen_region_ids: list[int] = Field(default_factory=list)
    # All operations, in order. When `steps` is empty they make up the single step.
    operations: list[Operation] = Field(default_factory=list)
    steps: list[StepDecision] = Field(default_factory=list)
    attempts: int = 1
    lookups: int = 0
    model: str = ""  # the model that gave this answer (when it matters, e.g. hedged requests)
    sources: list[dict[str, str]] = Field(default_factory=list)
    follow_ups: list[str] = Field(default_factory=list)
    goal: str = ""
    progress: Literal["continue", "off_track", "waiting", "done"] | None = None


class ModelAdapter(Protocol):
    name: str

    def decide(
        self,
        *,
        question: str,
        image_png: bytes,
        regions: list[Region],
        canvas: Canvas,
        turn: int,
        history: list[ChatTurn] | None = None,
        goal: str | None = None,
        trigger: str = "user",
    ) -> ModelDecision: ...


class RecordedModelAdapter:
    """Returns a fixed decision: one box on the first region, plus a caption."""

    name = "recorded"

    def __init__(self, decision: ModelDecision | None = None) -> None:
        self._decision = decision

    def decide(
        self,
        *,
        question: str,
        image_png: bytes,
        regions: list[Region],
        canvas: Canvas,
        turn: int,
        history: list[ChatTurn] | None = None,
        goal: str | None = None,
        trigger: str = "user",
    ) -> ModelDecision:
        if self._decision is not None:
            return self._decision
        region = regions[0]
        shape = Shape(
            id=f"turn{turn}-box",
            kind="box",
            anchor=Anchor(region_id=region.id, x=0.25, y=0.25, w=0.5, h=0.5),
            text="Walking skeleton",
            turn=turn,
        )
        return ModelDecision(
            explanation=f"This is a canned answer to: {question}",
            chosen_region_ids=[region.id],
            operations=[Operation(op="add", shape_id=shape.id, shape=shape)],
        )
