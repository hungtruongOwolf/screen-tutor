"""The real-model adapter, tested without any network call.

The model service is replaced by httpx.MockTransport returning recorded replies.
"""

import base64
import json

import cv2
import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.contract import Canvas, CaptureMeta, ExplainTurnRequest
from app.explain import explain_turn
from app.marking import mark_regions
from app.openai_adapter import (
    ModelOutputError,
    OpenAICompatibleAdapter,
    build_decision,
    extract_json,
)
from app.regions import decode_image, propose_regions
from app.server import create_app
from fixtures import lecture_frame, to_png

CAPTURE = CaptureMeta(width=1280, height=720)


def chat_reply(content: str) -> dict:
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}


def adapter_returning(content: str, *, status: int = 200, seen: list | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        if status != 200:
            return httpx.Response(status, text="boom")
        return httpx.Response(200, json=chat_reply(content))

    return OpenAICompatibleAdapter(
        base_url="https://models.test/v1",
        api_key="test-key",
        model="test/vision-model",
        transport=httpx.MockTransport(handler),
    )


def make_request(question: str = "What is the diagram?") -> ExplainTurnRequest:
    image, _ = lecture_frame()
    return ExplainTurnRequest(
        session_id="s",
        question=question,
        image_base64=base64.b64encode(to_png(image)).decode(),
        capture=CAPTURE,
    )


def figure_region_id() -> int:
    regions = propose_regions(to_png(lecture_frame()[0]), CAPTURE)
    return next(r.id for r in regions if r.kind == "figure")


GOOD_REPLY = {
    "explanation": "The diagram is a binary tree.",
    "region_ids": [3],
    "shapes": [{"kind": "box", "region_id": 3, "x": 0.1, "y": 0.1, "w": 0.5, "h": 0.5, "text": "root"}],
}


# --- parsing the model's reply -------------------------------------------------


def test_json_is_found_in_plain_fenced_and_reasoning_replies():
    expected = {"a": 1}
    assert extract_json('{"a": 1}') == expected
    assert extract_json('Sure!\n```json\n{"a": 1}\n```') == expected
    assert extract_json('<think>hmm {"x": 2}</think>{"a": 1}') == expected


@pytest.mark.parametrize("reply", ["no json here", "{not valid json", ""])
def test_a_reply_without_usable_json_is_an_error(reply):
    with pytest.raises(ModelOutputError):
        extract_json(reply)


def test_a_reply_becomes_operations_anchored_to_regions():
    regions = propose_regions(to_png(lecture_frame()[0]), CAPTURE)
    rid = figure_region_id()
    reply = json.dumps({**GOOD_REPLY, "region_ids": [rid], "shapes": [{**GOOD_REPLY["shapes"][0], "region_id": rid}]})

    decision = build_decision(reply, regions, turn=2)

    assert decision.explanation == "The diagram is a binary tree."
    assert decision.chosen_region_ids == [rid]
    [operation] = decision.operations
    assert operation.op == "add" and operation.shape_id == "t2-1"
    assert operation.shape.anchor.region_id == rid
    assert operation.shape.text == "root"


def test_a_shape_on_a_region_that_does_not_exist_is_rejected():
    regions = propose_regions(to_png(lecture_frame()[0]), CAPTURE)
    reply = json.dumps({**GOOD_REPLY, "shapes": [{**GOOD_REPLY["shapes"][0], "region_id": 999}]})

    with pytest.raises(ModelOutputError, match="do not exist"):
        build_decision(reply, regions, turn=0)


def test_a_reply_in_the_wrong_format_is_rejected():
    regions = propose_regions(to_png(lecture_frame()[0]), CAPTURE)

    for bad in (
        {"shapes": []},  # no explanation
        {"explanation": "x", "shapes": [{"kind": "box", "region_id": 0, "x": 2, "y": 0, "w": 1, "h": 1}]},
        {"explanation": "x", "shapes": [{"kind": "connector", "region_id": 0, "x": 0, "y": 0, "w": 1, "h": 1}]},
    ):
        with pytest.raises(ModelOutputError):
            build_decision(json.dumps(bad), regions, turn=0)


def test_an_arrow_keeps_its_own_tail_and_head():
    regions = propose_regions(to_png(lecture_frame()[0]), CAPTURE)
    arrow = {"kind": "arrow", "region_id": 0, "x": 0.1, "y": 0.9, "w": 0, "h": 0, "x2": 0.8, "y2": 0.2}

    decision = build_decision(json.dumps({"explanation": "x", "shapes": [arrow]}), regions, turn=0)

    shape = decision.operations[0].shape
    assert (shape.anchor.x, shape.anchor.y) == (0.1, 0.9)
    assert (shape.end.x, shape.end.y) == (0.8, 0.2)


def test_an_arrow_without_a_head_falls_back_to_the_rectangle_corner():
    regions = propose_regions(to_png(lecture_frame()[0]), CAPTURE)
    arrow = {"kind": "arrow", "region_id": 0, "x": 0.1, "y": 0.1, "w": 0.4, "h": 0.3}

    decision = build_decision(json.dumps({"explanation": "x", "shapes": [arrow]}), regions, turn=0)

    end = decision.operations[0].shape.end
    assert (round(end.x, 2), round(end.y, 2)) == (0.5, 0.4)


# --- the marked image ----------------------------------------------------------


def test_marking_draws_numbers_and_keeps_the_image_small():
    image, _ = lecture_frame()
    big = cv2.resize(image, (3840, 2160))
    capture = CaptureMeta(width=3840, height=2160)
    png = to_png(big)
    regions = propose_regions(png, capture)

    marked = decode_image(mark_regions(png, regions))

    assert marked.shape[1] <= 1600
    assert abs(marked.shape[1] / marked.shape[0] - 3840 / 2160) < 0.01
    assert not np.array_equal(cv2.resize(big, (marked.shape[1], marked.shape[0])), marked)


# --- the adapter over HTTP -----------------------------------------------------


def test_the_request_carries_the_question_regions_and_a_marked_image():
    seen: list[httpx.Request] = []
    rid = figure_region_id()
    reply = json.dumps({**GOOD_REPLY, "region_ids": [rid], "shapes": [{**GOOD_REPLY["shapes"][0], "region_id": rid}]})

    explain_turn(make_request("What is the diagram?"), adapter=adapter_returning(reply, seen=seen))

    [request] = seen
    assert request.url.path == "/v1/chat/completions"
    assert request.headers["authorization"] == "Bearer test-key"
    body = json.loads(request.content)
    assert body["model"] == "test/vision-model"
    content = body["messages"][1]["content"]
    text = next(part["text"] for part in content if part["type"] == "text")
    image = next(part["image_url"]["url"] for part in content if part["type"] == "image_url")
    assert "What is the diagram?" in text
    assert f"R{rid}: figure" in text
    assert "R0: whole screen" in text
    assert image.startswith("data:image/jpeg;base64,")


def test_a_full_turn_with_a_recorded_model_reply():
    rid = figure_region_id()
    reply = json.dumps({**GOOD_REPLY, "region_ids": [rid], "shapes": [{**GOOD_REPLY["shapes"][0], "region_id": rid}]})

    response = explain_turn(make_request(), adapter=adapter_returning(reply))

    assert response.explanation == "The diagram is a binary tree."
    assert response.chosen_region_ids == [rid]
    assert [s.anchor.region_id for s in response.canvas.shapes] == [rid]
    assert response.trace.model == "test/vision-model"


def test_the_current_canvas_is_described_to_the_model():
    seen: list[httpx.Request] = []
    request = make_request()
    first = explain_turn(request, adapter=adapter_returning(json.dumps({"explanation": "one", "shapes": [{"kind": "box", "region_id": 0, "x": 0, "y": 0, "w": 0.5, "h": 0.5}]})))
    second_request = request.model_copy(update={"canvas": first.canvas, "turn": 1})

    explain_turn(second_request, adapter=adapter_returning(json.dumps({"explanation": "two"}), seen=seen))

    body = json.loads(seen[0].content)
    text = next(p["text"] for p in body["messages"][1]["content"] if p["type"] == "text")
    assert "Already drawn on screen: t0-1: box on R0" in text


@pytest.mark.parametrize("status", [401, 429, 500])
def test_a_failing_model_service_is_reported_as_an_error(status):
    with pytest.raises(ModelOutputError, match=str(status)):
        explain_turn(make_request(), adapter=adapter_returning("", status=status))


def test_a_network_failure_is_reported_as_an_error():
    def handler(request):
        raise httpx.ConnectError("no route")

    adapter = OpenAICompatibleAdapter(
        base_url="https://models.test/v1", api_key="k", model="m", transport=httpx.MockTransport(handler)
    )

    with pytest.raises(ModelOutputError, match="cannot reach"):
        explain_turn(make_request(), adapter=adapter)


def test_the_http_endpoint_answers_502_when_the_model_misbehaves():
    client = TestClient(create_app(adapter_returning("this is not json")))

    response = client.post("/explain-turn", json=make_request().model_dump())

    assert response.status_code == 502


def triangle_request() -> ExplainTurnRequest:
    from fixtures import triangle_lecture

    return ExplainTurnRequest(
        session_id="s",
        question="Which side is x?",
        image_base64=base64.b64encode(to_png(triangle_lecture())).decode(),
        capture=CAPTURE,
    )


def test_the_model_is_told_where_each_line_runs():
    seen: list[httpx.Request] = []

    explain_turn(triangle_request(), adapter=adapter_returning(json.dumps({"explanation": "x"}), seen=seen))

    body = json.loads(seen[0].content)
    text = next(p["text"] for p in body["messages"][1]["content"] if p["type"] == "text")
    assert "line, " in text and " from (" in text
    assert "label," in text


def test_an_arrow_can_target_a_region():
    regions = propose_regions(to_png(lecture_frame()[0]), CAPTURE)
    figure = next(r for r in regions if r.kind == "figure")
    arrow = {"kind": "arrow", "region_id": figure.id, "x": 0.9, "y": 0.1, "w": 0, "h": 0, "target_region_id": figure.id}

    decision = build_decision(json.dumps({"explanation": "x", "shapes": [arrow]}), regions, turn=0)

    assert decision.operations[0].shape.target_region_id == figure.id


def test_an_arrow_aimed_at_a_region_that_does_not_exist_is_rejected():
    regions = propose_regions(to_png(lecture_frame()[0]), CAPTURE)
    arrow = {"kind": "arrow", "region_id": 0, "x": 0.5, "y": 0.5, "w": 0, "h": 0, "target_region_id": 999}

    with pytest.raises(ModelOutputError, match="do not exist"):
        build_decision(json.dumps({"explanation": "x", "shapes": [arrow]}), regions, turn=0)


# --- empty or unusable replies ---------------------------------------------------


def adapter_with_replies(replies: list[tuple[str, str]], seen: list | None = None, extra_body=None):
    """The model service answers with (content, finish_reason) pairs in turn."""
    queue = list(replies)

    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(json.loads(request.content))
        content, finish = queue.pop(0)
        return httpx.Response(
            200, json={"choices": [{"message": {"content": content}, "finish_reason": finish}]}
        )

    return OpenAICompatibleAdapter(
        base_url="https://models.test/v1",
        api_key="k",
        model="m",
        extra_body=extra_body,
        transport=httpx.MockTransport(handler),
    )


def test_an_empty_reply_is_retried_once_and_the_second_reply_is_used():
    seen: list = []
    good = json.dumps({"explanation": "second try"})
    adapter = adapter_with_replies([("", "length"), (good, "stop")], seen)

    response = explain_turn(make_request(), adapter=adapter)

    assert response.explanation == "second try"
    assert response.trace.attempts == 2
    assert len(seen) == 2
    assert "ONLY the JSON" in seen[1]["messages"][-1]["content"]


def test_a_bad_reply_is_included_when_asking_again():
    seen: list = []
    adapter = adapter_with_replies(
        [("Sure, let me think.", "stop"), (json.dumps({"explanation": "ok"}), "stop")], seen
    )

    explain_turn(make_request(), adapter=adapter)

    roles = [m["role"] for m in seen[1]["messages"]]
    assert roles == ["system", "user", "assistant", "user"]


def test_two_unusable_replies_give_an_error_that_says_what_the_model_said():
    adapter = adapter_with_replies([("", "length"), ("still no json", "stop")])

    with pytest.raises(ModelOutputError, match="still no json"):
        explain_turn(make_request(), adapter=adapter)


def test_a_reply_that_ran_out_of_room_while_thinking_says_so():
    adapter = adapter_with_replies([("", "length"), ("", "length")])

    with pytest.raises(ModelOutputError, match="ran out of room"):
        explain_turn(make_request(), adapter=adapter)


def test_a_good_first_reply_uses_one_attempt():
    adapter = adapter_with_replies([(json.dumps({"explanation": "fine"}), "stop")])

    assert explain_turn(make_request(), adapter=adapter).trace.attempts == 1


def test_extra_body_fields_are_sent_with_every_request():
    seen: list = []
    adapter = adapter_with_replies(
        [(json.dumps({"explanation": "x"}), "stop")], seen, extra_body={"reasoning_effort": "none"}
    )

    explain_turn(make_request(), adapter=adapter)

    assert seen[0]["reasoning_effort"] == "none"


def test_known_models_get_their_default_extra_body():
    from app.openai_adapter import MODEL_EXTRA_BODY

    assert MODEL_EXTRA_BODY["deepseek-ai/DeepSeek-V4.1-Flash"] == {"reasoning_effort": "none"}


# --- the two pictures sent to the model ----------------------------------------


def test_the_model_gets_a_clean_picture_and_a_marked_one():
    seen: list[httpx.Request] = []

    explain_turn(make_request(), adapter=adapter_returning(json.dumps({"explanation": "x"}), seen=seen))

    content = json.loads(seen[0].content)["messages"][1]["content"]
    images = [part["image_url"]["url"] for part in content if part["type"] == "image_url"]
    assert len(images) == 2
    clean, marked = (base64.b64decode(url.split(",", 1)[1]) for url in images)
    assert clean != marked


def test_the_clean_picture_has_no_marks_on_it():
    from app.marking import clean_image

    image, _ = lecture_frame()
    png = to_png(image)

    clean = decode_image(clean_image(png))

    # Same picture apart from JPEG noise: no coloured badge or outline pixels.
    assert np.abs(clean.astype(int) - image.astype(int)).mean() < 3


def test_badges_do_not_cover_each_other():
    image, _ = lecture_frame()
    big = to_png(image)
    regions = propose_regions(big, CAPTURE)

    marked = decode_image(mark_regions(big, regions))

    # Badge pixels are filled with the region colour: every region's colour must
    # still show a solid badge, i.e. none was completely hidden by a later one.
    from app.marking import COLORS

    for kind in {r.kind for r in regions if r.kind in COLORS}:
        color = np.array(COLORS[kind], dtype=int)
        solid = (np.abs(marked.astype(int) - color).sum(axis=2) < 40).sum()
        assert solid > 150, kind


# --- the conversation ------------------------------------------------------------


def test_the_conversation_so_far_goes_to_the_model_and_follow_up_ideas_come_back():
    from app.contract import ChatTurn

    seen: list = []
    reply = {**GOOD_REPLY, "steps": [{"caption": "Click Add service.", "shapes": []}], "follow_ups": ["Done, what next?"]}
    adapter = adapter_returning(json.dumps(reply), seen=seen)
    request = make_request("done")
    request.history = [
        ChatTurn(role="user", text="How do I price a server?"),
        ChatTurn(role="assistant", text="Step 1: click Add service."),
    ]

    response = explain_turn(request, adapter=adapter)

    prompt = json.loads(seen[0].content)["messages"][1]["content"][0]["text"]
    assert prompt.index("Conversation so far:") < prompt.index("Question: done")
    assert "Learner: How do I price a server?" in prompt and "You: Step 1: click Add service." in prompt
    assert response.follow_ups == ["Done, what next?"]


def test_a_long_conversation_is_trimmed_to_the_latest_messages():
    from app.contract import ChatTurn
    from app.prompting import describe_history

    history = [ChatTurn(role="user", text=f"message {i} " + "x" * 900) for i in range(30)]

    text = describe_history(history)

    assert "message 29" in text and "message 19" not in text
    assert all(len(line) < 700 for line in text.splitlines())
    assert describe_history([]) == ""


# --- following a task ---------------------------------------------------------------


def test_the_goal_and_progress_go_through_and_a_screen_change_is_told_to_the_model():
    seen: list = []
    reply = {
        "explanation": "e",
        "steps": [{"caption": "Now click Create user.", "shapes": []}],
        "goal": "Create an access key",
        "progress": "continue",
    }
    adapter = adapter_returning(json.dumps(reply), seen=seen)
    request = make_request("(the screen changed)")
    request.goal = "Create an access key"
    request.trigger = "screen_changed"

    response = explain_turn(request, adapter=adapter)

    prompt = json.loads(seen[0].content)["messages"][1]["content"][0]["text"]
    assert "The learner's goal: Create an access key" in prompt
    assert "The screen changed after your last answer" in prompt
    assert "Question: (the screen changed)" not in prompt
    assert (response.goal, response.progress) == ("Create an access key", "continue")


def test_a_waiting_answer_with_no_steps_is_allowed_and_says_nothing():
    adapter = adapter_returning(json.dumps({"steps": [], "progress": "waiting", "goal": "Create a key"}))
    request = make_request("(the screen changed)")
    request.trigger = "screen_changed"

    response = explain_turn(request, adapter=adapter)

    assert response.steps == [] and response.progress == "waiting"


def test_an_answer_with_nothing_in_it_that_is_not_waiting_is_still_refused():
    adapter = adapter_returning(json.dumps({"steps": [], "progress": "continue"}))

    with pytest.raises(ModelOutputError):
        explain_turn(make_request(), adapter=adapter)
