// Runs inside the overlay page: paints whatever the main process sends, and plays
// the drawing animation for the shapes of a new step.

import type { Canvas, OverlayUpdate, Region } from "../contract";
import { planAnimation, playAnimation, type Playback, type Pt } from "../render/animate";
import { renderCanvasSvg, renderRegionsDebugSvg, renderScanSvg } from "../render/renderCanvas";

declare global {
  interface Window {
    overlayApi: {
      onUpdate(callback: (update: OverlayUpdate) => void): void;
      onClear(callback: () => void): void;
      onStale(callback: (canvas: Canvas) => void): void;
      onToggleDebug(callback: () => void): void;
      onScan(callback: (scan: { regions: Region[]; view: { width: number; height: number } }) => void): void;
      animationDone(seq: number): void;
    };
  }
}

const canvasEl = document.getElementById("canvas") as HTMLDivElement;
const scanEl = document.getElementById("scan") as HTMLDivElement;

let lastUpdate: OverlayUpdate | undefined;
let showDebug = false;
let playback: Playback | undefined;
let lastCursor: Pt | undefined; // where the cursor was left, so the next step starts from there
let scanTimer: ReturnType<typeof setTimeout> | undefined;

function clearScan(): void {
  if (scanTimer !== undefined) clearTimeout(scanTimer);
  scanTimer = undefined;
  scanEl.innerHTML = "";
}

function paint(): SVGSVGElement | null {
  if (!lastUpdate) {
    canvasEl.innerHTML = "";
    return null;
  }
  canvasEl.innerHTML =
    renderCanvasSvg(lastUpdate.canvas, lastUpdate.regions, lastUpdate.view) +
    (showDebug ? renderRegionsDebugSvg(lastUpdate.regions, lastUpdate.view) : "");
  return canvasEl.querySelector("svg");
}

window.overlayApi.onUpdate((update) => {
  playback?.cancel();
  clearScan();
  lastUpdate = update;
  const svg = paint();

  const animateIds = new Set(update.animate ?? []);
  const fresh = update.canvas.shapes.filter((s) => animateIds.has(s.id));
  const waits: Promise<void>[] = [];

  if (animateIds.size > 0) {
    if (svg && fresh.length > 0) {
      const start = lastCursor ?? { x: update.view.width / 2, y: update.view.height * 0.9 };
      const plan = planAnimation(fresh, update.regions, { startCursor: start });
      const last = plan.items[plan.items.length - 1];
      if (last) lastCursor = last.path[last.path.length - 1];
      playback = playAnimation(svg, plan);
      waits.push(playback.finished);
    }
  }

  if (update.seq !== undefined) {
    const seq = update.seq;
    void Promise.all(waits).then(() => window.overlayApi.animationDone(seq));
  }
});

// The regions flash in one after another while the model is still thinking.
window.overlayApi.onScan(({ regions, view }) => {
  clearScan();
  scanEl.innerHTML = renderScanSvg(regions, view);
  scanTimer = setTimeout(clearScan, 2600);
});

window.overlayApi.onToggleDebug(() => {
  showDebug = !showDebug;
  paint();
});

window.overlayApi.onClear(() => {
  playback?.cancel();
  clearScan();
  lastUpdate = undefined;
  lastCursor = undefined;
  paint();
});

// The page changed: the pointing marks drawn for the old screen fade away and what is kept
// (formulas, squares, diagrams) stays.
window.overlayApi.onStale((canvas) => {
  playback?.cancel();
  if (!lastUpdate) return;
  lastUpdate = { ...lastUpdate, canvas, animate: [] };
  canvasEl.style.transition = "opacity 0.12s";
  canvasEl.style.opacity = "0";
  setTimeout(() => {
    canvasEl.style.transition = "none";
    paint();
    canvasEl.style.opacity = "1";
  }, 130);
});

