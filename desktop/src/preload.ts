import { contextBridge, ipcRenderer } from "electron";
import type { OverlayUpdate } from "./contract";

contextBridge.exposeInMainWorld("overlayApi", {
  onUpdate: (callback: (update: OverlayUpdate) => void) =>
    ipcRenderer.on("overlay:update", (_event, update: OverlayUpdate) => callback(update)),
  onClear: (callback: () => void) => ipcRenderer.on("overlay:clear", () => callback()),
  onStale: (callback: (canvas: unknown) => void) =>
    ipcRenderer.on("overlay:stale", (_event, canvas) => callback(canvas)),
  onToggleDebug: (callback: () => void) =>
    ipcRenderer.on("overlay:toggle-debug", () => callback()),
  onScan: (callback: (scan: unknown) => void) =>
    ipcRenderer.on("overlay:scan", (_event, scan) => callback(scan)),
  animationDone: (seq: number) => ipcRenderer.send("overlay:animation-done", seq),
});
