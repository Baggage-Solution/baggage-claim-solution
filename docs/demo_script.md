# Demo Script — ABC Airline Baggage Claim AI
### Mentor Demo Walkthrough · POC Sprint · 3 Weeks

---

## Pre-Demo Setup (Do This 10 Minutes Before)

```bash
# Terminal 1 — backend
cd baggage-claim-solution
source venv/Scripts/activate       # Windows Git Bash
# OR source venv/bin/activate      # Mac / Linux
uvicorn backend.main:app --reload --port 8000

# Terminal 2 — frontend
cd baggage-claim-solution/frontend
npm run dev

# Verify both are running:
# Backend: http://localhost:8000/health → {"status":"ok","configured":{"gemini":true,"supabase":true}}
# Frontend: http://localhost:5173 → WhatsApp simulator visible
```

**Have these ready:**
- Browser tab 1: http://localhost:5173 (simulator)
- Browser tab 2: http://localhost:5173/dashboard (staff dashboard)
- Browser tab 3: http://localhost:8000/docs (Swagger — for technical questions)
- Test images at: `tests/fixtures/damaged/` and `tests/fixtures/bag_tags/`

---

## Opening — 2 Minutes

> *"We built an AI system that lets airline passengers file baggage damage claims in under 2 minutes — directly on WhatsApp, no app download, no forms, no queues.*
>
> *A passenger lands, finds their bag damaged at the carousel, scans a QR code, and they're done. The AI handles everything: it looks at the photos, reads the bag tag, checks for fraud, and either auto-approves a voucher or routes to a staff reviewer.*
>
> *The whole thing runs at zero infra cost in POC mode. Free tier Gemini API. Free Supabase. All providers are swappable with one environment variable change — no code changes needed.*
>
> *Let me walk you through a live demo."*

---

## Scenario A — Lane 1: Standard Bag, Auto-Approve

**What to show:** Full claim in under 2 minutes, instant voucher.

**Images to use:**
```
Damage: tests/fixtures/damaged/damaged_01.jpg
Tag:    tests/fixtures/bag_tags/clear_tag_01.jpg
```

**Walkthrough:**

**Step 1 — Open the simulator**
> *"This is our WhatsApp simulator — it's a React app that mimics the WhatsApp interface. In production this would be the real WhatsApp Cloud API, but for the POC we've built a full simulator so we can demo without needing a real WhatsApp Business account."*

**Step 2 — Send first message**
- Type: `hi my bag is damaged` → hit Send

> *"The passenger sends their first message. This goes to POST /webhook → LangGraph → A1 ConversationAgent, which detects we're at the 'greeting' step and generates an empathetic response using Gemini."*

- Point to the A1 reply appearing in the chat

**Step 3 — Describe damage**
- Type: `the wheel is broken and the shell is cracked` → Send

> *"A1 advances to the 'damage_photos' step and asks for photos."*

**Step 4 — Upload damage photos**
- Click the attachment icon
- Select `tests/fixtures/damaged/damaged_01.jpg`
- Click Send

> *"The image goes to POST /upload first — saves to local storage, returns the file path. Then /webhook runs the full image pipeline: A2 Vision Agent sends the photo to Gemini Vision, gets back damage_types=['cracked shell', 'broken wheel'], severity_score=0.4, compensation estimate=$60. A3 waits for the tag."*

**Step 5 — Upload bag tag**
- Click attachment → select `tests/fixtures/bag_tags/clear_tag_01.jpg` → Send

> *"A3 OCR Agent reads the bag tag — flight number, PNR, bag ID — using Gemini Vision as an OCR engine. It validates the PNR format with regex. If confidence is below 0.7 it asks the passenger to retake the photo."*

**Step 6 — A4 Decision — the key moment**
> *"Now A4 runs two fraud checks: a perceptual hash check — has this exact image been submitted before for this PNR? And a frequency check — has this passenger filed 3+ claims in the last 30 days?*
>
> *In this case: standard bag, $60 compensation estimate, zero fraud score. All three conditions for auto-approval are met — compensation under $100, not a luxury bag, no fraud flags.*
>
> *Lane 1. Auto-approved."*

**Step 7 — Voucher appears**
- Point to the green voucher card with VCH-XXXXXXXX

> *"A5 Notification Agent generates the voucher, pushes a Server-Sent Event to the simulator via a GET /events/{session_id} stream, and updates the claim status to APPROVED in Supabase in real time."*

**Step 8 — Check Supabase (if internet available)**
> *"And here's the claim row in Supabase — status APPROVED, with the voucher code, fraud score, routing lane, all persisted."*

**Total time: under 2 minutes ✓**

---

## Scenario B — Lane 2: Luxury Bag, Staff Review

**What to show:** Luxury detection → staff queue → dashboard approve.

**Images to use:**
```
Damage: tests/fixtures/damaged/luxury_01.jpg   (Rimowa)
Tag:    tests/fixtures/bag_tags/clear_tag_01.jpg
```

**Walkthrough:**

**Step 1 — Click "Start a new claim"**
> *"Fresh session, new passenger."*

**Step 2 — Upload Rimowa damage photo**
- Same flow as Scenario A, but use `luxury_01.jpg`

