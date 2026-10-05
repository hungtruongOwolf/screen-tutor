// Notices when the screen has changed after the tutor pointed at something, and when it has
// settled again. Pure: it is fed grayscale pictures of the screen (about 15 a second) and the
// time, so it is tested without Electron.
//
// What the learner needs:
//   stale  the page changed a lot (a click took them somewhere, a dialog opened, they scrolled):
//          the marks drawn for the old screen mean nothing now and must go at once.
//   fire   the change has finished (nothing moved for a moment): time to look at the screen
//          and say what comes next, without the learner having to ask. This includes small
//          changes such as typing a name into a field.
//
// Three things keep it from firing for no reason:
//   - the mouse pointer: a box around it (and where it just was) is left out of every comparison;
//   - parts of the screen that never stop moving (a playing video, a spinner, a blinking caret
//     area): a cell that changes in most recent frames is left out until it is still again;
//   - tiny differences: a handful of cells is noise.

export interface Frame {
  width: number;
  height: number;
  gray: Uint8Array; // width * height brightness values
}

export interface Pointer {
  x: number; // in frame pixels
  y: number;
}

// The number of cells that differ between two frames (a cell counts when its brightness moved by
// more than `delta`).
export function changedCells(a: Frame, b: Frame, delta = 24): number {
  if (a.width !== b.width || a.height !== b.height) return a.gray.length;
  let changed = 0;
  for (let i = 0; i < a.gray.length; i++) {
    if (Math.abs((a.gray[i] as number) - (b.gray[i] as number)) > delta) changed += 1;
  }
  return changed;
}

// The share of the picture that differs between two frames.
export function changedFraction(a: Frame, b: Frame, delta = 24): number {
  const total = a.gray.length;
  return total === 0 ? 0 : changedCells(a, b, delta) / total;
}

// Brightness of an RGBA or BGRA picture (the channel order hardly matters for a comparison: the
// same weights are used for every picture).
export function toGray(pixels: Uint8Array | Uint8ClampedArray | Buffer, width: number, height: number): Frame {
  const gray = new Uint8Array(width * height);
  for (let i = 0; i < gray.length; i++) {
    const p = i * 4;
    gray[i] = Math.round(0.299 * (pixels[p + 2] as number) + 0.587 * (pixels[p + 1] as number) + 0.114 * (pixels[p] as number));
  }
  return { width, height, gray };
}

// The picture made smaller by averaging blocks of `factor` by `factor` cells. Flicker on single
// pixels (the edges of text as the screen is captured) averages out; real changes do not.
export function shrinkFrame(frame: Frame, factor: number): Frame {
  const width = Math.floor(frame.width / factor);
  const height = Math.floor(frame.height / factor);
  const gray = new Uint8Array(width * height);
  const area = factor * factor;
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      let sum = 0;
      for (let dy = 0; dy < factor; dy++) {
        const row = (y * factor + dy) * frame.width + x * factor;
        for (let dx = 0; dx < factor; dx++) sum += frame.gray[row + dx] as number;
      }
      gray[y * width + x] = Math.round(sum / area);
    }
  }
  return { width, height, gray };
}

export interface DetectorOptions {
  staleAt: number; // share of the picture changed that makes the old marks meaningless
  blockCells: number; // changed cells inside one block that make it a real change (a few typed letters)
  blockMotion: number; // changed cells between two frames inside one block that mean "still moving"
  blocksAcross: number; // the picture is divided into this many blocks across (sparse noise stays below the limits)
  settlePageMs: number; // how long nothing moves after a big change before it counts as finished
  settleSmallMs: number; // the same after a small change (a pause in typing is not the end of it)
  pointerRadius: number; // as a share of the frame width: left out around the mouse pointer
  ignoreBottom: number; // as a share of the height: the taskbar (a clock changes every minute)
  delta: number; // brightness difference that counts as a change
}

export const DEFAULT_OPTIONS: DetectorOptions = {
  staleAt: 0.04,
  blockCells: 6,
  blockMotion: 3,
  blocksAcross: 16,
  settlePageMs: 700,
  settleSmallMs: 1000,
  pointerRadius: 0.035,
  ignoreBottom: 0.05,
  delta: 20,
};

export type DetectorEvent = "stale" | "fire";

// How quickly a cell counts as always moving, and when it counts as still again.
const VOLATILITY_RISE = 0.4;
const MASK_ABOVE = 0.5;
const UNMASK_BELOW = 0.2;
const TRAIL = 4; // pointer positions remembered

export class ChangeDetector {
  private baseline: Frame | undefined;
  private previous: Frame | undefined;
  private volatility: Float32Array | undefined;
  private masked: Uint8Array | undefined;
  private trail: Pointer[] = [];
  private ignored: { x: number; y: number; w: number; h: number }[] = []; // as shares of the frame
  private staleSent = false;
  private peakShare = 0;
  private peakBlock = 0; // most changed cells seen in one block since the baseline
  private lastMotion = 0;
  private moving = false;
  // What the last frame looked like to the detector (for diagnosing a screen that does not behave).
  stats = { cells: 0, active: 0, block: 0, motionBlock: 0, masked: 0, moving: false, stillMs: 0, at: "" };

  constructor(private readonly options: DetectorOptions = DEFAULT_OPTIONS) {}

  // Parts of the screen to leave out of every comparison (the tutor's own windows when they can be recorded).
  setIgnore(rects: { x: number; y: number; w: number; h: number }[]): void {
    this.ignored = rects;
  }

