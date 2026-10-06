# Graviton (arm64) versus x86_64

Measured 2026-10-04 on AWS Lambda, us-east-1. Raw numbers: `benchmark.json` next to this file.

## Result

| | arm64 (Graviton) | x86_64 |
|---|---|---|
| Region proposer, mean (ms) | 207 | 215 |
| Region proposer, p95 (ms) | 262 | 273 |
| Service time per turn, mean (ms) | 207 | 215 |
| Service time per turn, p95 (ms) | 263 | 273 |
| Client wall time, p50 (ms) | 505 | 512 |
| First call after deploy (ms) | 630 | 559 |
| Compute cost per 1000 turns (USD) | 0.0057 | 0.0074 |

On this workload Graviton is about 4 % faster and **22 % cheaper per turn**. The price gap is almost all of the
saving (1.33 against 1.67 microdollars per GB-second); the speed difference is small, so the ranking would not
change if AWS repriced one of them a little. The same Docker image code builds for both (`linux/arm64` and
`linux/amd64`), so moving between them is a one-line change in the CDK stack.

What it means for a turn: the OpenCV work costs 0.0057 USD per 1000 turns on Graviton. The model call
(seconds, billed by Nebius) is what a turn really costs; the part that runs on our own compute is a rounding error
and is the same speed on either architecture, so Graviton is the right default and not a trade-off.

## Method (to reproduce)

1. In `infra/`: `npx cdk deploy SherpaBenchmark -c benchmark=true --require-approval never --outputs-file out.json`.
   This creates two Lambda functions from the same backend image code, `sherpa-bench-arm64` and
   `sherpa-bench-x86`, both 2048 MB, both with the canned model (`MODEL_ADAPTER=fake`), so no model call is
   in the measurement. The stack prints their Function URLs.
2. In `backend/`: `python tools/benchmark.py --arm <url> --x86 <url> --token <BACKEND_ACCESS_TOKEN> --runs 15 --out evaluation/benchmark.json`.
   It sends the six sample screens of the repository (scaled to 1920 x 1080, JPEG quality 85, the way the desktop
   app sends a capture) to each function: one first call, one warm-up round, then 15 rounds, 90 timed turns per
   architecture.
3. `npx cdk destroy SherpaBenchmark -c benchmark=true --force` removes the functions.

What the numbers are:

- **Region proposer / service time**: the service's own timers (`trace.timings_ms`), measured inside the
  function. With the canned model, service time is the region proposer plus building the answer.
- **Client wall time**: seen from a laptop on a home connection, so it includes the network (about 300 ms).
- **Cost**: service time x memory (GB) x the us-east-1 price per GB-second, plus the 0.20 USD per million request
  charge. Lambda bills per millisecond, so service time stands in for billed duration; the real bill adds a few
  milliseconds of runtime overhead, the same on both.
- **First call after deploy**: one sample per architecture, so it is noise, not a cold-start benchmark.

## Limits

- One region, one memory size (2048 MB), six frames, one afternoon. Lambda CPU scales with memory, so a
  different size shifts both columns.
- The x86 fleet may use different CPU models from call to call, which adds a few percent of noise; that is why
  the speed difference should not be quoted as a precise number.
