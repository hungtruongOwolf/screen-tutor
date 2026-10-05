# 20: Live, animated drawing: stream the steps and draw them stroke by stroke

**What to build:** The learner watches the explanation being drawn, instead of waiting and then seeing everything at once. As soon as the first step is ready it appears and is drawn stroke by stroke (a cursor glides to the spot, then the line, square or box is drawn on, then the text appears), while the model is still writing the later steps. Later steps follow automatically, each after the previous one finished drawing and the learner had time to read its caption; the keys for next and previous step still work. While the model is thinking, the learner sees quick feedback instead of nothing (the detected regions flash in as a scan).

**Blocked by:** 19

**Status:** ready-for-agent

- [x] The backend streams a turn as events (POST /explain-turn/stream and /playground/explain/stream, newline-delimited JSON): regions, searching, one step event per step, done, error; the non-streaming call is the last event of the same code (explain_events)
- [x] The first step reaches the client before the model has finished (test: a step is yielded before the last piece of the stream is read; live: first step 3.2 to 8 s of a 3.8 to 18 s turn depending on how slowly the service generates). The wait is dominated by the model's time to first token (about 2 s even for a tiny prompt, mostly image processing), not by writing the steps
- [x] A failure after some steps were already sent ends the turn with what was sent; a failure before any step still retries once (tests)
- [x] Squares of one picture get one scale chosen from the whole figure up front (DecisionBuilder; the model's own scale is ignored)
- [x] The overlay draws each new shape in order with a cursor that glides along a curve to the start and follows the stroke; outlines draw on, fills fade in, labels and equations appear, arrow heads pop in; earlier shapes stay static; reduced motion or no support falls back to instant drawing (verified in Chrome on the web page by scrubbing the animations; the desktop overlay itself is not yet confirmed by the owner)
- [x] The animation order and timing are planned by a pure function with tests (render/animate.ts: planAnimation; 20 tests incl. the driver with a stand-in for the Web Animations API)
- [x] Steps play automatically one after another (dwell 1.1 s plus 38 ms per caption character, at most 5 s) by render/player.ts (11 tests: waits for steps still arriving, survives a step that fails to draw, stops on a key, a new answer replaces the old); next and previous keys interrupt it
- [x] The captions appear as if typed (at most about 2 s per caption)
- [x] A scan effect shows the detected regions while the model is thinking (staggered flash of every region; clears when the first step arrives or after 2.6 s)
- [x] The web playground uses the same stream, animation and player (one bundled script)
- [x] On AWS the stream reaches the client progressively: Function URL invoke mode RESPONSE_STREAM plus AWS_LWA_INVOKE_MODE=response_stream; events arrive at different times (checked with timestamps)

## What was learned (2026-10-04)

- Research (Pointr source and docs; HeyClicky, which is open source): neither streams the model output; Pointr says generation is only about 28 percent of the model's time for its short answers. They hide latency with an immediate thinking state after the capture, a predicted next step, hedged duplicate requests after about 1.5 s, a glide of the cursor (CSS, 800 ms) and a spotlight dim. HeyClicky flies a cursor along a Bezier arc with smoothstep easing (0.6 to 1.4 s, swelling in the middle) and types the bubble text at 30 to 60 ms per character; its code draws no arrows or circles. We copied: immediate feedback (scan), arc glide with swell, typed captions, hedged requests (second model after 4 s). We go beyond both: steps stream and shapes are drawn stroke by stroke.
- The model service's speed varies a lot over time (first step 3 s to over 25 s for the same request). Hedging (MODEL_FALLBACK_NAME, default Qwen/Qwen3.8-27B, after HEDGE_AFTER_SECONDS, default 4) is the safety net.
- Time to first token is about 2 s even with a tiny prompt; images are the cost (about 1 s). Shrinking the images saved only about 0.2 s, so it was not done.
- A hidden browser tab freezes animations and slows timers: check the web page in a visible tab; to inspect an animation frame, pause document.getAnimations() and set currentTime.
- The backend package needs app/__init__.py: without it the empty stand-in package used to cache the dependency layer shadowed the real code in the container.
