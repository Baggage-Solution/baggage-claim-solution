# BRANCH: feature/qr-entry-flow

---

## Branch Metadata

```
Branch Name   →  feature/qr-entry-flow
Task ID       →  T-018
Workstream    →  QR / Entry
Author        →  Aditya
Reviewer      →  Anoushka Vyas
Start Date    →  Day 11, Week 3
Target Merge  →  Day 12, Week 3
Actual Merge  →  Day 12, Week 3
Status        →  Merged
```

---

## Objective

**What does this branch do?**
Generates a static QR code (via the `qrcode` library) that deep-links passengers
directly to the React simulator pre-filled with airport and terminal context.
Adds a dedicated `/simulator` React route that reads those URL params and
auto-starts the claim conversation on scan — no tapping, no typing.
Also generates a printable A4 PDF poster (via `reportlab`) that can be printed
and placed at the baggage carousel.

**Why is it needed?**
The POC's end-to-end demo must show the full passenger journey starting from
a physical QR code at the carousel. Without T-018, the demo starts by the
tester manually opening `localhost:5173` — which does not match the real-world
entry point and breaks the Lane 1 < 2-minute benchmark (time-to-QR-scan is
the clock start). This branch closes the gap between the physical world and
the digital claim flow.

---

## Local Setup

```bash
# Backend
source venv/Scripts/activate           # Git Bash / Windows
# OR
source venv/bin/activate               # macOS / Linux

uvicorn backend.main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev

# Generate QR code (PNG) — open in browser
http://localhost:8000/qr/generate?airport=T3&terminal=B

# Download QR as JSON (base64)
http://localhost:8000/qr/generate?airport=T3&terminal=B&format=json

# Download printable PDF poster
http://localhost:8000/qr/poster?airport=T3&terminal=B

# Test QR scan entry — simulator auto-starts:
http://localhost:5173/simulator?airport=T3&terminal=B&auto=1

# Standard simulator (no auto-start):
http://localhost:5173/simulator

# Agent dashboard (unchanged):
http://localhost:5173/dashboard
```

---

## Technical Approach

### Backend — Files Created

| File | Purpose |
|---|---|
| `backend/api/routes/qr.py` | Two endpoints: `GET /qr/generate` (QR PNG or JSON) and `GET /qr/poster` (A4 PDF). Internal helpers: `_build_simulator_url()`, `_generate_qr_image()`, `_generate_poster_pdf()`. All logic in one file — no business-layer imports, pure generation. |

### Backend — Files Modified

| File | What changed |
|---|---|
| `backend/main.py` | Added `from backend.api.routes import qr`. Added `app.include_router(qr.router)` below the other routers. No other changes — one line + one import. |

### Frontend — Files Created

| File | Purpose |
|---|---|
| `frontend/src/pages/Simulator.jsx` | Dedicated `/simulator` route — mirrors `App.jsx` but adds URL param parsing (`airport`, `terminal`, `auto`). On `auto=1`, fires a silent auto-start trigger to the backend after a 600ms mount delay. Renders a small blue context badge when airport/terminal params are present — helpful for demo and testing. |

### Frontend — Files Modified

| File | What changed |
|---|---|
| `frontend/src/main.jsx` | Added `import Simulator`. Added `<Route path="/simulator" element={<Simulator />} />`. Root `/` route (App) unchanged — backward compatible. |
| `frontend/src/hooks/useClaimFlow.js` | Added `{ airport = null, terminal = null }` options param. Both values forwarded to backend via `airport_context` / `terminal_context` fields in every `/webhook` POST body, so A1 has location context. Auto-start sentinel messages (`[QR_AUTO_START]...`) suppressed from rendering as user chat bubbles. |
| `frontend/vite.config.js` | Added `'/qr': 'http://localhost:8000'` proxy entry so `/qr/generate` and `/qr/poster` work from `localhost:5173` during dev. |

### Tests — Created

| File | Tests |
|---|---|
| `tests/test_qr_entry.py` | 18 tests — `_build_simulator_url` (4), `_generate_qr_image` (3), `GET /qr/generate` PNG (5), `GET /qr/generate` JSON (4), `GET /qr/poster` (4) |

---

## Key Design Decisions

