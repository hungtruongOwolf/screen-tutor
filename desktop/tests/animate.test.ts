// The animation plan (pure) and the driver (with a stand-in for the Web Animations API).

import { afterEach, describe, expect, it } from "vitest";
import type { Region, Shape } from "../src/contract";
import { drawDuration, drawPath, planAnimation, playAnimation, smoothstep } from "../src/render/animate";
import { renderCanvasSvg } from "../src/render/renderCanvas";

const line = (id: number, x1: number, y1: number, x2: number, y2: number): Region => ({
  id,
  kind: "line",
  bbox: { x: Math.min(x1, x2), y: Math.min(y1, y2), w: Math.max(Math.abs(x2 - x1), 6), h: Math.max(Math.abs(y2 - y1), 6) },
  line: [x1, y1, x2, y2],
});
const screen: Region = { id: 0, kind: "screen", bbox: { x: 0, y: 0, w: 1000, h: 700 } };
const figure: Region = { id: 1, kind: "figure", bbox: { x: 100, y: 100, w: 800, h: 500 } };
const base = line(2, 200, 500, 700, 500);
const side = line(3, 700, 500, 700, 200);
const label: Region = { id: 4, kind: "label", bbox: { x: 740, y: 330, w: 20, h: 24 } };
const all = [screen, figure, base, side, label];
const whole = { x: 0, y: 0, w: 1, h: 1 };

function shape(partial: Partial<Shape> & Pick<Shape, "id" | "kind" | "anchor">): Shape {
  return { turn: 0, ...partial };
}

const highlightBase = shape({ id: "h1", kind: "highlight", anchor: { region_id: 2, ...whole } });
const highlightSide = shape({ id: "h2", kind: "highlight", anchor: { region_id: 3, ...whole } });
const box = shape({ id: "b", kind: "box", anchor: { region_id: 4, ...whole } });
const square = shape({ id: "sq", kind: "square_on_line", anchor: { region_id: 2, ...whole }, side: "left", scale: 0.5 });
const arrow = shape({ id: "a", kind: "arrow", anchor: { region_id: 1, x: 0.9, y: 0.1, w: 0, h: 0 }, target_region_id: 4 });
const equation = shape({ id: "e", kind: "equation", anchor: { region_id: 0, x: 0.1, y: 0.1, w: 0, h: 0 }, text: "a^2 + b^2 = c^2" });

describe("easing", () => {
  it("starts at 0, ends at 1 and is slow at both ends", () => {
    expect(smoothstep(0)).toBe(0);
    expect(smoothstep(1)).toBe(1);
    expect(smoothstep(0.1)).toBeLessThan(0.1);
    expect(smoothstep(0.9)).toBeGreaterThan(0.9);
    expect(smoothstep(-1)).toBe(0);
    expect(smoothstep(2)).toBe(1);
  });
});

describe("where the cursor goes while a shape is drawn", () => {
  it("follows a highlighted line from end to end", () => {
    expect(drawPath(highlightBase, all)).toEqual([{ x: 200, y: 500 }, { x: 700, y: 500 }]);
  });

  it("goes from the tail of an arrow to the target region", () => {
    const path = drawPath(arrow, all) ?? [];

    // The tail is placed by the app in free space near the target; the head is the
    // nearest point of the label box to it.
    const tail = path[0]!;
    const head = path[1]!;
    expect(Math.hypot(head.x - tail.x, head.y - tail.y)).toBeGreaterThan(60);
    expect(head.x).toBeGreaterThanOrEqual(740);
    expect(head.x).toBeLessThanOrEqual(760);
    expect(head.y).toBeGreaterThanOrEqual(330);
    expect(head.y).toBeLessThanOrEqual(354);
  });

  it("goes around the corners of a square", () => {
    const path = drawPath(square, all) ?? [];

    expect(path).toHaveLength(4);
    expect(path[0]).toEqual({ x: 200, y: 500 });
    expect(path[2]).toEqual({ x: 450, y: 250 }); // half size, built upwards (the left of a line going right)
  });

  it("has nothing for a shape on a region that is not there", () => {
    expect(drawPath({ ...box, anchor: { region_id: 99, ...whole } }, all)).toBeNull();
  });
});

