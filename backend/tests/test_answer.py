"""The model's JSON into a decision: steps, removals and the new shapes."""

import json

import pytest

from app.answer import ModelOutputError, build_decision
from app.contract import Anchor, Canvas, CaptureMeta, Shape
from app.geometry import outward_side, square_corners
from app.regions import propose_regions
from fixtures import to_png, triangle_lecture

CAPTURE = CaptureMeta(width=1280, height=720)


def regions():
    return propose_regions(to_png(triangle_lecture()), CAPTURE)


def line_regions(rs):
    return [r for r in rs if r.kind == "line"]


def reply(**fields):
    return json.dumps({"explanation": "ok", **fields})


def test_a_quick_reply_is_a_single_step():
    rs = regions()
    figure = next(r for r in rs if r.kind == "figure")

    decision = build_decision(reply(shapes=[{"kind": "box", "region_id": figure.id}]), rs, 0)

    assert len(decision.steps) == 1
    assert decision.steps[0].caption == "ok"
    # A box with no size covers its whole region.
    anchor = decision.operations[0].shape.anchor
    assert (anchor.x, anchor.y, anchor.w, anchor.h) == (0, 0, 1, 1)


def test_a_reply_with_steps_keeps_them_in_order_with_their_own_shapes():
    rs = regions()
    a, b = line_regions(rs)[:2]
    steps = [
        {"caption": "first", "shapes": [{"kind": "highlight", "region_id": a.id, "keep": True}]},
        {"caption": "second", "shapes": [{"kind": "highlight", "region_id": b.id, "keep": True}]},
    ]

    decision = build_decision(reply(steps=steps), rs, 3)

    assert [s.caption for s in decision.steps] == ["first", "second"]
    assert [op.shape_id for op in decision.operations] == ["t3-1", "t3-2"]
    assert [len(s.operations) for s in decision.steps] == [1, 1]


def test_a_reply_may_have_steps_and_no_overall_explanation():
    rs = regions()
    decision = build_decision(json.dumps({"steps": [{"caption": "only", "shapes": []}]}), rs, 0)

    assert decision.explanation == "only"


def test_ids_never_clash_with_shapes_already_on_the_canvas():
    rs = regions()
    figure = next(r for r in rs if r.kind == "figure")
    canvas = Canvas(shapes=[Shape(id="t0-1", kind="box", keep=True, anchor=Anchor(region_id=0, x=0, y=0, w=1, h=1))])

    decision = build_decision(reply(shapes=[{"kind": "box", "region_id": figure.id}]), rs, 0, canvas)

    assert decision.operations[0].shape_id == "t0-2"


def test_removing_an_existing_shape_is_an_operation_and_an_unknown_one_is_ignored():
    rs = regions()
    canvas = Canvas(shapes=[Shape(id="old", kind="box", anchor=Anchor(region_id=0, x=0, y=0, w=1, h=1))])

    decision = build_decision(reply(remove=["old", "never-existed"]), rs, 1, canvas)

    assert [(op.op, op.shape_id) for op in decision.operations] == [("remove", "old")]


def test_a_square_on_a_line_resolves_its_side_and_scale():
    rs = regions()
    line = line_regions(rs)[0]
    draft = {"kind": "square_on_line", "region_id": line.id, "scale": 9, "text": "5^2"}

    shape = build_decision(reply(shapes=[draft]), rs, 0).operations[0].shape

    assert shape.side in ("left", "right")
    assert shape.side == outward_side(line, rs)
    # Asked for 9: clamped to 1.5, then shrunk until the square fits on the screen.
    assert 0 < shape.scale <= 1.5
    corners = square_corners(line.line, shape.side, shape.scale)
    assert all(0 <= x <= 1280 and 0 <= y <= 720 for x, y in corners)
    assert shape.text == "5^2"


def test_inward_is_the_opposite_of_outward():
    rs = regions()
    line = line_regions(rs)[0]

    inward = build_decision(reply(shapes=[{"kind": "square_on_line", "region_id": line.id, "side": "inward"}]), rs, 0)

    assert inward.operations[0].shape.side != outward_side(line, rs)


def test_a_square_on_something_that_is_not_a_line_is_rejected():
    rs = regions()
    figure = next(r for r in rs if r.kind == "figure")

    with pytest.raises(ModelOutputError, match="needs a line region"):
        build_decision(reply(shapes=[{"kind": "square_on_line", "region_id": figure.id}]), rs, 0)


def test_polygons_need_three_points_and_equations_need_text():
    rs = regions()
    with pytest.raises(ModelOutputError, match="three points"):
        build_decision(reply(shapes=[{"kind": "polygon", "region_id": 0, "points": [{"x": 0, "y": 0}, {"x": 1, "y": 1}]}]), rs, 0)
    with pytest.raises(ModelOutputError, match="needs text"):
        build_decision(reply(shapes=[{"kind": "equation", "region_id": 0, "x": 0.1, "y": 0.1}]), rs, 0)

    ok = build_decision(
        reply(shapes=[
            {"kind": "polygon", "region_id": 0, "points": [{"x": 0, "y": 0}, {"x": 1, "y": 0}, {"x": 0.5, "y": 1}]},
            {"kind": "equation", "region_id": 0, "x": 0.1, "y": 0.9, "text": "a^2 + b^2 = c^2"},
        ]),
        rs, 0,
    )
    assert [op.shape.kind for op in ok.operations] == ["polygon", "equation"]
    assert len(ok.operations[0].shape.points) == 3


def test_the_outward_side_of_a_triangle_points_away_from_the_triangle():
    """The square on each side of a right triangle must not cover the triangle."""
    rs = regions()
    lines = line_regions(rs)
    centre_x = sum(r.line[0] + r.line[2] for r in lines) / (2 * len(lines))
    centre_y = sum(r.line[1] + r.line[3] for r in lines) / (2 * len(lines))

    for region in lines[:3]:
        corners = square_corners(region.line, outward_side(region, rs))
        far = corners[2:]
        mid_x, mid_y = (region.line[0] + region.line[2]) / 2, (region.line[1] + region.line[3]) / 2
        square_cx = sum(c[0] for c in corners) / 4
        square_cy = sum(c[1] for c in corners) / 4
        # The square's centre is farther from the triangle's centre than the side's midpoint.
        assert (square_cx - centre_x) ** 2 + (square_cy - centre_y) ** 2 > (mid_x - centre_x) ** 2 + (mid_y - centre_y) ** 2
        assert len(far) == 2


def test_the_corners_of_a_square_on_a_horizontal_line():
    # Looking along the line from (0,0) to (10,0), "left" is up on a screen (y downwards).
    left = square_corners([0, 0, 10, 0], "left")
    right = square_corners([0, 0, 10, 0], "right")

    assert left == [(0, 0), (10, 0), (10, -10), (0, -10)]
    assert right == [(0, 0), (10, 0), (10, 10), (0, 10)]
    assert square_corners([0, 0, 10, 0], "left", 0.5)[2] == (5, -5)
