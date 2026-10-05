// Seam 2: the overlay renderer. Tests give it canvas states and check the SVG.

import { describe, expect, it } from "vitest";
import type { Canvas, Region, Shape } from "../src/contract";
import { squareCorners } from "../src/render/geometry";
import { formatMath, plainMath } from "../src/render/math";
import { nearestPoint, renderCanvasSvg, renderRegionsDebugSvg, resolveRect } from "../src/render/renderCanvas";

const region: Region = { id: 1, bbox: { x: 100, y: 50, w: 400, h: 200 }, kind: "screen" };

function shape(partial: Partial<Shape> & Pick<Shape, "id" | "kind">): Shape {
  return {
    anchor: { region_id: 1, x: 0.25, y: 0.5, w: 0.5, h: 0.25 },
    turn: 0,
    ...partial,
  };
}

function parse(svg: string): Document {
  return new DOMParser().parseFromString(svg, "image/svg+xml");
}

describe("resolveRect", () => {
  it("maps an anchor relative to its region into capture pixels", () => {
    const rect = resolveRect(shape({ id: "a", kind: "box" }), [region]);

    expect(rect).toEqual({ x: 200, y: 150, w: 200, h: 50 });
  });

  it("returns null when the region does not exist", () => {
    const orphan = shape({ id: "a", kind: "box", anchor: { region_id: 9, x: 0, y: 0, w: 1, h: 1 } });

    expect(resolveRect(orphan, [region])).toBeNull();
  });
});

describe("renderCanvasSvg", () => {
  const view = { width: 1000, height: 600 };

  it("uses the capture size as the viewBox so it is independent of display scale", () => {
    const svg = renderCanvasSvg({ shapes: [] }, [region], view);

    expect(svg).toContain('viewBox="0 0 1000 600"');
  });

  it("draws a box at the resolved position", () => {
    const canvas: Canvas = { shapes: [shape({ id: "b", kind: "box" })] };

    const doc = parse(renderCanvasSvg(canvas, [region], view));
    const rect = doc.querySelector('g[data-shape-id="b"] rect');

    expect(rect?.getAttribute("x")).toBe("200");
    expect(rect?.getAttribute("y")).toBe("150");
    expect(rect?.getAttribute("width")).toBe("200");
    expect(rect?.getAttribute("height")).toBe("50");
  });

  it("draws every shape kind", () => {
    const kinds = ["box", "ellipse", "highlight", "arrow", "label", "step_number"] as const;
    const canvas: Canvas = {
      shapes: kinds.map((kind, i) => shape({ id: `s${i}`, kind, text: "x" })),
    };

    const doc = parse(renderCanvasSvg(canvas, [region], view));

    for (const [i, kind] of kinds.entries()) {
      expect(doc.querySelector(`g[data-shape-id="s${i}"]`)?.getAttribute("data-kind")).toBe(kind);
    }
  });

  it("draws an arrow from its tail to its head in any direction", () => {
    // Tail at bottom-left of the region, head at top-right: not the top-left to bottom-right diagonal.
    const arrow = shape({
      id: "a",
      kind: "arrow",
      anchor: { region_id: 1, x: 0, y: 1, w: 0, h: 0 },
      end: { x: 1, y: 0 },
    });

    const doc = parse(renderCanvasSvg({ shapes: [arrow] }, [region], view));
    const line = doc.querySelector('g[data-shape-id="a"] line');

    expect(line?.getAttribute("x1")).toBe("100");
    expect(line?.getAttribute("y1")).toBe("250");
    expect(line?.getAttribute("x2")).toBe("500");
    expect(line?.getAttribute("y2")).toBe("50");
  });

  it("joins two shapes with a connector", () => {
    const canvas: Canvas = {
      shapes: [
        shape({ id: "a", kind: "box", anchor: { region_id: 1, x: 0, y: 0, w: 0.2, h: 0.2 } }),
        shape({ id: "b", kind: "box", anchor: { region_id: 1, x: 0.8, y: 0.8, w: 0.2, h: 0.2 } }),
        shape({ id: "c", kind: "connector", from_id: "a", to_id: "b" }),
      ],
    };

    const doc = parse(renderCanvasSvg(canvas, [region], view));
    const line = doc.querySelector('g[data-shape-id="c"] line');

    expect(line).not.toBeNull();
    expect(line?.getAttribute("x1")).toBe("140");
    expect(line?.getAttribute("x2")).toBe("460");
  });

  it("skips shapes anchored to a region that is missing", () => {
    const canvas: Canvas = {
      shapes: [shape({ id: "gone", kind: "box", anchor: { region_id: 7, x: 0, y: 0, w: 1, h: 1 } })],
    };

    const doc = parse(renderCanvasSvg(canvas, [region], view));

    expect(doc.querySelector('g[data-shape-id="gone"]')).toBeNull();
  });

  it("escapes text so a label cannot inject markup", () => {
    const canvas: Canvas = {
      shapes: [shape({ id: "t", kind: "label", text: '<script>alert("x")</script>' })],
    };

    const svg = renderCanvasSvg(canvas, [region], view);

    expect(svg).not.toContain("<script>");
    expect(parse(svg).querySelector("script")).toBeNull();
  });

  it("scales identically for any capture size (same shapes, different views)", () => {
    const canvas: Canvas = { shapes: [shape({ id: "b", kind: "box" })] };

    const small = renderCanvasSvg(canvas, [region], { width: 500, height: 300 });
    const large = renderCanvasSvg(canvas, [region], { width: 3000, height: 1800 });

    expect(small).toContain('viewBox="0 0 500 300"');
    expect(large).toContain('viewBox="0 0 3000 1800"');
    expect(parse(small).querySelector("rect")?.getAttribute("x")).toBe(
      parse(large).querySelector("rect")?.getAttribute("x"),
    );
  });
});

