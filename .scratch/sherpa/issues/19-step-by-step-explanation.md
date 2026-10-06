# 19: Step-by-step explanation

**What to build:** One question can produce an explanation in several steps. Each step has a short caption and its own drawings (for example: step 1 highlight the two short sides, step 2 draw the squares on them, step 3 draw the square on the long side, step 4 show that the areas add up). The learner moves between steps with a hotkey, and the drawings from earlier steps stay on screen unless a step removes them.

**Blocked by:** 06, 18

**Status:** ready-for-agent

- [x] The Explain Turn response can carry an ordered list of steps; each step has a caption, its operations and the whole canvas at that step
- [x] A hotkey moves to the next step (Ctrl+Shift+.) and another to the previous one (Ctrl+Shift+,); the caption shows 'Step 2 of 4' and how to go on (needs a human run)
- [x] A turn that needs no steps still works as one step
- [x] The prompt asks for steps when the question is "explain", "solve", "prove" or "show how" and for a single step when the question is a quick lookup
- [x] The overlay shows which step it is on (for example 2 of 4)
- [x] A new question after the last step starts a follow-up on the same canvas (ticket 06)
- [x] Tests cover applying steps in order (backend), the player that moves through them (render/player.ts) and going back; the hotkeys themselves live in the desktop main process and need the owner's manual check
- [ ] Optional after the core works: automatic advance with a timer, and spoken captions (ticket 08)

## Notes

- The app shows the canvas of the step it is on; a follow-up asked in the middle of a walkthrough builds on what is on screen at that step.
- Not done: automatic advance with a timer; spoken captions (ticket 08).

Steps are now played automatically and streamed: see ticket 20.
