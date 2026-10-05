# screen-tutor: decisions (from grilling, 2026-10-03)

Product: Windows desktop overlay (Electron + TypeScript). User presses a hotkey and speaks; the app captures the screen, an AI explains it and draws on it. Flagship demo: learning from a CS lecture video; extension demo: teaching a software app.

- Capture: only on hotkey/trigger (active window or full screen), with a visible "capturing" indicator. Never continuous.
- Pointing: hybrid. OpenCV 5 proposes numbered candidate regions (text blocks, figures, changed areas); the model picks region IDs and explains; the overlay draws on those regions. Model never asked for raw pixel coordinates.
- Drawing: the model returns a list of shapes with IDs (arrow, box, highlight, label, step number, connector). Rendered as SVG on a transparent click-through window. Later turns can add/update/remove shapes by ID (persistent canvas). "See + reason -> shape list" is separate from "render", so other renderers can be added.
- Models: NVIDIA vision (Nemotron-Nano-V2-12b, Cosmos3-Super-Reasoner; test Nemotron-3-Nano-Omni) and NVIDIA Nemotron text for reasoning, via Nebius Token Factory. Model is a config value, easy to swap.
- Voice: push-to-talk. Claude API has no speech, Nebius has no speech models. STT/TTS chosen to need no company account (see below).
- Web demo: a small web page sharing the same backend: judge uploads a screenshot/video frame, sees OpenCV regions and the model's annotations. Backend on the owner's personal AWS account, arm64/Graviton (OpenCV COOL award), OpenCV 5 workload.
- Demo content: Creative Commons or self-recorded video; CS lecture (binary tree or backpropagation) + one short app-teaching clip.
- Awards targeted: OpenCV overall + Agentic Vision + COOL; Nebius track + Tavily (functional runtime call, e.g. look up/cite definitions while explaining) + Most Valuable Feedback.
- Owner participates as an individual, not via employer accounts; needs a personal AWS account.
