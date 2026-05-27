# BRANCH: feature/agent-dashboard

---

## Branch Metadata

```
Branch Name   →  feature/agent-dashboard
Task ID       →  T-017
Workstream    →  Agent Dashboard
Author        →  Anoushka Vyas
Reviewer      →  Devam Dixit
Start Date    →  Day 11, Week 3
Target Merge  →  Day 13, Week 3
Actual Merge  →  Day 13, Week 3
Status        →  Merged
```

---

## Objective

**What does this branch do?**
Builds the Lane 2 staff review dashboard — a separate React page at `/dashboard`
where airline staff can see all AWAITING_REVIEW claims, view the actual uploaded
damage and bag tag photos inline with a click-to-enlarge lightbox, and approve
or reject each claim with an optional compensation adjustment.

Wires the two backend stubs (`GET /claims/pending` and `POST /decision`) to real
Supabase queries, adds `GET /claims/{claim_id}/images` to serve stored photos,
mounts `data/uploads/` as a FastAPI StaticFiles endpoint, and fixes the pending
upload folder so photos land under the correct `{claim_id}/` folder after A4
finalizes the claim.

**Why is it needed?**
Lane 2 routing is the core fraud-safety mechanism of the pipeline. A4 routes
high-value, luxury, or suspicious claims to Lane 2 for human review. Without
T-017 those claims sit in Supabase as AWAITING_REVIEW forever. Staff also cannot
make a proper decision without seeing the damage evidence — T-017 closes both
gaps: it surfaces the claims AND the photos to act on them.

---

## Local Setup

```bash
# Backend
source venv/Scripts/activate      # Git Bash / Windows
uvicorn backend.main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm install        # picks up react-router-dom added in this branch
npm run dev

# Open simulator:  http://localhost:5173
# Open dashboard:  http://localhost:5173/dashboard
```

---

## Technical Approach

**Backend — Files Modified:**

| File | What changed |
|---|---|
| `backend/main.py` | Added `import os`, `from fastapi.staticfiles import StaticFiles`. Added `os.makedirs("data/uploads", exist_ok=True)` and `app.mount("/uploads", StaticFiles(directory="data/uploads"), name="uploads")` to serve photos at `/uploads/{claim_id}/{filename}`. |
| `backend/db/base.py` | Added `get_claims_by_status(status)` abstract method. Added `List` to typing imports. |
| `backend/db/supabase_client.py` | Implemented `get_claims_by_status()` — queries claims table filtered by status, ordered newest first. |
| `backend/api/routes/decision.py` | Removed TODO stubs. Wired `GET /claims/pending` → `db.get_claims_by_status("AWAITING_REVIEW")`. Wired `POST /decision` → `db.update_claim_status()`. Added new `GET /claims/{claim_id}/images` endpoint that scans `data/uploads/{claim_id}/` and returns image descriptors. Added structured audit logging. |
| `backend/graph/orchestrator.py` | Added `import os`, `import shutil`. Added `_move_pending_uploads(claim_id)` function. Called it in `ClaimOrchestrator.run()` after A4 assigns `state.claim_id` — moves all files from `data/uploads/pending/` → `data/uploads/{claim_id}/` so the dashboard can find and serve them. |

**Frontend — Files Modified:**

| File | What changed |
|---|---|
| `frontend/package.json` | Added `react-router-dom` |
| `frontend/vite.config.js` | Added `/claims`, `/decision`, and `/uploads` proxy entries |
| `frontend/src/main.jsx` | Added `BrowserRouter` + `Routes`. `/` → App (simulator), `/dashboard` → Dashboard |
| `frontend/src/components/ClaimCard.jsx` | Full rewrite — added `useEffect` photo fetch from `/claims/{id}/images`, photo gallery with red Damage / blue Bag Tag thumbnail labels, hover scale effect, full-screen lightbox with caption bar and close button |

**Frontend — Files Created:**

