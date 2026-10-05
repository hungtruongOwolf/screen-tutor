// Runs inside the chat panel window: wires the view to the main process.

import type { PanelEvent } from "../contract";
import { ChatView, type PanelCommands } from "./chatView";

declare global {
  interface Window {
    panelApi: PanelCommands & { onEvent(callback: (event: PanelEvent) => void): void };
  }
}

const view = new ChatView(document.getElementById("root") as HTMLElement, window.panelApi);
window.panelApi.onEvent((event) => view.handle(event));