describe("the plan", () => {
  it("draws shapes one after another, in the order given", () => {
    const plan = planAnimation([highlightBase, highlightSide, box], all);

    expect(plan.items.map((i) => i.id)).toEqual(["h1", "h2", "b"]);
    for (let i = 1; i < plan.items.length; i++) {
      const before = plan.items[i - 1]!;
      expect(plan.items[i]!.start).toBeGreaterThanOrEqual(before.start + before.duration);
    }
    const last = plan.items[plan.items.length - 1]!;
    expect(plan.total).toBeCloseTo(last.start + last.duration, 5);
  });

  it("takes longer to draw a longer line, within limits", () => {
    const short = drawDuration(highlightSide, drawPath(highlightSide, all)!); // 300 px
    const long = drawDuration(highlightBase, drawPath(highlightBase, all)!); // 500 px

    expect(long).toBeGreaterThan(short);
    expect(short).toBeGreaterThanOrEqual(350);
    expect(long).toBeLessThanOrEqual(900);
  });

  it("types an equation for longer the longer it is", () => {
    const shortEquation = { ...equation, text: "x = 1" };
    const a = drawDuration(shortEquation, drawPath(shortEquation, all)!);
    const b = drawDuration(equation, drawPath(equation, all)!);

    expect(b).toBeGreaterThan(a);
  });

  it("skips shapes it cannot place and is empty for none", () => {
    expect(planAnimation([{ ...box, anchor: { region_id: 99, ...whole } }], all).items).toEqual([]);
    expect(planAnimation([], all)).toEqual({ items: [], cursor: [], total: 0 });
  });

  it("has the cursor at the start of each shape when it begins and at its end when it is done", () => {
    const plan = planAnimation([highlightBase, highlightSide], all);

    for (const item of plan.items) {
      const atStart = plan.cursor.find((f) => Math.abs(f.t - item.start) < 1e-6);
      expect(atStart?.x).toBeCloseTo(item.path[0]!.x);
      expect(atStart?.y).toBeCloseTo(item.path[0]!.y);
      const last = item.path[item.path.length - 1]!;
      const atEnd = plan.cursor.find((f) => Math.abs(f.t - (item.start + item.duration)) < 1e-6);
      expect(atEnd?.x).toBeCloseTo(last.x);
    }
  });

  it("starts the cursor from where it is told, invisible, and fades it out at the end", () => {
    const plan = planAnimation([highlightBase], all, { startCursor: { x: 500, y: 650 } });

    expect(plan.cursor[0]).toMatchObject({ t: 0, x: 500, y: 650, opacity: 0 });
    expect(plan.cursor[plan.cursor.length - 1]!.opacity).toBe(0);
    expect(plan.cursor[plan.cursor.length - 1]!.t).toBeGreaterThan(plan.total);
  });

  it("moves the cursor along a curve that bows upwards and swells in the middle", () => {
    const plan = planAnimation([highlightSide], all, { startCursor: { x: 100, y: 600 } });
    const travel = plan.cursor.filter((f) => f.t > 0 && f.t <= plan.items[0]!.start + 1e-6);
    const straightMiddleY = (600 + 500) / 2;
    const middle = travel[Math.floor(travel.length / 2) - 1]!;

    expect(middle.y).toBeLessThan(straightMiddleY); // lifted above the straight line
    expect(Math.max(...travel.map((f) => f.scale))).toBeGreaterThan(1.2);
    expect(travel[travel.length - 1]!.scale).toBeCloseTo(1);
  });

  it("keeps the cursor times in increasing order", () => {
    const plan = planAnimation([highlightBase, box, square, arrow, equation], all, { startCursor: { x: 10, y: 10 } });
    for (let i = 1; i < plan.cursor.length; i++) {
      expect(plan.cursor[i]!.t).toBeGreaterThanOrEqual(plan.cursor[i - 1]!.t);
    }
  });
});

// A stand-in for the Web Animations API: records what was animated and when.
interface Call {
  target: Element;
  keyframes: any;
  options: any;
}

function installFakeAnimations(): Call[] {
  const calls: Call[] = [];
  (Element.prototype as any).animate = function (this: Element, keyframes: any, options: any) {
    calls.push({ target: this, keyframes, options });
    return { finished: Promise.resolve(), finish() {} };
  };
  (SVGElement.prototype as any).getTotalLength = () => 200;
  return calls;
}

afterEach(() => {
  delete (Element.prototype as any).animate;
  delete (SVGElement.prototype as any).getTotalLength;
});

function draw(shapes: Shape[]): SVGSVGElement {
  document.body.innerHTML = renderCanvasSvg({ shapes }, all, { width: 1000, height: 700 });
  return document.querySelector("svg") as SVGSVGElement;
}

