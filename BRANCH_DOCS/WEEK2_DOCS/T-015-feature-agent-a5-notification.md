# BRANCH: feature/agent-a5-notification

---

## Branch Metadata

```
Branch Name   →  feature/agent-a5-notification
Task ID       →  T-015
Workstream    →  Notification / Last Mile
Author        →  Devam
Reviewer      →  Anoushka
Start Date    →  Day 9, Week 2
Target Merge  →  Day 10, Week 2
Actual Merge  →  Day 10, Week 2
Status        →  Merged
```

---

## Objective

**What does this branch do?**
Implements A5NotificationAgent — the last mile of the claim pipeline.
After A4 makes the routing decision, A5 delivers the result to the passenger
in real time via Server-Sent Events (SSE). Lane 1 claims get an instant
voucher (VCH-XXXXXXXX) and DB status APPROVED. Lane 2 claims get queued
for staff review with DB status AWAITING_REVIEW and an amber 'Under Review'
card in the simulator.

Also adds GET /events/{session_id} SSE endpoint to webhook.py so the React
simulator can receive real-time push notifications from the backend.

**Why is it needed?**
Without T-015, the pipeline completed silently — A4 made a decision but
the result was never pushed to the simulator in real time. T-015 closes
the loop: passenger sends a message → 5-agent pipeline runs → simulator
receives a live push event with the claim result. T-016 (Week 2 integration)
cannot be completed without T-015 since it verifies the full end-to-end flow.

---

## Local Setup

```bash
# Activate venv (every new terminal)
source venv/Scripts/activate      # Git Bash on Windows
source venv/bin/activate          # Mac / Linux

# Install dependencies
pip install -r requirements.txt

# Start backend server
uvicorn backend.main:app --reload --port 8000

# Start frontend simulator (separate terminal)
cd frontend
npm install
npm run dev
# Open http://localhost:5173
```

---

## Technical Approach

**Files Modified:**
```
backend/agents/a5_notification.py   →  Replaced TODO stubs with full implementation:
                                        - get_or_create_queue()   SSE queue manager
                                        - get_all_queues()        queue registry getter
                                        - _push_sse_event()       push to session queue
                                        - _handle_lane1()         voucher + APPROVED + SSE
                                        - _handle_lane2()         AWAITING_REVIEW + SSE
                                        - handle()                main dispatch method
                                        - Type hints + Google-style docstrings

backend/api/routes/webhook.py       →  Added GET /events/{session_id} SSE endpoint:
                                        - StreamingResponse with text/event-stream
                                        - asyncio.Queue per session
                                        - 30s timeout heartbeat keep-alive
                                        - CancelledError handler on client disconnect
                                        - Imports cleaned up and sorted (isort)

backend/graph/orchestrator.py       →  A5 node updated:
                                        - provide_db() now injected into A5NotificationAgent
                                        - A5 can update claim status in Supabase after routing
                                        - Added docstring to a5_node explaining Lane 1/2 flow
```

**Files Created:**
```
tests/test_a5_notification.py       →  13 unit tests covering:
                                        - Lane 1: voucher generation, notification_sent,
                                          DB status APPROVED, SSE event type + payload
                                        - Lane 2: hitl_queued, DB status AWAITING_REVIEW,
                                          SSE event type, no voucher generated
                                        - Error handling: DB failure graceful, no DB injected,
                                          unknown routing_lane no crash
```

**Files Already Complete (No Changes Needed):**
```
frontend/src/components/ClaimResultCard.jsx  →  Already renders Lane 1 + Lane 2 cards
frontend/src/hooks/useClaimFlow.js           →  Already handles routing_lane in _handleResult
backend/prompts/a5_notification.json         →  lane1_message + lane2_message templates done
backend/db/supabase_client.py                →  update_claim_status() wired in T-014
```

**Provider / Abstraction Used:**
```
Implements:  BaseAgent ABC (backend/agents/base_agent.py)
DB via:      DBProvider ABC (backend/db/base.py)
Injected by: provide_db() in orchestrator.py a5_node
A5 imports:  DBProvider only — never SupabaseDBProvider directly
SSE:         asyncio.Queue per session — global _sse_queues dict
```

---

## What A5 Does — Step by Step

