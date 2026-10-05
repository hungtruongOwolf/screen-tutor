"""A turn as a stream of newline-delimited JSON events.

Each line is one JSON object with an "event" field:

  regions    right after OpenCV: the regions, the canvas moved onto them, sizes
  searching  the model asked for a web search (query)
  step       one step as soon as it is complete: index, caption, operations, canvas
  done       last: explanation, sources, trace, chosen regions, final canvas
  error      the turn failed: status and detail (the stream ends there)

A client can start drawing at the first "step" while the model is still writing
the rest.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterator

from .canvas import InvalidOperation
from .contract import ExplainTurnRequest
from .explain import BadRequest, decode_capture, explain_events
from .model_adapter import ModelAdapter
from .openai_adapter import ModelOutputError
from .telemetry import log_turn_failed, log_turn_ok

STREAM_HEADERS = {"Cache-Control": "no-store", "X-Accel-Buffering": "no"}
STREAM_TYPE = "application/x-ndjson"


def _line(event: str, **fields) -> str:
    return json.dumps({"event": event, **fields}, ensure_ascii=False) + "\n"


def _dump(model) -> object:
    return model.model_dump(mode="json")


def check_request(request: ExplainTurnRequest) -> None:
    """Problems that can be reported as an ordinary HTTP error before streaming starts."""
    decode_capture(request.image_base64)


def stream_turn(
    request: ExplainTurnRequest,
    adapter: ModelAdapter,
    on_error: Callable[[int], None] | None = None,
) -> Iterator[str]:
    started = time.perf_counter()

    def elapsed() -> float:
        return (time.perf_counter() - started) * 1000

    try:
        for kind, value in explain_events(request, adapter=adapter):
            if kind == "regions":
                yield _line(
                    "regions",
                    regions=[_dump(r) for r in value["regions"]],
                    canvas=_dump(value["canvas"]),
                    dropped_shape_ids=value["dropped_shape_ids"],
                    width=value["width"],
                    height=value["height"],
                )
            elif kind == "searching":
                yield _line("searching", query=value["query"])
            elif kind == "step":
                step = value["step"]
                yield _line(
                    "step",
                    index=value["index"],
                    caption=step.caption,
                    operations=[_dump(o) for o in step.operations],
                    canvas=_dump(step.canvas),
                )
            elif kind == "done":
                response = value
                log_turn_ok(adapter.name, response.trace, len(response.steps), elapsed())
                yield _line(
                    "done",
                    explanation=response.explanation,
                    sources=[_dump(s) for s in response.sources],
                    follow_ups=response.follow_ups,
                    goal=response.goal,
                    progress=response.progress,
                    chosen_region_ids=response.chosen_region_ids,
                    trace=_dump(response.trace),
                    canvas=_dump(response.canvas),
                    steps=len(response.steps),
                )
    except (BadRequest, InvalidOperation) as error:
        log_turn_failed(adapter.name, 400, type(error).__name__, elapsed())
        yield _line("error", status=400, detail=str(error))
    except ModelOutputError as error:
        log_turn_failed(adapter.name, 502, "ModelOutputError", elapsed())
        yield _line("error", status=502, detail=str(error))
