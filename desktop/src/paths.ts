// Where the app keeps its data. The product used to be called screen-tutor: an existing folder of that
// name is still used (the voice models are large, the token is a one-time entry), so an update loses nothing.

import { existsSync } from "node:fs";
import { homedir, tmpdir } from "node:os";
import { join } from "node:path";

export const APP_FOLDER = "sherpa";
const LEGACY_FOLDER = "screen-tutor";

function pick(base: string): string {
  const current = join(base, APP_FOLDER);
  const legacy = join(base, LEGACY_FOLDER);
  return !existsSync(current) && existsSync(legacy) ? legacy : current;
}

// Models and programs (large): %LOCALAPPDATA%\sherpa
export function localRoot(): string {
  return pick(process.env.LOCALAPPDATA ?? join(homedir(), "AppData", "Local"));
}

// Settings and logs: %APPDATA%\sherpa
export function roamingRoot(): string {
  return pick(process.env.APPDATA ?? tmpdir());
}

// Every folder a .env may be in, the current one first.
export function roamingFolders(): string[] {
  const base = process.env.APPDATA;
  return base ? [join(base, APP_FOLDER), join(base, LEGACY_FOLDER)] : [];
}
