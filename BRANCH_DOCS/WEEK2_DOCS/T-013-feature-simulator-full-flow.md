# BRANCH: feature/simulator-full-flow

---

## Branch Metadata

```
Branch Name   →  feature/simulator-full-flow
Task ID       →  T-013
Workstream    →  Simulator UI
Author        →  Anoushka
Reviewer      →  Devam
Start Date    →  Day 7, Week 2
Target Merge  →  Day 9, Week 2
Actual Merge  →  Day 9, Week 2
Status        →  Merged
```

---

## Objective

**What does this branch do?**
Implements the full interactive claim conversation flow in the React WhatsApp
simulator. Replaces all T-003 stub handlers in `App.jsx` with a real state
machine that communicates with the FastAPI backend. Passengers can now complete
an end-to-end damage claim — from greeting through photo upload to final
Lane 1 voucher or Lane 2 under-review result — entirely in the browser.

**Why is it needed?**
T-003 delivered a static UI shell with no backend wiring. T-013 is the bridge
that makes the simulator a true end-to-end demo tool. Every upstream agent
(A1–A5) can now be exercised through the simulator UI, making T-016 (Week 2
integration) and the mentor demo possible.

---

## Local Setup

```bash
# ── Backend (terminal 1) ─────────────────────────────────────────────────────
source venv/Scripts/activate     # Windows Git Bash
# source venv/bin/activate       # Mac / Linux

uvicorn backend.main:app --reload --port 8000

# ── Frontend (terminal 2) ────────────────────────────────────────────────────
cd frontend
npm install          # first time only
npm run dev          # starts on http://localhost:5173
```

Open `http://localhost:5173` — the simulator loads with the greeting message.

---

## Conversation Flow (State Machine)

```
greeting
  └─ user types damage description
        ↓
damage_photos
  └─ user attaches 1-3 damage photos → Send
     (A2 analyses photos → damage_types, severity, brand returned in bot reply)
        ↓
tag_photo
  └─ user attaches bag tag photo → Send
     (A3 extracts flight_number, pnr, bag_id → shown in confirm summary)
     (if confidence < 0.7 → re_request_tag → loops back here)
        ↓
confirm
  └─ user types "yes" / "confirm" to proceed
        ↓
result
  ├─ Lane 1: ClaimResultCard (green voucher, instant approval ≤ $100)
  └─ Lane 2: ClaimResultCard (amber under-review, >$100 or luxury bag)
```

---

## Technical Approach

### Files Created

| File | Purpose |
|------|---------|
| `frontend/src/hooks/useClaimFlow.js` | Core state machine — manages messages, step, pending images, upload, webhook calls, result |
| `frontend/src/components/TypingIndicator.jsx` | Animated three-dot "AI typing" bubble shown while awaiting webhook |
| `frontend/src/components/ImageUploadPreview.jsx` | Horizontal strip of staged photos with per-photo remove buttons, shown before Send |
| `frontend/src/components/ClaimResultCard.jsx` | Terminal result card — Lane 1 (green voucher) or Lane 2 (amber under-review) |
| `BRANCH_DOCS/WEEK2_DOCS/T-013-feature-simulator-full-flow.md` | This document |

### Files Modified

| File | What Changed |
|------|-------------|
| `frontend/src/App.jsx` | Full rewrite — all T-003 stubs removed; `useClaimFlow` hook wired; `ImageUploadPreview` added between chat and input |
| `frontend/src/components/ChatInput.jsx` | Added `onKeyDown` + `hasPendingImages` props; send button enabled when images staged |
| `frontend/src/components/ChatWindow.jsx` | Added `isLoading` (renders `TypingIndicator`) + `claimResult` (renders `ClaimResultCard`) props |
| `frontend/src/components/MessageBubble.jsx` | `imagePreviews` now supports `{ name, url }` — shows real thumbnails from `URL.createObjectURL` |
| `frontend/src/index.css` | Added `@keyframes typing-bounce` for the TypingIndicator animation |

### Post-Merge Bugfixes (all committed to this branch before final merge)

The following bugs were found and fixed during manual testing after the initial
implementation. All fixes are included in this branch.

#### Fix 1 — A4 ran on every turn, jumping conversation to `result` immediately

