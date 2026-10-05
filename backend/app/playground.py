"""The public web playground: a page, its static files and an open endpoint.

The endpoint takes the same request as the desktop app but needs no token, so it
is guarded instead: a size limit, a short question, bounded drawings and a rate
limit per visitor. PLAYGROUND_ENABLED=0 switches it all off.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .canvas import InvalidOperation
from .contract import ExplainTurnRequest, ExplainTurnResponse
from .explain import BadRequest, explain_turn
from .model_adapter import ModelAdapter
from .openai_adapter import ModelOutputError
from .ratelimit import SlidingWindowLimiter
from .streaming import STREAM_HEADERS, STREAM_TYPE, check_request, stream_turn
from .telemetry import log_turn_failed, log_turn_ok

STATIC = Path(__file__).resolve().parent / "static"
MAX_IMAGE_CHARS = 4_200_000  # base64 text, about 3 MB of picture
MAX_QUESTION_CHARS = 300
MAX_SHAPES = 60
MAX_REGIONS = 200
MAX_HISTORY_CHARS = 12_000


def visitor_of(request: Request) -> str:
    """Who is calling. Behind a Lambda Function URL the address arrives in
    X-Forwarded-For (its first entry is the visitor)."""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def install_playground(app: FastAPI, adapter: ModelAdapter) -> None:
    if os.environ.get("PLAYGROUND_ENABLED", "1") == "0":
        return
    limiter = SlidingWindowLimiter(int(os.environ.get("PLAYGROUND_RATE_PER_MINUTE", "8")))
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def page() -> str:
        return (STATIC / "playground.html").read_text(encoding="utf-8")

    def guard(request: ExplainTurnRequest, http: Request) -> None:
        if len(request.image_base64) > MAX_IMAGE_CHARS:
            raise HTTPException(status_code=413, detail="the picture is too large")
        if (
            len(request.question) > MAX_QUESTION_CHARS
            or len(request.canvas.shapes) > MAX_SHAPES
            or len(request.previous_regions) > MAX_REGIONS
            or sum(len(turn.text) for turn in request.history) > MAX_HISTORY_CHARS
        ):
            raise HTTPException(status_code=400, detail="the request is too large")
        if not limiter.allow(visitor_of(http)):
            raise HTTPException(status_code=429, detail="too many requests, wait a minute")

    @app.post("/playground/explain/stream")
    def explain_stream(request: ExplainTurnRequest, http: Request) -> StreamingResponse:
        """The same guarded turn, as newline-delimited JSON events."""
        guard(request, http)
        try:
            check_request(request)
        except BadRequest as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return StreamingResponse(stream_turn(request, adapter), media_type=STREAM_TYPE, headers=STREAM_HEADERS)

    @app.post("/playground/explain", response_model=ExplainTurnResponse)
    def explain(request: ExplainTurnRequest, http: Request) -> ExplainTurnResponse:
        guard(request, http)

        started = time.perf_counter()

        def elapsed() -> float:
            return (time.perf_counter() - started) * 1000

        try:
            response = explain_turn(request, adapter=adapter)
        except (BadRequest, InvalidOperation) as error:
            log_turn_failed(adapter.name, 400, type(error).__name__, elapsed())
            raise HTTPException(status_code=400, detail=str(error)) from error
        except ModelOutputError as error:
            log_turn_failed(adapter.name, 502, "ModelOutputError", elapsed())
            raise HTTPException(status_code=502, detail=str(error)) from error
        log_turn_ok(adapter.name, response.trace, len(response.steps), elapsed())
        return response
