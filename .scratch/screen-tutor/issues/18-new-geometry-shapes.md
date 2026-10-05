# 18: Draw new geometry: squares on a side, polygons and equation labels

**What to build:** The AI can draw new figures, not only mark existing things. A learner asking about the Pythagorean theorem sees a square erected on each side of the triangle, each labelled with its area (for example "5 x 5 = 25"), so the theorem is visible. The new shapes are placed by the app from the line and region data (so they land exactly), not from guessed coordinates.

**Blocked by:** 04

**Status:** ready-for-agent

- [x] New shape kind "square_on_line": anchored to a line region, drawn on the outward side of a closed shape (or the side named by the model), with the side length equal to the line length times a shared scale, translucent fill, optional text inside
- [x] New shape kind "polygon": three or more points relative to a region, optional fill and text
- [x] New shape kind "equation": a text label that can show a formula (powers raised, sqrt as a root sign), placed automatically in free space near the region it is about when the model gives no position
- [x] The renderer draws all three at the right place at any display scale, and tests check the geometry (for example the square's corners for a given line)
- [x] The prompt tells the model when to use them (a Pythagorean recipe) and the backend validates them like other shapes
- [x] On the real Pythagoras frame the model draws three squares on the sides of the triangle with the areas 25, 144 and 169 (verified with tools/ask_model.py)
- [x] The dev tool that draws the model's answer on an image supports the new shapes (and writes one image per step)

## Built (superscripts and the overlay look not yet confirmed by the owner on screen)

- Squares share one scale so their areas stay proportional; the scale is reduced until every square is on screen and, down to 0.35, until none covers other text or controls.
- Equations are placed after the squares are final, avoiding every detected region, every square and every other equation alive at that step, with an 8 px margin.
- Shapes can be given a "name" so later steps remove them (replace an equation instead of stacking them).
- Powers use the SVG baseline-shift property; check in the real overlay that they appear raised.
- Captions of highlighted lines are placed beside the middle of the line.
