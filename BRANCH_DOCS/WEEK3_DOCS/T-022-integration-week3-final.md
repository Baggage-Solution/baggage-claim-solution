# BRANCH: integration/week3-final

---

## Branch Metadata

```
Branch Name   →  integration/week3-final
Task ID       →  T-022
Workstream    →  Integration
Author        →  Aditya (all team)
Reviewer      →  All (Anoushka + Devam)
Start Date    →  Day 14, Week 3
Target Merge  →  Day 15, Week 3
Actual Merge  →  Day 15, Week 3
Status        →  Merged
```

---

## Objective

**What does this branch do?**

Performs the final merge of all Week 3 branches (T-017 through T-021),
adds the full Week 3 smoke test suite (`tests/test_smoke_t017_t022.py`),
runs a complete end-to-end demo rehearsal covering all 3 demo scenarios,
fixes any blocking bugs found during rehearsal, and prepares the
demo environment so the mentor presentation runs without surprises.
The sprint ends with `git tag v1.0-poc` merged to `main`.

**Why is it needed?**

T-022 is the final integration gate for the 3-week POC sprint.
Every previous integration task (T-009 Week 1, T-016 Week 2) validated
one layer of the pipeline. T-022 validates everything together:
QR → Simulator → Full 5-agent pipeline → Dashboard → Supabase —
on a fresh machine, from the README, with all 3 demo scenarios rehearsed.
Nothing reaches `main` without passing this gate.

---

## Local Setup (Starting Point)

```bash
# 1. Ensure all Week 3 branches are merged to develop
git checkout develop
git pull origin develop

# 2. Verify branch status — T-017 through T-021 must all be Done
#    (check Excel tracker: B-7/B-8 rows all green)

# 3. Create T-022 integration branch
git checkout -b integration/week3-final

# 4. Run existing test suite — must be green before starting
pytest tests/ -v --tb=short
```

---

## Technical Approach

### Files Created

```
tests/test_smoke_t017_t022.py     →  Week 3 smoke test suite covering:
                                      - T-017: Dashboard CRUD (6 tests)
                                      - T-018: QR generation URL structure (4 tests)
                                      - T-019: Code quality — no provider leak,
                                               ABCs present, .env.example complete,
                                               docstrings, 300-line limit (6 tests)
                                      - T-020: Test file existence + importability (4 tests)
                                      - T-021: README + demo_script.md content (5 tests)
                                      - T-022: All 3 demo scenarios, voucher path,
                                               session isolation, claim_id format,
                                               v1.0-poc readiness check (10 tests)
                                      Total: 35 smoke assertions

BRANCH_DOCS/WEEK3_DOCS/T-022-integration-week3-final.md
                                  →  This document
```

### Files Modified

```
None — T-022 is additive only.
All bug fixes identified during rehearsal are committed directly on this branch.
Source code bugs (if found) → fix inline on integration/week3-final with
clear fix(scope): commit messages.
```

### Bug Fixes Applied During Rehearsal

> Fill this section during actual demo rehearsal.
> Template for each fix:

```
BUG: <symptom observed during rehearsal>
FIX: <file changed + what was changed>
COMMIT: fix(<scope>): <description>
VERIFIED: <how confirmed fixed>
```

### Provider / Abstraction Used

- No new providers introduced in T-022.
- All 5 existing providers (LLM, Vision, OCR, Storage, DB) exercised
  via the existing abstraction layer.
- Tests mock providers via `unittest.mock.patch` on
  `backend.dependencies.provide_*` — no real API calls in test suite.

### Key Design Decisions

1. **Smoke tests mirror T-001–T-016 pattern**: `test_smoke_t017_t022.py`
   follows the exact structure of `test_smoke_t001_t016.py` — one test
   class per task, one assertion per acceptance criterion from the tracker.
   Any reviewer can map a failing test back to a specific task and criterion.

2. **Full pipeline scenarios tested directly (not only via HTTP)**: The
   three demo scenarios (Lane 1, Lane 2 luxury, blurry tag retry) are
   tested by instantiating agents directly with `MagicMock` DBs — fast,
   readable, and independent of network availability. HTTP smoke tests sit
   on top for confidence.

3. **v1.0-poc readiness assertion**: `test_t022_v1_poc_tag_ready` checks
   that all required files exist before the `git tag v1.0-poc` command
   is run. Fails fast if a file was accidentally deleted or missed in a merge.

