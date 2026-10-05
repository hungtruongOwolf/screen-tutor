import { describe, expect, it } from "vitest";
import { ChangeDetector, changedCells, changedFraction, shrinkFrame, toGray, type Frame, type Pointer } from "../src/follow/changeDetector";

const W = 200;
const H = 100;

function frame(fill: (x: number, y: number) => number): Frame {
  const gray = new Uint8Array(W * H);
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) gray[y * W + x] = fill(x, y);
  return { width: W, height: H, gray };
}

const blank = () => frame(() => 240);
// a dark block at the left covering the given share of the width, full height
const withBlock = (share: number) => frame((x) => (x < W * share ? 30 : 240));
// a small dark patch (like a few typed letters): w by h cells at (x0, y0)
const patch = (x0: number, y0: number, w: number, h: number) =>
  frame((x, y) => (x >= x0 && x < x0 + w && y >= y0 && y < y0 + h ? 30 : 240));

describe("how much of the screen changed", () => {
  it("is nothing for the same picture and everything for a different one", () => {
    expect(changedFraction(blank(), blank())).toBe(0);
    expect(changedFraction(blank(), frame(() => 20))).toBe(1);
  });

  it("counts the cells that moved", () => {
    expect(changedFraction(blank(), withBlock(0.25))).toBeCloseTo(0.25);
    expect(changedCells(blank(), patch(10, 10, 6, 4))).toBe(24);
  });

  it("ignores tiny brightness drift", () => {
    expect(changedCells(blank(), frame(() => 232))).toBe(0);
  });

  it("treats pictures of different sizes as completely changed", () => {
    expect(changedFraction(blank(), { width: 2, height: 2, gray: new Uint8Array(4) })).toBe(1);
  });
});

describe("making a picture smaller", () => {
  it("averages blocks of cells", () => {
    const f: Frame = { width: 4, height: 2, gray: Uint8Array.from([0, 100, 200, 200, 100, 0, 200, 200]) };

    const small = shrinkFrame(f, 2);

    expect([small.width, small.height]).toEqual([2, 1]);
    expect(Array.from(small.gray)).toEqual([50, 200]);
  });

  it("makes single-pixel flicker disappear but keeps a real patch", () => {
    const base = frame(() => 240);
    const flicker = frame((x, y) => ((x * 7 + y * 13) % 53 === 0 ? 120 : 240)); // scattered pixels half as bright
    const patch8 = frame((x, y) => (x < 8 && y < 8 ? 30 : 240));

    expect(changedCells(shrinkFrame(base, 4), shrinkFrame(flicker, 4), 20)).toBe(0);
    expect(changedCells(shrinkFrame(base, 4), shrinkFrame(patch8, 4), 20)).toBe(4);
  });
});

describe("reading pixels", () => {
  it("turns BGRA bytes into brightness", () => {
    const pixels = Uint8Array.from([0, 0, 255, 255, 255, 255, 255, 255]); // red, then white
    const gray = toGray(pixels, 2, 1).gray;

    expect(gray[0]).toBeGreaterThan(70);
    expect(gray[0]).toBeLessThan(80);
    expect(gray[1]).toBe(255);
  });
});

// ~15 frames a second
const FRAME_MS = 66;

function play(detector: ChangeDetector, frames: Frame[], start: number, pointer?: (i: number) => Pointer | undefined) {
  const events: string[] = [];
  frames.forEach((f, i) => {
    const t = start + i * FRAME_MS;
    for (const e of detector.update(f, t, pointer?.(i))) events.push(`${e}@${Math.round(t)}`);
  });
  return events;
}
const repeat = (f: Frame, n: number) => Array.from({ length: n }, () => f);

