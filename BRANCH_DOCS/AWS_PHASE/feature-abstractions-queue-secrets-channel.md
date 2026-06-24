# BRANCH: feature/abstractions-queue-secrets-channel

---

## Branch Metadata

```
Branch Name        →  feature/abstractions-queue-secrets-channel
Task ID            →  P-002
Workstream         →  Abstractions
Author             →  Aditya
Reviewer           →  Devam
Start Date         →  Day 2, Week 1
Target Merge Date  →  Day 2, Week 1
Actual Merge Date  →  [Fill on completion]
Status             →  In Progress
```

---

## Objective

**What does this branch do?**
Adds three new abstraction layers under `backend/` — `QueueProvider`, `SecretsProvider`,
and `ChannelProvider` — each with an ABC (`base.py`) plus a default local implementation
(`InMemoryQueueProvider`, `EnvSecretsProvider`, `WebhookChannelProvider`). All three are
registered in `dependencies.py` via new factory branches, following the exact pattern
already established by `storage_provider/`. No AWS or WhatsApp imports are introduced.

**Why is it needed?**
These three ABCs are the contract that every later Batch 2 and Batch 3 task builds on:
P-006 (SQS queue impl), P-005 (Secrets Manager impl), and P-024 (WhatsApp channel impl)
all implement these interfaces rather than being built ad hoc. Establishing the
abstraction first — cloud-agnostic and channel-agnostic, with a working local default —
means the application code (agents/, graph/, api/, core/) never needs to know whether
it's running against an in-memory queue or SQS, env vars or Secrets Manager, SSE or
WhatsApp.

---

## Local Setup

```bash
git checkout develop-aws && git pull origin develop-aws
git checkout -b feature/abstractions-queue-secrets-channel

mkdir -p backend/queue_provider backend/secrets_provider backend/channel_provider
touch backend/queue_provider/__init__.py
touch backend/secrets_provider/__init__.py
touch backend/channel_provider/__init__.py

pip install -r requirements.txt -r requirements-dev.txt
```

---

## Technical Approach

**Files Created:**

| File | Purpose |
|---|---|
| `backend/queue_provider/__init__.py` | Package marker |
| `backend/queue_provider/base.py` | `QueueProvider` ABC — `enqueue` / `dequeue` / `ack` |
| `backend/queue_provider/in_memory_queue.py` | `InMemoryQueueProvider` — deque-backed local default |
| `backend/secrets_provider/__init__.py` | Package marker |
| `backend/secrets_provider/base.py` | `SecretsProvider` ABC — `get(name)` |
| `backend/secrets_provider/env_secrets.py` | `EnvSecretsProvider` — reads from process env / `.env` |
| `backend/channel_provider/__init__.py` | Package marker |
| `backend/channel_provider/base.py` | `ChannelProvider` ABC — `send_message(session_id, text, attachments)` |
| `backend/channel_provider/webhook_channel.py` | `WebhookChannelProvider` — wraps the existing SSE queue used by the simulator |
| `tests/test_abstractions_providers.py` | Unit tests for all three local default impls + factory branches |

**Files Modified:**

| File | What changed |
|---|---|
| `backend/dependencies.py` | Added `provide_queue()`, `provide_secrets()`, `provide_channel()` factory functions, each `@lru_cache` + env-driven branch, matching the existing `provide_storage()` pattern |
| `backend/config.py` | Added `queue_provider`, `secrets_provider`, `channel_provider` fields to `Settings`, defaulting to `memory` / `env` / `webhook` |
| `.env.example` | Added `QUEUE_PROVIDER=memory`, `SECRETS_PROVIDER=env`, `CHANNEL_PROVIDER=webhook` |

**Provider/Abstraction Used:**

```
Implements:    QueueProvider ABC      → InMemoryQueueProvider (local default)
               SecretsProvider ABC    → EnvSecretsProvider (local default)
               ChannelProvider ABC    → WebhookChannelProvider (local default)
Via:           dependencies.py factory branches (provide_queue / provide_secrets / provide_channel)
Injected by:   QUEUE_PROVIDER / SECRETS_PROVIDER / CHANNEL_PROVIDER env vars
Agent imports: None — agents/, graph/, api/, core/ are untouched in this branch
```

