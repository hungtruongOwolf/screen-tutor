import { contextBridge, ipcRenderer } from "electron";

contextBridge.exposeInMainWorld("watcherApi", {
  onMessage: (callback: (message: unknown) => void) =>
    ipcRenderer.on("watch:message", (_event, message) => callback(message)),
  send: (message: unknown) => ipcRenderer.send("watch:event", message),
});
