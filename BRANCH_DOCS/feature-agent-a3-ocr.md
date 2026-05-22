# BRANCH: feature/agent-a3-ocr

---

## Branch Metadata

```
Branch Name   →  feature/agent-a3-ocr
Task ID       →  T-011
Workstream    →  Vision / AI
Author        →  Anoushka Vyas
Reviewer      →  Devam Dixit
Start Date    →  Day 7, Week 2
Target Merge  →  Day 7, Week 2
Actual Merge  →  Day 7, Week 2
Status        →  Merged
```

---

## Objective

**What does this branch do?**
Implements `A3OCRAgent.handle()` — the OCR extraction node of the LangGraph
pipeline. Replaces the T-011 TODO stub with a real provider call to
`GeminiOCRProvider.extract_bag_tag()`. Writes `flight_number`, `pnr`,
`bag_id`, and `ocr_confidence` to `ClaimState`. Sets `re_request_tag=True`
if the tag photo quality is too low for reliable extraction.

**Why is it needed?**
A4's fraud detection depends on `state.pnr` — the pHash duplicate check and
claim frequency check both query the DB using the PNR. Without real PNR data
from A3, A4 cannot run fraud checks and the fraud_score stays 0.0 for every
claim. T-011 is what connects the bag tag photo to the fraud detection layer.

---

## Local Setup

```bash
source venv/Scripts/activate      # Git Bash / Windows
# source venv/bin/activate        # Mac / Linux

pip install -r requirements.txt
pytest tests/test_a3_ocr_agent.py -v
```

---

## Technical Approach

**Files Modified:**

| File | What changed |
|---|---|
| `backend/agents/a3_ocr.py` | Replaced TODO stub in `handle()` with real `self._ocr.extract_bag_tag()` call. Updated `BAG_ID_PATTERN` from `\d{10}` → `\d{10,12}` (real-world tags can be 10–12 digits, discovered in T-007 smoke test with Swissport SAW tag). Added structured warning logs for missing `pnr` and `bag_id` fields. Google-style docstring on `handle()`. |

**Files Created:**

| File | Purpose |
|---|---|
| `tests/test_a3_ocr_agent.py` | 10 unit tests — skip (no images, damage-only), full extraction, first-image-only selection, mixed list filtering, confidence threshold boundary, null pnr/bag_id handling, error resilience |

**Already complete in starter (no changes):**

| File | What was already there |
|---|---|
| `backend/ocr_provider/base.py` | `OCRProvider` ABC + `TagData` dataclass |
| `backend/ocr_provider/gemini_ocr.py` | `GeminiOCRProvider.extract_bag_tag()` — fully implemented in T-007 |
| `backend/dependencies.py` | `provide_ocr()` already routes `OCR_PROVIDER=gemini` → `GeminiOCRProvider` |
| `backend/graph/state.py` | All A3 output fields (`pnr`, `flight_number`, `bag_id`, `ocr_confidence`, `re_request_tag`) already defined |

**Provider / Abstraction:**

```
A3OCRAgent receives an OCRProvider instance via constructor injection.
It never imports GeminiOCRProvider directly.
Swap path: OCR_PROVIDER=paddleocr → paddleocr.py used instead.
Zero A3 changes needed for the swap.
```

**Key Design Decisions:**

```
1. FIRST TAG IMAGE ONLY
   A3 calls extract_bag_tag() on tag_images[0] only.
   A passenger rarely uploads multiple bag tag photos — if they do,
   the first one is the best angle (front of the tag).
   Running OCR on multiple identical tag images wastes API quota.

2. CONFIDENCE WRITTEN BEFORE THE THRESHOLD CHECK
   state.ocr_confidence = result.confidence is set BEFORE the
   threshold check. This means even when re_request_tag=True,
   the confidence value is persisted for monitoring and debugging.
   The downstream team (T-016 integration) can track OCR quality
   over the test runs.

3. FIELDS NOT WRITTEN ON LOW CONFIDENCE
   If confidence < 0.7, we do NOT write pnr/flight_number/bag_id.
   Writing low-confidence data and then asking for a retake would
   leave stale data in ClaimState that A4 might accidentally use.
   Clean slate is safer.

4. NULL FIELDS LOGGED AS WARNINGS (NOT ERRORS)
   Many real airline bag tags don't print a PNR (only boarding passes
   have PNR). A null pnr is expected on some tag types — it's a warning,
   not a failure. A4 handles missing PNR gracefully by skipping the
   PNR-based fraud checks.

5. BAG_ID_PATTERN UPDATED TO \d{10,12}
   The original stub used \d{10} (strict IATA standard).
   T-007 smoke testing revealed real Swissport tags print 12-digit
   bag IDs (e.g. "0452 30 674234" → stripped to "045230674234").
   Pattern updated to \d{10,12} to match the fix made in the provider.
   This is a BELT-AND-SUSPENDERS validation — provider already strips
   spaces. A3 pattern is here for defensive monitoring.

6. GRACEFUL ERROR HANDLING
   try/except wraps all provider calls.
   Any exception → state.set_error() set.
   Pipeline never crashes on OCR failure — A4 handles missing data.
```

---

## What A3 Does Step by Step

