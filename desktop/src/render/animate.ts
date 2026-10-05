// Animation of the drawing: a plan (pure, testable) and a driver (the DOM part).
//
// The plan says, for the shapes of one step, when each starts, how long it takes
// to draw and where the cursor is at every moment: it glides along a curve to the
// start of a shape (smooth easing, a little swell in the middle, like a hand
// reaching out), then follows the stroke while it is drawn.
//
// The driver applies a plan to an SVG made by renderCanvasSvg using the Web
// Animations API: outlines are drawn on along their length, fills fade in, labels
// and equations appear, arrow heads pop in when the arrow is complete.

import type { Motion, Region, Shape } from "../contract";
import { arrowEnds, type Pt } from "./renderCanvas";
import { squareCorners, type Line } from "./geometry";

export type { Pt };

export interface PlanItem {
  id: string;
  kind: Shape["kind"];
  start: number; // ms from the start of the step
  duration: number; // ms to draw
  path: Pt[]; // where the cursor goes while it is drawn (first to last)
  motion?: Motion; // a shape that slides into place instead of being drawn
}

export interface CursorFrame {
  t: number; // ms
  x: number;
  y: number;
  scale: number;
  opacity: number;
}

export interface Plan {
  items: PlanItem[];
  cursor: CursorFrame[];
  total: number; // ms until everything is drawn
}

// How long a piece takes to slide, and the delay between pieces so they move one after
// another in a ripple.
const SLIDE_MS = 1300;
const SLIDE_RIPPLE_MS = 160;

export interface PlanOptions {
  startCursor?: Pt; // where the cursor comes from (default: the first target)
  gap?: number; // ms between shapes
}

const FRAME_SAMPLES = 8;

// Easing used for the glide: slow start and end, fast in the middle.
export function smoothstep(u: number): number {
  const t = Math.max(0, Math.min(1, u));
  return t * t * (3 - 2 * t);
}

function distance(a: Pt, b: Pt): number {
  return Math.hypot(b.x - a.x, b.y - a.y);
}

function pathLength(path: Pt[]): number {
  let total = 0;
  for (let i = 1; i < path.length; i++) total += distance(path[i - 1] as Pt, path[i] as Pt);
  return total;
}

const clamp = (value: number, low: number, high: number) => Math.max(low, Math.min(high, value));

// The points the cursor follows while a shape is drawn (null: nothing to draw).
export function drawPath(shape: Shape, regions: Region[]): Pt[] | null {
  const region = regions.find((r) => r.id === shape.anchor.region_id);
  if (!region) return null;
  const { bbox } = region;
  const a = shape.anchor;
  const rect = { x: bbox.x + a.x * bbox.w, y: bbox.y + a.y * bbox.h, w: a.w * bbox.w, h: a.h * bbox.h };
  const corner = (p: Pt) => p;

  switch (shape.kind) {
    case "highlight":
      if (region.line && region.line.length === 4) {
        return [
          { x: region.line[0] as number, y: region.line[1] as number },
          { x: region.line[2] as number, y: region.line[3] as number },
        ];
      }
      return [corner({ x: rect.x, y: rect.y }), corner({ x: rect.x + rect.w, y: rect.y + rect.h })];
    case "box":
    case "ellipse":
      return [{ x: rect.x, y: rect.y }, { x: rect.x + rect.w, y: rect.y + rect.h }];
    case "arrow": {
      const ends = arrowEnds(shape, regions);
      return ends ? [ends.tail, ends.head] : null;
    }
    case "square_on_line": {
      if (!region.line || region.line.length !== 4) return null;
      const c = squareCorners(region.line as unknown as Line, shape.side ?? "left", shape.scale ?? 1);
      return [c[0] as Pt, c[1] as Pt, c[2] as Pt, c[3] as Pt];
    }
    case "polygon": {
      if (!shape.points || shape.points.length < 3) return null;
      return shape.points.map((p) => ({ x: bbox.x + p.x * bbox.w, y: bbox.y + p.y * bbox.h }));
    }
    case "label":
    case "step_number":
    case "equation":
    case "connector":
      return [{ x: rect.x, y: rect.y }, { x: rect.x, y: rect.y }];
  }
}

// How long a shape takes to draw.
export function drawDuration(shape: Shape, path: Pt[]): number {
  const length = pathLength(path);
  switch (shape.kind) {
    case "highlight":
      return clamp((length / 1100) * 1000, 350, 900);
    case "arrow":
      return clamp((length / 1200) * 1000, 350, 800);
    case "box":
    case "ellipse":
      return clamp((length / 700) * 1000, 450, 1000);
    case "square_on_line":
    case "polygon":
      return clamp((length / 1500) * 1000, 600, 1100);
    case "equation":
      return clamp(180 + 24 * (shape.text?.length ?? 0), 450, 1500);
    default:
      return 300;
  }
}