**Cloud-Agnostic Boundary:**

```
boto3 imports allowed in:    N/A — no AWS provider implementations in this branch
boto3 imports FORBIDDEN in:  backend/agents/  backend/graph/  backend/api/  backend/core/
                              (also: backend/queue_provider/, backend/secrets_provider/,
                               backend/channel_provider/ — these contain ONLY the local
                               defaults in this branch; AWS impls land in P-005/P-006)

Grep check:
grep -rn "boto3\|aws_\|anthropic\|supabase\|google\." \
  backend/agents/ backend/graph/ backend/api/ backend/core/
```

Result of the grep on this branch: **empty.**

**Channel-Agnostic Boundary:**

```
WhatsApp/Meta references allowed in:    N/A — no WhatsApp implementation in this branch
                                         (lands in P-024 as whatsapp_channel.py)
WhatsApp/Meta refs FORBIDDEN in:        backend/agents/  backend/graph/  backend/api/  backend/core/

Grep check:
grep -rn "whatsapp\|meta\|telegram\|twilio\|sms" \
  backend/agents/ backend/graph/ backend/api/ backend/core/
```

Result of the grep on this branch: **empty.**

**Key Design Decisions:**

```
1. NAMING MIRRORS storage_provider/ EXACTLY
   Each new package follows the established three-file shape: __init__.py, base.py (ABC),
   and one concrete local-default class. No deviation, so future contributors (and AI
   coding agents reading AGENTS.md) recognise the pattern instantly.

2. InMemoryQueueProvider CLASS NAME IS LOAD-BEARING
   P-007 (webhook decoupling) explicitly isinstance-checks for InMemoryQueueProvider to
   decide whether to run the LangGraph pipeline inline (dev mode) or push to a real queue.
   Renaming this class without coordinating with Devam would silently break that
   backward-compat branch.

3. WebhookChannelProvider WRAPS THE EXISTING SSE QUEUE, DOES NOT REPLACE IT
   backend/agents/a5_notification.py already maintains a module-level _sse_queues dict and
   get_or_create_queue(session_id) helper that the simulator polls. Rather than introduce a
   second, parallel notification mechanism, WebhookChannelProvider.send_message() calls
   get_or_create_queue() and does queue.put() — identical behaviour to what A5 does today.
   A5 itself is NOT refactored to call self._channel.send_message() in this branch — that
   refactor is explicitly P-024's scope. This branch only makes the abstraction available;
   it does not yet rewire the agent to use it.

4. KNOWN BOUNDARY VIOLATION (FLAGGED, NOT FIXED HERE)
   WebhookChannelProvider imports get_or_create_queue from backend.agents.a5_notification.
   This is a channel_provider → agents import, which is backwards from the intended
   dependency direction (agents should depend on providers, never the reverse). It is a
   deliberate, scoped exception to avoid touching A5 in an abstraction-only branch. P-024
   should resolve this by moving _sse_queues / get_or_create_queue out of a5_notification.py
   and into webhook_channel.py (or a shared sse_registry module), so agents/ no longer
   exposes queue internals for a provider to import.

5. NO boto3 / WHATSAPP IMPORTS ANYWHERE IN THIS BRANCH
   Per the task description, this is pure agnostic abstraction work. AWS-specific
   (aws_secrets.py, sqs_queue.py) and WhatsApp-specific (whatsapp_channel.py)
   implementations are explicitly out of scope — they land in P-005, P-006, and P-024.
```

**Future Swap Path:**

```
QueueProvider:   To switch to SQS: add backend/queue_provider/sqs_queue.py implementing
                 QueueProvider ABC via boto3; set QUEUE_PROVIDER=sqs. (Done in P-006.)

SecretsProvider: To switch to Secrets Manager: add backend/secrets_provider/aws_secrets.py
                 implementing SecretsProvider ABC; set SECRETS_PROVIDER=aws_sm. (Done in P-005.)

ChannelProvider: To switch to WhatsApp: add backend/channel_provider/whatsapp_channel.py
                 implementing ChannelProvider ABC, posting to N8N's outbound webhook; set
                 CHANNEL_PROVIDER=whatsapp. (Done in P-024.)

In all three cases: zero changes required in agents/, graph/, api/, or core/.
```

