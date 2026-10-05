Status: ready-for-agent
Feature: screen-tutor

# Spec: screen-tutor

## Problem Statement

A learner who is watching a lecture video, or stuck in an unfamiliar app, cannot get help from an AI without breaking their flow. They have to screenshot the screen, paste it into a chat, type a question, read a text answer, then map that answer back onto what they are looking at. The AI cannot point at the thing on their screen, and if it produces a visual explanation, the learner cannot ask it to keep drawing on that same picture. The result is that visual confusion ("what is that part of the diagram?", "where do I click?") is answered with words, and the learner still has to translate.

## Solution

screen-tutor is a Windows desktop overlay. The learner presses a hotkey, speaks (or types) a question, and the app captures the screen at that moment. An AI looks at it and answers by drawing directly on top of the screen: arrows, boxes, highlights, step numbers, labels and small connected diagrams, with a short spoken or captioned explanation. The drawing stays on screen as a persistent canvas across follow-up questions, so the learner can say "now explain the second part" and the AI adds to, edits or removes what it drew before. Capture only happens when the learner asks, and the app always shows when it is capturing.

Pointing is made reliable by splitting the work: OpenCV 5 finds and numbers candidate regions on the screenshot (text blocks, figures, controls, changed areas), the model chooses regions by number and decides what to draw, and the overlay renders the shapes on those regions. The model is never asked for raw pixel coordinates.

A small web playground shares the same backend, so a judge or any visitor can upload a screenshot or video frame and see the numbered regions and the annotations without installing the desktop app.

The flagship experience is learning from a computer-science lecture video. A short second demo shows the same product teaching a software application.

## User Stories

1. As a learner watching a lecture video, I want to press a hotkey and ask a question out loud, so that I do not have to leave the video or type.
2. As a learner, I want the AI to circle or highlight the exact part of the screen I am confused about, so that I do not have to translate a text answer back onto the screen.
3. As a learner, I want the AI to draw arrows between related parts of a diagram, so that I can see how they connect.
4. As a learner, I want numbered step markers placed on the screen, so that I can follow a multi-step explanation in order.
5. As a learner, I want short text labels drawn next to highlighted parts, so that each part is named where I can see it.
6. As a learner, I want the AI to draw a small helper diagram over empty areas of the screen when the existing picture is not enough, so that abstract ideas become visual.
7. As a learner, I want my follow-up question to add to what the AI already drew, so that the explanation builds on one picture instead of starting over.
8. As a learner, I want the AI to be able to edit or remove its earlier drawings, so that the canvas stays readable as the explanation changes.
9. As a learner, I want to clear everything the AI drew with one action, so that I can get back to the plain screen immediately.
10. As a learner, I want the overlay to let my mouse clicks pass through to the app underneath, so that the overlay never gets in the way of what I am doing.
11. As a learner, I want captions of the explanation to always appear on screen, so that I can follow without sound.
12. As a learner, I want the explanation spoken aloud when I turn speech on, so that I can keep my eyes on the picture.
13. As a learner, I want to type my question instead of speaking when I cannot talk, so that the product still works in a quiet room.
14. As a learner, I want push-to-talk (hold a key to speak, release to send), so that the app never listens when I did not ask.
15. As a learner, I want speech recognition to run on my own machine, so that my voice never leaves it.
16. As a learner, I want a clear on-screen indicator while a capture is happening, so that I always know when the app is looking at my screen.
17. As a learner, I want the app to capture only when I trigger it, so that nothing is captured in the background.
18. As a learner, I want the app to capture my primary screen only when I ask, so that it is simple and predictable.
19. As a learner, I want to define areas that are never sent (for example a chat window or a password manager), so that private content is excluded.
20. As a learner, I want the app to tell me when it cannot work out an answer or when a request failed, so that I am not left staring at an empty screen.
21. As a learner, I want the explanation to remain correct when the video has moved on between my questions, so that old drawings do not point at things that are no longer there.
22. As a learner, I want drawings whose underlying content changed to be marked as stale or removed, so that the canvas never lies about the screen.
23. As a learner, I want the AI to look up a definition or source when I ask about a concept, so that the explanation is grounded and cited.
24. As a learner, I want the cited source named in the explanation, so that I can check it myself.
25. As a learner, I want to ask "what is this?" about any region and get a labelled answer, so that I can learn from videos with no transcript help.
26. As a learner using an unfamiliar app, I want the AI to point at the button or menu I should use next, so that I can follow along without searching menus.
27. As a learner using an unfamiliar app, I want a step-by-step walk with numbered markers that I can advance with a follow-up, so that I learn the sequence.
28. As a learner, I want a hotkey to repeat the last explanation with a fresh capture, so that I can ask again after the screen changes.
29. As a learner, I want the app to run on Windows without a complicated install, so that I can try it in minutes.
30. As a learner, I want the overlay to look right on any monitor size and display scaling, so that drawings land on the correct spot.
31. As a learner with several monitors, I want the capture and overlay to follow the monitor I am using, so that drawings appear where I am looking.
32. As a visitor without the desktop app, I want to upload a screenshot or video frame to a web page, so that I can try the product immediately.
33. As a visitor, I want to see the numbered regions that the vision step found, so that I can see how the AI decides where to point.
34. As a visitor, I want to see the final annotated image with the explanation, so that I can judge the quality.
35. As a visitor, I want sample images to try, so that I can see a good result in one click.
36. As a visitor, I want to ask follow-up questions on the same uploaded image and see the canvas grow, so that I experience the persistent canvas.
37. As a hackathon judge, I want a working public endpoint, so that I can evaluate the system without installing anything.
38. As a hackathon judge, I want a written architecture and a reproducible build, deploy and test guide, so that I can verify the submission is real and repeatable.
39. As a hackathon judge, I want evidence of how well the pointing works (a measured evaluation on labelled examples), so that I can trust the claims.
40. As a hackathon judge, I want to see how the system handles bad model output and failures, so that I can judge robustness.
41. As a hackathon judge, I want evidence that the service runs on Arm (Graviton) with measured performance and cost against x86, so that cloud-optimised claims are backed by data.
42. As a hackathon judge, I want to see which NVIDIA model runs on Nebius and how it is configured, so that I can verify the required technology is genuinely used.
43. As the developer, I want to swap the vision model through configuration, so that I can benchmark candidates and change course without code changes.
44. As the developer, I want a recorded-response model adapter for tests, so that tests are deterministic and free.
45. As the developer, I want an evaluation harness over labelled screenshots, so that I can measure region-pick accuracy whenever I change prompts or models.
46. As the developer, I want structured logs and metrics from the service, so that I can see latency, failures and cost per turn.
47. As the developer, I want the service to keep no screenshots after a turn finishes, so that user data is not stored.
48. As the developer, I want the service protected by an access token and rate limits, so that it cannot be abused when it is public.
49. As the developer, I want the feedback I gather about Nebius, NVIDIA and Tavily collected as I build, so that the hackathon feedback form is easy to complete.
50. As a future maintainer, I want the part that turns a screenshot and a question into drawings to be independent of the part that paints them, so that other renderers (another platform, a web page) can be added.

