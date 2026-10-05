// Overlay renderer (seam 2): a pure function from canvas state to SVG.
//
// The SVG viewBox is the capture size in pixels, so every shape is computed in
// capture pixels and the browser scales the whole picture to the window. That
// keeps drawings correct at any display scale or resolution.

import type { Canvas, Region, Shape } from "../contract";
import { centroid, squareCorners, type Line } from "./geometry";
import { escapeXml, formatMath, plainMath } from "./math";
import {
  arrowTail,
  boxOf,
  measurePill,
  obstaclesOf,
  segmentBoxes,
  softObstaclesOf,
  pillCandidates,
  Placer,
  viewOf,
  type Box,
} from "./place";

export interface View {
  width: number;
  height: number;
}

interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

const DEFAULT_COLOR = "#ff3b30";
const DEFAULT_STROKE = 4;
const FONT = 'font-family="Segoe UI, sans-serif"';

function num(value: number): string {
  return String(Math.round(value * 100) / 100);
}

// The point of a region closest to `from`: for a line, the nearest point on the
// segment; for anything else, the nearest point of its box.
export function nearestPoint(region: Region, from: { x: number; y: number }): { x: number; y: number } {
  if (region.line && region.line.length === 4) {
    const [x1, y1, x2, y2] = region.line as [number, number, number, number];
    const dx = x2 - x1;
    const dy = y2 - y1;
    const lengthSquared = dx * dx + dy * dy || 1;
    const t = Math.max(0, Math.min(1, ((from.x - x1) * dx + (from.y - y1) * dy) / lengthSquared));
    return { x: x1 + t * dx, y: y1 + t * dy };
  }
  const { x, y, w, h } = region.bbox;
  return {
    x: Math.max(x, Math.min(from.x, x + w)),
    y: Math.max(y, Math.min(from.y, y + h)),
  };
}

// Anchor rectangle (relative to a region) to capture pixels.
export function resolveRect(shape: Shape, regions: Region[]): Rect | null {
  const region = regions.find((r) => r.id === shape.anchor.region_id);
  if (!region) return null;
  const { bbox } = region;
  const a = shape.anchor;
  return {
    x: bbox.x + a.x * bbox.w,
    y: bbox.y + a.y * bbox.h,
    w: a.w * bbox.w,
    h: a.h * bbox.h,
  };
}

export type Pt = { x: number; y: number };

// Where an arrow starts and ends in capture pixels: the tail is the anchor's x and
// y; the head is on the target region when there is one, else at `end` (relative
// to the region), else the far corner of the anchor rectangle.
export function arrowEnds(shape: Shape, regions: Region[]): { tail: Pt; head: Pt } | null {
  const region = regions.find((r) => r.id === shape.anchor.region_id);
  if (!region) return null;
  const { bbox } = region;
  const a = shape.anchor;
  const target =
    shape.target_region_id != null ? regions.find((r) => r.id === shape.target_region_id) : undefined;
  if (target) {
    // Pointing at a region: the tail goes in free space close to it (the model's own
    // tail is ignored), so the arrow is short and crosses nothing.
    const targetBox = boxOf(target);
    const caption = shape.text ? measurePill(shape.text) : null;
    const tail = arrowTail(targetBox, obstaclesOf(regions, [targetBox]), viewOf(regions), caption);
    return { tail, head: nearestPoint(target, tail) };
  }
  const tail = { x: bbox.x + a.x * bbox.w, y: bbox.y + a.y * bbox.h };
  const head = shape.end
    ? { x: bbox.x + shape.end.x * bbox.w, y: bbox.y + shape.end.y * bbox.h }
    : { x: tail.x + a.w * bbox.w, y: tail.y + a.h * bbox.h };
  return { tail, head };
}

// A filled triangle at the end of an arrow. It is a shape of its own (not an SVG
// marker) so the animation can show it when the line has been drawn.
function arrowHead(tail: Pt, head: Pt, color: string): string {
  const dx = head.x - tail.x;
  const dy = head.y - tail.y;
  const length = Math.hypot(dx, dy) || 1;
  const ux = dx / length;
  const uy = dy / length;
  const size = 18;
  const half = 9;
  const bx = head.x - ux * size;
  const by = head.y - uy * size;
  const points = `${num(head.x)},${num(head.y)} ${num(bx - uy * half)},${num(by + ux * half)} ${num(bx + uy * half)},${num(by - ux * half)}`;
  return `<polygon data-part="head" points="${points}" fill="${color}" style="transform-box:fill-box;transform-origin:center"/>`;
}

