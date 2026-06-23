# AGENTS.md
> Operating manual for AI coding agents working in this repository.
> Project: ABC Airline — Baggage Damage Claim AI · AWS Production Phase

---

## 1. Mission

Process baggage damage claims end-to-end via WhatsApp. Passenger sends a photo + bag tag → 5-agent LangGraph pipeline (intent → vision → OCR → decision → notification) → voucher reply, all on AWS in under 30 seconds.

This phase migrates the working POC (Gemini + Supabase + local storage + React simulator) to AWS production (Bedrock + S3 + Secrets Manager + SQS + Meta Cloud API via N8N) while keeping every provider swappable behind ABCs.

---

## 2. Architecture Pillars (the three rules that override everything else)

```
1. CLOUD-AGNOSTIC      — agents/graph/api/core MUST NOT import boto3 or any cloud SDK
2. CHANNEL-AGNOSTIC    — agents/graph/api/core MUST NOT mention WhatsApp/Meta/Telegram
3. MODEL-AGNOSTIC      — agents/graph/api/core MUST NOT hardcode model IDs
```

If a proposed change violates any of these three, STOP. Redesign so it doesn't. There is always a clean way through the abstraction layer.

---

## 3. Tech Stack

```
Backend     →  Python 3.11+, FastAPI, LangGraph, Pydantic v2
LLM         →  AWS Bedrock (Claude Sonnet 4 by default) — swappable
Vision/OCR  →  AWS Bedrock multimodal (same model) — swappable
Storage     →  AWS S3 — swappable
Secrets     →  AWS Secrets Manager — swappable
Queue       →  AWS SQS — swappable
Database    →  Supabase Postgres (Phase 1) → RDS (Phase 2)
Channel     →  Meta WhatsApp Cloud API via N8N relay on EC2 — swappable
Container   →  ECS Fargate (api + worker services, same image)
Edge        →  API Gateway HTTP API + internal ALB
CI/CD       →  GitHub Actions (build + ECR push + ECS UpdateService)
Frontend    →  React 18 + Vite (dashboard for Lane 2 review staff;
               simulator preserved behind ENABLE_SIMULATOR feature flag)
Observability → CloudWatch Logs + Metrics + Alarms + SNS
```

---

## 4. Repo Layout

```
baggage-claim-solution/
├── backend/
│   ├── agents/              ← 5 LangGraph agents (a1_intent .. a5_notification)
│   │                          ❌ NO boto3, anthropic SDK, google sdk, supabase imports
│   │                          ❌ NO whatsapp/meta/telegram refs
│   │                          ❌ NO hardcoded model IDs
│   ├── api/                 ← FastAPI routes (webhook, qr, dashboard)
│   │                          ❌ same forbidden imports as agents/
│   ├── core/                ← claim state, request context, shared types
│   │                          ❌ same forbidden imports as agents/
│   ├── graph/               ← LangGraph wiring (nodes, edges, conditional routing)
│   │                          ❌ same forbidden imports as agents/
│   ├── llm_provider/        ← LLMProvider ABC + gemini_llm.py + bedrock_llm.py
│   │                          ✅ boto3 / anthropic SDK allowed HERE only
│   ├── vision_provider/     ← VisionProvider ABC + gemini_vision.py + bedrock_vision.py
│   ├── ocr_provider/        ← OCRProvider ABC + gemini_ocr.py + bedrock_ocr.py
│   ├── storage_provider/    ← StorageProvider ABC + local_storage.py + s3_storage.py
│   ├── queue_provider/      ← QueueProvider ABC + inmemory_queue.py + sqs_queue.py
│   ├── secrets_provider/    ← SecretsProvider ABC + env_secrets.py + aws_secrets.py
│   ├── channel_provider/    ← ChannelProvider ABC + webhook_channel.py + whatsapp_channel.py
│   │                          ✅ "whatsapp"/"meta" allowed HERE only (and N8N JSON)
│   ├── db/                  ← Supabase / SQL access (already abstracted via DBProvider)
│   ├── prompts/             ← LLM prompt templates (Jinja2)
│   ├── config.py            ← Pydantic Settings — single source of truth for all knobs
│   ├── dependencies.py      ← Factory functions: provide_llm() / provide_storage() / ...
│   ├── main.py              ← FastAPI app + lifespan (loads secrets, wires providers)
│   └── worker.py            ← SQS long-poll worker (Week 1 — added by P-008)
├── frontend/                ← React + Vite (dashboard always available;
│                              simulator gated by VITE_ENABLE_SIMULATOR)
├── tests/                   ← pytest. moto for AWS mocks. NEVER real AWS in CI.
├── deploy/                  ← Task definitions, GH workflow, N8N JSON, dashboards
├── BRANCH_DOCS/             ← Per-branch documentation
│   ├── AWS_PHASE/           ← Current phase — drop your branch doc here
│   ├── WEEK1_DOCS/ ..       ← POC phase (preserved, do not modify)
│   └── TEMPLATE.md          ← POC template (preserved)
├── docs/                    ← Architecture diagrams, decision records
├── CONTRIBUTING.md          ← Git + coding rules (READ BEFORE OPENING A PR)
├── AGENTS.md                ← This file
├── CLAUDE.md                ← Same content as this file (Claude Code convention)
└── README.md                ← Project overview, local setup
```