## Implementation Decisions

**Product shape**
- Windows desktop app built with Electron and TypeScript, plus a backend service and a web playground. One repository.
- Capture is on demand only (hotkey) and always the full primary screen, with a visible capturing indicator. No continuous capture and no per-window capture (decided by the owner to keep it simple).
- Voice is push-to-talk. Speech recognition runs locally with whisper.cpp. Spoken replies use the voices built into Windows. Captions are always shown; text input is always available as a fallback.

**Modules**
- Desktop client: global hotkeys, screen capture, excluded-area handling, push-to-talk and local transcription, text-to-speech, settings, and the overlay window (transparent, always on top, click-through). It holds the current canvas for the session and calls the backend once per turn.
- Overlay renderer: a pure function from canvas state (plus screen geometry and scale) to vector drawing on the transparent window. This is independent of how the canvas was produced.
- Explain service (backend): receives a turn and returns the new canvas. Internally made of the region proposer, the model adapter, the turn orchestrator, the canvas reducer and the lookup tool.
- Region proposer: uses OpenCV 5 to produce numbered candidate regions on a screenshot: text blocks, figures and diagram areas, interface controls, and areas that changed compared with an earlier capture. It removes overlaps, limits the count, and returns each region with an id, a bounding box and a kind. It also supports checking whether the content under an existing shape has changed.
- Model adapter: calls vision and text models through Nebius Token Factory's OpenAI-compatible API. Model identifiers come from configuration. Initial candidates: Nemotron-Nano-V2-12b and Cosmos3-Super-Reasoner for vision, a Nemotron text model for dialogue, and Nemotron-3-Nano-Omni to be tested. The adapter returns structured output and is the single place where tests substitute recorded responses.
- Turn orchestrator: a short bounded loop. It asks the model to choose regions by number and describe shapes, validates the answer against known region ids and screen bounds, asks the model to repair invalid output, and gives up gracefully after a limit. It may call the lookup tool when the user asks about a concept.
- Canvas reducer: applies add, update and remove operations to the canvas by shape id. It is pure and deterministic.
- Lookup tool: a functional runtime call to Tavily for definitions and sources, with the source named in the on-screen label.
- Web playground: one page on the same backend. Upload an image, ask a question, see the numbered regions, the annotated result and follow-ups. Provides sample images. No login; rate-limited.

**Explain Turn contract (the main seam)**
- Input: a screenshot image, the user's question as text, the current canvas (list of shapes with ids), a session identifier, capture metadata (size, display scale, excluded areas), and optional settings.
- Output: the explanation text, the list of operations applied, the new canvas, the region ids the model chose, and a trace of the turn (regions proposed, number of attempts, model used, timings) for evaluation and logs.
- The model never produces raw pixel coordinates. Shapes anchor to region ids plus offsets relative to the region, so they survive different resolutions and scaling. The client maps them to screen pixels.