// Boxes and ellipses on a label get a little room so they surround it.
function around(rect: Rect, shape: Shape, regions: Region[]): Rect {
  const region = regions.find((r) => r.id === shape.anchor.region_id);
  if (region?.kind !== "label" && region?.kind !== "text") return rect;
  const pad = region.kind === "label" ? 6 : 5;
  return { x: rect.x - pad, y: rect.y - pad, w: rect.w + 2 * pad, h: rect.h + 2 * pad };
}

// A caption in a dark pill with the shape's colour as its outline, at a box chosen by
// the placer.
function pill(text: string | null | undefined, box: Box, color: string): string {
  if (!text) return "";
  const size = measurePill(text);
  const lines = size.lines
    .map(
      (line, index) =>
        `<text x="${num(box.x + 12)}" y="${num(box.y + 7 + 18 + index * 24)}" fill="#fff" font-size="18" ${FONT} font-weight="600">${formatMath(line)}</text>`,
    )
    .join("");
  return `<g data-part="pill"><rect x="${num(box.x)}" y="${num(box.y)}" width="${num(box.w)}" height="${num(box.h)}" rx="9" fill="rgba(20,20,24,0.92)" stroke="${color}" stroke-width="2"/>${lines}</g>`;
}

// A pill beside a box (or a point): the placer picks the first clear spot.
function pillBeside(text: string | null | undefined, target: Box, color: string, placer: Placer): string {
  if (!text) return "";
  const size = measurePill(text);
  return pill(text, placer.place(size, pillCandidates(target, size)), color);
}

// A pill beside the middle of a line, on whichever side is free.
function pillBesideLine(text: string | null | undefined, line: Line, color: string, placer: Placer): string {
  if (!text) return "";
  const size = measurePill(text);
  const mx = (line[0] + line[2]) / 2;
  const my = (line[1] + line[3]) / 2;
  const length = Math.hypot(line[2] - line[0], line[3] - line[1]) || 1;
  const nx = (line[3] - line[1]) / length;
  const ny = -(line[2] - line[0]) / length;
  // Out along the normal far enough to clear the stroke, on either side.
  const distance = (size.w / 2) * Math.abs(nx) + (size.h / 2) * Math.abs(ny) + 22;
  const dx = (line[2] - line[0]) / length;
  const dy = (line[3] - line[1]) / length;
  // Beside the middle first, then slid along the line, then further out: whichever side is free.
  const at = (side: number, along: number, extra: number) => ({
    x: mx + dx * along + side * nx * (distance + extra) - size.w / 2,
    y: my + dy * along + side * ny * (distance + extra) - size.h / 2,
  });
  const slides = [0, -0.3, 0.3, -0.45, 0.45].map((t) => t * length);
  const candidates = [0, 30].flatMap((extra) => slides.flatMap((along) => [at(1, along, extra), at(-1, along, extra)]));
  return pill(text, placer.place(size, candidates), color);
}

// A pill at the tail of an arrow, on the side away from the head.
function pillAtTail(text: string | null | undefined, tail: Pt, head: Pt, color: string, placer: Placer): string {
  if (!text) return "";
  const size = measurePill(text);
  const away = { x: tail.x - head.x, y: tail.y - head.y };
  const norm = Math.hypot(away.x, away.y) || 1;
  const score = (c: { x: number; y: number }) =>
    ((c.x + size.w / 2 - tail.x) * away.x + (c.y + size.h / 2 - tail.y) * away.y) / norm;
  // Close spots first (best the one on the far side of the tail), then further out.
  const all = pillCandidates({ x: tail.x, y: tail.y, w: 0, h: 0 }, size, 6);
  const tier = all.length / 3;
  const candidates = [0, 1, 2].flatMap((t) => all.slice(t * tier, (t + 1) * tier).sort((p, q) => score(q) - score(p)));
  return pill(text, placer.place(size, candidates), color);
}

