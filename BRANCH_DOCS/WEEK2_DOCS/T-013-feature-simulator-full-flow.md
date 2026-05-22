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
        ↓
tag_photo
  └─ user attaches bag tag photo → Send
     (if confidence < 0.7 → re_request_tag loop back here)
        ↓
confirm
  └─ user types "yes" / "confirm" to proceed
        ↓
result
  ├─ Lane 1: ClaimResultCard (green voucher)
  └─ Lane 2: ClaimResultCard (amber under-review)
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

### Architecture Decisions

**Hook pattern (`useClaimFlow.js`):**
All stateful logic lives in one custom hook. `App.jsx` is a thin composition
layer. This follows the same separation used in T-003 (UI shell separate from
logic) and keeps components individually testable.

**Session ID:**
Generated once via `makeSessionId()` on mount (timestamp + random suffix).
Passed to every `/webhook` and `/upload` call. Matches what the backend
uses as the LangGraph `thread_id` for session continuity (MemorySaver).

**Conversation history:**
The hook maintains a rolling `conversationHistory` ref (array of
`{role, content}` pairs). Sent with every `/webhook` call so A1 can give
contextually coherent replies across turns without backend session state.

**Photo upload:**
Files are staged in `pendingImages` (state) when the user selects them.
Upload to `/upload` happens only when the user hits Send — parallel via
`Promise.all`. The returned paths are bundled into the next `/webhook` call
as `image_paths`.

**Photo type detection:**
`useClaimFlow` infers `photoType` (`"damage"` or `"tag"`) from the current
`step` value synced from the backend response. No hardcoding in components.

**Result rendering:**
`claimResult` state is set when `response.routing_lane` is 1 or 2.
`ClaimResultCard` renders inside `ChatWindow` after the last message, and
`inputDisabled` prevents further input — the claim is complete.

**Backward compatibility:**
`MessageBubble` still accepts name-only `imagePreviews` objects (T-003
format), so any existing test snapshots are unaffected.

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
   Expected: AI asks for damage photos
4. Click 📎 → select 2 damage photos from tests/fixtures/damaged/
   Click Send
   Expected: Typing indicator → AI asks for bag tag photo
5. Click 📎 → select 1 tag photo from tests/fixtures/bag_tags/
   Click Send
   Expected: Typing indicator → AI shows extracted details, asks to confirm
6. Type: "yes"  → Send
   Expected: Typing indicator → ClaimResultCard appears
   Lane 1: green voucher card with CLM-YYYYMMDD-XXXX
   Lane 2: amber under-review card with reference number
7. Input bar is disabled — claim complete
Total time: < 3 minutes ✓
```

### Manual Test — Retry Flow (blurry tag)

```
1. Complete steps 1–4 above
2. At step 5, upload tests/fixtures/bag_tags/clear_tag_02.jpg (blurry)
3. Expected: AI requests a clearer photo (re_request_tag = true)
4. Upload a clear tag → flow continues
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
- [x] Lane 1 result: voucher card shown in simulator
- [x] Lane 2 result: "Under Review" card shown in simulator
- [x] Full flow completes in < 3 minutes with test images
- [x] Typing indicator shown while awaiting AI reply
- [x] Staged photo preview with per-photo remove before send
- [x] Input disabled after claim reaches terminal state

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

## PR Description (copy to GitHub)

```
## [T-013] feat(simulator): full conversation flow + photo upload

### What changed
Replaces all T-003 stub handlers with a real multi-turn claim flow.
Passengers can now complete a full Lane 1 or Lane 2 baggage claim
entirely in the simulator.

### New components
- `useClaimFlow.js` — hook with full state machine, /upload + /webhook wiring
- `TypingIndicator.jsx` — animated dots while awaiting AI response
- `ImageUploadPreview.jsx` — staged photo strip with per-photo remove
- `ClaimResultCard.jsx` — green voucher (Lane 1) / amber under-review (Lane 2)

### Modified components
- `App.jsx` — thin shell, delegates to useClaimFlow
- `ChatInput.jsx` — hasPendingImages prop, Enter-key support
- `ChatWindow.jsx` — isLoading + claimResult props
- `MessageBubble.jsx` — real image thumbnails via URL.createObjectURL
- `index.css` — typing-bounce keyframe

### How to test
1. `uvicorn backend.main:app --reload` (terminal 1)
2. `cd frontend && npm run dev` (terminal 2)
3. Open localhost:5173 → complete full claim flow with test fixtures
4. Verify Lane 1 shows voucher card in < 3 minutes

### Related
- Task ID: T-013
- Depends on: T-003, T-009
- Required by: T-016 (Week 2 integration)
```

---

## Notes / Blockers

| Item | Detail |
|------|--------|
| Backend must be running | Frontend calls `http://localhost:8000` — CORS is open in POC mode |
| Gemini API key required | `.env` must have `GEMINI_API_KEY` set for A1 to produce real replies |
| No auth in POC | /upload and /webhook have no auth — fine for POC, add in Phase 2 |
| Real WhatsApp swap | Replace `fetch('/webhook')` call in hook with Meta Cloud API webhook in Phase 2 |
| Lane detection | If A4 hasn't run yet (early turns), `routing_lane` is null — result card not shown |

---

## Links

- Task Tracker: `POC_Task_Tracker_latest_updated.xlsx` → T-013 row
- FastAPI /docs: `http://localhost:8000/docs`
- T-003 branch doc: `BRANCH_DOCS/WEEK1_DOCS/T-003-feature-simulator-ui-scaffold.md`
- T-009 branch doc: `BRANCH_DOCS/WEEK1_DOCS/T-009-integration-week1.md`
