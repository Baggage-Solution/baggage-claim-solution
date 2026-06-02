# ABC Airline — Baggage Damage Claim WhatsApp AI

**POC Sprint · 3 Weeks · $0 Budget**  
Team: Anoushka · Aditya · Devam

---

## What This Is

A WhatsApp-style AI assistant that lets airline passengers file baggage damage claims
in under 2 minutes — no forms, no queues, no phone calls.

The passenger scans a QR code at the baggage carousel, opens a chat interface,
uploads photos of the damage and their bag tag, and receives an instant decision:
either an approved compensation voucher or a staff review reference number.

**5-agent LangGraph pipeline (all Gemini Flash free tier):**

```
A1 Conversation  → talks to the passenger, manages the flow
A2 Vision        → analyses damage photos, detects luxury bags
A3 OCR           → reads the bag tag (flight number, PNR, bag ID)
A4 Decision      → fraud checks, routing: Lane 1 (auto) or Lane 2 (staff)
A5 Notification  → sends the result, updates Supabase, pushes SSE event
```

---

## Quick Start — Full Setup in Under 15 Minutes

### 1. Clone the repo

```bash
git clone https://github.com/<org>/baggage-claim-solution.git
cd baggage-claim-solution
```

### 2. Create virtual environment

```bash
# Mac / Linux
python -m venv venv && source venv/bin/activate

# Windows — Command Prompt
python -m venv venv && venv\Scripts\activate

# Windows — Git Bash (recommended)
python -m venv venv && source venv/Scripts/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment

```bash
cp .env.example .env
```

Open `.env` and fill in these three values (everything else has safe defaults):

```bash
GEMINI_API_KEY=<YOUR_GEMINI_API_KEY>
SUPABASE_URL=https://<YOUR_PROJECT_REF>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<YOUR_SUPABASE_SERVICE_ROLE_KEY>
```

**Get your keys (both free):**
- Gemini API key → https://aistudio.google.com/app/apikey (free, no credit card)
- Supabase → https://supabase.com → New project → Settings → API

### 5. Set up the Supabase database

In the Supabase dashboard → SQL Editor → paste and run this:

```sql
-- Claims table
CREATE TABLE IF NOT EXISTS claims (
    id TEXT PRIMARY KEY,
    pnr TEXT,
    bag_id TEXT,
    flight_number TEXT,
    damage_types JSONB DEFAULT '[]',
    severity_score FLOAT DEFAULT 0.0,
    is_luxury BOOLEAN DEFAULT FALSE,
    brand TEXT,
    compensation FLOAT DEFAULT 0.0,
    final_compensation FLOAT DEFAULT 0.0,
    fraud_score FLOAT DEFAULT 0.0,
    fraud_flags JSONB DEFAULT '[]',
    routing_lane INTEGER,
    voucher_code TEXT,
    status TEXT DEFAULT 'PENDING',
    agent_id TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Image hashes table (pHash fraud detection)
CREATE TABLE IF NOT EXISTS image_hashes (
    id BIGSERIAL PRIMARY KEY,
    pnr TEXT NOT NULL,
    phash TEXT NOT NULL,
    claim_id TEXT REFERENCES claims(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_image_hashes_pnr ON image_hashes(pnr);
CREATE INDEX IF NOT EXISTS idx_claims_pnr ON claims(pnr);
CREATE INDEX IF NOT EXISTS idx_claims_status ON claims(status);
```

### 6. Run the backend

```bash
make run
# OR directly:
uvicorn backend.main:app --reload --port 8000
```

Verify it's up:
```bash
curl http://localhost:8000/health
# {"status":"ok","service":"baggage-claim-ai","configured":{"gemini":true,"supabase":true}}
```

Swagger UI → http://localhost:8000/docs

### 7. Run the frontend simulator

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 — the WhatsApp simulator is ready.

### 8. Run the tests

```bash
make test
# OR:
pytest tests/ -v
# Expected: all tests pass, 0 failures
```

---

## System Architecture

```
frontend/
  src/
    App.jsx                     Root simulator (/)
    pages/Simulator.jsx         Full claim page (/simulator) — QR deep link target
    pages/Dashboard.jsx         Staff review dashboard (/dashboard)
    components/
      ChatHeader.jsx
      ChatWindow.jsx
      ChatInput.jsx
      MessageBubble.jsx
      ClaimResultCard.jsx       Lane 1 voucher / Lane 2 'Under Review'
      ImageUploadPreview.jsx
      ManualTagEntry.jsx
    hooks/useClaimFlow.js       Full conversation state machine

backend/
  main.py                       FastAPI app entry point + CORS
  config.py                     All settings via pydantic-settings (reads .env)
  dependencies.py               DI container — provide_llm(), provide_vision(), etc.

  agents/
    base_agent.py               Abstract BaseAgent
    a1_conversation.py          Conversation + conversation step machine
    a2_vision.py                Damage analysis + luxury detection
    a3_ocr.py                   Bag tag OCR + PNR/bag ID validation
    a4_decision.py              Fraud checks + Lane 1/2 routing + DB save
    a5_notification.py          Voucher generation + SSE push + DB status update

  graph/
    state.py                    ClaimState dataclass (flows through all agents)
    orchestrator.py             LangGraph 5-node pipeline + MemorySaver

  llm_provider/
    base.py                     LLMProvider ABC
    gemini_llm.py               Gemini 2.5 Flash (chat)

  vision_provider/
    base.py                     VisionProvider ABC
    gemini_vision.py            Gemini 2.5 Flash (multimodal — damage + brand)

  ocr_provider/
    base.py                     OCRProvider ABC
    gemini_ocr.py               Gemini 2.5 Flash (bag tag OCR)

  db/
    base.py                     DBProvider ABC
    supabase_client.py          Supabase (save_claim, update_status, fraud queries)

  storage_provider/
    base.py                     StorageProvider ABC
    local_storage.py            Local disk (./data/uploads)

  api/routes/
    health.py                   GET /health
    webhook.py                  POST /webhook · POST /upload · GET /events/{id}
    decision.py                 POST /decision (dashboard approve/reject)
    qr.py                       GET /qr/generate · GET /qr/poster

  core/
    exceptions.py               AppError hierarchy
    logging.py                  Structured JSON logging + request_id tracing
    masking.py                  PII redaction (PNR, bag ID, card numbers)
    middleware.py               RequestContextMiddleware
    prompt_loader.py            JSON prompt template loader

  prompts/
    a1_conversation.json        8-step conversation prompts for A1
    a4_decision.json            Decision explanation prompts
    a5_notification.json        Lane 1 + Lane 2 passenger messages

tests/
  test_smoke_t001_t016.py       Full sprint coverage smoke tests
  test_integration.py           Lane 1 + Lane 2 end-to-end (T-020)
  test_a1_agent.py              A1 conversation unit tests
  test_a2_vision.py             A2 vision node unit tests
  test_a3_ocr_agent.py          A3 OCR node unit tests
  test_a4_decision.py           A4 routing scenario tests (all 5 scenarios)
  test_a5_notification.py       A5 SSE + DB tests
  test_supabase_db.py           Supabase client unit tests
  fixtures/
    damaged/                    Test luggage damage images
    bag_tags/                   Test bag tag images
```

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| GET | `/health` | Server health + provider config status |
| POST | `/webhook` | Main entry — receives message + image paths |
| POST | `/upload` | Upload damage / tag photo, returns local path |
| GET | `/events/{session_id}` | SSE stream — real-time claim result push |
| GET | `/claims/pending` | Dashboard — list AWAITING_REVIEW claims |
| POST | `/decision` | Dashboard — approve / reject / modify claim |
| GET | `/qr/generate` | Generate QR code PNG |
| GET | `/qr/poster` | Generate printable A4 PDF poster |
| GET | `/docs` | FastAPI Swagger UI — all endpoints documented |

**POST /webhook request:**
```json
{
  "session_id": "unique-session-id",
  "message": "passenger text message",
  "image_paths": ["data/uploads/damage_01.jpg", "data/uploads/bag_tag.jpg"],
  "conversation_step": "greeting",
  "conversation_history": []
}
```

**POST /webhook response:**
```json
{
  "session_id": "unique-session-id",
  "reply": "A1 passenger-facing response",
  "claim_id": "CLM-20260526-A2E2",
  "routing_lane": 1,
  "voucher_code": "VCH-18B40C50",
  "conversation_step": "result",
  "re_request_tag": false,
  "re_request_damage": false,
  "error": null
}
```

---

## Claim Routing Logic

```
Lane 1 (auto-approve) — ALL of:
  compensation_estimate ≤ $100
  is_luxury = False
  fraud_score < 0.5

Lane 2 (staff review) — ANY of:
  compensation_estimate > $100
  is_luxury = True (Rimowa, Louis Vuitton, Tumi, Brics, etc.)
  fraud_score ≥ 0.5 (pHash duplicate OR high-frequency claimer)
```

**Fraud checks:**
- **pHash duplicate** — perceptual hash of each damage photo vs DB hashes for same PNR. Hamming distance < 10 → flagged.
- **High frequency** — 3+ claims from same PNR in last 30 days → flagged.

All thresholds configurable in `.env` without code changes.

---

## Test Scenarios (Demo Data)

Three scenarios to run in order for a mentor demo:

### Scenario A — Lane 1: Standard Bag, Auto-Approve

```
Upload:  tests/fixtures/damaged/damaged_01.jpg  (cracked shell)
         tests/fixtures/bag_tags/clear_tag_01.jpg
Expected: routing_lane=1, voucher VCH-XXXXXXXX displayed in simulator
DB:      claims table → status=APPROVED
```

### Scenario B — Lane 2: Luxury Bag, Staff Review

```
Upload:  tests/fixtures/damaged/luxury_01.jpg  (Rimowa suitcase)
         tests/fixtures/bag_tags/clear_tag_01.jpg
Expected: routing_lane=2, 'Under Review' card in simulator
DB:      claims table → status=AWAITING_REVIEW
Dashboard: claim appears at http://localhost:5173/dashboard
           → Approve → status=RESOLVED, voucher issued
```

### Scenario C — Retry: Blurry Tag Photo

```
Upload:  tests/fixtures/damaged/damaged_01.jpg  (damage photo)
         any small/dark image as the tag photo
Expected: Bot asks passenger to retake the tag photo
          routing_lane=null (A4 skipped)
          Re-upload a clear tag → full pipeline continues
```

---

## Swap Any Provider — Zero Code Changes

```bash
# Switch LLM to Claude (implement claude_llm.py first)
LLM_PROVIDER=claude uvicorn backend.main:app --reload

# Switch Vision to YOLOv8 (implement yolov8_vision.py first)
VISION_PROVIDER=yolov8 uvicorn backend.main:app --reload

# Switch OCR to PaddleOCR (implement paddleocr.py first)
OCR_PROVIDER=paddleocr uvicorn backend.main:app --reload
```

No changes to `agents/`, `orchestrator.py`, or any business logic.
Only `dependencies.py` routes to the new provider based on the env var.

---

## QR Code — Mobile Demo

Generate a QR code pointing to your machine (use ngrok for external access):

```bash
# Local testing (same machine)
curl "http://localhost:8000/qr/generate?airport=T3&terminal=B" --output qr_local.png

# With ngrok (mobile testing — phone on different network)
ngrok http 5173
# Copy the https://xxxx.ngrok.io URL, then:
curl "http://localhost:8000/qr/generate?airport=T3&terminal=B&host=https://xxxx.ngrok.io" --output qr_mobile.png

# Generate printable A4 poster PDF
curl "http://localhost:8000/qr/poster?airport=T3&terminal=B" --output poster.pdf
```

Scan the QR with your phone → simulator opens pre-filled with airport context → claim flow auto-starts.

---

## Environment Variables Reference

See `.env.example` for all variables with descriptions.

| Variable | Default | Description |
|---|---|---|
| `GEMINI_API_KEY` | — | Required. From https://aistudio.google.com |
| `SUPABASE_URL` | — | Required. From Supabase project settings |
| `SUPABASE_SERVICE_ROLE_KEY` | — | Required. Bypasses RLS for backend writes |
| `GEMINI_MODEL` | `gemini-2.5-flash` | LLM model |
| `GEMINI_VISION_MODEL` | `gemini-2.5-flash` | Vision model |
| `LANE1_MAX_COMPENSATION_USD` | `100` | Auto-approve threshold |
| `FRAUD_PHASH_THRESHOLD` | `10` | Hamming distance for duplicate detection |
| `MAX_CLAIMS_PER_PASSENGER` | `3` | Max claims per PNR in window |
| `CLAIM_FREQUENCY_WINDOW_DAYS` | `30` | Fraud lookback window |
| `IMAGEHASH_ENABLED` | `true` | Toggle pHash fraud check |

Never commit `.env` — it is in `.gitignore`.

---

## Make Commands

```bash
make run     # Start backend server on :8000
make test    # Run full pytest suite
make lint    # Run black + isort on backend/
make clean   # Remove __pycache__ and .pyc files
```

---

## Contributing

See `CONTRIBUTING.md` for branch naming, commit format, PR rules, and code standards.

Branch pattern: `feature/T-XXX-short-desc` · `chore/desc` · `integration/week-N-desc`  
All branches merge to `develop` via PR. Never push directly to `main`.  
Per-branch docs in `BRANCH_DOCS/` — template at `BRANCH_DOCS/TEMPLATE.md`.
