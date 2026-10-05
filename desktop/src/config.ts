// Reads settings from the process environment, loading a local .env first.
// The .env file is git-ignored; .env.example lists the variable names.

import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";

function loadEnvFile(path: string): void {
  if (!existsSync(path)) return;
  for (const line of readFileSync(path, "utf8").split(/\r?\n/)) {
    const match = /^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$/.exec(line);
    if (!match || line.trim().startsWith("#")) continue;
    const [, key, raw] = match;
    if (key && process.env[key] === undefined) {
      process.env[key] = (raw ?? "").replace(/^(['"])(.*)\1$/, "$2");
    }
  }
}

function loadDefaults(resources: string | undefined): void {
  const path = resources ? join(resources, "defaults.json") : "";
  if (!path || !existsSync(path)) return;
  try {
    for (const [key, value] of Object.entries(JSON.parse(readFileSync(path, "utf8")) as Record<string, string>)) {
      if (value && process.env[key] === undefined) process.env[key] = value;
    }
  } catch {
    // an unreadable file is the same as none
  }
}

export interface Config {
  backendUrl: string;
  accessToken: string | undefined;
  defaultQuestion: string;
  // The words that call the tutor by voice (the first names it in hints); WAKE_WORD, comma separated.
  wakeWords: string[];
  // How much faster than normal the tutor talks (SPEECH_RATE; 1 is normal).
  speechRate: number;
  // Whether captions are rewritten as speech by the backend (NARRATION=off switches it off).
  narration: boolean;
  hotkeys: {
    explain: string;
    newChat: string;
    clear: string;
    stop: string;
    mute: string;
    talk: string;
    debug: string;
    quit: string;
    // Recording mode: the tutor's windows can be seen by a screen recorder (for a demo video).
    record: string;
    // Opens the folder with the log file (what happened in this run).
    log: string;
    next: string;
    previous: string;
  };
}

export function loadConfig(projectRoot: string): Config {
  // The repository root holds the shared .env (also read by the backend); a .env
  // next to the app overrides it.
  loadEnvFile(join(projectRoot, ".env"));
  loadEnvFile(join(projectRoot, "..", ".env"));
  // A packaged build: a .env next to the program, or one of the user's own; the backend address baked
  // into the download (resources/defaults.json) comes last, so anything above overrides it.
  loadEnvFile(join(dirname(process.execPath), ".env"));
  if (process.env.APPDATA) loadEnvFile(join(process.env.APPDATA, "screen-tutor", ".env"));
  loadDefaults((process as { resourcesPath?: string }).resourcesPath);
  return {
    backendUrl: (process.env.EXPLAIN_BACKEND_URL ?? "http://127.0.0.1:8000").replace(/\/+$/, ""), // no trailing slash: Function URLs are copied with one
    accessToken: process.env.BACKEND_ACCESS_TOKEN || undefined,
    // Used when the learner submits an empty question.
    defaultQuestion: "Explain what I am looking at.",
    narration: process.env.NARRATION !== "off",
    speechRate: Math.min(2, Math.max(0.7, Number(process.env.SPEECH_RATE) || 1.2)),
    wakeWords: (process.env.WAKE_WORD ?? "nova,tutor").split(",").map((w) => w.trim()).filter(Boolean),
    hotkeys: {
      // Opens and hides the chat.
      explain: "CommandOrControl+Shift+E",
      newChat: "CommandOrControl+Shift+N",
      // Takes the drawings off the screen (the chat stays).
      clear: "CommandOrControl+Shift+X",
      // Stops everything: the answer being fetched, the following of the task, the marks.
      stop: "CommandOrControl+Shift+S",
      // Voice: mute or unmute the microphone; and talk now (the next thing said is for the tutor).
      mute: "CommandOrControl+Shift+M",
      talk: "CommandOrControl+Shift+Space",
      debug: "CommandOrControl+Shift+D",
      quit: "CommandOrControl+Shift+Q",
      record: "CommandOrControl+Shift+R",
      log: "CommandOrControl+Shift+L",
      // Ctrl+Shift+. and Ctrl+Shift+, are Ctrl+> and Ctrl+< on a US keyboard.
      next: "CommandOrControl+Shift+.",
      previous: "CommandOrControl+Shift+,",
    },
  };
}
