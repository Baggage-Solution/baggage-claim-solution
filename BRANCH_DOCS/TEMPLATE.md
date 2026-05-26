# Feature Branch Documentation Template
# Copy this file for each branch: BRANCH_DOCS/feature-T-XXX-desc.md

## Branch metadata

| Field | Value |
|---|---|
| Branch name | `feature/T-XXX-short-description` |
| Task ID | T-XXX |
| Workstream | [Vision AI / Backend / LangGraph / etc.] |
| Author | [Anoushka / Aditya / Devam] |
| Reviewer | [Name] |
| Start date | Day X, Week Y |
| Target merge date | Day X, Week Y |
| Actual merge date | |
| Status | Not Started / In Progress / Ready for Review / Merged |

## Objective

**What does this branch do?**
1–3 sentence summary.

**Why is it needed?**
How does it fit the overall architecture?

## Technical approach

**Files created**

| File | Purpose |
|---|---|
| `backend/agents/a2_vision.py` | A2 vision analysis LangGraph node |

**Files modified**

| File | What changed |
|---|---|

**Provider / abstraction used**
e.g. Implements `VisionProvider` ABC via Gemini Flash API.

**Key design decisions**
Any non-obvious choices and why.

**Future swap path**
e.g. Replace `gemini_vision.py` with `yolov8_vision.py` when ready. Set `VISION_PROVIDER=yolov8`.

## Dependencies

| Field | Value |
|---|---|
| Depends on (task IDs) | T-004, T-005 |
| External libraries | `google-generativeai==0.8.3` |
| Environment variables | `GEMINI_API_KEY`, `VISION_PROVIDER=gemini` |

## Testing

**How to test (manual)**
Step-by-step: what to run, what to check.

**Automated tests**
Path to test file: `tests/test_a2_vision.py`

**Test data used**
e.g. `tests/fixtures/damaged/suitcase_01.jpg`

**Acceptance criteria**
Copy from task tracker — what must pass for merge approval.

## PR checklist

- [ ] Type hints on all new functions
- [ ] Docstrings on all public functions/classes
- [ ] `.env.example` updated with new vars
- [ ] No hardcoded provider names in `agents/`
- [ ] At least 1 test written
- [ ] `pytest` passes locally
- [ ] PR description filled out on GitHub
- [ ] Reviewer assigned

## Notes / blockers

| Field | Value |
|---|---|
| Known issues | |
| Blockers | |
| Links | |
