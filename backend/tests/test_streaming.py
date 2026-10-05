"""Streaming a turn: steps reach the client while the model is still writing."""

import base64
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.contract import Canvas, CaptureMeta, ExplainTurnRequest
from app.explain import explain_events
from app.model_adapter import RecordedModelAdapter
from app.openai_adapter import ModelOutputError, OpenAICompatibleAdapter
from app.regions import propose_regions
from app.server import create_app
from fixtures import lecture_frame, to_png

CAPTURE = CaptureMeta(width=1280, height=720)
IMAGE = to_png(lecture_frame()[0])
REGIONS = propose_regions(IMAGE, CAPTURE)

ANSWER = {
    "analysis": "reading",
    "explanation": "summary",
    "region_ids": [0],
    "steps": [
        {"caption": "first", "shapes": [{"kind": "box", "region_id": 0, "keep": True}]},
        {"caption": "second", "shapes": [{"kind": "ellipse", "region_id": 0, "keep": True}]},
        {"caption": "third", "shapes": [{"kind": "highlight", "region_id": 0, "keep": True}]},
    ],
}


def sse(pieces, log=None, finish="stop"):
    """A server-sent-events body, one piece of the model's text per event."""

    def body():
        for index, piece in enumerate(pieces):
            if log is not None:
                log.append(f"sent {index}")
            yield f"data: {json.dumps({'choices': [{'delta': {'content': piece}}]})}\n\n".encode()
        yield f"data: {json.dumps({'choices': [{'delta': {}, 'finish_reason': finish}]})}\n\n".encode()
        yield b"data: [DONE]\n\n"

    return body()


def pieces_of(text, size=24):
    return [text[i : i + size] for i in range(0, len(text), size)]


def adapter_streaming(replies, log=None, status=200):
    """The model service answers each request with the next reply, streamed."""
    queue = list(replies)

    def handler(request: httpx.Request) -> httpx.Response:
        if status != 200:
            return httpx.Response(status, text="boom")
        pieces = queue.pop(0)
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=sse(pieces, log))

    return OpenAICompatibleAdapter(
        base_url="https://m.test/v1", api_key="k", model="m", transport=httpx.MockTransport(handler)
    )


def events_of(adapter, canvas=None):
    return adapter.decide_events(
        question="q", image_png=IMAGE, regions=REGIONS, canvas=canvas or Canvas(), turn=0
    )


def test_the_first_step_arrives_before_the_model_has_finished_writing():
    log = []
    adapter = adapter_streaming([pieces_of(json.dumps(ANSWER))], log)

    for kind, _ in events_of(adapter):
        log.append(f"event {kind}")

    first_step = log.index("event step")
    last_piece = max(i for i, entry in enumerate(log) if entry.startswith("sent"))
    assert first_step < last_piece  # drawn before the model was done


def test_every_step_comes_in_order_and_then_the_final_decision():
    adapter = adapter_streaming([pieces_of(json.dumps(ANSWER), 7)])

    events = list(events_of(adapter))

    assert [k for k, _ in events] == ["step", "step", "step", "final"]
    assert [v.caption for k, v in events if k == "step"] == ["first", "second", "third"]
    final = events[-1][1]
    assert final.attempts == 1 and final.explanation == "summary"
    assert [s.caption for s in final.steps] == ["first", "second", "third"]
    assert [op.shape_id for op in final.operations] == ["t0-1", "t0-2", "t0-3"]


def test_an_answer_without_steps_gives_one_step_at_the_end():
    flat = {"explanation": "quick", "shapes": [{"kind": "box", "region_id": 0}]}
    adapter = adapter_streaming([pieces_of(json.dumps(flat))])

    events = list(events_of(adapter))

    assert [k for k, _ in events] == ["step", "final"]
    assert events[0][1].caption == "quick"


def test_a_reply_that_breaks_off_after_a_step_keeps_what_was_shown():
    text = json.dumps(ANSWER)
    cut = text.index('"caption": "second"') + 5  # in the middle of the second step
    adapter = adapter_streaming([pieces_of(text[:cut])])

    events = list(events_of(adapter))

    assert [k for k, _ in events] == ["step", "final"]
    assert [s.caption for s in events[-1][1].steps] == ["first"]


def test_a_reply_that_is_unusable_before_any_step_is_asked_for_again():
    adapter = adapter_streaming([pieces_of("I cannot do that."), pieces_of(json.dumps(ANSWER))])

    events = list(events_of(adapter))

    assert events[-1][1].attempts == 2
    assert len([e for e in events if e[0] == "step"]) == 3


def test_two_unusable_replies_are_an_error_that_says_what_the_model_said():
    adapter = adapter_streaming([pieces_of("nope"), pieces_of("still nope")])

    with pytest.raises(ModelOutputError, match="still nope"):
        list(events_of(adapter))


def test_a_failing_model_service_is_an_error():
    with pytest.raises(ModelOutputError, match="503"):
        list(events_of(adapter_streaming([], status=503)))