---

## 5. The Provider Pattern (read this twice)

Every external dependency goes through the same 5-step pattern:

```python
# 1. ABC in backend/<thing>_provider/base.py
class LLMProvider(ABC):
    @abstractmethod
    async def chat(self, messages: list[Message], **opts) -> Response: ...

# 2. Concrete impls in backend/<thing>_provider/<name>.py
class BedrockLLM(LLMProvider):
    def __init__(self, model_id: str, region: str): ...
    async def chat(self, messages, **opts) -> Response:
        return await asyncio.to_thread(self._client.invoke_model, ...)

# 3. Factory in backend/dependencies.py
def provide_llm(settings: Settings = Depends(get_settings)) -> LLMProvider:
    match settings.llm_provider:
        case "gemini":  return GeminiLLM(settings.gemini_api_key, settings.gemini_model)
        case "bedrock": return BedrockLLM(settings.bedrock_llm_model, settings.bedrock_region)
        case _: raise ValueError(f"Unknown LLM_PROVIDER: {settings.llm_provider}")

# 4. Selection via env var
LLM_PROVIDER=bedrock         # or 'gemini', 'openai', ...

# 5. Agent depends on the ABC ONLY
class A1Intent:
    def __init__(self, llm: LLMProvider):   # ← never type the concrete class
        self._llm = llm
```

**Adding a new provider is always exactly these 5 steps. No exceptions.**

---

## 6. What NOT to Do

```
❌ Never import boto3 in backend/agents/, backend/graph/, backend/api/, backend/core/
❌ Never import google.generativeai or anthropic SDK anywhere outside *_provider/ files
❌ Never reference "whatsapp", "meta", "telegram", "twilio", "sms" outside channel_provider/
❌ Never hardcode model IDs like "anthropic.claude-sonnet-4" — read from Settings
❌ Never hardcode AWS regions, bucket names, ARNs, phone numbers
❌ Never write API keys, tokens, or secrets to .env files committed to git
❌ Never log secret values (even masked — just don't log them)
❌ Never docker build on the dev laptop — GitHub Actions runner is the only builder
❌ Never call real AWS / Meta in pytest — moto + unittest.mock only
❌ Never push directly to develop-aws, develop, or main — PRs only
❌ Never merge a PR without 1 reviewer approval + green CI
❌ Never use print() in committed code — logging.getLogger(__name__)
❌ Never exceed 300 lines in a single Python file — split into modules
❌ Never skip the branch doc — every PR has BRANCH_DOCS/AWS_PHASE/<branch>.md
```

---

## 7. Common Tasks

### Adding a new provider (e.g. switching LLM to OpenAI later)

```
1. Create backend/llm_provider/openai_llm.py implementing LLMProvider ABC
2. Add 'openai' case to provide_llm() in backend/dependencies.py
3. Add openai_api_key, openai_model fields to config.py Settings
4. Add OPENAI_API_KEY, OPENAI_MODEL entries to .env.example
5. Add tests/test_openai_llm.py (mocking the openai client)
6. Set LLM_PROVIDER=openai in env (or secrets) → done
```

