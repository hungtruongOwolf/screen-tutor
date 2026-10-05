# Task effectiveness

Model: `deepseek-ai/DeepSeek-V4.1-Flash`. Live runs of the guide loop on the made-up Acme Cloud console (three pages). A task succeeds when every turn points at the control the learner needs next and gives the expected verdict (`evaluation/tasks.py` has the definitions; the screens are in `backend/app/static/samples`).

| Task | Runs | Succeeded | Turns pointed | Verdict right | Median s per turn |
|---|---|---|---|---|---|
| from-the-dashboard | 3 | 3/3 | 9/9 | 9/9 | 3.2 |
| starts-on-the-user-list | 3 | 3/3 | 6/6 | 6/6 | 3.2 |
| goes-back | 3 | 3/3 | 6/6 | 6/6 | 2.5 |

**Overall: 9/9 tasks completed.**
