# Task effectiveness

Does the tutor get a learner through a task of several screens? `python -m evaluation.tasks --model <id> --repeat 3` runs the loop the desktop app runs (a question on the first screen, then an automatic turn each time the screen changes, carrying the goal, the conversation, the drawings and the regions of the last capture) on the made-up Acme Cloud console (three pages: dashboard, user list, create-user form). A task succeeds when **every** turn points at the control the learner needs next **and** gives the expected verdict (continue = on the way, off_track = went the wrong way). Live models on Nebius Token Factory, 2026-10-05, three runs of each task.

## Result

DeepSeek-V4.1-Flash (default):

| Task | Runs | Succeeded | Turns pointed | Verdict right | Median s per turn |
|---|---|---|---|---|---|
| from-the-dashboard | 3 | 3/3 | 9/9 | 9/9 | 3.2 |
| starts-on-the-user-list | 3 | 3/3 | 6/6 | 6/6 | 3.2 |
| goes-back | 3 | 3/3 | 6/6 | 6/6 | 2.5 |

**Overall: 9/9 tasks completed.**

Qwen3.8-27B (the second model of the hedged request):

| Task | Runs | Succeeded | Turns pointed | Verdict right | Median s per turn |
|---|---|---|---|---|---|
| from-the-dashboard | 3 | 3/3 | 9/9 | 9/9 | 3.6 |
| starts-on-the-user-list | 3 | 3/3 | 6/6 | 6/6 | 4.8 |
| goes-back | 3 | 3/3 | 6/6 | 6/6 | 2.9 |

**Overall: 9/9 tasks completed.**

Run to run the models vary a little: an earlier identical run of Qwen3.8-27B completed 8 of 9 (on one turn it pointed correctly but gave no verdict, so the tutor would not have said whether the learner was on track), and an earlier run of DeepSeek-V4.1-Flash completed 9 of 9. Raw results of the runs above: `tasks_results_<model>.json`; per-model tables: `tasks_report_<model>.md`.

## What the first run taught us

The first run of the same tasks, worded "I need an access key for my app", completed 3 of 9 (DeepSeek-V4.1-Flash). Most misses were not wrong answers: on the user list the model pointed at the existing user `ci-bot` ("it already has programmatic access, open it"), which is a reasonable reading of an ambiguous request, while the task expected "Create user". One run did go wrong in a plain way (on the Access & Identity page it said to click Secrets). We reworded the request so there is one right way ("a new user for my app that can use an access key") and kept the existing user as a distractor; the table above is that version. So: with a clear goal the loop completed 9/9 for both models (8/9 once for Qwen), with a vague one a model may take a different, valid path, and the task checker (a fixed expected control) cannot tell the difference. The goal wording matters, and the tutor's habit of stating the goal back in the first answer (the chat shows it) is there so that the learner can correct it.

## Limits

Three pages of a made-up console, nine runs per model, one afternoon: this shows the loop works end to end, not how it does on any real site. The `done` verdict (task finished) is not covered because the mock has no confirmation page. The region-pick cases (`report.md`) are a different, easier test: one picture, one pointer.