4. **Session isolation test**: Three independent `ClaimState` objects are
   created to confirm state fields don't bleed between sessions — guards
   against any accidental global mutation introduced in cleanup work.

5. **Second-machine env check**: `test_t022_second_machine_env_check_structure`
   verifies that `Settings` loads gracefully with only `GEMINI_API_KEY` set
   and no Supabase credentials — confirming the app starts on a fresh machine
   before Supabase is configured.

### Future Swap Path

Not applicable — T-022 is the final integration task. No future swaps
needed within the POC. Phase 2 starts from `main` at tag `v1.0-poc`.

---

## Dependencies

```
Depends On    →  T-017 (Agent Dashboard) — Scenario B uses dashboard approve
                 T-018 (QR Entry) — demo opens via QR scan
                 T-019 (Cleanup) — codebase must be clean before tag
                 T-020 (Test Suite) — test suite must pass before tag
                 T-021 (README + Demo Script) — README verified on second machine

External      →  No new libraries added in T-022.
                 All existing deps: see requirements.txt

Environment   →  GEMINI_API_KEY        (required — Gemini Flash LLM + Vision + OCR)
                 SUPABASE_URL          (required for Supabase persistence)
                 SUPABASE_SERVICE_ROLE_KEY (required for Supabase persistence)
                 All other vars have safe defaults — see .env.example
```

---

## Testing

### How to Run the Week 3 Smoke Suite (Manual)

```bash
# From project root — no .env needed (all providers mocked)
pytest tests/test_smoke_t017_t022.py -v

# Expected output:
# tests/test_smoke_t017_t022.py::TestT017Dashboard::test_t017_get_pending_claims_returns_list PASSED
# tests/test_smoke_t017_t022.py::TestT017Dashboard::test_t017_pending_claims_contain_required_fields PASSED
# ...
# 35 passed in Xs
```

### Full Suite (All Tasks T-001 to T-022)

```bash
pytest tests/ -v --tb=short

# Targets:
# ✅ 0 failures
# ✅ 0 errors
# Coverage target: > 70% (from T-020)
```

### Demo Rehearsal Checklist (Pre-Merge)

Run on the primary machine first, then repeat on a **second machine**
starting from a fresh `git clone`:

```
[ ] git clone <repo-url> && cd baggage-claim-solution
[ ] python -m venv venv && source venv/Scripts/activate (or bin/activate)
[ ] pip install -r requirements.txt  (no errors)
[ ] cp .env.example .env  →  fill GEMINI_API_KEY + SUPABASE_*
[ ] uvicorn backend.main:app --reload --port 8000
    →  GET /health → {"status":"ok","configured":{"gemini":true,"supabase":true}}
[ ] cd frontend && npm install && npm run dev
    →  http://localhost:5173 loads WhatsApp simulator ✓

[ ] Scenario A — Lane 1 (standard bag, auto-approve):
    Image: tests/fixtures/damaged/damaged_01.jpg
    Tag:   tests/fixtures/bag_tags/clear_tag_01.jpg
    Expected:  compensation < $100, Lane 1, voucher VCH-XXXXXXXX appears < 2 min ✓
    Supabase:  row status = APPROVED ✓

[ ] Scenario B — Lane 2 (luxury bag, staff review):
    Image: tests/fixtures/damaged/luxury_01.jpg
    Tag:   tests/fixtures/bag_tags/clear_tag_01.jpg
    Expected:  is_luxury = True, Lane 2, "Under Review" card appears ✓
    Dashboard: http://localhost:5173/dashboard → claim visible ✓
    Approve:   click Approve → simulator card flips to green ✓
    Supabase:  row status = RESOLVED ✓

[ ] Scenario C — Blurry tag retry:
    Image: tests/fixtures/damaged/damaged_02.jpg
    Tag:   any blurry/unclear image
    Expected:  re_request_tag = True, retry prompt appears ✓
    Recovery:  upload clear_tag_01.jpg → pipeline completes ✓

[ ] QR scan demo:
    GET http://localhost:8000/qr/generate?airport=T3&terminal=B
    →  PNG downloaded ✓
    Scan on mobile → http://localhost:5173/simulator?airport=T3&terminal=B&auto=1 ✓

[ ] pytest tests/ → 0 failures ✓
[ ] All 3 scenarios completed in < 15 min total ✓
```

### Acceptance Criteria (from Task Tracker)

