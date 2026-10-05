// The overlay renderer for the web playground: bundled to one script that exposes
// window.ScreenTutorRender, so the page draws, animates and plays steps exactly as
// the desktop app does.
export { renderCanvasSvg, renderRegionsDebugSvg, renderScanSvg } from "./renderCanvas";
export { planAnimation, playAnimation } from "./animate";
export { StepPlayer } from "./player";
export { ChatView } from "../panel/chatView";
