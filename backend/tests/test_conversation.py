"""Pointing marks live for one step; the conversation reaches the model; follow-up ideas come back."""

import json

from app.answer import build_decision
from app.canvas import apply_operations
from app.contract import Canvas
from app.regions import propose_regions
from app.contract import CaptureMeta
from fixtures import to_png, triangle_lecture

CAPTURE = CaptureMeta(width=1280, height=720)


def regions():
    return propose_regions(to_png(triangle_lecture()), CAPTURE)


def run(steps, rs=None, canvas=None):
    rs = rs or regions()
    decision = build_decision(json.dumps({"explanation": "e", "steps": steps}), rs, 0, canvas)
    shapes = canvas or Canvas()
    per_step = []
    for step in decision.steps:
        shapes = apply_operations(shapes, step.operations)
        per_step.append([s.kind for s in shapes.shapes])
    return decision, per_step


def test_a_pointing_mark_goes_when_the_next_step_draws_something():
    _, kinds = run([
        {"caption": "look here", "shapes": [{"kind": "box", "region_id": 0}, {"kind": "arrow", "region_id": 2, "target_region_id": 2}]},
        {"caption": "now here", "shapes": [{"kind": "ellipse", "region_id": 0}]},
    ])

    assert kinds == [["box", "arrow"], ["ellipse"]]


def test_a_kept_mark_stays():
    _, kinds = run([
        {"caption": "one", "shapes": [{"kind": "box", "region_id": 0, "keep": True}]},
        {"caption": "two", "shapes": [{"kind": "ellipse", "region_id": 0}]},
    ])

    assert kinds == [["box"], ["box", "ellipse"]]


def test_squares_and_equations_build_up_but_the_highlights_before_them_go():
    rs = regions()
    lines = [r for r in rs if r.kind == "line"][:2]
    _, kinds = run([
        {"caption": "sides", "shapes": [{"kind": "highlight", "region_id": r.id} for r in lines]},
        {"caption": "squares", "shapes": [{"kind": "square_on_line", "region_id": r.id} for r in lines]},
        {"caption": "formula", "shapes": [{"kind": "equation", "region_id": 0, "text": "a = b"}]},
    ], rs)

    assert kinds == [["highlight", "highlight"], ["square_on_line", "square_on_line"], ["square_on_line", "square_on_line", "equation"]]


def test_a_step_that_draws_nothing_leaves_the_marks_alone():
    _, kinds = run([
        {"caption": "one", "shapes": [{"kind": "box", "region_id": 0}]},
        {"caption": "just words", "shapes": []},
    ])

    assert kinds == [["box"], ["box"]]


def test_marks_left_by_an_earlier_turn_go_when_this_turn_draws():
    from app.contract import Anchor, Shape

    old = Canvas(shapes=[Shape(id="t0-1", kind="box", anchor=Anchor(region_id=0, x=0, y=0, w=1, h=1))])

    decision, kinds = run([{"caption": "new", "shapes": [{"kind": "ellipse", "region_id": 0}]}], canvas=old)

    assert [op.op for op in decision.steps[0].operations] == ["remove", "add"]
    assert kinds == [["ellipse"]]


def test_follow_up_ideas_come_back_trimmed_and_capped_at_three():
    rs = regions()
    reply = {"explanation": "e", "steps": [{"caption": "c", "shapes": []}], "follow_ups": ["  Why? ", "", "And then?", "More", "Too many"]}

    from app.answer import DecisionBuilder, parse_answer

    decision, _ = DecisionBuilder(rs, 0).finish(parse_answer(json.dumps(reply)))

    assert decision.follow_ups == ["Why?", "And then?", "More"]


def test_an_arrow_at_something_already_boxed_is_left_out():
    rs = regions()
    figure = next(r for r in rs if r.kind == "figure")

    decision, kinds = run([
        {"caption": "here", "shapes": [
            {"kind": "box", "region_id": figure.id, "text": "Click here"},
            {"kind": "arrow", "region_id": figure.id, "target_region_id": figure.id},
        ]},
    ], rs)

    assert kinds == [["box"]]


def test_an_arrow_at_something_not_marked_stays():
    rs = regions()
    figure = next(r for r in rs if r.kind == "figure")

    _, kinds = run([{"caption": "here", "shapes": [{"kind": "arrow", "region_id": figure.id, "target_region_id": figure.id}]}], rs)

    assert kinds == [["arrow"]]


def test_the_prompt_asks_for_english_everywhere_and_never_for_the_learners_language():
    from app.prompting import SYSTEM_PROMPT

    assert "EVERYTHING you produce in English" in SYSTEM_PROMPT
    for phrase in ("same language as", "learner's language", "their language"):
        assert phrase not in SYSTEM_PROMPT

