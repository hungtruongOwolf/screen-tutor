# 11: Robust turn orchestration

**What to build:** The turn runs as a bounded loop: it validates the model output against known region ids and screen bounds, asks the model to repair invalid output, falls back to a second configured model, enforces a time limit and an attempt limit, and shows the learner a clear message when it cannot answer.

**Blocked by:** 04

**Status:** ready-for-agent

- [ ] Invalid region ids or out-of-bounds shapes trigger a repair attempt, then a clear failure after the limit
- [ ] Time and attempt limits are configurable and enforced
- [ ] A model error or timeout falls back to the configured second model
- [ ] The learner sees a plain message instead of an empty screen on failure
- [ ] Tests simulate each failure with the recorded adapter
