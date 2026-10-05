# 06: Canvas that persists across turns

**What to build:** A follow-up question adds to, edits or removes the shapes the AI drew before, addressed by shape id, so the explanation builds on one picture. A hotkey clears the canvas. The canvas reducer is pure and deterministic.

**Blocked by:** 04

**Status:** ready-for-agent

- [x] Add, update and remove operations by shape id produce the expected canvas across several turns (the model adds and removes; replacing a shape is remove plus add)
- [x] Clear-all removes every shape immediately (Ctrl+Shift+X also starts a new topic)
- [x] The model receives the current canvas and can refer to earlier shapes by id (listed with ids; "remove" takes ids or the names it gave)
- [x] Invalid operations (unknown id) are rejected without corrupting the canvas (removing something that is not there is ignored)
- [x] Tests cover multi-turn sequences (test_followups.py)

## Decided behaviour (owner asked for follow-ups)

- Ctrl+Shift+E asks a question about the CURRENT drawing: the drawing stays, a fresh capture is taken, and the model may add, update or remove shapes by id. This is the default.
- Ctrl+Shift+X clears everything and starts a new topic.
- Until this ticket is done the app clears the drawing before every question (set in the desktop main process, "fresh drawing per question"); remove that line when this ticket lands.
- Depends on ticket 10 (stale shapes) to behave well when the video has moved on between questions.

## Built (not yet confirmed by the owner on screen)

- The desktop app keeps the drawing between turns and sends it back with the regions of the previous capture. The backend moves each old shape onto the new capture's regions by kind, position and a perceptual hash of the region's pixels (reanchor.py); region numbers change on every capture, so this is essential. The service keeps no images.
- The question bar says "Follow-up: the drawing stays" when a drawing is on screen.
- The 'fresh drawing per question' line in the desktop main process is gone.
