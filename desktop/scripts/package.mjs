// Builds what a person downloads, ready to run with nothing else installed:
//   npm run package -- --url=https://....on.aws    Sherpa-Setup-<version>.exe  (double click: installs for the current user,
//                      no admin rights, and starts) and Sherpa-Portable-<version>.exe (one file,
//                      no install), both in release/.
//
// The address of the backend (not a secret) comes from the repository's .env and is written to
// build/defaults.json, which is packed next to the program, so nobody has to type it. The access token is
// a secret and is NEVER put in a download: a person adds it to a .env beside the program or in
// %APPDATA%\sherpa\.env. The speech models are not in the file either: the app downloads them
// (about 200 MB) the first time it starts.

import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";

// --out=release-public: another folder for the files (so a build for the public does not overwrite another).
const outDir = process.argv.find((a) => a.startsWith("--out="))?.slice(6) ?? "";
const root = resolve(import.meta.dirname, "..");

function readEnv(path) {
  const values = {};
  if (!existsSync(path)) return values;
  for (const line of readFileSync(path, "utf8").split(/\r?\n/)) {
    const match = /^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$/.exec(line);
    if (match && !line.trim().startsWith("#")) values[match[1]] = match[2].replace(/^(['"])(.*)\1$/, "$2");
  }
  return values;
}

const env = { ...readEnv(join(root, "..", ".env")), ...readEnv(join(root, ".env")) };
// --url=https://....on.aws, or EXPLAIN_BACKEND_URL in .env when that is the cloud address (it is
// http://127.0.0.1:8000 while developing).
const argUrl = process.argv.find((a) => a.startsWith("--url="))?.slice(6) ?? "";
const candidate = argUrl || env.EXPLAIN_BACKEND_URL || "";
const cloud = /^https:\/\/.+/.test(candidate) ? candidate.replace(/\/+$/, "") : "";
if (!cloud) {
  console.error("Give the cloud address: npm run package -- --url=https://....on.aws (or set EXPLAIN_BACKEND_URL in .env).");
  process.exit(1);
}
mkdirSync(join(root, "build"), { recursive: true });
writeFileSync(join(root, "build", "defaults.json"), JSON.stringify({ EXPLAIN_BACKEND_URL: cloud }, null, 2));

for (const [command, args] of [
  ["node", ["build.mjs"]],
  ["npx", ["electron-builder", "--win", "--publish", "never", ...(outDir ? [`--config.directories.output=${outDir}`] : [])]],
]) {
  const run = spawnSync(command, args, { cwd: root, stdio: "inherit", shell: true });
  if (run.status !== 0) process.exit(run.status ?? 1);
}
rmSync(join(root, "build", "defaults.json"), { force: true });
console.log("built: release/ (the backend address is in it, the access token is not)");
