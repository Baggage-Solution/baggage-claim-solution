# BRANCH: chore/aws-repo-bootstrap

---

## Branch Metadata

```
Branch Name        →  chore/aws-repo-bootstrap
Task ID            →  P-001
Workstream         →  Project Setup
Author             →  Devam Dixit
Reviewer           →  Anoushka Vyas
Start Date         →  Day 1, Week 1
Target Merge Date  →  Day 1, Week 1
Actual Merge Date  →  [Fill on completion]
Status             →  In Progress
```

---

## Objective

**What does this branch do?**
Bootstraps the AWS production phase by (a) creating the long-lived `develop-aws` integration branch off `develop`, (b) scaffolding `BRANCH_DOCS/AWS_PHASE/` with an AWS-extended template, (c) replacing the POC-era `CONTRIBUTING.md` with AWS-phase rules (POC rules preserved as an archived section), and (d) introducing `AGENTS.md` + `CLAUDE.md` so AI coding agents (Claude Code, Codex CLI) inherit the right operating context for every session in this phase.

**Why is it needed?**
This task is the hard blocker for the entire AWS phase. Without `develop-aws`, no other feature branch has a base to fork from. Without the updated `CONTRIBUTING.md` and the new branch-doc template, the team can't enforce the cloud/channel/model agnosticism rules that every subsequent task depends on. Without `AGENTS.md` + `CLAUDE.md`, AI sessions will reach for the old (POC) conventions and produce non-compliant code.

---

## Local Setup

No backend/frontend code changes in this branch — pure scaffolding. Verification is filesystem-level:

```bash
git checkout chore/aws-repo-bootstrap

ls BRANCH_DOCS/AWS_PHASE/
# Expected: TEMPLATE.md  chore-aws-repo-bootstrap.md

cat CONTRIBUTING.md | head -3
# Expected first line: # Contributing Guide
# Expected third line: > **Team:** Anoushka · Aditya · Devam ... | **Sprint:** 4 Weeks · 20 Days | ...

ls AGENTS.md CLAUDE.md
# Both must exist at repo root

# Existing POC artifacts MUST be untouched:
ls BRANCH_DOCS/TEMPLATE.md BRANCH_DOCS/WEEK1_DOCS/ BRANCH_DOCS/WEEK2_DOCS/ BRANCH_DOCS/WEEK3_DOCS/ GIT_WORKFLOW.md
```

Optional — confirm no Python code changed:

```bash
git diff develop..chore/aws-repo-bootstrap -- 'backend/*.py' 'tests/*.py' 'frontend/**'
# Expected: empty diff
```

---

## Technical Approach

**Files Created:**

| File | Purpose |
|---|---|
| `BRANCH_DOCS/AWS_PHASE/TEMPLATE.md` | AWS-phase branch-doc template (adds Cloud-Agnostic Boundary, Channel-Agnostic Boundary, AWS Resources Required, IAM Permissions Required, Secrets Manager Keys, Mocking Strategy fields) |
| `BRANCH_DOCS/AWS_PHASE/chore-aws-repo-bootstrap.md` | This file — the branch doc for P-001 |
| `AGENTS.md` | Operating manual for AI coding agents — pillars, repo layout, provider pattern, forbidden imports, common tasks, secrets handling, observability |
| `CLAUDE.md` | Claude Code session pointer that defers to AGENTS.md plus a few Claude-specific notes (Edit/str_replace usage, the 2 grep checks) |

**Files Modified:**

| File | What changed |
|---|---|
| `CONTRIBUTING.md` | Rewritten for AWS phase: header now reads 4 weeks / 20 days / AWS Production Phase. §1 branch naming targets `develop-aws` with `P-XXX` task IDs. §6 code standards extended with cloud-agnostic + channel-agnostic + AWS SDK boundary rules. §7 new section: Agnosticism Rules (the three pillars + grep checks). §8 merge gates updated to MG-W1..MG-W4. §9 preserves POC rules as an archived reference. |

**Files Already Complete (No Changes Needed):**

| File | What was already there |
|---|---|
| `BRANCH_DOCS/TEMPLATE.md` | POC template — preserved for historical reference |
| `BRANCH_DOCS/WEEK1_DOCS/` … `WEEK3_DOCS/` | POC branch docs (T-001..T-023) — preserved |
| `GIT_WORKFLOW.md` | POC workflow doc — preserved for reference |
| `backend/`, `frontend/`, `tests/`, `docs/`, `requirements.txt`, `pytest.ini`, `Makefile`, `README.md` | Untouched in this branch |

