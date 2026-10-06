# 03: Find numbered regions with OpenCV 5

**What to build:** Given a capture, the backend returns numbered candidate regions (text blocks, figures and diagram areas, interface controls, areas changed compared with an earlier capture), with overlaps removed and a cap on the count. A debug mode on the overlay shows the numbers on the screen so the result can be checked by eye.

**Blocked by:** 02

**Status:** ready-for-agent

- [x] Regions have an id, bounding box and kind, and are returned in the Explain Turn response; the trace carries counts per kind
- [x] Overlapping regions are merged or removed and the count never exceeds the configured cap (MAX_REGIONS, default 40)
- [x] Fixture screenshots produce sensible regions in tests (synthetic slide and application window; REAL lecture frames with equations and small text are still untested, see notes)
- [ ] Debug overlay shows region numbers on a live capture (built, Ctrl+Shift+D; needs a human to confirm on a real screen)
- [x] OpenCV 5 is the version in use and is pinned (opencv-python-headless 5.0.0.93)

## Notes

- Whole-capture region has id 0 and kind `screen`; detected regions are numbered from 1 in reading order. Kinds: text, figure, control, changed.
- The `changed` kind works when a previous capture is passed in; the service does not keep captures, so wiring it to a session belongs to ticket 10.
- Heuristics are classical (gradients, morphology, contours). Tuned on synthetic fixtures only. Real frames to try next: equations, small text, video frames, dark themes.
- Tried on one real screenshot (YouTube Pythagoras lecture in a browser, 1920x1080): the problem statement line and the triangle figure with its labels are found as separate, correct regions. Browser chrome and taskbar produce many extra small text regions (noise, harmless but numerous). Small isolated labels such as "a)" are missed. Text merging was tightened after this (same-row words, then stacked aligned lines).
- Added after real-frame tests: kinds `line` (Hough segments inside figures, merged, with end points) and `label` (glyph blobs inside figures, digits joined). On the real Pythagoras frame all three triangle sides and the labels x, 5, 12 are found. Tested on a synthetic dark triangle slide too.