def test_a_service_that_does_not_stream_still_works():
    def handler(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(ANSWER)}, "finish_reason": "stop"}]})

    adapter = OpenAICompatibleAdapter(base_url="https://m.test/v1", api_key="k", model="m", transport=httpx.MockTransport(handler))

    events = list(events_of(adapter))

    assert [k for k, _ in events] == ["step", "step", "step", "final"]


def test_the_model_asking_for_a_search_is_announced_as_an_event():
    ask = json.dumps({"search": "who proved it"})
    searched = []

    def search(query):
        searched.append(query)
        return []

    adapter = adapter_streaming([pieces_of(ask), pieces_of(json.dumps({"explanation": "ok", "shapes": []}))])
    adapter._search = search

    kinds = [k for k, _ in events_of(adapter)]

    assert kinds[0] == "searching" and searched == ["who proved it"] and kinds[-1] == "final"


# --- explain_events and the HTTP stream -----------------------------------------


def request():
    return ExplainTurnRequest(
        session_id="s", question="q", image_base64=base64.b64encode(IMAGE).decode(), capture=CAPTURE
    )


def test_the_regions_event_comes_before_the_model_is_asked():
    asked = []

    class Spy:
        name = "spy"

        def decide(self, **call):
            asked.append(True)
            return RecordedModelAdapter().decide(**call)

    stream = explain_events(request(), adapter=Spy())
    kind, value = next(stream)

    assert kind == "regions" and not asked
    assert value["regions"][0].kind == "screen"


def test_a_streamed_turn_records_when_the_first_step_was_ready():
    adapter = adapter_streaming([pieces_of(json.dumps(ANSWER))])

    done = [v for k, v in explain_events(request(), adapter=adapter) if k == "done"][0]

    assert 0 < done.trace.timings_ms["first_step"] <= done.trace.timings_ms["total"]


def lines_of(response) -> list[dict]:
    return [json.loads(line) for line in response.text.splitlines() if line.strip()]


def test_the_http_stream_sends_regions_then_steps_then_done():
    client = TestClient(create_app(adapter_streaming([pieces_of(json.dumps(ANSWER))])))

    response = client.post("/explain-turn/stream", json=request().model_dump())

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    events = lines_of(response)
    assert [e["event"] for e in events] == ["regions", "step", "step", "step", "done"]
    assert events[0]["regions"][0]["kind"] == "screen" and events[0]["width"] == 1280
    assert [e["index"] for e in events[1:4]] == [0, 1, 2]
    assert [len(e["canvas"]["shapes"]) for e in events[1:4]] == [1, 2, 3]  # each step's canvas
    assert events[-1]["steps"] == 3 and events[-1]["trace"]["model"] == "m"


def test_the_http_stream_needs_the_token_when_one_is_set(monkeypatch):
    monkeypatch.setenv("BACKEND_ACCESS_TOKEN", "secret")
    client = TestClient(create_app(RecordedModelAdapter()))

    assert client.post("/explain-turn/stream", json=request().model_dump()).status_code == 401
    ok = client.post("/explain-turn/stream", json=request().model_dump(), headers={"Authorization": "Bearer secret"})
    assert ok.status_code == 200 and lines_of(ok)[-1]["event"] == "done"


def test_a_bad_picture_is_an_ordinary_400_before_streaming_starts():
    client = TestClient(create_app(RecordedModelAdapter()))
    body = request().model_dump()
    body["image_base64"] = base64.b64encode(b"not an image").decode()

    assert client.post("/explain-turn/stream", json=body).status_code == 400


def test_a_model_failure_during_the_stream_ends_it_with_an_error_event():
    client = TestClient(create_app(adapter_streaming([pieces_of("nope"), pieces_of("nope")])))

    events = lines_of(client.post("/explain-turn/stream", json=request().model_dump()))

    assert events[0]["event"] == "regions"
    assert events[-1]["event"] == "error" and events[-1]["status"] == 502


def test_the_playground_stream_has_the_same_guards(monkeypatch):
    monkeypatch.setenv("PLAYGROUND_RATE_PER_MINUTE", "1")
    client = TestClient(create_app(RecordedModelAdapter()))
    body = request().model_dump()

    first = client.post("/playground/explain/stream", json=body)
    second = client.post("/playground/explain/stream", json=body)
    too_big = client.post("/playground/explain/stream", json={**body, "image_base64": "A" * 4_300_000})

    assert first.status_code == 200 and lines_of(first)[-1]["event"] == "done"
    assert second.status_code == 429
    assert too_big.status_code in (413, 429)


def test_no_content_of_the_turn_is_logged_while_streaming(capsys):
    client = TestClient(create_app(adapter_streaming([pieces_of(json.dumps(ANSWER))])))
    body = request().model_copy(update={"question": "my private question"}).model_dump()

    client.post("/explain-turn/stream", json=body)

    out = capsys.readouterr().out
    assert "my private question" not in out and "first" not in out
    assert '"Status": 200' in out
