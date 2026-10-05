// Where the small pieces of a drawing go, so they never sit on top of each other or
// run off the screen: captions (pills) beside the thing they name, and the tail of
// an arrow. Pure functions of the regions and the screen size, so the renderer and
// the animation always agree.

import type { Region } from "../contract";
import { plainMath } from "./math";

export interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
}
export interface Pt {
  x: number;
  y: number;
}
export interface View {
  width: number;
  height: number;
}

export const PILL_FONT = 18;
const PILL_PAD_X = 12;
const PILL_PAD_Y = 7;
const PILL_LINE = 24;
const PILL_MAX_CHARS = 30;
const MARGIN = 8;

export function overlapArea(a: Box, b: Box): number {
  const w = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x);
  const h = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y);
  return w > 0 && h > 0 ? w * h : 0;
}

function inflate(box: Box, by: number): Box {
  return { x: box.x - by, y: box.y - by, w: box.w + 2 * by, h: box.h + 2 * by };
}

export function boxOf(region: Region): Box {
  return { x: region.bbox.x, y: region.bbox.y, w: region.bbox.w, h: region.bbox.h };
}

// The screen size, from the whole-screen region (or a default).
export function viewOf(regions: Region[]): View {
  const screen = regions.find((r) => r.kind === "screen");
  return screen ? { width: screen.bbox.w, height: screen.bbox.h } : { width: 1920, height: 1080 };
}

// Regions a caption or an arrow must keep off: text, controls and small marks. The
// figure and the whole screen are too big to be obstacles.
const OBSTACLE_KINDS = new Set(["text", "control", "changed", "label"]);

export function obstaclesOf(regions: Region[], except: Box[] = []): Box[] {
  const view = viewOf(regions);
  // A panel or a card is a container, not something to keep off: only its text counts.
  const container = 0.04 * view.width * view.height;
  return regions
    .filter((r) => OBSTACLE_KINDS.has(r.kind))
    .map(boxOf)
    .filter((box) => box.w * box.h < container)
    .filter((box) => !except.some((e) => overlapArea(box, e) > 0.5 * Math.min(box.w * box.h, e.w * e.h)));
}

// Places where a caption is better not put but may be if there is no other room: areas with
// detail the proposer did not name (handwriting, a digit, a face), and pictures. A weight
// says how bad it is to cover one (1 is as bad as covering text).
export interface Soft {
  box: Box;
  weight: number;
}

export function softObstaclesOf(regions: Region[]): Soft[] {
  const soft: Soft[] = [];
  for (const region of regions) {
    if (region.kind === "detail") soft.push({ box: boxOf(region), weight: 0.02 });
    else if (region.kind === "ink") soft.push({ box: boxOf(region), weight: 1 });
    else if (region.kind === "image") soft.push({ box: boxOf(region), weight: 0.6 });
  }
  return soft;
}

// A thin line or arrow as small boxes along it (its bounding box would claim all the empty
// room beside a slanted line).
export function segmentBoxes(from: Pt, to: Pt, thickness = 14): Box[] {
  const length = Math.hypot(to.x - from.x, to.y - from.y);
  const count = Math.max(1, Math.ceil(length / thickness));
  const boxes: Box[] = [];
  for (let i = 0; i <= count; i++) {
    const x = from.x + ((to.x - from.x) * i) / count;
    const y = from.y + ((to.y - from.y) * i) / count;
    boxes.push({ x: x - thickness / 2, y: y - thickness / 2, w: thickness, h: thickness });
  }
  return boxes;
}

// ---- captions ---------------------------------------------------------------------

export interface PillSize {
  lines: string[];
  w: number;
  h: number;
}

function textWidth(text: string): number {
  let width = 0;
  for (const ch of plainMath(text)) {
    width += (ch.codePointAt(0) ?? 0) > 0x2e80 ? PILL_FONT : PILL_FONT * 0.58;
  }
  return width;
}

