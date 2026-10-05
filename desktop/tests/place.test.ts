// Where captions and arrow tails go: always on the screen, never on text or on each other.

import { describe, expect, it } from "vitest";
import type { Region } from "../src/contract";
import { arrowTail, measurePill, obstaclesOf, overlapArea, pillCandidates, Placer, viewOf } from "../src/render/place";

const view = { width: 1000, height: 600 };

describe("measuring a caption", () => {
  it("keeps a short caption on one line", () => {
    const size = measurePill("Click here");

    expect(size.lines).toEqual(["Click here"]);
    expect(size.w).toBeGreaterThan(60);
    expect(size.w).toBeLessThan(200);
  });

  it("wraps a long caption onto a second line", () => {
    const size = measurePill("Click the orange Add service button on the right");

    expect(size.lines).toHaveLength(2);
    expect(size.lines.join(" ")).toBe("Click the orange Add service button on the right");
    expect(size.h).toBeGreaterThan(measurePill("Click here").h);
  });

  it("gives wide characters more room", () => {
    expect(measurePill("点击这里").w).toBeGreaterThan(measurePill("abcd").w);
  });
});

describe("the placer", () => {
  const size = { w: 120, h: 38 };
  const target = { x: 400, y: 300, w: 100, h: 40 };

  it("takes the first spot when it is clear (above the target, centred)", () => {
    const box = new Placer(view, []).place(size, pillCandidates(target, size));

    expect(box.y + box.h).toBeLessThanOrEqual(target.y);
    expect(box.x + box.w / 2).toBeCloseTo(target.x + target.w / 2);
  });

  it("skips a spot that is covered by text", () => {
    const text = { x: 380, y: 240, w: 200, h: 50 }; // right above the target
    const box = new Placer(view, [text]).place(size, pillCandidates(target, size));

    expect(overlapArea(box, text)).toBe(0);
  });

  it("never leaves the screen", () => {
    const corner = { x: 930, y: 10, w: 60, h: 30 };
    const box = new Placer(view, []).place(size, pillCandidates(corner, size));

    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.y).toBeGreaterThanOrEqual(0);
    expect(box.x + box.w).toBeLessThanOrEqual(view.width);
    expect(box.y + box.h).toBeLessThanOrEqual(view.height);
  });

  it("does not put two pills on top of each other", () => {
    const placer = new Placer(view, []);
    const first = placer.place(size, pillCandidates(target, size));
    const second = placer.place(size, pillCandidates(target, size));

    expect(overlapArea(first, second)).toBe(0);
  });

  it("when nowhere is free it takes the spot that covers least, still on the screen", () => {
    const everything = [{ x: 0, y: 0, w: 1000, h: 600 }];
    const box = new Placer(view, everything).place(size, pillCandidates(target, size));

    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.x + box.w).toBeLessThanOrEqual(view.width);
  });
});

describe("an arrow tail", () => {
  const target = { x: 500, y: 300, w: 100, h: 40 };

  it("is a short way off, up and to the left when that is free", () => {
    const tail = arrowTail(target, [], view, null);

    expect(tail.x).toBeLessThan(target.x);
    expect(tail.y).toBeLessThan(target.y);
    expect(Math.hypot(tail.x - 550, tail.y - 320)).toBeLessThan(260);
  });

  it("goes another way when the usual one is covered by text", () => {
    const text = { x: 300, y: 150, w: 260, h: 120 }; // up and to the left of the target
    const tail = arrowTail(target, [text], view, null);

    const inside = tail.x > text.x && tail.x < text.x + text.w && tail.y > text.y && tail.y < text.y + text.h;
    expect(inside).toBe(false);
  });

  it("stays on the screen when the target is in a corner", () => {
    const corner = { x: 10, y: 10, w: 80, h: 30 };
    const tail = arrowTail(corner, [], view, { w: 150, h: 38 });

    expect(tail.x).toBeGreaterThanOrEqual(0);
    expect(tail.y).toBeGreaterThanOrEqual(0);
    expect(tail.x).toBeLessThanOrEqual(view.width);
    expect(tail.y).toBeLessThanOrEqual(view.height);
  });

  it("does not run its line across text between it and the target", () => {
    const text = { x: 380, y: 200, w: 100, h: 60 };
    const tail = arrowTail(target, [text], view, null);
    let hits = 0;
    for (let i = 1; i <= 8; i++) {
      const t = i / 10;
      const p = { x: tail.x + (550 - tail.x) * t, y: tail.y + (320 - tail.y) * t };
      if (p.x > text.x && p.x < text.x + text.w && p.y > text.y && p.y < text.y + text.h) hits += 1;
    }
    expect(hits).toBe(0);
  });
});

describe("what counts as in the way", () => {
  const regions: Region[] = [
    { id: 0, kind: "screen", bbox: { x: 0, y: 0, w: 1000, h: 600 } },
    { id: 1, kind: "figure", bbox: { x: 100, y: 100, w: 600, h: 400 } },
    { id: 2, kind: "text", bbox: { x: 50, y: 20, w: 300, h: 40 } },
    { id: 3, kind: "control", bbox: { x: 800, y: 20, w: 100, h: 30 } },
  ];

  it("is text, controls and small marks, not the figure or the whole screen", () => {
    expect(obstaclesOf(regions).map((b) => b.x)).toEqual([50, 800]);
  });

  it("leaves out what is the target itself", () => {
    const target = { x: 800, y: 20, w: 100, h: 30 };

    expect(obstaclesOf(regions, [target]).map((b) => b.x)).toEqual([50]);
  });

  it("reads the screen size from the whole-screen region", () => {
    expect(viewOf(regions)).toEqual({ width: 1000, height: 600 });
    expect(viewOf([])).toEqual({ width: 1920, height: 1080 });
  });
});

describe("soft obstacles and thin lines", () => {
  it("keeps a caption off a handwritten digit that is not a region of its own", async () => {
    const { softObstaclesOf } = await import("../src/render/place");
    const digit: Region = { id: 5, kind: "ink", bbox: { x: 440, y: 380, w: 26, h: 40 } } as Region;
    const placer = new Placer(view, [], softObstaclesOf([digit]));
    // The first candidate sits on the digit; the second is clear.
    const box = placer.place({ w: 100, h: 40 }, [{ x: 420, y: 380 }, { x: 300, y: 380 }]);
    expect(overlapArea(box, digit.bbox)).toBe(0);
  });

  it("prefers a spot clear of detail when there is one", async () => {
    const { softObstaclesOf } = await import("../src/render/place");
    const detail: Region = { id: 6, kind: "detail", bbox: { x: 300, y: 200, w: 400, h: 200 } } as Region;
    const placer = new Placer(view, [], softObstaclesOf([detail]));
    expect(placer.place({ w: 100, h: 40 }, [{ x: 400, y: 250 }, { x: 40, y: 500 }]).x).toBe(40);
  });

  it("reserves a slanted line as a strip, not as its whole bounding box", async () => {
    const { segmentBoxes } = await import("../src/render/place");
    const boxes = segmentBoxes({ x: 0, y: 0 }, { x: 300, y: 200 });
    const placer = new Placer(view, []);
    for (const box of boxes) placer.reserve(box);
    // The corner of the bounding box opposite the line is free.
    const box = placer.place({ w: 60, h: 30 }, [{ x: 20, y: 150 }]);
    expect(box).toMatchObject({ x: 20, y: 150 });
  });
});
