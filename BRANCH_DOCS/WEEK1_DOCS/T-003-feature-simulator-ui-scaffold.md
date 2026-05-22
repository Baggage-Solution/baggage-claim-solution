# BRANCH: feature/simulator-ui-scaffold

---

## Branch Metadata

```
Branch Name   →  feature/simulator-ui-scaffold
Task ID       →  T-003
Workstream    →  Simulator UI / Project Setup
Author        →  Anoushka
Reviewer      →  Aditya
Start Date    →  Day 1, Week 1
Target Merge  →  Day 2, Week 1
Actual Merge  →  Day 2, Week 1
Status        →  Merged
```

---

## Objective

**What does this branch do?**
Bootstraps the React frontend for the WhatsApp baggage claim simulator. Sets up Vite + React 18 +
Tailwind CSS v3, and delivers a complete static WhatsApp-look chat UI shell — header, message bubbles
(sent and received), image upload previews, text input, paperclip file upload button, and send button.
No backend calls yet — all handlers are clearly marked stubs.

**Why is it needed?**
T-003 is the frontend foundation. The simulator is what passengers (and demo viewers) actually see and interact
with. Every other UI task (T-013 full conversation flow, T-017 agent dashboard) builds on top of this shell.
Having a clean, realistic WhatsApp-look frame from Day 1 also makes the Week 1 integration demo (T-009)
immediately convincing — the backend's A1 response lands in a real chat bubble, not a raw JSON blob.

---

## Technical Approach

**Files Created:**

| File | Purpose |
|---|---|
| `frontend/package.json` | Vite 5 + React 18 + Tailwind v3 + Prettier dependencies |
| `frontend/vite.config.js` | Dev server on :5173 with proxy stubs pointing /webhook and /upload to :8000 |
| `frontend/tailwind.config.js` | Content paths + WhatsApp colour design tokens (wa-teal, wa-green, wa-sent, wa-bg) |
| `frontend/postcss.config.js` | Tailwind + autoprefixer PostCSS pipeline |
| `frontend/.prettierrc` | Prettier with prettier-plugin-tailwindcss for class sorting |
| `frontend/index.html` | Updated page title to "ABC Airline — Baggage Claim AI" |
| `frontend/src/main.jsx` | React 18 root mount with StrictMode |
| `frontend/src/App.jsx` | Root component — composes header, window, input; stub handlers with console.log |
| `frontend/src/index.css` | Tailwind directives + custom scrollbar for chat area |
| `frontend/src/components/ChatHeader.jsx` | WhatsApp green top bar — airline avatar, name, online status dot, lock icon |
| `frontend/src/components/ChatWindow.jsx` | Scrollable message list on ECE5DD wallpaper, auto-scrolls to newest message |
| `frontend/src/components/MessageBubble.jsx` | Sent (DCF8C6 green, right-aligned) + received (white, left-aligned) bubbles with timestamp and blue read ticks |
| `frontend/src/components/ChatInput.jsx` | Paperclip file upload trigger + text field + teal send button; accepts disabled prop for loading states |
| `frontend/src/data/mockMessages.js` | Static 6-message sample conversation for T-003 scaffold display |
| `frontend/screenshots/` | UI screenshots committed for PR acceptance review |

**Files Modified:**

| File | What changed |
|---|---|
| `frontend/.gitkeep` | Deleted — replaced by the real app scaffold |

**Files Deleted from Vite Default:**

| File | Reason |
|---|---|
| `frontend/src/assets/` | Vite default assets (react.svg) — not needed; WhatsApp UI uses Tailwind + inline SVG |
| `frontend/src/App.css` | Vite default styles — replaced by Tailwind via index.css |

**Provider / Abstraction Used:**
No AI or data providers involved in this branch. Frontend only.
Vite proxy config (`/webhook`, `/upload` → `http://localhost:8000`) is the only backend coupling —
it means T-013 can call `fetch('/webhook')` without any CORS configuration or URL changes.

**Key Design Decisions:**

```
1. PHONE-FRAME LAYOUT
   The simulator renders as a 400 × 700px phone-shaped container centred on a dark
   grey background (bg-gray-700). This makes it immediately read as "mobile app" in
   a browser without any extra tooling or viewport trickery. Critical for the demo.

2. WHATSAPP COLOUR TOKENS IN TAILWIND CONFIG
   Exact hex values from WhatsApp's design (075E54 header, 128C7E green, DCF8C6
   sent bubble, ECE5DD background) are defined as named tokens in tailwind.config.js.
   T-013 and T-017 can use wa-teal, wa-sent etc. directly — no magic colour strings
   scattered through components.

3. MOCK MESSAGES IN SEPARATE DATA FILE
   mockMessages.js is a standalone data file, not baked into any component.
   T-013 replaces it with a real useState array — zero component edits required.

4. STUB HANDLERS WITH CONSOLE.LOG
   handleSend() and handleFileSelect() log clearly labelled [T-003 stub] messages.
   This makes it immediately obvious to T-013's author exactly what needs wiring.
   Silent no-ops would hide the integration points.

5. VITE PROXY CONFIG BAKED IN FROM DAY 1
   /webhook and /upload proxied to :8000 from the start. T-013 just calls
   fetch('/webhook') and it works — no additional config, no CORS errors during
   integration week.

6. NO FORM TAGS — CONTRIBUTING.md RULE
   All interactions use onClick / onChange handlers as required.
   File input is triggered programmatically via useRef — no <form> element anywhere.

7. DISABLED PROP ON CHATINPUT
   The disabled prop is wired on ChatInput from T-003. T-013 sets it to true while
   awaiting a backend reply, giving immediate loading-state UX without refactoring
   the component interface later.
```