// Wraps a caption at about 30 characters (two lines at most) and measures it.
export function measurePill(text: string): PillSize {
  const words = text.trim().split(/\s+/);
  const lines: string[] = [];
  let current = "";
  for (const word of words) {
    if (current && (current + " " + word).length > PILL_MAX_CHARS && lines.length < 1) {
      lines.push(current);
      current = word;
    } else {
      current = current ? current + " " + word : word;
    }
  }
  if (current) lines.push(current);
  const w = Math.ceil(Math.max(...lines.map(textWidth), 0)) + 2 * PILL_PAD_X;
  return { lines, w, h: lines.length * PILL_LINE + 2 * PILL_PAD_Y };
}

// Where a pill may go beside a target box, best first: close in all around, then
// further out (when the neighbourhood is busy with text).
export function pillCandidates(target: Box, size: { w: number; h: number }, gap = 10): Pt[] {
  const around = (distance: number): Pt[] => {
    const cx = target.x + target.w / 2 - size.w / 2;
    const cy = target.y + target.h / 2 - size.h / 2;
    const left = target.x;
    const right = target.x + target.w - size.w;
    const above = target.y - size.h - distance;
    const below = target.y + target.h + distance;
    return [
      { x: cx, y: above },
      { x: left, y: above },
      { x: right, y: above },
      { x: cx, y: below },
      { x: left, y: below },
      { x: right, y: below },
      { x: target.x + target.w + distance, y: cy },
      { x: target.x - size.w - distance, y: cy },
      { x: target.x + target.w + distance, y: above },
      { x: target.x - size.w - distance, y: above },
      { x: target.x + target.w + distance, y: below },
      { x: target.x - size.w - distance, y: below },
    ];
  };
  return [...around(gap), ...around(gap + 34), ...around(gap + 80)];
}

export class Placer {
  private taken: Box[];

  constructor(
    private readonly view: View,
    obstacles: Box[],
    private readonly soft: Soft[] = [],
  ) {
    this.taken = [...obstacles];
  }

  // Reserve room (a drawn shape, another pill).
  reserve(box: Box): void {
    this.taken.push(box);
  }

  // The first candidate that is on the screen and clear of everything. When every
  // candidate touches something, the same spots slid a little are tried before giving
  // up; as a last resort the one that covers the least (kept on the screen).
  place(size: { w: number; h: number }, candidates: Pt[]): Box {
    const fit = (p: Pt): Box => ({
      x: Math.max(MARGIN, Math.min(p.x, this.view.width - size.w - MARGIN)),
      y: Math.max(MARGIN, Math.min(p.y, this.view.height - size.h - MARGIN)),
      w: size.w,
      h: size.h,
    });
    const cost = (box: Box) =>
      this.taken.reduce((sum, t) => sum + overlapArea(inflate(box, 2), t), 0) +
      this.soft.reduce((sum, s) => sum + s.weight * overlapArea(box, s.box), 0);
    const onScreen = (p: Pt) =>
      p.x >= MARGIN && p.y >= MARGIN && p.x + size.w <= this.view.width - MARGIN && p.y + size.h <= this.view.height - MARGIN;

    let best: { box: Box; cost: number } | undefined;
    const consider = (p: Pt, order: number): boolean => {
      const box = fit(p);
      // A spot pushed back onto the screen counts as worse than one that fit.
      const total = cost(box) + (onScreen(p) ? 0 : 400) + order * 0.5;
      if (!best || total < best.cost) best = { box, cost: total };
      return onScreen(p) && total < 1;
    };

    let done = false;
    candidates.forEach((candidate, index) => {
      if (!done) done = consider(candidate, index);
    });
    if (!done) {
      for (const [dx, dy] of SLIDES) {
        for (const [index, candidate] of candidates.entries()) {
          if (consider({ x: candidate.x + dx, y: candidate.y + dy }, 100 + index)) {
            done = true;
            break;
          }
        }
        if (done) break;
      }
    }
    const chosen = best?.box ?? fit({ x: MARGIN, y: MARGIN });
    this.reserve(chosen);
    return chosen;
  }
}

