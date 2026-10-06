# 05: Evaluation harness for region picking

**What to build:** A set of labelled screenshots and questions, and a command that runs them against one or more configured models and reports region-pick accuracy. The result is used to choose the default model and is kept as evidence of task-effectiveness evaluation for the competition write-ups.

**Blocked by:** 04

**Status:** ready-for-agent

- [x] At least 30 labelled cases (31: right triangles in 4 orientations and 2 themes, toolbars, bullet slides; drawn in code, repeatable). Real frames can be added the same way
- [x] One command runs the set against chosen models and prints accuracy per model: python -m evaluation.run --models a,b
- [ ] Nemotron-Nano-V2-12b, Cosmos3-Super-Reasoner and Nemotron-3-Nano-Omni are compared and the best is recorded as the default (NOT possible yet: they have no public endpoint on Nebius; compared the public vision models instead; default stays deepseek-ai/DeepSeek-V4.1-Flash)
- [x] The harness is separate from the normal test run and is not part of CI (only its cases and scoring are unit tested)
- [x] Results are saved in a short written report (backend/evaluation/report.md and results.json)

## Results (2026-10-03, 31 synthetic cases, live models on Nebius Token Factory)

| Model | Pointed correctly | Keyword correct | Failed | Median seconds |
|---|---|---|---|---|
| deepseek-ai/DeepSeek-V4.1-Flash | 31/31 | 11/12 | 0 | 2.6 |
| Qwen/Qwen3.8-27B | 31/31 | 12/12 | 0 | 2.4 |
| zai-org/GLM-5.3-Flash | 31/31 | 11/12 | 0 (2 retried) | 5.9 |
| moonshotai/Kimi-K2.6 | 27/27 | 8/8 | 4 | 6.0 |
| google/gemma-3-27b-it | 26/29 | 7/10 | 2 | 3.5 |
| openbmb/MiniCPM-V-4_5 | 25/30 | 6/11 | 1 | 2.3 |

- Keep DeepSeek-V4.1-Flash as the default: it was used for every real-frame test (including the 4-step Pythagoras walkthrough with squares). Qwen3.8-27B is just as accurate and fast on these cases and a good fallback (on the real walkthrough it was correct but worded 'cube' for 'square' in Vietnamese).
- The synthetic cases are easy and clean; they separate weak models from strong ones but do not prove real-world accuracy. Add real frames (equations, small text, video frames) when available.
