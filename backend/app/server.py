"""HTTP wrapper around Explain Turn."""

from __future__ import annotations

import json
import os
import time

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import StreamingResponse

from .canvas import InvalidOperation
from .env import load_env_file
from .hedging import HedgedAdapter
from .narration import DEFAULT_NARRATION_MODEL, Narrator, NemotronNarrator, timed
from .playground import install_playground
from .ratelimit import SlidingWindowLimiter
from .tavily import TavilySearch
from .telemetry import log_narration, log_turn_failed, log_turn_ok
from .contract import ExplainTurnRequest, ExplainTurnResponse, NarrateRequest, NarrateResponse
from .explain import BadRequest, explain_turn
from .streaming import STREAM_HEADERS, STREAM_TYPE, check_request, stream_turn
from .model_adapter import ModelAdapter, RecordedModelAdapter
from .openai_adapter import (
    DEFAULT_BASE_URL,
    MODEL_EXTRA_BODY,
    ModelOutputError,
    OpenAICompatibleAdapter,
)

load_env_file()

DEFAULT_MODEL = "deepseek-ai/DeepSeek-V4.1-Flash"
DEFAULT_FALLBACK = "Qwen/Qwen3.8-27B"  # equally accurate on the evaluation set


def build_adapter() -> ModelAdapter:
    name = os.environ.get("MODEL_ADAPTER", "fake")
    if name == "fake":
        return RecordedModelAdapter()
    if name == "nebius":
        # MODEL_* settings let a dedicated endpoint (for example an NVIDIA vision
        # model) replace the public default without code changes.
        api_key = os.environ.get("MODEL_API_KEY") or os.environ.get("NEBIUS_API_KEY")
        if not api_key:
            raise RuntimeError("NEBIUS_API_KEY (or MODEL_API_KEY) is not set")
        model = os.environ.get("MODEL_NAME", DEFAULT_MODEL)
        # MODEL_EXTRA_BODY (a JSON object) overrides the built-in per-model defaults.
        raw_extra = os.environ.get("MODEL_EXTRA_BODY")
        extra_body = json.loads(raw_extra) if raw_extra else MODEL_EXTRA_BODY.get(model, {})
        base_url = os.environ.get("MODEL_BASE_URL", DEFAULT_BASE_URL)
        search = TavilySearch(os.environ["TAVILY_API_KEY"]) if os.environ.get("TAVILY_API_KEY") else None
        primary = OpenAICompatibleAdapter(
            base_url=base_url, api_key=api_key, model=model, extra_body=extra_body, search=search
        )
        # A second model is asked too when the first is slow (empty name: no hedging).
        fallback = os.environ.get("MODEL_FALLBACK_NAME", DEFAULT_FALLBACK)
        if not fallback or fallback == model:
            return primary
        secondary = OpenAICompatibleAdapter(
            base_url=base_url,
            api_key=api_key,
            model=fallback,
            extra_body=MODEL_EXTRA_BODY.get(fallback, {}),
            search=search,
        )
        return HedgedAdapter(primary, secondary, float(os.environ.get("HEDGE_AFTER_SECONDS", "4")))
    raise RuntimeError(f"unknown MODEL_ADAPTER: {name}")

# What this version of the service understands.
FEATURES = ["stream", "history", "follow_ups", "tasks", "narration"]


def build_narrator() -> Narrator | None:
    """The model that turns captions into speech (an NVIDIA Nemotron model by default); None when it is
    switched off (NARRATION_MODEL empty) or there is no key (the canned model, tests)."""
    model = os.environ.get("NARRATION_MODEL", DEFAULT_NARRATION_MODEL)
    api_key = os.environ.get("MODEL_API_KEY") or os.environ.get("NEBIUS_API_KEY")
    if not model or not api_key or os.environ.get("MODEL_ADAPTER", "fake") == "fake":
        return None
    return NemotronNarrator(base_url=os.environ.get("MODEL_BASE_URL", DEFAULT_BASE_URL), api_key=api_key, model=model)


def create_app(adapter: ModelAdapter | None = None, narrator: Narrator | None = None) -> FastAPI:
    app = FastAPI(title="Sherpa backend")
    chosen = adapter or build_adapter()

    limiter = SlidingWindowLimiter(int(os.environ.get("RATE_LIMIT_PER_MINUTE", "30")))

    def check_token(request: Request, authorization: str | None = Header(default=None)) -> None:
        expected = os.environ.get("BACKEND_ACCESS_TOKEN")
        if expected and authorization != f"Bearer {expected}":
            raise HTTPException(status_code=401, detail="invalid access token")
        caller = authorization or (request.client.host if request.client else "unknown")
        if not limiter.allow(caller):
            log_turn_failed(chosen.name, 429, "RateLimited", 0.0)
            raise HTTPException(status_code=429, detail="too many requests, slow down")

    @app.get("/health")
    def health() -> dict[str, object]:
        # `features` lets a client notice a backend that is older than it is (one started before an
        # update ignores fields it does not know, for example the conversation, without a word).
        return {"status": "ok", "model": chosen.name, "features": FEATURES}

    speaker = narrator if narrator is not None else build_narrator()

    @app.post("/narrate", response_model=NarrateResponse)
    def narrate(request: NarrateRequest, _: None = Depends(check_token)) -> NarrateResponse:
        """One step's caption as spoken words. Always answers: with the caption itself when there is no
        narrator or it could not do better (`source` says which)."""
        if speaker is None:
            return NarrateResponse(spoken=request.caption, source="caption", model="")
        spoken, ms = timed(speaker, request.caption, request.question, request.earlier)
        log_narration(speaker.name, ms, spoken is not None)
        if spoken is None:
            return NarrateResponse(spoken=request.caption, source="caption", model=speaker.name)
        source = "nemotron" if "nemotron" in speaker.name.lower() else "model"
        return NarrateResponse(spoken=spoken, source=source, model=speaker.name)

    @app.post("/explain-turn", response_model=ExplainTurnResponse)
    def explain(
        request: ExplainTurnRequest, _: None = Depends(check_token)
    ) -> ExplainTurnResponse:
        started = time.perf_counter()

        def elapsed() -> float:
            return (time.perf_counter() - started) * 1000

        try:
            response = explain_turn(request, adapter=chosen)
        except (BadRequest, InvalidOperation) as error:
            log_turn_failed(chosen.name, 400, type(error).__name__, elapsed())
            raise HTTPException(status_code=400, detail=str(error)) from error
        except ModelOutputError as error:
            log_turn_failed(chosen.name, 502, "ModelOutputError", elapsed())
            raise HTTPException(status_code=502, detail=str(error)) from error
        log_turn_ok(chosen.name, response.trace, len(response.steps), elapsed())
        return response

    @app.post("/explain-turn/stream")
    def explain_stream(request: ExplainTurnRequest, _: None = Depends(check_token)) -> StreamingResponse:
        """The same turn as /explain-turn, as newline-delimited JSON events."""
        try:
            check_request(request)
        except BadRequest as error:
            log_turn_failed(chosen.name, 400, type(error).__name__, 0.0)
            raise HTTPException(status_code=400, detail=str(error)) from error
        return StreamingResponse(stream_turn(request, chosen), media_type=STREAM_TYPE, headers=STREAM_HEADERS)

    install_playground(app, chosen)
    return app


app = create_app()