```
1. SEPARATE /simulator ROUTE (not modifying App root)
   App.jsx is the root "/" route — it has no URL param awareness and is
   used in all earlier tests and demos. Creating a new Simulator.jsx page
   at "/simulator" keeps the existing root completely unchanged (zero
   regression risk) while giving T-018 a clean, URL-param-aware entry point.
   Phase 2: when WhatsApp is the real entry channel, /simulator becomes
   the demo-only URL. No refactor needed.

2. AUTO-START SENTINEL PATTERN
   The QR auto-start sends "[QR_AUTO_START] airport=T3 terminal=B" as
   the first message when auto=1 is detected. This is suppressed from
   rendering as a user chat bubble (not shown to the passenger) but IS
   sent to the backend so A1 receives the full context on turn 1.
   Alternative considered: pass context only as webhook body fields.
   Rejected: A1's prompt template takes passenger_message as the primary
   input. Embedding context there is the most reliable path — no prompt
   changes needed.

3. 600MS AUTO-START DELAY
   The setTimeout(600) before firing handleSendText on auto-start ensures
   the chat UI is fully rendered before the first bot reply arrives.
   Without it, the loading spinner can appear before the initial greeting
   bubble renders — looks broken. 600ms is imperceptible to the passenger.

4. QR ERROR CORRECTION LEVEL H (30%)
   ERROR_CORRECT_H used for the QR code. This allows up to 30% of the
   code to be obscured (dirt, damage, partial sticker) and still scan.
   Print context (carousel environment, variable lighting, possible
   damage) warrants maximum error correction over smaller code size.

5. PDF POSTER FALLBACK
   If reportlab is not installed (e.g. minimal CI environment), the
   /qr/poster endpoint logs a warning and falls back to returning the
   QR PNG directly rather than a 500 error. The test suite checks for
   either content type — both are valid responses.

6. AIRPORT/TERMINAL FORWARDED ON EVERY TURN
   airport_context + terminal_context are sent on every /webhook POST,
   not just the first. This is intentional: if the conversation is
   interrupted and resumed (network error, page refresh), context is
   always available to A1 without re-parsing the URL.

7. NO BACKEND CHANGES TO A1 AGENT
   A1's system prompt already includes conversation context from the
   message body. The QR context arrives in passenger_message on turn 1
   and in the conversation_history on subsequent turns — A1 already
   has access to it. No prompt template changes needed for T-018.
   T-019 or T-021 can enhance A1's greeting with explicit location
   instructions if the demo review requires it.
```

---

## QR Entry Flow — End to End

```
Staff prints QR poster (GET /qr/poster?airport=T3&terminal=B)
  → A4 PDF: ABC Airline header + "Baggage Damaged?" + instructions
  → Large QR code (ERROR_CORRECT_H, box_size=12)
  → Footer: "✈  T3  ·  Terminal B"
  → Poster placed at carousel / baggage belt sign

Passenger notices damaged bag
        ↓
Scans QR code with phone camera
  QR encodes: http://<host>/simulator?airport=T3&terminal=B&auto=1
        ↓
Browser opens /simulator?airport=T3&terminal=B&auto=1
  Simulator.jsx mounts
  Reads params: airport="T3", terminal="B", autoStart=true
  Renders initial bot greeting bubble (generic greeting from useState init)
  Blue badge: "✈ T3 · Terminal B" visible top-left
        ↓
  useEffect fires after 600ms
  handleSendText("[QR_AUTO_START] airport=T3 terminal=B")
  → NOT rendered as user bubble
  → POST /webhook { message: "[QR_AUTO_START] airport=T3 terminal=B",
                    airport_context: "T3", terminal_context: "B", ... }
        ↓
A1 receives message + context
  Generates contextual greeting:
  "I can see you're at Terminal B — I'm sorry to hear your bag was damaged.
   Let's get your claim filed quickly. Could you describe what happened?"
        ↓
Chat continues: damage photos → tag photo → confirm → result
  (identical to existing T-013 flow — no changes downstream)
```

---

## QR Code Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `airport` | string | `T3` | Airport code or name embedded in URL and poster footer |
| `terminal` | string | `B` | Terminal letter/number embedded in URL and poster footer |
| `host` | string | `http://localhost:5173` | Base URL of the React simulator — change to ngrok/public URL for mobile testing |
| `format` | string | `png` | `png` returns binary image; `json` returns base64 + metadata |

**Example URLs for different airports:**
```
/qr/generate?airport=BOM&terminal=2&host=https://abc-poc.ngrok.io
/qr/generate?airport=DXB&terminal=A&host=https://abc-poc.ngrok.io
/qr/poster?airport=T3&terminal=B&host=https://abc-poc.ngrok.io
```

---

## Dependencies