describe("regions with finer parts", () => {
  const view = { width: 1000, height: 600 };
  const line: Region = { id: 5, bbox: { x: 100, y: 300, w: 400, h: 200 }, kind: "line", line: [100, 500, 500, 300] };
  const label: Region = { id: 6, bbox: { x: 300, y: 400, w: 20, h: 30 }, kind: "label" };
  const figure: Region = { id: 1, bbox: { x: 50, y: 250, w: 600, h: 300 }, kind: "figure" };
  const regions = [figure, line, label];
  const whole = { x: 0, y: 0, w: 1, h: 1 };

  it("draws a highlight on a line region as a stroke along the line", () => {
    const canvas: Canvas = {
      shapes: [shape({ id: "h", kind: "highlight", anchor: { region_id: 5, ...whole } })],
    };

    const doc = parse(renderCanvasSvg(canvas, regions, view));
    const stroke = doc.querySelector('g[data-shape-id="h"] line');

    expect(stroke?.getAttribute("x1")).toBe("100");
    expect(stroke?.getAttribute("y1")).toBe("500");
    expect(stroke?.getAttribute("x2")).toBe("500");
    expect(stroke?.getAttribute("y2")).toBe("300");
  });

  it("gives a box on a label a little room all round", () => {
    const canvas: Canvas = {
      shapes: [shape({ id: "b", kind: "box", anchor: { region_id: 6, ...whole } })],
    };

    const doc = parse(renderCanvasSvg(canvas, regions, view));
    const rect = doc.querySelector('g[data-shape-id="b"] rect');

    expect(rect?.getAttribute("x")).toBe("294");
    expect(rect?.getAttribute("width")).toBe("32");
  });

  it("lands an arrow on its target region", () => {
    const arrow = shape({
      id: "a",
      kind: "arrow",
      anchor: { region_id: 1, x: 0, y: 0, w: 0, h: 0 },
      target_region_id: 6,
    });

    const doc = parse(renderCanvasSvg({ shapes: [arrow] }, regions, view));
    const head = doc.querySelector('g[data-shape-id="a"] line');

    // The head touches the label box (300..320 x 400..430); the tail is in free space,
    // a short way off (not wherever the model said), inside the screen.
    const x2 = Number(head?.getAttribute("x2"));
    const y2 = Number(head?.getAttribute("y2"));
    expect(x2).toBeGreaterThanOrEqual(300);
    expect(x2).toBeLessThanOrEqual(320);
    expect(y2).toBeGreaterThanOrEqual(400);
    expect(y2).toBeLessThanOrEqual(430);
    const length = Math.hypot(x2 - Number(head?.getAttribute("x1")), y2 - Number(head?.getAttribute("y1")));
    expect(length).toBeGreaterThan(60);
    expect(length).toBeLessThan(260);
  });

  it("keeps a caption on the screen even when its box is at the edge", () => {
    const edge = shape({
      id: "edge",
      kind: "box",
      anchor: { region_id: 9, ...whole },
      text: "Click here to add a service",
    });
    const corner: Region = { id: 9, bbox: { x: 880, y: 20, w: 110, h: 40 }, kind: "control" };

    const doc = parse(renderCanvasSvg({ shapes: [edge] }, [corner], view));
    const pillBox = doc.querySelector('g[data-shape-id="edge"] g[data-part="pill"] rect');

    expect(pillBox).not.toBeNull();
    const x = Number(pillBox?.getAttribute("x"));
    const width = Number(pillBox?.getAttribute("width"));
    expect(x).toBeGreaterThanOrEqual(0);
    expect(x + width).toBeLessThanOrEqual(view.width);
  });

  it("puts the captions of two shapes side by side, not on top of each other", () => {
    const a: Region = { id: 11, bbox: { x: 400, y: 300, w: 120, h: 40 }, kind: "control" };
    const b: Region = { id: 12, bbox: { x: 540, y: 300, w: 120, h: 40 }, kind: "control" };
    const shapes = [
      shape({ id: "a", kind: "box", anchor: { region_id: 11, ...whole }, text: "Click this first" }),
      shape({ id: "b", kind: "box", anchor: { region_id: 12, ...whole }, text: "Then this one" }),
    ];

    const doc = parse(renderCanvasSvg({ shapes }, [a, b], view));
    const pills = ["a", "b"].map((id) => {
      const r = doc.querySelector(`g[data-shape-id="${id}"] g[data-part="pill"] rect`)!;
      return { x: Number(r.getAttribute("x")), y: Number(r.getAttribute("y")), w: Number(r.getAttribute("width")), h: Number(r.getAttribute("height")) };
    });

    const [p, q] = pills as [typeof pills[0], typeof pills[0]];
    const overlap = p.x < q.x + q.w && q.x < p.x + p.w && p.y < q.y + q.h && q.y < p.y + p.h;
    expect(overlap).toBe(false);
  });

  it("keeps a caption off the text of the screen", () => {
    const button: Region = { id: 13, bbox: { x: 400, y: 300, w: 120, h: 40 }, kind: "control" };
    const above: Region = { id: 14, bbox: { x: 300, y: 240, w: 400, h: 50 }, kind: "text" };
    const box = shape({ id: "c", kind: "box", anchor: { region_id: 13, ...whole }, text: "Click here" });

    const doc = parse(renderCanvasSvg({ shapes: [box] }, [button, above], view));
    const r = doc.querySelector('g[data-shape-id="c"] g[data-part="pill"] rect')!;
    const p = { x: Number(r.getAttribute("x")), y: Number(r.getAttribute("y")), w: Number(r.getAttribute("width")), h: Number(r.getAttribute("height")) };

    const covers = p.x < 700 && 300 < p.x + p.w && p.y < 290 && 240 < p.y + p.h;
    expect(covers).toBe(false);
  });

  it("finds the nearest point on a line", () => {
    // A point above the middle of the line projects onto the line itself.
    const middle = nearestPoint(line, { x: 300, y: 0 });
    expect(Math.round(middle.x)).toBeGreaterThan(100);
    expect(Math.round(middle.x)).toBeLessThan(500);
    const near = nearestPoint(line, { x: 0, y: 600 });
    expect(near).toEqual({ x: 100, y: 500 });
  });
});

