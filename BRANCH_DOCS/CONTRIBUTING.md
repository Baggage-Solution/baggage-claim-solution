# Contributing Guide
### ABC Airline — Baggage Damage Claim AI · AWS Production Phase
> **Team:** Anoushka · Aditya · Devam &nbsp;|&nbsp; **Sprint:** 4 Weeks · 20 Days &nbsp;|&nbsp; **Region:** us-east-1 &nbsp;|&nbsp; **Channel:** Meta Cloud API via N8N

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
| Check cloud / channel agnosticism | [§7 Agnosticism Rules](#7-agnosticism-rules) |
| Check merge gates | [§8 Merge Gates](#8-merge-gates) |
| Reference POC phase rules | [§9 POC Phase (archived)](#9-poc-phase-archived) |

---

## 1. Branch Naming

In the AWS phase, **always branch off `develop-aws`** — never off `develop`, never off `main`.
Use lowercase and hyphens only. No spaces, no underscores.

```
feature/<short-desc>            ← new feature
  e.g.  feature/bedrock-llm-vision-ocr
        feature/s3-storage
        feature/sqs-queue-provider
        feature/channel-provider-whatsapp

chore/<desc>                    ← setup / config / infra / tooling (no production logic change)
  e.g.  chore/aws-repo-bootstrap
        chore/github-actions-deploy
        chore/secrets-bootstrap
        chore/n8n-ec2-install

integration/week<N>-<desc>      ← weekly integration / smoke test
  e.g.  integration/week1-aws-ready
        integration/week2-aws-smoke
        integration/week3-whatsapp-live

docs/<desc>                     ← documentation only
  e.g.  docs/runbook-on-call

hotfix/<desc>                   ← emergency fix to develop-aws
  e.g.  hotfix/webhook-hmac-bug
```

**Branch protection on `develop-aws`, `develop`, and `main`** — these can only be updated via PR. No direct pushes.

---

## 2. Commit Message Format

```
<type>(<scope>): <short description>
```

> Max 72 characters. Present tense. Example: "add feature" not "added feature".

**Allowed types:**

```
feat      → new feature or functionality
fix       → bug fix
chore     → setup, config, tooling (no production code change)
docs      → documentation only
test      → adding or updating tests
refactor  → code restructure, no behaviour change
style     → formatting / linting, no logic change
perf      → performance improvement
build     → build system / dependencies
ci        → CI/CD pipeline changes
```

**Good examples (AWS phase):**

```bash
feat(bedrock): add Claude Sonnet 4 vision provider
feat(channel): implement WhatsApp ChannelProvider via N8N
fix(channel-whatsapp): correct HMAC validation against raw body
chore(repo): bootstrap AWS production phase scaffolding
chore(secrets): populate prod secret in Secrets Manager
ci(deploy): pin aws-actions versions for reproducible builds
test(sqs): add moto-mocked SQSQueueProvider integration tests
docs(runbook): add Bedrock throttle response playbook
```

**Never do this:**

```bash
fixed stuff        ❌
update             ❌
WIP                ❌
ok now it works    ❌
final v2           ❌
```

**End-of-day WIP push** — never leave uncommitted work overnight:

```bash
git add .
git commit -m "WIP: P-XXX brief description of where you left off"
git push origin feature/<your-branch>
```

---

## 3. Daily Workflow

```bash
# ── Morning: sync first ──────────────────────────────
git checkout develop-aws
git pull origin develop-aws

# ── Create your task branch (first time only) ────────
git checkout -b feature/<short-desc>          # or chore/ docs/ etc.

# ── During the day: commit often ─────────────────────
git add .
git commit -m "feat(scope): description of what you did"

# ── End of day: push even if not done ────────────────
git add .
git commit -m "WIP: P-XXX description"
git push origin feature/<short-desc>
```

---

## 4. Pull Request Rules

**The golden rule:** every branch merges to `develop-aws` via PR — no direct merges, ever.
Never open a PR targeting `develop` or `main` mid-sprint. Those only update at MG-W4.

**Before opening a PR:**

- [ ] Rebased on latest `develop-aws`
- [ ] `pytest` passes locally (both `PROVIDER=local` and `PROVIDER=aws` variants)
- [ ] `black backend/ tests/ && isort backend/ tests/` run
- [ ] Cloud-agnostic grep returns empty (see §7)
- [ ] Channel-agnostic grep returns empty (see §7)
- [ ] At least 1 test written for your feature
- [ ] Branch doc drafted at `BRANCH_DOCS/AWS_PHASE/<branch-name>.md`

**PR title format:**

```
[P-XXX] type(scope): short description

Example: [P-003] feat(bedrock): add Claude Sonnet 4 vision provider
```

**PR description template:**

```markdown
## What changed
-

## How to test
1.
2.
3. Expected:

## Cloud-agnostic check
```bash
grep -rn "boto3\|aws_\|import anthropic\|import google\|supabase" \
  backend/agents/ backend/graph/ backend/api/ backend/core/
```
Result: (paste output — must be empty)

## Channel-agnostic check
```bash
grep -rni "whatsapp\|meta\|telegram\|twilio\|sms" \
  backend/agents/ backend/graph/ backend/api/ backend/core/
```
Result: (paste output — must be empty)

## Task
P-XXX — Task Name
```

**Who reviews who:**

```
Devam     →  assign Anoushka
Anoushka  →  assign Aditya
Aditya    →  assign Devam
```

For security-sensitive changes (Secrets, IAM, HMAC verification) → **2 reviewers required**.

**After approval:** Squash and merge → Delete the feature branch (local + remote) → Notify team in group chat: "P-XXX merged to develop-aws ✓".

---

## 5. Merge Workflow (Step by Step)

Run these exact steps every time you are ready to merge:

```bash
# 1. Sync develop-aws
git checkout develop-aws
git pull origin develop-aws

# 2. Rebase your branch on top of develop-aws
git checkout feature/<your-branch>
git rebase develop-aws

# 3. If conflicts appear — for each conflicted file:
git add <conflicted-file>
git rebase --continue

# 4. Run tests — must be green before PR
pytest

# 5. Run agnosticism greps — must be empty
grep -rn "boto3\|aws_\|import anthropic\|import google\|supabase" \
  backend/agents/ backend/graph/ backend/api/ backend/core/
grep -rni "whatsapp\|meta\|telegram\|twilio\|sms" \
  backend/agents/ backend/graph/ backend/api/ backend/core/

# 6. Push your branch
git push origin feature/<your-branch> --force-with-lease

# 7. Open PR on GitHub
#    Base branch : develop-aws  ← important
#    Title       : [P-XXX] type(scope): description
#    Assign reviewer

# 8. After approval + green CI on GitHub → Squash and merge → Delete branch

# 9. Clean up locally
git checkout develop-aws
git pull origin develop-aws
git branch -d feature/<your-branch>
git push origin --delete feature/<your-branch>

# 10. Notify the team
#     Post in group chat: "P-XXX merged to develop-aws ✓"

# 11. Update AWS_Phase_Tracker.xlsx
#     Status=Done · Actual Hours · Completion Date · PR Link
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
Logging         →  logging.getLogger(__name__) — NEVER print() in committed code
                   All log lines MUST include request_id from RequestContextMiddleware
Async           →  All I/O paths are async. Wrap sync SDK calls (boto3) in asyncio.to_thread
```

### Frontend — React

```
Formatter       →  Prettier (default config + .prettierrc if needed)
State           →  React hooks. Avoid Redux for this phase.
API calls       →  fetch + AbortController (no axios)
Env vars        →  All prefixed VITE_. Documented in frontend/.env.example
```

### Environment & Secrets

```
NO hardcoded API keys, ARNs, region, bucket names, phone numbers, secret values.
NO secrets in git. EVER.
.env.example is the source of truth for what env vars exist.

Production secrets live in AWS Secrets Manager: baggage-claim/<env>
SecretsProvider loads them once at startup → cached in Settings.

Local dev → .env file (gitignored) or environment variables
Production → Secrets Manager via SECRETS_PROVIDER=aws_sm
```

### Provider Pattern (CRITICAL — see §7)

```
All AI, storage, queue, secrets, channel integrations follow:

  1. ABC in backend/<thing>_provider/base.py
  2. Concrete impls in backend/<thing>_provider/<name>.py
  3. Factory branch in backend/dependencies.py
  4. Selection via <THING>_PROVIDER env var (e.g. LLM_PROVIDER=bedrock)
  5. Agents and orchestrator depend ONLY on the ABC — never the concrete class
```

### Tests

```
Framework       →  pytest
AWS mocking     →  moto for S3, SQS, Secrets Manager
                   unittest.mock for Bedrock (moto does not support it)
NEVER call real AWS in CI. NEVER call real Meta in CI.
New provider   →  new test file with at least 1 happy path + 1 failure path
Coverage goal  →  ≥ 75% on new code (not enforced via CI yet but tracked)
```

### Infrastructure

```
Naming          →  <project>-<resource>-<env>
                   abc-baggage-claims-prod (S3)
                   baggage-claim-cluster (ECS)
                   baggage-claim/prod (Secrets Manager)
Tagging         →  Required on every billable AWS resource:
                   Project=baggage-claim · Env=prod|dev · Owner=emerging-markets
Local Docker    →  🚫 Never docker build on office laptops.
                   GitHub Actions runner is the ONLY image builder.
IaC             →  Phase 1 keeps configs in deploy/ folder (task defs, GH workflow,
                   N8N workflow JSON, CloudWatch dashboard JSON). Phase 2 = Terraform.
Region          →  ONLY in config.py / Secrets Manager. Never in agent or business-logic files.
```

---

## 7. Agnosticism Rules

The whole point of the AWS phase architecture is that we can swap any provider in one config change. Three axes of agnosticism are enforced:

### Cloud-Agnostic

```
boto3 imports are ALLOWED in:
  backend/llm_provider/bedrock_*.py
  backend/vision_provider/bedrock_*.py
  backend/ocr_provider/bedrock_*.py
  backend/storage_provider/s3_*.py
  backend/queue_provider/sqs_*.py
  backend/secrets_provider/aws_*.py

boto3 imports are FORBIDDEN in:
  backend/agents/
  backend/graph/
  backend/api/
  backend/core/

CI check (runs on every PR):
  grep -rn "boto3\|aws_\|import anthropic\|import google\|supabase" \
    backend/agents/ backend/graph/ backend/api/ backend/core/
  → must return ZERO results
```

### Channel-Agnostic

```
"whatsapp", "meta", "telegram", "twilio", "sms" are ALLOWED in:
  backend/channel_provider/whatsapp_channel.py (and future siblings)
  deploy/n8n/*.json

These are FORBIDDEN in:
  backend/agents/
  backend/graph/
  backend/api/
  backend/core/

CI check:
  grep -rni "whatsapp\|meta\|telegram\|twilio\|sms" \
    backend/agents/ backend/graph/ backend/api/ backend/core/
  → must return ZERO results
```

### Model-Agnostic

```
Specific model IDs (e.g. "anthropic.claude-sonnet-4", "gemini-2.5-flash") live ONLY in:
  config.py / .env / Secrets Manager

Never hardcoded in:
  agents/  graph/  api/  core/  any provider impl

Provider impls read model ID from Settings — they never embed it literally.
```

**If a swap is harder than (a) write a new provider impl and (b) flip one env var, the abstraction has been violated.**

---

## 8. Merge Gates

The AWS phase has 4 hard gates. No work crosses a gate until criteria are met.

```
MG-W1  →  End of Day 5   →  All P-001–P-011 merged to develop-aws
                            pytest green with all PROVIDER=aws env vars
                            ⛔ develop is NOT touched

MG-W2  →  End of Day 10  →  All P-013–P-019 done · P-020 cloud smoke green
                            ECS api + worker healthy · N8N HTTPS reachable
                            Tag develop-aws: w2-aws-green

MG-W3  →  End of Day 15  →  P-021–P-024 merged · P-025 e2e real WhatsApp passes
                            Tag develop-aws: w3-whatsapp-green

MG-W4  →  Day 20 (after 24h watch) →
                            All Week 4 done · demo signed off · 24h incident-free
                            git checkout develop && git merge develop-aws --no-ff
                            git checkout main && git merge develop --no-ff
                            git tag v1.0-aws && git push origin main --tags
                            ✅ Sprint complete
```

Between gates, communication via the mini-syncs in the tracker (MS-1 through MS-7).

---

## 9. POC Phase (Archived)

The POC phase (T-001–T-023, 3 weeks) was completed prior to this phase. Its artifacts remain in:

```
BRANCH_DOCS/WEEK1_DOCS/        ← T-001–T-009 docs (preserved)
BRANCH_DOCS/WEEK2_DOCS/        ← T-010–T-018 docs (preserved)
BRANCH_DOCS/WEEK3_DOCS/        ← T-019–T-023 docs (preserved)
BRANCH_DOCS/TEMPLATE.md        ← POC template (preserved)
GIT_WORKFLOW.md                ← POC workflow doc (preserved for reference)
```

POC rules — branches off `develop`, T-XXX task IDs, 3-week sprint, $0 budget — applied **only** during the POC phase. The AWS phase rules in §1–§8 supersede them entirely.

The POC's `develop` branch is preserved as the merge-target for the AWS phase at MG-W4.

---

*Last updated: AWS Production Phase Day 1*