// Text centred in a shape, white with a dark outline so it reads on any fill.
function centredText(text: string | null | undefined, cx: number, cy: number): string {
  if (!text) return "";
  return `<text x="${num(cx)}" y="${num(cy + 8)}" text-anchor="middle" fill="#fff" font-size="24" ${FONT} font-weight="700" paint-order="stroke" stroke="#000" stroke-width="4">${formatMath(text)}</text>`;
}

function renderShape(
  shape: Shape,
  rect: Rect,
  rects: Map<string, Rect>,
  regions: Region[],
  view: View,
  placer: Placer,
): string {
  const color = escapeXml(shape.style?.color ?? DEFAULT_COLOR);
  const stroke = shape.style?.stroke_width ?? DEFAULT_STROKE;
  const id = `data-shape-id="${escapeXml(shape.id)}" data-kind="${shape.kind}"`;
  const region = regions.find((r) => r.id === shape.anchor.region_id);

  switch (shape.kind) {
    case "box": {
      const r = around(rect, shape, regions);
      return `<g ${id}><rect x="${num(r.x)}" y="${num(r.y)}" width="${num(r.w)}" height="${num(r.h)}" fill="none" stroke="${color}" stroke-width="${stroke}" rx="6"/>${pillBeside(shape.text, r, color, placer)}</g>`;
    }
    case "ellipse": {
      const r = around(rect, shape, regions);
      return `<g ${id}><ellipse cx="${num(r.x + r.w / 2)}" cy="${num(r.y + r.h / 2)}" rx="${num(r.w / 2)}" ry="${num(r.h / 2)}" fill="none" stroke="${color}" stroke-width="${stroke}"/>${pillBeside(shape.text, r, color, placer)}</g>`;
    }
    case "highlight": {
      // On a line region the highlight is a thick stroke along the line itself.
      const line = region?.line;
      if (line && line.length === 4) {
        return `<g ${id}><line x1="${num(line[0] as number)}" y1="${num(line[1] as number)}" x2="${num(line[2] as number)}" y2="${num(line[3] as number)}" stroke="${color}" stroke-opacity="0.5" stroke-width="14" stroke-linecap="round"/>${pillBesideLine(shape.text, line as unknown as Line, color, placer)}</g>`;
      }
      return `<g ${id}><rect x="${num(rect.x)}" y="${num(rect.y)}" width="${num(rect.w)}" height="${num(rect.h)}" fill="${color}" fill-opacity="0.3" stroke="none"/>${pillBeside(shape.text, rect, color, placer)}</g>`;
    }
    case "arrow": {
      const ends = arrowEnds(shape, regions);
      if (!ends) return "";
      return `<g ${id}><line x1="${num(ends.tail.x)}" y1="${num(ends.tail.y)}" x2="${num(ends.head.x)}" y2="${num(ends.head.y)}" stroke="${color}" stroke-width="${stroke}" stroke-linecap="round"/>${arrowHead(ends.tail, ends.head, color)}${pillAtTail(shape.text, ends.tail, ends.head, color, placer)}</g>`;
    }
    case "label":
      return `<g ${id}>${pillBeside(shape.text, { x: rect.x, y: rect.y, w: 1, h: 1 }, color, placer)}</g>`;
    case "step_number": {
      const r = 18;
      const cx = rect.x + r;
      const cy = rect.y + r;
      return `<g ${id}><circle cx="${num(cx)}" cy="${num(cy)}" r="${r}" fill="${color}"/><text x="${num(cx)}" y="${num(cy + 7)}" text-anchor="middle" fill="#fff" font-size="20" ${FONT} font-weight="700">${escapeXml(shape.text ?? "")}</text></g>`;
    }
    case "connector": {
      const from = shape.from_id ? rects.get(shape.from_id) : undefined;
      const to = shape.to_id ? rects.get(shape.to_id) : undefined;
      if (!from || !to) return "";
      const tail = { x: from.x + from.w / 2, y: from.y + from.h / 2 };
      const head = { x: to.x + to.w / 2, y: to.y + to.h / 2 };
      return `<g ${id}><line x1="${num(tail.x)}" y1="${num(tail.y)}" x2="${num(head.x)}" y2="${num(head.y)}" stroke="${color}" stroke-width="${stroke}" stroke-linecap="round"/>${arrowHead(tail, head, color)}</g>`;
    }
    case "square_on_line": {
      // A new square built on a line region, sized and placed from the line itself.
      if (!region?.line || region.line.length !== 4) return "";
      const corners = squareCorners(region.line as unknown as Line, shape.side ?? "left", shape.scale ?? 1);
      const points = corners.map((p) => `${num(p.x)},${num(p.y)}`).join(" ");
      const middle = centroid(corners);
      return `<g ${id}><polygon points="${points}" fill="${color}" fill-opacity="0.25" stroke="${color}" stroke-width="${stroke}" stroke-linejoin="round"/>${centredText(shape.text, middle.x, middle.y)}</g>`;
    }
    case "polygon": {
      if (!region || !shape.points || shape.points.length < 3) return "";
      const corners = shape.points.map((p) => ({
        x: region.bbox.x + p.x * region.bbox.w,
        y: region.bbox.y + p.y * region.bbox.h,
      }));
      const points = corners.map((p) => `${num(p.x)},${num(p.y)}`).join(" ");
      const middle = centroid(corners);
      return `<g ${id}><polygon points="${points}" fill="${color}" fill-opacity="0.25" stroke="${color}" stroke-width="${stroke}" stroke-linejoin="round"/>${centredText(shape.text, middle.x, middle.y)}</g>`;
    }
    case "equation": {
      if (!shape.text) return "";
      // A dark rounded box sized to the text, kept inside the picture.
      const fontSize = 26;
      const width = Math.ceil(plainMath(shape.text).length * fontSize * 0.6) + 24;
      const height = fontSize + 18;
      const x = Math.max(8, Math.min(rect.x, view.width - width - 8));
      const y = Math.max(8, Math.min(rect.y, view.height - height - 8));
      return `<g ${id}><rect x="${num(x)}" y="${num(y)}" width="${width}" height="${height}" rx="10" fill="rgba(20,20,24,0.88)" stroke="${color}" stroke-width="2"/><text x="${num(x + 12)}" y="${num(y + height / 2 + 9)}" fill="#fff" font-size="${fontSize}" ${FONT} font-weight="600">${formatMath(shape.text)}</text></g>`;
    }
  }
}