### Adding a new agent

```
1. Create backend/agents/aN_<name>.py — subclass of BaseAgent
2. Accept ABC-typed providers in __init__ (LLMProvider, VisionProvider, ...)
3. Wire it into backend/graph/builder.py
4. Add tests/test_aN_<name>.py with mocked providers
5. Update prompts in backend/prompts/aN_<name>.j2
```

### Running tests

```bash
# Default (PROVIDER=local) — uses in-memory + Gemini if API key in env
pytest

# AWS variant — moto-mocked S3/SQS/Secrets, mock.patch'd Bedrock
LLM_PROVIDER=bedrock VISION_PROVIDER=bedrock OCR_PROVIDER=bedrock \
STORAGE_PROVIDER=s3 QUEUE_PROVIDER=sqs SECRETS_PROVIDER=aws_sm \
  pytest

# Specific test file
pytest tests/test_bedrock_llm.py -v
```

### Running locally (POC dev mode)

```bash
# Backend
source venv/Scripts/activate                    # or venv/bin/activate on mac/linux
pip install -r requirements.txt
uvicorn backend.main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend && npm install && npm run dev
```

### Running locally (cloud-targeting mode, no real AWS)

```bash
# Set all PROVIDERs to aws variants; moto / mocks make this safe
LLM_PROVIDER=bedrock VISION_PROVIDER=bedrock OCR_PROVIDER=bedrock \
STORAGE_PROVIDER=s3 QUEUE_PROVIDER=sqs SECRETS_PROVIDER=aws_sm \
  uvicorn backend.main:app --reload --port 8000
```

### Formatting + linting

```bash
black backend/ tests/
isort backend/ tests/
# Run before every commit. Pre-commit hook recommended.
```

---

## 8. Where Secrets Live

```
Local dev (developer laptop):
  → .env file (gitignored) or shell env vars
  → SECRETS_PROVIDER=env  (default, reads from os.environ)

Production (AWS):
  → AWS Secrets Manager
  → Secret name: baggage-claim/prod
  → Contents: single JSON blob with keys (SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY,
              META_ACCESS_TOKEN, META_APP_SECRET, N8N_WEBHOOK_TOKEN, ...)
  → Loaded ONCE at startup by AWSSecretsManagerProvider, cached in Settings
  → SECRETS_PROVIDER=aws_sm
```

**Never** write secrets to disk in production. **Never** log them. **Never** commit them.

---

## 9. Observability

All logs go to CloudWatch via the awslogs ECS log driver.
Log group: `/aws/ecs/baggage-claim`
Every log line MUST include `request_id` (injected by `RequestContextMiddleware` in `backend/core/middleware.py`).

```python
import logging
log = logging.getLogger(__name__)

# Inside a handler — request_id is automatically attached by the middleware
log.info("processing claim", extra={"claim_id": claim_id, "lane": lane})
```

CloudWatch Logs Insights query for a single request:

```
fields @timestamp, @message, request_id, claim_id
| filter request_id = "abc-123-def"
| sort @timestamp asc
```

---

## 10. Quick Reference Card

| Need | File |
|---|---|
| New provider | `backend/<thing>_provider/<name>.py` + `dependencies.py` + `config.py` |
| New env var | `config.py` Settings field + `.env.example` |
| New agent | `backend/agents/aN_<name>.py` + `graph/builder.py` |
| New API route | `backend/api/routes/<name>.py` registered in `main.py` |
| Branch rules | `CONTRIBUTING.md` §1 |
| Commit format | `CONTRIBUTING.md` §2 |
| Merge gates | `CONTRIBUTING.md` §8 |
| Branch doc template | `BRANCH_DOCS/AWS_PHASE/TEMPLATE.md` |
| Tracker | `AWS_Phase_Tracker.xlsx` (top-level) |

---

## 11. When in Doubt

1. Re-read §2 (the three agnosticism rules)
2. Find the closest existing provider impl and copy its structure
3. Check `BRANCH_DOCS/WEEK1_DOCS/` (POC) for examples of branch docs
4. Ask in the team chat — never guess at architecture
5. Never create a new top-level folder without team consensus

---

*Last updated: AWS Production Phase Day 1*