**Root cause:** The LangGraph graph was wired as a linear `a1→a2→a3→a4→a5`
pipeline unconditionally. A4 always set `routing_lane` (defaults to Lane 1
when `compensation_estimate_usd = 0`), and A1's `_advance_step()` logic
jumped to `"result"` the moment `routing_lane` was not None — even on the
very first greeting turn.

**Fix:** Restructured `orchestrator.py` to use a `router` node at the entry
point. The router dispatches to either the text branch (`a1_text → END`) or
the image pipeline branch (`a2 → a3 → a1_image → [a4 → [a5 → END]]`).
A4 only runs when both damage and tag images are present in `state.image_paths`.
A5 only runs when `routing_lane` is 1 or 2.

**Files:** `backend/graph/orchestrator.py`

---

#### Fix 2 — `conversation_step` reset to `"greeting"` on every webhook call

**Root cause:** `ClaimOrchestrator.run()` created a fresh `ClaimState()` on
each invocation. LangGraph's `MemorySaver` does not persist plain Python
dataclass field values across separate `ainvoke()` calls — input state values
override checkpoint values for fields without `Annotated` reducers. So
`conversation_step` always re-initialised to its default `"greeting"`,
meaning A1 never knew which step it was on.

**Fix (two-part):**
1. Added `conversation_step: Optional[str]` field to `WebhookRequest` schema.
   The frontend now echoes the step it received from the previous response
   back to the backend on every request.
2. `ClaimOrchestrator.run()` accepts the echoed `conversation_step` and
   injects it into `ClaimState()` so A1 always has the correct step.

**Files:** `backend/api/schemas/claim_request.py`, `backend/api/routes/webhook.py`,
`frontend/src/hooks/useClaimFlow.js`

---

#### Fix 3 — Bot re-asked for photos the user had just uploaded

**Root cause:** A1 ran before A2 in the pipeline (`a1→a2→...`). When the user
uploaded damage photos at `step=damage_photos`, A1 picked the `"damage_photos"`
prompt — which instructs the LLM to ask for photos — and sent that back to the
user who had just sent photos.

**Fix (two-part):**
1. Reordered pipeline: `a2 → a3 → a1_image → ...` for image turns. A2 and
   A3 now run first and populate `state.damage_types`, `severity_score`,
   `flight_number` etc. A1 then runs with full analysis data available.
2. Added `damage_photos_received` and `tag_photo_received` prompt variants
   to `a1_conversation.json`. `_get_step_prompt()` in A1 checks whether
   `image_paths` are present for the current step and switches to the
   `*_received` variant, which instructs the LLM to acknowledge the photos
   and move forward rather than re-requesting them.
3. Added `_build_analysis_context()` method to A1 that constructs a hidden
   `[ANALYSIS RESULTS]` block from A2/A3 state fields. This block is injected
   into the LLM messages so A1 can include specific damage findings (types,
   severity, compensation estimate, tag data) in its passenger-facing reply.

**Files:** `backend/graph/orchestrator.py`, `backend/agents/a1_conversation.py`,
`backend/prompts/a1_conversation.json`

---

#### Fix 4 — A4 needed belt-and-suspenders guard for incomplete image sets

**Root cause:** Even with the orchestrator routing fix, A4 could theoretically
be invoked when only damage images (no tag) were present, causing it to make
a routing decision without OCR data and set `routing_lane` prematurely.

**Fix:** Added an early-return guard at the top of `A4DecisionAgent.handle()`
that checks `damage_images` and `tag_images` separately. If either is missing,
A4 logs `a4_skipped` and returns state unchanged.

**Files:** `backend/agents/a4_decision.py`

---

#### Fix 5 — Image paths lost at confirm step; A4 could not run

**Root cause:** When the user typed "yes" at the confirm step, no new images
were attached. The original `useClaimFlow.js` only sent the image paths
uploaded in the *current* turn, so `image_paths = []` at confirm. A4's guard
(Fix 4) would correctly skip, meaning the claim was never finalised.

**Fix:** Added `allUploadedPaths` ref to `useClaimFlow.js` that accumulates
every successfully uploaded path across the entire session. Every `/webhook`
call sends the full accumulated set (not just new paths), so A4 always has
both damage and tag images available — including at the confirm step.

