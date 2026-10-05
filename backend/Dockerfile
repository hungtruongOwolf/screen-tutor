# The backend as a container for AWS Lambda (arm64 / Graviton).
# AWS Lambda Web Adapter lets the same FastAPI app run behind a Lambda Function URL.
FROM public.ecr.aws/docker/library/python:3.11-slim

COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:0.9.1 /lambda-adapter /opt/extensions/lambda-adapter

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8080 \
    AWS_LWA_PORT=8080 \
    AWS_LWA_READINESS_CHECK_PATH=/health

WORKDIR /app
COPY pyproject.toml ./
# Install the dependencies first, with an empty stand-in for the package, so this
# slow layer (it compiles under emulation on x86 machines) is cached and only
# runs again when pyproject.toml changes.
RUN mkdir app && touch app/__init__.py && pip install . && rm -rf app
# The real code: changes here are quick to rebuild. /app comes first on sys.path,
# so it is the one that runs.
COPY app ./app

CMD ["python", "-m", "uvicorn", "app.server:app", "--host", "0.0.0.0", "--port", "8080"]