function boundsOf(points: { x: number; y: number }[]): Box {
  const xs = points.map((p) => p.x);
  const ys = points.map((p) => p.y);
  return { x: Math.min(...xs), y: Math.min(...ys), w: Math.max(...xs) - Math.min(...xs), h: Math.max(...ys) - Math.min(...ys) };
}

// The room a shape fills on the screen, when it is a solid one (what a pill must not cover).
function solidBounds(shape: Shape, rect: Rect, regions: Region[], view: View): Box | undefined {
  const region = regions.find((r) => r.id === shape.anchor.region_id);
  switch (shape.kind) {
    case "box":
    case "ellipse":
      return around(rect, shape, regions);
    case "highlight":
      return region?.line ? undefined : rect;
    case "square_on_line":
      return region?.line
        ? boundsOf(squareCorners(region.line as unknown as Line, shape.side ?? "left", shape.scale ?? 1))
        : undefined;
    case "polygon":
      return region && shape.points && shape.points.length >= 3
        ? boundsOf(shape.points.map((p) => ({ x: region.bbox.x + p.x * region.bbox.w, y: region.bbox.y + p.y * region.bbox.h })))
        : undefined;
    case "equation": {
      if (!shape.text) return undefined;
      const width = Math.ceil(plainMath(shape.text).length * 26 * 0.6) + 24;
      const height = 26 + 18;
      return {
        x: Math.max(8, Math.min(rect.x, view.width - width - 8)),
        y: Math.max(8, Math.min(rect.y, view.height - height - 8)),
        w: width,
        h: height,
      };
    }
    default:
      return undefined;
  }
}

function thinBounds(shape: Shape, regions: Region[]): Box[] | undefined {
  if (shape.kind === "arrow") {
    const ends = arrowEnds(shape, regions);
    return ends ? segmentBoxes(ends.tail, ends.head) : undefined;
  }
  const region = regions.find((r) => r.id === shape.anchor.region_id);
  if (shape.kind === "highlight" && region?.line) {
    const [x1, y1, x2, y2] = region.line as [number, number, number, number];
    return segmentBoxes({ x: x1, y: y1 }, { x: x2, y: y2 });
  }
  return undefined;
}

