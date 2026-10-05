"""Visual aids: ready-made constructions the model can ask for by name, when they fit
what the learner is looking at. An aid is turned into ordinary shapes (polygons,
labels) plus, for the ones that move, a motion, so the overlay needs no special
case. Aids know nothing about the screen except the free space they are given."""

from __future__ import annotations

from typing import Callable

from .contract import Anchor, Motion, Operation, Point, Shape, Style
from .proof import Arrangement, Point as Pt, arrange

# What the model may ask for.
AIDS = ("pythagoras_proof",)

FRAME_COLOR = "#9aa0a6"
TRIANGLE_COLOR = "#ffd23f"
HOLE_COLOR = "#ff3b30"
A_COLOR = "#34c759"
B_COLOR = "#0a84ff"
LABEL_ROOM = 30  # above the square, for the lengths of the legs


def number(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else str(round(value, 2))


class PythagoreanProof:
    """The rearrangement proof drawn in free space.

    `first()` draws four triangles in a square with a tilted square (side c) left
    uncovered; `second()` slides the same triangles into the other arrangement,
    which leaves a square of side a and one of side b. Remembers its pieces so the
    second step moves the shapes the first one drew.
    """

    def __init__(
        self,
        a: float,
        b: float,
        origin: Pt,
        size: float,
        screen: tuple[int, int],
        next_id: Callable[[], str],
        turn: int,
        c_name: str = "c",
    ) -> None:
        self.a, self.b = a, b
        self.c_name = c_name
        self.origin, self.size = origin, size
        self.screen = screen
        self.next_id = next_id
        self.turn = turn
        self.pieces: Arrangement = arrange(a, b, origin, size)
        self.ids: dict[str, str] = {}  # piece name -> shape id, once drawn
        self.drawn_first = False

    @property
    def box(self) -> tuple[float, float, float, float]:
        """The rectangle it occupies, labels included."""
        return self.origin[0], self.origin[1] - LABEL_ROOM, self.size, self.size + LABEL_ROOM

    # -- shapes ------------------------------------------------------------------

    def _fraction(self, x: float, y: float) -> tuple[float, float]:
        w, h = self.screen
        return min(1.0, max(0.0, x / w)), min(1.0, max(0.0, y / h))

    def _polygon(self, name: str, points: list[Pt], color: str, text: str | None = None) -> Shape:
        shape = Shape(
            id=self.next_id(),
            kind="polygon",
            anchor=Anchor(region_id=0, x=0, y=0, w=1, h=1),
            points=[Point(x=fx, y=fy) for fx, fy in (self._fraction(x, y) for x, y in points)],
            text=text,
            style=Style(color=color),
            turn=self.turn,
        )
        self.ids[name] = shape.id
        return shape

    def _label(self, name: str, text: str, x: float, y: float) -> Shape:
        fx, fy = self._fraction(x - 6 * len(text), y)
        shape = Shape(
            id=self.next_id(),
            kind="label",
            anchor=Anchor(region_id=0, x=fx, y=fy, w=0, h=0),
            text=text,
            style=Style(color=TRIANGLE_COLOR),
            keep=True,  # part of the diagram, not a pointing mark
            turn=self.turn,
        )
        self.ids[name] = shape.id
        return shape

    def _frame_and_labels(self) -> list[Shape]:
        p = self.pieces
        la, lb = self.a * self.size / (self.a + self.b), self.b * self.size / (self.a + self.b)
        ox, oy = self.origin
        return [
            self._polygon("frame", p.frame, FRAME_COLOR),
            self._label("label_a", number(self.a), ox + la / 2, oy),
            self._label("label_b", number(self.b), ox + la + lb / 2, oy),
        ]

    def _squares(self) -> list[Shape]:
        p = self.pieces
        return [
            self._polygon("square_a", p.square_a, A_COLOR, f"{number(self.a)}^2 = {number(self.a ** 2)}"),
            self._polygon("square_b", p.square_b, B_COLOR, f"{number(self.b)}^2 = {number(self.b ** 2)}"),
        ]

    # -- the two steps -----------------------------------------------------------

    def first(self) -> list[Operation]:
        p = self.pieces
        shapes = self._frame_and_labels()
        shapes += [self._polygon(f"triangle_{i + 1}", t, TRIANGLE_COLOR) for i, t in enumerate(p.first)]
        shapes.append(self._polygon("hole", p.hole, HOLE_COLOR, f"{self.c_name}^2"))
        self.drawn_first = True
        return [Operation(op="add", shape_id=s.id, shape=s) for s in shapes]

    def second(self) -> list[Operation]:
        p = self.pieces
        if not self.drawn_first:
            # Nothing of the first step is on screen: draw the finished picture.
            shapes = self._frame_and_labels()
            shapes += [self._polygon(f"triangle_{i + 1}", t, TRIANGLE_COLOR) for i, t in enumerate(p.second)]
            shapes += self._squares()
            return [Operation(op="add", shape_id=s.id, shape=s) for s in shapes]

        operations = [Operation(op="remove", shape_id=self.ids.pop("hole"))]
        for i, (end, slide) in enumerate(zip(p.second, p.slides)):
            shape_id = self.ids[f"triangle_{i + 1}"]
            moved = Shape(
                id=shape_id,
                kind="polygon",
                anchor=Anchor(region_id=0, x=0, y=0, w=1, h=1),
                points=[Point(x=fx, y=fy) for fx, fy in (self._fraction(x, y) for x, y in end)],
                style=Style(color=TRIANGLE_COLOR),
                motion=Motion(
                    dx=slide.dx, dy=slide.dy, rotate=slide.rotate, pivot_x=slide.pivot[0], pivot_y=slide.pivot[1]
                ),
                turn=self.turn,
            )
            operations.append(Operation(op="update", shape_id=shape_id, shape=moved))
        operations += [Operation(op="add", shape_id=s.id, shape=s) for s in self._squares()]
        return operations

    def groups(self) -> dict[str, list[str]]:
        """Names a later step can remove: "proof" takes the whole picture off."""
        return {"proof": list(self.ids.values())}
