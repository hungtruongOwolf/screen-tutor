// A log file, so that what happened in a run can be read afterwards (a packaged app has no terminal):
// %APPDATA%\sherpa\logs\app.log. Everything the app prints with console.log / console.error is
// written there too, with the time. No screenshots, no tokens and no spoken or typed text go into it:
// only what happened (turns, timings, errors, what the screen watcher saw).

import { appendFileSync, existsSync, mkdirSync, renameSync, statSync } from "node:fs";
import { join } from "node:path";
import { roamingRoot } from "./paths";

const MAX_BYTES = 1_000_000;

export function logDirectory(): string {
  return join(roamingRoot(), "logs");
}

let ready = false;

export function logLine(level: string, text: string): void {
  try {
    const folder = logDirectory();
    const file = join(folder, "app.log");
    if (!ready) {
      mkdirSync(folder, { recursive: true });
      if (existsSync(file) && statSync(file).size > MAX_BYTES) renameSync(file, join(folder, "app.old.log"));
      ready = true;
    }
    const stamp = new Date().toISOString().replace("T", " ").slice(0, 23);
    appendFileSync(file, `${stamp} ${level} ${text.replace(/\s+$/, "")}\n`);
  } catch {
    // a log that cannot be written must never stop the app
  }
}

// What goes to the console also goes to the file.
export function installConsoleLog(): void {
  const original = { log: console.log.bind(console), error: console.error.bind(console) };
  const text = (args: unknown[]) => args.map((a) => (typeof a === "string" ? a : a instanceof Error ? a.stack ?? a.message : JSON.stringify(a))).join(" ");
  console.log = (...args: unknown[]) => {
    original.log(...args);
    logLine("info ", text(args));
  };
  console.error = (...args: unknown[]) => {
    original.error(...args);
    logLine("ERROR", text(args));
  };
  logLine("info ", `---- Sherpa started (${process.platform}, electron ${process.versions.electron})`);
}
