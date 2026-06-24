# BRANCH: feature/s3-storage

---

## Branch Metadata

```
Branch Name        →  feature/s3-storage
Task ID            →  P-004
Workstream         →  AWS Platform
Author             →  Devam Dixit
Reviewer           →  Aditya Bhavsar
Start Date         →  Day 2, Week 1
Target Merge Date  →  Day 3, Week 1
Actual Merge Date  →  [Fill on completion]
Status             →  Ready for Review
```

---

## Objective

**What does this branch do?**
Implements `S3StorageProvider`, a production AWS S3-backed implementation of the existing `StorageProvider` ABC. Adds the `s3` branch to the `provide_storage()` factory in `dependencies.py`, the required `S3_BUCKET` / `AWS_REGION` / `S3_PRESIGN_EXPIRY_SECONDS` settings, and a moto-mocked test suite. No existing file is replaced — every shared file (`config.py`, `dependencies.py`, `.env.example`, `requirements.txt`) is patched by appending new lines after a specific anchor, so P-002 (Aditya's QueueProvider/SecretsProvider/ChannelProvider work) is untouched.

**Why is it needed?**
`STORAGE_PROVIDER=local` writes to disk inside the container, which doesn't survive ECS task restarts or scale-out, and isn't reachable from a second task. S3 gives durable, shared storage across however many `api` and `worker` tasks Fargate runs, and unlocks presigned URLs so the Bedrock vision/OCR providers (P-003, in progress) and any browser preview can fetch an image over HTTPS without holding AWS credentials.

---

## Local Setup

```bash
source venv/Scripts/activate      # Git Bash / Windows
# source venv/bin/activate        # Mac / Linux

pip install -r requirements.txt   # picks up boto3 + moto from this branch
pytest tests/test_s3_storage.py -v
```

Cloud-targeting smoke test (moto-backed, no real AWS):

```bash
export STORAGE_PROVIDER=s3 S3_BUCKET=abc-baggage-claims-test AWS_REGION=us-east-1
pytest tests/ -v        # moto intercepts boto3 — no real AWS hit
```

---

## Technical Approach

**Files Created:**

| File | Purpose |
|---|---|
| `backend/storage_provider/s3_storage.py` | `S3StorageProvider` — implements `StorageProvider.save()` / `.get_path()` via boto3 S3 |
| `tests/test_s3_storage.py` | 8 moto-mocked unit tests — save, content-type guessing, presigned URLs, claim isolation, failure path |

**Files Modified (append-only — see `P-004_file_patches.md` for exact diffs):**

| File | What changed |
|---|---|
| `requirements.txt` | Added `boto3==1.35.36` and `moto[s3]==5.0.18` |
| `backend/config.py` | Added `s3_bucket`, `aws_region`, `s3_presign_expiry_seconds` Settings fields |
| `backend/dependencies.py` | Added `s3` branch inside `provide_storage()`, before the existing `raise ValueError` |
| `.env.example` | Added AWS S3 block documenting `S3_BUCKET`, `AWS_REGION`, `S3_PRESIGN_EXPIRY_SECONDS` |

**Files Already Complete (No Changes Needed):**

| File | What was already there |
|---|---|
| `backend/storage_provider/base.py` | `StorageProvider` ABC — `save()` / `get_path()` contract, unchanged |
| `backend/storage_provider/local_storage.py` | POC disk implementation — left fully intact, still the default |

**Provider / Abstraction Used:**

```
Implements:    StorageProvider ABC
Via:           AWS S3 (boto3)
Injected by:   provide_storage() in dependencies.py, branch: STORAGE_PROVIDER=s3
Agent imports: StorageProvider only — backend/api/routes/webhook.py calls
               provide_storage() and never imports S3StorageProvider directly
```

**Key Design Decisions:**

```
1. CLAIM-SCOPED KEY PREFIX (s3://{bucket}/{claim_id}/{filename})
   Mirrors LocalStorageProvider's directory-per-claim layout exactly, so the
   existing /upload route in webhook.py needed zero changes beyond flipping
   STORAGE_PROVIDER. Also gives S3 lifecycle policies and IAM bucket scoping
   a clean prefix to key off later.

2. get_path() RETURNS A PRESIGNED HTTPS URL, NOT A RAW s3:// URI
   LocalStorageProvider.get_path() returns a filesystem path because the
   caller is always on the same machine. S3StorageProvider's caller is not
   guaranteed to have AWS credentials (browser previews, future Bedrock
   multimodal calls that need an HTTPS image URL). A presigned GET URL with
   a configurable TTL (default 1h) solves this without changing the ABC's
   return type (still `str`).

3. boto3 CALLS OFFLOADED VIA asyncio.to_thread
   boto3 is synchronous. save() blocks on put_object, so it runs in a worker
   thread to avoid stalling the FastAPI event loop. generate_presigned_url
   in get_path() is a local signature computation (no network round-trip),
   so it is NOT offloaded — added thread overhead there would be pure waste.

4. CONTENT-TYPE GUESSED FROM EXTENSION, NOT FROM MAGIC BYTES
   The existing upload flow only ever sends .jpg/.jpeg/.png/.webp damage and
   tag photos (enforced client-side in the simulator / WhatsApp media flow).
   A simple extension-based guess keeps this provider small; a content-
   sniffing library would be overkill for the actual input domain.

5. aws_region IN config.py IS GENERIC, NOT s3_region
   P-003 (Bedrock) and P-006 (SQS) will also need an AWS region. Rather than
   each provider adding its own *_region field, this branch introduces a
   single shared aws_region so all three converge on one Settings field.
   Flagged in the patch notes in case P-003 merges first with its own field.

6. ClientError PROPAGATES, NEVER SWALLOWED
   webhook.py's /upload route needs to know if a save failed (e.g. bad
   bucket name, no network) rather than silently returning a path to an
   object that doesn't exist. Both save() and get_path() let ClientError
   bubble up; the caller decides how to respond to the passenger.
```

**Future Swap Path:**

```
To switch away from S3 (e.g. to Cloudflare R2, which is S3-compatible):
1. Create backend/storage_provider/r2_storage.py implementing StorageProvider
   (can likely subclass/wrap S3StorageProvider since R2's API is S3-compatible
   — just point boto3 at R2's endpoint_url)
2. Add an 'r2' branch in provide_storage()
3. Set STORAGE_PROVIDER=r2 + R2_* env vars
4. Zero changes to webhook.py, agents/, or any other caller.
```

---

## Cloud-Agnostic Boundary

```
boto3 imports allowed in:    backend/storage_provider/s3_storage.py   ✅ (this file)

boto3 imports FORBIDDEN in:  backend/agents/   backend/graph/   backend/api/   backend/core/

Grep check:
grep -rn "boto3\|aws_\|import anthropic\|import google\|supabase" \
  backend/agents/ backend/graph/ backend/api/ backend/core/
```

Result of the grep on this branch:
```
backend/api/routes/health.py:31:    supabase_configured = bool(
backend/api/routes/health.py:32:        settings.supabase_url and settings.supabase_service_role_key
backend/api/routes/health.py:35:    status = "ok" if (gemini_configured and supabase_configured) else "degraded"
backend/api/routes/health.py:52:            "supabase": supabase_configured,
```
**⚠️ Pre-existing from POC phase — NOT introduced by this branch.** `health.py` references `supabase_*` Settings fields directly instead of going through `provide_db()`. This branch touches zero lines in `health.py`. Flagging for a future cleanup task rather than scope-creeping P-004 to fix it.

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
backend/agents/a5_notification.py:65-66   (docstring mentioning future WhatsApp swap)
backend/api/routes/webhook.py:26-84       (verify_whatsapp_signature, WHATSAPP_APP_SECRET)
```
**⚠️ Pre-existing from POC phase — NOT introduced by this branch.** `webhook.py` already hardcodes WhatsApp HMAC verification directly in `api/routes/`. This is exactly the coupling that P-024 (WhatsApp ChannelProvider) is scoped to fix. This branch touches zero lines in either file — flagging so it isn't lost track of, not claiming it as in-scope here.

---

## Dependencies

```
Depends On (Task IDs)      →  P-001 (develop-aws branch must exist)
External Libraries         →  boto3==1.35.36 (new), moto[s3]==5.0.18 (new, test-only)
Environment Variables      →  S3_BUCKET (new), AWS_REGION (new, shared with future P-003/P-006),
                              S3_PRESIGN_EXPIRY_SECONDS (new, optional — defaults to 3600)
Secrets Manager Keys       →  None — AWS credentials come from the default credential chain
                              (IAM role on ECS task in production; local AWS profile in dev).
                              No key/secret is ever read from Secrets Manager for this provider.
AWS Resources Required     →  S3 bucket abc-baggage-claims-prod (admin pre-creates — tracked
                              under P-013 admin coordination ticket)
IAM Permissions Required   →  s3:PutObject, s3:GetObject on arn:aws:s3:::abc-baggage-claims-prod/*
```

---

## Testing

**Run tests:**

```bash
pytest tests/test_s3_storage.py -v
# 8 passed

pytest tests/ -v
# 337 passed, 1 skipped — confirmed zero regressions against full suite
```

**Mocking Strategy:**

```
moto[s3]:   Full S3 mock via @mock_aws context manager. create_bucket, put_object,
            get_object, generate_presigned_url all intercepted — no real AWS calls,
            no credentials needed, no network access required.
```

**Manual Smoke Test (cloud-targeting):**

```bash
STORAGE_PROVIDER=s3 S3_BUCKET=abc-baggage-claims-test AWS_REGION=us-east-1 \
  uvicorn backend.main:app --reload --port 8000

curl -X POST http://localhost:8000/upload \
  -F "session_id=smoke-001" -F "claim_id=CLM-SMOKE" -F "photo_type=damage" \
  -F "file=@tests/fixtures/damaged/damaged_01.jpg"
# Expected (against real AWS, with valid creds + bucket):
# {"path": "s3://abc-baggage-claims-test/CLM-SMOKE/damage_damaged_01.jpg", "filename": "damage_damaged_01.jpg"}
```

**Test Data Used:**
No fixture files needed — all 8 tests use inline byte strings (`b"fake-image-bytes"` etc.) against a moto-mocked bucket, since the provider only cares about byte-for-byte storage/retrieval, not actual image content.

**Acceptance Criteria:**

```
✅ STORAGE_PROVIDER=s3 with moto mock: save() returns 's3://bucket/key'
✅ get_path() returns a presigned URL, not a raw S3 URI
✅ pytest tests/test_s3_storage.py → 8 passed
✅ pytest tests/ → 337 passed, 1 skipped (zero regressions)
✅ black + isort clean on both new files
✅ Cloud-agnostic grep — only pre-existing POC hits, none from this branch
✅ Channel-agnostic grep — only pre-existing POC hits, none from this branch
```

---

## PR Checklist

```
[x] PR title includes Task ID — [P-004] feat(storage): add S3 storage provider
[x] PR description filled out on GitHub (What changed / How to test / Task)
[x] Base branch set to develop-aws (NOT develop, NOT main)
[x] Reviewer assigned — Aditya Bhavsar
[ ] GitHub Actions green                                    ← confirm after push
[ ] Squash merged to develop-aws                             ← after approval
[ ] Feature branch deleted after merge (local + remote)      ← after merge
[ ] Tracker updated: Status=Done, Actual Hours, Completion Date, PR Link

[x] Type hints on all new/modified functions
[x] Google-style docstrings on all public functions
[x] .env.example updated (S3_BUCKET, AWS_REGION, S3_PRESIGN_EXPIRY_SECONDS added)
[x] config.py updated (3 new Settings fields, appended after local_storage_base_path)
[x] dependencies.py updated (s3 branch added to provide_storage(), before raise)
[x] No hardcoded provider names / regions / bucket names / channel names in agents/, graph/, api/, core/
[x] No hardcoded API keys or ARNs anywhere
[x] pytest → 337 passed, 1 skipped (both PROVIDER=local default and STORAGE_PROVIDER=s3 variants)
[x] black backend/storage_provider/s3_storage.py tests/test_s3_storage.py → clean
[x] isort backend/storage_provider/s3_storage.py tests/test_s3_storage.py → clean
[x] Branch doc committed to BRANCH_DOCS/AWS_PHASE/ before merge
[x] Cloud-agnostic grep — empty for files touched by this branch (pre-existing hits flagged, not introduced here)
[x] Channel-agnostic grep — empty for files touched by this branch (pre-existing hits flagged, not introduced here)
[x] Secrets never logged or committed — no secrets used by this provider at all
```

---

## Notes / Blockers

```
Known Issues    →  None.

Scope Note      →  This branch does NOT touch backend/api/routes/health.py or
                   backend/api/routes/webhook.py, despite both surfacing in the
                   agnosticism grep checks. Those are pre-existing POC-era
                   violations: health.py reads supabase_* settings directly
                   instead of going through provide_db(); webhook.py hardcodes
                   WhatsApp HMAC verification instead of deferring to a future
                   ChannelProvider. Both are flagged here for visibility —
                   health.py's cloud-agnostic violation needs a small follow-up
                   task (not yet on the tracker); webhook.py's channel coupling
                   is explicitly in scope for P-024 (WhatsApp ChannelProvider).

Blockers        →  None. P-005 (Secrets Manager Provider, also assigned to
                   Devam) depends on P-002 — which Aditya has already merged —
                   so P-005 can start immediately once this PR is in review,
                   no need to wait for this one to merge first.

Links           →  AWS_Phase_Tracker.xlsx (row P-004 — Workstream Overview + Task Tracker)
                   AWS_Deployment_Plan.docx §5 (cloud-agnostic provider layer)
                   BRANCH_DOCS/AWS_PHASE/TEMPLATE.md (template this doc follows)
                   BRANCH_DOCS/AWS_PHASE/feature-abstractions-queue-secrets-channel.md
                     (P-002 — Aditya's ABCs this branch builds alongside)
```

---

*Branch opened: Day 2, Week 1 — Devam Dixit*
*Merged to develop-aws: [Day 3, Week 1 — fill on merge]*