| File | Purpose |
|---|---|
| `frontend/src/pages/Dashboard.jsx` | Staff review page — fetches pending claims, renders ClaimCards, handles approve/reject decisions, optimistic card removal |
| `frontend/src/components/ClaimCard.jsx` | Claim card — photo gallery, severity bar, damage type chips, fraud flags, approve/reject/modify buttons |

**Tests — Created:**

| File | Tests |
|---|---|
| `tests/test_dashboard.py` | 12 tests — GET /claims/pending (3), POST /decision (5), GET /claims/{id}/images (4) |

---

## Key Design Decisions

```
1. PENDING FOLDER → CLAIM FOLDER (the critical fix)
   LocalStorageProvider saves photos to data/uploads/pending/ at upload
   time because the claim_id doesn't exist yet (A4 generates it only when
   the passenger confirms). _move_pending_uploads() is called in
   ClaimOrchestrator.run() immediately after state.claim_id is set.
   Files are moved via shutil.move() to data/uploads/{claim_id}/ so
   GET /claims/{claim_id}/images finds them correctly.

   Before fix: dashboard showed "No photos on file" for every claim.
   After fix:  photos appear in the dashboard under the correct claim.

2. STATICFILES MOUNT FOR PHOTO SERVING
   FastAPI app.mount("/uploads", StaticFiles(directory="data/uploads"))
   serves photos at /uploads/{claim_id}/{filename} directly from disk.
   os.makedirs("data/uploads", exist_ok=True) guards against startup
   failure if the directory doesn't exist yet.
   Phase 2 swap: Cloudflare R2 or S3 signed URLs — change one line in main.py.

3. IS_TAG DETECTION BY FILENAME PREFIX
   "tag" in filename.lower() → is_tag=True (blue Bag Tag label).
   "damage" prefix → is_tag=False (red Damage label).
   Consistent with A2/A3 filtering logic throughout the pipeline.

4. PATCH AT ROUTE LEVEL NOT DEPENDENCIES
   Tests patch "backend.api.routes.decision.provide_db" not
   "backend.dependencies.provide_db". The lru_cache on provide_db means
   patching at source has no effect after the first real call.

5. LIGHTBOX UX
   Click thumbnail → full-screen lightbox with dark backdrop.
   Click outside or ✕ → close. Click inside → stays open (stopPropagation).
   Caption shows filename + Damage / Bag Tag pill.

6. OPTIMISTIC UI UPDATE
   Claim card disappears from list immediately on approve/reject.
   No re-fetch needed — faster UX for demo.

7. NO AUTH FOR POC
   Per tracker note. agent_id hardcoded "AGENT-001".
   Field already in DecisionRequest + logged for audit trail.
   Phase 2 adds JWT middleware — additive change only.
```

---

## Upload → Dashboard Full Flow (Post-Fix)

```
Passenger uploads damage + tag photos (T-013 simulator)
        ↓
LocalStorageProvider saves to data/uploads/pending/
  damage_xxx.jpg
  tag_yyy.jpg

Passenger confirms → A4 runs → claim_id = CLM-20260526-94E2
        ↓
_move_pending_uploads("CLM-20260526-94E2") runs
  shutil.move: pending/damage_xxx.jpg → CLM-20260526-94E2/damage_xxx.jpg
  shutil.move: pending/tag_yyy.jpg    → CLM-20260526-94E2/tag_yyy.jpg
        ↓
Log: uploads_moved_to_claim  count=2  claim_id=CLM-20260526-94E2

A5 sets status = AWAITING_REVIEW in Supabase
        ↓
Staff opens /dashboard
  GET /claims/pending → Supabase returns CLM-20260526-94E2
        ↓
ClaimCard mounts
  GET /claims/CLM-20260526-94E2/images
    → scans data/uploads/CLM-20260526-94E2/ ✅
    → returns [{url: "/uploads/CLM-.../damage_xxx.jpg", is_tag: false},
               {url: "/uploads/CLM-.../tag_yyy.jpg",    is_tag: true}]
        ↓
Browser fetches
  GET /uploads/CLM-20260526-94E2/damage_xxx.jpg → StaticFiles → 200 ✅
  GET /uploads/CLM-20260526-94E2/tag_yyy.jpg    → StaticFiles → 200 ✅
        ↓
ClaimCard renders:
  [📷 Damage 1]  [📷 Bag Tag]
  Click → lightbox → full-size photo
        ↓
Staff clicks Approve
  POST /decision {action: "approve", agent_id: "AGENT-001"}
  → db.update_claim_status("CLM-...", "RESOLVED")
  → card disappears ✅
```

