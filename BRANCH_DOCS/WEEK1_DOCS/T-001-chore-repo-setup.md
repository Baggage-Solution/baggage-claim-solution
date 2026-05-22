# BRANCH: chore/repo-setup

---

## Branch Metadata

```
Branch Name   →  chore/repo-setup
Task ID       →  T-001
Workstream    →  Project Setup
Author        →  Devam
Reviewer      →  Anoushka
Start Date    →  Day 1, Week 1
Target Merge  →  Day 1, Week 1
Actual Merge  →  Day 1, Week 1
Status        →  Merged
```

---

## Objective

**What does this branch do?**
Initializes the GitHub repository, establishes the two-branch strategy (main + develop),
enforces branch protection rules, and provides team-wide contribution guidelines via
CONTRIBUTING.md and CODEOWNERS.

**Why is it needed?**
T-001 is the blocker for the entire sprint. No other task can begin until the repo is
live, develop exists, and branch protection is active. This sets the engineering
discipline baseline for all 22 remaining tasks.

---

## Technical Approach

**Files Created:**
```
CONTRIBUTING.md          →  Full Git workflow, branch naming, commit standards,
                             code standards, and merge gate calendar
.github/CODEOWNERS       →  Auto-assigns reviewers by directory ownership
```

**Files Modified:**
```
None — all other files came from the starter kit (committed as-is)
```

**Provider / Abstraction Used:**
```
N/A — infrastructure and configuration task only
```

**Key Design Decisions:**
```
1. Squash merge strategy chosen for develop — keeps history readable
2. CODEOWNERS scoped by directory to match task ownership from tracker
   - /backend/          → Devam
   - /frontend/         → Anoushka
   - /tests/            → Aditya
   - /backend/config.py → All three (critical shared file)
3. 1 approval required — appropriate for a 3-person POC team
4. Repo made public to enable branch protection on free GitHub org plan
```

**Future Swap Path:**
```
- Add required CI status checks to branch protection after T-020 test
  suite is merged (Week 3)
- Require 2 approvals before main merge in Phase 2
- Move repo back to private once team upgrades to GitHub Team plan
```

---

## Dependencies

```
Depends On          →  None — this is the first task
External Libraries  →  None
Environment Vars    →  None
```

---

## Testing

**How to Test (Manual):**
```
1. Try: git push origin main directly from local
   Expected: rejected by GitHub (branch protection working)

2. Open any PR to develop
   Expected: CODEOWNERS auto-assigns correct reviewer based on files changed

3. ls at repo root
   Expected: CONTRIBUTING.md present

4. ls .github/
   Expected: CODEOWNERS present with correct GitHub usernames
```

**Automated Tests:** N/A — infrastructure task

**Test Data:** N/A

**Acceptance Criteria:**
```
✅ main and develop branches visible and protected on GitHub
✅ Direct push to main is blocked
✅ CONTRIBUTING.md committed at repo root
✅ .github/CODEOWNERS committed with correct usernames
```

---

## PR Checklist

```
[x] PR title includes Task ID — [T-001] chore(repo): ...
[x] PR description filled out on GitHub
[x] Base branch set to develop (not main)
[x] Reviewer assigned — Anoushka
[x] Squash merged to develop
[x] Feature branch deleted after merge
[ ] N/A — Type hints (no code written)
[ ] N/A — Docstrings (no code written)
[ ] N/A — Tests (infrastructure task)
[ ] N/A — pytest (infrastructure task)
```

---

## Notes / Blockers

```
Known Issues  →  Branch protection requires public repo on free GitHub org plan.
                 Repo is currently public — acceptable for POC with no secrets in code.
                 All API keys are in .env which is gitignored.

Blockers      →  None — completed on Day 1

Links         →  GitHub Branch Protection docs:
                 https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches

                 CODEOWNERS syntax reference:
                 https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners
```