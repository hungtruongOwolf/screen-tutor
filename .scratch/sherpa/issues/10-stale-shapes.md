# 10: Stale shapes when content changes

**What to build:** When a new capture shows that the content under an existing shape has changed (for example the video moved on), that shape is marked stale and removed unless the model re-anchors it, so the canvas never points at something that is gone.

**Blocked by:** 06, 03

**Status:** ready-for-agent

- [x] The region proposer can report whether the content under a given region changed between two captures (each region carries a 64-bit perceptual hash; reanchor compares them)
- [x] Shapes on changed regions are removed in the new canvas and listed in trace.dropped_shape_ids
- [x] Shapes on unchanged regions are kept and follow their region when numbers shift
- [x] Tests cover a changed and an unchanged case with fixture frames (test_reanchor.py)

## Note

Done together with ticket 06 (same mechanism). Only the explicit 'changed' region kind (needs a previous image) is still unused by the app: the hash approach does not need one.