```
ClaimState arrives from A4 (routing_lane = 1 or 2, claim_id set)
        ↓
handle() dispatches by routing_lane
        ↓
┌── Lane 1 (auto-approve) ─────────────────────────────────────────┐
│  Step 1: Generate voucher_code = VCH-{uuid4().hex[:8].upper()}   │
│  Step 2: state.notification_sent = True                          │
│  Step 3: await self._db.update_claim_status(claim_id, "APPROVED")│
│  Step 4: Load lane1_message from a5_notification.json            │
│  Step 5: Push SSE event to session queue:                        │
│          {"type": "lane1_result",                                │
│           "voucher_code": "VCH-XXXXXXXX",                        │
│           "compensation": 60.0,                                  │
│           "claim_id": "CLM-YYYYMMDD-XXXX",                       │
│           "message": "Your claim is approved! Voucher: VCH-..."}  │
│  React simulator receives event → renders green voucher card     │
└──────────────────────────────────────────────────────────────────┘

┌── Lane 2 (staff review) ─────────────────────────────────────────┐
│  Step 1: state.hitl_queued = True                                │
│  Step 2: await self._db.update_claim_status(                     │
│              claim_id, "AWAITING_REVIEW")                        │
│  Step 3: Load lane2_message from a5_notification.json            │
│  Step 4: Push SSE event to session queue:                        │
│          {"type": "lane2_result",                                │
│           "claim_id": "CLM-YYYYMMDD-XXXX",                       │
│           "message": "Submitted for review. Staff will..."}       │
│  React simulator receives event → renders amber 'Under Review'   │
└──────────────────────────────────────────────────────────────────┘
```

---

## SSE Architecture

```
React Simulator                FastAPI Backend
───────────────                ───────────────
GET /events/session-id ──────► SSE endpoint subscribes to session queue
        │                               │
        │ (connection open)             │ data: {"type": "connected"}
        │◄──────────────────────────────│
        │                               │
        │                               │ (30s heartbeat if no events)
        │◄──────────────────────────────│ data: {"type": "heartbeat"}
        │                               │
POST /webhook ──────────────────────────► Pipeline runs
                                        │ A4 decides lane
                                        │ A5 runs → puts event in queue
                                        │
        │◄──────────────────────────────│ data: {"type": "lane1_result",
        │                               │        "voucher_code": "VCH-..."}
        │
  Renders green voucher card
```

---

## Key Design Decisions

```
1. ASYNCIO.QUEUE PER SESSION — NOT WEBSOCKET
   SSE (Server-Sent Events) chosen over WebSocket for POC simplicity.
   One asyncio.Queue per session_id, stored in module-level _sse_queues dict.
   A5 puts events in the queue. SSE endpoint reads from it.
   No external message broker needed — zero infra cost for POC.
   Production: replace with Meta Cloud API POST to passenger's WhatsApp number.

2. DB FAILURE IS GRACEFUL — NEVER CRASHES A5
   Both _handle_lane1 and _handle_lane2 wrap the DB update_claim_status()
   call in try/except. If Supabase is unreachable, a warning is logged
   and A5 continues — SSE event still pushed, voucher still generated.
   A passenger is never stuck because of a DB timeout.

3. DB IS OPTIONAL (db=None SUPPORTED)
   A5NotificationAgent(db=None) works without DB injection.
   Backward compatible with any existing tests that don't inject DB.
   If db is None, DB update step is silently skipped.

4. HEARTBEAT EVERY 30 SECONDS
   asyncio.wait_for(queue.get(), timeout=30.0) sends a heartbeat ping
   if no real events arrive. This prevents proxy/load balancer timeouts
   from closing the SSE connection prematurely.

5. PROMPT TEMPLATE WITH FALLBACK
   A5 loads lane1_message/lane2_message from a5_notification.json via
   PromptLoader. If loading fails for any reason, a hardcoded fallback
   message is used — A5 never crashes due to a missing prompt file.

6. conversation_step ALWAYS SET TO 'result'
   Both lanes set state.conversation_step = "result" so A1 picks up
   the correct result prompt on any subsequent message turn.
```

**POC → Production swap path:**
```
POC:        SSE push → simulator reads event → renders card
Production: Remove SSE. Replace _push_sse_event() with:
            await meta_cloud_api.send_message(
                to=passenger_phone,
                template="claim_result",
                params=[voucher_code, compensation]
            )
Zero other code changes needed — only A5 internals.
```

---

## Dependencies

```
Depends On          →  T-014 (Supabase DB — update_claim_status() must exist)
                       T-012 (A4 Decision — routing_lane must be set)
External Libraries  →  None new — asyncio, json, uuid all stdlib
Environment Vars    →  No new env vars — uses existing DB + provider config
```

---

## Testing

