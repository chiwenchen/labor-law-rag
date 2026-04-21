# syntax=docker/dockerfile:1.7
# Multi-stage: `dev` target for local Compose (bind-mount + reload),
# `prod` target for GHCR → EC2 (no bind-mount, non-root, tini).

FROM python:3.11-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
        tini \
        curl \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install -r requirements.txt

# ---------- dev ----------
FROM base AS dev
COPY app/ ./app/
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ---------- prod ----------
FROM base AS prod
RUN useradd --system --uid 1000 --home /app app \
    && mkdir -p /app/.cache/huggingface \
    && chown -R app:app /app
COPY --chown=app:app app/ ./app/
USER app
ENV HF_HOME=/app/.cache/huggingface
HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=300s \
    CMD python -c "import urllib.request,sys;sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health',timeout=3).status==200 else 1)"
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
