# screen-tutor

A Windows overlay where a learner asks a question about their screen and an AI answers by drawing on it.

## Language

**Turn**:
One question from the learner plus the AI's answer, starting from one capture.
_Avoid_: request, query, message

**Capture**:
A screenshot taken at the moment the learner triggers a turn, of the active window or the full screen.
_Avoid_: recording, stream

**Region**:
A numbered candidate area on a capture (text block, figure, control, changed area) found by OpenCV. The model points by region number, never by pixel.
_Avoid_: element, box, coordinate

**Shape**:
One drawn item (arrow, box, ellipse, highlight, label, step number, connector) with a stable id, anchored to a region.
_Avoid_: annotation, drawing, sticker

**Canvas**:
The set of shapes currently on screen for a session. It persists across turns.
_Avoid_: layer, board

**Overlay**:
The transparent, always-on-top, click-through window that paints the canvas over the screen.
_Avoid_: HUD, window

**Explain Turn**:
The backend operation that takes a capture, a question and the current canvas, and returns the explanation and the new canvas.
_Avoid_: inference, analyze

**Stale shape**:
A shape whose underlying region content has changed since it was drawn.

**Playground**:
The web page that lets a visitor try the Explain Turn on an uploaded image without the desktop app.

## Relationships

- A **Turn** starts from one **Capture** and ends with a new **Canvas**.
- The **Explain Turn** proposes **Regions**; the model chooses **Regions**; **Shapes** anchor to **Regions**.
- The **Overlay** only renders the **Canvas**; it knows nothing about how it was produced.

## Flagged ambiguities

- "harness" appears in the sibling agent-bridge project and means something unrelated (an agent's prompt, tools and MCP config). Do not use it here.
