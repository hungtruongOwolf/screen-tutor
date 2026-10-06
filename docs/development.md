# Developing Sherpa

## Requirements

Windows 10 (2004+) or 11, Node.js 22+, Python 3.11+.

## Pieces

- `desktop/`: the Windows app (Electron).
- `backend/`: the Explain Turn service (Python, FastAPI, OpenCV 5). Also serves the public web playground at `/`.
- `backend/evaluation/`: 31 labelled cases and `python -m evaluation.run --models a,b` (report in `backend/evaluation/report.md`).
- `infra/`: AWS CDK for the backend as an arm64 (Graviton) Lambda container. See `infra/README.md`.

To use the deployed backend from the desktop app, set `EXPLAIN_BACKEND_URL` to its address and `BACKEND_ACCESS_TOKEN` in `.env`.

## Run it

Backend (terminal 1):

```powershell
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m uvicorn app.server:app --port 8000
```

`backend/requirements.lock` has the exact versions the evaluation and the benchmark were run with (OpenCV `opencv-python-headless==5.0.0.93`); for a reproducible install use `pip install -r requirements.lock` and then `pip install --no-deps -e .`. The desktop app's versions are pinned by `desktop/package-lock.json` (`npm ci`).

Desktop app (terminal 2):

```powershell
cd desktop
npm install
node node_modules/electron/install.js   # only if npm skipped the Electron download
npm start
```

Settings come from environment variables or a local `.env` (copy `.env.example`; `.env` is git-ignored). The backend reads `.env` once when it starts: after editing it, stop the backend (Ctrl+C) and start it again. `MODEL_ADAPTER=fake` gives a canned answer with no network; `MODEL_ADAPTER=nebius` calls the real model (needs `NEBIUS_API_KEY`; `MODEL_NAME` picks the model, default `deepseek-ai/DeepSeek-V4.1-Flash`).

Try the real model on any image without the desktop app:

```powershell
cd backend
.\.venv\Scripts\python.exe toolssk_model.py my-screenshot.png "What is x in the triangle?" out.png
```

## Tests

```powershell
cd backend; .\.venv\Scripts\python.exe -m pytest      # seam 1: Explain Turn
cd desktop; npm test                                  # seam 2: overlay renderer
cd desktop; npm run typecheck
```

Not covered by automated tests (check by hand): screen capture, global hotkeys, click-through, and that the overlay does not appear in captures.

## Reproduce the evaluation

All of these need `NEBIUS_API_KEY` in `.env` and call a live model (a few cents each); results are written next to the scripts in `backend/evaluation/`.

- `python -m evaluation.run --models a,b`: 31 labelled screens, one mark each (`report.md`).
- `python -m evaluation.tasks --model <id> --repeat 3`: whole tasks across three pages (`tasks_report.md`).
- `python tools/trace.py`: a decision trace of the guide loop, what OpenCV found and what the agent did next (`trace.md`).
- COOL against stock OpenCV on Graviton4: `evaluation/cool.md` (method and the benchmark `tools/cool_bench.py`).
- Graviton against x86: see "Deploying and measuring on AWS"; the method is in `benchmark.md`.

## Look at what the region proposer finds

```powershell
cd backend
.\.venv\Scripts\python.exe tools\draw_regions.py lecture out.png      # fixtures: lecture, lecture_changed, app
.\.venv\Scripts\python.exe tools\draw_regions.py my-screenshot.png out.png
```

It saves the image with every numbered region drawn on it and prints the list. `MAX_REGIONS` (default 70) caps the count. Lines of text are separate regions unless packed like a paragraph, so a menu item or a list row can be pointed at.

## Manual smoke test

1. Start the backend and the desktop app as above.
2. The chat panel opens in the bottom right corner. Type a question about what is on screen and press Enter. With `MODEL_ADAPTER=fake` a red box labelled "Walking skeleton" appears; with `nebius` the model draws and explains (about 3 to 8 seconds).
   Try "Explain why the Pythagorean theorem is true" on a video with a right triangle: a proof diagram appears beside it and the four triangles slide into their new places. Move through the steps with the panel buttons or Ctrl+Shift+. and Ctrl+Shift+,.
   Then type a follow-up (no hotkey needed): the conversation and the drawing carry on.
   Try the guide: open a page you find confusing and ask "I am lost, where do I click to ...?".
3. Click through the box onto the window underneath: the click must reach that window.
4. Press Ctrl+Shift+X: the drawings disappear (the chat stays). Press Ctrl+Shift+N: the chat starts empty.
5. Stop the backend and send a message: the chat says the backend cannot be reached.
6. With the backend running, send a message, then press Ctrl+Shift+D: numbered, coloured boxes appear over the text blocks, figures and controls on your screen (blue text, green figure, red control). Press Ctrl+Shift+D again to hide them.

## Building the installer

`cd desktop; npm install; npm run package -- --url=https://<your function url>.on.aws` writes both files to `desktop/release/`. Tested here on a clean set of data folders: the installer's program starts, downloads the voice models by itself and starts listening without a restart.

## Deploying and measuring on AWS

`infra/README.md`: `cd infra; npx cdk deploy` deploys the backend as an arm64 Lambda container with a streaming Function URL and a CloudWatch dashboard. `npx cdk deploy SherpaBenchmark -c benchmark=true` creates the arm64 and x86 pair for the benchmark (destroy it afterwards with `cdk destroy`).

Vocabulary used in the code and the tickets (Turn, Capture, Region, Shape, Canvas, Overlay, Explain Turn) is in `CONTEXT.md`.
