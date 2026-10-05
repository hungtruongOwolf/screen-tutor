// The voice side of the app (main process): a small window that listens to the microphone and
// speaks, a local speech recogniser, and the decisions about what an utterance means. The rest of
// the app only hears about it through VoiceActions.

import { BrowserWindow, ipcMain, screen } from "electron";
import { join } from "node:path";
import { pcmToWav } from "./audio";
import { routeUtterance, wakeLabel, type Command } from "./intent";
import type { OrbState, VoiceEvent, VoiceMessage } from "./protocol";
import { PiperTts, type PiperPaths } from "./piper";
import { splitSentences } from "./speakable";
import { WhisperServer, type VoicePaths } from "./whisper";

export interface VoiceActions {
  ask(text: string): void; // a request to answer (interrupting an answer in progress)
  openChat(): void;
  closeChat(): void;
  stopTask(): void;
  newChat(): void;
  setFollowing(on: boolean): void;
  nextStep(): void;
  previousStep(): void;
  clearMarks(): void;
  taskActive(): boolean; // a task is being followed
}

const ENGAGED_MS = 12_000; // how long after the tutor speaks, or is spoken to, a follow-up needs no wake word
const REOPEN_MS = 500; // the microphone opens again this long after the tutor stops talking (its own echo)

export class VoiceController {
  private window: BrowserWindow | undefined;
  private readonly whisper: WhisperServer;
  private muted = false;
  private spokenReplies = true;
  private engagedUntil = 0;
  private nextId = 1;
  private waiters = new Map<number, () => void>();
  private speakingId = 0;
  private lastSpoken = "";
  private state: OrbState = "starting";
  private heardTimer: ReturnType<typeof setTimeout> | undefined;
  private requests = 0;
  private thinking = false;
  private listeners: { settled?: () => void } = {};
  micWorking = false; // the microphone is open (the tutor can still speak without one)
  micProblem = "";

  private readonly piper: PiperTts | undefined;

  // `speech`: the Piper voice, if it is installed (otherwise the Windows voices are used), and how
  // much faster than normal to talk.
  constructor(
    paths: VoicePaths,
    private readonly actions: VoiceActions,
    private readonly log: (line: string) => void = () => undefined,
    private readonly speech: { piper?: PiperPaths; rate: number } = { rate: 1.2 },
  ) {
    this.whisper = new WhisperServer(paths, log);
    this.piper = speech.piper ? new PiperTts(speech.piper, speech.rate, log) : undefined;
  }

  // The orb's window, for the recording mode (it can then be seen by a screen recorder).
  get orbWindow(): BrowserWindow | undefined {
    return this.window;
  }

  // Starts the recogniser and the window; resolves once the microphone has opened or failed to (check
  // micWorking: without a microphone the tutor can still speak, and the chat is the way in).
  async start(): Promise<void> {
    const recogniser = this.whisper.start();
    this.piper?.warm();
    const display = screen.getPrimaryDisplay().workArea;
    const width = 430;
    const height = 84;
    const window = new BrowserWindow({
      x: display.x + 16,
      y: display.y + display.height - height - 16,
      width,
      height,
      frame: false,
      transparent: true,
      resizable: false,
      movable: true,
      focusable: false,
      skipTaskbar: true,
      alwaysOnTop: true,
      hasShadow: false,
      show: false,
      webPreferences: {
        preload: join(__dirname, "voicePreload.js"),
        contextIsolation: true,
        nodeIntegration: false,
        sandbox: true,
        backgroundThrottling: false,
        autoplayPolicy: "no-user-gesture-required",
      },
    });
    this.window = window;
    window.setAlwaysOnTop(true, "screen-saver");
    window.setContentProtection(true); // not in screen captures
    ipcMain.on("voice:event", (_event, message: VoiceEvent) => void this.onEvent(message));
    await window.loadFile(join(__dirname, "voiceWindow.html"));
    window.showInactive();

    const opened = new Promise<void>((resolve) => {
      this.listeners = { settled: resolve };
      setTimeout(resolve, 12_000);
    });
    this.send({ type: "start-mic" });
    await Promise.all([recogniser, opened]);
    this.idle();
  }

  get speaking(): boolean {
    return this.spokenReplies && !this.muted;
  }