> *"This time A2 Vision identifies the bag as a Rimowa — a luxury brand. It cross-checks against our LUXURY_BRANDS set and sets is_luxury=True.*
>
> *A4 sees is_luxury=True and routes directly to Lane 2 — no matter what the compensation estimate is. Luxury bags always go to staff review."*

**Step 3 — 'Under Review' card appears**
- Point to the amber 'Under Review' card

> *"The passenger gets a reference number and is told staff will contact them within 24 hours."*

**Step 4 — Switch to Dashboard**
- Open browser tab 2: http://localhost:5173/dashboard

> *"This is the staff review dashboard. Our Lane 2 claim just appeared — you can see the damage photo, damage types, severity score, brand, fraud score, and compensation estimate.*
>
> *The staff agent can approve, reject, or modify the compensation amount."*

**Step 5 — Approve the claim**
- Click Approve

> *"Approved. The claim status updates to RESOLVED in Supabase. In production, A5 would send the voucher directly to the passenger's WhatsApp via the Meta Cloud API. In the POC, the simulator's result card would update to show the voucher."*

---

## Scenario C — Retry: Blurry Tag Photo

**What to show:** System gracefully handles bad input, asks for retake.

**Images to use:**
```
Damage: tests/fixtures/damaged/damaged_02.jpg
Tag:    any small/dark image (e.g. a screenshot of a black screen)
```

**Walkthrough:**

**Step 1 — Start a new claim, upload damage photo first**
- Use `damaged_02.jpg` as damage photo

**Step 2 — Upload a blurry or unclear tag photo**
- Upload any non-tag image as the "bag tag"

> *"A3 OCR tries to extract flight number, PNR, and bag ID. OCR confidence comes back at 0.3 — well below our 0.7 threshold.*
>
> *A3 sets re_request_tag=True in the state. A4 sees this flag and skips entirely — no routing decision is made, no claim ID generated. A1 picks up the re_request_tag step and asks the passenger to retake the photo."*

- Point to the retry message in chat

**Step 3 — Upload a clear tag photo**
- Upload `tests/fixtures/bag_tags/clear_tag_01.jpg`

> *"Good confidence this time. A3 validates the PNR format — 6 alphanumeric characters — and the bag ID. Everything passes. Pipeline continues normally to A4."*

---

## Technical Deep Dive (If Asked)

**"How does the provider swap work?"**
> *"Every AI provider is behind an abstract base class. A1 only calls `self._llm.chat()`. It has no idea if that's Gemini, Claude, or a local Ollama model. The actual provider is injected by `dependencies.py` based on a single environment variable — `LLM_PROVIDER=gemini`. To swap to Claude you implement `claude_llm.py`, set the env var, and nothing else changes."*

**"What happens if Gemini goes down?"**
> *"Every agent wraps its provider calls in try/except. If A1 fails, it sets state.error and returns — the pipeline continues, the webhook always returns HTTP 200, and the error is surfaced in the response JSON. The server never crashes. A5 also handles Supabase failures gracefully — the voucher is still generated and the SSE event is still pushed even if the DB write fails."*

**"How is fraud detected?"**
> *"Two checks. First: perceptual hashing — we compute a pHash fingerprint of each damage photo and compare against all hashes we've seen for this PNR using Hamming distance. If two photos are visually similar (distance < 10), it's flagged as a duplicate submission. Second: claim frequency — we query Supabase for how many claims this PNR has filed in the last 30 days. 3 or more triggers the flag. Both thresholds are configurable in .env without code changes."*

**"What's the cost?"**
> *"POC: zero. Gemini Flash free tier is 1500 requests/day, 1 million tokens/day. Supabase free tier is 500MB with 50,000 monthly active users. Local storage for images — no cloud storage cost. Production Phase 2 would switch to paid tiers, but for a PoC it's genuinely $0."*

**"What's Phase 2?"**
> *"Real WhatsApp Business Account integration — replace the SSE push in A5 with a Meta Cloud API call. Replace Gemini Vision with a YOLOv8 model trained on airline-specific damage data for better accuracy. Add LangGraph interrupt() for real human-in-the-loop workflows where the graph actually pauses and waits for staff input. Add auth to the dashboard. None of these require touching the agent code — only the provider implementations change."*

---

## Demo Checklist

Run through this before the mentor arrives:

```
[ ] make run → /health returns {"status":"ok","configured":{"gemini":true,"supabase":true}}
[ ] npm run dev → simulator loads at localhost:5173
[ ] Scenario A: upload damage + tag → Lane 1 voucher appears
[ ] Scenario B: upload Rimowa + tag → Lane 2 card → dashboard approve works
[ ] Scenario C: blurry tag → retry message → clear tag → pipeline continues
[ ] pytest tests/ -v → 0 failures
[ ] Supabase dashboard → claims visible with correct status
[ ] Browser tabs: simulator + dashboard + Swagger open and ready
[ ] Test images in tests/fixtures/ confirmed
```

---

## Timing Guide

| Section | Time |
|---|---|
| Opening | 2 min |
| Scenario A — Lane 1 | 4 min |
| Scenario B — Lane 2 + Dashboard | 4 min |
| Scenario C — Retry | 3 min |
| Q&A buffer | 5 min |
| **Total** | **~18 min** |

---

*Demo script created: Week 3, Day 13 — Anoushka + Devam*