**Future Swap Path:**
```
T-013  →  Replace mockMessages with real useState + fetch('/webhook') calls.
           Wire handleSend to POST /webhook. Wire handleFileSelect to POST /upload.
           Set disabled=true on ChatInput while awaiting response.

T-017  →  Add /dashboard route in App.jsx using React Router.
           ChatHeader can be reused. Agent dashboard is a new route, not a new app.

Phase 2 →  Replace React simulator with real WhatsApp Cloud API.
           Frontend becomes optional (for internal demos only).
           No backend changes needed — /webhook endpoint stays identical.
```

---

## Dependencies

```
Depends On          →  T-001 (repo + develop branch must exist)
                       T-002 (not strictly required for npm — but develop must be
                              green before branching off it per sprint rules)

External Libraries  →  react@^18.3.1
                       react-dom@^18.3.1
                       vite@^5.4.10
                       @vitejs/plugin-react@^4.3.1
                       tailwindcss@^3.4.14
                       postcss@^8.4.47
                       autoprefixer@^10.4.20
                       prettier@^3.3.3
                       prettier-plugin-tailwindcss@^0.6.8

Environment Vars    →  None — pure frontend. No .env.example changes required.
                       (VITE_* vars will be added in T-013 if needed for backend URL config)
```

---

## Testing

**How to Test (Manual):**

```bash
# 1. Navigate to the frontend folder
cd frontend

# 2. Install dependencies
npm install

# 3. Start the dev server
npm run dev

# 4. Open the simulator
#    http://localhost:5173
```

**What to verify:**

```
✅ Dark grey page background with a centred phone-frame chat window
✅ Green header — "ABC Airline — Baggage Claims", green dot, lock icon
✅ 6 mock messages rendered — alternating bot (white/left) and user (green/right)
✅ User message 5 shows two image placeholder tiles (damage_photo_1.jpg, bag_tag.jpg)
✅ All timestamps visible (10:42, 10:43, 10:44)
✅ Blue read-tick icon appears on all user messages
✅ Bottom input bar: paperclip icon, text field, teal send button
✅ Type in text field → send button becomes active (not greyed out)
✅ Press Enter or click send → [T-003 stub] send: <text> in DevTools console → input clears
✅ Click paperclip → file picker opens → select images → [T-003 stub] files selected: [...] in console
✅ Zero red errors in browser DevTools console
```

**Format check:**

```bash
# From inside frontend/
npx prettier --check src/

# All files should pass — fix with:
npx prettier --write src/
```

**Automated Tests:**
T-003 is a static UI scaffold — no backend logic, no state machines, no provider calls.
No automated test file is added in this branch. Per project standards, this is acceptable
for pure UI scaffolding tasks with no testable logic. The acceptance criteria (load on :5173,
no console errors) are verified manually via the steps above.

First automated frontend tests will be written in T-020 (feature/test-suite, Week 3, Aditya).

**Test Data Used:**
`frontend/src/data/mockMessages.js` — in-code static data only.
`frontend/screenshots/` — committed UI screenshots for PR review.

**Acceptance Criteria:**

```
✅ App loads on localhost:5173 with no console errors
✅ Looks like WhatsApp — header, bubbles, input bar, correct colours
✅ Message bubbles: bot = white left-aligned, user = green right-aligned
✅ File upload button opens the file picker
✅ Send button is disabled when text field is empty
✅ Prettier passes on all src/ files
✅ Screenshots committed to frontend/screenshots/
```

---

## PR Checklist

```
[x] PR title includes Task ID — [T-003] feat(simulator): ...
[x] PR description filled out on GitHub
[x] Base branch set to develop (not main)
[x] Reviewer assigned — Aditya
[x] Squash merged to develop
[x] Feature branch deleted after merge

[~] Type hints — N/A (JavaScript/React, not Python)
[x] Docstrings — JSDoc on all components (param types, purpose documented)
[~] .env.example — no changes needed (no new env vars in frontend)
[~] No hardcoded provider names — N/A (no AI calls in frontend T-003 scope)
[~] pytest — N/A (no Python code changed in this branch)
[x] Prettier passes on all src/ files
[x] App loads with zero console errors
[x] Screenshots committed
```

---

## Notes / Blockers

```
Known Issues  →  None.

Design Scope  →  T-003 is the UI frame only. The following are intentionally deferred:
                 - Real fetch('/webhook') calls          → T-013
                 - Conversation step state machine        → T-013
                 - Multi-photo upload with previews       → T-013
                 - Lane 1 voucher result card             → T-013
                 - Lane 2 "Under Review" card             → T-013
                 - /dashboard route                       → T-017
                 These are stub console.log calls in T-003 — clearly labelled
                 [T-003 stub] so T-013 author knows exactly what to wire.

Blockers      →  None — T-001 (Devam) merged and develop was green before this
                 branch was opened.

Links         →  Vite docs:             https://vite.dev/guide/
                 Tailwind CSS v3 docs:  https://v3.tailwindcss.com/docs/installation
                 WhatsApp colour refs:  https://www.whatsapp.com/brand (075E54, 128C7E, 25D366)
                 Prettier TW plugin:    https://github.com/tailwindlabs/prettier-plugin-tailwindcss
```

---

*Branch opened: Day 1, Week 1 — Anoushka*
*Merged to develop: Day 2, Week 1*