```
ClaimState arrives from A2 (damage assessed, image_paths populated)
        ↓
tag_images = [p for p in image_paths if "tag" in p.lower()]
        ↓
if not tag_images → return unchanged (no tag photo uploaded yet)
        ↓
result = await self._ocr.extract_bag_tag(tag_images[0])
        ↓
state.ocr_confidence = result.confidence
        ↓
if result.confidence < 0.7:
    state.re_request_tag = True
    return state   ← A1 asks passenger to retake tag photo
        ↓
state.flight_number = result.flight_number   (e.g. "AI202" or None)
state.pnr           = result.pnr             (e.g. "ABC123" or None)
state.bag_id        = result.bag_id          (e.g. "0572351234" or None)
        ↓
A4 runs next:
  - pnr used for pHash duplicate check + frequency fraud check
  - flight_number + bag_id stored in claim record for airline reference
```

---

## Impact on Fraud Detection (Before vs After T-011)

```
BEFORE T-011:
  state.pnr = "ABC123"  (hardcoded stub — same for every claim)
  → A4 frequency check queries DB for "ABC123" every time
  → meaningless fraud data

AFTER T-011:
  state.pnr = real PNR from bag tag (or None if unreadable)
  → A4 frequency check queries ACTUAL passenger PNR
  → real fraud detection possible ✅
```

---

## Dependencies

```
Depends On          →  T-007 (GeminiOCRProvider — extract_bag_tag() implemented)
                       T-005 (LangGraph skeleton — orchestrator + ClaimState)
External Libraries  →  google-generativeai (already in requirements.txt)
                       No new dependencies added.
Environment Vars    →  GEMINI_API_KEY (existing)
                       OCR_PROVIDER=gemini (existing default)
                       No new env vars added.
```

---

## Testing

**Run tests:**
```bash
pytest tests/test_a3_ocr_agent.py -v
# Expected: 10 passed

pytest tests/ -v
# Expected: 80 passed total (70 existing + 10 new)
```

**Manual smoke test (with both damage + tag image):**
```bash
uvicorn backend.main:app --reload --port 8000

curl -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "smoke-a3-full",
    "message": "my bag is damaged",
    "image_paths": [
      "tests/fixtures/damaged/damaged_01.jpg",
      "tests/fixtures/bag_tags/clear_tag_01.jpg"
    ]
  }'
```

Expected server logs:
```
a2_damage_analyzed      severity=1.0   damage_types=[...]
a2_completed            compensation_usd=150.0
a3_started
gemini_ocr_extract_tag_started
gemini_ocr_extract_tag_completed    bag_id=045230674234  confidence=0.9
a3_completed            pnr=None  flight_number=None  bag_id=045230674234
a4_completed            lane=2
```

**Acceptance Criteria:**
```
✅ A3 only processes tag photos (paths with "tag" in filename)
✅ extract_bag_tag() called on first tag image only
✅ ocr_confidence written to state in all cases (including re-request)
✅ Confidence < 0.7 → re_request_tag=True, fields NOT written
✅ Confidence ≥ 0.7 → flight_number, pnr, bag_id all written
✅ Null pnr / bag_id from provider → None in state, no crash
✅ Provider failure → state.error set, pipeline continues
✅ BAG_ID_PATTERN updated to \d{10,12} (T-007 real-world fix)
✅ No direct Gemini or Supabase imports in agents/
✅ Type hints on handle()
✅ Google-style docstring on handle()
✅ pytest tests/test_a3_ocr_agent.py → 10 passed
✅ pytest tests/ → 80 passed, 0 failures
✅ black + isort clean
```

---

## PR Checklist

```
[x] PR title includes Task ID — [T-011] feat(agents): ...
[x] PR description filled out on GitHub
[x] Base branch: develop (not main)
[x] Reviewer: Devam
[x] No direct Gemini/DB imports in agents/
[x] OCRProvider ABC used throughout
[x] Type hints + Google-style docstring on handle()
[x] No hardcoded API keys
[x] BAG_ID_PATTERN updated to \d{10,12}
[x] pytest tests/test_a3_ocr_agent.py → 10 passed
[x] pytest tests/ → 80 passed, 0 failures
[x] black backend/ tests/ → clean
[x] isort backend/ tests/ → clean
[x] Branch doc committed to BRANCH_DOCS/ before merge
[x] Squash merged to develop
[x] Feature branch deleted after merge
```

---

## Notes

```
Pattern fix    →  BAG_ID_PATTERN changed from \d{10} → \d{10,12}.
                  Discovered during T-007 smoke testing: Swissport SAW tag
                  printed "0452 30 674234" (12 digits after space stripping).
                  GeminiOCRProvider already handles this — A3 pattern updated
                  to match.

Null PNR       →  Expected on many tag types (Swissport, Air NZ etc. don't
                  print PNR on the bag tag, only on the boarding pass).
                  A4 handles missing PNR gracefully — skips PNR-based fraud
                  checks and proceeds with pHash check only.

Parallel work  →  T-010 (A2 vision) merged before this branch opened.
                  T-012 (A4 decision) already merged to develop.
                  Zero file overlap with both.

Next Tasks     →  T-013 (simulator full flow) — Anoushka
                  T-014 (Supabase DB) — Aditya
                  T-015 (A5 notifications) — Devam
                  All depend on T-012 ✅ — all can start now.

Blockers       →  None — T-011 complete.

Links          →  OCRProvider ABC:         backend/ocr_provider/base.py
                  GeminiOCRProvider:       backend/ocr_provider/gemini_ocr.py
                  ClaimState A3 fields:    backend/graph/state.py
                  T-007 bag_id fix:        BRANCH_DOCS/fix-ocr-bag-id.md
```

---

*Branch opened: Day 7, Week 2 — Anoushka Vyas*
*Merged to develop: Day 7, Week 2*
