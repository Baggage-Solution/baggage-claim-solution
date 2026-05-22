# BRANCH: feature/fastapi-base

---

## Branch Metadata

```
Branch Name   →  feature/fastapi-base
Task ID       →  T-004
Workstream    →  Backend / API
Author        →  Devam
Reviewer      →  Aditya
Start Date    →  Day 2, Week 1
Target Merge  →  Day 2, Week 1
Actual Merge  →  Day 2, Week 1
Status        →  Merged
```

---

## Objective

**What does this branch do?**
Sets up the FastAPI application with a `/webhook` POST endpoint, `/health` GET endpoint,
CORS configuration, structured logging middleware, and WhatsApp signature verification stub.
This is the entry point for all incoming messages from the WhatsApp simulator into the
5-agent LangGraph pipeline.

**Why is it needed?**
T-004 is the backend foundation. Every other backend task (T-005, T-008, T-009) depends
on this running. Without the webhook endpoint, no message can reach the AI agents.
The `/health` endpoint also lets the team confirm the server is running and all providers
are configured correctly before starting integration work.

---

## Local Setup — Run This First

```bash
# 1. Create virtual environment
python -m venv venv

# 2. Activate virtual environment (Windows)
venv\Scripts\activate

# 3. Install all dependencies
pip install -r requirements.txt

# 4. Copy env file and fill in your keys
cp .env.example .env
# Open .env and fill: GEMINI_API_KEY, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY

# 5. Start the server
uvicorn backend.main:app --reload --port 8000
```

Server is ready when you see:
```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Application startup complete.
```

> **Windows note:** `make run` requires GNU Make. If not installed, use the uvicorn
> command above directly. Install make via: `winget install GnuWin32.Make`

---

## Technical Approach

**Files Created:**
```
None — all files existed in the starter kit as stubs
```

**Files Modified:**
```
backend/api/routes/webhook.py   →  Added verify_whatsapp_signature() function
                                    Added signature verification to POST /webhook
                                    Added structured logging on every request
                                    Added type hints + Google-style docstrings

.env.example                    →  Updated GEMINI_MODEL and GEMINI_VISION_MODEL
                                    from gemini-1.5-flash (deprecated) to gemini-2.5-flash
                                    Added comment explaining the model upgrade
```

**Files Already Complete in Starter (No Changes Needed):**
```
backend/main.py                         →  FastAPI app, CORS, middleware, router registration
backend/api/routes/health.py            →  /health GET endpoint (fully complete)
backend/api/schemas/claim_request.py    →  WebhookRequest model
backend/api/schemas/claim_response.py   →  WebhookResponse model
backend/core/logging.py                 →  Structured JSON logging with request_id
backend/core/middleware.py              →  RequestContextMiddleware (request_id per request)
backend/core/exceptions.py             →  AppError, UpstreamServiceError etc.
backend/dependencies.py                 →  Provider factory functions
backend/graph/orchestrator.py           →  ClaimOrchestrator + LangGraph pipeline
```

**Provider / Abstraction Used:**
```
No new providers introduced in T-004.
ClaimOrchestrator (already wired) runs the full 5-agent pipeline on every /webhook call.
Provider injection happens via dependencies.py — no provider imported directly in routes.
```

**Key Design Decisions:**

```
1. SIGNATURE VERIFICATION — POC STUB PATTERN
   verify_whatsapp_signature() checks for WHATSAPP_APP_SECRET in .env.
   If not set → skips verification (returns True) → simulator works freely.
   If set → full HMAC-SHA256 verification runs automatically.
   Result: zero code changes needed to go from POC to production — just add the env var.

2. GEMINI MODEL UPGRADE
   gemini-1.5-flash is deprecated as of early 2026.
   Upgraded to gemini-2.5-flash (stable GA) in .env.example.
   Ref: https://ai.google.dev/gemini-api/docs/models

3. HMAC CONSTANT-TIME COMPARE
   Used hmac.compare_digest() instead of == for signature comparison.
   Prevents timing attacks where an attacker could guess the signature
   character by character by measuring response times.

4. STRUCTURED LOGGING ON EVERY REQUEST
   Every /webhook call logs: session_id, message_preview (first 50 chars),
   image_count, and request_id. Makes debugging and tracing easy across
   the full pipeline without exposing sensitive passenger data.

5. ASYNC THROUGHOUT
   All routes use async def as required by coding standards.
   No sync FastAPI routes anywhere in the codebase.
```

**Future Swap Path:**
```
POC  → Production:  Set WHATSAPP_APP_SECRET in .env — verification activates instantly
POC  → Production:  Restrict CORS origins in main.py (currently allow_origins=["*"])
Phase 2:            Add rate limiting middleware per session_id
Phase 2:            Add request size limits for image uploads
```

---

## What Happens When /webhook is Called

