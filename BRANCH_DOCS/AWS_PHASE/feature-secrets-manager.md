# BRANCH: feature/secrets-manager

---

## Branch Metadata

```
Branch Name        →  feature/secrets-manager
Task ID            →  P-005
Workstream          →  AWS Platform
Author              →  Devam Dixit
Reviewer             →  Anoushka Vyas
Start Date          →  Day 3, Week 1
Target Merge Date    →  Day 3, Week 1
Actual Merge Date    →  [Fill on completion]
Status               →  Ready for Review
```

---

## Objective

**What does this branch do?**
Implements `AWSSecretsManagerProvider` against the existing `SecretsProvider` ABC, and — the genuinely non-trivial part of this task — rewrites `get_settings()` so that when `SECRETS_PROVIDER=aws_sm`, AWS-sourced credential fields (currently the Supabase trio) are populated from a single Secrets Manager JSON blob rather than `.env`, with any value present in the secret overriding `.env`, and any value absent from the secret falling back gracefully to `.env`/defaults.

**Why is it needed?**
Plaintext `.env` files don't belong in a production container image or ECS task definition. Secrets Manager gives the app one vaulted JSON blob (`baggage-claim/<env>`) holding every AWS-sourced credential, read once at startup and cached — matching the task's explicit requirement ("Bedrock + Supabase + Meta creds all live in ONE secret JSON") and giving P-013's admin ticket exactly one secret to provision and scope IAM around.

---

## Local Setup

```bash
source venv/Scripts/activate      # Git Bash / Windows
# source venv/bin/activate        # Mac / Linux

pip install -r requirements.txt   # boto3/moto already present from P-004
pytest tests/test_aws_secrets.py tests/test_config.py -v
```

Cloud-targeting smoke test (moto, no real AWS):

```bash
export SECRETS_PROVIDER=aws_sm SECRETS_MANAGER_NAME=baggage-claim/test AWS_REGION=us-east-1
pytest tests/ -v        # moto intercepts boto3 secretsmanager calls — no real AWS hit
```

---

## Technical Approach

**Files Created:**

| File | Purpose |
|---|---|
| `backend/secrets_provider/aws_secrets.py` | `AWSSecretsManagerProvider` — fetches and caches a Secrets Manager JSON blob at init, serves `get(name)` from the in-memory cache |
| `tests/test_aws_secrets.py` | 8 moto-mocked tests for the provider in isolation — fetch/cache, missing secret, invalid JSON, missing key, multi-key secrets |
| `tests/test_config.py` | 8 tests for `get_settings()`'s new Secrets Manager integration — the override-vs-fallback logic, non-secret-field isolation, lru_cache behaviour |

**Files Modified:**

| File | What changed |
|---|---|
| `backend/config.py` | Added `secrets_manager_name` Settings field. Rewrote `get_settings()`: builds `Settings()` from env first (always), then — only if `secrets_provider == "aws_sm"` — fetches the named secret and re-validates Settings with matching fields overridden via `model_copy(update=...)`. Added `_SECRET_FIELD_MAP` mapping Settings field names to secret JSON keys (currently the Supabase trio only) |
| `backend/dependencies.py` | Added `aws_sm` branch to `provide_secrets()` |
| `.env.example` | Documented `SECRETS_MANAGER_NAME` |

**Files Already Complete (No Changes Needed):**

| File | What was already there |
|---|---|
| `backend/secrets_provider/base.py` | `SecretsProvider` ABC — `get(name) -> str` contract, unchanged (P-002, Aditya) |
| `backend/secrets_provider/env_secrets.py` | POC env-var implementation — left fully intact, still the default |

**Provider / Abstraction Used:**

```
Implements:    SecretsProvider ABC
Via:           AWS Secrets Manager (boto3 secretsmanager client)
Injected by:   provide_secrets() in dependencies.py, branch: SECRETS_PROVIDER=aws_sm
Special case:  get_settings() ALSO consults this provider directly (not via
               provide_secrets()) to populate Settings fields before Pydantic
               validation completes — this is the one place in the codebase
               where a provider is used outside the normal DI factory path,
               because Settings itself needs to exist before dependencies.py's
               factories can run.
```

**Key Design Decisions:**

