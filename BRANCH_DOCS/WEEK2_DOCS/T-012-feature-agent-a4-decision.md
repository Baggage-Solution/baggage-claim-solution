# BRANCH: feature/agent-a4-decision

---

## Branch Metadata

```
Branch Name   →  feature/agent-a4-decision
Task ID       →  T-012
Workstream    →  Decision Engine
Author        →  Devam
Reviewer      →  Aditya
Start Date    →  Day 7, Week 2
Target Merge  →  Day 9, Week 2
Actual Merge  →  Day 9, Week 2
Status        →  Merged
```

---

## Objective

**What does this branch do?**
Implements A4DecisionAgent — the decision engine of the baggage claim AI system.
Given a fully populated ClaimState (damage assessed by A2, bag tag read by A3),
A4 runs two fraud checks, calculates final compensation, routes the claim to
Lane 1 (auto-approve) or Lane 2 (staff review), generates a unique claim ID,
and persists the claim to the database.

**Why is it needed?**
A4 is the most critical decision point in the entire pipeline. Every claim must
pass through A4 before a passenger receives a voucher or is told their claim
is under review. T-015 (A5 Notification) and T-014 (Supabase DB) both depend
on A4 being complete and correct. All 5 routing scenarios from the architecture
doc must be verified before the Week 2 integration (T-016) can proceed.

---

## Local Setup

```bash
# Activate venv (every new terminal)
source venv/Scripts/activate      # Git Bash on Windows
source venv/bin/activate          # Mac / Linux

# Install dependencies (imagehash added in this branch)
pip install -r requirements.txt

# Start server
uvicorn backend.main:app --reload --port 8000
```

---

## Technical Approach

**Files Modified:**
```
backend/agents/a4_decision.py   →  Replaced TODO stubs with full implementation:
                                    - _run_phash_check()     pHash duplicate detection
                                    - _run_frequency_check() claim frequency fraud check
                                    - _state_to_claim_dict() ClaimState → DB dict
                                    - handle()               full decision flow
                                    - Luxury 1.5x compensation multiplier
                                    - await self._db.save_claim() after routing
                                    - Type hints + Google-style docstrings throughout

requirements.txt                →  Added imagehash==4.3.1
```

**Files Created:**
```
tests/test_a4_decision.py       →  11 unit tests covering all 5 routing scenarios,
                                    claim ID format, DB persistence, error handling,
                                    and luxury compensation multiplier
```

**Files Already Complete (No Changes Needed):**
```
backend/graph/state.py          →  is_lane1_eligible() routing thresholds wired
backend/config.py               →  all fraud thresholds configurable via .env
backend/db/base.py              →  DBProvider ABC complete
backend/db/supabase_client.py   →  get_claim_count() + get_recent_hashes() stubs
                                    (real queries wired in T-014 by Aditya)
```

**Provider / Abstraction Used:**
```
Implements:  BaseAgent ABC (backend/agents/base_agent.py)
DB via:      DBProvider ABC (backend/db/base.py)
Injected by: provide_db() in dependencies.py
A4 imports:  DBProvider only — never SupabaseDBProvider directly
```

---

## What A4 Does — Step by Step

```
ClaimState arrives from A3 (pnr, image_paths, severity_score, is_luxury set)
        ↓
Step 1 — Generate claim_id
         CLM-20260522-A2E2 (CLM + YYYYMMDD + 4-char hex)
        ↓
Step 2 — Fraud Check 1: pHash duplicate detection
         For each damage photo:
           compute pHash (perceptual hash via imagehash library)
           compare against stored hashes for this PNR in DB
           hamming distance < 10 → visually similar → phash_duplicate flag
           fraud_score += 0.4
        ↓
Step 3 — Fraud Check 2: Claim frequency check
         Query DB: how many claims for this PNR in last 30 days?
         count >= 3 → high_frequency flag
         fraud_score += 0.3
        ↓
Step 4 — Calculate final compensation
         is_luxury = True  → compensation × 1.5
         is_luxury = False → compensation unchanged
        ↓
Step 5 — Routing decision via is_lane1_eligible()
         ALL must be true for Lane 1:
           compensation_estimate_usd <= $100
           is_luxury = False
           fraud_score < 0.5
         ANY fails → Lane 2
        ↓
Step 6 — Persist to DB
         await self._db.save_claim(claim_dict)
        ↓
State returned to orchestrator → A5 reads routing_lane
```

