# 15: Graviton versus x86 benchmark

**What to build:** A repeatable benchmark of the region proposer and of a full turn on arm64 and x86, with measured speed and cost, and a short written report, to support the Best Use of COOL award.

**Blocked by:** 03, 13

**Status:** resolved (2026-10-04)

- [ ] Benchmark script runs on both architectures from the documented setup
- [ ] Report shows latency and cost per turn for each
- [ ] Report states the method so results can be reproduced
- [ ] Findings are linked from the README

## Result (2026-10-04)

Benchmark stack `ScreenTutorBenchmark` (infra/lib/benchmark-stack.ts) and `backend/tools/benchmark.py`; report with method in `backend/evaluation/benchmark.md`, linked from the README. Graviton: 22 % cheaper per turn, about 4 % faster. The region proposer now takes about 207 ms warm at 1920 x 1080 (it was 35 to 60 ms before the occupancy and ink passes and on smaller frames): fast enough, but a candidate for optimisation if turn latency matters.
