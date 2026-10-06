// Downloads what the voice needs, once, into %LOCALAPPDATA%\sherpa: the whisper.cpp program and an
// English speech model (to understand you), and the Piper program and an English voice (to talk). Both run
// on this computer, so no audio ever leaves it. The app does this by itself the first time it starts
// (about 200 MB); `npm run setup:voice` does the same from a terminal.
//
// Not under the project folder: the programs cannot open files below a path with accented letters.

import { spawn } from "node:child_process";
import { createWriteStream, existsSync, mkdirSync, readdirSync, renameSync, rmSync, statSync } from "node:fs";
import { join } from "node:path";
import { Readable } from "node:stream";
import { pipeline } from "node:stream/promises";
import { localRoot } from "../paths";

const WHISPER_ZIP = "https://github.com/ggml-org/whisper.cpp/releases/download/v1.9.2/whisper-bin-x64.zip";
const PIPER_ZIP = "https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_windows_amd64.zip";

export function dataRoot(): string {
  return localRoot();
}

export interface InstallOptions {
  whisperDir?: string;
  piperDir?: string;
  listenModel?: string; // base.en, small.en or tiny.en
  voice?: string; // language_COUNTRY-name-quality, from https://huggingface.co/rhasspy/piper-voices
  listenOnly?: boolean;
  // What is happening now ("Downloading the speech model") and how far along (0 to 1) when known.
  progress?: (what: string, fraction?: number) => void;
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

async function download(url: string, file: string, what: string, progress: InstallOptions["progress"]): Promise<void> {
  if (existsSync(file) && statSync(file).size > 10_000) return;
  progress?.(what, 0);
  const response = await fetch(url, { redirect: "follow" });
  if (!response.ok || !response.body) throw new Error(`${what}: the download failed (${response.status})`);
  const total = Number(response.headers.get("content-length")) || 0;
  let received = 0;
  const source = Readable.fromWeb(response.body as never);
  source.on("data", (chunk: Buffer) => {
    received += chunk.length;
    if (total) progress?.(what, received / total);
  });
  await pipeline(source, createWriteStream(file + ".part"));
  renameSync(file + ".part", file);
}

function unzip(zip: string, target: string): Promise<void> {
  // PowerShell unpacks zip files on every Windows (a "tar" on the path may be GNU tar, which cannot).
  return new Promise((resolve, reject) => {
    const child = spawn("powershell", ["-NoProfile", "-Command", `Expand-Archive -LiteralPath '${zip}' -DestinationPath '${target}' -Force`], {
      windowsHide: true,
      stdio: "ignore",
    });
    child.on("error", reject);
    child.on("exit", (code) => {
      rmSync(zip, { force: true });
      code === 0 ? resolve() : reject(new Error("could not unpack the download"));
    });
  });
}

export async function installVoice(options: InstallOptions = {}): Promise<void> {
  const root = dataRoot();
  const whisperDir = options.whisperDir ?? process.env.VOICE_DIR ?? join(root, "whisper");
  const piperDir = options.piperDir ?? process.env.PIPER_DIR ?? join(root, "piper");
  const listenModel = options.listenModel ?? "base.en";
  const voice = options.voice ?? process.env.PIPER_VOICE ?? "en_US-lessac-medium";
  const progress = options.progress;

  // ---- to understand you: whisper.cpp ----
  mkdirSync(whisperDir, { recursive: true });
  if (!find(whisperDir, "whisper-server.exe")) {
    const zip = join(whisperDir, "whisper-bin-x64.zip");
    await download(WHISPER_ZIP, zip, "Downloading the listening program", progress);
    progress?.("Unpacking the listening program");
    await unzip(zip, whisperDir);
  }
  await download(`https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-${listenModel}.bin`, join(whisperDir, `ggml-${listenModel}.bin`), "Downloading the speech model", progress);

  // ---- to talk: Piper ----
  if (options.listenOnly) return;
  mkdirSync(piperDir, { recursive: true });
  if (!find(piperDir, "piper.exe")) {
    const zip = join(piperDir, "piper_windows_amd64.zip");
    await download(PIPER_ZIP, zip, "Downloading the voice program", progress);
    progress?.("Unpacking the voice program");
    await unzip(zip, piperDir);
  }
  const [language = "", name = "", quality = ""] = voice.split("-");
  const base = `https://huggingface.co/rhasspy/piper-voices/resolve/main/${language.split("_")[0]}/${language}/${name}/${quality}/${voice}`;
  await download(`${base}.onnx`, join(piperDir, `${voice}.onnx`), "Downloading the voice", progress);
  await download(`${base}.onnx.json`, join(piperDir, `${voice}.onnx.json`), "Downloading the voice", undefined);
}
