run:
	uvicorn backend.main:app --reload --port 8000

test:
	pytest tests/ -v

lint:
	black backend/ && isort backend/

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete
	find . -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
