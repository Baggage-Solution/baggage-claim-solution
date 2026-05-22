# BRANCH: feature/agent-a2-vision

---

## Branch Metadata

```
Branch Name   →  feature/agent-a2-vision
Task ID       →  T-010
Workstream    →  Vision / AI
Author        →  Anoushka Vyas
Reviewer      →  Devam Dixit
Start Date    →  Day 6, Week 2
Target Merge  →  Day 7, Week 2
Actual Merge  →  Day 7, Week 2
Status        →  Merged
```

---

## Objective

**What does this branch do?**
Implements `A2VisionAgent.handle()` — the vision analysis node of the LangGraph
pipeline. Replaces the T-010 TODO stub with a full implementation that calls
`GeminiVisionProvider` for every damage photo in `state.image_paths`, aggregates
damage types and severity across multiple images, runs brand classification for
luxury detection, calculates the initial compensation estimate, and handles low
quality photos by requesting a retake.

**Why is it needed?**
Before T-010, `is_luxury` was always `False` and `compensation_estimate_usd`
was always `0.0` — meaning A4's decision engine always routed claims to Lane 1
regardless of actual damage. T-010 is what gives A4 real data to work with.
After this merge, luxury bags correctly route to Lane 2 and high-severity damage
correctly pushes compensation above the $100 Lane 1 threshold.

---

## Local Setup

```bash
source venv/Scripts/activate      # Git Bash / Windows
# source venv/bin/activate        # Mac / Linux

pip install -r requirements.txt
pytest tests/test_a2_vision.py -v
```

---

## Technical Approach

**Files Modified:**

| File | What changed |
|---|---|
| `backend/agents/a2_vision.py` | Replaced TODO stub in `handle()` with full implementation. Added `_is_damage_photo()` (tag photo filter), `_calculate_compensation()` (linear severity scale), and the complete 5-step analysis flow in `handle()`. Added module-level constants `_SEVERITY_TO_USD_SCALE = 150.0` and `_MIN_ACCEPTABLE_CONFIDENCE = 0.4`. Type hints and Google-style docstrings throughout. |

**Files Created:**

| File | Purpose |
|---|---|
| `tests/test_a2_vision.py` | 10 unit tests — skip conditions (no images, tag-only), single image, multi-image aggregation, deduplication, tag photo filtering, luxury detection, low-confidence re-request, compensation linear scale, provider failure graceful handling |

**Already complete in starter (no changes):**

| File | What was already there |
|---|---|
| `backend/vision_provider/base.py` | `VisionProvider` ABC + `DamageResult` + `BrandResult` dataclasses |
| `backend/vision_provider/gemini_vision.py` | `GeminiVisionProvider.analyze_damage()` + `classify_brand()` — fully implemented in T-006 |
| `backend/dependencies.py` | `provide_vision()` already routes `VISION_PROVIDER=gemini` → `GeminiVisionProvider` |
| `backend/graph/state.py` | All A2 output fields (`damage_types`, `severity_score`, `brand_detected`, `is_luxury`, `compensation_estimate_usd`, `re_request_damage`) already defined |

**Provider / Abstraction:**

```
A2VisionAgent receives a VisionProvider instance via constructor injection.
It never imports GeminiVisionProvider directly.
Swap path: VISION_PROVIDER=yolov8 in .env → yolov8_vision.py used instead.
Zero A2 changes needed for the swap.
```

**Key Design Decisions:**

```
1. DAMAGE PHOTO FILTER: "tag" NOT IN FILENAME
   A2 processes damage photos. A3 processes bag tag photos.
   The split is by filename convention: tag photos contain "tag"
   (e.g. "tag_front.jpg", "tag_barcode.jpg").
   This is simple and reliable — the /upload endpoint names files
   with photo_type prefix: "damage_" or "tag_".

2. MAX SEVERITY (WORST DAMAGE WINS)
   When multiple damage photos are uploaded, A2 takes the maximum
   severity_score across all images. This ensures we don't average
   out severe damage with cosmetic damage from a different angle.
   Example: scratch (0.3) + broken wheel (0.8) → severity = 0.8.

3. DEDUPLICATED DAMAGE TYPES
   Same damage type may appear in multiple photos of different angles.
   dict.fromkeys() preserves insertion order while deduplicating.
   Example: [cracked shell, broken wheel, cracked shell] → [cracked shell, broken wheel]

4. BRAND CLASSIFICATION ON FIRST DAMAGE PHOTO ONLY
   classify_brand() is called once — on damage_photos[0].
   The brand is visible on the bag body which appears in every damage photo.
   Running it on every photo would waste API quota with identical results.

5. CONFIDENCE THRESHOLD = 0.4
   If max confidence across ALL images is below 0.4, the photos are
   unusable — passenger is asked to retake them (re_request_damage=True).
   The state is NOT updated with partial data in this case.
   Threshold matches the OCR confidence threshold in T-007.

6. LINEAR COMPENSATION SCALE: severity × $150
   severity 0.0 → $0.00  (no damage)
   severity 0.5 → $75.00 (moderate — below $100 Lane 1 threshold)
   severity 0.67 → $100.00 (exact Lane 1/2 boundary)
   severity 0.8 → $120.00 (significant → Lane 2)
   severity 1.0 → $150.00 (destroyed → Lane 2)
   A4 applies 1.5× luxury multiplier on top: Rimowa at 0.5 → $75 × 1.5 = $112.50 → Lane 2.

7. GRACEFUL ERROR HANDLING
   try/except wraps all provider calls.
   Any exception → state.set_error() → A5 will handle gracefully.
   Pipeline never crashes on a vision failure.
```

---

## What A2 Does Step by Step

