# chore/env-setup — Branch Documentation

## Branch metadata

| Field | Value |
|---|---|
| Branch name | `chore/env-setup` |
| Task ID | T-002 |
| Workstream | Project Setup |
| Author | Aditya |
| Reviewer | Devam |
| Start date | Day 1, Week 1 |
| Target merge date | Day 1, Week 1 |
| Actual merge date | Day 1, Week 1 |
| Status | Ready for Review |

## Objective

**What does this branch do?**
Sets up the local development environment for the full team — finalises `requirements.txt` with all pinned dependencies, documents every required environment variable in `.env.example`, updates the README with a complete local-run walkthrough, and fixes a LangGraph state compatibility bug in `orchestrator.py` discovered during environment verification.

**Why is it needed?**
Before any agent, API route, or LangGraph node can be built or tested, every team member needs a reproducible local environment. This branch is the shared foundation that T-004 (FastAPI base), T-005 (LangGraph skeleton), and every subsequent task depend on to run their code locally.

## Technical approach

**Files created**

| File | Purpose |
|---|---|
| `.env.example` | Documents every required environment variable with descriptions and placeholder values. Safe to commit — contains no secrets. |

**Files modified**

| File | What changed |
|---|---|
| `requirements.txt` | Upgraded `pydantic` to `>=2.11.4` and `pydantic-settings` to `>=2.9.1` for Python 3.14 pre-built wheel compatibility. Added `python-multipart==0.0.20` for FastAPI file upload support. Upgraded `Pillow` to `>=11.0.0` for cp314 wheel availability. |
| `README.md` | Filled in complete Quick Start section: venv creation, pip install, `.env` configuration, `make run`, health check, test run. Added explicit "No Docker needed" note. |
| `backend/graph/orchestrator.py` | Fixed `AddableValuesDict` bug — LangGraph's `ainvoke()` returns its own dict type, not `ClaimState`. Added conversion back to `ClaimState` immediately after `ainvoke` so all downstream dot-notation access works correctly across `webhook.py` and any future consumers. |

**Provider / abstraction used**
No AI provider directly invoked in this task. `.env.example` documents all provider switch variables: `LLM_PROVIDER`, `VISION_PROVIDER`, `OCR_PROVIDER`, `STORAGE_PROVIDER`, `DB_PROVIDER` — all set to `gemini` / `local` / `supabase` for POC.

**Key design decisions**

- **No Docker** — `Dockerfile` and `uvloop` removed from the project entirely. Local dev runs via `uvicorn` directly. Documented clearly in README to prevent confusion for new team members joining.
- **Python 3.14 compatibility** — original pinned versions (`pydantic==2.9.2`, `Pillow==11.0.0`) had no pre-built `cp314-win_amd64` wheels on PyPI, causing Rust/maturin source builds to fail on corporate networks with SSL restrictions. Unpinned to `>=` minimums so pip resolves to the latest cp314-compatible wheel automatically.
- **`python-multipart` added** — FastAPI requires this package for any `UploadFile` / `Form` endpoint. The `/upload` route in `webhook.py` (T-004 starter) uses `UploadFile`, so this is a hard runtime dependency. Was missing from original `requirements.txt`.
- **`orchestrator.py` ClaimState fix** — LangGraph `StateGraph.ainvoke()` always returns `AddableValuesDict`, not the typed state class passed in. Fix uses `ClaimState.__dataclass_fields__` to safely filter only known fields before reconstructing the dataclass, preventing `TypeError` on unexpected LangGraph internal keys.

**Future swap path**
All provider names (`gemini`, `supabase`, `local`) live only in `.env` and `config.py`. To swap any provider: change the relevant `*_PROVIDER` value in `.env` and implement the corresponding provider class (e.g. `claude_llm.py` for LLM). Zero agent code changes required — enforced by the ABC pattern.

## Dependencies

| Field | Value |
|---|---|
| Depends on (task IDs) | T-001 — repo must exist with `develop` branch and initial folder scaffold |
| External libraries | `fastapi==0.115.0`, `uvicorn==0.32.0`, `langgraph==0.2.55`, `google-generativeai==0.8.3`, `pydantic>=2.11.4`, `pydantic-settings>=2.9.1`, `python-multipart==0.0.20`, `Pillow>=11.0.0`, `supabase==2.10.0`, `pytest==8.3.3` |
| Environment variables | `GEMINI_API_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` (minimum required to start server) |

## Testing

**How to test (manual)**

```bash
# 1. Create and activate virtual environment
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS / Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Fill in: GEMINI_API_KEY, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY

# 4. Start the server
uvicorn backend.main:app --reload

# 5. Verify health endpoint
curl http://localhost:8000/health
# Expected: {"status": "ok"}

# 6. Verify Swagger UI
# Open http://127.0.0.1:8000/docs in browser — all endpoints visible

# 7. Smoke test full pipeline via Swagger /webhook
# POST /webhook with {"session_id": "test-001", "message": "hi", "image_paths": []}
# Expected: 200 response with a1_response, claim_id, routing_lane
```

**Automated tests**

```
tests/test_state.py    ← 7 unit tests for ClaimState, all pass out of the box
```

Run with:
```bash
pytest tests/test_state.py -v
```

**Test data used**
No fixture images needed for T-002. `test_state.py` uses in-memory `ClaimState` objects only.

**Acceptance criteria**
- `pip install -r requirements.txt` completes with no errors on Python 3.14
- `cp .env.example .env` → fill 3 keys → `uvicorn backend.main:app --reload` starts successfully
- `GET /health` returns `{"status": "ok"}`
- `POST /webhook` runs all 5 agents (A1→A2→A3→A4→A5) and returns a valid response with no `AttributeError`
- `pytest tests/test_state.py` → 7 tests pass
- Any team member can set up from README alone — no additional instructions needed
- No Docker required — confirmed and documented

## PR checklist

- [x] Type hints on all new functions
- [x] Docstrings on all public functions/classes
- [x] `.env.example` updated with new vars
- [x] No hardcoded provider names in `agents/`
- [x] At least 1 test written
- [x] `pytest` passes locally
- [ ] PR description filled out on GitHub
- [ ] Reviewer assigned

## Notes / blockers

| Field | Value |
|---|---|
| Known issues | Python 3.14 is newer than specified in the tracker (3.11+ required). All packages resolve correctly with `>=` version pins — no functional difference for POC. |
| Blockers | None — T-001 (Devam) merged and reviewed by Anoushka before this branch was opened. |
| Links | Gemini free tier: https://ai.google.dev/pricing · Supabase free tier: https://supabase.com/pricing · pydantic-core cp314 wheels: https://pypi.org/project/pydantic-core/ |