  // The screen as it is now is what the marks were drawn for.
  reset(frame: Frame): void {
    this.baseline = frame;
    this.previous = frame;
    this.staleSent = false;
    this.peakShare = 0;
    this.peakBlock = 0;
    this.moving = false;
    if (!this.volatility || this.volatility.length !== frame.gray.length) {
      this.volatility = new Float32Array(frame.gray.length);
      this.masked = new Uint8Array(frame.gray.length);
    }
  }

  // Feed the next frame; returns what, if anything, just happened.
  update(frame: Frame, now: number, pointer?: Pointer): DetectorEvent[] {
    if (!this.baseline || !this.previous || !this.volatility || !this.masked) {
      this.reset(frame);
      return [];
    }
    if (frame.gray.length !== this.baseline.gray.length) {
      this.reset(frame); // the screen changed size (another display, a new resolution)
      return [];
    }
    if (pointer) {
      this.trail.push(pointer);
      if (this.trail.length > TRAIL) this.trail.shift();
    }
    const { width, height } = frame;
    const reach = this.options.pointerRadius * width;
    const near = (x: number, y: number) =>
      this.trail.some((p) => Math.abs(x - p.x) <= reach && Math.abs(y - p.y) <= reach);
    const blockSize = Math.max(4, Math.floor(width / this.options.blocksAcross));
    const columns = Math.ceil(width / blockSize);
    const rows = Math.ceil(height / blockSize);
    const changedInBlock = new Uint16Array(columns * rows); // differs from the baseline
    const movedInBlock = new Uint16Array(columns * rows); // differs from the last frame
    const lastRow = Math.floor(height * (1 - this.options.ignoreBottom));
    const skip = this.ignored.map((r) => ({ x0: r.x * width, y0: r.y * height, x1: (r.x + r.w) * width, y1: (r.y + r.h) * height }));
    const skipped = (x: number, y: number) => skip.some((r) => x >= r.x0 && x < r.x1 && y >= r.y0 && y < r.y1);

    let fromBaseline = 0;
    let active = 0;
    for (let y = 0; y < height; y++) {
      for (let x = 0; x < width; x++) {
        const i = y * width + x;
        const value = frame.gray[i] as number;
        const moved = Math.abs(value - (this.previous.gray[i] as number)) > this.options.delta ? 1 : 0;

        // Cells that keep changing (video, spinners) are left out until they are still again.
        const v = (this.volatility[i] as number) * (1 - VOLATILITY_RISE) + moved * VOLATILITY_RISE;
        this.volatility[i] = v;
        if (this.masked[i] === 0 && v > MASK_ABOVE) this.masked[i] = 1;
        else if (this.masked[i] === 1 && v < UNMASK_BELOW) this.masked[i] = 0;
        if (this.masked[i] === 1 || y >= lastRow || near(x, y) || (skip.length > 0 && skipped(x, y))) continue;

        active += 1;
        const block = Math.floor(y / blockSize) * columns + Math.floor(x / blockSize);
        if (moved) movedInBlock[block] = (movedInBlock[block] as number) + 1;
        if (Math.abs(value - (this.baseline.gray[i] as number)) > this.options.delta) {
          fromBaseline += 1;
          changedInBlock[block] = (changedInBlock[block] as number) + 1;
        }
      }
    }
    this.previous = frame;
    const mostChanged = changedInBlock.reduce((m, n) => Math.max(m, n), 0);
    const peak = changedInBlock.indexOf(mostChanged);
    // Only movement where the change is counts: a block that carries it, or touches one that does.
    // Flicker elsewhere on the screen is none of our business.
    const carries = (c: number, r: number) =>
      c >= 0 && r >= 0 && c < columns && r < rows && (changedInBlock[r * columns + c] as number) >= this.options.blockCells / 2;
    let mostMoved = 0;
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < columns; c++) {
        let tracked = false;
        for (let dr = -1; dr <= 1 && !tracked; dr++) for (let dc = -1; dc <= 1 && !tracked; dc++) tracked = carries(c + dc, r + dr);
        if (tracked) mostMoved = Math.max(mostMoved, movedInBlock[r * columns + c] as number);
      }
    }
    this.stats = { cells: fromBaseline, active, block: mostChanged, motionBlock: mostMoved, masked: frame.gray.length - active, moving: this.moving, stillMs: Math.round(now - this.lastMotion), at: mostChanged > 0 ? `${Math.round(((peak % columns) + 0.5) / columns * 100)}%,${Math.round(((Math.floor(peak / columns)) + 0.5) / rows * 100)}%` : "" };
    if (active === 0) return [];
    const share = fromBaseline / active;
    this.peakShare = Math.max(this.peakShare, share);
    this.peakBlock = Math.max(this.peakBlock, mostChanged);

    const events: DetectorEvent[] = [];
    if (share >= this.options.staleAt && !this.staleSent) {
      this.staleSent = true;
      events.push("stale");
    }
    // A real change is cells piling up in one place; sparse noise spread over the picture is not.
    if (mostMoved >= this.options.blockMotion && (this.peakBlock >= this.options.blockCells || this.moving)) {
      this.moving = true;
      this.lastMotion = now;
    } else if (this.moving) {
      const settle = this.peakShare >= this.options.staleAt ? this.options.settlePageMs : this.options.settleSmallMs;
      if (now - this.lastMotion >= settle) {
        this.moving = false;
        if (this.peakBlock >= this.options.blockCells) events.push("fire");
        this.peakBlock = 0;
        this.peakShare = 0;
      }
    }
    return events;
  }
}
