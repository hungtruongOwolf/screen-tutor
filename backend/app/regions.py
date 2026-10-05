"""Region proposer: finds numbered candidate regions on a capture with OpenCV 5.

Why this exists: vision models are poor at returning pixel coordinates, but
good at choosing from a short numbered list. The proposer produces that list.

Kinds of region:
  screen   the whole capture, always present with id 0 (a fallback anchor)
  text     a block of text (title, paragraph, label)
  figure   a large non-text area (diagram, picture, chart, video area)
  control  a rectangular interface control (button, input, panel)
  changed  an area that differs from an earlier capture
  line     a straight segment inside a figure (a side of a triangle, an axis);
           it carries its end points
  label    a small mark inside a figure (a letter, a number)

Pipeline: shrink for speed -> propose candidates per kind -> drop duplicates
-> cap the count -> number in reading order -> scale boxes back to capture
pixels. Detection is classical (gradients, morphology, contours), so it is
deterministic, fast and needs no model.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass

import cv2
import numpy as np

from .contract import BBox, CaptureMeta, Region

DEFAULT_MAX_REGIONS = 70
# Lines of text join into a block only when they are packed like a paragraph (the gap
# between them at most this many line heights). Menu items, list rows and buttons are
# spaced wider, so each stays a region of its own that can be pointed at.
STACK_GAP = 0.8
SMALL_FIGURE = 0.002  # the smallest share of the screen a line drawing can fill
DETECTION_WIDTH = 1280  # captures wider than this are shrunk before analysis


@dataclass(frozen=True)
class Box:
    x: int
    y: int
    w: int
    h: int
    kind: str
    # Only for kind "line": the segment end points (x1, y1, x2, y2).
    line: tuple[int, int, int, int] | None = None

    @property
    def area(self) -> int:
        return self.w * self.h

    @property
    def x2(self) -> int:
        return self.x + self.w

    @property
    def y2(self) -> int:
        return self.y + self.h


def intersection(a: Box, b: Box) -> int:
    w = min(a.x2, b.x2) - max(a.x, b.x)
    h = min(a.y2, b.y2) - max(a.y, b.y)
    return max(w, 0) * max(h, 0)


def iou(a: Box, b: Box) -> float:
    inter = intersection(a, b)
    union = a.area + b.area - inter
    return inter / union if union else 0.0


def contained_fraction(inner: Box, outer: Box) -> float:
    """Share of `inner` that lies inside `outer`."""
    return intersection(inner, outer) / inner.area if inner.area else 0.0


def decode_image(image_png: bytes) -> np.ndarray | None:
    array = np.frombuffer(image_png, dtype=np.uint8)
    return cv2.imdecode(array, cv2.IMREAD_COLOR)


def merge_where(boxes: list[Box], should_merge, kind: str) -> list[Box]:
    """Repeatedly merge any two boxes for which `should_merge(a, b)` holds."""
    boxes = list(boxes)
    changed = True
    while changed:
        changed = False
        result: list[Box] = []
        while boxes:
            current = boxes.pop()
            index = 0
            while index < len(boxes):
                other = boxes[index]
                if should_merge(current, other):
                    x, y = min(current.x, other.x), min(current.y, other.y)
                    x2, y2 = max(current.x2, other.x2), max(current.y2, other.y2)
                    current = Box(x, y, x2 - x, y2 - y, kind)
                    boxes.pop(index)
                    changed = True
                else:
                    index += 1
            result.append(current)
        boxes = result
    return boxes


def same_row(a: Box, b: Box, gap: int) -> bool:
    """Side by side on one text row: mostly the same height band, small gap."""
    overlap = min(a.y2, b.y2) - max(a.y, b.y)
    if overlap < 0.6 * min(a.h, b.h):
        return False
    return max(a.x, b.x) - min(a.x2, b.x2) <= gap


def stacked_in_a_block(a: Box, b: Box, gap: int, align: int) -> bool:
    """One above the other like lines of a paragraph: small vertical gap and
    sharing a left edge, a right edge or a centre line."""
    upper, lower = (a, b) if a.y <= b.y else (b, a)
    if lower.y - upper.y2 > gap:
        return False
    share = min(a.x2, b.x2) - max(a.x, b.x)
    if share < 0.5 * min(a.w, b.w):
        return False
    return (
        abs(a.x - b.x) <= align
        or abs(a.x2 - b.x2) <= align
        or abs((a.x + a.x2) - (b.x + b.x2)) <= 2 * align
    )


def text_regions(gray: np.ndarray) -> list[Box]:
    height, width = gray.shape
    gradient = cv2.morphologyEx(
        gray, cv2.MORPH_GRADIENT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    )
    _, strokes = cv2.threshold(gradient, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)

    # Join characters into words and lines: wide horizontal closing.
    kernel_width = max(9, int(width * 0.012))
    joined = cv2.morphologyEx(
        strokes, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_width, 3))
    )
    contours, _ = cv2.findContours(joined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    lines: list[Box] = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if h < 6 or w < 20 or h > height * 0.12 or w * h > width * height * 0.5:
            continue
        if w / h < 1.3:
            continue
        density = float(np.count_nonzero(strokes[y : y + h, x : x + w])) / (w * h)
        if density < 0.08:
            continue
        lines.append(Box(x, y, w, h, "text"))

    if not lines:
        return []
    typical_height = int(np.median([line.h for line in lines]))
    # Words on one row form a line; lines that stack and line up form a block.
    rows = merge_where(lines, lambda a, b: same_row(a, b, typical_height), "text")
    return merge_where(
        rows,
        lambda a, b: stacked_in_a_block(a, b, int(typical_height * STACK_GAP), 2 * typical_height),
        "text",
    )


def figure_regions(gray: np.ndarray, text: list[Box]) -> list[Box]:
    height, width = gray.shape
    edges = cv2.Canny(gray, 50, 150)
    size = max(9, int(width * 0.012))
    grown = cv2.dilate(
        edges, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size)), iterations=2
    )
    contours, _ = cv2.findContours(grown, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # The ground within reach of a line of text: edge growth joins neighbouring lines of
    # text into blobs that are not figures.
    near_text = np.zeros_like(gray)
    reach = 2 * size
    for t in text:
        cv2.rectangle(near_text, (t.x - reach, t.y - reach), (t.x2 + reach, t.y2 + reach), 255, -1)

    boxes: list[Box] = []
    image_area = width * height
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        box = Box(x, y, w, h, "figure")
        if box.area > image_area * 0.85 or box.area < image_area * SMALL_FIGURE:
            continue
        # Smaller than a figure usually is (icons, buttons are): only a line drawing, such as a
        # triangle in a video that is not full screen, is kept. And a drawing is kept even where
        # the text finder took it, with its labels, for a block of text: its structure says it is
        # a figure.
        drawing = box.area < image_area * 0.08 and looks_like_drawing(gray, box)
        if box.area < image_area * 0.015 and not drawing:
            continue
        if not drawing:
            if np.count_nonzero(near_text[y : y + h, x : x + w]) >= 0.85 * w * h:
                continue
            # An edge halo around text is not a figure: it holds a text region and
            # is not much bigger than it.
            if any(contained_fraction(t, box) > 0.8 and box.area < 3.5 * t.area for t in text):
                continue
            # Or it sits inside a text block (the halo of one line of a paragraph).
            if any(contained_fraction(box, t) > 0.7 for t in text):
                continue
        boxes.append(box)
    return boxes


def image_regions(gray: np.ndarray, known: list[Box]) -> list[Box]:
    """Photos and video of the real world (a presenter, a thumbnail): big areas with a lot of
    detail that are not text, a figure or a control. Nothing should be drawn on top of them, and
    the tutor can point at them as "the picture". Told from a flat background by the spread of
    brightness inside small cells.
    """
    height, width = gray.shape
    cell = max(16, width // 40)
    columns, rows = width // cell, height // cell
    if columns < 4 or rows < 4:
        return []
    small = cv2.resize(gray, (columns * cell, rows * cell), interpolation=cv2.INTER_AREA).astype(np.float32)
    mean = cv2.boxFilter(small, -1, (cell, cell))
    spread = np.sqrt(np.maximum(cv2.boxFilter(small * small, -1, (cell, cell)) - mean * mean, 0))
    # One value per cell, from the middle of each.
    centres = spread[cell // 2 :: cell, cell // 2 :: cell][:rows, :columns]
    # A photo has many in-between greys; text and line drawings are a background and strokes.
    mid = ((small >= 50) & (small <= 215)).astype(np.float32)
    middle = cv2.boxFilter(mid, -1, (cell, cell))[cell // 2 :: cell, cell // 2 :: cell][:rows, :columns]
    busy = ((centres >= 22) & (middle >= 0.15)).astype(np.uint8)
    # What is already known (text, figures, controls) is not a photo.
    scale_x, scale_y = columns * cell / width, rows * cell / height
    for box in known:
        if box.area > 0.25 * width * height:
            continue  # the frame of a video is not a reason to ignore what is inside it
        c0, r0 = int(box.x * scale_x // cell), int(box.y * scale_y // cell)
        c1, r1 = int(box.x2 * scale_x // cell) + 1, int(box.y2 * scale_y // cell) + 1
        busy[max(0, r0) : max(0, r1), max(0, c0) : max(0, c1)] = 0
    busy = cv2.morphologyEx(busy, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    busy = cv2.morphologyEx(busy, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(busy, connectivity=8)
    boxes = []
    for index in range(1, count):
        c, r, w, h, cells = stats[index]
        box = Box(
            int(c * cell / scale_x), int(r * cell / scale_y), int(w * cell / scale_x), int(h * cell / scale_y), "image"
        )
        share = box.area / (width * height)
        # Big, and mostly detail (not a few scattered cells).
        if 0.015 <= share <= 0.6 and cells >= 0.5 * w * h:
            boxes.append(box)
    boxes.sort(key=lambda b: b.area, reverse=True)
    return boxes[:4]


def control_regions(gray: np.ndarray) -> list[Box]:
    height, width = gray.shape
    edges = cv2.Canny(gray, 40, 120)
    closed = cv2.morphologyEx(
        edges, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    )
    contours, _ = cv2.findContours(closed, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    image_area = width * height
    boxes: list[Box] = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if h < 14 or w < 24 or w * h < image_area * 0.0004 or w * h > image_area * 0.06:
            continue
        aspect = w / h
        if not 1.2 <= aspect <= 12:
            continue
        contour_area = cv2.contourArea(contour)
        perimeter = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.03 * perimeter, True)
        # A control is a closed, roughly rectangular outline.
        if len(approx) != 4 or contour_area < 0.8 * w * h:
            continue
        boxes.append(Box(x, y, w, h, "control"))
    return boxes


def changed_regions(current_gray: np.ndarray, previous_gray: np.ndarray) -> list[Box]:
    height, width = current_gray.shape
    if previous_gray.shape != current_gray.shape:
        previous_gray = cv2.resize(previous_gray, (width, height), interpolation=cv2.INTER_AREA)
    difference = cv2.absdiff(current_gray, previous_gray)
    _, changed = cv2.threshold(difference, 25, 255, cv2.THRESH_BINARY)
    size = max(9, int(width * 0.012))
    grown = cv2.dilate(changed, cv2.getStructuringElement(cv2.MORPH_RECT, (size, size)), iterations=2)
    contours, _ = cv2.findContours(grown, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    boxes = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if w * h >= width * height * 0.003:
            boxes.append(Box(x, y, w, h, "changed"))
    return boxes


# --- finer parts inside figures: lines and labels --------------------------------

PART_KINDS = ("figure", "line", "label")
MAX_FIGURES_WITH_PARTS = 2
MAX_LINES_PER_FIGURE = 6
MAX_LABELS_PER_FIGURE = 12


def _direction(segment) -> tuple[float, float, float]:
    x1, y1, x2, y2 = segment
    length = math.hypot(x2 - x1, y2 - y1) or 1.0
    return (x2 - x1) / length, (y2 - y1) / length, length


def _can_merge_segments(a, b, angle_tolerance, distance_tolerance, gap_tolerance) -> bool:
    ax, ay, _ = _direction(a)
    bx, by, _ = _direction(b)
    cross = abs(ax * by - ay * bx)
    if math.asin(min(1.0, cross)) > angle_tolerance:
        return False
    # Perpendicular distance of b's midpoint from the line through a.
    mx, my = (b[0] + b[2]) / 2 - a[0], (b[1] + b[3]) / 2 - a[1]
    if abs(mx * ay - my * ax) > distance_tolerance:
        return False

    def project(x, y):
        return (x - a[0]) * ax + (y - a[1]) * ay

    a_low, a_high = sorted((project(a[0], a[1]), project(a[2], a[3])))
    b_low, b_high = sorted((project(b[0], b[1]), project(b[2], b[3])))
    return b_low <= a_high + gap_tolerance and a_low <= b_high + gap_tolerance


def merge_segments(segments, angle_tolerance=math.radians(5), distance_tolerance=10.0, gap_tolerance=20.0):
    """Merge segments that lie on one line (also the two edges of a thick stroke)."""
    pending = [tuple(float(v) for v in segment) for segment in segments]
    changed = True
    while changed:
        changed = False
        result = []
        while pending:
            current = pending.pop()
            index = 0
            while index < len(pending):
                other = pending[index]
                if _can_merge_segments(current, other, angle_tolerance, distance_tolerance, gap_tolerance):
                    ax, ay, _ = _direction(current)
                    points = [(current[0], current[1]), (current[2], current[3]), (other[0], other[1]), (other[2], other[3])]
                    points.sort(key=lambda point: point[0] * ax + point[1] * ay)
                    current = (*points[0], *points[-1])
                    pending.pop(index)
                    changed = True
                else:
                    index += 1
            result.append(current)
        pending = result
    return pending


def find_lines(gray: np.ndarray, figure: Box) -> list[Box]:
    crop = gray[figure.y : figure.y2, figure.x : figure.x2]
    height, width = crop.shape
    edges = cv2.Canny(crop, 40, 120)
    minimum = max(30, int(0.18 * min(width, height)))
    found = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=30, minLineLength=minimum, maxLineGap=10)
    if found is None:
        return []
    merged = merge_segments([tuple(row) for row in np.asarray(found).reshape(-1, 4)])
    merged = [segment for segment in merged if _direction(segment)[2] >= minimum]
    merged.sort(key=lambda segment: _direction(segment)[2], reverse=True)

    boxes = []
    for x1, y1, x2, y2 in merged[:MAX_LINES_PER_FIGURE]:
        ax, ay = int(round(x1)) + figure.x, int(round(y1)) + figure.y
        bx, by = int(round(x2)) + figure.x, int(round(y2)) + figure.y
        boxes.append(
            Box(min(ax, bx), min(ay, by), max(abs(bx - ax), 6), max(abs(by - ay), 6), "line", line=(ax, ay, bx, by))
        )
    return boxes


def _slanted(segment) -> bool:
    dx, dy, _ = _direction(segment)
    return 12 <= math.degrees(math.atan2(abs(dy), abs(dx))) <= 78


def _meet(a, b, reach: float) -> bool:
    """Two segments touch: an end of one near an end of the other, or resting on the other."""
    ends_a = [(a[0], a[1]), (a[2], a[3])]
    ends_b = [(b[0], b[1]), (b[2], b[3])]
    if any(math.hypot(p[0] - q[0], p[1] - q[1]) <= reach for p in ends_a for q in ends_b):
        return True
    for points, other in ((ends_a, b), (ends_b, a)):
        ox, oy, length = _direction(other)
        for px, py in points:
            along = (px - other[0]) * ox + (py - other[1]) * oy
            if 0 <= along <= length and abs((px - other[0]) * oy - (py - other[1]) * ox) <= reach:
                return True
    return False


def looks_like_drawing(gray: np.ndarray, box: Box) -> bool:
    """Is this small group of edges a line drawing (a triangle, a graph) and not an icon or some
    text? It has at least three long straight segments that meet, one of them slanted (the frames
    of an interface are only horizontal and vertical), and together they fill the box."""
    crop = gray[box.y : box.y2, box.x : box.x2]
    height, width = crop.shape
    longest = max(width, height)
    minimum = max(24, int(0.3 * longest))
    edges = cv2.Canny(crop, 40, 120)
    found = cv2.HoughLinesP(
        edges, 1, np.pi / 180, threshold=max(18, int(0.2 * longest)), minLineLength=minimum, maxLineGap=8
    )
    if found is None:
        return False
    segments = [
        seg
        for seg in merge_segments([tuple(row) for row in np.asarray(found).reshape(-1, 4)])
        if _direction(seg)[2] >= minimum
    ]
    if len(segments) < 3:
        return False
    reach = max(8.0, 0.08 * longest)
    group = list(range(len(segments)))

    def root(i: int) -> int:
        while group[i] != i:
            group[i] = group[group[i]]
            i = group[i]
        return i

    for i in range(len(segments)):
        for j in range(i + 1, len(segments)):
            if _meet(segments[i], segments[j], reach):
                group[root(i)] = root(j)
    members: dict[int, list] = {}
    for i, seg in enumerate(segments):
        members.setdefault(root(i), []).append(seg)
    for connected in members.values():
        if len(connected) < 3 or not any(_slanted(seg) for seg in connected):
            continue
        xs = [v for seg in connected for v in (seg[0], seg[2])]
        ys = [v for seg in connected for v in (seg[1], seg[3])]
        if (max(xs) - min(xs)) >= 0.55 * width and (max(ys) - min(ys)) >= 0.4 * height:
            return True
    return False


def closed_shape_regions(gray: np.ndarray, text: list[Box]) -> list[Box]:
    """Closed shapes drawn with straight lines (a triangle, a quadrilateral) anywhere on the screen.

    The blob finder in `figure_regions` joins strokes that are close together, so on a busy picture
    (a presenter next to the drawing, a title above it, a bright frame) a small drawing merges with
    everything around it and is lost. This looks at the straight segments themselves: a shape is
    three or four segments whose ends meet in a ring, at least one of them slanted (the frames of
    an interface are only horizontal and vertical). Its bounding box becomes a figure.
    """
    height, width = gray.shape
    edges = cv2.Canny(gray, 40, 120)
    minimum = max(30, int(0.03 * width))
    # Tolerant settings: compression breaks a thin stroke into pieces with gaps between them.
    found = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=max(20, int(0.6 * minimum)), minLineLength=minimum // 2, maxLineGap=10)
    if found is None:
        return []
    segments = []
    for seg in merge_segments([tuple(row) for row in np.asarray(found).reshape(-1, 4)], gap_tolerance=0.04 * width):
        dx, dy, length = _direction(seg)
        if length < minimum or length > 0.6 * width:
            continue
        box = Box(int(min(seg[0], seg[2])), int(min(seg[1], seg[3])), max(1, int(abs(seg[2] - seg[0]))), max(1, int(abs(seg[3] - seg[1]))), "line")
        if any(contained_fraction(box, t) > 0.8 for t in text):
            continue
        segments.append(seg)
    if len(segments) < 3:
        return []

    # Ends that are close are one corner.
    reach = max(6.0, 0.008 * width)
    ends = [(seg[0], seg[1]) for seg in segments] + [(seg[2], seg[3]) for seg in segments]
    corner = list(range(len(ends)))

    def root(i: int) -> int:
        while corner[i] != i:
            corner[i] = corner[corner[i]]
            i = corner[i]
        return i

    for i in range(len(ends)):
        for j in range(i + 1, len(ends)):
            if math.hypot(ends[i][0] - ends[j][0], ends[i][1] - ends[j][1]) <= reach:
                corner[root(i)] = root(j)
    count = len(segments)
    adjacent: dict[int, list[tuple[int, int]]] = {}
    for k in range(count):
        a, b = root(k), root(k + count)
        if a == b:
            continue
        adjacent.setdefault(a, []).append((b, k))
        adjacent.setdefault(b, []).append((a, k))

    rings: set[frozenset[int]] = set()

    def walk(start: int, at: int, corners: list[int], used: list[int]) -> None:
        for other, k in adjacent.get(at, []):
            if k in used:
                continue
            if other == start and len(used) + 1 >= 3:
                rings.add(frozenset([*used, k]))
                continue
            if other in corners or len(used) + 1 >= 4:
                continue
            walk(start, other, [*corners, other], [*used, k])

    for start in list(adjacent):
        walk(start, start, [start], [])

    boxes: list[Box] = []
    for ring in rings:
        sides = [segments[k] for k in ring]
        if not any(_slanted(side) for side in sides):
            continue
        xs = [v for side in sides for v in (side[0], side[2])]
        ys = [v for side in sides for v in (side[1], side[3])]
        margin = 12
        x1, y1 = max(0, int(min(xs)) - margin), max(0, int(min(ys)) - margin)
        x2, y2 = min(width, int(max(xs)) + margin), min(height, int(max(ys)) + margin)
        box = Box(x1, y1, x2 - x1, y2 - y1, "figure")
        if 0.0008 * width * height <= box.area <= 0.25 * width * height:
            boxes.append(box)
    boxes.sort(key=lambda b: b.area, reverse=True)
    kept: list[Box] = []
    for box in boxes:
        if not any(iou(box, other) > 0.5 or contained_fraction(box, other) > 0.8 for other in kept):
            kept.append(box)
    return kept[:MAX_SHAPES]


MAX_SHAPES = 3


def find_labels(gray: np.ndarray, figure: Box, lines: list[Box]) -> list[Box]:
    """Small glyph-like blobs inside a figure. Lines are erased first so a label
    touching a line is not swallowed by it."""
    crop = gray[figure.y : figure.y2, figure.x : figure.x2]
    height, width = crop.shape
    mask = cv2.Canny(crop, 40, 120)
    for line in lines:
        x1, y1, x2, y2 = line.line
        cv2.line(mask, (x1 - figure.x, y1 - figure.y), (x2 - figure.x, y2 - figure.y), 0, 11)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # A small figure has small labels.
    min_glyph = max(7, min(12, int(0.12 * height)))
    glyphs = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if h < min_glyph or w < 4 or h > 0.3 * height or w > 0.4 * width:
            continue
        if not 0.15 <= w / h <= 6:
            continue
        glyphs.append(Box(x + figure.x, y + figure.y, w, h, "label"))

    # The digits of one number sit side by side.
    joined = merge_where(glyphs, lambda a, b: same_row(a, b, int(0.8 * max(a.h, b.h))), "label")
    joined = [box for box in joined if box.area >= 50]
    joined.sort(key=lambda box: box.area, reverse=True)
    return joined[:MAX_LABELS_PER_FIGURE]


def drop_duplicates(boxes: list[Box], threshold: float = 0.6) -> list[Box]:
    """Within one kind, keep the larger of any two boxes that mostly overlap."""
    kept: list[Box] = []
    for box in sorted(boxes, key=lambda b: b.area, reverse=True):
        if any(k.kind == box.kind and iou(k, box) > threshold for k in kept):
            continue
        kept.append(box)
    return kept


def drop_redundant(boxes: list[Box]) -> list[Box]:
    """Remove boxes that another kind already represents better.

    - Text mostly covered by controls is the controls' own label.
    - A figure or control that is the same area as a changed region is kept only
      as the changed region, which carries the extra meaning.
    """
    controls = [b for b in boxes if b.kind == "control"]
    changed = [b for b in boxes if b.kind == "changed"]
    labels = [b for b in boxes if b.kind == "label"]
    kept = []
    for box in boxes:
        if box.kind == "text":
            covered = sum(intersection(box, c) for c in controls)
            if covered / box.area > 0.8:
                continue
            if any(iou(box, label) > 0.4 for label in labels):
                continue
        if box.kind in ("figure", "control") and any(iou(box, c) > 0.6 for c in changed):
            continue
        kept.append(box)
    return kept


def reading_order(boxes: list[Box], height: int) -> list[Box]:
    band = max(1, int(height * 0.03))
    return sorted(boxes, key=lambda b: (b.y // band, b.x, b.y))


def region_signature(gray: np.ndarray, box: Box) -> str:
    """A 64-bit difference hash (hex) of the pixels inside the box."""
    crop = gray[max(box.y, 0) : box.y2, max(box.x, 0) : box.x2]
    if crop.size == 0:
        return "0" * 16
    small = cv2.resize(crop, (9, 8), interpolation=cv2.INTER_AREA)
    bits = (small[:, 1:] > small[:, :-1]).flatten()
    value = 0
    for index, bit in enumerate(bits):
        if bit:
            value |= 1 << index
    return f"{value:016x}"


# Regions that only say "something is here" (for placing drawings in empty space): not shown to the
# model and not drawn.
HIDDEN_KINDS = ("detail", "ink")


def occupancy_regions(image_png: bytes, capture: CaptureMeta, first_id: int) -> list[Region]:
    """Where the picture has detail of any kind (text, handwriting, edges, photos) as rectangles of
    kind "detail", so a drawing that needs room (a diagram) can be put on flat background and not
    on the title of a video or a person's face. They are found from the pixels, not from the other
    regions, because not everything on a screen is a region (handwriting, a browser bar)."""
    image = decode_image(image_png)
    if image is None:
        return []
    source_height, source_width = image.shape[:2]
    scale = min(1.0, DETECTION_WIDTH / source_width)
    if scale < 1.0:
        image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float32)
    height, width = gray.shape
    cell = 24
    columns, rows = width // cell, height // cell
    if columns < 4 or rows < 4:
        return []
    cut = gray[: rows * cell, : columns * cell]
    mean = cv2.boxFilter(cut, -1, (cell, cell))
    spread = np.sqrt(np.maximum(cv2.boxFilter(cut * cut, -1, (cell, cell)) - mean * mean, 0))
    busy = spread[cell // 2 :: cell, cell // 2 :: cell][:rows, :columns] >= 10
    # A cell next to a busy one is close to something: keep a little clear space around everything.
    grown = cv2.dilate(busy.astype(np.uint8), np.ones((3, 3), np.uint8))

    # Runs of busy cells along each row, then joined down the rows when they line up.
    runs: list[list[int]] = []  # [first column, last column, first row, last row]
    open_runs: dict[tuple[int, int], list[int]] = {}
    for r in range(rows):
        seen: dict[tuple[int, int], list[int]] = {}
        c = 0
        while c < columns:
            if grown[r, c]:
                start = c
                while c + 1 < columns and grown[r, c + 1]:
                    c += 1
                key = (start, c)
                run = open_runs.get(key)
                if run is not None and run[3] == r - 1:
                    run[3] = r
                    seen[key] = run
                else:
                    run = [start, c, r, r]
                    runs.append(run)
                    seen[key] = run
            c += 1
        open_runs = seen
    runs.sort(key=lambda run: -((run[1] - run[0] + 1) * (run[3] - run[2] + 1)))
    to_x = capture.width / (columns * cell)
    to_y = capture.height / (rows * cell)
    regions: list[Region] = []
    for run in runs[:120]:
        x, y = int(run[0] * cell * to_x), int(run[2] * cell * to_y)
        w, h = int((run[1] - run[0] + 1) * cell * to_x), int((run[3] - run[2] + 1) * cell * to_y)
        regions.append(
            Region(id=first_id + len(regions), bbox=BBox(x=x, y=y, w=max(1, w), h=max(1, h)), kind="detail")
        )
    return regions


def ink_regions(image_png: bytes, capture: CaptureMeta, known: list[Region], first_id: int) -> list[Region]:
    """Small marks the other regions do not cover (a handwritten digit, a symbol, a logo) as
    tight rectangles of kind "ink". A caption can then keep off the thing it labels, which the
    coarse "detail" rectangles are too wide to say."""
    image = decode_image(image_png)
    if image is None:
        return []
    scale = min(1.0, DETECTION_WIDTH / image.shape[1])
    if scale < 1.0:
        image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape
    local = cv2.absdiff(gray, cv2.GaussianBlur(gray, (0, 0), 6))
    mask = (local > 28).astype(np.uint8)
    mask = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    count, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    to_x = capture.width / width
    to_y = capture.height / height
    covering = [r for r in known if r.kind in ("text", "control", "label", "line")]
    found: list[tuple[int, BBox]] = []
    for index in range(1, count):
        x, y, w, h, area = (int(v) for v in stats[index])
        if area < 30 or w * h > 0.06 * width * height:
            continue
        box = BBox(x=int(x * to_x), y=int(y * to_y), w=max(1, int(w * to_x)), h=max(1, int(h * to_y)))
        # Already something the proposer knows about: nothing to add.
        if any(_overlap_area(box, r.bbox) > 0.6 * box.w * box.h for r in covering):
            continue
        found.append((box.w * box.h, box))
    found.sort(key=lambda item: -item[0])
    return [
        Region(id=first_id + i, bbox=box, kind="ink") for i, (_, box) in enumerate(found[:150])
    ]


def _overlap_area(a: BBox, b: BBox) -> int:
    w = min(a.x + a.w, b.x + b.w) - max(a.x, b.x)
    h = min(a.y + a.h, b.y + b.h) - max(a.y, b.y)
    return w * h if w > 0 and h > 0 else 0


def max_regions_setting() -> int:
    try:
        return max(1, int(os.environ.get("MAX_REGIONS", DEFAULT_MAX_REGIONS)))
    except ValueError:
        return DEFAULT_MAX_REGIONS


def propose_regions(
    image_png: bytes,
    capture: CaptureMeta,
    previous_png: bytes | None = None,
    max_regions: int | None = None,
) -> list[Region]:
    """Return the whole-capture region (id 0) plus numbered candidate regions.

    Boxes are in capture pixels. Detected regions are numbered from 1 in
    reading order (top to bottom, then left to right). `previous_png`, when
    given, adds regions for areas that changed since that earlier capture.
    """
    cap = max_regions if max_regions is not None else max_regions_setting()
    screen = Region(
        id=0, bbox=BBox(x=0, y=0, w=capture.width, h=capture.height), kind="screen"
    )

    image = decode_image(image_png)
    if image is None:
        return [screen]

    source_height, source_width = image.shape[:2]
    scale = min(1.0, DETECTION_WIDTH / source_width)
    if scale < 1.0:
        image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape

    text = text_regions(gray)
    figures = figure_regions(gray, text)
    # Closed line shapes that the blob finder lost to their surroundings.
    # (A figure that is most of the screen, such as the frame of a video, does not make a shape
    # inside it a duplicate.)
    for shape in closed_shape_regions(gray, text):
        smaller = [f for f in figures if f.area < 0.25 * width * height]
        if not any(iou(shape, f) > 0.3 or contained_fraction(shape, f) > 0.6 for f in smaller):
            figures.append(shape)
    controls = control_regions(gray)
    boxes = text + figures + controls + image_regions(gray, text + figures + controls)
    # Drawings first: the strips of an interface (a browser bar) can be bigger than a small
    # triangle but have no sides worth pointing at.
    image_area = width * height
    drawings = {id(f) for f in figures if f.area < image_area * 0.25 and looks_like_drawing(gray, f)}
    for figure in sorted(figures, key=lambda b: (id(b) not in drawings, -b.area))[:MAX_FIGURES_WITH_PARTS]:
        lines = find_lines(gray, figure)
        boxes += lines + find_labels(gray, figure, lines)
    if previous_png is not None:
        previous = decode_image(previous_png)
        if previous is not None:
            if scale < 1.0:
                previous = cv2.resize(previous, (width, height), interpolation=cv2.INTER_AREA)
            boxes += changed_regions(gray, cv2.cvtColor(previous, cv2.COLOR_BGR2GRAY))

    boxes = drop_redundant(drop_duplicates(boxes))

    # Keep the largest when over the cap, then number in reading order.
    # Figures and their parts first: they are what the learner usually points at.
    boxes = sorted(boxes, key=lambda b: (b.kind not in PART_KINDS, -b.area))[:cap]

    # Excluded areas are normally blacked out by the client; also never propose
    # a region whose centre lies inside one.
    to_capture_x = capture.width / width
    to_capture_y = capture.height / height

    def excluded(box: Box) -> bool:
        cx = (box.x + box.w / 2) * to_capture_x
        cy = (box.y + box.h / 2) * to_capture_y
        return any(
            e.x <= cx <= e.x + e.w and e.y <= cy <= e.y + e.h for e in capture.excluded
        )

    boxes = [b for b in boxes if not excluded(b)]

    regions = [screen]
    for number, box in enumerate(reading_order(boxes, height), start=1):
        x = int(round(box.x * to_capture_x))
        y = int(round(box.y * to_capture_y))
        x2 = min(capture.width, int(round(box.x2 * to_capture_x)))
        y2 = min(capture.height, int(round(box.y2 * to_capture_y)))
        line = None
        if box.line is not None:
            line = [
                int(round(box.line[0] * to_capture_x)),
                int(round(box.line[1] * to_capture_y)),
                int(round(box.line[2] * to_capture_x)),
                int(round(box.line[3] * to_capture_y)),
            ]
        regions.append(
            Region(
                id=number,
                bbox=BBox(x=x, y=y, w=max(1, x2 - x), h=max(1, y2 - y)),
                kind=box.kind,
                line=line,
                signature=region_signature(gray, box),
            )
        )
    return regions
