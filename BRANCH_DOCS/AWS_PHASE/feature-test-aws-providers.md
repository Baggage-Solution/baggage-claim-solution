# BRANCH: feature/test-aws-providers

---

## Branch Metadata

```
Branch Name        →  feature/test-aws-providers
Task ID            →  P-011
Workstream          →  Test Suite
Author              →  Aditya
Reviewer             →  Anoushka
Start Date          →  Day 4, Week 1
Target Merge Date    →  Day 5, Week 1
Actual Merge Date    →  [Fill on completion]
Status               →  Ready for Review
```

---

## Objective

**What does this branch do?**
Adds `tests/conftest.py` (shared fixtures) and `tests/test_aws_providers.py` (cross-provider integration tests) — the two pieces of test infrastructure that did NOT exist yet, even though each individual AWS provider (Bedrock LLM/Vision/OCR, S3, Secrets Manager, SQS) already had its own isolated test file from P-003 through P-006. Also fixes one pre-existing test (`test_simulator_flag_p009.py`) that only passed when a developer's local `.env` happened to be populated, and fixes one genuine cross-test state-pollution bug discovered while building this branch's own test fixtures.

**Why is it needed?**
The individual provider tests prove each provider works in isolation. Nobody had yet verified that (a) `dependencies.py`'s factory wiring actually selects the *correct* class for every `*_PROVIDER` env var — not just "the class exists somewhere" — and (b) multiple providers genuinely work together in the same request lifecycle the way `webhook.py`/`worker.py` actually use them (save to S3, then enqueue to SQS referencing that S3 path). This branch closes both gaps, and confirms 96% coverage across all 6 AWS provider modules, well above the 75% target.

---

## Local Setup

```bash
source venv/Scripts/activate      # Git Bash / Windows
# source venv/bin/activate        # Mac / Linux

pip install -r requirements.txt -r requirements-dev.txt
pytest tests/test_aws_providers.py -v
```

Full suite + coverage on the AWS provider modules:

```bash
pytest tests/ -v
pytest tests/ --cov=backend.llm_provider.bedrock_llm --cov=backend.vision_provider.bedrock_vision \
  --cov=backend.ocr_provider.bedrock_ocr --cov=backend.storage_provider.s3_storage \
  --cov=backend.secrets_provider.aws_secrets --cov=backend.queue_provider.sqs_queue \
  --cov-report=term-missing
```

---

## Technical Approach

**Files Created:**

| File | Purpose |
|---|---|
| `tests/conftest.py` | Shared fixtures: `sample_claim_job` / `sample_claim_job_with_tag` (matching the EXACT shape `webhook.py::_build_job_payload()` produces), `make_bedrock_text_response()` helper, `moto_s3_and_sqs` combined fixture (bucket + main queue + DLQ with redrive policy, in one moto context) |
| `tests/test_aws_providers.py` | 17 cross-provider integration tests: factory-wiring correctness (6 tests), PROVIDER=local defaults (4 tests), S3→SQS round-trip integrity (3 tests), shared Bedrock mock helper usage (3 tests), credential-free construction sanity check (1 test) |

**Files Modified:**

| File | What changed |
|---|---|
| `tests/test_simulator_flag_p009.py` | Fixed `test_dashboard_route_reachable_when_simulator_disabled` — was asserting `/health` returns exactly `200`, which only held true when the runner's environment happened to have Supabase/Gemini env vars set. Changed to accept `200` or `503`, matching the exact precedent already established in `test_smoke_t001_t016.py::test_t004_health_endpoint_up` for the identical class of environment-dependent health check. |

**Files Already Complete (No Changes Needed):**

| File | What was already there |
|---|---|
| `tests/test_bedrock_llm.py`, `test_bedrock_vision.py`, `test_bedrock_ocr.py` | Isolated provider tests from P-003 (Anoushka) — left fully intact |
| `tests/test_s3_storage.py` | Isolated provider tests from P-004 (Devam) — left fully intact |
| `tests/test_aws_secrets.py`, `test_config.py` | Isolated provider tests from P-005 (Devam) — left fully intact |
| `tests/test_sqs_queue.py` | Isolated provider tests from P-006 (Aditya, prior branch) — left fully intact |
| `requirements-dev.txt` | Already had `moto[all]==5.0.18` — someone on the unified P-006–P-010 branch had already completed this pick-up step before this branch started |

**Key Design Decisions:**