**Files:** `frontend/src/hooks/useClaimFlow.js`

---

#### Fix 6 — `filename` key in `logger.info()` crashed on Python 3.14

**Root cause:** `filename` is a reserved built-in field of Python's
`logging.LogRecord`. Python 3.14 strictly raises
`KeyError: "Attempt to overwrite 'filename' in LogRecord"` when any caller
passes `filename` in the `extra={}` dict. Earlier Python versions silently
ignored this, masking the bug.

**Fix:** Renamed the key from `"filename"` to `"upload_filename"` in the
`logger.info("upload_saved", ...)` call inside `upload_image()`.

**Files:** `backend/api/routes/webhook.py`

---

### Architecture Decisions

**Hook pattern (`useClaimFlow.js`):**
All stateful logic lives in one custom hook. `App.jsx` is a thin composition
layer. This follows the same separation used in T-003 (UI shell separate from
logic) and keeps components individually testable.

**Session ID:**
Generated once via `makeSessionId()` on mount (timestamp + random suffix).
Passed to every `/webhook` and `/upload` call as `session_id`.

**Conversation step tracking:**
Frontend is authoritative for `conversation_step` in this POC. Each webhook
response returns the new step; the frontend stores it in `useState` and sends
it back on the next request. This pattern is required because LangGraph's
`MemorySaver` does not persist plain dataclass fields across separate
`ainvoke()` calls.

**Conversation history:**
Rolling `conversationHistory` ref (last 6 turns of `{role, content}` pairs)
sent with every `/webhook` call so A1 produces contextually coherent replies.

**Accumulated image paths:**
`allUploadedPaths` ref accumulates all server-side file paths returned by
`/upload` across the session. Sent in full on every `/webhook` call so
A4 always has both damage and tag images regardless of which turn is active.

**Photo type detection:**
`useClaimFlow` infers `photoType` (`"damage"` or `"tag"`) from the current
`step` value. `step === 'tag_photo'` → `"tag"`, all others → `"damage"`.
The uploaded filename is prefixed accordingly (`damage_*` / `tag_*`), which
is how A2/A3 filter images from `state.image_paths`.

**Pipeline order (image turns):**
`router → a2 → a3 → a1_image → [a4 → [a5 → END] | END] | END`
A2 and A3 run before A1 on image turns so their analysis results (damage
types, severity, OCR data) are available when A1 composes its reply.

**Pipeline order (text turns):**
`router → a1_text → END`
Text-only turns (greeting, description, "yes" confirm) skip the image
pipeline entirely so A4 is never triggered without a complete image set.

**Result rendering:**
`claimResult` state is set when `response.routing_lane` is 1 or 2.
`ClaimResultCard` renders inside `ChatWindow` after the last message, and
`inputDisabled` prevents further input — the claim is complete.

**A2/A3 prompt files:**
A2 and A3 do not have `backend/prompts/` JSON files. Their prompts are
hardcoded constants in `gemini_vision.py` and `gemini_ocr.py` respectively.
This is intentional — A2/A3 are structured-output agents (they return JSON,
not conversational text) and their prompts are stable extraction contracts,
not passenger-facing copy that needs hot-swapping.

---

## Dependencies

| Dependency | Source |
|-----------|--------|
| Depends On | T-003 (UI scaffold), T-009 (Week 1 integration — backend + A1 live) |
| External Libraries | None added — uses native `fetch`, `FormData`, `URL.createObjectURL` |
| Environment Variables | None new — backend `GEMINI_API_KEY` must be set for A1 to reply |
| Backend Endpoints | `POST /upload`, `POST /webhook` (both from T-004 + T-009) |

---

## Testing

### Manual Test — Full Lane 1 Flow