describe("renderRegionsDebugSvg", () => {
  const view = { width: 1000, height: 600 };
  const regions: Region[] = [
    { id: 0, bbox: { x: 0, y: 0, w: 1000, h: 600 }, kind: "screen" },
    { id: 1, bbox: { x: 10, y: 20, w: 300, h: 80 }, kind: "text" },
    { id: 2, bbox: { x: 500, y: 100, w: 200, h: 200 }, kind: "figure" },
  ];

  it("draws each detected region with its number and skips the whole-screen region", () => {
    const doc = parse(renderRegionsDebugSvg(regions, view));

    expect(doc.querySelector('g[data-region-id="0"]')).toBeNull();
    expect(doc.querySelector('g[data-region-id="1"] text')?.textContent).toBe("1");
    expect(doc.querySelector('g[data-region-id="2"]')?.getAttribute("data-kind")).toBe("figure");
  });

  it("places the outline at the region box in capture pixels", () => {
    const doc = parse(renderRegionsDebugSvg(regions, view));
    const outline = doc.querySelector('g[data-region-id="1"] rect');

    expect(outline?.getAttribute("x")).toBe("10");
    expect(outline?.getAttribute("width")).toBe("300");
  });
});

describe("new geometry", () => {
  const view = { width: 1000, height: 600 };
  const base: Region = { id: 2, bbox: { x: 100, y: 500, w: 400, h: 8 }, kind: "line", line: [100, 500, 500, 500] };
  const figure: Region = { id: 1, bbox: { x: 50, y: 100, w: 600, h: 450 }, kind: "figure" };
  const regions = [figure, base];
  const whole = { x: 0, y: 0, w: 1, h: 1 };

  function polygonPoints(svg: string, id: string): number[][] {
    const attr = parse(svg).querySelector(`g[data-shape-id="${id}"] polygon`)?.getAttribute("points") ?? "";
    return attr.split(" ").map((pair) => pair.split(",").map(Number));
  }

  it("draws a square on a line, on the chosen side, at the line's length", () => {
    const left = shape({ id: "s", kind: "square_on_line", anchor: { region_id: 2, ...whole }, side: "left", scale: 1 });

    const svg = renderCanvasSvg({ shapes: [left] }, regions, view);

    // Looking from (100,500) to (500,500), "left" is up on a screen.
    expect(polygonPoints(svg, "s")).toEqual([[100, 500], [500, 500], [500, 100], [100, 100]]);
  });

  it("builds the square on the other side, and smaller when scaled", () => {
    const right = shape({ id: "r", kind: "square_on_line", anchor: { region_id: 2, ...whole }, side: "right", scale: 0.5 });

    const svg = renderCanvasSvg({ shapes: [right] }, regions, view);

    expect(polygonPoints(svg, "r")).toEqual([[100, 500], [300, 500], [300, 700], [100, 700]]);
  });

  it("writes the text of a square in its middle, with a raised power", () => {
    const square = shape({ id: "s", kind: "square_on_line", anchor: { region_id: 2, ...whole }, side: "left", text: "5^2 = 25" });

    const doc = parse(renderCanvasSvg({ shapes: [square] }, regions, view));
    const text = doc.querySelector('g[data-shape-id="s"] text');

    expect(text?.getAttribute("x")).toBe("300");
    expect(text?.querySelector("tspan")?.textContent).toBe("2");
  });

  it("draws nothing for a square on a region that is not a line", () => {
    const wrong = shape({ id: "w", kind: "square_on_line", anchor: { region_id: 1, ...whole }, side: "left" });

    expect(parse(renderCanvasSvg({ shapes: [wrong] }, regions, view)).querySelector('g[data-shape-id="w"]')).toBeNull();
  });

  it("draws a polygon through points relative to its region", () => {
    const triangle = shape({
      id: "p",
      kind: "polygon",
      anchor: { region_id: 1, ...whole },
      points: [{ x: 0, y: 0 }, { x: 1, y: 0 }, { x: 0.5, y: 1 }],
    });

    expect(polygonPoints(renderCanvasSvg({ shapes: [triangle] }, regions, view), "p")).toEqual([
      [50, 100],
      [650, 100],
      [350, 550],
    ]);
  });

  it("keeps an equation box inside the picture", () => {
    const equation = shape({ id: "e", kind: "equation", anchor: { region_id: 1, x: 1, y: 1, w: 0, h: 0 }, text: "a^2 + b^2 = c^2" });

    const rect = parse(renderCanvasSvg({ shapes: [equation] }, regions, view)).querySelector('g[data-shape-id="e"] rect');
    const x = Number(rect?.getAttribute("x"));
    const width = Number(rect?.getAttribute("width"));
    const y = Number(rect?.getAttribute("y"));
    const height = Number(rect?.getAttribute("height"));

    expect(x + width).toBeLessThanOrEqual(1000);
    expect(y + height).toBeLessThanOrEqual(600);
  });
});