  stop(): void {
    this.whisper.stop();
    this.piper?.stop();
    this.window?.destroy();
    this.window = undefined;
  }

  // ---- what the rest of the app calls ----------------------------------------------------------

  // Says it aloud; resolves when it has been said (or cut short).
  speak(text: string): Promise<void> {
    if (!this.spokenReplies || !text.trim() || !this.window) return Promise.resolve();
    this.lastSpoken = text;
    const id = this.nextId++;
    this.speakingId = id;
    this.send({ type: "gate", open: false });
    this.ui("speaking", text, "Say “stop” or press Ctrl+Shift+S to interrupt");
    return new Promise<void>((resolve) => {
      const timer = setTimeout(() => this.finishSpeech(id), 45_000); // never wait for ever
      this.waiters.set(id, () => {
        clearTimeout(timer);
        resolve();
      });
      if (this.piper) void this.speakWithPiper(id, text);
      else this.send({ type: "speak", id, text, rate: this.speech.rate });
    });
  }

  // A sentence at a time: the first is playing while the next ones are being made.
  private async speakWithPiper(id: number, text: string): Promise<void> {
    const parts = splitSentences(text);
    const made = parts.map((part) => (this.piper as PiperTts).synthesize(part));
    for (let i = 0; i < parts.length; i++) {
      if (this.speakingId !== id) return; // cut short
      try {
        const sound = await made[i];
        if (this.speakingId !== id || !sound) return;
        this.send({ type: "play", id, pcm: sound.pcm.slice().buffer, sampleRate: sound.sampleRate, last: i === parts.length - 1 });
      } catch (error) {
        // The voice failed: the Windows voice says the rest.
        this.log(`piper failed: ${(error as Error).message}`);
        this.send({ type: "speak", id, text: parts.slice(i).join(" "), rate: this.speech.rate });
        return;
      }
    }
  }

  // Said without waiting for the end.
  say(text: string): void {
    void this.speak(text);
  }

  cancelSpeech(): void {
    if (this.speakingId) {
      this.send({ type: "cancel-speech" });
      this.finishSpeech(this.speakingId);
    }
  }

  // The answer is being fetched.
  setThinking(on: boolean): void {
    this.thinking = on;
    if (on && !this.speakingId) this.ui("thinking", "Thinking");
    else if (!on && !this.speakingId) this.idle();
  }

  toggleMute(): void {
    if (!this.micWorking) {
      // Nothing to mute: the click asks for another try.
      this.ui("starting", "Looking for the microphone", "");
      this.send({ type: "retry-mic" });
      return;
    }
    this.muted = !this.muted;
    this.cancelSpeech();
    this.send({ type: "gate", open: !this.muted });
    this.idle();
  }

  // Push to talk: the next thing said is for the tutor, whatever it starts with.
  listenNow(): void {
    this.cancelSpeech();
    this.muted = false;
    this.engagedUntil = Date.now() + ENGAGED_MS;
    this.send({ type: "gate", open: true });
    this.ui("listening", "Listening", "Go ahead");
  }

  // ---- the microphone ------------------------------------------------------------------------

  private async onEvent(event: VoiceEvent): Promise<void> {
    switch (event.kind) {
      case "ready": {
        this.log(`microphone: ${event.voices[0] ?? "open"}; voices: ${event.voices.slice(1).join(", ") || "none"}`);
        const recovered = !this.micWorking && this.micProblem !== "";
        this.micWorking = true;
        this.micProblem = "";
        this.listeners.settled?.();
        if (recovered) this.heard("Microphone is working now", "");
        else this.idle();
        break;
      }
      case "mic-error":
        this.log(`microphone: ${event.detail}`);
        this.micWorking = false;
        this.micProblem = event.detail;
        this.listeners.settled?.();
        this.ui("error", "Can't hear you: no microphone", `${event.detail} Click here to try again.`);
        break;
      case "speech-start":
        if (!this.muted && !this.speakingId && !this.thinking && this.state === "listening") this.ui("hearing", "…");
        break;
      case "speak-end":
        this.finishSpeech(event.id);
        break;
      case "toggle-mute":
        this.toggleMute();
        break;
      case "utterance":
        await this.onUtterance(new Int16Array(event.pcm));
        break;
      case "level":
        break;
    }
  }