```
1. CONFTEST.PY ADDS NEW SHARED FIXTURES — DOES NOT REFACTOR EXISTING ONES
   Each provider's own test file (test_s3_storage.py etc.) already has its
   own self-contained, passing fixtures. Forcing those into shared
   conftest.py fixtures now would mean touching 6 already-merged files for
   pure tidiness, with real risk of breaking something that currently
   works, for zero functional benefit. conftest.py instead provides ONLY
   the fixtures that genuinely did not exist: a realistic job payload and
   a combined multi-service moto setup, both needed for the NEW
   integration tests in this branch.

2. sample_claim_job MATCHES THE REAL PRODUCER, NOT AN INVENTED SHAPE
   Pulled directly from backend/api/routes/webhook.py::_build_job_payload()
   — every field name, every default — rather than writing a simplified
   "looks about right" dict. A test built on a fictional payload shape
   can drift silently from what the real producer/consumer actually
   exchange; this fixture cannot, because it IS that shape.

3. FACTORY-WIRING TESTS CHECK isinstance(), NOT JUST "DID NOT RAISE"
   Confirms LLM_PROVIDER=bedrock genuinely produces a BedrockLLMProvider
   instance (and likewise for all 6 provider switches) — catching, for
   example, a typo'd string comparison in dependencies.py that would
   silently fall through to the wrong branch without raising any error.

4. moto_s3_and_sqs FIXTURE MIRRORS THE REAL QUEUE TOPOLOGY
   Creates claim-jobs + claim-jobs-dlq with the actual redrive policy
   (maxReceiveCount=3) and visibility timeout (60s) specified in P-006's
   own task notes — not a bare single queue. The DLQ redrive test
   (test_dlq_redrive_policy_is_correctly_configured) exists specifically
   to confirm this fixture's setup is correct, since a wrong fixture would
   make every test built on it falsely confident.

5. ALL BEDROCK ASSERTIONS USE unittest.mock, NEVER moto
   Confirmed (again, independently) that moto has no Bedrock backend.
   make_bedrock_text_response() in conftest.py is a SHARED helper so the
   3 Bedrock-touching tests in this file (and any future test) don't each
   reinvent the same response-shape mock.

6. test_simulator_flag_p009.py FIX: ALIGNED ASSERTION, NOT WIDENED SCOPE
   The test's own docstring says "must respond" — not "must be fully
   configured." /health legitimately returns 503 when Supabase/Gemini
   aren't configured (P-004's own design). The fix makes the assertion
   match the test's stated intent, using the exact same 200-or-503
   acceptance already established elsewhere in the suite — not a new
   pattern invented for this fix.

7. _clean_settings_cache FIXTURE CLEARS CACHES BOTH BEFORE *AND* AFTER —
   A REAL BUG, FOUND AND FIXED DURING THIS BRANCH'S OWN VERIFICATION
   Initial version only cleared provider lru_caches BEFORE each test.
   Running the full suite (not just this file) surfaced a real failure:
   test_smoke_t001_t016.py::test_t013_upload_endpoint_exists started
   failing with NoCredentialsError — entirely unrelated to AWS on its
   face. Root cause: provide_storage() is @lru_cache'd at module level;
   one of THIS branch's own tests (test_no_real_aws_credentials_required_
   to_run_this_file) constructs an S3StorageProvider with
   STORAGE_PROVIDER=s3 and no real credentials, and that broken instance
   stayed cached for the rest of the pytest SESSION — poisoning a
   completely unrelated test in a different file that runs later
   alphabetically. Fixed by clearing every provide_*() cache AFTER each
   test too, not just before. This is exactly the class of bug P-011
   exists to catch, and it was caught against this branch's own code,
   not anyone else's.
```

**Future Swap Path:**

```
N/A — this branch adds test infrastructure, not a new provider. Any
future provider (P-024's WhatsApp ChannelProvider, a hypothetical GCP/
Azure provider) should add its OWN isolated test file (matching the
existing pattern), and can optionally add a factory-wiring isinstance()
check + integration scenario to test_aws_providers.py if it participates
in a multi-provider flow worth covering.
```

---

## Cloud-Agnostic Boundary

```
Grep check:
grep -rn "boto3\|aws_\|import anthropic\|import google\|supabase" \
  backend/agents/ backend/graph/ backend/api/ backend/core/
```

Result of the grep on this branch:
```
backend/api/routes/health.py:25,28   (pre-existing P-004 docstring, unchanged by this branch)
```
**Zero new hits introduced by P-011.**

---

## Channel-Agnostic Boundary

```
Grep check:
grep -rni "whatsapp\|meta\|telegram\|twilio\|sms" \
  backend/agents/ backend/graph/ backend/api/ backend/core/
```

Result of the grep on this branch:
```
Identical set to every prior branch doc — backend/agents/a5_notification.py,
backend/api/routes/webhook.py, backend/api/routes/qr.py,
backend/graph/orchestrator.py — all pre-existing POC/P-024-scope, none
touched by this branch.
```
**Zero new hits introduced by P-011.**

---

## Dependencies

```
Depends On (Task IDs)      →  P-003, P-004, P-005, P-006 (all merged — every provider
                              this branch tests against already exists)
External Libraries         →  moto[all]==5.0.18 (already present in requirements-dev.txt
                              before this branch started), pytest-cov (test-only, used
                              for coverage verification — not added to requirements files
                              since coverage reporting isn't part of the CI gate itself)
Environment Variables      →  None new — this branch only sets env vars WITHIN tests via
                              monkeypatch, never adds a new persistent .env entry
Secrets Manager Keys       →  None
AWS Resources Required     →  None — 100% of this branch runs against moto + unittest.mock
IAM Permissions Required   →  None
```

---

## Testing