export function renderCanvasSvg(canvas: Canvas, regions: Region[], view: View): string {
  const rects = new Map<string, Rect>();
  for (const shape of canvas.shapes) {
    const rect = resolveRect(shape, regions);
    if (rect) rects.set(shape.id, rect);
  }

  // Pills and arrow tails keep clear of the text on the screen and of each other; the
  // room that solid shapes take is reserved first.
  const placer = new Placer(view, obstaclesOf(regions), softObstaclesOf(regions));
  for (const shape of canvas.shapes) {
    const rect = rects.get(shape.id);
    const bounds = rect ? solidBounds(shape, rect, regions, view) : undefined;
    if (bounds) placer.reserve(bounds);
  }

  const body = canvas.shapes
    .map((shape) => {
      const rect = rects.get(shape.id);
      if (!rect) return "";
      const svg = renderShape(shape, rect, rects, regions, view, placer);
      // An arrow or a line highlight is thin: its room is taken once its pill is placed.
      const thin = thinBounds(shape, regions);
      for (const part of thin ?? []) placer.reserve(part);
      return svg;
    })
    .join("");

  return (
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${view.width} ${view.height}" width="100%" height="100%" preserveAspectRatio="none">` +
    body +
    `</svg>`
  );
}

// A quick "scan": the detected regions outlined one after another, each fading in
// and out (the page's CSS gives .st-scan its animation). Shown while the model is
// still thinking, so the learner sees the screen being read straight away.
export function renderScanSvg(regions: Region[], view: View): string {
  const shown = regions.filter((r) => r.kind !== "screen" && r.kind !== "detail" && r.kind !== "ink");
  const step = Math.min(45, 800 / Math.max(shown.length, 1));
  const body = shown
    .map((region, index) => {
      const { x, y, w, h } = region.bbox;
      const style = `animation-delay:${Math.round(index * step)}ms`;
      return region.line && region.line.length === 4
        ? `<line class="st-scan" style="${style}" x1="${region.line[0]}" y1="${region.line[1]}" x2="${region.line[2]}" y2="${region.line[3]}"/>`
        : `<rect class="st-scan" style="${style}" x="${x}" y="${y}" width="${w}" height="${h}" rx="4"/>`;
    })
    .join("");
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${view.width} ${view.height}" width="100%" height="100%" preserveAspectRatio="none">` +
    body +
    `</svg>`
  );
}

const DEBUG_COLORS: Record<string, string> = {
  text: "#0050c8",
  figure: "#008c00",
  control: "#dc0000",
  changed: "#b400b4",
  line: "#ff8000",
  label: "#c800c8",
};

// Debug view: draws every detected region with its number, so the output of the
// region proposer can be checked by eye on a live capture. The whole-screen
// region (kind "screen") is not drawn.
export function renderRegionsDebugSvg(regions: Region[], view: View): string {
  const body = regions
    .filter((region) => region.kind !== "screen" && region.kind !== "detail" && region.kind !== "ink")
    .map((region) => {
      const { x, y, w, h } = region.bbox;
      const color = DEBUG_COLORS[region.kind] ?? "#444";
      const outline =
        region.line && region.line.length === 4
          ? `<line x1="${region.line[0]}" y1="${region.line[1]}" x2="${region.line[2]}" y2="${region.line[3]}" stroke="${color}" stroke-width="3"/>`
          : `<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="none" stroke="${color}" stroke-width="2"/>`;
      return (
        `<g data-region-id="${region.id}" data-kind="${escapeXml(region.kind)}">` +
        outline +
        `<rect x="${x}" y="${y}" width="${String(region.id).length * 12 + 10}" height="20" fill="${color}"/>` +
        `<text x="${x + 5}" y="${y + 15}" fill="#fff" font-size="14" ${FONT} font-weight="700">${region.id}</text>` +
        `</g>`
      );
    })
    .join("");
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${view.width} ${view.height}" width="100%" height="100%" preserveAspectRatio="none">` +
    body +
    `</svg>`
  );
}