---

## The 5 Routing Scenarios

```
Scenario 1 — Standard bag, $60 estimate, fraud 0.0
             60 <= 100 ✅  not luxury ✅  fraud 0.0 < 0.5 ✅
             → LANE 1: auto-approve, voucher issued instantly

Scenario 2 — Standard bag, $150 estimate, fraud 0.0
             150 > 100 ❌
             → LANE 2: staff review (exceeds threshold)

Scenario 3 — Rimowa bag, $40 estimate, fraud 0.0
             is_luxury = True ❌
             → LANE 2: luxury always staff review

Scenario 4 — Standard bag, fraud_score = 0.5 (phash duplicate)
             fraud 0.5 >= 0.5 ❌
             → LANE 2: suspected duplicate fraud

Scenario 5 — Standard bag, fraud_score = 0.6 (high frequency + existing)
             fraud 0.6 >= 0.5 ❌
             → LANE 2: suspected frequent claimer fraud
```

---

## Key Design Decisions

```
1. FRAUD CHECKS ARE GRACEFUL — NEVER CRASH A4
   Both _run_phash_check() and _run_frequency_check() wrap all logic in
   try/except. If imagehash is not installed, DB is unreachable, or image
   file is missing — the check is skipped with a warning log and A4
   continues normally. A claim is never blocked due to a fraud check failure.

2. IMAGEHASH ENABLED FLAG
   IMAGEHASH_ENABLED=true in .env controls whether pHash runs.
   Set to false in test environments or if imagehash is not installed.
   Zero code changes needed — just flip the env var.

3. ALL THRESHOLDS CONFIGURABLE VIA .ENV
   LANE1_MAX_COMPENSATION_USD=100.0
   FRAUD_PHASH_THRESHOLD=10
   MAX_CLAIMS_PER_PASSENGER=3
   CLAIM_FREQUENCY_WINDOW_DAYS=30
   None of these are hardcoded. Airline can tune them without touching code.

4. LUXURY COMPENSATION MULTIPLIER
   Luxury bags get 1.5x multiplier on final_compensation_usd.
   This means a $80 estimate on a Rimowa → $120 final.
   Even if somehow routed to Lane 1 (shouldn't happen), compensation
   is still calculated correctly.

5. DB ABSTRACTION
   A4 calls self._db.save_claim() — never imports SupabaseDBProvider.
   T-014 (Aditya) wires the real Supabase queries inside supabase_client.py.
   Swapping to PostgresDBProvider in Phase 2 requires zero A4 changes.

6. LUXURY SMOKE TEST NOTE
   End-to-end luxury routing shows Lane 1 until T-010 (A2 Vision) merges.
   A2 is responsible for setting is_luxury=True in ClaimState.
   Without A2, is_luxury stays False and A4 sees a standard bag.
   Unit test Scenario 3 proves A4's luxury routing logic is correct.
   Will work end-to-end automatically after T-010 merges.
```

**Future Swap Path:**
```
Fraud checks Phase 2 upgrades:
  - Add EXIF metadata check (T-023 buffer task)
  - Add ML-based fraud scoring model
  - Add velocity checks (claims per IP, claims per device)
All are additive — zero changes to existing fraud check methods needed.

DB swap: implement PostgresDBProvider → set DB_PROVIDER=postgres in .env
Zero A4 changes needed.
```

---

## Dependencies

```
Depends On          →  T-010 (A2 Vision — sets is_luxury, compensation_estimate)
                       T-011 (A3 OCR — sets pnr for fraud checks)
                       T-005 (LangGraph skeleton — orchestrator must exist)
External Libraries  →  imagehash==4.3.1 (added to requirements.txt)
                       Pillow (already in requirements.txt from T-006)
Environment Vars    →  LANE1_MAX_COMPENSATION_USD=100.0
                       FRAUD_PHASH_THRESHOLD=10
                       MAX_CLAIMS_PER_PASSENGER=3
                       CLAIM_FREQUENCY_WINDOW_DAYS=30
                       IMAGEHASH_ENABLED=true
```

---

## Testing

