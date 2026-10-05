"""The evaluation cases and scoring (not the live models)."""

import numpy as np

from app.contract import Anchor, BBox, Canvas, ExplainTurnResponse, Operation, Region, Shape, Step, Trace
from evaluation.cases import build_cases
from evaluation.scoring import region_hits, score_answer, segment_hit


def response(shapes, regions, explanation="x"):
    return ExplainTurnResponse(
        explanation=explanation, operations=[], canvas=Canvas(shapes=shapes),
        steps=[Step(
            caption=explanation,
            operations=[Operation(op="add", shape_id=s.id, shape=s) for s in shapes],
            canvas=Canvas(shapes=shapes),
        )],
        regions=regions, chosen_region_ids=[],
        trace=Trace(regions_proposed=len(regions), attempts=1, model="m", timings_ms={}),
    )


def region(rid, x, y, w, h, kind="figure"):
    return Region(id=rid, bbox=BBox(x=x, y=y, w=w, h=h), kind=kind)


def shape_on(rid):
    return Shape(id="s", kind="box", anchor=Anchor(region_id=rid, x=0, y=0, w=1, h=1))


def test_there_are_at_least_thirty_cases_and_they_are_repeatable():
    first, second = build_cases(), build_cases()

    assert len(first) >= 30
    assert [c.name for c in first] == [c.name for c in second]
    assert all(np.array_equal(a.image, b.image) for a, b in zip(first, second))
    assert len({c.name for c in first}) == len(first)


def test_every_case_has_a_target_inside_the_image_or_a_keyword():
    for case in build_cases():
        assert case.target or case.segment or case.keywords, case.name
        if case.target:
            x, y, w, h = case.target
            assert x >= 0 and y >= 0 and x + w <= 1280 and y + h <= 720 and w > 0 and h > 0, case.name
        if case.segment:
            x1, y1, x2, y2 = case.segment
            assert all(0 <= v <= 1280 for v in (x1, x2)) and all(0 <= v <= 720 for v in (y1, y2)), case.name


def test_the_cases_cover_three_kinds():
    assert {c.kind for c in build_cases()} == {"triangle", "toolbar", "bullets"}


def test_a_region_on_the_target_counts_and_a_far_one_does_not():
    target = (100, 100, 200, 60)

    assert region_hits(region(1, 110, 105, 190, 50, "control"), target)
    assert not region_hits(region(2, 800, 500, 100, 40, "control"), target)
    assert not region_hits(region(0, 0, 0, 1280, 720, "screen"), target)


def test_a_small_part_inside_the_target_counts_but_a_huge_region_around_it_does_not():
    target = (400, 300, 400, 200)

    assert region_hits(region(1, 420, 320, 300, 80, "text"), target)  # a good part of it, inside
    assert not region_hits(region(3, 420, 320, 30, 20, "label"), target)  # a speck inside
    assert not region_hits(region(2, 0, 0, 1280, 720, "figure"), target)  # the whole slide


def test_pointing_is_scored_from_the_shapes_regions():
    case = next(c for c in build_cases() if c.kind == "toolbar")
    x, y, w, h = case.target
    right, wrong = region(1, x, y, w, h, "control"), region(2, 900, 600, 100, 50, "control")

    assert score_answer(case, response([shape_on(1)], [right, wrong])).pointed is True
    assert score_answer(case, response([shape_on(2)], [right, wrong])).pointed is False
    assert score_answer(case, response([], [right, wrong])).pointed is False


def test_a_keyword_is_checked_in_the_explanation_without_regard_to_case():
    case = next(c for c in build_cases() if c.keywords)

    assert score_answer(case, response([], [], explanation=f"The ANSWER is {case.keywords[0].upper()}")).keyword is True
    assert score_answer(case, response([], [], explanation="no idea")).keyword is False


def test_a_case_without_a_target_or_keywords_is_not_scored_on_them():
    case = next(c for c in build_cases() if not c.keywords)

    assert score_answer(case, response([], [])).keyword is None


def line_region(rid, x1, y1, x2, y2):
    return Region(
        id=rid, bbox=BBox(x=min(x1, x2), y=min(y1, y2), w=max(abs(x2 - x1), 6), h=max(abs(y2 - y1), 6)),
        kind="line", line=[x1, y1, x2, y2],
    )


def test_a_segment_is_matched_by_a_line_with_the_same_end_points_in_either_order():
    seg = (400, 500, 800, 300)

    assert segment_hit(line_region(1, 405, 495, 795, 305), seg)
    assert segment_hit(line_region(1, 795, 305, 405, 495), seg)
    assert not segment_hit(line_region(1, 400, 500, 800, 500), seg)  # another side from the same corner


def test_a_label_beside_the_segment_counts_but_one_beside_another_side_does_not():
    seg = (400, 500, 800, 300)

    assert segment_hit(region(1, 590, 380, 20, 24, "label"), seg)
    assert not segment_hit(region(2, 580, 560, 20, 24, "label"), seg)


def test_the_triangle_cases_are_scored_on_the_segment_not_a_box():
    case = next(c for c in build_cases() if c.kind == "triangle" and c.segment)
    x1, y1, x2, y2 = case.segment

    good = response([shape_on(1)], [line_region(1, x1, y1, x2, y2)])
    wrong = response([shape_on(1)], [line_region(1, 10, 10, 300, 10)])

    assert score_answer(case, good).pointed is True
    assert score_answer(case, wrong).pointed is False