**Canvas and shapes**
- Shape kinds: arrow, box, ellipse, highlight, text label, step number, connector between shapes, and a small free diagram built from these.
- Every shape has a stable id, kind, anchor (region and relative offset or another shape), text if any, style, and the turn that created it.
- Canvas persists across turns in a session. On each new capture, shapes whose underlying content changed are marked stale and removed unless the model re-anchors them. The user can clear all.

**Agentic behaviour, safety and privacy**
- The turn orchestrator is bounded (attempt limit, time limit), validates all model output, repairs or fails safely, and reports failures clearly to the user.
- The service retains no screenshots after a turn; logs contain no image data. The service requires an access token and applies rate limits. Excluded areas are removed on the client before anything is sent.
- A task-effectiveness evaluation is kept in the repository: labelled screenshots and questions, with a metric for whether the chosen regions are correct.

**Deployment**
- Backend and playground run on the owner's personal AWS account as an arm64 (Graviton) container, defined as code, with pinned dependencies and a documented build, deploy and test procedure. A benchmark compares arm64 with x86 on performance and cost. Structured logs and metrics are produced.
- The repository carries an open-source licence and a README, an architecture diagram, and notes for the Nebius feedback form.
- The owner participates as an individual; no employer accounts or resources are used.

**Demo content**
- Flagship: a computer-science lecture (for example binary trees or backpropagation) from a Creative Commons or self-recorded video. Secondary: a short clip teaching a software application. Separate demo videos are recorded per hackathon from the same product.

## Testing Decisions

- A good test checks external behaviour only: what a caller gives and gets back, not how regions are computed or how the loop is written. Tests do not call live models.
- Seam 1, Explain Turn: tests call the turn interface with fixture screenshots and a recorded-response model adapter. They check that responses match the contract; that every shape anchors to a region that exists and lies in bounds; that adding, updating and removing shapes by id across several turns produces the expected canvas; that stale shapes are detected when content changes; that invalid model output is repaired or reported rather than crashing; that no raw coordinates reach the output; and that no image is retained afterwards.
- Seam 2, Overlay renderer: tests give the renderer canvas states with different screen sizes and display scales and check the resulting drawing (which elements exist and where they land, in vector form). They do not test the transparent window itself.
- Evaluation harness (separate from tests): runs labelled screenshots against a live model on demand and reports region-pick accuracy per model and prompt. It is a measurement tool, not a pass/fail gate in normal test runs.
- Not automated, covered by a manual checklist: screen capture, global hotkeys, push-to-talk and transcription, text-to-speech, click-through behaviour, multi-monitor behaviour and the capture indicator.
- Prior art: none; the repository is empty. The first tests establish the pattern.

## Out of Scope

- macOS, Linux, mobile, Chrome extension, Fire TV, VR.
- Continuous or background capture; recording or storing the user's screen.
- Music-production (DAW) specific integrations (the product may work on them, but no dedicated support).
- Generating images or video; the AI draws only the listed shape kinds.
- Accounts, billing, multi-user features, cloud storage of user data.
- Alexa or other voice-assistant integrations.
- Executing actions on the user's behalf (clicking or typing for them); the product only points and explains.
- Comparisons with, or positioning against, other products.

## Further Notes

- Deadlines: OpenCV AI Competition 26 Oct 2026 (11:45 pm PDT); Nebius x NVIDIA 30 Oct 2026 (10:00 am PDT). Awards targeted: OpenCV Overall, Agentic Vision and COOL; Nebius track prize, Best Use of Tavily, Most Valuable Feedback.
- OpenCV's judging weights technical depth of the OpenCV 5 use (30%), so the region proposer is a primary feature, not a helper. Cloud delivery and reproducibility are scored separately (10%).
- First technical risks to test early: whether OpenCV candidate regions cover equations, small text and diagrams in video frames; which NVIDIA vision model picks the right region most reliably; end-to-end latency per turn (target a few seconds).
- Nebius credit: redeem the activation code on the hackathon's resources page before real testing.
- Planning hub with shared context and decisions: the sibling HACKATHONS.md and `.scratch/decisions.md` in this repository.

## Spec update (after the first real runs)

- Out of Scope originally said the AI draws only the listed shape kinds. Extended: new geometry (square on a line, polygon, equation label) is in scope (ticket 18), and one question may be explained in several steps moved through by hotkey (ticket 19).
- Follow-up questions keep the same drawing by default; Ctrl+Shift+X starts a new topic (ticket 06).
- The model now receives a clean picture and a marked picture, plus line orientation and label-to-line hints. Region labels are written R1, R2, ... to avoid confusion with numbers in the picture.
- Practical findings: reasoning models need their long reasoning switched off for latency and empty replies (per-model request fields); on Windows the overlay window must be forced to the full display, or drawings drift.
