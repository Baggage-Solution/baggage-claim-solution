# BRANCH: feature/vision-provider-gemini

---

## Branch Metadata

```
Branch Name   →  feature/vision-provider-gemini
Task ID       →  T-006
Workstream    →  Vision / AI
Author        →  Anoushka
Reviewer      →  Devam
Start Date    →  Day 2, Week 1
Target Merge  →  Day 4, Week 1
Actual Merge  →  Day 4, Week 1
Status        →  Merged
```

---

## Objective

**What does this branch do?**
Implements the GeminiVisionProvider — the vision layer of the baggage claim AI system.
Given a photo of a damaged bag, it returns structured damage assessment (damage types,
severity score, confidence). Given a bag photo, it identifies the brand and determines
if it is a luxury item. Built on top of the VisionProvider abstract base class so the
entire vision layer can be swapped to YOLOv8 or MobileNet in Phase 2 with zero agent
code changes.

**Why is it needed?**
A2VisionAgent (T-010) depends entirely on this provider. Without it, the system cannot
assess damage severity, cannot flag luxury bags, and cannot calculate compensation
estimates. This is the component that gives the AI system its "eyes".

---

## Local Setup

```bash
# Activate venv (run this every time you open a new terminal)
source venv/Scripts/activate       # Git Bash / Mac / Linux
# OR
venv\Scripts\activate              # Windows CMD

# Install dependencies
pip install -r requirements.txt

# Start server (separate terminal)
uvicorn backend.main:app --reload --port 8000
```

---

## Technical Approach

**Files Created:**
```
tests/test_vision_provider.py        →  8 unit tests, all Gemini calls mocked
tests/fixtures/damaged/damaged_01.jpg  →  destroyed red bag (severity 1.0)
tests/fixtures/damaged/damaged_02.jpg  →  torn fabric luggage
tests/fixtures/damaged/luxury_01.jpg   →  Rimowa silver aluminum suitcase
```

**Files Modified:**
```
backend/vision_provider/gemini_vision.py  →  Replaced stubs with full implementation:
                                              - analyze_damage() with real Gemini API call
                                              - classify_brand() with real Gemini API call
                                              - _load_image() helper
                                              - _parse_json_response() helper
                                              - DAMAGE_ANALYSIS_PROMPT constant
                                              - BRAND_CLASSIFICATION_PROMPT constant
                                              - Type hints + Google-style docstrings
requirements.txt                          →  Added Pillow for image loading
pytest.ini                               →  Added asyncio_mode = auto for async tests
```

**Files Already Complete (No Changes Needed):**
```
backend/vision_provider/base.py   →  VisionProvider ABC, DamageResult, BrandResult
backend/agents/a2_vision.py       →  Calls this provider (fully wired in T-010)
backend/dependencies.py           →  provide_vision() already wired correctly
```

**Provider / Abstraction Used:**
```
Implements:  VisionProvider ABC (backend/vision_provider/base.py)
Via:         Gemini 2.5 Flash multimodal API (free tier — 1500 req/day)
Injected by: provide_vision() in dependencies.py
A2 imports:  VisionProvider only — never GeminiVisionProvider directly
```

**Key Design Decisions:**

```
1. STRUCTURED PROMPT DESIGN
   Both prompts explicitly instruct Gemini to return ONLY a JSON object
   with exact field names and value ranges. This makes parsing reliable
   and consistent across all image types.

2. MARKDOWN STRIPPING IN _parse_json_response()
   Gemini sometimes wraps its JSON response in markdown code blocks
   (```json ... ```). _parse_json_response() strips these before parsing
   so the system never breaks due to Gemini's inconsistent formatting.

3. LUXURY_BRANDS DOUBLE CHECK
   classify_brand() uses TWO checks for is_luxury:
   - Gemini's own is_luxury assessment
   - Cross-check against our hardcoded LUXURY_BRANDS set
   If EITHER is true → is_luxury = True
   This prevents Gemini from missing a known luxury brand.
   The set is intentional business logic — defined by airline policy.

4. PIL IMAGE LOADING
   Images are loaded via PIL (Pillow) before passing to Gemini.
   This ensures format compatibility (JPG, PNG, WEBP all supported)
   and gives a clean FileNotFoundError if the path doesn't exist.

5. ASYNC THROUGHOUT
   Both analyze_damage() and classify_brand() are async def as required
   by coding standards and the LangGraph async pipeline.
```

**Future Swap Path:**
```
To swap Gemini for YOLOv8 in Phase 2:
1. Create backend/vision_provider/yolov8_vision.py
2. Implement VisionProvider ABC (analyze_damage + classify_brand)
3. Add to dependencies.py: if s.vision_provider == "yolov8": return YOLOv8VisionProvider(...)
4. Set VISION_PROVIDER=yolov8 in .env
5. Zero changes needed in agents/, orchestrator, or any other file
```

---

## Real-World Test Results (Smoke Test with Actual Gemini API)

