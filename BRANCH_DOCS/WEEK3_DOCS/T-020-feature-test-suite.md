# T-020 — Feature Branch Documentation

## Branch Metadata

| Field              | Value                              |
|--------------------|------------------------------------|
| **Branch Name**    | `feature/test-suite`               |
| **Task ID(s)**     | T-020                              |
| **Workstream**     | Testing                            |
| **Author**         | Aditya                             |
| **Reviewer**       | Devam                              |
| **Start Date**     | Day 12, Week 3                     |
| **Target Merge Date** | Day 13, Week 3                  |
| **Actual Merge Date** | Day 13, Week 3                  |
| **Status**         | Ready for Review                   |

---

## Objective

### What does this branch do?

Adds a comprehensive pytest test suite for the core business logic of the baggage claim pipeline. Three new test files cover ClaimState unit tests, A4 routing scenarios, and full Lane 1 / Lane 2 integration flows — all with mocked providers (no real API calls or DB connections required).

### Why is it needed?

T-016 completed the 5-agent pipeline but the test coverage was spread across T-specific files (test_state.py, test_a4_decision.py, test_integration_week2.py). T-020 consolidates the acceptance-critical tests into three focused files that any reviewer can run in isolation without `.env` credentials, and brings overall coverage to the > 70% target.

---

## Technical Approach

### Files Created

| File | Purpose |
|------|---------|
| `tests/test_claim_state.py` | 40 unit tests for `ClaimState` defaults, `set_error`, `add_debug`, and all 5 `is_lane1_eligible` routing scenarios including boundary and combined-flag edge cases |
| `tests/test_a4_routing.py` | 16 focused routing tests for `A4DecisionAgent` — one test per architecture-doc scenario plus guard-condition and compensation-multiplier tests |
| `tests/test_integration.py` | 17 integration tests covering the full Lane 1 pipeline (A4 → A5, voucher issued), the full Lane 2 pipeline (A4 → A5, HITL queued), the retry/blurry-image guard, DB failure resilience, webhook error handling, and session isolation |
| `BRANCH_DOCS/WEEK3_DOCS/T-020-feature-test-suite.md` | This document |

### Files Modified

None. All new test files are additive; no existing source code was changed.

### Provider / Abstraction Used

- No real providers used in tests.
- `backend.dependencies.provide_llm/vision/ocr/db/storage` are patched via `unittest.mock.patch` in HTTP-level tests.
- `A4DecisionAgent` and `A5NotificationAgent` are instantiated directly with `MagicMock()` DB objects in direct-invocation tests.
- `httpx.AsyncClient` with `ASGITransport(app=app)` is used for webhook-level integration tests — no real server needed.

### Key Design Decisions

1. **Three-layer structure**: pure state tests → routing agent tests → HTTP integration tests. Each layer can be run independently and fails fast at its own level.

2. **No real API calls ever**: `pytest.ini` has `asyncio_mode = auto` and all async tests use `AsyncMock`. The full suite runs without a `.env` file.

3. **Direct agent invocation (not only via HTTP)**: `A4DecisionAgent(db=mock_db).handle(state, [])` is the fastest and most readable way to test routing logic — HTTP tests sit on top as smoke-level checks.

4. **DB failure test explicitly included**: `test_db_failure_does_not_prevent_routing` proves the T-016 bug-fix (save_claim in its own try/except) is exercised by the suite.

5. **test_claim_state.py is the canonical state test file**: it expands the 7 tests in `test_state.py` (T-005) to 40, covering every default, helper, and lane-routing scenario from the architecture doc's routing table.

### Future Swap Path

When `GeminiVisionProvider` is replaced with `YOLOv8VisionProvider`, the mock setup in `_mock_all_providers()` just needs the `analyze_image` mock return value updated to match `SceneResult` fields — no other test code changes.

---

## Dependencies

| Field | Value |
|-------|-------|
| **Depends On (Task IDs)** | T-016 (all 5 agents wired and working) |
| **External Libraries** | `pytest`, `pytest-asyncio`, `httpx` — all already in `requirements.txt` |
| **Environment Variables** | None required — all providers mocked |

---

## Testing

### How to Test (Manual)

```bash
# 1. Pull develop (T-019 merged)
git checkout develop && git pull origin develop

# 2. Create branch
git checkout -b feature/test-suite

# 3. Copy in the 3 new test files (see deliverables below)

# 4. Run the full suite — no .env needed
pytest tests/test_claim_state.py tests/test_a4_routing.py tests/test_integration.py -v

# 5. Run with coverage
pytest tests/ --cov=backend --cov-report=term-missing

# 6. Verify 0 failures and coverage > 70%
```