// How far a spot is slid, smallest first, when none of the neat ones is clear.
const SLIDES: [number, number][] = [
  [-24, 0], [24, 0], [0, -20], [0, 20],
  [-48, 0], [48, 0], [0, -40], [0, 40],
  [-24, -20], [24, -20], [-24, 20], [24, 20],
  [-80, 0], [80, 0],
];

// ---- arrows -----------------------------------------------------------------------

// How far from the target the tail is: close enough to read as pointing, far enough
// to be seen.
const ARROW_GAP = 95;

const DIRECTIONS: Pt[] = [
  { x: -1, y: -1 },
  { x: 0, y: -1 },
  { x: -1, y: 0 },
  { x: 1, y: -1 },
  { x: -1, y: 1 },
  { x: 1, y: 0 },
  { x: 0, y: 1 },
  { x: 1, y: 1 },
].map((d) => {
  const length = Math.hypot(d.x, d.y);
  return { x: d.x / length, y: d.y / length };
});

function distanceToBoxEdge(box: Box, direction: Pt): number {
  const sx = direction.x === 0 ? Infinity : box.w / 2 / Math.abs(direction.x);
  const sy = direction.y === 0 ? Infinity : box.h / 2 / Math.abs(direction.y);
  return Math.min(sx, sy);
}

function segmentHits(from: Pt, to: Pt, boxes: Box[]): number {
  let hits = 0;
  for (let i = 1; i <= 8; i++) {
    const t = i / 10; // stop short of the head
    const p = { x: from.x + (to.x - from.x) * t, y: from.y + (to.y - from.y) * t };
    if (boxes.some((b) => p.x > b.x && p.x < b.x + b.w && p.y > b.y && p.y < b.y + b.h)) hits += 1;
  }
  return hits;
}

// The tail of an arrow that points at `target`: a short distance away in a free
// direction, on the screen, with a clear straight line to the target. `caption` is
// the size of the pill that will sit at the tail (so it is on the screen too).
export function arrowTail(
  target: Box,
  obstacles: Box[],
  view: View,
  caption: { w: number; h: number } | null,
): Pt {
  const centre = { x: target.x + target.w / 2, y: target.y + target.h / 2 };
  const others = obstacles.filter((o) => overlapArea(o, target) < 0.5 * Math.min(o.w * o.h, target.w * target.h));
  let best: { tail: Pt; cost: number } | undefined;
  DIRECTIONS.forEach((direction, index) => {
    const reach = distanceToBoxEdge(target, direction) + ARROW_GAP;
    const tail = { x: centre.x + direction.x * reach, y: centre.y + direction.y * reach };
    const room = caption ? { w: caption.w, h: caption.h } : { w: 24, h: 24 };
    const outside =
      tail.x - room.w / 2 < MARGIN ||
      tail.x + room.w / 2 > view.width - MARGIN ||
      tail.y - room.h < MARGIN ||
      tail.y + room.h > view.height - MARGIN;
    const spot: Box = { x: tail.x - room.w / 2, y: tail.y - room.h / 2, w: room.w, h: room.h };
    const covered = others.reduce((sum, o) => sum + (overlapArea(spot, o) > 0 ? 1 : 0), 0);
    const cost = (outside ? 100 : 0) + covered * 10 + segmentHits(tail, centre, others) * 3 + index * 0.1;
    if (!best || cost < best.cost) best = { tail, cost };
  });
  const tail = best?.tail ?? { x: centre.x - ARROW_GAP, y: centre.y - ARROW_GAP };
  return {
    x: Math.max(MARGIN, Math.min(tail.x, view.width - MARGIN)),
    y: Math.max(MARGIN, Math.min(tail.y, view.height - MARGIN)),
  };
}
