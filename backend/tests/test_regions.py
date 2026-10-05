"""Region proposer tests: behaviour on screens with known layouts."""

import cv2
import pytest

from app.contract import BBox, CaptureMeta, Region
from app.regions import Box, decode_image, iou, propose_regions
import numpy as np
from fixtures import FONT, INK, app_window, lecture_frame, lecture_frame_with_change, to_png

WIDTH, HEIGHT = 1280, 720
CAPTURE = CaptureMeta(width=WIDTH, height=HEIGHT)


def as_box(region) -> Box:
    b = region.bbox
    return Box(b.x, b.y, b.w, b.h, region.kind)


def truth_box(rect, kind="truth") -> Box:
    x, y, w, h = rect
    return Box(x, y, w, h, kind)


def of_kind(regions, kind):
    return [r for r in regions if r.kind == kind]


def best_overlap(regions, kind, rect) -> float:
    expected = truth_box(rect)
    return max((iou(as_box(r), expected) for r in of_kind(regions, kind)), default=0.0)


def bullet_lines(regions, truth):
    """How many text regions sit inside the truth box: the lines of a list are
    separate regions, so each can be pointed at."""
    tx, ty, tw, th = truth
    return sum(
        1
        for r in regions
        if r.kind == "text" and tx <= r.bbox.x + r.bbox.w / 2 <= tx + tw and ty <= r.bbox.y + r.bbox.h / 2 <= ty + th
    )


def test_the_whole_capture_is_always_region_zero():
    regions = propose_regions(to_png(lecture_frame()[0]), CAPTURE)

    assert regions[0].id == 0
    assert regions[0].kind == "screen"
    assert regions[0].bbox == BBox(x=0, y=0, w=WIDTH, h=HEIGHT)


def test_lecture_slide_title_text_and_diagram_are_found():
    image, truth = lecture_frame()

    regions = propose_regions(to_png(image), CAPTURE)

    assert best_overlap(regions, "text", truth["title"]) > 0.5
    assert bullet_lines(regions, truth["bullets"]) >= 3  # each bullet is a region of its own
    assert best_overlap(regions, "figure", truth["diagram"]) > 0.5


def test_application_controls_are_found():
    image, truth = app_window()

    regions = propose_regions(to_png(image), CAPTURE)

    for name in ("new", "open", "save", "search"):
        assert best_overlap(regions, "control", truth[name]) > 0.5, name


def test_changed_area_is_reported_when_a_previous_capture_is_given():
    previous = to_png(lecture_frame()[0])
    image, changed = lecture_frame_with_change()

    regions = propose_regions(to_png(image), CAPTURE, previous_png=previous)

    assert best_overlap(regions, "changed", changed) > 0.5


def test_nothing_is_reported_changed_when_the_screen_did_not_change():
    png = to_png(lecture_frame()[0])

    regions = propose_regions(png, CAPTURE, previous_png=png)

    assert of_kind(regions, "changed") == []


def test_count_never_exceeds_the_cap():
    png = to_png(lecture_frame()[0])

    regions = propose_regions(png, CAPTURE, max_regions=3)

    assert len(regions) - 1 <= 3


def test_cap_can_be_set_by_environment(monkeypatch):
    monkeypatch.setenv("MAX_REGIONS", "2")

    regions = propose_regions(to_png(lecture_frame()[0]), CAPTURE)

    assert len(regions) - 1 <= 2


@pytest.mark.parametrize("make", [lecture_frame, app_window])
def test_regions_are_numbered_unique_in_bounds_and_not_duplicated(make):
    regions = propose_regions(to_png(make()[0]), CAPTURE)

    detected = regions[1:]
    assert [r.id for r in detected] == list(range(1, len(detected) + 1))
    for region in regions:
        b = region.bbox
        assert 0 <= b.x and 0 <= b.y and b.w > 0 and b.h > 0
        assert b.x + b.w <= WIDTH and b.y + b.h <= HEIGHT
    for index, a in enumerate(detected):
        for b in detected[index + 1 :]:
            if a.kind == b.kind:
                assert iou(as_box(a), as_box(b)) <= 0.6


def test_regions_follow_reading_order():
    regions = propose_regions(to_png(lecture_frame()[0]), CAPTURE)

    title = next(r for r in of_kind(regions, "text") if r.bbox.y < 150)
    bullets = next(r for r in of_kind(regions, "text") if r.bbox.y > 150)
    assert title.id < bullets.id


