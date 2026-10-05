"""Drawings from earlier turns follow the screen: they move to the new regions or are dropped."""

import cv2
import numpy as np

from app.contract import Anchor, Canvas, CaptureMeta, Shape
from app.reanchor import hamming, reanchor_canvas
from app.regions import propose_regions
from fixtures import FONT, INK, lecture_frame, to_png, triangle_lecture

CAPTURE = CaptureMeta(width=1280, height=720)


def shape_on(region_id: int, shape_id: str = "s", **extra) -> Shape:
    return Shape(
        id=shape_id,
        kind="box",
        anchor=Anchor(region_id=region_id, x=0, y=0, w=1, h=1),
        **extra,
    )


def regions_of(image):
    return propose_regions(to_png(image), CAPTURE)


def test_drawings_stay_when_the_screen_is_the_same():
    regions = regions_of(lecture_frame()[0])
    figure = next(r for r in regions if r.kind == "figure")
    canvas = Canvas(shapes=[shape_on(figure.id)])

    kept, dropped = reanchor_canvas(canvas, regions, regions_of(lecture_frame()[0]))

    assert dropped == []
    assert kept.shapes[0].anchor.region_id == figure.id


def test_drawings_follow_their_region_when_the_numbers_shift():
    """A new text at the top right (a clock, say) renumbers every region; the drawing must follow."""
    before = lecture_frame()[0]
    after = before.copy()
    cv2.putText(after, "Clock 10:42", (1000, 40), FONT, 0.7, INK, 2, cv2.LINE_AA)
    old_regions, new_regions = regions_of(before), regions_of(after)
    figure_old = next(r for r in old_regions if r.kind == "figure")
    figure_new = next(r for r in new_regions if r.kind == "figure")
    assert figure_old.id != figure_new.id  # the premise: numbering did shift

    kept, dropped = reanchor_canvas(Canvas(shapes=[shape_on(figure_old.id)]), old_regions, new_regions)

    assert dropped == []
    assert kept.shapes[0].anchor.region_id == figure_new.id


def test_a_drawing_is_dropped_when_what_was_under_it_changed():
    before = lecture_frame()[0]
    after = before.copy()
    # Replace the diagram by something else in the same place.
    after[190:520, 770:1190] = 255
    cv2.rectangle(after, (800, 250), (1100, 480), (30, 30, 30), -1)
    old_regions, new_regions = regions_of(before), regions_of(after)
    figure_old = next(r for r in old_regions if r.kind == "figure")

    kept, dropped = reanchor_canvas(Canvas(shapes=[shape_on(figure_old.id, "gone")]), old_regions, new_regions)

    assert dropped == ["gone"]
    assert kept.shapes == []


def test_a_drawing_on_the_whole_screen_always_stays():
    regions = regions_of(lecture_frame()[0])

    kept, dropped = reanchor_canvas(Canvas(shapes=[shape_on(0)]), regions, [])

    assert dropped == [] and len(kept.shapes) == 1


def test_an_arrow_aimed_at_a_region_that_vanished_is_dropped():
    old_regions = regions_of(triangle_lecture())
    figure = next(r for r in old_regions if r.kind == "figure")
    label = next(r for r in old_regions if r.kind == "label")
    arrow = Shape(
        id="a", kind="arrow", anchor=Anchor(region_id=figure.id, x=0, y=0, w=0, h=0),
        target_region_id=label.id,
    )
    no_labels = [r for r in old_regions if r.kind != "label"]

    kept, dropped = reanchor_canvas(Canvas(shapes=[arrow]), old_regions, no_labels)

    assert dropped == ["a"]


def test_a_connector_goes_when_one_of_its_ends_is_dropped():
    old = regions_of(lecture_frame()[0])
    new = [r for r in old if r.kind != "figure"]
    figure = next(r for r in old if r.kind == "figure")
    text = next(r for r in old if r.kind == "text")
    shapes = [
        shape_on(figure.id, "a"),
        shape_on(text.id, "b"),
        Shape(id="c", kind="connector", anchor=Anchor(region_id=0, x=0, y=0, w=1, h=1), from_id="a", to_id="b"),
    ]

    kept, dropped = reanchor_canvas(Canvas(shapes=shapes), old, new)

    assert sorted(dropped) == ["a", "c"]
    assert [s.id for s in kept.shapes] == ["b"]


def test_without_previous_regions_a_shape_is_kept_only_if_its_number_still_exists():
    regions = regions_of(lecture_frame()[0])
    canvas = Canvas(shapes=[shape_on(1, "ok"), shape_on(999, "bad")])

    kept, dropped = reanchor_canvas(canvas, [], regions)

    assert [s.id for s in kept.shapes] == ["ok"]
    assert dropped == ["bad"]


def test_every_detected_region_has_a_signature_and_the_screen_does_not_need_one():
    regions = regions_of(lecture_frame()[0])

    for region in regions:
        if region.kind != "screen":
            assert region.signature and len(region.signature) == 16


def test_signatures_of_the_same_pixels_are_equal_and_of_different_pixels_differ():
    regions = regions_of(lecture_frame()[0])
    text = next(r for r in regions if r.kind == "text")
    figure = next(r for r in regions if r.kind == "figure")

    assert hamming(text.signature, text.signature) == 0
    assert hamming(text.signature, figure.signature) > 5
