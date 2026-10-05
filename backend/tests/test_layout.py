"""Where equations go, how squares are fitted, and naming shapes to remove them later."""

import json

from app.answer import build_decision
from app.contract import Canvas, CaptureMeta
from app.geometry import square_corners
from app.layout import equation_size, fit_square_scale, place_equation
from app.regions import propose_regions
from fixtures import to_png, triangle_lecture

CAPTURE = CaptureMeta(width=1280, height=720)


def regions():
    return propose_regions(to_png(triangle_lecture()), CAPTURE)


def overlaps(a, b):
    return not (a[0] + a[2] <= b[0] or b[0] + b[2] <= a[0] or a[1] + a[3] <= b[1] or b[1] + b[3] <= a[1])


def test_an_equation_is_placed_in_free_space_close_to_what_it_is_about():
    rs = regions()
    figure = next(r for r in rs if r.kind == "figure")

    x, y = place_equation("5^2 + 12^2 = 13^2", figure, rs, [], (1280, 720))

    width, height = equation_size("5^2 + 12^2 = 13^2")
    box = (x, y, width, height)
    for region in rs:
        if region.kind != "screen":
            assert not overlaps(box, (region.bbox.x, region.bbox.y, region.bbox.w, region.bbox.h)), region.kind
    assert 0 <= x and x + width <= 1280 and 0 <= y and y + height <= 720
    # Close to the figure rather than in a far corner.
    assert abs(x + width / 2 - (figure.bbox.x + figure.bbox.w / 2)) < 700


def test_two_equations_do_not_cover_each_other():
    rs = regions()
    figure = next(r for r in rs if r.kind == "figure")
    first = place_equation("a^2 + b^2 = c^2", figure, rs, [], (1280, 720))
    width, height = equation_size("a^2 + b^2 = c^2")

    second = place_equation("x = 13", figure, rs, [(first[0], first[1], width, height)], (1280, 720))

    assert not overlaps((first[0], first[1], width, height), (second[0], second[1], *equation_size("x = 13")))


def test_equations_with_no_position_are_anchored_to_the_whole_screen():
    rs = regions()
    figure = next(r for r in rs if r.kind == "figure")
    reply = json.dumps({"explanation": "e", "shapes": [{"kind": "equation", "region_id": figure.id, "text": "x = 13"}]})

    shape = build_decision(reply, rs, 0).operations[0].shape

    assert shape.anchor.region_id == 0
    assert 0 <= shape.anchor.x <= 1 and 0 <= shape.anchor.y <= 1


def test_an_equation_with_a_position_is_left_where_the_model_put_it():
    rs = regions()
    figure = next(r for r in rs if r.kind == "figure")
    draft = {"kind": "equation", "region_id": figure.id, "x": 0.3, "y": 0.4, "text": "x = 13"}

    shape = build_decision(json.dumps({"explanation": "e", "shapes": [draft]}), rs, 0).operations[0].shape

    assert shape.anchor.region_id == figure.id and (shape.anchor.x, shape.anchor.y) == (0.3, 0.4)


def test_a_square_too_big_for_the_screen_is_shrunk_to_fit():
    line = [100, 600, 1100, 600]  # 1000 px long, 120 px above the bottom of a 1280x720 screen

    scale = fit_square_scale(line, "right", 1.0, (1280, 720))

    assert 0.1 < scale < 0.13  # the square goes down from y=600, so at most 120 px tall
    assert all(0 <= y <= 720 for _, y in square_corners(line, "right", scale))


def test_a_square_that_overhangs_an_edge_a_little_stays_true_to_size_but_one_far_off_is_shrunk():
    from app.contract import BBox, Region

    def scale_for(line):
        rs = [
            Region(id=0, bbox=BBox(x=0, y=0, w=1280, h=720), kind="screen"),
            Region(id=1, bbox=BBox(x=0, y=0, w=1, h=1), kind="line", line=line),
        ]
        decision = build_decision(
            json.dumps({"explanation": "e", "shapes": [{"kind": "square_on_line", "region_id": 1, "side": "left"}]}), rs, 0
        )
        return decision.operations[0].shape.scale

    assert scale_for([100, 330, 500, 330]) == 1.0  # a lone line: its square goes down and runs 10 px past the bottom edge
    assert scale_for([100, 700, 500, 700]) < 1.0  # almost all of it would be off the screen


