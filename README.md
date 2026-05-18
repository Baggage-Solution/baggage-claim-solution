# Baggage Damage Claim — WhatsApp AI

**ABC Airline · POC · 3-Week Sprint · $0 Budget**

Team: Anoushka · Aditya · Devam

---

## Quick Start (local, no Docker needed)

### 1. Clone & create virtual environment

```bash
git clone <repo-url>
cd baggage-claim-ai-starter

# Mac / Linux
python -m venv venv && source venv/bin/activate

# Windows
python -m venv venv && venv\Scripts\activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
# Open .env and fill in:
#   GEMINI_API_KEY      ← from https://ai.google.dev (free)
#   SUPABASE_URL        ← from your Supabase project settings
#   SUPABASE_SERVICE_ROLE_KEY  ← from Supabase → Settings → API
```

### 4. Run the backend

```bash
make run
# OR directly:
uvicorn backend.main:app --reload
```

- Swagger UI  → http://127.0.0.1:8000/docs
- Health check → http://127.0.0.1:8000/health
- Webhook     → POST http://127.0.0.1:8000/webhook

### 5. Run tests

```bash
make test
# tests/test_state.py has 7 tests that pass out of the box
```

---

## Architecture

```
backend/
  main.py                   FastAPI app entry point
  config.py                 All settings via pydantic-settings (reads .env)
  dependencies.py           DI container — @lru_cache provide_X() functions

  agents/
    base_agent.py           Abstract BaseAgent — extend for every agent
    a1_conversation.py      Conversation agent (LLM)
    a2_vision.py            Vision analysis agent (Gemini Vision)
    a3_ocr.py               OCR / bag tag agent (Gemini Vision)
    a4_decision.py          Decision engine — fraud checks, routing
    a5_notification.py      Notification — Lane 1 voucher / Lane 2 HITL

  graph/
    state.py                ClaimState dataclass (flows through all agents)
    orchestrator.py         LangGraph 5-agent pipeline

  vision_provider/          VisionProvider ABC + gemini_vision.py (POC)
  ocr_provider/             OCRProvider ABC + gemini_ocr.py (POC)
  llm_provider/             LLMProvider ABC + gemini_llm.py (POC)
  db/                       DBProvider ABC + supabase_client.py (POC)
  storage_provider/         StorageProvider ABC + local_storage.py (POC)

  core/
    exceptions.py           AppError hierarchy
    logging.py              Structured JSON logging + request-id context
    masking.py              PII redaction (PNR, bag ID, PAN, etc.)
    middleware.py           RequestContextMiddleware
    prompt_loader.py        JSON prompt file loader

  api/
    routes/health.py        GET /health
    routes/webhook.py       POST /webhook + POST /upload
    routes/decision.py      POST /decision (agent dashboard)
    schemas/                Pydantic request/response models

  prompts/                  JSON prompt templates for A1, A4, A5

tests/
  test_state.py             7 unit tests — run immediately, all pass
  fixtures/                 Test images (add damaged bags, tags, etc.)

BRANCH_DOCS/TEMPLATE.md    Copy per feature branch
```

## Swap any provider with one env var change

```bash
# Switch to Claude when ready (implement claude_llm.py first)
LLM_PROVIDER=claude uvicorn backend.main:app --reload

# Switch Vision to YOLOv8 (implement yolov8_vision.py first)
VISION_PROVIDER=yolov8 uvicorn backend.main:app --reload
```

No agent code changes — only the `.env` value changes.

---

## Environment variables

See `.env.example` — every variable is documented with a description.
Never commit `.env` — it is in `.gitignore`.

## Contributing

Branch naming: `feature/T-XXX-short-desc` · `chore/desc` · `integration/week-N-desc`
All branches merge to `develop` via PR. Never push directly to `main`.
See `BRANCH_DOCS/TEMPLATE.md` for per-branch documentation.
