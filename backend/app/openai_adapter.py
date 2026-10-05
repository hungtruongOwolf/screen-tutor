"""Model adapter for any OpenAI-compatible chat API (Nebius Token Factory).

The capture goes to a vision model twice (as it is, and with the detected regions
marked and listed by number). The model answers with strict JSON that `answer.py`
turns into steps. It is never asked for pixel coordinates.

The reply is read as a stream: each step of the answer is handed on as soon as the
model has finished writing it, so the first step can be drawn while the later ones
are still being written. A non-streaming service works too (its whole reply is
treated as one piece of text).
"""

from __future__ import annotations

import base64
import json
from collections.abc import Callable, Iterator
from typing import Any

import httpx
from pydantic import ValidationError

from .answer import (  # noqa: F401  (build_decision and extract_json are re-exported)
    DecisionBuilder,
    ModelOutputError,
    StepDraft,
    build_decision,
    extract_json,
    parse_answer,
)
from .contract import Canvas, ChatTurn, Region
from .marking import clean_image, mark_regions
from .model_adapter import ModelDecision, StepDecision
from .prompting import SYSTEM_PROMPT, describe_canvas, describe_history, describe_regions  # noqa: F401
from .stream_parse import StepStreamParser
from .tavily import Source, describe_results

DEFAULT_BASE_URL = "https://api.tokenfactory.nebius.com/v1"
MAX_ATTEMPTS = 2

# Request fields that suit particular models. DeepSeek-V4.1-Flash otherwise spends
# its whole token budget on reasoning and returns nothing.
MODEL_EXTRA_BODY: dict[str, dict[str, Any]] = {
    "deepseek-ai/DeepSeek-V4.1-Flash": {"reasoning_effort": "none"},
}

# What decide_events yields: ("searching", query), ("step", StepDecision) and, last,
# ("final", ModelDecision).
Event = tuple[str, Any]


