# BRANCH: [branch-name]
<!-- Copy this file → BRANCH_DOCS/AWS_PHASE/{branch-name}.md -->
<!-- Naming: chore-aws-repo-bootstrap.md, feature-bedrock-llm-vision-ocr.md, feature-sqs-queue-provider.md etc. -->
<!-- Do NOT include the P-XXX in the filename — that's in the metadata block below. -->

---

## Branch Metadata

```
Branch Name        →  feature/short-description   (or chore/ docs/ integration/ hotfix/)
Task ID            →  P-XXX
Workstream         →  [Project Setup / Abstractions / AWS AI Providers / AWS Platform / Messaging Infra /
                       Application Refactor / Build & Containerise / Test Suite / CI/CD /
                       Admin Coordination / Secrets Population / First Deploy / N8N Provisioning /
                       Network & VPC / WhatsApp Onboarding / N8N Workflow / Media Pipeline /
                       Reply Channel / Observability / Auto-scaling / Load Testing /
                       Cost Hardening / Documentation / Demo / Go-Live]
Author             →  [Anoushka Vyas / Aditya Bhavsar / Devam Dixit]
Reviewer           →  [Name]
Start Date         →  Day X, Week Y
Target Merge Date  →  Day X, Week Y
Actual Merge Date  →  [Fill on completion]
Status             →  [Not Started / In Progress / Ready for Review / Merged]
```

---

## Objective

**What does this branch do?**
1–3 sentence summary of what was implemented.

**Why is it needed?**
How does it fit the cloud-agnostic / channel-agnostic architecture? What breaks or stays blocked without it?

---

## Local Setup

```bash
source venv/Scripts/activate      # Git Bash / Windows
# source venv/bin/activate        # Mac / Linux

pip install -r requirements.txt
pytest tests/test_XXX.py -v
```

For cloud-targeting changes, run with AWS provider env vars set:
```bash
export LLM_PROVIDER=bedrock VISION_PROVIDER=bedrock OCR_PROVIDER=bedrock
export STORAGE_PROVIDER=s3 QUEUE_PROVIDER=sqs SECRETS_PROVIDER=aws_sm
pytest tests/ -v        # moto + mock.patch handle the AWS calls — no real AWS hit
```

---

## Technical Approach

**Files Created:**

| File | Purpose |
|---|---|
| `backend/xxx_provider/yyy.py` | Implements XxxProvider ABC via YYY service |
| `tests/test_yyy.py` | N unit tests — describe coverage |

**Files Modified:**

| File | What changed |
|---|---|
| `backend/dependencies.py` | Added `yyy` branch in `provide_xxx()` factory |
| `backend/config.py` | Added new fields `yyy_*` |
| `.env.example` | Documented new env vars |

**Files Already Complete (No Changes Needed):**

| File | What was already there |
|---|---|
| `backend/xxx_provider/base.py` | ABC / interface — complete from POC |

**Provider / Abstraction Used:**

```
Implements:    [XxxProvider ABC / QueueProvider / SecretsProvider / ChannelProvider]
Via:           [Bedrock Claude Sonnet 4 / S3 / SQS / Secrets Manager / Meta Cloud API via N8N]
Injected by:   provide_xxx() in dependencies.py
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
3. Set XXX_PROVIDER=alternative in env / Secrets Manager
4. Zero other code changes needed.
```

---

## Cloud-Agnostic Boundary

```
boto3 imports allowed in:    backend/{queue,secrets,storage,llm,vision,ocr}_provider/*aws*.py
                              backend/{...}_provider/*bedrock*.py
                              backend/{...}_provider/*s3*.py
                              backend/{...}_provider/*sqs*.py

boto3 imports FORBIDDEN in:  backend/agents/   backend/graph/   backend/api/   backend/core/

Grep check (must return ZERO results):
grep -rn "boto3\|aws_\|import anthropic\|import google\|supabase" \
  backend/agents/ backend/graph/ backend/api/ backend/core/
```

Result of the grep on this branch: [paste output — must be empty]

---

## Channel-Agnostic Boundary