```
✅ All Week 3 PRs merged to develop (T-017 through T-021)
✅ Full demo rehearsal: QR scan → Lane 1 → Lane 2 → dashboard approve — all pass
✅ Run on a second machine (fresh env from README in < 15 min)
✅ Lane 1 claim completes with voucher in < 2 minutes
✅ Lane 2 claim routes to dashboard; staff approve resolves claim
✅ Blurry tag retry prompt triggered; re-upload recovers pipeline
✅ pytest tests/ → 0 failures
✅ git checkout main → git merge develop --no-ff → git tag v1.0-poc → git push
```

---

## PR Checklist

```
[x] Branch: integration/week3-final (off develop)
[x] PR title: [T-022] integration(week3): final integration, demo prep, v1.0-poc
[x] PR description filled (what changed, how to test, all 3 scenarios documented)
[x] Base branch set to develop (NOT main — main receives the --no-ff merge after this)
[x] All Week 3 branches confirmed merged to develop before opening this PR
[x] tests/test_smoke_t017_t022.py created (35 tests, 0 failures)
[x] pytest tests/ → 0 failures (full suite)
[x] Demo rehearsal passed on primary machine (all 3 scenarios)
[x] Demo rehearsal passed on second machine (fresh env from README)
[x] Reviewer assigned — Anoushka + Devam (both must approve for final gate)
[x] Squash merged to develop
[x] Feature branch deleted after merge

POST-MERGE (after develop is green):
[x] git checkout main
[x] git merge develop --no-ff -m "chore: POC v1.0 — 3-week sprint complete"
[x] git tag v1.0-poc
[x] git push origin main --tags
[x] Notify team: "v1.0-poc tagged ✓ Sprint complete ✓"
```

---

## Demo Preparation

### Pre-loaded Test Data

```
tests/fixtures/damaged/
    damaged_01.jpg       →  Scenario A — standard cracked shell
    damaged_02.jpg       →  Scenario C — blurry/unclear (triggers retry)
    damaged_04.jpg       →  Spare standard bag
    damaged_05.jpg       →  Spare standard bag
    luxury_01.jpg        →  Scenario B — luxury bag (Rimowa-style)

tests/fixtures/bag_tags/
    clear_tag_01.jpg     →  Scenarios A + B — high OCR confidence
    clear_tag_02.jpg     →  Spare tag
    clear_tag_04.jpg     →  Spare tag
    clear_tag_05.jpg     →  Spare tag
```

### Browser Tab Setup

```
Tab 1:  http://localhost:5173            →  WhatsApp Simulator
Tab 2:  http://localhost:5173/dashboard  →  Agent Dashboard (Lane 2 review)
Tab 3:  http://localhost:8000/docs       →  FastAPI Swagger (for technical Q&A)
Tab 4:  Supabase Dashboard              →  Live DB view (optional)
```

### Timing Guide

```
Opening narrative        →  2 min
Scenario A (Lane 1)      →  4 min
Scenario B (Lane 2)      →  4 min  (includes dashboard approve)
Scenario C (retry)       →  3 min
Technical Q&A            →  5 min
──────────────────────────────────
Total                    →  18 min
```

---

## Notes / Blockers

```
Known Issues  →  None at merge time. Any bugs found during rehearsal are
                 documented in the "Bug Fixes Applied" section above.

Co-authorship →  T-022 is listed as "All" in the tracker.
                 Integration branch opened and run by Aditya.
                 Demo rehearsal run jointly by all three.
                 v1.0-poc tag applied after mentor demo sign-off.

Blockers      →  None — T-022 complete and merged.

Next Steps    →  Phase 2 planning:
                 1. Replace React simulator with Meta WhatsApp Cloud API
                 2. Add yolov8_vision.py (local, offline vision)
                 3. Add paddleocr_ocr.py (local, no PII egress)
                 4. Wire LangGraph interrupt() for true HITL in A5
                 5. Add XGBoost severity/fraud model
                 6. Add HTTP Basic auth to /dashboard

Links         →  Task Tracker:     POC_Tracker_latest_updated.xlsx
                 Project Overview: Project_Overview.docx
                 GIT_WORKFLOW.md:  repo root
                 CONTRIBUTING.md:  repo root
                 TEMPLATE.md:      BRANCH_DOCS/TEMPLATE.md
                 FastAPI Swagger:  http://localhost:8000/docs
                 Supabase:         https://supabase.com/dashboard
```