**Automated Tests (No Real API / DB Calls):**
```bash
pytest tests/test_a4_decision.py -v

# Expected:
# test_generate_claim_id_format                    PASSED
# test_generate_claim_id_unique                    PASSED
# test_scenario1_standard_bag_low_value_lane1      PASSED
# test_scenario2_high_value_lane2                  PASSED
# test_scenario3_luxury_bag_always_lane2           PASSED
# test_scenario4_phash_duplicate_lane2             PASSED
# test_scenario5_high_frequency_lane2              PASSED
# test_a4_saves_claim_to_db                        PASSED
# test_a4_sets_error_on_db_failure                 PASSED
# test_a4_luxury_compensation_multiplier           PASSED
# test_a4_standard_compensation_no_multiplier      PASSED
# 11 passed

# Full suite:
pytest tests/ -v
# Expected: 60 passed
```

**Manual Smoke Tests (Server Running):**
```bash
# Start server
uvicorn backend.main:app --reload --port 8000

# Test 1 — Standard bag → Lane 1
curl -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -d "{\"session_id\": \"smoke-lane1\", \"message\": \"my bag handle broke\"}"
# Expected: routing_lane=1, claim_id=CLM-YYYYMMDD-XXXX, voucher_code set, error=null

# Test 2 — Two sessions get different claim IDs
curl -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -d "{\"session_id\": \"smoke-s1\", \"message\": \"bag is broken\"}"
curl -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -d "{\"session_id\": \"smoke-s2\", \"message\": \"bag is broken\"}"
# Expected: different claim_ids, both error=null

# Test 3 — Empty message never crashes server
curl -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -d "{\"session_id\": \"smoke-empty\", \"message\": \"\"}"
# Expected: HTTP 200, claim_id set, error=null

# Test 4 — Health still green
curl http://localhost:8000/health
# Expected: {"status":"ok"}
```

**Smoke Test Notes:**
```
Luxury routing (Scenario 3) confirmed via unit tests only.
End-to-end smoke test shows Lane 1 for luxury message because
A2 Vision (T-010) not yet merged — is_luxury stays False.
Will route Lane 2 automatically after T-010 merges.
```

**Acceptance Criteria:**
```
✅ pHash duplicate check runs on all damage photos
✅ Frequency check queries DB for PNR claim count
✅ All 5 routing scenarios route correctly (unit tested)
✅ claim_id generated in CLM-YYYYMMDD-XXXX format
✅ Two claim IDs are always unique
✅ await self._db.save_claim() called after every decision
✅ Luxury bags get 1.5x compensation multiplier
✅ Fraud checks fail gracefully — never crash A4
✅ No hardcoded provider names or DB names in agents/
✅ All thresholds configurable via .env
✅ Type hints on all functions
✅ Google-style docstrings on all public functions
✅ black + isort run clean
✅ 11 unit tests pass, all 5 routing scenarios covered
✅ pytest tests/ → 60 passed, 0 failures
```

---

## PR Checklist

```
[x] PR title includes Task ID — [T-012] feat(decision): ...
[x] PR description filled out on GitHub
[x] Base branch set to develop (not main)
[x] Reviewer assigned — Aditya
[x] Type hints on all new/modified functions
[x] Google-style docstrings on all public functions
[x] No hardcoded provider or DB names in agents/
[x] No hardcoded API keys — all via Settings / .env
[x] imagehash added to requirements.txt
[x] black backend/ → clean
[x] isort backend/ → clean
[x] pytest tests/ → 60 passed, 0 failures
[x] Squash merged to develop
[x] Feature branch deleted after merge
```

---

## Notes / Blockers

```
Known Issues  →  Luxury end-to-end routing shows Lane 1 until T-010 merges.
                 A2 Vision sets is_luxury in ClaimState — without it, A4
                 sees is_luxury=False for all claims. Unit test Scenario 3
                 proves A4 logic is correct. Resolves automatically with T-010.

                 pytest shows 2587 deprecation warnings from pytest-asyncio
                 and langgraph internals. Library-level, not our code.
                 Safe to ignore for POC.

Blockers      →  None — T-012 complete and merged

Next Tasks    →  T-015 (A5 Notification) — depends on T-012 ✅ — Devam
                 T-014 (Supabase DB)     — depends on T-012 ✅ — Aditya
                 T-010 (A2 Vision node)  — independent      — Anoushka
                 T-011 (A3 OCR node)     — independent      — Anoushka

Links         →  imagehash library:   https://github.com/JohannesBuchner/imagehash
                 pHash explained:     https://www.hackerfactor.com/blog/index.php?/archives/432-Looks-Like-It.html
                 DBProvider ABC:      backend/db/base.py
                 Routing thresholds:  backend/config.py → Settings class
```
