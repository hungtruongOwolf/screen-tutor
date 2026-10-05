"""The rearrangement proof: the geometry must be exact, or the picture proves nothing."""

import math

import pytest

from app.proof import ProofError, arrange


def area(points):
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1]))) / 2


def apply_slide(points, slide):
    """Where a piece that rests at `points` was before it slid (the overlay's CSS
    transform: translate(dx, dy) rotate(angle) about the pivot)."""
    angle = math.radians(slide.rotate)
    out = []
    for x, y in points:
        rx, ry = x - slide.pivot[0], y - slide.pivot[1]
        out.append(
            (
                slide.pivot[0] + rx * math.cos(angle) - ry * math.sin(angle) + slide.dx,
                slide.pivot[1] + rx * math.sin(angle) + ry * math.cos(angle) + slide.dy,
            )
        )
    return out


def same(a, b):
    key = lambda pts: sorted((round(x, 2), round(y, 2)) for x, y in pts)  # noqa: E731
    return key(a) == key(b)


@pytest.mark.parametrize("a,b", [(5, 12), (3, 4), (12, 5), (1, 1), (8, 15)])
def test_the_hole_has_the_area_of_the_hypotenuse_square_and_the_leftovers_those_of_the_legs(a, b):
    p = arrange(a, b, (100, 50), 340)
    k = 340 / (a + b)

    assert area(p.hole) == pytest.approx((a * k) ** 2 + (b * k) ** 2)  # c^2 = a^2 + b^2
    assert area(p.square_a) == pytest.approx((a * k) ** 2)
    assert area(p.square_b) == pytest.approx((b * k) ** 2)
    assert area(p.hole) == pytest.approx(area(p.square_a) + area(p.square_b))


@pytest.mark.parametrize("a,b", [(5, 12), (3, 4), (12, 5), (8, 15)])
def test_the_four_triangles_fill_the_big_square_with_the_hole_or_with_the_two_squares(a, b):
    p = arrange(a, b, (0, 0), 340)
    triangles = sum(area(t) for t in p.first)

    assert triangles + area(p.hole) == pytest.approx(340**2)
    assert sum(area(t) for t in p.second) + area(p.square_a) + area(p.square_b) == pytest.approx(340**2)
    assert triangles == pytest.approx(sum(area(t) for t in p.second))


@pytest.mark.parametrize("a,b", [(5, 12), (3, 4), (12, 5), (1, 1)])
def test_each_slide_carries_a_triangle_from_its_first_place_to_its_second_without_flipping(a, b):
    p = arrange(a, b, (30, 20), 300)

    for first, second, slide in zip(p.first, p.second, p.slides):
        assert same(apply_slide(second, slide), first)
        assert slide.rotate % 90 == 0
        assert -180 <= slide.rotate <= 180  # never the long way round


def test_the_pieces_stay_inside_the_square_they_are_drawn_in():
    p = arrange(5, 12, (200, 100), 300)

    for piece in [*p.first, *p.second, p.hole, p.square_a, p.square_b]:
        for x, y in piece:
            assert 200 - 1e-6 <= x <= 500 + 1e-6 and 100 - 1e-6 <= y <= 400 + 1e-6


def test_legs_that_make_no_sense_are_refused():
    for a, b in [(0, 3), (-1, 4), (1, 100)]:
        with pytest.raises(ProofError):
            arrange(a, b, (0, 0), 300)