def test_a_square_that_fits_keeps_its_scale():
    assert fit_square_scale([400, 500, 600, 500], "left", 0.8, (1280, 720)) == 0.8


def test_all_squares_of_an_answer_share_one_scale_so_their_areas_stay_in_proportion():
    rs = regions()
    lines = [r for r in rs if r.kind == "line"][:3]
    shapes = [{"kind": "square_on_line", "region_id": r.id, "scale": 1.0} for r in lines]

    decision = build_decision(json.dumps({"explanation": "e", "shapes": shapes}), rs, 0)

    scales = {op.shape.scale for op in decision.operations}
    assert len(scales) == 1
    assert next(iter(scales)) <= 1.0


def test_a_shape_can_be_removed_by_the_name_the_model_gave_it():
    rs = regions()
    steps = [
        {"caption": "one", "shapes": [{"kind": "equation", "region_id": 0, "text": "a = 1", "name": "eq"}]},
        {"caption": "two", "remove": ["eq"], "shapes": [{"kind": "equation", "region_id": 0, "text": "a = 2"}]},
    ]

    decision = build_decision(json.dumps({"explanation": "e", "steps": steps}), rs, 0, Canvas())

    assert [(op.op, op.shape_id) for op in decision.steps[1].operations][0] == ("remove", "t0-1")
    assert decision.steps[1].operations[1].shape.id == "t0-2"


def test_a_removed_equation_frees_its_place_for_the_next_one():
    rs = regions()
    steps = [
        {"caption": "one", "shapes": [{"kind": "equation", "region_id": 0, "text": "a = 1", "name": "eq"}]},
        {"caption": "two", "remove": ["eq"], "shapes": [{"kind": "equation", "region_id": 0, "text": "a = 2"}]},
    ]

    decision = build_decision(json.dumps({"explanation": "e", "steps": steps}), rs, 0)

    first = decision.steps[0].operations[0].shape.anchor
    second = decision.steps[1].operations[1].shape.anchor
    assert (first.x, first.y) == (second.x, second.y)


def test_squares_are_true_to_size_when_they_fit_on_the_screen():
    from app.contract import BBox, Region

    rs = [
        Region(id=0, bbox=BBox(x=0, y=0, w=1280, h=720), kind="screen"),
        Region(id=1, bbox=BBox(x=500, y=300, w=200, h=2), kind="line", line=[500, 300, 700, 300]),
    ]

    decision = build_decision(
        json.dumps({"explanation": "e", "shapes": [{"kind": "square_on_line", "region_id": 1}]}), rs, 0
    )

    assert decision.operations[0].shape.scale == 1.0  # a side of 200 px gets a square of 200 px


def test_an_equation_does_not_cover_the_squares():
    from app.layout import boxes_hit, equation_size, square_box

    rs = regions()
    lines = [r for r in rs if r.kind == "line"][:3]
    figure = next(r for r in rs if r.kind == "figure")
    shapes = [{"kind": "square_on_line", "region_id": r.id, "scale": 0.5} for r in lines]
    shapes.append({"kind": "equation", "region_id": figure.id, "text": "5^2 + 12^2 = 13^2"})

    decision = build_decision(json.dumps({"explanation": "e", "shapes": shapes}), rs, 0)

    by_id = {r.id: r for r in rs}
    equation = next(op.shape for op in decision.operations if op.shape.kind == "equation")
    width, height = equation_size(equation.text)
    box = (equation.anchor.x * 1280, equation.anchor.y * 720, width, height)
    for op in decision.operations:
        if op.shape.kind == "square_on_line":
            assert not boxes_hit(box, [square_box(by_id[op.shape.anchor.region_id].line, op.shape.side, op.shape.scale)])