```
1. THE CHICKEN-AND-EGG PROBLEM, SOLVED BY TWO-PHASE CONSTRUCTION
   get_settings() needs SECRETS_PROVIDER and SECRETS_MANAGER_NAME to know
   whether/which secret to fetch — but those are themselves Settings fields.
   Solution: build Settings() from env ONCE (phase 1) to learn those two
   values, THEN — only if secrets_provider=="aws_sm" — fetch the secret and
   produce a second, corrected Settings instance via model_copy(update=...)
   (phase 2). secrets_provider/secrets_manager_name/aws_region are never
   themselves eligible for Secrets-Manager override — they have to be
   readable before any secret fetch can happen.

2. model_copy(update=...) INSTEAD OF MANUAL ATTRIBUTE ASSIGNMENT
   Settings is a frozen-by-convention Pydantic model. model_copy(update=...)
   re-runs Pydantic validation on the updated fields (so a malformed secret
   value still gets caught by Settings' own type coercion/validation rules),
   rather than bypassing validation with direct attribute mutation.

3. _SECRET_FIELD_MAP IS AN ALLOWLIST, NOT "OVERRIDE EVERYTHING THE SECRET HAS"
   Only fields explicitly listed in _SECRET_FIELD_MAP can be overridden from
   Secrets Manager. A secret that happens to contain a key spelled
   "LLM_PROVIDER" does NOT change settings.llm_provider — provider switches,
   model IDs, and thresholds are configuration, belong in version-controlled
   .env.example, and must never silently change behaviour based on what's in
   a vault. Verified by test_get_settings_aws_sm_does_not_override_non_secret_fields.

4. PARTIAL SECRETS DEGRADE GRACEFULLY, NOT DESTRUCTIVELY
   If the secret JSON has SUPABASE_URL but not SUPABASE_ANON_KEY, only
   supabase_url gets overridden — supabase_anon_key keeps its .env/default
   value rather than being wiped to None. This matters operationally: admin
   can populate the secret incrementally without breaking unrelated fields.

5. AWSSecretsManagerProvider FETCHES ONCE, IN __init__, NOT LAZILY
   Per the task note ("Cache once at startup") and for fail-fast behaviour —
   if the secret is missing/malformed/inaccessible, the app should refuse
   to start rather than serve traffic and discover the problem on the first
   real secret lookup mid-request. ClientError/ValueError propagate
   immediately from __init__.

6. aws_region REUSED, NOT A SEPARATE secrets_manager_region
   Same pattern established in P-003/P-004 — one AWS region setting shared
   across S3, Bedrock, and now Secrets Manager.
```

**Future Swap Path:**

```
To switch away from Secrets Manager (e.g. to HashiCorp Vault):
1. Create backend/secrets_provider/vault_secrets.py implementing SecretsProvider
2. Add a 'vault' branch in provide_secrets()
3. get_settings() would need a small addition: a 'vault' branch alongside
   the existing 'aws_sm' branch, following the exact same
   fetch-then-model_copy pattern — _SECRET_FIELD_MAP itself needs no changes.
4. Set SECRETS_PROVIDER=vault + VAULT_* env vars.
```

---

## Cloud-Agnostic Boundary

```
boto3 imports allowed in:    backend/secrets_provider/aws_secrets.py   ✅ (this branch)
                              backend/storage_provider/s3_storage.py     (P-004, untouched)
                              backend/{llm,vision,ocr}_provider/bedrock_*.py (P-003, untouched)

boto3 imports FORBIDDEN in:  backend/agents/   backend/graph/   backend/api/   backend/core/

Grep check:
grep -rn "boto3\|aws_\|import anthropic\|import google\|supabase" \
  backend/agents/ backend/graph/ backend/api/ backend/core/
```

Result of the grep on this branch:
```
backend/api/routes/health.py:25,28   (pre-existing P-004 docstring, unchanged by this branch)
```
**Zero new hits introduced by P-005.**

---

## Channel-Agnostic Boundary

```
WhatsApp/Meta references allowed in:    (none yet — channel_provider/whatsapp_channel.py lands in P-024)

Grep check:
grep -rni "whatsapp\|meta\|telegram\|twilio\|sms" \
  backend/agents/ backend/graph/ backend/api/ backend/core/
```

Result of the grep on this branch:
```
backend/agents/a5_notification.py, backend/api/routes/webhook.py,
backend/api/routes/qr.py, backend/graph/orchestrator.py
  — all pre-existing POC/P-024-scope hits, identical to the set already
    documented in P-003's and P-004's branch docs.
```
**Zero new hits introduced by P-005.**

---

## Dependencies

```
Depends On (Task IDs)      →  P-002 (SecretsProvider ABC + EnvSecretsProvider, Aditya)
External Libraries         →  boto3==1.35.36, moto[s3]==5.0.18 (both already present from P-004 — no requirements.txt change needed)
Environment Variables      →  SECRETS_MANAGER_NAME (new, defaults to "baggage-claim/local")
Secrets Manager Keys       →  This task CREATES the consumer of the secret; the actual
                              secret itself (baggage-claim/prod) is populated in P-015
                              once P-013's admin ticket provisions it.
AWS Resources Required     →  Secrets Manager secret baggage-claim/<env> (admin pre-creates
                              under P-013; populated with real values in P-015)
IAM Permissions Required   →  secretsmanager:GetSecretValue on
                              arn:aws:secretsmanager:us-east-1:*:secret:baggage-claim/*
```

