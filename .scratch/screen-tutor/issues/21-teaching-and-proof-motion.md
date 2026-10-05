# 21: Teach, don't just state: true-size squares, a moving proof, general teaching rules

**What to build:** the owner's feedback after the first run of the animated overlay: (1) the explanation drew three squares and then wrote the formula without showing why it holds; (2) a square built on a side of 12 was drawn smaller than that side; (3) is the prompt hardcoded to one topic?

**Blocked by:** 20 (live, animated drawing).

**Status:** built, needs the owner's check on screen (desktop and web page).

- [x] Squares on a line are true to size (scale 1). They only shrink when more than a quarter of the square would run off the screen (SHRINK_ONLY_BELOW in answer.py); a small overhang is left to the screen edge. The text-avoidance shrink was removed.
- [x] A shape can arrive by sliding: Shape.motion (dx, dy, rotate, pivot) on an update operation. The overlay draws it where it ends and animates from the displaced, turned start (planAnimation puts sliding pieces first, in a ripple, then the new drawings; the cursor stays hidden meanwhile).
- [x] Visual aid `pythagoras_proof` (aids.py, proof.py): a square of side a+b with four copies of the triangle (stage 1: they leave a tilted square c^2), then stage 2 slides the same triangles so the leftover is a^2 and b^2. Geometry is exact and tested (areas, no flips, shortest turns). The diagram goes in free space (place_box in layout.py), keeps equations off it, and "remove": ["proof"] takes it off.
- [x] The system prompt no longer has a fixed Pythagoras recipe: it has general teaching rules (given, idea, why with a picture or movement, working, answer; formula after the picture; remove old marks), a description of aids, and one example. The engine's shapes stay general.
- [x] Tried on the real Pythagoras frame (5 steps: highlight, true-size squares, proof stage 1, proof stage 2 sliding, equation) and on two other subjects (adding fractions; an off-by-one bug in code): the explanations are correct and in order, the model did not misuse the proof aid.
- [ ] Weak spots seen: on the code frame the model boxed `s = 0` for "the loop starts at 1" instead of the `for` line (text lines in a dense block; the region pick is wrong); for fractions the drawing is mostly boxes and equations (no bars being cut). More aids (a bar model, a number line) and a better text-line pick are possible follow-ups.
- [ ] Owner check on screen: the squares match the sides; the proof diagram appears and the four triangles slide; steps play on their own.