```
ClaimState arrives from A1 (passenger_message set, image_paths populated by /upload)
        ↓
if not image_paths → return unchanged (passenger hasn't sent photos yet)
        ↓
damage_photos = [p for p in image_paths if "tag" not in p.lower()]
        ↓
if not damage_photos → return unchanged (only tag photos, A3 will handle)
        ↓
For each damage photo:
  result = await self._vision.analyze_damage(image_path)
  all_damage_types += result.damage_types
  max_severity = max(max_severity, result.severity_score)
  max_confidence = max(max_confidence, result.confidence)
        ↓
if max_confidence < 0.4:
  state.re_request_damage = True
  return state   ← A1 will ask passenger to retake photos
        ↓
brand_result = await self._vision.classify_brand(damage_photos[0])
        ↓
state.damage_types              = deduplicated(all_damage_types)
state.severity_score            = max_severity
state.brand_detected            = brand_result.brand
state.is_luxury                 = brand_result.is_luxury
state.compensation_estimate_usd = severity × 150.0
        ↓
A3 runs next → reads same state, adds OCR fields
        ↓
A4 runs → sees real is_luxury and compensation → makes real routing decision
```

---

## Impact on Routing (Before vs After T-010)

```
BEFORE T-010 (stub):
  is_luxury               = False  (always)
  compensation_estimate   = $0.00  (always)
  fraud_score             = 0.0    (always)
  → A4 always routes Lane 1 ❌

AFTER T-010 (real):
  Standard bag, minor damage:   is_luxury=False, compensation=$45  → Lane 1 ✅
  Standard bag, major damage:   is_luxury=False, compensation=$120 → Lane 2 ✅
  Rimowa bag, any damage:       is_luxury=True                     → Lane 2 ✅
  Blurry photos:                re_request_damage=True             → A1 asks retake ✅
```

---

## Dependencies

```
Depends On          →  T-006 (GeminiVisionProvider — analyze_damage + classify_brand)
                       T-005 (LangGraph skeleton — orchestrator + ClaimState)
External Libraries  →  google-generativeai (already in requirements.txt)
                       Pillow (already in requirements.txt)
                       No new dependencies added.
Environment Vars    →  GEMINI_API_KEY (existing)
                       VISION_PROVIDER=gemini (existing default)
                       No new env vars added.
```

---

## Testing

**Run tests:**
```bash
pytest tests/test_a2_vision.py -v
# Expected: 10 passed

pytest tests/ -v
# Expected: 70 passed total (60 existing + 10 new)
```

**Manual smoke tests (real Gemini API — needs server running):**
```bash
uvicorn backend.main:app --reload --port 8000

# Standard bag → Lane 1
curl -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -d '{"session_id":"smoke-std","message":"my bag is damaged","image_paths":["tests/fixtures/damaged/damaged_01.jpg"]}'
# Expected: routing_lane=1, compensation in [$0–$100] range

# Luxury bag → Lane 2
curl -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -d '{"session_id":"smoke-lux","message":"my rimowa is damaged","image_paths":["tests/fixtures/damaged/luxury_01.jpg"]}'
# Expected: routing_lane=2, is_luxury flag visible in server logs
```

**Acceptance Criteria:**
```
✅ A2 filters tag photos — only damage photos sent to VisionProvider
✅ damage_types aggregated and deduplicated across all damage images
✅ severity_score = max across all damage images
✅ brand_detected and is_luxury set from classify_brand()
✅ Luxury brands (Rimowa etc.) correctly set is_luxury=True → A4 routes Lane 2
✅ compensation_estimate_usd = severity × $150
✅ max_confidence < 0.4 → re_request_damage=True, state not updated
✅ VisionProvider failure → state.error set, pipeline never crashes
✅ No direct Gemini imports in agents/ — only VisionProvider ABC
✅ All thresholds as named module constants, not magic numbers
✅ Type hints on all methods
✅ Google-style docstrings on all public methods
✅ pytest tests/test_a2_vision.py → 10 passed
✅ pytest tests/ → 70 passed, 0 failures
✅ black + isort clean
```

---

## PR Checklist

```
[x] PR title includes Task ID — [T-010] feat(agents): ...
[x] PR description filled out on GitHub
[x] Base branch: develop (not main)
[x] Reviewer: Devam
[x] No direct Gemini imports in agents/
[x] Module constants used for all thresholds
[x] Type hints on all methods
[x] Google-style docstrings on all public methods
[x] No hardcoded API keys
[x] pytest tests/test_a2_vision.py → 10 passed
[x] pytest tests/ → 70 passed, 0 failures
[x] black backend/ tests/ → clean
[x] isort backend/ tests/ → clean
[x] Branch doc committed to BRANCH_DOCS/ before merge
[x] Squash merged to develop
[x] Feature branch deleted after merge
```

---

## Notes

```
Known Issues  →  end-to-end luxury routing only visible via smoke test after
                 server is running with GEMINI_API_KEY. Unit tests verify A2
                 logic is correct using mocked provider responses.

Parallel work →  T-011 (A3 OCR node) — Anoushka, starts after T-010 merges.
                 T-012 (A4 decision)  — Devam, already merged to develop.
                 Zero file overlap with both.

Next Task     →  T-011 (feature/agent-a3-ocr) — same pattern as T-010
                 but for OCR provider instead of vision provider.

Blockers      →  None — T-010 complete.

Links         →  VisionProvider ABC:      backend/vision_provider/base.py
                 GeminiVisionProvider:    backend/vision_provider/gemini_vision.py
                 ClaimState A2 fields:    backend/graph/state.py
                 Routing thresholds:      backend/config.py → Settings class
```

---

*Branch opened: Day 6, Week 2 — Anoushka Vyas*
*Merged to develop: Day 7, Week 2*
