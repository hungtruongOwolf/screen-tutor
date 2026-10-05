"""Explain Turn: the main seam.

Takes a capture, a question, the current canvas and the previous capture's
regions; returns the explanation, the steps and the new canvas. Everything
model-specific sits behind the adapter.
"""

from __future__ import annotations

import base64
import binascii
import time
from collections import Counter
from collections.abc import Iterator
from typing import Any

from .canvas import apply_operations
from .contract import ExplainTurnRequest, ExplainTurnResponse, Source, Step, Trace
from .model_adapter import ModelAdapter, StepDecision
from .reanchor import reanchor_canvas
from .regions import ink_regions, occupancy_regions, propose_regions

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
JPEG_SIGNATURE = b"\xff\xd8\xff"


class BadRequest(ValueError):
    pass


def decode_capture(image_base64: str) -> bytes:
    try:
        data = base64.b64decode(image_base64, validate=True)
    except (binascii.Error, ValueError) as error:
        raise BadRequest("image_base64 is not valid base64") from error
    if not data.startswith((PNG_SIGNATURE, JPEG_SIGNATURE)):
        raise BadRequest("image must be a PNG or a JPEG")
    return data


def _model_events(adapter: ModelAdapter, **call: Any) -> Iterator[tuple[str, Any]]:
    """The adapter's events, or, for an adapter that only answers whole, its
    decision turned into the same events."""
    if hasattr(adapter, "decide_events"):
        yield from adapter.decide_events(**call)
        return
    decision = adapter.decide(**call)
    for step in decision.steps or [StepDecision(caption=decision.explanation, operations=decision.operations)]:
        yield ("step", step)
    yield ("final", decision)


def explain_events(
    request: ExplainTurnRequest, *, adapter: ModelAdapter
) -> Iterator[tuple[str, Any]]:
    """One turn as a series of events, so a client can start drawing early:

      ("regions", {...})    right after OpenCV, before the model is asked
      ("searching", {...})  when the model asked for a web search
      ("step", {...})       each step as soon as it is complete (with the canvas as
                            it should look at that step)
      ("done", response)    last: the whole ExplainTurnResponse

    Raises BadRequest, InvalidOperation or ModelOutputError when the turn fails.
    """
    timings: dict[str, float] = {}
    started = time.perf_counter()

    image = decode_capture(request.image_base64)

    mark = time.perf_counter()
    regions = propose_regions(image, request.capture)
    # For placing drawings in empty space (the model never sees these).
    regions += occupancy_regions(image, request.capture, first_id=max((r.id for r in regions), default=0) + 1)
    regions += ink_regions(image, request.capture, regions, first_id=max((r.id for r in regions), default=0) + 1)
    timings["regions"] = (time.perf_counter() - mark) * 1000

    # Move the drawings of earlier turns onto this capture; drop what no longer fits.
    canvas_before, dropped = reanchor_canvas(request.canvas, request.previous_regions, regions)
    yield (
        "regions",
        {
            "regions": regions,
            "canvas": canvas_before,
            "dropped_shape_ids": dropped,
            "width": request.capture.width,
            "height": request.capture.height,
        },
    )

    region_ids = {region.id for region in regions}
    steps: list[Step] = []
    running = canvas_before
    decision = None
    first_step_ms: float | None = None
    mark = time.perf_counter()
    for kind, value in _model_events(
        adapter,
        question=request.question,
        image_png=image,
        regions=regions,
        canvas=canvas_before,
        turn=request.turn,
        history=request.history,
        goal=request.goal,
        trigger=request.trigger,
    ):
        if kind == "searching":
            yield ("searching", {"query": value})
        elif kind == "step":
            for shape_op in value.operations:
                if shape_op.shape is not None:
                    used = {shape_op.shape.anchor.region_id}
                    if shape_op.shape.target_region_id is not None:
                        used.add(shape_op.shape.target_region_id)
                    unknown = used - region_ids
                    if unknown:
                        raise BadRequest(f"shape {shape_op.shape_id} uses unknown region {sorted(unknown)}")
            running = apply_operations(running, value.operations)
            step = Step(caption=value.caption, operations=value.operations, canvas=running)
            steps.append(step)
            if first_step_ms is None:
                first_step_ms = (time.perf_counter() - started) * 1000
            yield ("step", {"index": len(steps) - 1, "step": step})
        elif kind == "final":
            decision = value
    timings["model"] = (time.perf_counter() - mark) * 1000
    assert decision is not None

    timings["total"] = (time.perf_counter() - started) * 1000
    if first_step_ms is not None:
        timings["first_step"] = first_step_ms

    yield (
        "done",
        ExplainTurnResponse(
            explanation=decision.explanation,
            operations=decision.operations,
            canvas=running,
            steps=steps,
            sources=[Source(**s) for s in decision.sources],
            follow_ups=decision.follow_ups,
            goal=decision.goal,
            progress=decision.progress,
            regions=regions,
            chosen_region_ids=decision.chosen_region_ids,
            trace=Trace(
                regions_proposed=len(regions),
                attempts=decision.attempts,
                lookups=decision.lookups,
                model=decision.model or adapter.name,
                timings_ms=timings,
                region_counts=dict(Counter(region.kind for region in regions)),
                dropped_shape_ids=dropped,
            ),
        ),
    )


def explain_turn(
    request: ExplainTurnRequest, *, adapter: ModelAdapter
) -> ExplainTurnResponse:
    """The whole turn at once: the last event of explain_events."""
    response = None
    for kind, value in explain_events(request, adapter=adapter):
        if kind == "done":
            response = value
    assert response is not None
    return response
