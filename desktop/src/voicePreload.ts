import { contextBridge, ipcRenderer } from "electron";

contextBridge.exposeInMainWorld("voiceApi", {
  onMessage: (callback: (message: unknown) => void) =>
    ipcRenderer.on("voice:message", (_event, message) => callback(message)),
  send: (event: unknown) => ipcRenderer.send("voice:event", event),
});