**Provider / Abstraction Used:**

```
Implements:    N/A — pure scaffolding, no code or providers introduced
Via:           N/A
Injected by:   N/A
Agent imports: N/A
```

**Key Design Decisions:**

```
1. TWO-BRANCH BOOTSTRAP (develop-aws + chore/aws-repo-bootstrap)
   develop-aws is the long-lived integration branch (created once, lives until MG-W4).
   chore/aws-repo-bootstrap is the short-lived feature branch carrying the actual files.
   This honours the §4 rule that every change reaches develop-aws via PR — including the
   first one — instead of a special-case direct push.

2. PRESERVE POC ARTIFACTS, DO NOT DELETE
   BRANCH_DOCS/WEEK1_DOCS through WEEK3_DOCS, the POC TEMPLATE.md, and GIT_WORKFLOW.md are
   kept verbatim. They document a completed phase; the AWS phase supersedes their rules but
   does not invalidate the history. The archived §9 in CONTRIBUTING.md points to them.

3. AGENTS.md AND CLAUDE.md AS SIBLINGS, NOT SYMLINKS
   Symlinks are unreliable across Windows/Git Bash, which is the team's primary environment.
   CLAUDE.md is a short pointer file that mirrors the core rules from AGENTS.md and includes
   Claude-Code-specific operational notes. AGENTS.md is the canonical file.

4. AWS-PHASE TEMPLATE REPLACES, NOT EXTENDS, THE POC TEMPLATE
   The new TEMPLATE.md adds Cloud-Agnostic Boundary, Channel-Agnostic Boundary,
   AWS Resources Required, IAM Permissions Required, Secrets Manager Keys, and
   Mocking Strategy fields. Trying to bolt these on to the POC template would be messier
   than a clean parallel template in BRANCH_DOCS/AWS_PHASE/.

5. CONTRIBUTING.md REWRITE OVER PATCH
   The original CONTRIBUTING.md was POC-shaped (3 weeks, $0 budget, T-XXX, develop). A
   patch-style update would leave POC fragments interleaved with AWS-phase rules. A
   rewrite with POC content archived in §9 keeps the active guide single-purpose.
```

**Future Swap Path:**

```
This branch introduces no provider — no swap path applies.
The future-swap-path field is mandatory in feature branches that introduce providers
(see TEMPLATE.md).
```

---

## Cloud-Agnostic Boundary

```
boto3 imports allowed in:    backend/{queue,secrets,storage,llm,vision,ocr}_provider/*aws*.py
                              backend/{...}_provider/*bedrock*.py
                              backend/{...}_provider/*s3*.py
                              backend/{...}_provider/*sqs*.py

boto3 imports FORBIDDEN in:  backend/agents/   backend/graph/   backend/api/   backend/core/

Grep check:
grep -rn "boto3\|aws_\|import anthropic\|import google\|supabase" \
  backend/agents/ backend/graph/ backend/api/ backend/core/
```

Result of the grep on this branch: **empty (no Python code modified in this branch).**

---

## Channel-Agnostic Boundary

```
WhatsApp/Meta references allowed in:    backend/channel_provider/whatsapp_channel.py
                                         deploy/n8n/*.json

WhatsApp/Meta refs FORBIDDEN in:        backend/agents/  backend/graph/  backend/api/  backend/core/

Grep check:
grep -rni "whatsapp\|meta\|telegram\|twilio\|sms" \
  backend/agents/ backend/graph/ backend/api/ backend/core/
```

Result of the grep on this branch: **empty (no Python code modified in this branch).**

---

## Dependencies

```
Depends On (Task IDs)      →  None (P-001 is the root of the AWS phase dependency graph)
External Libraries         →  None added
Environment Variables      →  None added
Secrets Manager Keys       →  None added
AWS Resources Required     →  None — this task is repo-local scaffolding
IAM Permissions Required   →  None
```

---

## Testing

**Run tests:**

```bash
pytest tests/ -v
# Expected: same N passed as on develop — no new tests, no test changes
```

**Mocking Strategy:**

```
N/A — no code under test in this branch.
```