---

## Testing

**Run tests:**

```bash
pytest tests/test_aws_secrets.py -v    # 8 passed
pytest tests/test_config.py -v         # 8 passed

pytest tests/ -v
# 390 passed, 1 skipped — confirmed zero regressions against full suite
```

**Mocking Strategy:**

```
moto:  Full Secrets Manager mock via @mock_aws — create_secret, get_secret_value,
       delete_secret all intercepted. No real AWS calls, no credentials needed.
```

**Manual Smoke Test (cloud-targeting):**

```bash
SECRETS_PROVIDER=aws_sm SECRETS_MANAGER_NAME=baggage-claim/test AWS_REGION=us-east-1 \
  uvicorn backend.main:app --reload --port 8000
# Against real AWS with valid creds + a populated secret, Settings would load
# the Supabase trio from Secrets Manager instead of .env.
```

**Test Data Used:**
No fixture files — all tests construct secret JSON inline against moto-mocked Secrets Manager.

**Acceptance Criteria:**

```
✅ SECRETS_PROVIDER=aws_sm with moto: secret values are read into Settings
   without using .env — verified live (not just via test) in the working
   session before writing tests
✅ Partial secrets degrade gracefully (missing keys keep .env/default values)
✅ Non-secret fields (provider switches, model IDs) never overridden by a secret
✅ pytest tests/test_aws_secrets.py tests/test_config.py → 16 passed
✅ pytest tests/ → 390 passed, 1 skipped (zero regressions)
✅ black + isort clean
✅ Cloud-agnostic grep — zero new hits
✅ Channel-agnostic grep — zero new hits
```

---

## PR Checklist

```
[x] PR title includes Task ID — [P-005] feat(secrets): add AWS Secrets Manager provider
[x] PR description filled out on GitHub (What changed / How to test / Task)
[x] Base branch set to develop-aws (NOT develop, NOT main)
[x] Reviewer assigned — Anoushka Vyas
[ ] GitHub Actions green                                    ← confirm after push
[ ] Squash merged to develop-aws                             ← after approval
[ ] Feature branch deleted after merge (local + remote)      ← after merge
[ ] Tracker updated: Status=Done, Actual Hours, Completion Date, PR Link

[x] Type hints on all new/modified functions
[x] Google-style docstrings on all public functions
[x] .env.example updated (SECRETS_MANAGER_NAME added)
[x] config.py updated (secrets_manager_name field + get_settings() rewrite)
[x] dependencies.py updated (aws_sm branch added to provide_secrets())
[x] No hardcoded provider names / regions / secret names in agents/, graph/, api/, core/
[x] No hardcoded API keys, secret values, or ARNs anywhere
[x] pytest → 390 passed, 1 skipped (both env and aws_sm SECRETS_PROVIDER variants)
[x] black backend/secrets_provider/aws_secrets.py backend/config.py backend/dependencies.py
    tests/test_aws_secrets.py tests/test_config.py → clean
[x] isort (same files) → clean
[x] Branch doc committed to BRANCH_DOCS/AWS_PHASE/ before merge
[x] Cloud-agnostic grep — zero new hits
[x] Channel-agnostic grep — zero new hits
[x] Secrets never logged or committed — AWSSecretsManagerProvider logs key
    NAMES on cache miss, never values; get_settings() never logs the
    overridden values either
```

---

## Notes / Blockers

```
Known Issues    →  None.

Scope Note      →  _SECRET_FIELD_MAP currently has only the Supabase trio —
                   that's all that exists as a credential field in Settings
                   today. Bedrock needs no secret (AWS IAM role handles auth,
                   not an app-level credential), so it was correctly NOT
                   added to the map. When P-021 introduces Meta WhatsApp
                   credentials, that task should add 1-2 lines to
                   _SECRET_FIELD_MAP — no other change needed, by design.

Blockers        →  None for merging this branch. For the secret to actually
                   contain real values, P-013 (admin provisions the empty
                   secret) and P-015 (Aditya populates it) both need to
                   complete first — neither blocks this branch's code review,
                   since all tests run against moto.

Links           →  AWS_Phase2_Tracker.xlsx (row P-005 — Task Tracker)
                   AWS_Deployment_Plan.docx §5 (cloud-agnostic provider layer)
                   BRANCH_DOCS/AWS_PHASE/TEMPLATE.md (template this doc follows)
                   BRANCH_DOCS/AWS_PHASE/feature-abstractions-queue-secrets-channel.md
                     (P-002 — Aditya's SecretsProvider ABC this branch implements)
```

---

*Branch opened: Day 3, Week 1 — Devam Dixit*
*Merged to develop-aws: [Day 3, Week 1 — fill on merge]*
