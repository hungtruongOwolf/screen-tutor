# Sherpa

**The AI guide that sees your screen, points at what to do next, and walks with you to the end.**

<p align="center"><img src="docs/img/loop.svg" alt="Sherpa sees the page, understands the goal, points at the next step, and follows you to the next page" width="100%"></p>

## The problem

Ask any AI "how do I create an IAM user for my CLI?" and you get correct steps, and still no idea where they are. The menu is called something slightly different. The button is on another page. So you scroll, you guess, you paste a screenshot and ask again, and again at the next page.

Sherpa is the guide that **sees the page you are on and shows you**: the box, the arrow, the next page, until you are done.

## What it does

- **Sees** the screen you are looking at, right now, and finds what is really on it with OpenCV 5.
- **Understands** the goal ("create an IAM user with an access key") and keeps it across pages.
- **Points** at the next step on your screen: a box, an arrow, a highlighted line, a diagram, a proof that moves.
- **Follows** you: when you click and the page changes, the old marks disappear at once and the next step appears, without you asking again.
- **Talks**: say "Hey Sherpa" and ask. Speech recognition and the voice run on your computer.

It teaches too: ask why the Pythagorean theorem is true and it draws the proof on top of the video that shows the triangle.

<!-- demo: add the video link and two GIFs (guided IAM task, animated proof) here -->

## Try it

**In the browser, nothing to install:** the [web playground](https://yz6et5qn3u2w247zc2rcndjxqa0tcgso.lambda-url.us-east-1.on.aws/) has sample screens, a made-up cloud console and a three-page task.

**On Windows, two steps:**

1. Download **Sherpa-Setup** from the [latest release](https://github.com/hungtruongOwolf/sherpa/releases/latest) and open it (a portable single file is there too). It installs for your user, no admin rights.
2. The first start downloads the speech models (about 200 MB, once). When the chat says the voice is ready, say **"Hey Sherpa, I need to create an IAM user. Where do I start?"** with a cloud console open, or press Ctrl+Shift+E to type.

The app is not code-signed, so Windows may say "unknown publisher": choose More info, then Run anyway.

## How it works

<p align="center"><img src="docs/img/system.svg" alt="The client on your computer, the backend on AWS Graviton, the models and tools" width="100%"></p>

1. **OpenCV 5 finds what is on the screen.** Text lines, lines of a drawing, controls, labels, figures and pictures become numbered regions with pixel boxes.
2. **The vision model chooses, it does not guess.** It picks regions by number and writes the steps, so every mark lands on a real element and never at an invented coordinate.
3. **Each step is drawn and said.** Captions and arrows are placed clear of text, animated, and rewritten as natural speech.
4. **The watcher keeps the thread.** The client keeps the goal and the conversation, watches the screen, clears stale marks the moment the page changes, and starts the next step when the page has settled. The backend is stateless.

## Guide, don't operate

Sherpa shows where to act and **you** act. Agents that click for you already exist (a CLI, a computer-use agent); a guide is useful for the opposite reason. You stay in control, you see where everything is, and you learn the interface you will use again tomorrow. It never clicks, types or changes anything on your behalf.

## What we measured

| | Result | Report |
|---|---|---|
| Pointing at the right region, 31 labelled cases, six models | The default model points correctly on all 31; the second model on 30 or 31 | [`backend/evaluation/report.md`](backend/evaluation/report.md) |
| Whole tasks over several pages, driven like the app drives them | 9 of 9 tasks completed with each of the two models, including leading the learner back after a wrong click | [`backend/evaluation/tasks_report.md`](backend/evaluation/tasks_report.md) |
| Graviton against x86 for the backend | About 22 % cheaper per turn, slightly faster | [`backend/evaluation/benchmark.md`](backend/evaluation/benchmark.md) |

## Built with

- **OpenCV 5**: the perception layer. Contours and text-line merging for regions, a Hough transform and closed-shape tracing for the sides of a drawing, texture statistics for pictures and free space, and a block-based change detector on a live frame stream. Code: `backend/app/regions.py`, `desktop/src/follow/`.
- **Nebius Token Factory**: the vision turns. DeepSeek V4.1 Flash as the default and Qwen3.8 as a second model asked when the first is slow (hedged requests), compared with four other models on the same cases.
- **NVIDIA Nemotron**: Nemotron-3-Super turns each step into natural speech, with reasoning off, and every rewrite is checked so it cannot lose a number or add a claim. Code: `backend/app/narration.py`.
- **Tavily**: when the screen does not hold a fact, the model asks for a web search and the answer shows its sources.
- **AWS Graviton**: the backend is a container on Lambda arm64 behind a streaming Function URL, with CloudWatch metrics and a CDK definition in `infra/`.

## Where it is going

Sherpa is built for any software, not for one subject: onboarding in enterprise tools, customer support with a shared screen, training from a recorded expert walkthrough, accessibility, and other agents that need eyes. The full design (agent graph, verifier, MCP tools, retrieval at task time, tenants, a browser extension and an SDK) is in [`ARCHITECTURE.md`](ARCHITECTURE.md).

## Documentation

- [`docs/usage.md`](docs/usage.md): keys, voice, following a task, recording a demo
- [`docs/development.md`](docs/development.md): run from source, tests, building the installer, deploying
- [`ARCHITECTURE.md`](ARCHITECTURE.md): the design of the full product
- [`docs/feedback.md`](docs/feedback.md): notes on the platforms we used
- [`infra/README.md`](infra/README.md): the AWS deployment

Licence: MIT ([`LICENSE`](LICENSE)).
