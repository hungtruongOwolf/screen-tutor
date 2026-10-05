"""The proof diagram as the model asks for it: placement, steps and the moving pieces."""

import json

from app.answer import build_decision
from app.canvas import apply_operations
from app.contract import Canvas, CaptureMeta
from app.layout import equation_size
from app.regions import propose_regions
from fixtures import to_png, triangle_lecture

CAPTURE = CaptureMeta(width=1280, height=720)


def regions():
    return propose_regions(to_png(triangle_lecture()), CAPTURE)


def proof(stage, **extra):
    return {"kind": "pythagoras_proof", "region_id": 0, "a": 5, "b": 12, "stage": stage, **extra}


def build(steps, rs=None):
    rs = rs or regions()
    return build_decision(json.dumps({"explanation": "e", "steps": steps}), rs, 0, Canvas()), rs


def test_the_first_stage_draws_the_square_four_triangles_and_the_tilted_square():
    decision, _ = build([{"caption": "one", "shapes": [proof(1)]}])

    ops = decision.steps[0].operations
    assert all(op.op == "add" for op in ops)
    texts = [op.shape.text for op in ops if op.shape.text]
    assert "c^2" in texts and "5" in texts and "12" in texts
    assert sum(1 for op in ops if op.shape.kind == "polygon") == 1 + 4 + 1  # frame, triangles, hole


def test_the_second_stage_slides_the_same_four_triangles_and_swaps_the_hole_for_two_squares():
    decision, _ = build([
        {"caption": "one", "shapes": [proof(1)]},
        {"caption": "two", "shapes": [proof(2)]},
    ])

    first, second = decision.steps
    hole = next(op.shape_id for op in first.operations if op.shape.text == "c^2")
    triangles = [op.shape_id for op in first.operations if op.shape.kind == "polygon" and op.shape.style.color == "#ffd23f"]
    assert [op.op for op in second.operations].count("update") == 4
    assert {op.shape_id for op in second.operations if op.op == "update"} == set(triangles)
    assert all(op.shape.motion is not None for op in second.operations if op.op == "update")
    assert ("remove", hole) in [(op.op, op.shape_id) for op in second.operations]
    assert sorted(op.shape.text for op in second.operations if op.op == "add") == ["12^2 = 144", "5^2 = 25"]


def test_the_steps_apply_to_a_canvas_in_order():
    decision, _ = build([
        {"caption": "one", "shapes": [proof(1)]},
        {"caption": "two", "shapes": [proof(2)]},
    ])

    canvas = Canvas()
    for step in decision.steps:
        canvas = apply_operations(canvas, step.operations)

    assert len(canvas.shapes) == 1 + 2 + 4 + 2  # frame, two labels, triangles, two squares (hole gone)
    assert all(s.motion is not None for s in canvas.shapes if s.style and s.style.color == "#ffd23f" and s.kind == "polygon")


def test_the_second_stage_alone_draws_the_finished_picture_without_motion():
    decision, _ = build([{"caption": "two", "shapes": [proof(2)]}])

    ops = decision.steps[0].operations
    assert all(op.op == "add" for op in ops)
    assert all(op.shape.motion is None for op in ops)


def test_the_diagram_is_in_free_space_and_an_equation_keeps_clear_of_it():
    decision, rs = build([
        {"caption": "one", "shapes": [proof(1), {"kind": "equation", "region_id": 0, "text": "5^2 + 12^2 = 13^2"}]},
    ])

    def box(points):
        xs, ys = [p.x * 1280 for p in points], [p.y * 720 for p in points]
        return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)

    def overlap(a, b):
        return not (a[0] + a[2] <= b[0] or b[0] + b[2] <= a[0] or a[1] + a[3] <= b[1] or b[1] + b[3] <= a[1])

    ops = decision.steps[0].operations
    frame = box(next(op.shape.points for op in ops if op.shape.kind == "polygon"))
    for region in rs:
        if region.kind != "screen":
            assert not overlap(frame, (region.bbox.x, region.bbox.y, region.bbox.w, region.bbox.h))
    equation = next(op.shape for op in ops if op.shape.kind == "equation")
    width, height = equation_size(equation.text)
    assert not overlap(frame, (equation.anchor.x * 1280, equation.anchor.y * 720, width, height))


def test_a_proof_needs_the_legs():
    import pytest

    from app.answer import ModelOutputError

    with pytest.raises(ModelOutputError):
        build([{"caption": "x", "shapes": [{"kind": "pythagoras_proof", "region_id": 0, "stage": 1}]}])


def test_the_whole_proof_can_be_taken_off_by_the_name_proof():
    decision, _ = build([
        {"caption": "one", "shapes": [proof(1)]},
        {"caption": "two", "remove": ["proof"], "shapes": []},
    ])

    assert {op.op for op in decision.steps[1].operations} == {"remove"}
    canvas = Canvas()
    for step in decision.steps:
        canvas = apply_operations(canvas, step.operations)
    assert canvas.shapes == []


def test_the_hole_carries_the_learners_own_letter_for_the_hypotenuse():
    decision, _ = build([{"caption": "one", "shapes": [proof(1, c_name="x")]}])

    texts = [op.shape.text for op in decision.steps[0].operations if op.shape.text]
    assert "x^2" in texts and "c^2" not in texts
