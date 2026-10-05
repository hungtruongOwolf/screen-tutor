# 14: Web playground for judges

**What to build:** A single web page on the same backend: upload an image or paste a screenshot, ask a question, see the numbered regions, the annotated result and the caption, and ask follow-ups that grow the canvas. Sample images are provided. No login; rate-limited; no images retained.

**Blocked by:** 06, 13

**Status:** ready-for-agent

- [x] Visitor can upload an image (file, drop or paste) and get regions and annotations without installing anything
- [x] Follow-up questions on the same image extend the canvas (and steps, sources and the debug view of regions work)
- [x] Sample images give a good result in one click (right triangle, toolbar, bullet slide)
- [ ] Page works in desktop browsers and is publicly reachable (verified in Chrome on localhost with the real model; the public address needs the next deploy)
- [x] Rate limiting is in effect (8 per minute per visitor by default, per instance; size and question limits; PLAYGROUND_ENABLED=0 switches it off)

## Built

- GET / serves the page; POST /playground/explain is the open endpoint (no token, guarded). The page uses the desktop app's own renderer, bundled for the browser (desktop/build.mjs writes backend/app/static/render.js). Samples: backend/tools/make_samples.py.
- The page shows a 'What happened' panel (model, number of regions OpenCV 5 found per kind, timings, attempts, web searches) for judges.
- Checked in Chrome: the triangle sample with 'explain step by step' drew three squares with the areas 9, 16, 25 over four steps.
- Risk: the open endpoint spends model credits per request. Mitigations: per-visitor limit, size limits, kill switch, AWS Budget alert.
