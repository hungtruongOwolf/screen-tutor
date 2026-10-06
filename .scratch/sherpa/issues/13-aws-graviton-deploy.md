# 13: Deploy the backend on AWS Graviton

**What to build:** The backend runs as an arm64 container on the owner's personal AWS account, defined as code, with pinned dependencies. It requires an access token, rate-limits callers, keeps no screenshots after a turn, and emits structured logs and metrics. The desktop app can point at the cloud backend.

**Blocked by:** 04, 01

**Status:** ready-for-agent

- [x] Deployment is reproducible from a clean checkout with documented commands (infra/README.md: npm install, cdk bootstrap, cdk deploy)
- [x] Requests without a valid token are rejected (401, verified live) and rate limits apply (30 per minute per key by default, per instance; a hard spend cap needs an AWS Budget)
- [x] No image is stored after a turn and logs contain no image data (checked in the live CloudWatch logs: no question, image data or token)
- [x] Logs are visible in AWS (/sherpa/explain); metrics are written in embedded metric format (namespace Sherpa) with a dashboard named Sherpa (metrics take some minutes to appear)
- [ ] The desktop app works against the cloud backend (it sends JPEG and the bearer token; the same calls were verified by script; set EXPLAIN_BACKEND_URL; not yet run by the owner)

## Deployed (2026-10-03)

- Lambda container, arm64 (Graviton), 2 GB, 120 s, Function URL in us-east-1; stack Sherpa, bootstrap done. Cold start 9 to 12 s, warm turn 2 to 4 s; the OpenCV region step takes about 35 to 60 ms warm.
- Keys are Lambda environment variables (not Parameter Store): fine for a personal project, noted in infra/README.md.
- Lambda Web Adapter runs the unchanged FastAPI app. Captures are sent as JPEG (a 6 MB request limit applies).
- Dockerfile caches the dependency layer (emulated arm64 builds on x86 are slow: about 10 minutes for the first build).
- Lessons: cv2.imwrite cannot write to a path with non-ASCII characters on Windows; tests must not read the developer's .env (conftest isolates them).