---

## Dependencies

```
Depends On (Task IDs)      →  P-001 (develop-aws branch must exist)
External Libraries         →  None added (no new third-party packages — pure stdlib: abc, asyncio, collections, uuid, os, logging)
Environment Variables      →  QUEUE_PROVIDER=memory, SECRETS_PROVIDER=env, CHANNEL_PROVIDER=webhook
Secrets Manager Keys       →  None — Secrets Manager itself is not wired until P-005
AWS Resources Required     →  None
IAM Permissions Required   →  None
```

---

## Testing

**How to Test (Manual):**

```bash
# 1. Confirm the three packages exist with the right shape
ls backend/queue_provider/ backend/secrets_provider/ backend/channel_provider/

# 2. Confirm default providers resolve without error
python -c "from backend.dependencies import provide_queue, provide_secrets, provide_channel; \
print(provide_queue(), provide_secrets(), provide_channel())"

# 3. Confirm existing simulator pipeline is unaffected (no env vars changed)
make dev   # or however the local dev server is started
# Send a test claim through the simulator UI — should behave exactly as before
```

**Automated Tests:**

```
tests/test_abstractions_providers.py
```

**Mocking Strategy:**

```
None required — all three providers under test in this branch are local, in-process
implementations (deque, os.environ, asyncio.Queue). No external services, no moto,
no unittest.mock needed. AWS-backed implementations (and their moto/unittest.mock
strategies) are introduced in P-005 and P-006.
```

**Test Data Used:**

```
Inline synthetic payloads only (e.g. {"claim_id": "CLM-001", "message": "hello"}).
No fixture files needed for this branch.
```

**Acceptance Criteria:**

```
✅ pytest tests/ passes — 0 failures, including all pre-existing tests
✅ Existing pipeline (simulator → A1-A5) runs unchanged with default impls
   (QUEUE_PROVIDER=memory, SECRETS_PROVIDER=env, CHANNEL_PROVIDER=webhook)
✅ 3 new provider packages exist, each with ABC + local default impl + DI factory branch
✅ Cloud-agnostic grep — empty
✅ Channel-agnostic grep — empty
```

---

## PR Checklist

```
[x] Type hints on all new functions
[x] Docstrings on all public functions (Google style)
[x] .env.example updated with new vars
[x] config.py updated with new fields
[x] dependencies.py updated with new factory branches
[x] No hardcoded provider/region/bucket/channel names in agents/, graph/, api/, core/
[x] At least 1 test written (tests/test_abstractions_providers.py — no moto/mock needed, pure local impls)
[ ] pytest passes locally with PROVIDER=local AND PROVIDER=aws variants
     (AWS variants don't exist yet for these three — only local defaults ship in P-002)
[x] Secrets never logged or committed
[ ] PR description filled out on GitHub (what, how to test, related task)
[ ] Reviewer assigned (Devam) + GitHub Actions green
```

---

## Notes / Blockers

```
Known Issues    →  WebhookChannelProvider imports get_or_create_queue from
                   backend.agents.a5_notification — a channel_provider → agents
                   dependency, which is backwards from the intended direction.
                   Scoped and deliberate for this branch; flagged for cleanup in P-024
                   (see Key Design Decision #4 above).

Blockers        →  None. P-001 is merged; this branch is unblocked.

Links           →  AWS_Phase2_Tracker.xlsx — Task Tracker row P-002, Branch Doc Template sheet
                   backend/storage_provider/ — the existing pattern this branch mirrors
                   backend/agents/a5_notification.py — SSE queue mechanism wrapped by
                   WebhookChannelProvider
```

---

*Branch opened: Day 2, Week 1 — Aditya*
*Merged to develop-aws: [Day 2, Week 1 — fill on merge]*