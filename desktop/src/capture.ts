import { desktopCapturer, screen } from "electron";
import type { CaptureMeta } from "./contract";

export interface Capture {
  // A JPEG of the screen: far smaller than a PNG, so a turn stays well under the
  // 6 MB limit of a request to AWS Lambda.
  image: Buffer;
  meta: CaptureMeta;
}

// Captures the primary display. Active-window capture, the capturing indicator
// and excluded areas arrive with the capture-scope ticket.
export async function captureScreen(): Promise<Capture> {
  const display = screen.getPrimaryDisplay();
  const width = Math.round(display.size.width * display.scaleFactor);
  const height = Math.round(display.size.height * display.scaleFactor);

  const sources = await desktopCapturer.getSources({
    types: ["screen"],
    thumbnailSize: { width, height },
  });
  const source = sources.find((s) => s.display_id === String(display.id)) ?? sources[0];
  if (!source) throw new Error("No screen source available to capture");

  const image = source.thumbnail;
  const size = image.getSize();
  return {
    image: image.toJPEG(92),
    meta: {
      width: size.width,
      height: size.height,
      scale: display.scaleFactor,
      mode: "full_screen",
      excluded: [],
    },
  };
}
