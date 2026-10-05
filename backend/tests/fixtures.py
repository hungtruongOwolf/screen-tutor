"""Synthetic capture fixtures with known layouts.

They are drawn in code so tests stay deterministic and nothing binary is
committed. They only approximate real screens (see Further Notes in the spec):
real lecture frames and application windows need to be added over time.
"""

from __future__ import annotations

import cv2
import numpy as np

WIDTH, HEIGHT = 1280, 720
FONT = cv2.FONT_HERSHEY_SIMPLEX
INK = (30, 30, 30)


def to_png(image: np.ndarray) -> bytes:
    ok, encoded = cv2.imencode(".png", image)
    assert ok
    return encoded.tobytes()


def text(image: np.ndarray, label: str, origin: tuple[int, int], scale: float, thickness: int = 2):
    cv2.putText(image, label, origin, FONT, scale, INK, thickness, cv2.LINE_AA)


def lecture_frame() -> tuple[np.ndarray, dict[str, tuple[int, int, int, int]]]:
    """A slide: title, bullet text on the left, a three-box diagram on the right.

    Returns the image and the ground-truth boxes (x, y, w, h) by name.
    """
    image = np.full((HEIGHT, WIDTH, 3), 255, np.uint8)

    text(image, "Binary search trees", (60, 100), 1.8, 3)
    for index, line in enumerate(
        [
            "Each node has at most two children",
            "Left subtree holds smaller keys",
            "Right subtree holds larger keys",
            "Lookup takes O(log n) when balanced",
        ]
    ):
        text(image, line, (60, 230 + index * 70), 0.95)

    # Diagram: root with two children.
    boxes = {"root": (900, 200, 160, 80), "left": (780, 420, 160, 80), "right": (1020, 420, 160, 80)}
    for name, (x, y, w, h) in boxes.items():
        cv2.rectangle(image, (x, y), (x + w, y + h), INK, 4)
        text(image, {"root": "8", "left": "3", "right": "10"}[name], (x + w // 2 - 12, y + 55), 1.4, 3)
    cv2.line(image, (950, 280), (860, 420), INK, 4)
    cv2.line(image, (1010, 280), (1100, 420), INK, 4)

    truth = {
        "title": (60, 50, 700, 70),
        "bullets": (60, 180, 740, 300),
        "diagram": (780, 200, 400, 300),
    }
    return image, truth


def lecture_frame_with_change() -> tuple[np.ndarray, tuple[int, int, int, int]]:
    """The same slide with a new filled shape drawn at a known place."""
    image, _ = lecture_frame()
    changed = (120, 560, 300, 120)
    x, y, w, h = changed
    cv2.rectangle(image, (x, y), (x + w, y + h), (40, 120, 220), -1)
    return image, changed


def app_window() -> tuple[np.ndarray, dict[str, tuple[int, int, int, int]]]:
    """A plain application window: toolbar buttons, a search box and a paragraph."""
    image = np.full((HEIGHT, WIDTH, 3), 235, np.uint8)
    cv2.rectangle(image, (40, 40), (WIDTH - 40, HEIGHT - 40), (255, 255, 255), -1)

    buttons = {"new": (80, 80, 130, 44), "open": (230, 80, 130, 44), "save": (380, 80, 130, 44)}
    for label, (x, y, w, h) in buttons.items():
        cv2.rectangle(image, (x, y), (x + w, y + h), (225, 225, 225), -1)
        cv2.rectangle(image, (x, y), (x + w, y + h), (90, 90, 90), 2)
        text(image, label.title(), (x + 22, y + 30), 0.7)

    search = (700, 80, 460, 44)
    x, y, w, h = search
    cv2.rectangle(image, (x, y), (x + w, y + h), (90, 90, 90), 2)
    text(image, "Search documents", (x + 14, y + 30), 0.7)

    for index in range(6):
        text(image, "The quick brown fox jumps over the lazy dog again", (80, 260 + index * 48), 0.8, 1)

    truth = dict(buttons)
    truth["search"] = search
    return image, truth


TRIANGLE = {
    "base": (410, 570, 880, 570),
    "side": (880, 570, 880, 372),
    "hypotenuse": (410, 570, 880, 372),
}
TRIANGLE_LABELS = {"x": (636, 445), "5": (898, 485), "12": (665, 598)}


def triangle_lecture() -> np.ndarray:
    """A dark slide with a right triangle and three labels, like a real maths video."""
    image = np.zeros((HEIGHT, WIDTH, 3), np.uint8)
    cv2.putText(image, "53. Find x in figure 127.", (400, 255), FONT, 1.3, (60, 200, 200), 3, cv2.LINE_AA)
    cv2.line(image, (410, 570), (880, 570), (0, 220, 230), 3, cv2.LINE_AA)
    cv2.line(image, (880, 570), (880, 372), (0, 220, 230), 3, cv2.LINE_AA)
    cv2.line(image, (410, 570), (880, 372), (220, 190, 0), 3, cv2.LINE_AA)
    cv2.putText(image, "x", (626, 458), FONT, 1.5, (40, 220, 40), 3, cv2.LINE_AA)
    cv2.putText(image, "5", (888, 500), FONT, 1.5, (60, 150, 255), 3, cv2.LINE_AA)
    cv2.putText(image, "12", (645, 612), FONT, 1.5, (0, 220, 230), 3, cv2.LINE_AA)
    return image
