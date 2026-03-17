# ─────────────────────────────────────────────────────────────────────────────
# QOpz.AI — API Docker Image
# Target: Fly.io (fra), ARM-compatible, Python 3.12
# Serve: FastAPI + uvicorn on :8765
# Volume: /app/db  (DuckDB persistent)
# ─────────────────────────────────────────────────────────────────────────────

FROM python:3.12-slim

# System libs: libgomp1 required by xgboost/scikit-learn (OpenMP)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 \
        curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    OPZ_PROFILE=dev

WORKDIR /app

# ── Python dependencies ───────────────────────────────────────────────────────
COPY requirements-core.txt requirements-web.txt ./
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir \
        -r requirements-core.txt \
        -r requirements-web.txt

# ── Application code ──────────────────────────────────────────────────────────
COPY api/          api/
COPY execution/    execution/
COPY strategy/     strategy/
COPY config/       config/
COPY rebuild_manifest.py ./

# ── Runtime directories (db/ sarà montato come volume su Fly.io) ──────────────
RUN mkdir -p db logs ops reports

# ── Health check ──────────────────────────────────────────────────────────────
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8765/health || exit 1

EXPOSE 8765

CMD ["uvicorn", "api.opz_api:app", \
     "--host", "0.0.0.0", \
     "--port", "8765", \
     "--workers", "1", \
     "--log-level", "info"]
