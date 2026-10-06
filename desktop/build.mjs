// Bundles the main process, the preload script and the overlay page with esbuild.
import { build } from "esbuild";
import { copyFileSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";

mkdirSync("dist", { recursive: true });

const common = { bundle: true, sourcemap: true, logLevel: "info" };

await build({
  ...common,
  entryPoints: ["src/main.ts"],
  outfile: "dist/main.js",
  platform: "node",
  format: "cjs",
  target: "node22",
  external: ["electron"],
});

await build({
  ...common,
  entryPoints: ["src/voice/setupCli.ts"],
  outfile: "dist/setupVoice.js",
  platform: "node",
  format: "cjs",
  target: "node22",
});

await build({
  ...common,
  entryPoints: ["src/preload.ts"],
  outfile: "dist/preload.js",
  platform: "node",
  format: "cjs",
  target: "node22",
  external: ["electron"],
});

await build({
  ...common,
  entryPoints: ["src/panelPreload.ts"],
  outfile: "dist/panelPreload.js",
  platform: "node",
  format: "cjs",
  target: "node22",
  external: ["electron"],
});

await build({
  ...common,
  entryPoints: ["src/panel/renderer.ts"],
  outfile: "dist/panel.js",
  platform: "browser",
  format: "iife",
  target: "chrome120",
});

await build({
  ...common,
  entryPoints: ["src/watcherPreload.ts"],
  outfile: "dist/watcherPreload.js",
  platform: "node",
  format: "cjs",
  target: "node22",
  external: ["electron"],
});

await build({
  ...common,
  entryPoints: ["src/follow/watcher.ts"],
  outfile: "dist/watcher.js",
  platform: "browser",
  format: "iife",
  target: "chrome120",
});

await build({
  ...common,
  entryPoints: ["src/voicePreload.ts"],
  outfile: "dist/voicePreload.js",
  platform: "node",
  format: "cjs",
  target: "node22",
  external: ["electron"],
});

await build({
  ...common,
  entryPoints: ["src/voice/voiceRenderer.ts"],
  outfile: "dist/voice.js",
  platform: "browser",
  format: "iife",
  target: "chrome120",
});

await build({
  ...common,
  entryPoints: ["src/overlay/renderer.ts"],
  outfile: "dist/overlay.js",
  platform: "browser",
  format: "iife",
  target: "chrome120",
});

// The same renderer for the web playground (served by the backend).
await build({
  ...common,
  sourcemap: false,
  minify: true,
  entryPoints: ["src/render/browser.ts"],
  outfile: "../backend/app/static/render.js",
  platform: "browser",
  format: "iife",
  globalName: "SherpaRender",
  target: "chrome120",
});

copyFileSync("src/overlay/overlay.html", "dist/overlay.html");
copyFileSync("src/follow/watcher.html", "dist/watcher.html");
copyFileSync("src/voice/voiceWindow.html", "dist/voiceWindow.html");
// The chat look is one file used twice: inlined into the panel page (its Content Security
// Policy allows inline styles only) and served by the backend to the web playground.
const chatCss = readFileSync("src/panel/chat.css", "utf8");
writeFileSync("dist/panel.html", readFileSync("src/panel/panel.html", "utf8").replace("/*CHAT_CSS*/", chatCss));
copyFileSync("src/panel/chat.css", "../backend/app/static/chat.css");