```
# Test 1 — damaged_01.jpg (destroyed red bag)
damage_types:   ['severely torn fabric', 'shredded exterior',
                 'exposed internal structure', 'compromised structural integrity']
severity_score: 1.0
confidence:     1.0
→ Pipeline result: Lane 2 (compensation exceeds $100 threshold)

# Test 2 — luxury_01.jpg (Rimowa silver suitcase)
brand:          Rimowa
is_luxury:      True
confidence:     0.95
→ Pipeline result: Lane 2 (luxury bag always goes to staff review)
```

---

## Dependencies

```
Depends On          →  T-002 (venv + pip install must work)
External Libraries  →  google-generativeai (already in requirements.txt)
                       Pillow==10.4.0 (added in this branch)
                       pytest-asyncio==0.23.8 (added in this branch)
Environment Vars    →  GEMINI_API_KEY
                       GEMINI_VISION_MODEL=gemini-2.5-flash
                       VISION_PROVIDER=gemini
```

---

## Testing

**Automated Tests (No Real API Calls):**
```bash
pytest tests/test_vision_provider.py -v

# Expected:
# test_analyze_damage_returns_damage_result    PASSED
# test_analyze_damage_no_damage                PASSED
# test_analyze_damage_strips_markdown_json     PASSED
# test_classify_brand_luxury_detected          PASSED
# test_classify_brand_standard_bag             PASSED
# test_classify_brand_luxury_set_override      PASSED
# test_classify_brand_unknown                  PASSED
# test_analyze_damage_file_not_found           PASSED
# 8 passed

# Full suite:
pytest tests/ -v
# Expected: 15 passed (7 original ClaimState tests + 8 new vision tests)
```

**Manual Smoke Test (Real Gemini API):**
```bash
# Test damage analysis
python -c "import asyncio; from backend.dependencies import provide_vision; \
vision = provide_vision(); \
result = asyncio.run(vision.analyze_damage('tests/fixtures/damaged/damaged_01.jpg')); \
print('damage_types:', result.damage_types); \
print('severity_score:', result.severity_score); \
print('confidence:', result.confidence)"

# Test brand classification
python -c "import asyncio; from backend.dependencies import provide_vision; \
vision = provide_vision(); \
result = asyncio.run(vision.classify_brand('tests/fixtures/damaged/luxury_01.jpg')); \
print('brand:', result.brand); \
print('is_luxury:', result.is_luxury); \
print('confidence:', result.confidence)"
```

**Test Fixtures:**
```
tests/fixtures/damaged/damaged_01.jpg  →  severely destroyed red bag  (severity 1.0)
tests/fixtures/damaged/damaged_02.jpg  →  torn fabric suitcase
tests/fixtures/damaged/luxury_01.jpg   →  Rimowa silver aluminum case (is_luxury True)
```

**Acceptance Criteria:**
```
✅ analyze_damage() returns DamageResult with damage_types + severity_score > 0
✅ classify_brand() returns BrandResult with is_luxury=True for Rimowa image
✅ LUXURY_BRANDS set cross-check works (overrides Gemini if needed)
✅ JSON safely parsed — handles markdown code blocks from Gemini
✅ No provider names imported in agents/ — only VisionProvider ABC used
✅ Type hints on all functions
✅ Google-style docstrings on all public functions
✅ black + isort run clean
✅ 8 unit tests pass — all Gemini calls mocked (no real API in test suite)
✅ pytest tests/ → 15 passed total
```

---

## PR Checklist

```
[x] PR title includes Task ID — [T-006] feat(vision): ...
[x] PR description filled out on GitHub
[x] Base branch set to develop (not main)
[x] Reviewer assigned — Devam
[x] Type hints on all new/modified functions
[x] Google-style docstrings on all public functions
[x] No hardcoded provider names in agents/
[x] No hardcoded API keys — all via os.getenv / Settings
[x] Pillow added to requirements.txt
[x] pytest-asyncio added to requirements.txt
[x] pytest.ini created with asyncio_mode = auto
[x] black backend/ → clean
[x] isort backend/ → clean
[x] pytest tests/ → 15 passed, 0 failures
[x] Squash merged to develop
[x] Feature branch deleted after merge
```

---

## Notes / Blockers

```
Known Issues  →  pytest shows deprecation warnings from pytest-asyncio internals
                 (asyncio.get_event_loop_policy). Library-level issue, not our code.
                 Safe to ignore for POC.

                 Test fixture images are real photos saved from web search.
                 For production: replace with airline-provided dataset (requested via email).

Model Note    →  Using gemini-2.5-flash (upgraded from deprecated gemini-1.5-flash in T-004)

Blockers      →  None — T-006 complete

Next Task     →  T-007 (OCR Provider Wrapper) — depends on T-006 ✅

Links         →  Gemini Vision API:   https://ai.google.dev/gemini-api/docs/vision
                 Gemini Pricing:      https://ai.google.dev/pricing
                 VisionProvider ABC:  backend/vision_provider/base.py
                 Future YOLOv8 swap:  implement backend/vision_provider/yolov8_vision.py
```
