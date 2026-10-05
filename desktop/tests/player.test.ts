// The step player, driven with promises instead of real time.

import { describe, expect, it } from "vitest";
import { StepPlayer } from "../src/render/player";

interface Step {
  name: string;
}

// A show/sleep pair whose promises the test resolves by hand.
function harness() {
  const log: string[] = [];
  const shows: { index: number; animate: boolean; done: () => void }[] = [];
  const sleeps: { ms: number; done: () => void }[] = [];
  let failOn = -1;

  const player = new StepPlayer<Step>({
    show: (index, animate, step) =>
      new Promise<void>((resolve, reject) => {
        log.push(`show ${step.name}${animate ? " animated" : ""}`);
        if (index === failOn) {
          reject(new Error("boom"));
          return;
        }
        shows.push({ index, animate, done: resolve });
      }),
    sleep: (ms) =>
      new Promise<void>((resolve) => {
        log.push(`sleep ${ms}`);
        sleeps.push({ ms, done: resolve });
      }),
    dwell: (step) => step.name.length * 100,
    onError: (error) => log.push(`error ${(error as Error).message}`),
  });

  // Let queued promise callbacks run.
  const settle = async () => {
    for (let i = 0; i < 10; i++) await Promise.resolve();
  };
  return {
    player,
    log,
    shows,
    sleeps,
    settle,
    failOn: (index: number) => {
      failOn = index;
    },
  };
}

describe("the step player", () => {
  it("shows the first step as soon as it arrives, animated", async () => {
    const h = harness();
    h.player.begin();
    h.player.add({ name: "a" });
    await h.settle();

    expect(h.log).toEqual(["show a animated"]);
  });

  it("waits for a drawing to finish and then for the reading time before the next step", async () => {
    const h = harness();
    h.player.begin();
    h.player.add({ name: "one" });
    h.player.add({ name: "two" });
    await h.settle();
    expect(h.log).toEqual(["show one animated"]); // the second waits for the first to finish drawing

    h.shows[0]!.done();
    await h.settle();
    expect(h.log).toEqual(["show one animated", "sleep 300"]); // reading time of "one"

    h.sleeps[0]!.done();
    await h.settle();
    expect(h.log).toEqual(["show one animated", "sleep 300", "show two animated"]);
  });

  it("waits for steps that have not arrived yet and goes on when they do", async () => {
    const h = harness();
    h.player.begin();
    h.player.add({ name: "a" });
    await h.settle();
    h.shows[0]!.done();
    await h.settle();
    h.sleeps[0]!.done();
    await h.settle();
    expect(h.log).toEqual(["show a animated", "sleep 100"]); // nothing more yet: it waits

    h.player.add({ name: "b" });
    await h.settle();

    expect(h.log).toContain("show b animated");
  });

  it("does not wait after the last step once no more can arrive", async () => {
    const h = harness();
    h.player.begin();
    h.player.add({ name: "a" });
    h.player.end();
    await h.settle();
    h.shows[0]!.done();
    await h.settle();

    expect(h.log).toEqual(["show a animated"]); // no reading time at the end
    expect(h.sleeps).toHaveLength(0);
  });

  it("finishes by itself when the stream ends while it is waiting for a step", async () => {
    const h = harness();
    h.player.begin();
    h.player.add({ name: "a" });
    await h.settle();
    h.shows[0]!.done();
    await h.settle();
    h.sleeps[0]!.done();
    await h.settle();

    h.player.end();
    await h.settle();

    expect(h.log).toEqual(["show a animated", "sleep 100"]);
    expect(h.shows).toHaveLength(1);
  });

  it("goes on with the next step when showing one fails", async () => {
    const h = harness();
    h.failOn(0);
    h.player.begin();
    h.player.add({ name: "bad" });
    h.player.add({ name: "good" });
    await h.settle();

    expect(h.log).toEqual(["show bad animated", "error boom", "sleep 300"]);
    h.sleeps[0]!.done();
    await h.settle();
    expect(h.log).toContain("show good animated");
  });

  it("stops when the viewer takes over, even in the middle of a step", async () => {
    const h = harness();
    h.player.begin();
    h.player.add({ name: "one" });
    h.player.add({ name: "two" });
    await h.settle();

    h.player.stop();
    h.shows[0]!.done();
    await h.settle();

    expect(h.log).toEqual(["show one animated"]); // no reading time, no second step
    expect(h.sleeps).toHaveLength(0);
  });

  it("stops while waiting for a step that has not arrived", async () => {
    const h = harness();
    h.player.begin();
    await h.settle();

    h.player.stop();
    h.player.add({ name: "late" });
    await h.settle();

    expect(h.log).toEqual([]);
  });

  it("a new answer replaces the old one and the old playback never shows another step", async () => {
    const h = harness();
    h.player.begin();
    h.player.add({ name: "old1" });
    h.player.add({ name: "old2" });
    await h.settle();

    h.player.begin();
    h.player.add({ name: "new1" });
    h.shows[0]!.done(); // the old drawing finishes late
    await h.settle();

    expect(h.log).toEqual(["show old1 animated", "show new1 animated"]);
    expect(h.player.steps.map((s) => s.name)).toEqual(["new1"]);
  });

  it("remembers the step shown last, and can show any step on request", async () => {
    const h = harness();
    h.player.begin();
    h.player.add({ name: "a" });
    h.player.add({ name: "b" });
    h.player.stop();
    await h.settle();

    const done = h.player.goTo(1, false);
    await h.settle();
    h.shows[h.shows.length - 1]!.done();
    await done;

    expect(h.player.index).toBe(1);
    expect(h.log[h.log.length - 1]).toBe("show b"); // not animated
  });

  it("ignores a request for a step that does not exist", async () => {
    const h = harness();

    await h.player.goTo(5, true);

    expect(h.log).toEqual([]);
  });
});

describe("pausing and resuming", () => {
  it("says when playback starts and when it ends", async () => {
    const h = harness();
    const states: boolean[] = [];
    (h.player as any).deps.onPlaying = (value: boolean) => states.push(value);

    h.player.begin();
    h.player.add({ name: "a" });
    h.player.end();
    await h.settle();
    expect(h.player.playing).toBe(true);
    h.shows[0]!.done();
    await h.settle();

    expect(h.player.playing).toBe(false);
    expect(states).toEqual([true, false]);
  });

  it("is paused when the viewer takes over, and carries on from the next step when resumed", async () => {
    const h = harness();
    h.player.begin();
    h.player.add({ name: "one" });
    h.player.add({ name: "two" });
    h.player.add({ name: "three" });
    await h.settle();
    h.shows[0]!.done();
    await h.settle();

    h.player.stop();
    expect(h.player.playing).toBe(false);
    h.player.resume();
    await h.settle();

    expect(h.player.playing).toBe(true);
    expect(h.log).toContain("show two animated");
    expect(h.log).not.toContain("show one animated twice");
  });

  it("resuming after the last step shown has nothing to play and ends at once", async () => {
    const h = harness();
    h.player.begin();
    h.player.add({ name: "only" });
    h.player.end();
    await h.settle();
    h.shows[0]!.done();
    await h.settle();

    h.player.resume();
    await h.settle();

    expect(h.player.playing).toBe(false);
    expect(h.shows).toHaveLength(1);
  });
});

