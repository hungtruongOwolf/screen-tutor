# Deploying the backend on AWS (Graviton)

The backend runs as a **container on AWS Lambda, arm64 (AWS Graviton)**, behind a public HTTPS Function URL. Everything is defined as code with the AWS CDK, so a clean checkout can rebuild it.

```
desktop app / web page  --HTTPS-->  Lambda Function URL  -->  FastAPI (OpenCV 5)  -->  Nebius Token Factory (vision model)
                                         |
                                         +--> CloudWatch Logs + metrics + dashboard
```

What is created: one Lambda function (arm64, 2 GB, 120 s timeout) built from `backend/Dockerfile`, its Function URL, a log group (one month retention) and a CloudWatch dashboard named `Sherpa`. The one-time `cdk bootstrap` also creates the CDK's own storage bucket, container repository and roles.

## Requirements

- An AWS account and the AWS CLI configured (`aws sts get-caller-identity` works).
- Node.js 22 and Docker (Docker Desktop on Windows). Docker builds the arm64 image; on an x86 machine this uses emulation and the first build takes several minutes.
- A Nebius Token Factory API key.

## Deploy

1. Copy `.env.example` to `.env` at the repository root and fill in `NEBIUS_API_KEY` and a long random `BACKEND_ACCESS_TOKEN` (optionally `TAVILY_API_KEY`, `MODEL_NAME`). `.env` is git-ignored.
2. From this folder:

```bash
npm install
npx cdk bootstrap        # once per account and region
npx cdk deploy
```

The output shows `FunctionUrl`. Check it: `GET <FunctionUrl>/health` answers `{"status":"ok","model":"..."}`.

3. Point the desktop app at it by setting `EXPLAIN_BACKEND_URL=<FunctionUrl>` (no trailing slash) in `.env` and starting the app. The app sends `BACKEND_ACCESS_TOKEN` with every request.

## Live streaming

The Function URL uses invoke mode `RESPONSE_STREAM` and the function sets `AWS_LWA_INVOKE_MODE=response_stream`, so the steps of an answer reach the client one by one while the model is still writing (`POST /explain-turn/stream`, newline-delimited JSON). With a plain buffered Function URL everything would arrive at the end.

If the main model is slow (no step after `HEDGE_AFTER_SECONDS`, default 4), the same request also goes to a second model (`MODEL_FALLBACK_NAME`, default `Qwen/Qwen3.8-27B`; empty switches it off) and whichever answers first is used.

## Security and privacy

- `POST /explain-turn` needs `Authorization: Bearer <BACKEND_ACCESS_TOKEN>`. `/health` is open.
- No screenshot is stored. The service keeps nothing between requests.
- Logs hold numbers only (latency, counts, status), never an image, a question or an answer.
- The keys are environment variables of the function: encrypted at rest by AWS and visible to administrators of the account. Use Secrets Manager for anything shared.
- Cost control: pay per request. Set an AWS Budget alert on the account anyway.

## Observability

- Logs: CloudWatch log group `/screen-tutor/explain`.
- Metrics (namespace `ScreenTutor`, from the service's embedded metric lines): `TurnLatencyMs`, `ModelLatencyMs`, `RegionsLatencyMs`, `Attempts`, `Regions`, `Steps`, `DroppedShapes`, `TurnFailures`. Lambda's own `Invocations`, `Errors` and `Duration` come with it.
- The `Sherpa` dashboard graphs them.

## Benchmark (Graviton against x86)

```bash
npx cdk deploy ScreenTutorBenchmark -c benchmark=true --require-approval never --outputs-file out.json
# then, in backend/: python tools/benchmark.py --arm <Urlarm64> --x86 <Urlx86> --token <BACKEND_ACCESS_TOKEN>
npx cdk destroy ScreenTutorBenchmark -c benchmark=true --force
```

Two functions with the same image code and the canned model; results and method in `backend/evaluation/benchmark.md`.

## Tear down

```bash
npx cdk destroy
```

(The bootstrap stack stays; delete the `CDKToolkit` stack and its bucket and repository to remove it too.)
