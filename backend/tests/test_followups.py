"""Explain Turn across several turns: steps, follow-ups and what is dropped."""

import base64
import json

import cv2

from app.contract import CaptureMeta, ExplainTurnRequest
from app.explain import explain_turn
from fixtures import FONT, INK, lecture_frame, to_png
from test_openai_adapter import adapter_with_replies

CAPTURE = CaptureMeta(width=1280, height=720)


def request_for(image, canvas=None, previous=None, turn=0, question="q"):
    return ExplainTurnRequest(
        session_id="s",
        question=question,
        image_base64=base64.b64encode(to_png(image)).decode(),
        capture=CAPTURE,
        canvas=canvas or {"shapes": []},
        previous_regions=previous or [],
        turn=turn,
    )


def box_reply(region_id, remove=()):
    return json.dumps({
        "explanation": "e",
        "shapes": [{"kind": "box", "region_id": region_id, "keep": True}],
        "remove": list(remove),
    })


def test_steps_come_back_with_the_canvas_for_each_step():
    steps = [
        {"caption": "one", "shapes": [{"kind": "box", "region_id": 0, "keep": True}]},
        {"caption": "two", "shapes": [{"kind": "ellipse", "region_id": 0, "keep": True}]},
    ]
    adapter = adapter_with_replies([(json.dumps({"explanation": "sum", "steps": steps}), "stop")])

    response = explain_turn(request_for(lecture_frame()[0]), adapter=adapter)

    assert [s.caption for s in response.steps] == ["one", "two"]
    assert [len(s.canvas.shapes) for s in response.steps] == [1, 2]
    assert response.canvas == response.steps[-1].canvas
    assert response.explanation == "sum"


def test_a_reply_without_steps_still_gives_one_step():
    adapter = adapter_with_replies([(box_reply(0), "stop")])

    response = explain_turn(request_for(lecture_frame()[0]), adapter=adapter)

    assert len(response.steps) == 1 and response.steps[0].caption == "e"


def test_a_follow_up_keeps_the_drawing_and_adds_to_it():
    image = lecture_frame()[0]
    first = explain_turn(request_for(image), adapter=adapter_with_replies([(box_reply(0), "stop")]))

    second = explain_turn(
        request_for(image, first.canvas.model_dump(), first.regions, turn=1),
        adapter=adapter_with_replies([(box_reply(0), "stop")]),
    )

    assert [s.id for s in second.canvas.shapes] == ["t0-1", "t1-1"]
    assert second.trace.dropped_shape_ids == []


def test_a_follow_up_can_remove_an_old_drawing():
    image = lecture_frame()[0]
    first = explain_turn(request_for(image), adapter=adapter_with_replies([(box_reply(0), "stop")]))

    second = explain_turn(
        request_for(image, first.canvas.model_dump(), first.regions, turn=1),
        adapter=adapter_with_replies([(box_reply(0, remove=["t0-1"]), "stop")]),
    )

    assert [s.id for s in second.canvas.shapes] == ["t1-1"]


def test_the_model_is_told_about_drawings_that_survived_not_ones_that_were_dropped():
    from app.regions import propose_regions

    image = lecture_frame()[0]
    regions = propose_regions(to_png(image), CAPTURE)
    figure = next(r for r in regions if r.kind == "figure")
    first = explain_turn(request_for(image), adapter=adapter_with_replies([(box_reply(figure.id), "stop")]))

    changed = image.copy()
    changed[190:520, 770:1190] = 255
    cv2.rectangle(changed, (800, 250), (1100, 480), (30, 30, 30), -1)
    seen = []
    second = explain_turn(
        request_for(changed, first.canvas.model_dump(), first.regions, turn=1),
        adapter=adapter_with_replies([(json.dumps({"explanation": "x"}), "stop")], seen),
    )

    assert second.trace.dropped_shape_ids == ["t0-1"]
    text = next(p["text"] for p in seen[0]["messages"][1]["content"] if p["type"] == "text")
    assert "t0-1" not in text
    assert second.canvas.shapes == []
