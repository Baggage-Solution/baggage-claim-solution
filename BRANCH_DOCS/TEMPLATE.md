# BRANCH: [branch-name]
<!-- Copy this file → BRANCH_DOCS/WEEK{N}_DOCS/{T-XXX-branch-name}.md -->
<!-- Follow naming: T-001-chore-repo-setup.md, T-010-feature-agent-a2-vision.md etc. -->

---

## Branch Metadata

```
Branch Name   →  feature/short-description   (or chore/ fix/ integration/ docs/)
Task ID       →  T-XXX
Workstream    →  [Project Setup / Backend / LangGraph / Vision AI / LLM / Frontend / Integration / Docs]
Author        →  [Anoushka Vyas / Aditya Bhavsar / Devam Dixit]
Reviewer      →  [Name]
Start Date    →  Day X, Week Y
Target Merge  →  Day X, Week Y
Actual Merge  →  Day X, Week Y
Status        →  [Not Started / In Progress / Ready for Review / Merged]
```

---

## Objective

**What does this branch do?**
1–3 sentence summary of what was implemented.

**Why is it needed?**
How does it fit the overall architecture? What breaks or stays blocked without it?

---

## Local Setup

```bash
source venv/Scripts/activate      # Git Bash / Windows
# source venv/bin/activate        # Mac / Linux

pip install -r requirements.txt
pytest tests/test_XXX.py -v
```

---

## Technical Approach

**Files Modified:**

| File | What changed |
|---|---|
| `backend/agents/aX_xxx.py` | Replaced TODO stub with full implementation. Added ... |

**Files Created:**

| File | Purpose |
|---|---|
| `tests/test_aX_xxx.py` | N unit tests — describe coverage |

**Files Already Complete (No Changes Needed):**

| File | What was already there |
|---|---|
| `backend/xxx/base.py` | ABC / interface — complete from T-00X |

**Provider / Abstraction Used:**

```
Implements:  [XxxProvider ABC / BaseAgent / etc.]
Via:         [Gemini Flash / Supabase / local storage / etc.]
Injected by: provide_xxx() in dependencies.py
Agent imports: XxxProvider only — never the concrete class directly
```

**Key Design Decisions:**

```
1. DECISION NAME
   Explanation of the non-obvious choice and why it was made.

2. DECISION NAME
   Explanation.
```

**Future Swap Path:**

```
To swap [current provider] for [alternative]:
1. Create backend/xxx_provider/alternative.py
2. Implement the ABC
3. Set XXX_PROVIDER=alternative in .env
4. Zero other code changes needed.
```

---

## Dependencies

```
Depends On          →  T-XXX (reason why)
External Libraries  →  library==version (already in requirements.txt / new addition)
Environment Vars    →  VAR_NAME (existing / new — update .env.example if new)
```

---

## Testing

**Run tests:**

```bash
pytest tests/test_XXX.py -v
# Expected: N passed

pytest tests/ -v
# Expected: N passed total
```

**Manual Smoke Test:**

```bash
uvicorn backend.main:app --reload --port 8000

curl -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -d '{"session_id": "smoke-001", "message": "..."}'
# Expected: ...
```

**Test Data Used:**
`tests/fixtures/...` — describe what fixtures are needed.

**Acceptance Criteria:**

```
✅ Criterion 1
✅ Criterion 2
✅ pytest → N passed, 0 failures
✅ black + isort clean
```

---

## PR Checklist

```
[x] PR title includes Task ID — [T-XXX] feat/fix/chore/docs: ...
[x] PR description filled out on GitHub
[x] Base branch set to develop (not main)
[x] Reviewer assigned
[x] Squash merged to develop
[x] Feature branch deleted after merge

[x] Type hints on all new/modified functions
[x] Google-style docstrings on all public functions
[ ] .env.example updated (only if new env vars added)
[x] No hardcoded provider names in agents/ or orchestrator
[x] No hardcoded API keys
[x] pytest tests/ → N passed, 0 failures
[x] black backend/ tests/ → clean
[x] isort backend/ tests/ → clean
[x] Branch doc committed to BRANCH_DOCS/ before merge
```

---

## Notes / Blockers

```
Known Issues  →  [None / description]
Scope Note    →  What is intentionally deferred to a future task.
Blockers      →  [None / description]
Links         →  Relevant docs, library links, architecture references
```

---

*Branch opened: Day X, Week Y — [Author]*
*Merged to develop: Day X, Week Y*