```
WhatsApp/Meta references allowed in:    backend/channel_provider/whatsapp_channel.py
                                         deploy/n8n/*.json

WhatsApp/Meta refs FORBIDDEN in:        backend/agents/  backend/graph/  backend/api/  backend/core/

Grep check (must return ZERO results):
grep -rni "whatsapp\|meta\|telegram\|twilio\|sms" \
  backend/agents/ backend/graph/ backend/api/ backend/core/
```

Result of the grep on this branch: [paste output — must be empty]

---

## Dependencies

```
Depends On (Task IDs)      →  P-XXX (reason)
External Libraries         →  library==version (already in requirements.txt / new addition)
Environment Variables      →  VAR_NAME (existing / new — update .env.example if new)
Secrets Manager Keys       →  key.name (new keys added to baggage-claim/<env> secret)
AWS Resources Required     →  ECR repo abc-baggage-claim, S3 bucket abc-baggage-claims-prod,
                              SQS queue claim-jobs, Secrets Manager secret baggage-claim/prod
IAM Permissions Required   →  secretsmanager:GetSecretValue on baggage-claim/*
                              bedrock:InvokeModel on us-east-1::foundation-model/anthropic.*
                              s3:PutObject, s3:GetObject on abc-baggage-claims-prod/*
                              sqs:ReceiveMessage, sqs:DeleteMessage on claim-jobs
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

**Mocking Strategy:**

```
moto:           S3, SQS, Secrets Manager (full mocks, transparent)
unittest.mock:  Bedrock invoke_model (moto does NOT support Bedrock)
real APIs:      NEVER in CI — only on manual cloud-smoke branches
```

**Manual Smoke Test (cloud-targeting):**

```bash
# Local against moto
LLM_PROVIDER=bedrock STORAGE_PROVIDER=s3 SECRETS_PROVIDER=aws_sm QUEUE_PROVIDER=sqs \
  uvicorn backend.main:app --reload --port 8000

curl -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -d '{"session_id": "smoke-001", "message": "..."}'
# Expected: {"accepted": true, "claim_id": "..."}
```

**Test Data Used:**
`tests/fixtures/...` — describe what fixtures are needed.

**Acceptance Criteria:**

```
✅ Criterion 1
✅ Criterion 2
✅ pytest → N passed, 0 failures
✅ black + isort clean
✅ Cloud-agnostic grep returns ZERO results
✅ Channel-agnostic grep returns ZERO results
```

---

## PR Checklist

```
[x] PR title includes Task ID — [P-XXX] feat/fix/chore/docs(scope): ...
[x] PR description filled out on GitHub (What changed / How to test / Task)
[x] Base branch set to develop-aws (NOT develop, NOT main)
[x] Reviewer assigned
[x] GitHub Actions green
[x] Squash merged to develop-aws
[x] Feature branch deleted after merge (local + remote)
[x] Tracker updated: Status=Done, Actual Hours, Completion Date, PR Link

[x] Type hints on all new/modified functions
[x] Google-style docstrings on all public functions
[x] .env.example updated (only if new env vars added)
[x] config.py updated (only if new Settings fields added)
[x] dependencies.py updated (only if new factory branch added)
[x] No hardcoded provider names / regions / bucket names / channel names in agents/, graph/, api/, core/
[x] No hardcoded API keys or ARNs anywhere
[x] pytest → N passed, 0 failures (both PROVIDER=local and PROVIDER=aws variants)
[x] black backend/ tests/ → clean
[x] isort backend/ tests/ → clean
[x] Branch doc committed to BRANCH_DOCS/AWS_PHASE/ before merge
[x] Cloud-agnostic grep — empty
[x] Channel-agnostic grep — empty
[x] Secrets never logged or committed
```

---

## Notes / Blockers

```
Known Issues    →  [None / description]
Scope Note      →  What is intentionally deferred to a future task.
Blockers        →  [None / description — e.g. waiting on P-013 admin coordination]
Links           →  Relevant docs: Bedrock API reference, Meta Cloud API docs, N8N node docs,
                   internal JIRA ticket, CloudWatch dashboard URL, AWS_Deployment_Plan.docx section X
```

---

*Branch opened: Day X, Week Y — [Author]*
*Merged to develop-aws: Day X, Week Y*