def test_boxes_are_in_capture_pixels_when_the_image_is_smaller_than_the_capture():
    image, truth = lecture_frame()
    half = cv2.resize(image, (WIDTH // 2, HEIGHT // 2), interpolation=cv2.INTER_AREA)

    regions = propose_regions(to_png(half), CAPTURE)

    assert bullet_lines(regions, truth["bullets"]) >= 3
    assert best_overlap(regions, "figure", truth["diagram"]) > 0.4


def test_regions_centred_in_an_excluded_area_are_not_proposed():
    image, truth = lecture_frame()
    x, y, w, h = truth["diagram"]
    capture = CAPTURE.model_copy(update={"excluded": [BBox(x=x, y=y, w=w, h=h)]})

    regions = propose_regions(to_png(image), capture)

    assert best_overlap(regions, "figure", truth["diagram"]) == 0.0
    assert bullet_lines(regions, truth["bullets"]) >= 3  # each bullet is a region of its own


def test_a_blank_screen_or_an_unreadable_image_gives_only_the_whole_capture():
    blank = to_png(cv2.UMat(HEIGHT, WIDTH, cv2.CV_8UC3).get() * 0 + 255)

    assert [r.kind for r in propose_regions(blank, CAPTURE)] == ["screen"]
    assert [r.kind for r in propose_regions(b"not an image", CAPTURE)] == ["screen"]


def test_decode_image_reads_png_bytes():
    assert decode_image(to_png(lecture_frame()[0])).shape == (HEIGHT, WIDTH, 3)


def test_labels_far_apart_on_one_row_do_not_merge_into_one_block():
    """A tab-bar-like row: separate labels must stay separate regions."""
    image = np.full((HEIGHT, WIDTH, 3), 255, np.uint8)
    for x in (60, 400, 740):
        cv2.putText(image, "Tab title here", (x, 40), FONT, 0.7, INK, 2, cv2.LINE_AA)

    regions = of_kind(propose_regions(to_png(image), CAPTURE), "text")

    assert len(regions) == 3
    assert all(r.bbox.w < 300 for r in regions)


def test_a_title_bar_row_and_a_text_row_below_it_with_different_left_edges_stay_separate():
    image = np.full((HEIGHT, WIDTH, 3), 255, np.uint8)
    cv2.putText(image, "Window title", (60, 40), FONT, 0.7, INK, 2, cv2.LINE_AA)
    cv2.putText(image, "https://example.com/some/long/address", (600, 90), FONT, 0.7, INK, 2, cv2.LINE_AA)

    regions = of_kind(propose_regions(to_png(image), CAPTURE), "text")

    assert len(regions) == 2


def test_the_sides_of_a_triangle_are_found_as_lines_with_end_points():
    from fixtures import TRIANGLE, triangle_lecture

    regions = propose_regions(to_png(triangle_lecture()), CAPTURE)
    lines = [r.line for r in regions if r.kind == "line"]

    def close(a, b, tolerance=15):
        return all(abs(p - q) <= tolerance for p, q in zip(a, b))

    for name, (x1, y1, x2, y2) in TRIANGLE.items():
        assert any(close(line, (x1, y1, x2, y2)) or close(line, (x2, y2, x1, y1)) for line in lines), name


def test_numbers_and_letters_inside_a_figure_are_found_as_labels():
    from fixtures import TRIANGLE_LABELS, triangle_lecture

    regions = propose_regions(to_png(triangle_lecture()), CAPTURE)
    labels = [r.bbox for r in regions if r.kind == "label"]

    for name, (cx, cy) in TRIANGLE_LABELS.items():
        assert any(b.x <= cx <= b.x + b.w and b.y <= cy <= b.y + b.h for b in labels), name


def test_line_regions_have_end_points_and_other_regions_do_not():
    from fixtures import triangle_lecture

    regions = propose_regions(to_png(triangle_lecture()), CAPTURE)

    assert all((r.line is not None) == (r.kind == "line") for r in regions)


# ---- a small line drawing (a triangle in a video that is not full screen) ----------------------------


def screen_with_small_triangle(size: int):
    """A 1920 by 1080 dark screen: a title line, browser-like frames and a right triangle with its
    labels, `size` pixels wide."""
    image = np.zeros((1080, 1920, 3), np.uint8)
    cv2.rectangle(image, (0, 0), (1919, 110), (45, 45, 45), -1)  # browser bar
    cv2.line(image, (0, 165), (1919, 165), (90, 90, 90), 2)
    cv2.putText(image, "53. Find the length x in figure 127.", (700, 300), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (120, 190, 190), 2, cv2.LINE_AA)
    x0, y0 = 800, 420
    w, h = size, int(size * 0.42)
    a, b, c = (x0, y0 + h), (x0 + w, y0 + h), (x0 + w, y0)
    for p1, p2, color in ((a, b, (0, 200, 220)), (b, c, (0, 200, 220)), (a, c, (255, 200, 0))):
        cv2.line(image, p1, p2, color, 3, cv2.LINE_AA)
    font = max(0.5, size / 420)
    cv2.putText(image, "12", (x0 + w // 2 - 10, y0 + h + 38), cv2.FONT_HERSHEY_SIMPLEX, font, (0, 220, 255), 2, cv2.LINE_AA)
    cv2.putText(image, "5", (x0 + w + 12, y0 + h // 2), cv2.FONT_HERSHEY_SIMPLEX, font, (0, 140, 255), 2, cv2.LINE_AA)
    cv2.putText(image, "x", (x0 + w // 2 - 30, y0 + h // 2 - 20), cv2.FONT_HERSHEY_SIMPLEX, font, (0, 220, 0), 2, cv2.LINE_AA)
    return image, (a, b, c)


def near(point, other, tolerance=25):
    return abs(point[0] - other[0]) <= tolerance and abs(point[1] - other[1]) <= tolerance


@pytest.mark.parametrize("size", [470, 300, 220, 170])
def test_the_three_sides_of_a_triangle_are_found_however_big_it_is_drawn(size):
    image, (a, b, c) = screen_with_small_triangle(size)

    regions = propose_regions(to_png(image), CaptureMeta(width=1920, height=1080))

    lines = [r for r in regions if r.kind == "line"]
    ends = [((r.line[0], r.line[1]), (r.line[2], r.line[3])) for r in lines]
    for p1, p2 in ((a, b), (b, c), (a, c)):
        assert any((near(e1, p1) and near(e2, p2)) or (near(e1, p2) and near(e2, p1)) for e1, e2 in ends), (p1, p2, ends)


def test_a_screen_of_small_buttons_and_straight_frames_has_no_drawing():
    image = np.zeros((1080, 1920, 3), np.uint8)
    for row in range(4):
        for column in range(10):
            x, y = 80 + column * 180, 150 + row * 90
            cv2.rectangle(image, (x, y), (x + 140, y + 50), (120, 120, 120), 2)
            cv2.line(image, (x + 10, y + 25), (x + 130, y + 25), (120, 120, 120), 1)

    regions = propose_regions(to_png(image), CaptureMeta(width=1920, height=1080))

    assert [r for r in regions if r.kind == "line"] == []


# ---- a busy lecture frame: white board, handwriting, a thin triangle, a presenter ---------------------


def lecture_with_presenter():
    """A 1920 by 1080 screen: dark browser, a white video with handwriting, a triangle drawn with thin
    black lines and a presenter (a smooth, noisy, many-toned blob) beside it."""
    image = np.full((1080, 1920, 3), 20, np.uint8)
    image[165:905, 290:1610] = 248  # the white video
    cv2.putText(image, "Use the Pythagorean Theorem to find the missing value.", (340, 240), cv2.FONT_HERSHEY_SCRIPT_SIMPLEX, 1.7, (40, 40, 40), 2, cv2.LINE_AA)
    a, b, c = (480, 477), (690, 477), (480, 320)
    for p1, p2 in ((a, b), (b, c), (c, a)):
        cv2.line(image, p1, p2, (10, 10, 10), 3, cv2.LINE_AA)
    cv2.rectangle(image, (480, 462), (497, 477), (10, 10, 10), 2)
    cv2.putText(image, "6", (440, 420), cv2.FONT_HERSHEY_SIMPLEX, 1.6, (10, 10, 10), 2, cv2.LINE_AA)
    cv2.putText(image, "8", (575, 535), cv2.FONT_HERSHEY_SIMPLEX, 1.6, (10, 10, 10), 2, cv2.LINE_AA)
    cv2.putText(image, "x", (590, 380), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (10, 10, 10), 2, cv2.LINE_AA)
    # the presenter: many overlapping patches of in-between tones, like a photograph
    rng = np.random.default_rng(3)
    person = image[440:1076, 911:1361].copy()
    mask = np.zeros(person.shape[:2], np.uint8)
    cv2.ellipse(mask, (225, 330), (200, 300), 0, 0, 360, 255, -1)
    texture = person.copy()
    for _ in range(90):
        center = (int(rng.integers(0, 450)), int(rng.integers(0, 636)))
        axes = (int(rng.integers(15, 70)), int(rng.integers(15, 70)))
        tone = rng.integers(60, 200, 3).tolist()
        cv2.ellipse(texture, center, axes, int(rng.integers(0, 180)), 0, 360, tone, -1)
    texture = cv2.GaussianBlur(texture, (0, 0), 2.5)
    person[mask > 0] = texture[mask > 0]
    image[440:1076, 911:1361] = person
    return image, (a, b, c)


@pytest.mark.parametrize("quality", [None, 92, 70])
def test_a_thin_triangle_next_to_a_presenter_still_gives_its_three_sides(quality):
    image, (a, b, c) = lecture_with_presenter()
    data = to_png(image) if quality is None else cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, quality])[1].tobytes()

    regions = propose_regions(data, CaptureMeta(width=1920, height=1080))

    ends = [((r.line[0], r.line[1]), (r.line[2], r.line[3])) for r in regions if r.kind == "line"]
    for p1, p2 in ((a, b), (b, c), (a, c)):
        assert any((near(e1, p1, 30) and near(e2, p2, 30)) or (near(e1, p2, 30) and near(e2, p1, 30)) for e1, e2 in ends), (p1, p2, ends)


def test_a_presenter_is_an_image_region_and_handwriting_and_a_flat_wall_are_not():
    image, _ = lecture_with_presenter()

    regions = propose_regions(to_png(image), CaptureMeta(width=1920, height=1080))

    images = [r for r in regions if r.kind == "image"]
    assert any(r.bbox.x < 1100 < r.bbox.x + r.bbox.w and r.bbox.y < 800 < r.bbox.y + r.bbox.h for r in images)  # the person
    for r in images:  # nothing on the title row or on the empty wall to the left of the person
        assert not (r.bbox.y < 250 < r.bbox.y + r.bbox.h and r.bbox.w > 600)
        assert not (r.bbox.x < 400 < r.bbox.x + r.bbox.w and r.bbox.y < 700 < r.bbox.y + r.bbox.h)


def test_the_proof_diagram_keeps_off_a_presenter_and_off_the_picture_it_is_about():
    import json

    from app.answer import build_decision
    from app.contract import Canvas

    image, _ = lecture_with_presenter()
    regions = propose_regions(to_png(image), CaptureMeta(width=1920, height=1080))
    figure = next(r for r in regions if r.kind == "figure")
    steps = [{"caption": "proof", "shapes": [{"kind": "pythagoras_proof", "region_id": figure.id, "a": 6, "b": 8, "stage": 1}]}]

    decision = build_decision(json.dumps({"explanation": "e", "steps": steps}), regions, 0, Canvas())

    frame = next(op.shape for op in decision.steps[0].operations if op.shape.kind == "polygon")
    xs = [p.x * 1920 for p in frame.points]
    ys = [p.y * 1080 for p in frame.points]
    box = (min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))

    def overlap(r):
        return not (box[0] + box[2] <= r.bbox.x or r.bbox.x + r.bbox.w <= box[0] or box[1] + box[3] <= r.bbox.y or r.bbox.y + r.bbox.h <= box[1])

    assert not any(overlap(r) for r in regions if r.kind in ("image", "figure", "text"))



def test_ink_regions_find_a_small_mark_that_no_other_region_covers():
    from app.regions import ink_regions

    image = np.full((1080, 1920, 3), 250, np.uint8)
    cv2.putText(image, "6", (440, 420), cv2.FONT_HERSHEY_SIMPLEX, 1.6, (10, 10, 10), 3, cv2.LINE_AA)
    capture = CaptureMeta(width=1920, height=1080)

    ink = ink_regions(to_png(image), capture, [], first_id=100)

    assert len(ink) == 1
    box = ink[0].bbox
    assert ink[0].kind == "ink" and box.x <= 450 <= box.x + box.w and box.y <= 400 <= box.y + box.h
    assert box.w < 80 and box.h < 80

    # Something the proposer already knows about is not added again.
    known = [Region(id=1, bbox=BBox(x=box.x - 5, y=box.y - 5, w=box.w + 10, h=box.h + 10), kind="label")]
    assert ink_regions(to_png(image), capture, known, first_id=100) == []