**Run tests:**

```bash
pytest tests/test_aws_providers.py -v             # 17 passed
pytest tests/test_simulator_flag_p009.py -v       # 7 passed (1 was previously failing)

pytest tests/ -v
# 468 passed, 1 skipped — ran twice in a row to confirm not flaky
```

**Coverage (the explicit P-011 acceptance criterion — target >75%):**

```bash
pytest tests/ --cov=backend.llm_provider.bedrock_llm --cov=backend.vision_provider.bedrock_vision \
  --cov=backend.ocr_provider.bedrock_ocr --cov=backend.storage_provider.s3_storage \
  --cov=backend.secrets_provider.aws_secrets --cov=backend.queue_provider.sqs_queue \
  --cov-report=term-missing

# Result: 96% combined coverage across all 6 AWS provider modules
#   bedrock_llm.py        98%
#   bedrock_ocr.py         98%
#   sqs_queue.py            87%
#   aws_secrets.py         100%
#   s3_storage.py           91%
#   bedrock_vision.py       98%
```

**Mocking Strategy:**

```
moto:           S3, SQS, Secrets Manager — full native mocks via @mock_aws
unittest.mock:  Bedrock (all 3 providers) — moto has no Bedrock backend, confirmed
Real fixtures:  tests/fixtures/damaged/*.jpg, tests/fixtures/bag_tags/*.jpg (already
                existing POC fixtures, reused — not duplicated)
```

**Test Data Used:**
`sample_claim_job` / `sample_claim_job_with_tag` fixtures in `conftest.py` — built to match the real `_build_job_payload()` shape exactly, not an invented simplification.

**Acceptance Criteria:**

```
✅ pytest tests/ → 0 failures, both PROVIDER=local default and AWS provider env vars
✅ Coverage > 75% — achieved 96% across all 6 AWS provider modules
✅ Each provider class tested in isolation — confirmed already true from P-003–P-006,
   this branch adds cross-provider coverage on top
✅ Fixtures for sample claim job payload — added, matching the real producer shape
✅ Never call real AWS in tests — confirmed via dedicated sanity-check test
✅ black + isort clean on both new files
✅ Cloud-agnostic / channel-agnostic greps — zero new hits
```

---

## PR Checklist

```
[x] PR title includes Task ID — [P-011] test(aws-providers): add shared fixtures and cross-provider integration tests
[x] PR description filled out on GitHub (What changed / How to test / Task)
[x] Base branch set to develop-aws (NOT develop, NOT main)
[x] Reviewer assigned — Anoushka
[ ] GitHub Actions green                                    ← confirm after push
[ ] Squash merged to develop-aws                             ← after approval
[ ] Feature branch deleted after merge (local + remote)      ← after merge
[ ] Tracker updated: Status=Done, Actual Hours, Completion Date, PR Link

[x] Type hints on all new functions
[x] Google-style docstrings on all public functions
[x] .env.example — no changes needed (no new env vars introduced)
[x] config.py / dependencies.py — no changes needed (this branch tests existing wiring,
    does not add a new provider)
[x] No hardcoded provider names / regions / bucket names / channel names in agents/,
    graph/, api/, core/
[x] No hardcoded API keys or ARNs anywhere
[x] pytest → 468 passed, 1 skipped (both default and AWS provider variants)
[x] black tests/conftest.py tests/test_aws_providers.py → clean
[x] isort (same files) → clean
[x] Branch doc committed to BRANCH_DOCS/AWS_PHASE/ before merge
[x] Cloud-agnostic grep — zero new hits
[x] Channel-agnostic grep — zero new hits
[x] Secrets never logged or committed — no secrets used anywhere in this branch
```

---

## Notes / Blockers

```
Known Issues    →  None.

Scope Note      →  This branch fixes ONE pre-existing test
                   (test_simulator_flag_p009.py) and ONE bug found in its OWN
                   new code (the lru_cache pollution bug) — both flagged
                   explicitly above rather than silently folded in. Neither
                   required touching any provider implementation file; both
                   were test-only fixes, squarely within P-011's scope as
                   the task responsible for making the suite CI-ready.

Blockers        →  None. This branch has zero AWS resource dependencies —
                   100% moto/unittest.mock. Does not block or get blocked by
                   P-013 (admin coordination).

Links           →  AWS_Phase2_Tracker_Updated.xlsx (row P-011 — Task Tracker)
                   BRANCH_DOCS/AWS_PHASE/TEMPLATE.md (template this doc follows)
                   BRANCH_DOCS/AWS_PHASE/feature-bedrock-llm-vision-ocr.md (P-003)
                   BRANCH_DOCS/AWS_PHASE/feature-s3-storage.md (P-004)
                   BRANCH_DOCS/AWS_PHASE/feature-secrets-manager.md (P-005)
                   BRANCH_DOCS/AWS_PHASE/feature-unified-p006-p010-anoushka-aditya-devam.md (P-006–P-010)
```

---

*Branch opened: Day 4, Week 1 — Aditya*
*Merged to develop-aws: [Day 5, Week 1 — fill on merge]*
