# COOL on Graviton4 against stock OpenCV 5

Measured 2026-10-06 on AWS EC2, us-east-1. Raw numbers: `cool/cool_1.json`, `cool/cool_2.json`, `cool/stock_1.json`, `cool/stock_2.json`.

## What was run

| | |
|---|---|
| Instance | `c8g.xlarge` (AWS Graviton4, Neoverse-V2, 4 vCPU), Ubuntu 24.04 |
| COOL | AWS Marketplace "Cloud Optimized OpenCV For AWS Graviton4" (product `prod-k6u24vxijyzvg`), AMI `ami-033e481a24f94c8cb` (`Graviton5-COOL-v3-prod-k6u24vxijyzvg`), Python 3.12 environment under `/opt/cool` |
| COOL build | `cv2.__version__` = `5.1.0-dev` (OpenCV 5 line), `-O3 -mcpu=neoverse-v2`, Custom HAL: **KleidiCV 0.7.0** and carotene, Arm Performance Libraries 25.07.1, NEON/SVE baseline |
| Baseline | the standard `opencv-python-headless==5.0.0.93` wheel from PyPI, same instance, Python 3.12, 4 threads |
| Workload | the real Sherpa region proposer (`app.regions.propose_regions`), unchanged: the OpenCV work of one turn |

Both builds run the identical code and produce the identical output: the same number of regions on every frame (bullets 7, console1 36, console2 34, console3 41, toolbar 12, triangle 9).

## Result

Region proposer on the six sample screens (1920 x 1080, JPEG quality 85), 90 timed calls per run after a warm-up round, two runs each, alternating COOL and stock:

| | COOL | stock OpenCV 5.0.0.93 |
|---|---|---|
| Mean, run 1 (ms) | 44.8 | 48.7 |
| Mean, run 2 (ms) | 47.4 | 48.9 |
| p50 (ms), runs 1 and 2 | 43.0 / 45.5 | 47.0 / 47.4 |
| p95 (ms), runs 1 and 2 | 56.8 / 59.5 | 64.2 / 64.4 |

On the whole proposer COOL is about 5 % faster (mean of the two runs 46.1 ms against 48.8 ms), and its p95 is lower in both runs.

Individual operations on a 1080p frame (mean ms, 100 to 200 calls, run 1):

| Operation | COOL | stock | Ratio |
|---|---|---|---|
| `adaptiveThreshold` (Gaussian) | 3.85 | 7.20 | **1.9x faster** |
| `GaussianBlur` 5x5 | 0.15 | 0.18 | 1.2x faster |
| `findContours` | 1.51 | 1.65 | 1.1x faster |
| `resize` 1920x1080 to 960x540, INTER_AREA | 0.26 | 0.28 | 1.1x faster |
| `resize` 1920x1080 to 1280x720, INTER_LINEAR | 1.03 | 0.30 | **3.4x slower** |

The gain on the proposer is smaller than on `adaptiveThreshold` because the proposer also runs Python, morphology, Hough and contour tracing that COOL does not change, and because a single `resize` in COOL's INTER_LINEAR path was slower than stock in this build (one operation, reported as measured).

## How this fits the deployment

The deployed Lambda (`benchmark.md`) runs stock OpenCV 5.0.0.93 on Graviton (arm64). COOL ships as an AMI, so the COOL path is an EC2 Graviton4 instance running the same backend code; the two paths share one codebase and one contract, and the region proposer is the part that was measured on both.

## Method (to reproduce)

1. Subscribe to the COOL listing on AWS Marketplace (7-day free trial; usage fee from 0.01 USD per hour for `c8g.large`/`c8g.xlarge`) and launch the AMI on a `c8g.xlarge`.
2. Copy `backend/app` and `backend/tools/cool_bench.py` to the instance.
3. COOL: `source /opt/cool/venvs/python_3.12/bin/activate`, install `pydantic` into a writable folder (`pip install --target ~/pyd pydantic`, then `export PYTHONPATH="$PYTHONPATH:$HOME/pyd"`), run `python tools/cool_bench.py --label cool --out cool_1.json`.
4. Stock: `python3 -m venv stock && stock/bin/pip install opencv-python-headless==5.0.0.93 numpy pydantic`, run it with `PYTHONPATH` and `LD_LIBRARY_PATH` unset (COOL's activation sets them and would load COOL's build): `stock/bin/python tools/cool_bench.py --label stock --out stock_1.json`.
5. Repeat both, alternating, and compare. Terminate the instance.

## Limits

One instance size, one afternoon, two runs; the numbers move by a few percent between runs. The COOL build reports `5.1.0-dev`, a different OpenCV revision from the stock 5.0.0.93 wheel, so the comparison covers the library as shipped, not an isolated switch of one optimisation. The benchmark times the OpenCV region proposer only (no model call).