describe("the change detector", () => {
  it("says nothing while the screen stays as it was", () => {
    const d = new ChangeDetector();
    d.reset(blank());

    expect(play(d, repeat(blank(), 60), 0)).toEqual([]);
  });

  it("calls the marks stale on the very first frame of a big change, and fires once it has settled", () => {
    const d = new ChangeDetector();
    d.reset(blank());

    const events = play(d, [...repeat(blank(), 3), ...repeat(withBlock(0.5), 30)], 0);

    expect(events[0]).toBe("stale@198"); // the first changed frame: no waiting for anything
    expect(events[1]).toMatch(/^fire@/);
    expect(events).toHaveLength(2);
  });

  it("notices typing: a small change that stays, after the typing pauses", () => {
    const d = new ChangeDetector();
    d.reset(blank());
    const typing = [patch(20, 20, 4, 4), patch(20, 20, 8, 4), patch(20, 20, 12, 4), patch(20, 20, 16, 4)];

    const events = play(d, [...repeat(blank(), 3), ...typing, ...repeat(typing[3]!, 30)], 0);

    expect(events).toHaveLength(1);
    expect(events[0]).toMatch(/^fire@/); // fires, but the marks are not stale: it is only a few letters
  });

  it("waits through a pause between words (a small change needs a longer stillness)", () => {
    const d = new ChangeDetector();
    d.reset(blank());
    const word = patch(20, 20, 16, 4);

    const events = play(d, [word, ...repeat(word, 8)], 0); // 0.5 s still: not yet

    expect(events).toEqual([]);
  });

  it("ignores a hover: a few cells at the pointer", () => {
    const d = new ChangeDetector();
    d.reset(blank());
    const pointer = (i: number) => ({ x: 103 + i, y: 53 });
    const frames = Array.from({ length: 30 }, (_, i) => patch(100 + i, 48, 6, 10)); // the arrow image moving with it

    expect(play(d, frames, 0, pointer)).toEqual([]);
  });

  it("ignores a part of the screen that never stops moving (a playing video)", () => {
    const d = new ChangeDetector();
    d.reset(blank());
    const video = (n: number) => frame((x, y) => (x > 100 && y > 30 && y < 90 ? (n % 2 === 0 ? 40 : 220) : 240));

    const events = play(d, Array.from({ length: 80 }, (_, n) => video(n)), 0);

    // the first frames differ from the baseline, but once the area is known to be moving it is left out
    expect(events.filter((e) => e.startsWith("fire")).length).toBeLessThanOrEqual(1);
    const later = play(d, Array.from({ length: 80 }, (_, n) => video(n)), 6000);
    expect(later).toEqual([]);
  });

  it("still notices a click that changes the page while a video plays elsewhere", () => {
    const d = new ChangeDetector();
    const video = (n: number, left: number) =>
      frame((x, y) => (x > 140 && y > 30 && y < 90 ? (n % 2 === 0 ? 40 : 220) : x < left ? 30 : 240));
    d.reset(video(0, 0));
    play(d, Array.from({ length: 60 }, (_, n) => video(n, 0)), 0); // the video area becomes known
    d.reset(video(60, 0)); // the next answer arms it again

    const events = play(d, Array.from({ length: 40 }, (_, n) => video(n, 100)), 4000);

    expect(events[0]).toMatch(/^stale@/);
    expect(events.some((e) => e.startsWith("fire"))).toBe(true);
  });

  it("starts again from a new baseline", () => {
    const d = new ChangeDetector();
    d.reset(blank());
    play(d, repeat(withBlock(0.5), 30), 0);

    d.reset(withBlock(0.5));

    expect(play(d, repeat(withBlock(0.5), 30), 3000)).toEqual([]);
  });

  it("starts over when the screen changes size", () => {
    const d = new ChangeDetector();
    d.reset(blank());
    const other: Frame = { width: 10, height: 10, gray: new Uint8Array(100).fill(240) };

    expect(d.update(other, 0)).toEqual([]);
    expect(d.update(other, 66)).toEqual([]);
  });
});


describe("noise and the taskbar", () => {
  it("is not kept moving by sparse noise spread over the screen (frames are averaged down first)", () => {
    const d = new ChangeDetector();
    d.reset(shrinkFrame(blank(), 4));
    // a few isolated pixels flicker somewhere new every frame (capture noise, a clock)
    const noisy = (n: number) =>
      shrinkFrame(
        frame((x, y) => {
          const flicker = (x * 7 + y * 13 + n * 31) % 997 < 3; // about 0.3 percent of pixels, scattered
          const inPatch = x >= 20 && x < 44 && y >= 20 && y < 28; // typed letters
          return inPatch ? 30 : flicker ? 100 : 240;
        }),
        4,
      );
    const frames = [...repeat(shrinkFrame(blank(), 4), 3), ...Array.from({ length: 50 }, (_, n) => noisy(n))];

    const events = play(d, frames, 0);

    expect(events.filter((e) => e.startsWith("fire"))).toHaveLength(1); // the typed patch, once it is still
  });

  it("ignores changes in the taskbar at the bottom of the screen", () => {
    const d = new ChangeDetector();
    d.reset(blank());
    const clock = patch(150, 96, 40, 4); // bottom 4 percent of the height

    expect(play(d, [...repeat(blank(), 3), ...repeat(clock, 40)], 0)).toEqual([]);
  });

  it("is not fooled by a change that is only isolated specks", () => {
    const d = new ChangeDetector();
    d.reset(blank());
    const specks = frame((x, y) => ((x * 7 + y * 13) % 997 < 3 ? 30 : 240));

    expect(play(d, [...repeat(blank(), 3), ...repeat(specks, 40)], 0)).toEqual([]);
  });
});

describe("leaving out parts of the screen", () => {
  it("does not take a change inside an ignored rectangle (the tutor's own window) for a page change", () => {
    const d = new ChangeDetector();
    d.reset(blank());
    d.setIgnore([{ x: 0, y: 0, w: 0.6, h: 1 }]); // the left 60 %

    const events = play(d, [...repeat(blank(), 3), ...repeat(withBlock(0.5), 30)], 0);

    expect(events).toEqual([]);
  });

  it("still sees a change outside it", () => {
    const d = new ChangeDetector();
    d.reset(blank());
    d.setIgnore([{ x: 0, y: 0, w: 0.3, h: 1 }]);

    const events = play(d, [...repeat(blank(), 3), ...repeat(frame((x) => (x > W * 0.5 ? 30 : 240)), 30)], 0);

    expect(events.some((e) => e.startsWith("fire"))).toBe(true);
  });
});
