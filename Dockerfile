# ── ABC Airline Baggage Claim AI — Production Dockerfile (P-010) ─────────────
#
# Single-stage build on python:3.11-slim.
# Same image runs as:
#   - API server:  uvicorn backend.main:app --host 0.0.0.0 --port 8000  (default CMD)
#   - Worker:      python -m backend.worker   (ECS task definition command override)
#
# Build: NEVER run docker build on office laptops.
#        GitHub Actions CI runner is the sole image builder (P-014).
#
# Size target: < 500MB image (verified by CI on every push).
# Startup target: < 8s cold start (uvicorn ready to serve /health).
#
# Authors: Devam + Aditya + Anoushka (unified branch — P-010)
# ─────────────────────────────────────────────────────────────────────────────

FROM python:3.11-slim

# ── System dependencies ───────────────────────────────────────────────────────
# curl  — healthcheck (ECS target group checks /health via curl)
# No build tools needed; all packages in requirements.txt are pure-Python or
# have pre-built wheels on PyPI for linux/amd64.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# ── Working directory ─────────────────────────────────────────────────────────
WORKDIR /app

# ── Python dependencies ───────────────────────────────────────────────────────
# Copy requirements before the rest of the source so Docker caches this layer
# independently of code changes — pip install only reruns when requirements.txt
# changes.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# ── Application source ────────────────────────────────────────────────────────
# .dockerignore excludes: frontend/, tests/, .env*, BRANCH_DOCS/, .git/,
# __pycache__, *.pyc, docs/, deploy/ — backend/ + prompts/ + config files only.
COPY backend/ ./backend/
# Prompts directory (YAML/JSON files read at runtime by PromptLoader)
COPY backend/core/prompt_loader.py ./backend/core/prompt_loader.py

# Copy any top-level package config files needed at runtime
COPY pyproject.toml pytest.ini* ./

# ── Non-root user — principle of least privilege ──────────────────────────────
RUN useradd --create-home --shell /bin/sh appuser
USER appuser

# ── Port ──────────────────────────────────────────────────────────────────────
EXPOSE 8000

# ── Health check ──────────────────────────────────────────────────────────────
# ECS uses the ALB target group health check; this Docker HEALTHCHECK is for
# local `docker run` and CI validation only. Interval/timeout sized for cold
# start: first check at 15s, then every 30s.
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# ── Default entrypoint — API server ──────────────────────────────────────────
# The ECS worker task definition overrides this with:
#   "command": ["python", "-m", "backend.worker"]
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "1", "--log-level", "info"]
