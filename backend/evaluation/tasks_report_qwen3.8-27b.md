# Task effectiveness

Model: `Qwen/Qwen3.8-27B`. Live runs of the guide loop on the made-up Acme Cloud console (three pages). A task succeeds when every turn points at the control the learner needs next and gives the expected verdict (`evaluation/tasks.py` has the definitions; the screens are in `backend/app/static/samples`).

| Task | Runs | Succeeded | Turns pointed | Verdict right | Median s per turn |
|---|---|---|---|---|---|
| from-the-dashboard | 3 | 3/3 | 9/9 | 9/9 | 3.6 |
| starts-on-the-user-list | 3 | 3/3 | 6/6 | 6/6 | 4.8 |
| goes-back | 3 | 3/3 | 6/6 | 6/6 | 2.9 |

**Overall: 9/9 tasks completed.**