// Points along a curve from a to b that bows upwards, sampled at eased times.
function glide(a: Pt, b: Pt, startMs: number, durationMs: number): CursorFrame[] {
  const d = distance(a, b);
  const lift = Math.min(d * 0.2, 80);
  const control = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 - lift };
  const frames: CursorFrame[] = [];
  for (let i = 1; i <= FRAME_SAMPLES; i++) {
    const u = i / FRAME_SAMPLES;
    const t = smoothstep(u);
    const x = (1 - t) * (1 - t) * a.x + 2 * (1 - t) * t * control.x + t * t * b.x;
    const y = (1 - t) * (1 - t) * a.y + 2 * (1 - t) * t * control.y + t * t * b.y;
    frames.push({ t: startMs + u * durationMs, x, y, scale: 1 + 0.3 * Math.sin(Math.PI * u), opacity: 1 });
  }
  return frames;
}

// Where a sliding polygon starts and ends (centres, capture pixels).
function slidePath(shape: Shape, regions: Region[]): Pt[] | null {
  const final = drawPath({ ...shape, motion: null }, regions);
  const motion = shape.motion;
  if (!final || !motion) return null;
  const end = {
    x: final.reduce((sum, p) => sum + p.x, 0) / final.length,
    y: final.reduce((sum, p) => sum + p.y, 0) / final.length,
  };
  return [{ x: end.x + motion.dx, y: end.y + motion.dy }, end];
}

export function planAnimation(shapes: Shape[], regions: Region[], options: PlanOptions = {}): Plan {
  const gap = options.gap ?? 70;
  const items: PlanItem[] = [];
  let at = 0;
  const cursor: CursorFrame[] = [];
  let position: Pt | null = options.startCursor ?? null;

  // Pieces that slide go first, together (each a moment after the one before); then
  // what is drawn new, so it appears in the room the pieces left.
  const sliding = shapes.filter((s) => s.motion);
  sliding.forEach((shape, index) => {
    const path = slidePath(shape, regions);
    if (!path) return;
    items.push({
      id: shape.id,
      kind: shape.kind,
      start: index * SLIDE_RIPPLE_MS,
      duration: SLIDE_MS,
      path,
      motion: shape.motion as Motion,
    });
  });
  if (items.length > 0) at = Math.max(...items.map((i) => i.start + i.duration)) + gap;
  const drawn = shapes.filter((s) => !s.motion);

  for (const shape of drawn) {
    const path = drawPath(shape, regions);
    if (!path || path.length === 0) continue;
    const first = path[0] as Pt;
    if (position === null) position = first;

    // Reach out to where the shape begins.
    const travel = clamp((distance(position, first) / 1500) * 1000, 120, 650);
    if (cursor.length === 0) {
      cursor.push({ t: 0, x: position.x, y: position.y, scale: 1, opacity: 0 });
      // Stay out of sight while the pieces slide.
      if (at > 0) cursor.push({ t: at, x: position.x, y: position.y, scale: 1, opacity: 0 });
    }
    cursor.push(...glide(position, first, at, travel).map((f) => ({ ...f, opacity: 1 })));
    at += travel;

    // Follow the stroke while it is drawn.
    const duration = drawDuration(shape, path);
    const total = Math.max(1, pathLength(path));
    let walked = 0;
    for (let i = 1; i < path.length; i++) {
      const from = path[i - 1] as Pt;
      const to = path[i] as Pt;
      walked += distance(from, to);
      cursor.push({ t: at + (walked / total) * duration, x: to.x, y: to.y, scale: 1, opacity: 1 });
    }
    items.push({ id: shape.id, kind: shape.kind, start: at, duration, path });
    position = path[path.length - 1] as Pt;
    at += duration + gap;
  }

  const total = Math.max(0, at - gap);
  if (position && cursor.length > 0) {
    cursor.push({ t: total + 350, x: position.x, y: position.y, scale: 1, opacity: 0 });
  }
  return { items, cursor, total };
}

// ---------------------------------------------------------------------------------
// The driver

export interface Playback {
  finished: Promise<void>;
  cancel(): void;
}

const NS = "http://www.w3.org/2000/svg";
const EASE = "cubic-bezier(.3,.7,.2,1)";