```
Incoming POST /webhook
        ↓
RequestContextMiddleware     → assigns unique request_id
        ↓
verify_whatsapp_signature()  → validates X-Hub-Signature-256 (skipped in POC)
        ↓
logger.info("webhook_received")
        ↓
ClaimOrchestrator.run()      → builds ClaimState, runs LangGraph graph
        ↓
    A1 ConversationAgent     → sets a1_response, advances conversation_step
    A2 VisionAgent           → analyzes damage photos (stub until T-006/T-010)
    A3 OCRAgent              → extracts bag tag data (stub until T-007/T-011)
    A4 DecisionAgent         → generates claim_id, sets routing_lane, fraud_score
    A5 NotificationAgent     → generates voucher_code (Lane 1) or queues HITL (Lane 2)
        ↓
WebhookResponse              → returned to simulator with full pipeline output
```

---

## Dependencies

```
Depends On          →  T-002 (env + deps setup — venv + requirements.txt must work)
External Libraries  →  fastapi==0.115.0, uvicorn==0.32.0 (see requirements.txt)
Environment Vars    →  GEMINI_API_KEY, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
                       GEMINI_MODEL=gemini-2.5-flash
                       GEMINI_VISION_MODEL=gemini-2.5-flash
                       WHATSAPP_APP_SECRET= (leave empty for POC)
```

---

## Testing

**How to Test (Manual):**

```bash
# Terminal 1 — start server
uvicorn backend.main:app --reload --port 8000

# Terminal 2 — run tests

# Test 1: Health check
curl http://localhost:8000/health
# Expected: {"status":"ok","service":"baggage-claim-ai","configured":{"gemini":true,"supabase":true},...}

# Test 2: Webhook POST
curl -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -d "{\"session_id\": \"s1\", \"message\": \"hi my bag is damaged\"}"
# Expected: {"session_id":"s1","reply":"[A1 stub]...","claim_id":"CLM-...","routing_lane":1,...}

# Test 3: API docs
# Open in browser: http://localhost:8000/docs
# Expected: Swagger UI showing /health, /webhook, /upload, /decision
```

**Automated Tests:**
```bash
# Run from project root with venv active
pytest tests/ -v

# Expected output:
# tests/test_state.py::test_default_state               PASSED
# tests/test_state.py::test_set_error                   PASSED
# tests/test_state.py::test_add_debug                   PASSED
# tests/test_state.py::test_lane1_eligible_low_value    PASSED
# tests/test_state.py::test_lane1_ineligible_high_value PASSED
# tests/test_state.py::test_lane1_ineligible_luxury     PASSED
# tests/test_state.py::test_lane1_ineligible_high_fraud PASSED
# 7 passed
```

**Test Data:** No fixture files needed — unit tests use in-memory ClaimState objects.

**Acceptance Criteria:**
```
✅ curl /health → 200 with {"status":"ok"} and all providers listed
✅ curl POST /webhook → 200 with stub A1 reply + claim_id + voucher_code
✅ Signature verification present — skips gracefully when secret not set
✅ async def used throughout — no sync routes
✅ No hardcoded keys — all via os.getenv() / Settings
✅ Type hints on all functions
✅ Google-style docstrings on all public functions
✅ black + isort run clean (24 files reformatted, 0 errors)
✅ pytest → 7 passed, 0 failures
```

---

## PR Checklist

```
[x] PR title includes Task ID — [T-004] feat(webhook): ...
[x] PR description filled out on GitHub
[x] Base branch set to develop (not main)
[x] Reviewer assigned — Aditya
[x] Type hints on all new/modified functions
[x] Google-style docstrings on all public functions
[x] .env.example updated — Gemini model upgraded to 2.5-flash
[x] No hardcoded provider names in routes (only base classes used)
[x] No hardcoded API keys (all via os.getenv / Settings)
[x] black backend/ → 24 files reformatted, 0 errors
[x] isort backend/ → 10 files fixed, 0 errors
[x] pytest tests/ -v → 7 passed, 0 failures
[x] Squash merged to develop
[x] Feature branch deleted after merge
```

---

## Notes / Blockers

```
Known Issues  →  pytest shows 239 deprecation warnings from pytest-asyncio and
                 langgraph internals (asyncio.iscoroutinefunction, get_event_loop_policy).
                 These are library-level warnings, not issues in our code.
                 Will resolve when those libraries update for Python 3.16 compatibility.
                 Safe to ignore for POC.

                 make run does not work on Windows without GNU Make installed.
                 Workaround: uvicorn backend.main:app --reload --port 8000
                 Fix: winget install GnuWin32.Make

Model Note    →  gemini-1.5-flash deprecated as of early 2026.
                 Upgraded to gemini-2.5-flash (stable GA) in this branch.

Blockers      →  None — T-004 complete

Links         →  FastAPI docs:        https://fastapi.tiangolo.com
                 Gemini models:       https://ai.google.dev/gemini-api/docs/models
                 WhatsApp webhooks:   https://developers.facebook.com/docs/whatsapp/webhooks
```
