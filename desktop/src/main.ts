import { randomUUID } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { app, BrowserWindow, desktopCapturer, globalShortcut, ipcMain, screen, session } from "electron";
import { BackendError, explainTurnStream, narrate } from "./backendClient";
import { captureScreen } from "./capture";
import { Conversation } from "./chat/conversation";
import { loadConfig } from "./config";
import type { Canvas, OverlayUpdate, PanelEvent, Progress, Region, StreamEvent } from "./contract";
import { POINTER_KINDS } from "./contract";
import type { WatcherMessage } from "./follow/watcher";
import { StepPlayer } from "./render/player";
import { speakable } from "./voice/speakable";
import { VoiceController } from "./voice/voiceController";
import { configureWake } from "./voice/intent";
import { findPiper } from "./voice/piper";
import { installVoice } from "./voice/installer";
import { findVoice, type VoicePaths } from "./voice/whisper";

const config = loadConfig(join(__dirname, ".."));
const sessionId = randomUUID();

// One step of the answer as it arrives from the stream.
interface PlayedStep {
  caption: string;
  canvas: Canvas; // the whole canvas at this step
  newIds: string[]; // shapes this step adds or moves: these are animated
}

let overlay: BrowserWindow | undefined;
let panel: BrowserWindow | undefined;
// Voice: the tutor listens and speaks (when the speech recogniser has been downloaded).
let voice: VoiceController | undefined;
const conversation = new Conversation();
let canvas: Canvas = { shapes: [] }; // what is on screen right now
let regions: Region[] = []; // the regions the drawings are anchored to
let stepIndex = -1; // the step on screen (-1: none yet)
let view = { width: 0, height: 0 };
let turn = 0;
let busy = false; // an answer is being fetched
let abort: AbortController | undefined;
let seq = 0; // numbers what is shown so the windows can say which one they finished
// The spoken words of each step of the turn (the caption said as a person would, from a Nemotron model),
// asked for as soon as the step arrives so they are ready when the step is reached.
const narrations = new Map<number, Promise<string | undefined>>();
const NARRATION_WAIT_MS = 2500; // longer than this and the caption itself is read
const overlayWaiters = new Map<number, () => void>();
const typedWaiters = new Map<number, () => void>();

// What the stream said once it ended, kept until the steps have been played so the
// sources and the suggested replies appear after the last step.
let finished: { sources: { title: string; url: string }[]; followUps: string[] } | undefined;

// ---- following a task ------------------------------------------------------------------
// When the learner is getting something done over several screens the tutor states the goal.
// From then on the app watches the screen (a few small pictures a second): when the page
// changes a lot the marks drawn for the old page are taken off at once, and when it has
// settled the tutor looks at the new page by itself and gives the next step (or says the
// learner went the wrong way, or that the task is done). No message is needed per step.
let goal: string | null = null;
let following = true; // the learner can pause the automatic steps
let autoTurns = 0; // automatic turns for this goal
let offTrack = 0; // in a row
let lastProgress: Progress | null | undefined;
let idleTimer: ReturnType<typeof setTimeout> | undefined;
const IDLE_MS = 15 * 60 * 1000; // following pauses by itself after this long without any activity
const MAX_AUTO_TURNS = 25;
// The screen is watched from a hidden window that reads it as a video stream (about 15 pictures a
// second): a still picture of the whole screen takes over half a second, a stream notices a
// changed page in a tenth of one.
let watchWindow: BrowserWindow | undefined;
let watchReady = false;
let watchQueue: WatcherMessage[] = [];
let pointerTimer: ReturnType<typeof setInterval> | undefined;
let readyTimer: ReturnType<typeof setTimeout> | undefined;

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

// ---- windows ---------------------------------------------------------------------

