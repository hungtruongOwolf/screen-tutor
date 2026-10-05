import { contextBridge, ipcRenderer } from "electron";
import type { PanelEvent } from "./contract";

contextBridge.exposeInMainWorld("panelApi", {
  send: (text: string) => ipcRenderer.send("panel:send", text),
  newChat: () => ipcRenderer.send("panel:new-chat"),
  clearDrawings: () => ipcRenderer.send("panel:clear-drawings"),
  hide: () => ipcRenderer.send("panel:hide"),
  stop: () => ipcRenderer.send("panel:stop"),
  goTo: (index: number) => ipcRenderer.send("panel:go-to", index),
  step: (direction: "prev" | "next") => ipcRenderer.send("panel:step", direction),
  togglePlay: () => ipcRenderer.send("panel:toggle-play"),
  typed: (seq: number) => ipcRenderer.send("panel:typed", seq),
  toggleFollow: () => ipcRenderer.send("panel:toggle-follow"),
  endTask: () => ipcRenderer.send("panel:end-task"),
  onEvent: (callback: (event: PanelEvent) => void) =>
    ipcRenderer.on("panel:event", (_event, payload: PanelEvent) => callback(payload)),
});
