// Runs inside a hidden window: looks at the screen as a video stream (about 15 pictures a
// second, hidden windows excluded) and tells the main process when the page has changed
// ("stale") and when the change has settled ("fire"). A still picture of the whole screen takes
// more than half a second to get; a stream is what makes the marks go within a tenth of one.

import { ChangeDetector, changedCells, shrinkFrame, toGray, type Frame } from "./changeDetector";

declare global {
  interface Window {
    watcherApi: {
      onMessage(callback: (message: WatcherMessage) => void): void;
      send(message: { kind: "ready" | "stale" | "fire" | "error" | "debug"; detail?: string }): void;
    };
  }
}

export type WatcherMessage =
  | { type: "start"; sourceId: string }
  | { type: "mark" } // the screen as it is now, kept (a question was just asked)
  | { type: "arm" } // the marks were drawn: watch for change from here
  | { type: "pointer"; fx: number; fy: number } // the mouse, as a share of the screen
  | { type: "debug" } // report what the detector sees, twice a second
  | { type: "stop" };

const FRAME_MS = 66;
const MAX_WIDTH = 640;
const MAX_HEIGHT = 360;
const SHRINK = 4; // frames are compared at a quarter of that size, averaged
const MIN_CHANGED_CELLS = 8; // fewer cells than this is noise, not a change that happened during the answer

const detector = new ChangeDetector();
const video = document.createElement("video");
const canvas = document.createElement("canvas");
const context = canvas.getContext("2d", { willReadFrequently: true }) as CanvasRenderingContext2D;

let timer: ReturnType<typeof setInterval> | undefined;
let latest: Frame | undefined;
let marked: Frame | undefined;
let armed = false;
let pointer: { x: number; y: number } | undefined;
let debugging = false;
let frames = 0;

function look(): Frame | undefined {
  if (!video.videoWidth || !video.videoHeight) return undefined;
  if (canvas.width !== video.videoWidth || canvas.height !== video.videoHeight) {
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
  }
  context.drawImage(video, 0, 0);
  const pixels = context.getImageData(0, 0, canvas.width, canvas.height);
  return shrinkFrame(toGray(pixels.data, canvas.width, canvas.height), SHRINK);
}

function tick(): void {
  const frame = look();
  if (!frame) return;
  latest = frame;
  if (!armed) return;
  const at = pointer ? { x: pointer.x * frame.width, y: pointer.y * frame.height } : undefined;
  for (const event of detector.update(frame, performance.now(), at)) window.watcherApi.send({ kind: event });
  frames += 1;
  if (debugging && frames % 8 === 0) window.watcherApi.send({ kind: "debug", detail: JSON.stringify(detector.stats) });
}

async function start(sourceId: string): Promise<void> {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: false,
      video: {
        mandatory: {
          chromeMediaSource: "desktop",
          chromeMediaSourceId: sourceId,
          maxWidth: MAX_WIDTH,
          maxHeight: MAX_HEIGHT,
          maxFrameRate: 15,
        },
      } as unknown as MediaTrackConstraints,
    });
    video.srcObject = stream;
    video.muted = true;
    await video.play();
    timer = setInterval(tick, FRAME_MS);
    window.watcherApi.send({ kind: "ready" });
  } catch (error) {
    window.watcherApi.send({ kind: "error", detail: (error as Error).message });
  }
}

function stop(): void {
  if (timer) clearInterval(timer);
  timer = undefined;
  armed = false;
  (video.srcObject as MediaStream | null)?.getTracks().forEach((track) => track.stop());
  video.srcObject = null;
}

window.watcherApi.onMessage((message) => {
  switch (message.type) {
    case "start":
      void start(message.sourceId);
      break;
    case "mark":
      marked = latest;
      break;
    case "arm": {
      const now = look() ?? latest;
      if (!now) return;
      // If the screen already changed while the answer was being written, measure from the screen
      // it was written for, so the change is noticed straight away.
      const base = marked && changedCells(marked, now) >= MIN_CHANGED_CELLS ? marked : now;
      detector.reset(base);
      armed = true;
      break;
    }
    case "pointer":
      pointer = { x: message.fx, y: message.fy };
      break;
    case "debug":
      debugging = true;
      break;
    case "stop":
      stop();
      break;
  }
});
