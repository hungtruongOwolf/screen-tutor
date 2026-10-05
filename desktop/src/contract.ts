// Mirrors backend/app/contract.py (the Explain Turn contract). Keep in sync.

export type ShapeKind =
  | "arrow"
  | "box"
  | "ellipse"
  | "highlight"
  | "label"
  | "step_number"
  | "connector"
  | "square_on_line"
  | "polygon"
  | "equation";

export interface BBox {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface Region {
  id: number;
  bbox: BBox; // capture pixels
  kind: string;
  // Only for kind "line": the segment end points [x1, y1, x2, y2] in capture pixels.
  line?: number[] | null;
  // A 64-bit perceptual hash of the region pixels (hex).
  signature?: string | null;
}

export interface Anchor {
  region_id: number;
  // Rectangle relative to the region, 0..1 on both axes.
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface Point {
  x: number;
  y: number;
}

export interface Style {
  color: string;
  stroke_width: number;
}

// A shape that arrives by sliding: it starts displaced by (dx, dy) pixels and turned
// by `rotate` degrees about the pivot, and ends where it is drawn.
export interface Motion {
  dx: number;
  dy: number;
  rotate: number;
  pivot_x: number;
  pivot_y: number;
}

export interface Shape {
  id: string;
  kind: ShapeKind;
  anchor: Anchor;
  text?: string | null;
  style?: Style | null;
  // Arrows only: where the arrowhead is (relative to the region). The anchor's
  // x and y are the tail.
  end?: Point | null;
  // Arrows only: when set, the head lands on this region.
  target_region_id?: number | null;
  // Polygons only: corners relative to the anchor region.
  points?: Point[] | null;
  // Squares on a line only: which side of the line, and the size relative to it.
  side?: "left" | "right" | null;
  scale?: number;
  // Set on the step in which the shape was moved.
  motion?: Motion | null;
  // Pointing marks go when the screen changes or the next step draws; a kept one stays.
  keep?: boolean;
  turn: number;
  from_id?: string | null;
  to_id?: string | null;
}

export interface Canvas {
  shapes: Shape[];
}

export interface CaptureMeta {
  width: number;
  height: number;
  scale: number;
  mode: "full_screen" | "active_window";
  excluded: BBox[];
}

export interface ExplainTurnRequest {
  session_id: string;
  question: string;
  image_base64: string;
  capture: CaptureMeta;
  canvas: Canvas;
  // The regions the previous response returned, so drawings can follow the screen.
  previous_regions: Region[];
  turn: number;
  // The conversation so far, oldest first (the backend keeps nothing between turns).
  history?: { role: "user" | "assistant"; text: string }[];
  // The task the learner is on, and what started this turn (a message, or the app seeing
  // the screen change after the last step).
  goal?: string | null;
  trigger?: "user" | "screen_changed";
}

export interface Step {
  caption: string;
  operations: unknown[];
  // The whole canvas as it should look at this step.
  canvas: Canvas;
}

export interface ExplainTurnResponse {
  explanation: string;
  operations: unknown[];
  canvas: Canvas;
  steps: Step[];
  // Web pages the answer relied on (when it searched the web).
  sources: { title: string; url: string }[];
  follow_ups?: string[];
  regions: Region[];
  chosen_region_ids: number[];
  trace: {
    regions_proposed: number;
    attempts: number;
    model: string;
    timings_ms: Record<string, number>;
    region_counts: Record<string, number>;
    lookups: number;
    dropped_shape_ids: string[];
  };
}

// How a task is going, as the tutor judges it after a screen change.
export type Progress = "continue" | "off_track" | "waiting" | "done";

// Marks that point at something on one screen: they mean nothing once the page changes.
export const POINTER_KINDS: readonly string[] = ["box", "ellipse", "arrow", "highlight", "label", "step_number"];

// The events of POST /explain-turn/stream (one JSON object per line).
export interface StreamRegionsEvent {
  event: "regions";
  regions: Region[];
  canvas: Canvas; // the drawings of earlier turns, moved onto these regions
  dropped_shape_ids: string[];
  width: number;
  height: number;
}
export interface StreamSearchingEvent {
  event: "searching";
  query: string;
}
export interface StreamStepEvent {
  event: "step";
  index: number;
  caption: string;
  operations: { op: "add" | "update" | "remove"; shape_id: string }[];
  canvas: Canvas; // the whole canvas as it should look at this step
}
export interface StreamDoneEvent {
  event: "done";
  explanation: string;
  sources: { title: string; url: string }[];
  follow_ups?: string[];
  goal?: string;
  progress?: Progress | null;
  chosen_region_ids: number[];
  trace: ExplainTurnResponse["trace"];
  canvas: Canvas;
  steps: number;
}
export interface StreamErrorEvent {
  event: "error";
  status: number;
  detail: string;
}
export type StreamEvent =
  | StreamRegionsEvent
  | StreamSearchingEvent
  | StreamStepEvent
  | StreamDoneEvent
  | StreamErrorEvent;

// What the main process sends to the overlay after a turn.
export interface OverlayUpdate {
  canvas: Canvas;
  regions: Region[];
  explanation: string; // the caption to show
  view: { width: number; height: number }; // capture pixel size
  // Shapes to draw on with animation (the rest appear at once), and a number the
  // overlay sends back when the drawing has finished so the next step can start.
  animate?: string[];
  seq?: number;
  // True while the model is still writing more steps.
  more?: boolean;
}

// What the main process tells the chat panel.
export type PanelEvent =
  | { type: "reset" } // a new chat
  | { type: "user"; text: string } // the learner's message
  | { type: "busy"; value: boolean } // an answer is being fetched
  | { type: "status"; text: string | null } // a line of progress ("Looking at your screen…")
  | {
      type: "step"; // show this step now; typed in when `animate`
      index: number;
      total: number;
      streaming: boolean; // more steps may still come
      caption: string;
      animate: boolean;
      seq: number; // the panel answers with typed(seq) when the caption is complete
    }
  | { type: "done"; sources: { title: string; url: string }[]; followUps: string[] }
  | { type: "error"; text: string }
  | { type: "playing"; value: boolean } // automatic playback runs or is paused
  | { type: "task"; goal: string | null; following: boolean } // the task being followed
  | { type: "auto"; text: string } // the app acted by itself (the screen changed): a quiet line
  | { type: "focus" }; // the panel was opened: put the cursor in the box

