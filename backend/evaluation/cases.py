"""Labelled evaluation cases, drawn in code so they are repeatable.

Each case is an image, a question, and what a correct answer must do:
  target    the box (x, y, w, h) the answer must point at (a shape on a region
            that overlaps it)
  segment   or the line segment (x1, y1, x2, y2) it must point at (a shape on a line
            region with the same end points, or on a label next to it)
            (a case has a target, a segment, or neither when it only needs a fact)
  keywords  words (any one) the explanation must contain; empty when not checked

Three kinds: right-triangle slides (which side is x, which side is N, how long
is x), application toolbars (which button is Save) and bullet slides (where does
it say ...). They are synthetic stand-ins; real frames can be added the same way.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

import cv2
import numpy as np

WIDTH, HEIGHT = 1280, 720
FONT = cv2.FONT_HERSHEY_SIMPLEX
Box = tuple[int, int, int, int]


@dataclass
class Case:
    name: str
    kind: str
    image: np.ndarray
    question: str
    target: Box | None = None
    keywords: list[str] = field(default_factory=list)
    segment: tuple[int, int, int, int] | None = None


def _box_of_points(points: list[tuple[float, float]], pad: int = 12) -> Box:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    x, y = int(min(xs)) - pad, int(min(ys)) - pad
    return x, y, int(max(xs) - min(xs)) + 2 * pad, int(max(ys) - min(ys)) + 2 * pad


# ---------------------------------------------------------------- triangles

TRIPLES = [(3, 4, 5), (5, 12, 13), (6, 8, 10), (8, 15, 17), (9, 12, 15), (7, 24, 25)]


def _triangle_case(index: int, rng: random.Random) -> list[Case]:
    a, b, c = TRIPLES[index % len(TRIPLES)]
    dark = index % 2 == 1
    corner = index % 4  # where the right angle is: 0 bottom-left, 1 bottom-right, 2 top-left, 3 top-right
    scale = 420 / max(a, b)
    ox, oy = rng.randint(380, 520), rng.randint(150, 210)
    horizontal, vertical = a * scale, b * scale
    # Right angle vertex and the two other vertices.
    if corner == 0:
        right, h_end, v_end = (ox, oy + vertical), (ox + horizontal, oy + vertical), (ox, oy)
    elif corner == 1:
        right, h_end, v_end = (ox + horizontal, oy + vertical), (ox, oy + vertical), (ox + horizontal, oy)
    elif corner == 2:
        right, h_end, v_end = (ox, oy), (ox + horizontal, oy), (ox, oy + vertical)
    else:
        right, h_end, v_end = (ox + horizontal, oy), (ox, oy), (ox + horizontal, oy + vertical)

    bg = (20, 20, 20) if dark else (255, 255, 255)
    ink = (230, 230, 230) if dark else (30, 30, 30)
    side_colour = [(0, 200, 230), (60, 200, 60), (240, 160, 0)] if dark else [(0, 120, 200), (30, 140, 30), (200, 90, 0)]
    image = np.full((HEIGHT, WIDTH, 3), bg, np.uint8)
    cv2.putText(image, "Find x in the figure.", (60, 90), FONT, 1.3, ink, 3, cv2.LINE_AA)

    sides = {
        "horizontal": (right, h_end, str(a)),
        "vertical": (right, v_end, str(b)),
        "hypotenuse": (h_end, v_end, "x"),
    }
    centroid = ((right[0] + h_end[0] + v_end[0]) / 3, (right[1] + h_end[1] + v_end[1]) / 3)
    segments: dict[str, tuple[int, int, int, int]] = {}
    for colour, (name, (p, q, label)) in zip(side_colour, sides.items()):
        cv2.line(image, (int(p[0]), int(p[1])), (int(q[0]), int(q[1])), colour, 4, cv2.LINE_AA)
        mx, my = (p[0] + q[0]) / 2, (p[1] + q[1]) / 2
        dx, dy = mx - centroid[0], my - centroid[1]
        norm = math.hypot(dx, dy) or 1
        tx, ty = mx + dx / norm * 38 - 12 * len(label), my + dy / norm * 38 + 14
        cv2.putText(image, label, (int(tx), int(ty)), FONT, 1.5, colour, 3, cv2.LINE_AA)
        segments[name] = (int(p[0]), int(p[1]), int(q[0]), int(q[1]))

    tag = f"tri{index}"
    return [
        Case(f"{tag}-which-x", "triangle", image, "Which side of the triangle is x? Point at it.", None, ["hypotenuse", "longest"], segments["hypotenuse"]),
        Case(f"{tag}-which-{a}", "triangle", image, f"Which side has length {a}? Point at it.", None, [], segments["horizontal"]),
        Case(f"{tag}-length", "triangle", image, "What is the length of x?", None, [str(c)], segments["hypotenuse"]),
    ]


# ---------------------------------------------------------------- toolbars

BUTTONS = ["Save", "Open", "Print", "Share", "Undo", "Redo", "Copy", "Paste", "Export", "Delete"]


def _toolbar_case(index: int, rng: random.Random) -> Case:
    labels = rng.sample(BUTTONS, 5)
    target_label = labels[index % len(labels)]
    image = np.full((HEIGHT, WIDTH, 3), 236, np.uint8)
    cv2.rectangle(image, (40, 40), (WIDTH - 40, HEIGHT - 40), (255, 255, 255), -1)
    cv2.putText(image, "Document editor", (70, 100), FONT, 0.9, (60, 60, 60), 2, cv2.LINE_AA)
    boxes: dict[str, Box] = {}
    x = 70
    for label in labels:
        w = 150
        cv2.rectangle(image, (x, 140), (x + w, 192), (225, 225, 225), -1)
        cv2.rectangle(image, (x, 140), (x + w, 192), (90, 90, 90), 2)
        cv2.putText(image, label, (x + 28, 174), FONT, 0.8, (30, 30, 30), 2, cv2.LINE_AA)
        boxes[label] = (x, 140, w, 52)
        x += w + 24
    for line in range(5):
        cv2.putText(image, "Lorem ipsum dolor sit amet consectetur adipiscing", (70, 300 + line * 50), FONT, 0.75, (90, 90, 90), 1, cv2.LINE_AA)
    return Case(f"toolbar{index}", "toolbar", image, f"Which button is {target_label}? Point at it.", boxes[target_label], [])


# ---------------------------------------------------------------- bullet slides

PHRASES = [
    "Each node has at most two children",
    "Lookup takes logarithmic time when balanced",
    "The left subtree holds smaller keys",
    "Insertion keeps the ordering property",
    "Deleting a leaf is the simplest case",
    "Traversal visits every node once",
    "A balanced tree has small height",
    "The root has no parent",
]


def _bullet_case(index: int, rng: random.Random) -> Case:
    lines = rng.sample(PHRASES, 5)
    chosen = index % len(lines)
    image = np.full((HEIGHT, WIDTH, 3), 255, np.uint8)
    cv2.putText(image, "Binary search trees", (60, 100), FONT, 1.7, (30, 30, 30), 3, cv2.LINE_AA)
    target: Box = (0, 0, 0, 0)
    for number, phrase in enumerate(lines):
        y = 220 + number * 80
        cv2.putText(image, phrase, (80, y), FONT, 1.0, (40, 40, 40), 2, cv2.LINE_AA)
        (width, height), _ = cv2.getTextSize(phrase, FONT, 1.0, 2)
        if number == chosen:
            target = (80 - 10, y - height - 10, width + 20, height + 24)
    return Case(f"bullets{index}", "bullets", image, f'Where does it say "{lines[chosen]}"? Point at it.', target, [])


def build_cases() -> list[Case]:
    """At least 30 cases, the same every time."""
    rng = random.Random(7)
    cases: list[Case] = []
    for index in range(6):
        cases += _triangle_case(index, rng)  # 18 cases
    for index in range(7):
        cases.append(_toolbar_case(index, rng))  # 7
    for index in range(6):
        cases.append(_bullet_case(index, rng))  # 6
    return cases
