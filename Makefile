# ── ABC Airline Baggage Claim AI — Makefile ──────────────────────────────────
# Targets:
#   make run      — start API server (dev, QUEUE_PROVIDER=memory, ENABLE_SIMULATOR=true)
#   make worker   — start SQS worker (P-008; needs QUEUE_PROVIDER=sqs + SQS_QUEUE_URL)
#   make test     — run full pytest suite
#   make lint     — black + isort
#   make clean    — remove __pycache__, .pyc, .pytest_cache
# ─────────────────────────────────────────────────────────────────────────────

# API server — local dev, simulator active, in-memory queue
run:
	ENABLE_SIMULATOR=true uvicorn backend.main:app --reload --port 8000

# Worker — long-poll SQS loop (P-008)
# Requires: QUEUE_PROVIDER=sqs and SQS_QUEUE_URL set in .env or environment.
# In production, ECS overrides the Docker CMD — this Makefile target is for
# local testing against a moto-mocked or real SQS queue.
worker:
	python -m backend.worker

test:
	pytest tests/ -v

lint:
	black backend/ && isort backend/

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete
	find . -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true