**Automated Tests (No Real API / DB Calls):**
```bash
pytest tests/test_a5_notification.py -v

# Expected:
# test_lane1_generates_voucher                   PASSED
# test_lane1_sets_notification_sent              PASSED
# test_lane1_updates_db_status_approved          PASSED
# test_lane1_pushes_sse_event                    PASSED
# test_lane1_sets_result_step                    PASSED
# test_lane2_sets_hitl_queued                    PASSED
# test_lane2_updates_db_status_awaiting_review   PASSED
# test_lane2_pushes_sse_event                    PASSED
# test_lane2_no_voucher_generated                PASSED
# test_lane2_sets_result_step                    PASSED
# test_a5_db_failure_does_not_crash              PASSED
# test_a5_no_db_injected_still_works             PASSED
# test_a5_unknown_lane_does_not_crash            PASSED
# 13 passed

# Full suite:
pytest tests/ -v
# Expected: 108 passed
```

**Manual Smoke Tests:**
```bash
# Start server
uvicorn backend.main:app --reload --port 8000

# Test 1 — Webhook still responds correctly
curl -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -d "{\"session_id\": \"smoke-a5\", \"message\": \"my bag handle is broken\"}"
# Expected: HTTP 200, reply set, error=null

# Test 2 — SSE endpoint is live
curl -N http://localhost:8000/events/smoke-a5
# Expected: data: {"type": "connected", "session_id": "smoke-a5"}

# Test 3 — Two terminals: subscribe first, then trigger full pipeline
# Terminal 1:
curl -N http://localhost:8000/events/smoke-sse-test
# Terminal 2:
curl -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -d "{\"session_id\": \"smoke-sse-test\", \"message\": \"bag is damaged\"}"
# Terminal 1 should receive heartbeats (text-only = no A5)
# Full SSE lane events require image_paths with both damage + tag photos

# Test 4 — API docs show new endpoint
# Open: http://localhost:8000/docs
# Expected: GET /events/{session_id} visible under Webhook section
```

**Smoke Test Note:**
```
SSE lane1_result / lane2_result events only fire when:
  - image_paths contains at least 1 damage photo AND 1 tag photo
  - A2 vision confidence >= 0.4
  - A3 OCR confidence >= 0.7
  - A4 makes routing decision → A5 runs → event pushed

Text-only webhook calls take the text branch (router → a1_text → END)
and skip A2, A3, A4, A5 entirely. This is correct by design.
Full end-to-end SSE events verified in T-016 integration tests.
```

**Acceptance Criteria:**
```
✅ Lane 1: VCH-XXXXXXXX voucher generated (uuid4 hex, 8 chars)
✅ Lane 1: DB update_claim_status("APPROVED") called
✅ Lane 1: SSE event type="lane1_result" pushed to session queue
✅ Lane 1: notification_sent=True, conversation_step="result"
✅ Lane 2: DB update_claim_status("AWAITING_REVIEW") called
✅ Lane 2: SSE event type="lane2_result" pushed to session queue
✅ Lane 2: hitl_queued=True, voucher_code=None, conversation_step="result"
✅ DB failure handled gracefully — A5 continues without crashing
✅ db=None supported — backward compatible
✅ Unknown routing_lane handled gracefully — no crash
✅ GET /events/{session_id} endpoint live with heartbeat keep-alive
✅ No hardcoded provider names in agents/
✅ Type hints + Google-style docstrings on all functions
✅ black + isort run clean
✅ 13 unit tests pass, 0 failures
✅ pytest tests/ → 108 passed total
```

---

## PR Checklist

```
[x] PR title includes Task ID — [T-015] feat(notification): ...
[x] PR description filled out on GitHub
[x] Base branch set to develop (not main)
[x] Reviewer assigned — Anoushka
[x] Type hints on all new/modified functions
[x] Google-style docstrings on all public functions
[x] No hardcoded provider or DB names in agents/
[x] No hardcoded API keys — all via Settings / .env
[x] No new dependencies added to requirements.txt
[x] black backend/ → clean
[x] isort backend/ → clean
[x] pytest tests/ → 108 passed, 0 failures
[x] Squash merged to develop
[x] Feature branch deleted after merge
```

---

## Notes / Blockers

```
Known Issues  →  SSE lane events only visible in smoke test when full image
                 set (damage + tag) is sent. Text-only messages correctly
                 skip A5. Full SSE event flow verified in T-016 integration
                 tests using mocked providers.

                 pytest shows deprecation warnings from pytest-asyncio and
                 langgraph internals. Library-level, not our code. Safe to
                 ignore for POC.

Blockers      →  None — T-015 complete and merged

Next Task     →  T-016 (Week 2 Integration) — depends on T-015 ✅

Links         →  SSE spec:            https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events
                 FastAPI StreamingResponse: https://fastapi.tiangolo.com/advanced/custom-response
                 A5 prompt templates: backend/prompts/a5_notification.json
                 ClaimResultCard:     frontend/src/components/ClaimResultCard.jsx
                 Production swap:     implement Meta Cloud API send_message()
                                      in backend/agents/a5_notification.py
```