```
Depends On          →  T-013 (simulator UI — full conversation flow)
                       qrcode[pil] (already in requirements.txt since T-001 starter)
                       reportlab (new — added to requirements.txt for PDF poster)
External Libraries  →  qrcode[pil]==8.0 (existing)
                       reportlab>=4.0 (new — pure Python, no system deps)
                       Pillow>=11.0.0 (existing — used by qrcode + imagehash)
                       react-router-dom ^7.15.1 (existing — added in T-017)
Environment Vars    →  None new. No env vars added.
                       host param controls QR URL — set via query param, not env.
```

---

## Testing

```bash
# Run T-018 tests
pytest tests/test_qr_entry.py -v
# Expected: 18 passed

# Run full suite
pytest tests/ -v
# Expected: 222 passed (204 from T-017 + 18 new)

# Code quality
black backend/ tests/ && isort backend/ tests/
```

**Manual test — QR scan on mobile:**
```
1. Start backend: uvicorn backend.main:app --reload --port 8000
2. Start frontend: cd frontend && npm run dev
3. (Optional) Expose localhost via ngrok: ngrok http 5173
4. Visit: http://localhost:8000/qr/generate?format=json
5. Copy qr_base64 value → paste into browser as data:image/png;base64,<value>
6. Scan QR from phone → verify simulator opens pre-filled with airport context
7. Verify blue badge visible: "✈ T3 · Terminal B"
8. Verify bot reply acknowledges location context
9. GET /qr/poster → download PDF → open → verify A4 layout renders correctly
```

**Acceptance Criteria:**
```
✅ GET /qr/generate returns valid PNG QR code (200, image/png)
✅ GET /qr/generate?format=json returns base64 + metadata JSON
✅ JSON 'url' field contains airport, terminal, and auto=1 params
✅ GET /qr/poster returns PDF (or PNG fallback) with 200 status
✅ Poster filename includes airport + terminal identifiers
✅ /simulator route renders in React (registered in main.jsx)
✅ /simulator?airport=T3&terminal=B&auto=1 auto-fires claim start
✅ Blue context badge visible when airport/terminal params present
✅ Sentinel message [QR_AUTO_START] NOT rendered as user bubble
✅ airport_context + terminal_context forwarded in webhook body
✅ Scanning QR on mobile opens correct URL (manual test)
✅ 18 new tests passing (test_qr_entry.py)
✅ 222 total tests passing
✅ black + isort clean
✅ No new env vars required
```

---

## PR Checklist

```
[x] PR title includes Task ID: [T-018] feat(qr): QR code generation + simulator entry flow
[x] Base branch: develop (not main)
[x] Reviewer: Anoushka
[x] qr.py uses no provider imports — pure generation logic only
[x] No hardcoded API keys
[x] No hardcoded provider names in routes
[x] reportlab added to requirements.txt
[x] /qr proxy added to vite.config.js
[x] /simulator route added to main.jsx
[x] useClaimFlow accepts airport/terminal options (backward compatible default=null)
[x] Auto-start sentinel suppressed from user bubble rendering
[x] 18 tests passing
[x] 222 total tests passing
[x] black + isort clean
[x] Branch doc in BRANCH_DOCS/WEEK3_DOCS/
[x] Squash merged to develop
[x] Feature branch deleted after merge
```

---

## Notes

```
ngrok for mobile testing  →  The QR URL defaults to localhost:5173 which
                              only works when the phone is on the same network.
                              For a real device demo: run `ngrok http 5173`,
                              copy the HTTPS URL, pass it as:
                              /qr/generate?host=https://abc-poc.ngrok.io
                              The QR will encode the public URL correctly.

reportlab install         →  pip install reportlab>=4.0 --break-system-packages
                             (or within venv: pip install reportlab>=4.0)
                             Added to requirements.txt. CI will pick it up.

No WhatsApp needed        →  Per architecture: for POC, the QR deep-links to
                             the React simulator, not to WhatsApp. Phase 2
                             swap: change the QR URL to wa.me/<number> with a
                             pre-filled message parameter. Zero code changes
                             to the backend or agents.

Parallel task             →  T-017 (Anoushka — agent dashboard). Zero file
                             overlap confirmed: T-017 touched Dashboard.jsx,
                             ClaimCard.jsx, decision.py, orchestrator.py,
                             supabase_client.py. T-018 touches qr.py (new),
                             main.py (1 line), Simulator.jsx (new), main.jsx
                             (2 lines), useClaimFlow.js (options param),
                             vite.config.js (1 line). No conflicts.

Next tasks                →  T-019 Devam (structure cleanup), T-020 Aditya
                             (test suite), T-021 Anoushka (README + demo script)

Blockers                  →  None.
```

---

*Branch opened: Day 11, Week 3 — Aditya*
*Merged to develop: Day 12, Week 3*