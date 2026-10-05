// Speech to text on this computer: a whisper.cpp server that keeps its model loaded, so a short
// request is recognised in about half a second. No audio leaves the machine and none is written
// to disk.

import { spawn, type ChildProcess } from "node:child_process";
import { existsSync, readdirSync } from "node:fs";
import { createServer } from "node:net";
import { homedir } from "node:os";
import { dirname, join } from "node:path";

export interface VoicePaths {
  server: string;
  model: string;
}

// Where voice/installer.ts puts things. Not under the project: whisper.cpp cannot open files
// below a path with accented letters.
export function voiceDirectory(): string {
  return process.env.VOICE_DIR ?? join(process.env.LOCALAPPDATA ?? join(homedir(), "AppData", "Local"), "screen-tutor", "whisper");
}

function find(folder: string, name: string): string | undefined {
  if (!existsSync(folder)) return undefined;
  for (const entry of readdirSync(folder, { withFileTypes: true })) {
    const path = join(folder, entry.name);
    if (entry.isDirectory()) {
      const found = find(path, name);
      if (found) return found;
    } else if (entry.name === name) {
      return path;
    }
  }
  return undefined;
}

// The recogniser and an English model, if they have been downloaded.
export function findVoice(directory = voiceDirectory()): VoicePaths | undefined {
  const server = find(directory, "whisper-server.exe");
  const model = ["ggml-base.en.bin", "ggml-tiny.en.bin", "ggml-small.en.bin"].map((m) => join(directory, m)).find(existsSync);
  return server && model ? { server, model } : undefined;
}

async function freePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const probe = createServer();
    probe.once("error", reject);
    probe.listen(0, "127.0.0.1", () => {
      const address = probe.address();
      const port = typeof address === "object" && address ? address.port : 0;
      probe.close(() => resolve(port));
    });
  });
}

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

export class WhisperServer {
  private process: ChildProcess | undefined;
  private port = 0;
  private starting: Promise<void> | undefined;
  private queue: Promise<unknown> = Promise.resolve();

  constructor(
    private readonly paths: VoicePaths,
    private readonly log: (line: string) => void = () => undefined,
  ) {}

  get running(): boolean {
    return this.process !== undefined && this.process.exitCode === null;
  }

  async start(): Promise<void> {
    if (this.running) return;
    this.starting ??= this.launch().finally(() => {
      this.starting = undefined;
    });
    return this.starting;
  }

  private async launch(): Promise<void> {
    this.port = await freePort();
    const args = [
      "-m", this.paths.model,
      "--host", "127.0.0.1",
      "--port", String(this.port),
      "-t", "6",
      "-l", "en",
      "-nt",
      "-ac", "768", // a shorter audio window: about half the time for requests of a few seconds
    ];
    this.process = spawn(this.paths.server, args, { cwd: dirname(this.paths.server), windowsHide: true, stdio: "ignore" });
    const child = this.process;
    child.on("exit", (code) => this.log(`whisper server exited (${code})`));
    for (let i = 0; i < 100; i++) {
      if (child.exitCode !== null) throw new Error("the speech recogniser stopped while starting");
      try {
        await fetch(`http://127.0.0.1:${this.port}/`, { signal: AbortSignal.timeout(500) });
        this.log(`whisper server ready on ${this.port}`);
        return;
      } catch {
        await sleep(200);
      }
    }
    this.stop();
    throw new Error("the speech recogniser did not start in time");
  }

  // The words in a WAV file (16 kHz mono). Requests are handled one at a time.
  transcribe(wav: Uint8Array): Promise<string> {
    const run = async (): Promise<string> => {
      await this.start();
      const form = new FormData();
      form.append("file", new Blob([wav as BlobPart], { type: "audio/wav" }), "speech.wav");
      form.append("temperature", "0.0");
      form.append("response_format", "json");
      const response = await fetch(`http://127.0.0.1:${this.port}/inference`, {
        method: "POST",
        body: form,
        signal: AbortSignal.timeout(20_000),
      });
      if (!response.ok) throw new Error(`the speech recogniser answered ${response.status}`);
      const body = (await response.json()) as { text?: string };
      return (body.text ?? "").replace(/\s+/g, " ").trim();
    };
    const result = this.queue.then(run, run);
    this.queue = result.catch(() => undefined);
    return result;
  }

  stop(): void {
    const child = this.process;
    this.process = undefined;
    if (child && child.exitCode === null) child.kill();
  }
}