describe("formula text", () => {
  it("raises powers and keeps the rest", () => {
    expect(formatMath("5^2 + 12^2")).toBe(
      '5<tspan baseline-shift="super" font-size="70%">2</tspan> + 12<tspan baseline-shift="super" font-size="70%">2</tspan>',
    );
  });

  it("accepts braces for longer exponents", () => {
    expect(formatMath("x^{n+1}")).toContain(">n+1</tspan>");
  });

  it("turns plain spellings into symbols", () => {
    expect(formatMath("sqrt(169) = 13, 3*4 <= 12")).toBe("√(169) = 13, 3×4 ≤ 12");
  });

  it("escapes markup so a label cannot inject anything", () => {
    expect(formatMath('<b>"x"</b> & y')).toBe("&lt;b&gt;&quot;x&quot;&lt;/b&gt; &amp; y");
  });

  it("measures a formula without its markup", () => {
    expect(plainMath("a^2 + b^{12}")).toBe("a2 + b12");
  });
});

describe("square corners", () => {
  it("matches the backend for a slanted line", () => {
    const corners = squareCorners([0, 0, 3, 4], "left");

    // Length 5. Left of the direction (3, 4)/5 is (4, -3)/5 on screen.
    expect(corners.map((p) => [Math.round(p.x * 100) / 100, Math.round(p.y * 100) / 100])).toEqual([
      [0, 0],
      [3, 4],
      [7, 1],
      [4, -3],
    ]);
  });
});
