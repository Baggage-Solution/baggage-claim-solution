# Feature Branch: unified-p006-p010-anoushka-aditya-devam

## Branch Metadata

| Field | Value |
|---|---|
| Branch Name | `feature/unified-p006-p010-anoushka-aditya-devam` |
| Task IDs | P-006, P-007, P-008, P-009, P-010 |
| Workstream | Messaging Infra · Application Refactor · Build & Containerise |
| Authors | Anoushka (P-007, P-009) · Aditya (P-006, P-008) · Devam (P-008, P-010) |
| Reviewer | All three |
| Target Merge | Week 1 Day 5 (MS-3 sync) |
| Status | Ready for Review |

## Objective

Five tasks that together complete the Week 1 application refactor and production
containerisation. Delivered as a single unified branch to eliminate inter-task
merge conflicts and speed up the MS-3 review sync.

**What this branch does:**

- **P-006** (Aditya): SQS QueueProvider — already existed, test coverage confirmed via `requirements-dev.txt` adding `moto[all]`.
- **P-007** (Anoushka + Devam): Webhook decoupling — `POST /webhook` enqueues to SQS and returns `{accepted: true}` in <500ms. Memory-queue dev flow preserved 100%.
- **P-008** (Aditya + Devam): `backend/worker.py` — long-poll loop, SIGTERM graceful drain, `process_job` pipeline + ack.
- **P-009** (Anoushka): Simulator feature flag — `ENABLE_SIMULATOR` env var gates `/uploads` mount and simulator React routes. `/dashboard` always available.
- **P-010** (Devam): Production `Dockerfile` + `.dockerignore` + `deploy/taskdef-api.json` + `deploy/taskdef-worker.json`.

## Files Changed

### Created / Modified

| File | Task | Change |
|---|---|---|
| `backend/api/routes/webhook.py` | P-007 | Enqueue-and-return SQS path; inline dev path preserved |
| `backend/worker.py` | P-008 | NEW — long-poll worker entrypoint |
| `backend/config.py` | P-009 | Added `enable_simulator: bool = False` field |
| `backend/main.py` | P-009 | Conditional `/uploads` mount on `settings.enable_simulator` |
| `frontend/src/App.jsx` | P-009 | `VITE_ENABLE_SIMULATOR` flag; `SimulatorDisabledPage`; `DevModeBanner`; React Router |
| `.env.example` | P-009 | Added `ENABLE_SIMULATOR` + `VITE_ENABLE_SIMULATOR` entries |
| `Dockerfile` | P-010 | NEW — single-stage, python:3.11-slim, dual API/worker CMD |
| `.dockerignore` | P-010 | NEW — excludes tests/, frontend/, .env*, BRANCH_DOCS/, .git/ |
| `deploy/taskdef-api.json` | P-010 | NEW — ECS API task definition template |
| `deploy/taskdef-worker.json` | P-010 | NEW — ECS worker task definition template (command override) |
| `Makefile` | P-008 | Added `make worker` target |
| `requirements-dev.txt` | P-006/P-011 | NEW — `moto[all]` for test isolation |
| `tests/test_webhook_p007.py` | P-007 | NEW — SQS path, memory path, HMAC, payload serialisation |
| `tests/test_worker_p008.py` | P-008 | NEW — state rebuild, process_job success/failure/no-ack |
| `tests/test_simulator_flag_p009.py` | P-009 | NEW — config flag, mount gate, dashboard reachability |
| `tests/test_dockerfile_p010.py` | P-010 | NEW — Dockerfile structural validation |

## Cloud-Agnostic Boundary

```bash
# Must return ZERO results — AWS SDK never imported in business logic
grep -rn 'boto3\|aws_\|anthropic\|supabase\|google.' backend/agents/ backend/graph/ backend/api/ backend/core/
```

`webhook.py` only imports `QueueProvider` via `provide_queue()`. `worker.py` only imports `ClaimOrchestrator` and `QueueProvider` / `ChannelProvider` interfaces. No provider-specific imports.

## Channel-Agnostic Boundary

```bash
# Must return ZERO results
grep -rn 'whatsapp\|meta\|telegram\|twilio\|sms' backend/agents/ backend/graph/ backend/api/ backend/core/
```

`worker.py` uses `ChannelProvider` interface only. A5 still uses SSE queue via `WebhookChannelProvider` (unchanged — P-024 will add `WhatsAppChannelProvider`).

## Key Design Decisions

**P-007 — Backward compat via isinstance check:**
The webhook handler detects `InMemoryQueueProvider` by type and runs the pipeline inline. This is intentional: the simulator has no polling loop and depends on the synchronous response. In production, any non-in-memory queue (SQS) triggers the enqueue path. This avoids a config-string comparison that could silently fail on typos.

**P-008 — Same Docker image for API and worker:**
The `command` field in the ECS task definition selects the entrypoint. This means one image build per deploy, no image drift between API and worker, and trivial rollback (repoint both services to the previous image tag).

**P-009 — Code not deleted:**
The simulator JSX is not removed. `VITE_ENABLE_SIMULATOR=false` renders `<SimulatorDisabledPage />` instead. The actual simulator component is still imported and available for offline demos. Removing it would break `useClaimFlow` and `ChatHeader` imports that the Dashboard also uses.

**P-010 — No local Docker build:**
Office laptops cannot run Docker. GitHub Actions CI (P-014) is the only builder. `tests/test_dockerfile_p010.py` validates the Dockerfile structurally without running `docker build`.

## Environment Variables Added

| Variable | Default | Description |
|---|---|---|
| `ENABLE_SIMULATOR` | `false` | Backend: gate `/uploads` mount |
| `VITE_ENABLE_SIMULATOR` | (not set) | Frontend: gate simulator routes |

## How to Test Locally

```bash
# Dev mode — simulator active, in-memory queue (unchanged from before)
ENABLE_SIMULATOR=true make run

# Worker (separate terminal) — requires SQS_QUEUE_URL in .env
QUEUE_PROVIDER=sqs make worker

# Test suite
pip install -r requirements-dev.txt
pytest tests/ -v -k "p006 or p007 or p008 or p009 or p010 or abstractions or sqs"
```

## Acceptance Criteria

| Task | Criterion | Verified |
|---|---|---|
| P-006 | `moto[all]` test suite runs; SQS enqueue/dequeue/ack round-trip | ✅ (existing test_sqs_queue.py) |
| P-007 | SQS: POST returns `{accepted: true}` in <500ms. Memory: returns full WebhookResponse | ✅ test_webhook_p007.py |
| P-008 | `make worker` drains 5 messages from mocked queue; SIGTERM handled | ✅ test_worker_p008.py |
| P-009 | `ENABLE_SIMULATOR=true` → simulator works. `false` → `/simulator` shows disabled page, `/dashboard` reachable | ✅ test_simulator_flag_p009.py |
| P-010 | Dockerfile: python:3.11-slim, port 8000, dual CMD. taskdef-worker.json has command override | ✅ test_dockerfile_p010.py |