describe("the driver", () => {
  it("leaves everything drawn and finishes at once when animations are not supported", async () => {
    const svg = draw([highlightBase]);

    await playAnimation(svg, planAnimation([highlightBase], all)).finished;

    expect(svg.querySelector('g[data-shape-id="h1"]')).not.toBeNull();
    expect(svg.querySelector("[data-cursor]")).toBeNull();
  });

  it("finishes at once when told to be instant, even if animations are supported", async () => {
    const calls = installFakeAnimations();
    const svg = draw([highlightBase]);

    await playAnimation(svg, planAnimation([highlightBase], all), { instant: true }).finished;

    expect(calls).toHaveLength(0);
  });

  it("hides each shape until its turn and draws its stroke on along its length", async () => {
    const calls = installFakeAnimations();
    const shapes = [highlightBase, highlightSide];
    const svg = draw(shapes);
    const plan = planAnimation(shapes, all);

    await playAnimation(svg, plan).finished;

    const group = svg.querySelector('g[data-shape-id="h2"]')!;
    const hide = calls.find((c) => c.target === group)!;
    expect(hide.options.delay).toBeCloseTo(plan.items[1]!.start);
    const stroke = calls.find((c) => c.target.tagName.toLowerCase() === "line" && group.contains(c.target))!;
    expect(stroke.keyframes[0].strokeDashoffset).toBe(200);
    expect(stroke.keyframes[1].strokeDashoffset).toBe(0);
    expect(stroke.target.getAttribute("style")).toContain("stroke-dasharray:200 200");
  });

  it("shows the head of an arrow only once its line is drawn", async () => {
    const calls = installFakeAnimations();
    const svg = draw([arrow]);
    const plan = planAnimation([arrow], all);

    await playAnimation(svg, plan).finished;

    const head = calls.find((c) => c.target.getAttribute("data-part") === "head")!;
    expect(head.options.delay).toBeGreaterThan(plan.items[0]!.start + plan.items[0]!.duration * 0.8);
  });

  it("fades the fill of a square in after its outline starts", async () => {
    const calls = installFakeAnimations();
    const svg = draw([square]);
    const plan = planAnimation([square], all);

    await playAnimation(svg, plan).finished;

    const fill = calls.find((c) => c.keyframes[0]?.fillOpacity === 0)!;
    expect(fill.options.delay).toBeGreaterThan(plan.items[0]!.start);
    expect(fill.keyframes[1].fillOpacity).toBeCloseTo(0.25);
  });

  it("adds a cursor that moves through the planned frames and removes it afterwards", async () => {
    const calls = installFakeAnimations();
    const svg = draw([highlightBase, box]);
    const plan = planAnimation([highlightBase, box], all);

    const playback = playAnimation(svg, plan);
    const cursor = svg.querySelector("[data-cursor]");
    expect(cursor).not.toBeNull();
    const move = calls.find((c) => c.target === cursor)!;
    expect(move.keyframes).toHaveLength(plan.cursor.length);
    expect(move.keyframes[0].transform).toContain("translate(");

    await playback.finished;
    expect(svg.querySelector("[data-cursor]")).toBeNull();
  });

  it("cancelling takes the cursor away", () => {
    installFakeAnimations();
    const svg = draw([highlightBase]);

    playAnimation(svg, planAnimation([highlightBase], all)).cancel();

    expect(svg.querySelector("[data-cursor]")).toBeNull();
  });
});

describe("pieces that slide", () => {
  const slider = shape({
    id: "tri",
    kind: "polygon",
    anchor: { region_id: 0, ...whole },
    points: [
      { x: 0.5, y: 0.5 },
      { x: 0.6, y: 0.5 },
      { x: 0.5, y: 0.6 },
    ],
    motion: { dx: -200, dy: 40, rotate: -90, pivot_x: 550, pivot_y: 380 },
  });

  it("slide first, together in a ripple, and what is drawn new comes after them", () => {
    const plan = planAnimation([highlightBase, slider], all);

    expect(plan.items.map((i) => i.id)).toEqual(["tri", "h1"]);
    const [slide, drawn] = plan.items as [typeof plan.items[0], typeof plan.items[0]];
    expect(slide.motion).toBeDefined();
    expect(drawn.start).toBeGreaterThanOrEqual(slide.start + slide.duration);
  });

  it("the cursor stays out of sight while the pieces slide", () => {
    const plan = planAnimation([slider, highlightBase], all);

    const first = plan.cursor.find((f) => f.t > 0)!;
    expect(plan.cursor[0]!.opacity).toBe(0);
    expect(first.t).toBeGreaterThan(0);
    expect(plan.cursor.filter((f) => f.t <= plan.items[0]!.duration && f.opacity > 0)).toHaveLength(0);
  });

  it("starts displaced and turned about its own centre and comes to rest", async () => {
    const calls = installFakeAnimations();
    const svg = draw([slider]);

    await playAnimation(svg, planAnimation([slider], all)).finished;

    const group = svg.querySelector('g[data-shape-id="tri"]')!;
    const slide = calls.find((c) => c.target === group)!;
    expect(slide.keyframes[0].transform).toBe("translate(-200px, 40px) rotate(-90deg)");
    expect(slide.keyframes[1].transform).toBe("translate(0px, 0px) rotate(0deg)");
    expect(group.getAttribute("style")).toContain("transform-origin:550px 380px");
    // no stroke is drawn on and nothing is hidden
    expect(calls.filter((c) => c.target !== group && group.contains(c.target))).toHaveLength(0);
  });
});