  private finishSpeech(id: number): void {
    const waiter = this.waiters.get(id);
    this.waiters.delete(id);
    if (this.speakingId === id) {
      this.speakingId = 0;
      this.engagedUntil = Date.now() + ENGAGED_MS;
      setTimeout(() => {
        if (!this.speakingId && !this.muted) this.send({ type: "gate", open: true });
      }, REOPEN_MS);
      if (this.thinking) this.ui("thinking", "Thinking");
      else this.idle();
    }
    waiter?.();
  }

  private async onUtterance(pcm: Int16Array): Promise<void> {
    if (this.muted || this.speakingId) return;
    this.ui("thinking", "…");
    let text = "";
    try {
      text = await this.whisper.transcribe(pcmToWav(pcm));
    } catch (error) {
      this.log(`recognition failed: ${(error as Error).message}`);
      this.idle();
      return;
    }
    const intent = routeUtterance(text, { inConversation: Date.now() < this.engagedUntil, taskActive: this.actions.taskActive() });
    this.log(`heard "${text}" -> ${intent.kind}${intent.kind === "command" ? " " + intent.command : ""}`);

    if (intent.kind === "ignore") {
      // Show what was heard when it was real speech that was not for the tutor, so a miss is understood.
      if (intent.reason === "not addressed" && text.split(" ").length >= 3) this.heard(`Heard: “${text}”`, `Not for me. Say “Hey ${wakeLabel()}” first`);
      else this.idle();
      return;
    }
    this.engagedUntil = Date.now() + ENGAGED_MS;
    if (intent.kind === "wake") {
      this.ui("listening", "Yes?", "Go ahead");
      return;
    }
    if (intent.kind === "command") {
      this.heard(`“${text}”`, "");
      this.run(intent.command);
      return;
    }
    this.requests += 1;
    this.heard(`“${intent.text}”`, "");
    this.actions.ask(intent.text);
  }

  private run(command: Command): void {
    switch (command) {
      case "open-chat": this.actions.openChat(); break;
      case "close-chat": this.actions.closeChat(); break;
      case "stop": this.cancelSpeech(); this.actions.stopTask(); break;
      case "new-chat": this.actions.newChat(); this.say("Okay, starting fresh."); break;
      case "pause-following": this.actions.setFollowing(false); this.say("Paused. Say resume when you are ready."); break;
      case "resume-following": this.actions.setFollowing(true); this.say("Following again."); break;
      case "next-step": this.actions.nextStep(); break;
      case "previous-step": this.actions.previousStep(); break;
      case "clear-marks": this.actions.clearMarks(); break;
      case "mute": this.toggleMute(); break;
      case "repeat": if (this.lastSpoken) this.say(this.lastSpoken); break;
      case "quiet": this.cancelSpeech(); this.spokenReplies = false; this.heard("Okay, I will stay quiet", `Say “Hey ${wakeLabel()}, talk to me” to hear me again`); break;
      case "speak": this.spokenReplies = true; this.say("Okay, I will talk."); break;
    }
  }

  // ---- the orb ---------------------------------------------------------------------------------

  private idle(): void {
    if (this.muted) this.ui("muted", "Microphone muted", "Click the orb or press Ctrl+Shift+M");
    else if (this.requests < 3) this.ui("listening", "Listening", `Say “Hey ${wakeLabel()}, …” · “Open chat” to type`);
    else this.ui("listening", "Listening", `Hey ${wakeLabel()}… · Ctrl+Shift+M mutes`);
  }

  // What was heard, for a moment, and then back to listening.
  private heard(main: string, sub: string): void {
    this.ui(this.thinking ? "thinking" : "listening", main, sub);
    if (this.heardTimer) clearTimeout(this.heardTimer);
    this.heardTimer = setTimeout(() => {
      if (!this.speakingId && !this.thinking) this.idle();
    }, 3000);
  }

  private ui(state: OrbState, main: string, sub = ""): void {
    this.state = state;
    this.send({ type: "ui", state, main, sub });
  }

  private send(message: VoiceMessage): void {
    this.window?.webContents.send("voice:message", message);
  }
}