function prefersReducedMotion(): boolean {
  return typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function canAnimate(root: Element): boolean {
  return typeof (root as Element).animate === "function" && !prefersReducedMotion();
}

function isStroked(el: Element): el is SVGGeometryElement {
  const tag = el.tagName.toLowerCase();
  return ["line", "rect", "ellipse", "polygon", "path", "circle"].includes(tag) && "getTotalLength" in el;
}

function makeCursor(): SVGGElement {
  const g = document.createElementNS(NS, "g");
  g.setAttribute("data-cursor", "true");
  g.setAttribute("style", "opacity:0; pointer-events:none");
  g.innerHTML =
    '<circle r="18" fill="rgba(255,210,63,0.30)"/>' +
    '<path d="M0 0 L0 22 L6 17 L10 26 L14 24 L10 15 L18 15 Z" fill="#ffd23f" stroke="#2a1f00" stroke-width="1.5" stroke-linejoin="round"/>';
  return g;
}

// Play a plan on the SVG that renderCanvasSvg produced. With nothing to animate
// (no support, reduced motion, an empty plan) it leaves everything drawn and
// finishes at once.
export function playAnimation(svg: SVGSVGElement, plan: Plan, options: { instant?: boolean } = {}): Playback {
  const done = Promise.resolve();
  const instant = options.instant || plan.items.length === 0 || !canAnimate(svg);
  if (instant) return { finished: done, cancel() {} };

  const animations: Animation[] = [];
  const keep = <T extends Animation>(a: T): T => {
    animations.push(a);
    return a;
  };

  const groups = new Map<string, Element>();
  svg.querySelectorAll("g[data-shape-id]").forEach((g) => groups.set(g.getAttribute("data-shape-id") ?? "", g));

  for (const item of plan.items) {
    const group = groups.get(item.id);
    if (!group) continue;
    if (item.motion) {
      // A piece that slides: it is drawn where it ends, so it starts displaced and turned
      // about its own centre and comes to rest.
      const m = item.motion;
      group.setAttribute(
        "style",
        `${group.getAttribute("style") ?? ""};transform-box:view-box;transform-origin:${m.pivot_x}px ${m.pivot_y}px`,
      );
      keep(group.animate(
        [
          { transform: `translate(${m.dx}px, ${m.dy}px) rotate(${m.rotate}deg)` },
          { transform: "translate(0px, 0px) rotate(0deg)" },
        ],
        { delay: item.start, duration: item.duration, fill: "both", easing: "cubic-bezier(.45,0,.25,1)" },
      ));
      continue;
    }
    // Hidden until its turn.
    keep(group.animate([{ opacity: 0 }, { opacity: 1 }], { delay: item.start, duration: 1, fill: "both" }));

    for (const el of Array.from(group.children)) {
      const tag = el.tagName.toLowerCase();
      const part = el.getAttribute("data-part");
      if (part === "head") {
        // Arrow head: appears when the line has been drawn.
        keep(el.animate([{ opacity: 0, transform: "scale(0.4)" }, { opacity: 1, transform: "scale(1)" }], {
          delay: item.start + item.duration * 0.9, duration: 160, fill: "both", easing: "ease-out",
        }));
      } else if (tag === "text") {
        keep(el.animate([{ opacity: 0, transform: "translateY(8px)" }, { opacity: 1, transform: "translateY(0)" }], {
          delay: item.start + item.duration * 0.35, duration: Math.max(200, item.duration * 0.6), fill: "both", easing: EASE,
        }));
      } else if (isStroked(el)) {
        const length = el.getTotalLength();
        if (length > 0) {
          el.setAttribute("style", `${el.getAttribute("style") ?? ""};stroke-dasharray:${length} ${length}`);
          keep(el.animate([{ strokeDashoffset: length }, { strokeDashoffset: 0 }], {
            delay: item.start, duration: item.duration, fill: "both", easing: EASE,
          }));
        }
        const fill = el.getAttribute("fill-opacity");
        if (fill !== null) {
          keep(el.animate([{ fillOpacity: 0 }, { fillOpacity: Number(fill) }], {
            delay: item.start + item.duration * 0.5, duration: Math.max(250, item.duration * 0.5), fill: "both",
          }));
        }
      } else {
        keep(el.animate([{ opacity: 0 }, { opacity: 1 }], {
          delay: item.start + item.duration * 0.3, duration: 250, fill: "both",
        }));
      }
    }
  }

  // The cursor.
  if (plan.cursor.length > 1) {
    const cursor = makeCursor();
    svg.appendChild(cursor);
    const end = plan.cursor[plan.cursor.length - 1]?.t ?? 1;
    const frames = plan.cursor.map((f) => ({
      offset: Math.min(1, f.t / end),
      transform: `translate(${f.x}px, ${f.y}px) scale(${f.scale})`,
      opacity: f.opacity,
    }));
    keep(cursor.animate(frames, { duration: end, fill: "both", easing: "linear" }));
  }

  const finished = Promise.all(animations.map((a) => a.finished.catch(() => undefined))).then(() => {
    svg.querySelector('[data-cursor="true"]')?.remove();
  });
  return {
    finished,
    cancel() {
      for (const a of animations) a.finish();
      svg.querySelector('[data-cursor="true"]')?.remove();
    },
  };
}
