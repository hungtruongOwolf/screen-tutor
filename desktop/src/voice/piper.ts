// The tutor's voice: Piper, a neural speech synthesiser that runs on this computer. It is kept
// running with its voice loaded, so after the first sentence each one takes about 0.1 s to make.

import { spawn, type ChildProcess } from "node:child_process";
import { existsSync, mkdirSync, readdirSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { localRoot } from "../paths";
import { parseWav } from "./audio";

export interface PiperPaths {
  exe: string;
  model: string;
}

export function piperDirectory(): string {
  return process.env.PIPER_DIR ?? join(localRoot(), "piper");
}

function findExe(folder: string): string | undefined {
  if (!existsSync(folder)) return undefined;
  for (const entry of readdirSync(folder, { withFileTypes: true })) {
    const path = join(folder, entry.name);
    if (entry.isDirectory()) {
      const found = findExe(path);
      if (found) return found;
    } else if (entry.name === "piper.exe") {
      return path;
    }
  }
  return undefined;
}

// The program and the voice, if they have been downloaded. PIPER_VOICE names the voice
// (default en_US-lessac-medium); otherwise any voice that is there.
export function findPiper(directory = piperDirectory()): PiperPaths | undefined {
  const exe = findExe(directory);
  if (!exe || !existsSync(directory)) return undefined;
  const wanted = process.env.PIPER_VOICE ?? "en_US-lessac-medium";
  const voices = readdirSync(directory).filter((f) => f.endsWith(".onnx"));
  const model = voices.find((f) => f === `${wanted}.onnx`) ?? voices[0];
  return model ? { exe, model: join(directory, model) } : undefined;
}

export interface Speech {
  pcm: Int16Array;
  sampleRate: number;
}

export class PiperTts {
  private process: ChildProcess | undefined;
  private buffer = "";
  private waiting: ((path: string | Error) => void)[] = [];
  private queue: Promise<unknown> = Promise.resolve();
  private readonly folder = join(tmpdir(), `sherpa-voice-${process.pid}`);

  // `rate` is how much faster than normal it talks: 1.2 is a fifth faster.
  constructor(
    private readonly paths: PiperPaths,
    private readonly rate = 1.2,
    private readonly log: (line: string) => void = () => undefined,
  ) {}

  private start(): void {
    if (this.process && this.process.exitCode === null) return;
    mkdirSync(this.folder, { recursive: true });
    const child = spawn(
      this.paths.exe,
      ["--model", this.paths.model, "--json-input", "--length_scale", String(1 / this.rate), "--output_dir", this.folder],
      { cwd: join(this.paths.exe, ".."), windowsHide: true, stdio: ["pipe", "pipe", "ignore"] },
    );
    this.process = child;
    this.buffer = "";
    child.stdout?.on("data", (data: Buffer) => {
      this.buffer += data.toString();
      for (let at = this.buffer.indexOf("\n"); at >= 0; at = this.buffer.indexOf("\n")) {
        const line = this.buffer.slice(0, at).trim();
        this.buffer = this.buffer.slice(at + 1);
        if (line) this.waiting.shift()?.(line);
      }
    });
    child.on("exit", (code) => {
      this.log(`piper exited (${code})`);
      const failed = new Error("the voice stopped");
      for (const waiter of this.waiting.splice(0)) waiter(failed);
    });
  }

  // Warm up: the first sentence otherwise pays for loading the voice.
  warm(): void {
    void this.synthesize("Ready.").catch(() => undefined);
  }

  // One piece of text as audio. Requests are handled one at a time, in order.
  synthesize(text: string): Promise<Speech> {
    const run = async (): Promise<Speech> => {
      this.start();
      const child = this.process as ChildProcess;
      const path = await new Promise<string>((resolve, reject) => {
        const timer = setTimeout(() => reject(new Error("the voice did not answer in time")), 20_000);
        this.waiting.push((value) => {
          clearTimeout(timer);
          if (value instanceof Error) reject(value);
          else resolve(value);
        });
        child.stdin?.write(JSON.stringify({ text }) + "\n");
      });
      try {
        return parseWav(readFileSync(path));
      } finally {
        rmSync(path, { force: true });
      }
    };
    const result = this.queue.then(run, run);
    this.queue = result.catch(() => undefined);
    return result;
  }

  stop(): void {
    const child = this.process;
    this.process = undefined;
    if (child && child.exitCode === null) child.kill();
    rmSync(this.folder, { recursive: true, force: true });
  }
}
