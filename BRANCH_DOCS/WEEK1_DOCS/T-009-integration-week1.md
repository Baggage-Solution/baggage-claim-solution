# BRANCH: integration/week1-backend-llm

---

## Branch Metadata

```
Branch Name   →  integration/week1-backend-llm
Task ID       →  T-009
Workstream    →  Integration
Author        →  Devam Dixit
Reviewer      →  All
Start Date    →  Day 5, Week 1
Target Merge  →  Day 5, Week 1
Actual Merge  →  Day 5, Week 1
Status        →  Merged
```

---

## Objective

**What does this branch do?**
Validates the complete Week 1 pipeline end-to-end: POST /webhook → FastAPI →
LangGraph orchestrator → A1 conversation agent → Gemini LLM → structured reply.
Adds 7 integration tests that exercise the real FastAPI app (not individual units),
verifying that all T-004 + T-005 + T-008 pieces fit together correctly.

**Why is it needed?**
T-004 built the API. T-005 built the graph. T-008 built A1.
T-009 is the first time they run together as a system.
Without this integration pass, it's possible for all unit tests to pass
while the assembled pipeline silently fails.

---

## Technical Approach

**Files Created:**

| File | Purpose |
|---|---|
| `tests/test_integration_week1.py` | 7 integration tests using httpx.AsyncClient against the real FastAPI app. Covers health endpoint, single message round-trip, 3 consecutive messages, session isolation, LLM failure resilience, and schema validation. |

**Files Already Complete (No Changes):**
All wiring was already done across T-004, T-005, T-008:
```
backend/main.py               → FastAPI app + middleware + routes
backend/api/routes/webhook.py → POST /webhook → ClaimOrchestrator.run()
backend/graph/orchestrator.py → LangGraph graph + MemorySaver
backend/agents/a1_conversation.py → Full conversation state machine
backend/llm_provider/gemini_llm.py → Real Gemini API calls
```

**Key Design Decisions:**

```
1. REAL FASTAPI APP — NOT STARLETTE TESTCLIENT
   Uses httpx.AsyncClient(transport=ASGITransport(app=app)) — the modern
   async approach. Tests the actual middleware stack (CORS, RequestContext,
   logging) that the real server runs, not a stripped-down test version.

2. ALL PROVIDERS MOCKED
   LLM, vision, OCR, DB, storage all mocked with AsyncMock.
   Integration tests verify the wiring and flow, not the AI quality.
   Real Gemini tests are manual smoke tests (see below).

3. THREE ROUND TRIPS AS PRIMARY CRITERION
   test_webhook_three_round_trips_same_session() directly maps to the
   tracker acceptance criteria: "3 full round-trip messages work with
   <5s latency each". If this passes, T-009 is done.

4. NEVER 500 CONTRACT
   test_webhook_never_returns_500_on_llm_failure() verifies the system
   contract: no matter what fails internally, the webhook always returns
   200 with error field set. The simulator must never see a 500.
```

---

## Dependencies

```
Depends On         →  T-004 ✅  T-005 ✅  T-008 ✅
External Libraries →  httpx==0.27.2 (already in requirements.txt)
Environment Vars   →  None needed for automated tests (all mocked)
                      GEMINI_API_KEY needed for manual smoke tests only
```

---

## Testing

**Run automated integration tests:**
```bash
pytest tests/test_integration_week1.py -v
# Expected: 7 passed

pytest tests/ -v
# Expected: 35 passed total
```

**Manual smoke test — real Gemini API (needs GEMINI_API_KEY in .env):**
```bash
# Terminal 1 — start server
uvicorn backend.main:app --reload --port 8000

# Terminal 2 — send test messages
curl -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -d '{"session_id": "smoke-001", "message": "hi my bag is damaged"}'

# Expected: real A1 reply in JSON, not stub text

curl -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -d '{"session_id": "smoke-001", "message": "the wheel is cracked"}'

curl -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -d '{"session_id": "smoke-001", "message": "here are the photos"}'
```

**Acceptance Criteria:**
```
✅ GET /health → 200 OK
✅ POST /webhook → 200 with non-empty reply
✅ 3 consecutive messages → all 200, all with replies, no errors
✅ Two different session_ids → independent responses, no state bleed
✅ LLM failure → 200 with error field (never 500)
✅ Missing session_id → 422 Unprocessable Entity
✅ pytest tests/ → 35 passed, 0 failed
```

---

## PR Checklist

```
[x] PR title includes Task ID
[x] Base branch: develop
[x] Reviewer: All
[x] Squash merged to develop
[x] Branch deleted after merge
[x] No new env vars
[x] All tests passing
```

---

*Branch opened: Day 5, Week 1 — Devam Dixit*
*Merged to develop: Day 5, Week 1*