---

## Dependencies

```
Depends On          →  T-014 (Supabase DB — SupabaseDBProvider)
                       T-015 (A5 sets AWAITING_REVIEW on Lane 2 claims)
External Libraries  →  react-router-dom (new — added to package.json)
                       fastapi.staticfiles (FastAPI built-in — no new install)
                       shutil, os (Python stdlib — no new install)
Environment Vars    →  SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY (existing)
                       No new env vars added.
```

---

## Testing

```bash
pytest tests/test_dashboard.py -v
# Expected: 12 passed

pytest tests/ -v
# Expected: 204 passed total

black backend/ tests/ && isort backend/ tests/
```

**Acceptance Criteria:**

```
✅ GET /claims/pending returns AWAITING_REVIEW claims from Supabase
✅ POST /decision approve → RESOLVED in Supabase + audit log
✅ POST /decision reject  → REJECTED in Supabase + audit log
✅ GET /claims/{id}/images → correct URL list from data/uploads/{id}/
✅ GET /uploads/{id}/{file} → image bytes served via StaticFiles
✅ _move_pending_uploads() moves files from pending/ → {claim_id}/ after A4
✅ Dashboard renders at /dashboard with claim cards
✅ Photos shown with Damage (red) / Bag Tag (blue) thumbnail labels
✅ Click thumbnail → full-screen lightbox with filename + type caption
✅ Approve / Reject / Modify all functional
✅ Optimistic card removal after decision
✅ Empty state when no pending claims
✅ 12 tests passing
✅ 204 total tests passing
✅ black + isort clean
```

---

## PR Checklist

```
[x] PR title includes Task ID
[x] Base branch: develop (not main)
[x] Reviewer: Devam
[x] DBProvider ABC used in routes — no direct SupabaseDBProvider imports
[x] No hardcoded API keys
[x] Tests patch at route level (bypass lru_cache)
[x] StaticFiles mount with os.makedirs guard
[x] _move_pending_uploads() called after claim_id assigned
[x] react-router-dom in package.json
[x] /uploads proxy in vite.config.js
[x] 12 tests passing
[x] 204 total tests passing
[x] black + isort clean
[x] Branch doc in BRANCH_DOCS/WEEK3_DOCS/
[x] Squash merged to develop
[x] Feature branch deleted after merge
```

---

## Notes

```
Photo mapping     →  Photos belong to the claim that was active when the
                     passenger confirmed. If two passengers submit at the
                     exact same second, pending/ could mix photos. For POC
                     demo (sequential use) this is fine. Phase 2 fix: prefix
                     uploaded filenames with session_id before saving.

Auth              →  No auth per tracker. Phase 2 adds JWT middleware.

lru_cache fix     →  Tests patch backend.api.routes.decision.provide_db.
                     Patching backend.dependencies.provide_db fails because
                     lru_cache returns the real Supabase instance after first call.

Parallel          →  T-018 (Aditya — QR code). Zero file overlap.

Next tasks        →  T-019 Devam, T-020 Aditya, T-021 Anoushka

Blockers          →  None.
```

---

*Branch opened: Day 11, Week 3 — Anoushka Vyas*
*Merged to develop: Day 13, Week 3*