**Manual Smoke Test:**

```bash
# 1. Filesystem verification
ls BRANCH_DOCS/AWS_PHASE/TEMPLATE.md
ls BRANCH_DOCS/AWS_PHASE/chore-aws-repo-bootstrap.md
ls AGENTS.md CLAUDE.md
head -3 CONTRIBUTING.md

# 2. POC artifacts intact
ls BRANCH_DOCS/TEMPLATE.md
ls BRANCH_DOCS/WEEK1_DOCS/ BRANCH_DOCS/WEEK2_DOCS/ BRANCH_DOCS/WEEK3_DOCS/
ls GIT_WORKFLOW.md

# 3. No code changes
git diff develop..HEAD -- 'backend/' 'frontend/' 'tests/'
# Expected: empty
```

**Test Data Used:**
N/A.

**Acceptance Criteria:**

```
✅ develop-aws branch exists locally and on origin
✅ develop-aws branch protection enabled on GitHub (PR required, 1 approval, CI green)
✅ BRANCH_DOCS/AWS_PHASE/ folder exists with TEMPLATE.md (AWS-phase variant)
✅ CONTRIBUTING.md reflects 4-week / AWS / develop-aws / P-XXX / Agnosticism Rules
✅ AGENTS.md present at repo root with the 3 pillars and provider pattern
✅ CLAUDE.md present at repo root, defers to AGENTS.md
✅ POC artifacts (TEMPLATE.md, WEEK1-3_DOCS, GIT_WORKFLOW.md) are untouched
✅ No Python or frontend code modified in this branch
✅ pytest unchanged (no regression)
✅ Other team members can `git checkout develop-aws` and start their Batch 2 branches
```

---

## PR Checklist

```
[x] PR title — [P-001] chore(repo): bootstrap AWS production phase scaffolding
[x] PR description filled out on GitHub (What changed / How to test / Task)
[x] Base branch set to develop-aws
[x] Reviewer assigned — Anoushka
[ ] GitHub Actions green
[ ] Squash merged to develop-aws
[ ] Feature branch deleted after merge (local + remote)
[ ] Tracker updated: Status=Done, Actual Hours, Completion Date, PR Link

[x] Type hints on all new/modified functions   (N/A — no code)
[x] Google-style docstrings on all public functions   (N/A — no code)
[x] .env.example updated (only if new env vars added)   (N/A — no new env vars)
[x] config.py updated (only if new Settings fields added)   (N/A — no new fields)
[x] dependencies.py updated (only if new factory branch added)   (N/A)
[x] No hardcoded provider names / regions / bucket names / channel names in agents/, graph/, api/, core/
[x] No hardcoded API keys or ARNs anywhere
[x] pytest unchanged   (no test churn)
[x] black backend/ tests/ → clean   (no Python changed)
[x] isort backend/ tests/ → clean   (no Python changed)
[x] Branch doc committed at BRANCH_DOCS/AWS_PHASE/chore-aws-repo-bootstrap.md
[x] Cloud-agnostic grep — empty
[x] Channel-agnostic grep — empty
[x] Secrets never logged or committed
```

---

## Notes / Blockers

```
Known Issues    →  None
Scope Note      →  This task does NOT add any Python code. New ABCs (QueueProvider,
                   SecretsProvider, ChannelProvider) are introduced in P-002. Bedrock /
                   S3 / SQS / Secrets Manager provider implementations come in
                   P-003..P-006. Dockerfile in P-010. GH Actions deploy in P-014.

Blockers        →  None — this is the dependency root of the AWS phase.
                   MS-1 mini-sync fires as soon as this PR is merged: the whole team
                   pulls develop-aws and opens their Batch 2 branches in parallel.

Links           →  AWS_Phase_Tracker.xlsx (row P-001 — Workstream Overview + Task Tracker)
                   AWS_Deployment_Plan.docx (sections 1–10 — the architectural backdrop)
                   BRANCH_DOCS/AWS_PHASE/TEMPLATE.md (the new template this doc follows)
                   CONTRIBUTING.md §1, §6, §7, §8 (the rules this scaffolding enforces)
                   AGENTS.md §2 (the three agnosticism pillars)
```

---

*Branch opened: Day 1, Week 1 — Devam Dixit*
*Merged to develop-aws: [Day 1, Week 1 — fill on merge]*