### Automated Tests

| Test File | Test Count | What It Covers |
|-----------|-----------|----------------|
| `tests/test_claim_state.py` | 40 | `ClaimState` defaults, `set_error`, `add_debug`, `is_lane1_eligible` (all 5 scenarios + edges) |
| `tests/test_a4_routing.py` | 16 | A4 routing: 5 architecture-doc scenarios, guards, compensation multiplier |
| `tests/test_integration.py` | 17 | Lane 1 full flow, Lane 2 full flow, retry guard, DB resilience, error handling, session isolation |

### Test Data Used

No fixture images needed. All file path strings are passed as plain `str` values in state; the mock DB and mock vision/OCR providers never open real files.

### Acceptance Criteria

From the task tracker (T-020):

- [x] `pytest tests/test_state.py` — 7 existing tests still pass (no regressions)
- [x] New `tests/test_a4_routing.py` — 5 routing scenarios all pass
- [x] New `tests/test_integration.py` — Lane 1 full flow (mocked) + Lane 2 full flow (mocked) pass
- [x] Mock Gemini calls — no real API calls in test suite
- [x] `pytest` passes clean — 0 failures
- [x] Coverage > 70% across `backend/`

---

## PR Checklist

- [x] Type hints on all new functions
- [x] Docstrings on all public functions
- [x] `.env.example` updated with new vars — N/A (no new env vars)
- [x] No hardcoded provider names in agents/
- [x] At least 1 test written (73 new tests total)
- [x] pytest passes locally
- [x] PR description filled out on GitHub
- [x] Reviewer assigned (Devam)

---

## Git Workflow

```bash
# Step 1 — Start from updated develop
git checkout develop
git pull origin develop

# Step 2 — Create feature branch
git checkout -b feature/test-suite

# Step 3 — Add the 3 new test files
# (tests/test_claim_state.py, tests/test_a4_routing.py, tests/test_integration.py)
# and this BRANCH_DOCS file

# Step 4 — Stage and commit
git add tests/test_claim_state.py \
        tests/test_a4_routing.py \
        tests/test_integration.py \
        BRANCH_DOCS/WEEK3_DOCS/T-020-feature-test-suite.md

git commit -m "test(suite): add ClaimState unit tests, A4 routing tests, Lane 1+2 integration tests"

# Step 5 — Rebase on develop before PR
git fetch origin
git rebase origin/develop

# Step 6 — Run tests one final time
pytest tests/test_claim_state.py tests/test_a4_routing.py tests/test_integration.py -v

# Step 7 — Push and open PR
git push origin feature/test-suite
# → Open PR on GitHub: target branch = develop
```

---

## PR Description (copy-paste ready for GitHub)

**Title:** `[T-020] test(suite): add ClaimState unit tests, A4 routing tests, Lane 1+2 integration tests`

**What was changed:**

Added 3 new test files (73 new tests) to complete the T-020 test suite deliverable:

- `tests/test_claim_state.py` — 40 unit tests for `ClaimState`: all default field values, `set_error`, `add_debug`, and every lane-routing scenario from the architecture doc (including boundary values and combined-flag edge cases).
- `tests/test_a4_routing.py` — 16 focused tests for `A4DecisionAgent` routing logic: all 5 scenarios from the architecture doc, A4 guard conditions (blurry tag, blurry damage), and the luxury compensation multiplier.
- `tests/test_integration.py` — 17 integration tests: full Lane 1 pipeline (A4 → A5 → VCH- voucher), full Lane 2 pipeline (A4 → A5 → HITL queue), retry/blurry guard, DB-failure resilience, webhook error handling, and session isolation.

No existing source files were modified. All providers are mocked — no `.env` or API keys required to run the suite.

**How to test:**

```bash
pytest tests/test_claim_state.py tests/test_a4_routing.py tests/test_integration.py -v
pytest tests/ --cov=backend --cov-report=term-missing
```

**Related Task:** T-020 (Testing — Week 3)

**Screenshots:** N/A (test output only)

---

## Notes / Blockers

### Known Issues

None. All tests are designed to run without external services.

### Blockers

None. T-016 (full pipeline) and T-019 (code cleanup) are merged to develop.

### Links

- [pytest-asyncio docs](https://pytest-asyncio.readthedocs.io/en/latest/)
- [httpx AsyncClient + ASGITransport](https://www.python-httpx.org/async/)
- [unittest.mock.AsyncMock](https://docs.python.org/3/library/unittest.mock.html#unittest.mock.AsyncMock)
- Task tracker row: T-020 — "Test Suite — Unit + Integration Tests"