class OpenAICompatibleAdapter:
    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        api_key: str,
        model: str,
        timeout: float = 90.0,
        max_tokens: int = 4000,
        extra_body: dict[str, Any] | None = None,
        search: Callable[[str], list[Source]] | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.name = model
        self._search = search  # a web search (Tavily), or None
        self._model = model
        self._max_tokens = max_tokens
        # Extra request fields for this model, for example to switch off long reasoning.
        self._extra_body = dict(extra_body or {})
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
            transport=transport,
        )

    # -- the public calls -----------------------------------------------------------

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
        """The whole decision at once (reads the stream to the end)."""
        final: ModelDecision | None = None
        for kind, value in self.decide_events(
            question=question,
            image_png=image_png,
            regions=regions,
            canvas=canvas,
            turn=turn,
            history=history,
            goal=goal,
            trigger=trigger,
        ):
            if kind == "final":
                final = value
        assert final is not None
        return final

    def decide_events(
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
    ) -> Iterator[Event]:
        messages = self._messages(question, image_png, regions, canvas, history, goal, trigger)
        problem = ""
        lookups = 0
        found: list[Source] = []
        attempt = 0
        while attempt < MAX_ATTEMPTS:
            builder = DecisionBuilder(regions, turn, canvas)
            parser = StepStreamParser()
            pieces: list[str] = []
            finished: str | None = None
            streamed = 0
            failure: ModelOutputError | None = None

            try:
                for text, finish in self._stream(messages):
                    pieces.append(text)
                    finished = finish or finished
                    for raw in parser.feed(text):
                        try:
                            step = builder.add_step(StepDraft.model_validate(raw))
                        except ValidationError as error:
                            raise ModelOutputError(f"a step does not match the format: {error}") from error
                        streamed += 1
                        yield ("step", step)
            except ModelOutputError as error:
                failure = error
            reply = "".join(pieces)

            if failure is None:
                query = self._requested_search(reply) if lookups == 0 and streamed == 0 else None
                if query:
                    # The model asked for a web search: run it and ask again with the
                    # results. This is a normal step, not a failed attempt.
                    lookups = 1
                    yield ("searching", query)
                    found = self._search(query) if self._search else []
                    messages.append({"role": "assistant", "content": reply})
                    messages.append({"role": "user", "content": describe_results(query, found)})
                    continue
                try:
                    decision, fresh = builder.finish(parse_answer(reply))
                except ModelOutputError as error:
                    failure = error
                else:
                    for step in fresh:
                        yield ("step", step)
                    decision.attempts = attempt + 1
                    decision.lookups = lookups
                    decision.model = self.name
                    decision.sources = [{"title": s.title, "url": s.url} for s in found]
                    yield ("final", decision)
                    return

            # Something went wrong with this reply.
            if streamed > 0:
                # Steps were already shown: keep them rather than start over.
                decision = builder.partial_decision()
                decision.attempts = attempt + 1
                decision.lookups = lookups
                decision.model = self.name
                decision.sources = [{"title": s.title, "url": s.url} for s in found]
                yield ("final", decision)
                return
            attempt += 1
            snippet = " ".join(reply.split())[:160] or "(empty reply)"
            problem = f"{failure} Model said: {snippet}"
            if finished == "length" and not reply.strip():
                problem += " (it ran out of room while thinking)"
            # Ask once more, reminding the model of the required format.
            if reply.strip():
                messages.append({"role": "assistant", "content": reply})
            messages.append(
                {
                    "role": "user",
                    "content": "That was not usable. Reply again with ONLY the JSON object described, with no other text and no long reasoning.",
                }
            )
        raise ModelOutputError(problem)

    # -- building the request ---------------------------------------------------------

    def _messages(
        self,
        question: str,
        image_png: bytes,
        regions: list[Region],
        canvas: Canvas,
        history: list[ChatTurn] | None = None,
        goal: str | None = None,
        trigger: str = "user",
    ) -> list[dict[str, Any]]:
        clean = base64.b64encode(clean_image(image_png)).decode()
        marked = base64.b64encode(mark_regions(image_png, regions)).decode()
        conversation = describe_history(history)
        task = f"The learner's goal: {goal}\n\n" if goal else ""
        if trigger == "screen_changed":
            asked = "The screen changed after your last answer (the learner acted; they wrote nothing). Decide how the task is going."
        else:
            asked = f"Question: {question}"
        user_text = (
            (f"{conversation}\n\n" if conversation else "")
            + task
            + f"{asked}\n\nRegions:\n{describe_regions(regions)}\n\n{describe_canvas(canvas)}"
        )
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {"type": "text", "text": "Image 1: the screenshot as it is."},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{clean}"}},
                    {"type": "text", "text": "Image 2: the same screenshot with the regions outlined and labelled."},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{marked}"}},
                ],
            },
        ]

    @staticmethod
    def _requested_search(reply: str) -> str | None:
        """The query when the reply is only a search request, else None."""
        try:
            data = extract_json(reply)
        except ModelOutputError:
            return None
        if isinstance(data, dict) and isinstance(data.get("search"), str) and data["search"].strip():
            if not data.get("explanation") and not data.get("steps"):
                return data["search"].strip()[:200]
        return None

    # -- talking to the model -----------------------------------------------------------

    def _stream(self, messages: list[dict[str, Any]]) -> Iterator[tuple[str, str | None]]:
        """The reply as (text piece, finish reason) pairs. A service that does not
        stream returns one piece."""
        payload = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "temperature": 0,
            "messages": messages,
            "stream": True,
            **self._extra_body,
        }
        try:
            with self._client.stream("POST", "/chat/completions", json=payload) as response:
                if response.status_code != 200:
                    body = response.read().decode(errors="ignore")[:200]
                    raise ModelOutputError(f"the model service answered {response.status_code}: {body}")
                if "text/event-stream" not in response.headers.get("content-type", ""):
                    yield from self._whole_reply(response.read())
                    return
                for line in response.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        return
                    try:
                        choice = json.loads(data)["choices"][0]
                    except (ValueError, KeyError, IndexError):
                        continue
                    text = (choice.get("delta") or {}).get("content") or ""
                    finish = choice.get("finish_reason")
                    if text or finish:
                        yield text, finish
        except httpx.HTTPError as error:
            raise ModelOutputError(f"cannot reach the model service: {error}") from error

    @staticmethod
    def _whole_reply(body: bytes) -> Iterator[tuple[str, str | None]]:
        try:
            choice = json.loads(body)["choices"][0]
            yield choice["message"].get("content") or "", choice.get("finish_reason")
        except (KeyError, IndexError, ValueError, AttributeError) as error:
            raise ModelOutputError("the model service reply has an unexpected shape") from error
