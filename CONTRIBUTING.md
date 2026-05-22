# Contributing Guide
### ABC Airline — Baggage Damage Claim AI
> **Team:** Anoushka · Aditya · Devam &nbsp;|&nbsp; **Sprint:** 3 Weeks · 15 Days &nbsp;|&nbsp; **Budget:** $0

---

## Quick Reference

| I want to... | Go to |
|---|---|
| Name a new branch | [§1 Branch Naming](#1-branch-naming) |
| Write a commit message | [§2 Commit Messages](#2-commit-message-format) |
| Start my day / task | [§3 Daily Workflow](#3-daily-workflow) |
| Open a Pull Request | [§4 Pull Request Rules](#4-pull-request-rules) |
| Merge my branch | [§5 Merge Workflow](#5-merge-workflow-step-by-step) |
| Check code rules | [§6 Code Standards](#6-code-standards) |
| Check merge gates | [§7 Merge Gates](#7-merge-gates) |

---

## 1. Branch Naming

Always branch off `develop` — **never** off `main`.
Use lowercase and hyphens only. No spaces, no underscores.

```
feature/T-006-vision-provider-gemini   ← new feature (include Task ID)
chore/repo-setup                       ← setup / config / tooling
integration/week2-full-pipeline        ← weekly integration task
docs/readme-and-demo                   ← documentation only
hotfix/fix-webhook-crash               ← emergency fix (Phase 2+ only)
```

---

## 2. Commit Message Format

```
<type>(<scope>): <short description>
```

> Max 72 characters. Present tense. Example: "add feature" not "added feature"

**Allowed types:**

```
feat      → new feature or functionality
fix       → bug fix
chore     → setup, config, tooling (no production code change)
docs      → documentation only
test      → adding or updating tests
refactor  → code restructure, no behaviour change
style     → formatting / linting, no logic change
```

**Good examples:**
```bash
feat(vision): add Gemini Flash damage analysis wrapper
fix(a4-decision): correct severity formula weight calculation
chore(repo): add CONTRIBUTING.md and CODEOWNERS
test(state): add ClaimState lane routing unit tests
docs(readme): add local setup walkthrough
```

**Never do this:**
```bash
fixed stuff        ❌
update             ❌
WIP                ❌
ok now it works    ❌
```

**End-of-day WIP push** — never leave uncommitted work overnight:
```bash
git add .
git commit -m "WIP: T-XXX brief description of where you left off"
git push origin feature/T-XXX-name
```

---

## 3. Daily Workflow

```bash
# ── Morning: sync first ──────────────────────────────
git checkout develop
git pull origin develop

# ── Create your task branch (first time only) ────────
git checkout -b feature/T-XXX-short-desc

# ── During the day: commit often ─────────────────────
git add .
git commit -m "feat(scope): description of what you did"

# ── End of day: push even if not done ────────────────
git add .
git commit -m "WIP: T-XXX description"
git push origin feature/T-XXX-short-desc
```

---

## 4. Pull Request Rules

**The golden rule:** every branch merges to `develop` via PR — no direct merges, ever.
Never open a PR targeting `main`.

**Before opening a PR:**
- [ ] Rebased on latest `develop`
- [ ] `pytest` passes locally
- [ ] `black backend/ && isort backend/` run
- [ ] At least 1 test written for your feature

**PR title format:**
```
[T-XXX] type(scope): short description

Example: [T-006] feat(vision): add Gemini Flash vision provider
```

**PR description — copy this template:**
```
## What changed
-

## How to test
1.
2.
3. Expected result:

## Screenshots
(attach if UI change)

## Task
T-XXX — Task Name
```

**Who reviews who:**
```
Devam     →  assign Anoushka
Anoushka  →  assign Aditya
Aditya    →  assign Devam
```

**After approval:** Squash and merge → Delete the feature branch → Notify team.

---

## 5. Merge Workflow (Step by Step)

Run these exact steps every time you are ready to merge:

```bash
# 1. Sync develop
git checkout develop
git pull origin develop

# 2. Rebase your branch on top of develop
git checkout feature/T-XXX-name
git rebase develop

# 3. If conflicts appear — for each conflicted file:
git add <conflicted-file>
git rebase --continue

# 4. Run tests — must be green before PR
pytest

# 5. Push your branch
git push origin feature/T-XXX-name --force-with-lease

# 6. Open PR on GitHub
#    Base branch : develop  ← important, not main
#    Title       : [T-XXX] type(scope): description
#    Assign reviewer

# 7. After approval on GitHub → Squash and merge → Delete branch

# 8. Clean up locally
git checkout develop
git pull origin develop
git branch -d feature/T-XXX-name

# 9. Notify the team
#    Post in group chat: "T-XXX merged to develop ✓"
```

---

## 6. Code Standards

### Python — Backend

```
Python version  →  3.11+
Formatter       →  Black + isort  (run before every PR)
Type hints      →  Required on ALL functions and return values
Docstrings      →  Google style, required on all public functions/classes
File size       →  Max 300 lines — split into modules if larger
Routes          →  async def throughout — no sync FastAPI routes
```

Run before every PR:
```bash
black backend/
isort backend/
pytest
```

### Environment Variables

```python
# ❌ NEVER hardcode keys
GEMINI_API_KEY = "AIzaSy..."

# ✅ ALWAYS read from environment
import os
api_key = os.getenv("GEMINI_API_KEY")
```

- All keys live in `.env` — gitignored, never committed
- All keys documented in `.env.example` with placeholder values
- `.env.example` is the **only** env file that gets committed

### Provider Pattern — Critical Rule

```python
# ❌ WRONG — never import a concrete provider inside agents/
from backend.vision_provider.gemini_vision import GeminiVisionProvider

# ✅ CORRECT — always use the abstract base class
from backend.vision_provider.base import VisionProvider
```

Agent code in `backend/agents/` must **never** reference Gemini, Claude, YOLOv8,
or any provider by name. Provider selection happens only in `config.py` via env vars.
This is what makes the architecture swappable.

### Testing Rules

```
Every new feature   →  at least 1 automated test (no exceptions)
External API calls  →  always mocked in tests, never hit real Gemini/Supabase
Test file location  →  tests/ mirroring the module structure
```

### React — Frontend

```
Version    →  React 18+
Bundler    →  Vite
Styling    →  Tailwind CSS
Formatter  →  Prettier
Forms      →  Use onClick / onChange handlers — never use <form> tags
```

---

## 7. Merge Gates

These are sprint checkpoints. **No one skips a gate.**

---

### 🔀 MG-W1 — End of Day 5

```
✅ T-001 through T-008 all merged to develop
✅ make run → POST /webhook → A1 replies correctly × 3 messages
✅ pytest → 0 failures
✅ Notify team: "Week 1 integration ✓ develop is green"
⛔ main is NOT touched here
```

---

### 🔀 MG-W2 — End of Day 10

```
✅ T-010 through T-015 all merged to develop
✅ Full pipeline: Lane 1 + Lane 2 + retry scenario all pass
✅ pytest → 0 failures
✅ Notify team: "Week 2 integration ✓ develop is green"
⛔ main is NOT touched here
```

---

### 🔀 MG-W3 — Day 14–15 (after demo rehearsal)

```
✅ All Week 3 tasks merged to develop
✅ Demo rehearsal passes on a second machine
✅ Then and only then — merge to main:

git checkout main
git merge develop --no-ff -m "chore: POC v1.0"
git tag v1.0-poc
git push origin main --tags

🏁 main = POC complete. Sprint done.
```

---

## 8. Branch Lifetime

```
feature/T-XXX-*       →  lives only during that task  →  DELETE after merge
integration/week-N-*  →  opens and merges same day    →  DELETE after merge
chore/* / docs/*      →  short-lived, max 1 day       →  DELETE after merge
develop               →  always open, shared branch   →  NEVER delete
main                  →  always open, prod-ready       →  NEVER delete
```

> Never reuse a deleted branch name. Always create a fresh branch per task.

---

## 9. What Syncs With What

```
feature  ──► develop    rebase before PR, then squash merge  (every task)
develop  ──► feature    not needed — rebase handles it
develop  ──► main       no-ff merge + tag only               (MG-W3 only)
main     ──► develop    NEVER
```

---

*Last updated: Week 1, Day 1 — Devam*