function createOverlay(): BrowserWindow {
  const { bounds } = screen.getPrimaryDisplay();
  const window = new BrowserWindow({
    x: bounds.x,
    y: bounds.y,
    width: bounds.width,
    height: bounds.height,
    transparent: true,
    frame: false,
    resizable: false,
    movable: false,
    focusable: false,
    skipTaskbar: true,
    hasShadow: false,
    alwaysOnTop: true,
    show: false,
    // Windows otherwise trims a frameless window to the work area (screen minus
    // the taskbar), which squashes every drawing vertically.
    enableLargerThanScreen: true,
    webPreferences: {
      preload: join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  window.setAlwaysOnTop(true, "screen-saver");
  // Clicks pass through to whatever is underneath.
  window.setIgnoreMouseEvents(true, { forward: true });
  // Keep the overlay out of screen captures so the AI never sees its own drawings.
  window.setContentProtection(true);
  window.loadFile(join(__dirname, "overlay.html"));
  window.once("ready-to-show", () => {
    window.setBounds(bounds);
    window.showInactive();
    window.setBounds(bounds);
    if (process.env.SCREEN_TUTOR_DEBUG_GEOMETRY) {
      const display = screen.getPrimaryDisplay();
      console.log(
        JSON.stringify({
          displayBounds: display.bounds,
          workArea: display.workArea,
          scaleFactor: display.scaleFactor,
          overlayBounds: window.getBounds(),
          overlayContentBounds: window.getContentBounds(),
        }),
      );
    }
  });
  return window;
}

// The chat: a panel in the corner that stays open, where the learner types and the
// tutor's steps are written. Hidden from screen captures like the overlay.
function createPanel(showAtStart: boolean): BrowserWindow {
  const { workArea } = screen.getPrimaryDisplay();
  const width = 420;
  const height = Math.min(660, workArea.height - 40);
  const window = new BrowserWindow({
    x: workArea.x + workArea.width - width - 16,
    y: workArea.y + workArea.height - height - 16,
    width,
    height,
    minWidth: 340,
    minHeight: 420,
    frame: false,
    resizable: true,
    skipTaskbar: false,
    alwaysOnTop: true,
    show: false,
    backgroundColor: "#14141a",
    title: "screen-tutor",
    webPreferences: {
      preload: join(__dirname, "panelPreload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  window.setAlwaysOnTop(true, "screen-saver");
  window.setContentProtection(true);
  window.loadFile(join(__dirname, "panel.html"));
  window.once("ready-to-show", () => {
    if (showAtStart) {
      window.show();
      emit({ type: "focus" });
    }
  });
  return window;
}

function send(channel: string, payload?: unknown): void {
  overlay?.webContents.send(channel, payload);
}

function emit(event: PanelEvent): void {
  panel?.webContents.send("panel:event", event);
}

function describe(error: unknown): string {
  if (error instanceof BackendError && /answered 40[13]/.test(error.message)) {
    // The token was refused: ask for it again, this time it replaces the one that is stored.
    config.accessToken = undefined;
    setTimeout(askForToken, 500);
    return "The backend did not accept the access token.";
  }
  return error instanceof BackendError ? error.message : `Something went wrong: ${(error as Error).message}`;
}

// A backend that was started before an update ignores what it does not know (the conversation, the
// goal) without a word: the tutor then seems to forget. Ask it what it understands when the app
// starts and say so if it is out of date or not there.
const REQUIRED_FEATURES = ["history", "tasks", "stream"];

async function checkBackend(): Promise<void> {
  let problem = "";
  try {
    const response = await fetch(`${config.backendUrl}/health`, { signal: AbortSignal.timeout(6000) });
    const body = (await response.json()) as { features?: string[] };
    const missing = REQUIRED_FEATURES.filter((f) => !(body.features ?? []).includes(f));
    if (missing.length > 0) {
      problem = `The backend at ${config.backendUrl} is an older version (it does not know: ${missing.join(", ")}), so I would forget the conversation. Stop it and start it again.`;
    }
  } catch {
    problem = `I cannot reach the backend at ${config.backendUrl}. Start it, or set EXPLAIN_BACKEND_URL.`;
  }
  if (!problem) return;
  console.error(`backend check: ${problem}`);
  emit({ type: "error", text: problem });
  openChat(); // so it can be read
  voice?.say(problem.split(". ")[0] + ".");
}

// Ctrl+Shift+E: show the chat, or hide it when it is already in front.
function togglePanel(): void {
  if (!panel) return;
  if (panel.isVisible() && panel.isFocused()) {
    panel.hide();
  } else {
    panel.show();
    panel.focus();
    emit({ type: "focus" });
  }
}

// ---- showing steps -----------------------------------------------------------------

// Plays the steps one after another as they arrive (draw, let the learner read, go
// on). The keys and the panel's buttons take over from it.
const player = new StepPlayer<PlayedStep>({
  show: (index, animate) => showStep(index, animate),
  sleep,
  // With a voice the reading time is the time it takes to say it.
  dwell: (step) => (voice?.speaking ? 450 : Math.min(5000, 1100 + step.caption.length * 38)),
  onError: (error, index) => console.error(`showing step ${index + 1} failed:`, error),
  onPlaying: (playing) => {
    emit({ type: "playing", value: playing });
    if (!playing) maybeFinishTurn();
  },
});

// Show one step: the drawing on the overlay and the caption in the chat. With
// `animate` the new shapes are drawn on stroke by stroke and the caption is typed;
// this resolves when both have finished.
async function showStep(index: number, animate: boolean): Promise<void> {
  const step = player.steps[index];
  if (!step) return;
  stepIndex = index;
  canvas = step.canvas;
  const id = ++seq;
  const update: OverlayUpdate = {
    canvas,
    regions,
    explanation: "",
    view,
    animate: animate ? step.newIds : [],
    seq: id,
    more: player.streaming,
  };
  const wait = (waiters: Map<number, () => void>) =>
    new Promise<void>((resolve) => {
      const timer = setTimeout(resolve, 9000); // never wait for ever
      waiters.set(id, () => {
        clearTimeout(timer);
        resolve();
      });
    });
  const drawn = wait(overlayWaiters);
  const typed = animate ? wait(typedWaiters) : Promise.resolve();
  const spoken = animate && voice?.speaking ? speakStep(index, step.caption) : Promise.resolve();
  emit({
    type: "step",
    index,
    total: player.steps.length,
    streaming: player.streaming,
    caption: step.caption,
    animate,
    seq: id,
  });
  send("overlay:update", update);
  await Promise.all([drawn, typed, spoken]);
  overlayWaiters.delete(id);
  typedWaiters.delete(id);
}

// What is said for a step: the narration if it is there in time, else the caption.
async function speakStep(index: number, caption: string): Promise<void> {
  const ready = narrations.get(index);
  const words = ready
    ? await Promise.race([ready, new Promise<undefined>((resolve) => setTimeout(resolve, NARRATION_WAIT_MS))])
    : undefined;
  await voice?.speak(speakable(words ?? caption));
}

// Starts the narration of a step that has just arrived (after the one before it, which it follows on from).
function requestNarration(index: number, caption: string, question: string): void {
  if (!voice || !config.narration) return;
  const before = index > 0 ? narrations.get(index - 1) : undefined;
  narrations.set(
    index,
    (async () => {
      const earlier = before ? [(await before) ?? ""].filter(Boolean) : [];
      return narrate(config.backendUrl, config.accessToken, { caption, question, earlier });
    })(),
  );
}

// The keys and buttons: they take over from automatic playback.
function nextStep(): void {
  if (player.steps.length === 0) return;
  player.stop();
  void player.goTo(Math.min(stepIndex + 1, player.steps.length - 1), true);
}

function previousStep(): void {
  if (player.steps.length === 0) return;
  player.stop();
  void player.goTo(Math.max(stepIndex - 1, 0), true);
}

function togglePlay(): void {
  if (player.playing) player.stop();
  else if (player.steps.length > 0) player.resume();
}

// ---- a turn -----------------------------------------------------------------------------

function handle(event: StreamEvent): void {
  if (event.event === "regions") {
    regions = event.regions;
    view = { width: event.width, height: event.height };
    canvas = event.canvas;
    // Drawings from earlier turns stay, moved onto the new capture.
    if (canvas.shapes.length > 0) {
      send("overlay:update", { canvas, regions, explanation: "", view, animate: [] } satisfies OverlayUpdate);
    }
    send("overlay:scan", { regions, view });
    emit({ type: "status", text: "Thinking" });
  } else if (event.event === "searching") {
    emit({ type: "status", text: `Searching the web for "${event.query}"` });
  } else if (event.event === "step") {
    player.add({
      caption: event.caption,
      canvas: event.canvas,
      newIds: event.operations.filter((op) => op.op !== "remove").map((op) => op.shape_id),
    });
    requestNarration(player.steps.length - 1, event.caption, "");
  } else if (event.event === "done") {
    finished = { sources: event.sources, followUps: event.follow_ups ?? [] };
    if (event.goal) goal = event.goal;
    lastProgress = event.progress;
  } else if (event.event === "error" && player.steps.length === 0) {
    emit({ type: "error", text: `The model could not answer (${event.status}): ${event.detail}` });
  }
}

// The answer is complete (the stream ended) and the steps have been played or the
// learner paused them: show the sources and the suggested replies.
function maybeFinishTurn(): void {
  if (busy || player.playing || !finished) return;
  if (player.steps.length === 0) {
    finished = undefined; // a silent answer (still waiting for the learner): nothing to add
    return;
  }
  const { sources, followUps } = finished;
  finished = undefined;
  emit({ type: "done", sources, followUps });
}

// A turn: a message from the learner, or (trigger "screen_changed") the app having seen the
// screen change after the last step. Looks at the screen now, sends it with the conversation
// and the goal, and plays the answer as it arrives.
// The cloud backend needs an access token, and a token is a secret that is never part of the download.
// The first time (no token and a backend that is not on this computer) the chat asks for it, and the
// next thing typed there is kept in %APPDATA%\screen-tutor\.env, so this happens once.
function needsToken(): boolean {
  return !config.accessToken && !/^https?:\/\/(localhost|127\.0\.0\.1|\[::1\])/.test(config.backendUrl);
}

function askForToken(): void {
  openChat();
  emit({ type: "auto", text: "One thing before we start: paste your access token here and press Enter. You only do this once." });
}

function saveToken(text: string): void {
  const token = text.trim();
  if (!/^[\w.~+/=-]{8,}$/.test(token)) {
    emit({ type: "error", text: "That does not look like an access token (it has no spaces). Paste it again." });
    return;
  }
  try {
    const folder = join(process.env.APPDATA ?? app.getPath("userData"), "screen-tutor");
    mkdirSync(folder, { recursive: true });
    writeFileSync(join(folder, ".env"), `BACKEND_ACCESS_TOKEN=${token}

`, { flag: "a" });
  } catch (error) {
    console.error("could not save the token:", (error as Error).message);
  }
  config.accessToken = token;
  emit({ type: "reset" }); // the token should not stay on the screen
  emit({ type: "auto", text: "Saved. Ask me anything about your screen." });
  void checkBackend();
}

async function ask(text: string, trigger: "user" | "screen_changed" = "user"): Promise<void> {
  const question = text.trim();
  if (!question || busy) return;
  touch();
  busy = true;
  narrations.clear();
  voice?.setThinking(true);
  finished = undefined;
  lastProgress = undefined;
  stepIndex = -1;
  const history = conversation.history();
  if (trigger === "user") {
    autoTurns = 0;
    conversation.addUser(question);
    emit({ type: "user", text: question });
  } else {
    conversation.addUser("(I did something and the screen changed)");
    emit({ type: "auto", text: "The screen changed. Checking what comes next" });
  }
  emit({ type: "busy", value: true });
  emit({ type: "status", text: "Looking at your screen" });
  const controller = new AbortController();
  abort = controller;

  try {
    // The panel and the overlay are hidden from captures, so this is the screen as the
    // learner sees it, without the tutor's own windows.
    void startWatching().then(() => watchSend({ type: "mark" }));
    const capture = await captureScreen();
    player.begin();
    // The drawing on screen stays and the backend moves it onto this capture (or
    // drops what no longer fits); the regions of the last capture are sent back so
    // it can tell which is which.
    await explainTurnStream(
      config.backendUrl,
      config.accessToken,
      {
        session_id: sessionId,
        question,
        image_base64: capture.image.toString("base64"),
        capture: capture.meta,
        canvas,
        previous_regions: regions,
        turn,
        history,
        goal,
        trigger,
      },
      handle,
      controller.signal,
    );
    turn += 1;
    if (abort === controller) afterTurn();
  } catch (error) {
    if (!controller.signal.aborted && player.steps.length === 0) {
      emit({ type: "error", text: describe(error) });
      voice?.say("Sorry, I could not get an answer.");
    }
  } finally {
    if (abort === controller) {
      busy = false;
      abort = undefined;
      voice?.setThinking(false);
      emit({ type: "busy", value: false });
      emit({ type: "status", text: null });
      conversation.addAssistant(player.steps.map((s) => s.caption));
      // Lets playback finish: it shows the later captions as it reaches them. Nothing is
      // repainted here: that would cut a drawing in progress short.
      player.end();
      maybeFinishTurn();
    }
  }
}

// What the answer said about the task: show it, and decide whether to keep watching.
function afterTurn(): void {
  if (lastProgress === "done") {
    emit({ type: "auto", text: "Task complete" });
    voice?.say("That is done. Nicely done.");
    endTask();
    return;
  }
  if (lastProgress === "off_track") offTrack += 1;
  else if (lastProgress === "continue") offTrack = 0;
  if (offTrack >= 3 && following) {
    following = false;
    emit({ type: "auto", text: "A few steps went off track, so I paused following. Tell me where you are, or press Following to go on" });
  }
  emit({ type: "task", goal, following });
  if (!goal) {
    stopWatching(); // not a task: nothing to follow
    return;
  }
  // From the screen as the answer was started (so anything the learner did while it was
  // being written is noticed) or, failing that, as it is now.
  watchSend({ type: "arm" });
}

function watchSend(message: WatcherMessage): void {
  if (watchWindow && watchReady) watchWindow.webContents.send("watch:message", message);
  else watchQueue.push(message);
}

async function startWatching(): Promise<void> {
  if (watchWindow) return;
  const display = screen.getPrimaryDisplay();
  const window = new BrowserWindow({
    show: false,
    webPreferences: {
      preload: join(__dirname, "watcherPreload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      backgroundThrottling: false,
    },
  });
  watchWindow = window;
  watchReady = false;
  try {
    await window.loadFile(join(__dirname, "watcher.html"));
    const sources = await desktopCapturer.getSources({ types: ["screen"], thumbnailSize: { width: 1, height: 1 } });
    const source = sources.find((s) => s.display_id === String(display.id)) ?? sources[0];
    if (!source) throw new Error("No screen source available to watch");
    window.webContents.send("watch:message", { type: "start", sourceId: source.id } satisfies WatcherMessage);
    // If the stream does not come up (a capture that hangs), start again once rather than
    // sit there never noticing anything.
    readyTimer = setTimeout(() => {
      if (watchReady || watchWindow !== window) return;
      console.error("watcher did not become ready; starting again");
      const pending = watchQueue;
      stopWatching();
      void startWatching().then(() => pending.forEach((m) => watchSend(m)));
    }, 5000);
  } catch (error) {
    console.error("could not start watching the screen:", error);
    stopWatching();
    return;
  }
  // Where the mouse is, so its own movement is not taken for the page changing.
  pointerTimer = setInterval(() => {
    if (!watchWindow || !watchReady) return;
    const point = screen.getCursorScreenPoint();
    const { bounds } = display;
    watchWindow.webContents.send("watch:message", {
      type: "pointer",
      fx: (point.x - bounds.x) / bounds.width,
      fy: (point.y - bounds.y) / bounds.height,
    } satisfies WatcherMessage);
  }, 50);
}

function stopWatching(): void {
  if (readyTimer) clearTimeout(readyTimer);
  readyTimer = undefined;
  if (pointerTimer) clearInterval(pointerTimer);
  pointerTimer = undefined;
  watchQueue = [];
  watchReady = false;
  const window = watchWindow;
  watchWindow = undefined;
  if (window && !window.isDestroyed()) {
    window.webContents.send("watch:message", { type: "stop" } satisfies WatcherMessage);
    window.destroy();
  }
}

// What the hidden window reports.
function onWatch(message: { kind: string; detail?: string }): void {
  if (message.kind !== "debug") console.log(`watcher: ${message.kind}${message.detail ? " " + message.detail : ""}`);
  if (message.kind === "ready") {
    watchReady = true;
    if (readyTimer) clearTimeout(readyTimer);
    readyTimer = undefined;
    const queued = watchQueue;
    watchQueue = [];
    for (const item of queued) watchWindow?.webContents.send("watch:message", item);
  } else if (message.kind === "stale") {
    markStale();
  } else if (message.kind === "fire") {
    fireAuto();
  } else if (message.kind === "error") {
    console.error("watching the screen failed:", message.detail);
  }
}

// The page changed: marks that pointed at the old page go (what builds up stays).
function markStale(): void {
  player.stop();
  canvas = { shapes: canvas.shapes.filter((s) => !(POINTER_KINDS.includes(s.kind) && !s.keep)) };
  send("overlay:stale", canvas);
}

// The change has settled: look at the new page and say what comes next.
function fireAuto(): void {
  if (!following || !goal || busy) return;
  touch();
  if (autoTurns >= MAX_AUTO_TURNS) {
    following = false;
    emit({ type: "auto", text: `I followed ${MAX_AUTO_TURNS} steps and paused. Press Following to go on` });
    emit({ type: "task", goal, following });
    return;
  }
  autoTurns += 1;
  void ask("(the screen changed)", "screen_changed");
}

function toggleFollow(): void {
  if (!goal) return;
  following = !following;
  offTrack = 0;
  emit({ type: "task", goal, following });
  if (following) watchSend({ type: "arm" }); // start from the screen as it is now
}

// Activity: the idle clock starts again. A task nobody has touched for a long while stops being followed.
function touch(): void {
  if (idleTimer) clearTimeout(idleTimer);
  idleTimer = setTimeout(() => {
    if (!goal || !following) return;
    following = false;
    emit({ type: "task", goal, following });
    emit({ type: "auto", text: "Nothing happened for a while, so I paused following. Press Following to go on" });
  }, IDLE_MS);
}

// The learner ends the task: cancel what is being fetched, stop following, take the marks off.
function stopTask(): void {
  if (busy) {
    abort?.abort();
    player.end();
    player.stop();
    busy = false;
    abort = undefined;
    emit({ type: "busy", value: false });
    emit({ type: "status", text: null });
    conversation.addAssistant(player.steps.map((s) => s.caption));
    finished = undefined;
  }
  voice?.cancelSpeech();
  if (goal) emit({ type: "auto", text: "Task ended" });
  endTask();
  markStale();
}

function endTask(): void {
  if (idleTimer) clearTimeout(idleTimer);
  idleTimer = undefined;
  goal = null;
  following = true;
  autoTurns = 0;
  offTrack = 0;
  stopWatching();
  emit({ type: "task", goal: null, following: true });
}

// A spoken request while an answer is still coming: the old answer is dropped quietly, then the new
// request is answered.
function interruptAndAsk(text: string): void {
  voice?.cancelSpeech();
  if (busy) {
    abort?.abort();
    player.end();
    player.stop();
    busy = false;
    abort = undefined;
    emit({ type: "busy", value: false });
    conversation.addAssistant(player.steps.map((s) => s.caption));
    finished = undefined;
  }
  void ask(text);
}

function setFollowing(on: boolean): void {
  if (!goal || following === on) return;
  following = on;
  offTrack = 0;
  emit({ type: "task", goal, following });
  if (on) watchSend({ type: "arm" });
}

function openChat(): void {
  if (!panel) return;
  panel.show();
  panel.focus();
  emit({ type: "focus" });
}

// Stop button: give up on the answer being fetched, keep what has been shown.
function stopAnswer(): void {
  if (!busy) return;
  if (goal && following) {
    // The learner stopped an answer in a task: it must not start again by itself on the next change.
    following = false;
    emit({ type: "task", goal, following });
    emit({ type: "auto", text: "Stopped. Following is paused: press Following to go on, or End task" });
  }
  abort?.abort();
  player.end();
  player.stop();
  busy = false;
  abort = undefined;
  emit({ type: "busy", value: false });
  emit({ type: "status", text: null });
  conversation.addAssistant(player.steps.map((s) => s.caption));
  maybeFinishTurn();
}

// Take the drawings off the screen; the conversation goes on.
function clearDrawings(): void {
  player.stop();
  canvas = { shapes: [] };
  stepIndex = -1;
  send("overlay:clear");
}

// A fresh start: forget the conversation and the drawings.
function newChat(showPanel = true): void {
  abort?.abort();
  abort = undefined;
  busy = false;
  finished = undefined;
  endTask();
  player.reset();
  conversation.reset();
  canvas = { shapes: [] };
  regions = [];
  stepIndex = -1;
  turn = 0;
  send("overlay:clear");
  emit({ type: "reset" });
  if (showPanel) {
    if (panel && !panel.isVisible()) panel.show();
    panel?.focus();
    emit({ type: "focus" });
  }
}

// Screen and microphone capture are only for our own two hidden pages (the screen watcher and the
// voice window); nothing else the app opens may use them.
function allowCapture(url: string, permission: string): boolean {
  return permission === "media" && (url.endsWith("/watcher.html") || url.endsWith("/voiceWindow.html"));
}

function startVoice(voicePaths: VoicePaths): void {
  voice = new VoiceController(
    voicePaths,
    {
      ask: interruptAndAsk,
      openChat,
      closeChat: () => panel?.hide(),
      stopTask,
      newChat: () => newChat(false),
      setFollowing,
      nextStep,
      previousStep,
      clearMarks: clearDrawings,
      taskActive: () => goal !== null && following,
    },
    (line) => console.log(`voice: ${line}`),
    { piper: findPiper(), rate: config.speechRate },
  );
  voice.start().then(() => {
    // Without a microphone the tutor still speaks; the chat is how to ask.
    if (voice && !voice.micWorking) openChat();
  }).catch((error: Error) => {
    console.error("voice could not start:", error.message);
    voice?.stop();
    voice = undefined;
    openChat(); // the chat is still a way in
  });
}

// The first start: download the speech models (about 200 MB, once), showing the progress in the
// chat, then start the voice without a restart. The chat works meanwhile.
async function setUpVoice(): Promise<void> {
  emit({ type: "auto", text: "Setting up the voice (one time, about 200 MB). You can already type." });
  let last = "";
  try {
    await installVoice({
      progress: (what, fraction) => {
        const text = fraction === undefined ? `${what}…` : `${what}… ${Math.round(fraction * 100)} %`;
        if (text !== last) {
          emit({ type: "status", text });
          if (fraction === undefined || fraction === 0 || fraction >= 1) console.log(`voice setup: ${text}`);
        }
        last = text;
      },
    });
    emit({ type: "status", text: null });
    const found = findVoice();
    if (!found) throw new Error("the files are not where they should be");
    startVoice(found);
    console.log("voice setup: done");
    emit({ type: "auto", text: `The voice is ready. Say "Hey ${config.wakeWords[0] ?? "Nova"}" and ask.` });
  } catch (error) {
    emit({ type: "status", text: null });
    emit({ type: "error", text: `I could not set up the voice (${(error as Error).message}). Typing works; restart the app to try again.` });
  }
}

app.whenReady().then(() => {
  session.defaultSession.setPermissionRequestHandler((contents, permission, callback) =>
    callback(allowCapture(contents.getURL(), permission)),
  );
  session.defaultSession.setPermissionCheckHandler((contents, permission) =>
    allowCapture(contents?.getURL() ?? "", permission),
  );
  overlay = createOverlay();
  // With a speech recogniser installed the tutor is voice first: the chat opens when asked
  // ("open chat", Ctrl+Shift+E). Without one, the chat is the way in.
  configureWake(config.wakeWords);
  const voiceWanted = process.env.VOICE !== "off";
  const voicePaths = voiceWanted ? findVoice() : undefined;
  panel = createPanel(!voicePaths);
  if (voicePaths) startVoice(voicePaths);
  else if (voiceWanted) void setUpVoice(); // the first start: the speech models are downloaded once

  ipcMain.on("panel:send", (_event, text: string) => {
    if (needsToken()) saveToken(String(text ?? ""));
    else void ask(String(text ?? ""));
  });
  ipcMain.on("panel:new-chat", () => newChat());
  ipcMain.on("panel:clear-drawings", clearDrawings);
  ipcMain.on("panel:hide", () => panel?.hide());
  ipcMain.on("panel:stop", stopAnswer);
  ipcMain.on("panel:go-to", (_event, index: number) => {
    player.stop();
    void player.goTo(Number(index), true);
  });
  ipcMain.on("panel:step", (_event, direction: "prev" | "next") => {
    if (direction === "next") nextStep();
    else previousStep();
  });
  ipcMain.on("panel:toggle-play", togglePlay);
  ipcMain.on("panel:toggle-follow", toggleFollow);
  ipcMain.on("panel:end-task", stopTask);
  ipcMain.on("watch:event", (_event, message: { kind: string; detail?: string }) => onWatch(message));
  ipcMain.on("panel:typed", (_event, finishedSeq: number) => typedWaiters.get(finishedSeq)?.());
  ipcMain.on("overlay:animation-done", (_event, finishedSeq: number) => overlayWaiters.get(finishedSeq)?.());

  setTimeout(() => (needsToken() ? askForToken() : void checkBackend()), 3000); // after the windows are up
  const { explain, newChat: newChatKey, clear, stop, mute, talk, debug, quit, next, previous } = config.hotkeys;
  const registered = [
    globalShortcut.register(explain, togglePanel),
    globalShortcut.register(newChatKey, () => newChat()),
    globalShortcut.register(clear, clearDrawings),
    globalShortcut.register(stop, stopTask),
    globalShortcut.register(mute, () => voice?.toggleMute()),
    globalShortcut.register(talk, () => voice?.listenNow()),
    globalShortcut.register(next, nextStep),
    globalShortcut.register(previous, previousStep),
    globalShortcut.register(debug, () => send("overlay:toggle-debug")),
    globalShortcut.register(quit, () => app.quit()),
  ];
  if (registered.includes(false)) {
    console.error("Some hotkeys could not be registered (already in use by another app?)");
  }
  console.log(
    `screen-tutor running. Chat: ${explain}  New chat: ${newChatKey}  Clear drawings: ${clear}  Stop task: ${stop}  Mute mic: ${mute}  Talk now: ${talk}  Next step: ${next}  Previous step: ${previous}  Debug regions: ${debug}  Quit: ${quit}  Backend: ${config.backendUrl}`,
  );
});

app.on("will-quit", () => {
  globalShortcut.unregisterAll();
  stopWatching();
  voice?.stop();
});
app.on("window-all-closed", () => app.quit());