```
1. npm run dev + uvicorn backend.main:app --reload
2. Open http://localhost:5173
3. Type: "My suitcase wheel broke during landing"  → Send
   Expected: AI asks for damage photos (step advances to damage_photos)
4. Click 📎 → select 2 damage photos from tests/fixtures/damaged/
   Click Send
   Expected: Typing indicator → AI acknowledges photos, describes damage
   found (types + severity), asks for bag tag photo (step = tag_photo)
5. Click 📎 → select 1 tag photo from tests/fixtures/bag_tags/
   Click Send
   Expected: Typing indicator → AI confirms tag received, shows claim
   summary with damage + tag data, asks to confirm (step = confirm)
6. Type: "yes"  → Send
   Expected: Typing indicator → ClaimResultCard appears
   Lane 1 ($0–$100): green voucher card with CLM-YYYYMMDD-XXXX + VCH-XXXXXXXX
   Lane 2 (>$100 or luxury): amber under-review card with reference number
7. Input bar is disabled — claim complete
Total time: < 3 minutes ✓
```

### Manual Test — Retry Flow (blurry tag)

```
1. Complete steps 1–4 above
2. At step 5, upload tests/fixtures/bag_tags/clear_tag_02.jpg (blurry)
3. Expected: AI requests a clearer photo (re_request_tag = true, step stays tag_photo)
4. Upload a clear tag → flow continues to confirm
```

### Automated Tests

```bash
# No new automated tests in T-013 scope (UI-only branch)
# Integration covered by T-016 + T-020 test suite
pytest tests/ -v  # existing tests must still pass
```

**Test Data Used:**
- `tests/fixtures/damaged/damaged_01.jpg`, `damaged_02.jpg`, `luxury_01.jpg`
- `tests/fixtures/bag_tags/clear_tag_01.jpg`, `clear_tag_02.jpg`

### Acceptance Criteria (from Task Tracker)

- [x] Multi-photo upload functional (input[type=file multiple])
- [x] Full conversation state machine: greeting → damage_photos → tag_photo → confirm → result
- [x] After damage photo upload: bot reports detected damage types and severity
- [x] After tag photo upload: bot shows extracted flight number, bag ID in summary
- [x] Lane 1 result: voucher card shown in simulator
- [x] Lane 2 result: "Under Review" card shown in simulator
- [x] Full flow completes in < 3 minutes with test images
- [x] Typing indicator shown while awaiting AI reply
- [x] Staged photo preview with per-photo remove before send
- [x] Input disabled after claim reaches terminal state
- [x] Retry prompt shown when bag tag photo confidence < 0.7

---

## PR Checklist

- [x] Type hints — N/A (JavaScript/JSX; JSDoc comments on all components)
- [x] Docstrings / JSDoc on all exported components and the hook
- [x] `.env.example` — no new env vars introduced
- [x] No hardcoded provider names in UI code
- [x] No automated tests added (UI-only; covered by T-016 + T-020)
- [x] `pytest tests/` passes locally
- [x] PR description filled out on GitHub
- [x] Reviewer (Devam) assigned

---

## Notes / Blockers

| Item | Detail |
|------|--------|
| Backend must be running | Frontend calls `http://localhost:8000` — CORS is open in POC mode |
| Gemini API key required | `.env` must have `GEMINI_API_KEY` set for A1/A2/A3 to reply |
| No auth in POC | `/upload` and `/webhook` have no auth — fine for POC, add in Phase 2 |
| Real WhatsApp swap | Replace `fetch('/webhook')` with Meta Cloud API webhook in Phase 2 |
| PromptLoader cache | `PromptLoader.load()` uses `@lru_cache` — must restart uvicorn after editing any `prompts/*.json` |
| conversation_step ownership | Frontend is authoritative for step in POC. Phase 2: migrate to LangGraph state with `Annotated` reducers or a Redis session store so backend owns the step |
| Supabase DB stub | `SupabaseDBProvider.save_claim()` is a stub pending T-014. Claim routing still works — A4 generates `claim_id` and `routing_lane` in memory |
| A5 notification stub | A5 sets `voucher_code` and `routing_lane` in state (used by frontend result card) but does not push to an external notification queue — that is T-015 scope |

---

## Links

- Task Tracker: `POC_Task_Tracker_latest_updated.xlsx` → T-013 row
- FastAPI /docs: `http://localhost:8000/docs`
- T-003 branch doc: `BRANCH_DOCS/WEEK1_DOCS/T-003-feature-simulator-ui-scaffold.md`
- T-009 branch doc: `BRANCH_DOCS/WEEK1_DOCS/T-009-integration-week1.md`
