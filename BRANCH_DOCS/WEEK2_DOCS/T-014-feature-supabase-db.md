# BRANCH: feature/supabase-db

---

## Branch Metadata

```
Branch Name   →  feature/supabase-db
Task ID       →  T-014
Workstream    →  Data / Storage
Author        →  Aditya
Reviewer      →  Anoushka
Start Date    →  Day 8, Week 2
Target Merge  →  Day 9, Week 2
Actual Merge  →  Day 9, Week 2
Status        →  Merged
```

---

## Objective

**What does this branch do?**
Implements the real Supabase database layer behind the existing `DBProvider` ABC.
All five methods in `SupabaseDBProvider` were previously TODO stubs returning
hard-coded values. This branch replaces every stub with a real `supabase-py`
client call, provides the full SQL migration to run once in the Supabase
dashboard, and adds 15 unit tests that verify every method in isolation
without needing a live Supabase connection.

**Why is it needed?**
T-012 (A4 Decision Engine) already calls `save_claim()` and `get_claim_count()`
— but they were stubbed, so claims were never actually persisted anywhere.
T-015 (A5 Notification) calls `update_claim_status()` to set `AWAITING_REVIEW`
on Lane 2 claims. T-017 (Agent Dashboard) calls `get_claim()` to populate the
review cards. None of those tasks can be properly tested without a working DB
layer. T-014 is the foundation every other Week 2+ task depends on.

---

## Local Setup

```bash
# ── 1. Activate virtual environment ──────────────────────────────────────────
source venv/Scripts/activate      # Windows — Git Bash
# source venv/bin/activate        # Mac / Linux

# ── 2. Install dependencies (supabase already in requirements.txt) ────────────
pip install -r requirements.txt

# ── 3. Fill in your .env ─────────────────────────────────────────────────────
cp .env.example .env
# Add these three lines (get values from your Supabase project → Settings → API):
#   SUPABASE_URL=https://<your-ref>.supabase.co
#   SUPABASE_ANON_KEY=<your-anon-key>
#   SUPABASE_SERVICE_ROLE_KEY=<your-service-role-key>

# ── 4. Run the SQL migration in Supabase ──────────────────────────────────────
# Go to: https://supabase.com → your project → SQL Editor → New Query
# Paste the SQL from the "SQL Migration" section below → Run

# ── 5. Start backend ─────────────────────────────────────────────────────────
uvicorn backend.main:app --reload --port 8000

# ── 6. Run tests ─────────────────────────────────────────────────────────────
pytest tests/test_supabase_db.py -v
```

---

## SQL Migration

Run this **once** in your Supabase project's SQL Editor before starting the backend.
(Dashboard → SQL Editor → New Query → paste → Run)

```sql
-- ── claims table ─────────────────────────────────────────────────────────────
create table if not exists claims (
    id              text primary key,
    pnr             text,
    bag_id          text,
    flight_number   text,
    damage_types    jsonb,
    severity_score  float,
    is_luxury       boolean default false,
    brand           text,
    compensation    float,
    fraud_score     float  default 0,
    fraud_flags     jsonb  default '[]',
    routing_lane    int,
    voucher_code    text,
    status          text   default 'PENDING',
    created_at      timestamptz default now(),
    updated_at      timestamptz default now()
);

-- ── image_hashes table (pHash duplicate fraud check) ─────────────────────────
create table if not exists image_hashes (
    id          bigserial primary key,
    pnr         text    not null,
    hash_value  text    not null,
    claim_id    text    references claims(id) on delete cascade,
    created_at  timestamptz default now()
);

-- ── indexes ───────────────────────────────────────────────────────────────────
create index if not exists idx_claims_pnr        on claims (pnr);
create index if not exists idx_claims_status     on claims (status);
create index if not exists idx_image_hashes_pnr  on image_hashes (pnr);

-- ── Row Level Security (disabled for POC — service-role key handles auth) ─────
alter table claims       disable row level security;
alter table image_hashes disable row level security;
```

**Verify it worked:**
- Go to Supabase → Table Editor → you should see `claims` and `image_hashes` tables.
- Or run: `select count(*) from claims;` → should return `0` (empty, ready to go).

---

## Technical Approach

### Files Modified

```
backend/db/supabase_client.py   →  Replaced all 5 TODO stubs with real
                                    supabase-py client calls:
                                    - save_claim()           insert into claims
                                    - update_claim_status()  update status column
                                    - get_claim()            select by id
                                    - get_claim_count()      count by pnr + interval
                                    - get_recent_hashes()    select from image_hashes
```

### Files Created

```
tests/test_supabase_db.py       →  15 unit tests covering all 5 methods
                                    + __init__ validation (missing url/key).
                                    All supabase-py calls are mocked — no
                                    live Supabase connection needed in tests.

BRANCH_DOCS/WEEK2_DOCS/
  T-014-feature-supabase-db.md  →  This file.
```

### Provider / Abstraction Used

`SupabaseDBProvider` implements `DBProvider` ABC (`backend/db/base.py`).
Agent code (A4, A5, dashboard route) only ever calls `DBProvider` methods —
they never import Supabase directly. Swapping to any PostgreSQL backend in
Phase 2 requires only writing a new `PostgresDBProvider` class and setting
`DB_PROVIDER=postgres` in `.env`.

### Key Design Decisions

| Decision | Reason |
|---|---|
| Service-role key for all backend calls | Bypasses Row Level Security cleanly for POC. Frontend never sees this key. |
| `count="exact"` on claim frequency query | Supabase-py returns `.count` only when explicitly requested — avoids fetching all rows just to count them. |
| `gte("created_at", "now() - interval '30 days'")` | Passes Postgres interval syntax directly — no Python datetime arithmetic needed. |
| `RuntimeError` on empty `save_claim` response | Silent failure here would cause a null `claim_id` to propagate through A4/A5 — better to fail loud. |
| `__init__` validates url/key before calling `create_client` | Gives a clear, actionable error message if `.env` is misconfigured, rather than a cryptic Supabase SDK error. |

### Future Swap Path

Replace `SupabaseDBProvider` with `PostgresDBProvider` (asyncpg/SQLAlchemy)
by implementing the same 5 `DBProvider` abstract methods and setting
`DB_PROVIDER=postgres` in `.env`. Zero changes to any agent code.

---

## Dependencies

**Depends On (Task IDs):** T-012 (A4 calls `save_claim` + `get_claim_count`)

**External Libraries:**
```
supabase==2.10.0    # already in requirements.txt from T-002
```

**Environment Variables (add to .env):**
```
SUPABASE_URL=https://<your-project-ref>.supabase.co
SUPABASE_ANON_KEY=<your-anon-key>
SUPABASE_SERVICE_ROLE_KEY=<your-service-role-key>
DB_PROVIDER=supabase   # default — already set in .env.example
```

Get these from: Supabase Dashboard → Your Project → Settings → API

---

## Testing

### Automated Tests

**File:** `tests/test_supabase_db.py`
**Run:** `pytest tests/test_supabase_db.py -v`
**Result:** 15 passed, 0 failed

| Test | What it verifies |
|---|---|
| `test_init_raises_on_missing_url` | ValueError when SUPABASE_URL is None |
| `test_init_raises_on_missing_key` | ValueError when SERVICE_ROLE_KEY is None |
| `test_init_raises_on_empty_url` | ValueError when SUPABASE_URL is `""` |
| `test_save_claim_inserts_and_returns_id` | Correct insert call + returns claim_id |
| `test_save_claim_raises_on_empty_response` | RuntimeError on empty Supabase response |
| `test_update_claim_status_calls_update` | Correct `.update().eq().execute()` chain |
| `test_update_claim_status_resolved` | Works with RESOLVED status (agent approve) |
| `test_get_claim_returns_dict_when_found` | Returns claim dict when row exists |
| `test_get_claim_returns_none_when_not_found` | Returns None when no row found |
| `test_get_claim_count_returns_integer` | Returns count integer from Supabase |
| `test_get_claim_count_zero_for_new_pnr` | Returns 0 for first-time PNR |
| `test_get_claim_count_passes_pnr_filter` | Filters by PNR correctly |
| `test_get_recent_hashes_returns_list` | Returns list of hash strings |
| `test_get_recent_hashes_empty_for_new_pnr` | Returns `[]` for new PNR |
| `test_get_recent_hashes_filters_by_pnr` | Queries `image_hashes` table, filters by pnr |

### Manual Smoke Test (with real Supabase)

After running the SQL migration and setting `.env`:

```bash
# 1. Start backend
uvicorn backend.main:app --reload --port 8000

# 2. Run a full claim via the simulator (localhost:5173)
#    Upload damage photos → upload tag photo → confirm
#    Lane 1 result → voucher shown

# 3. Check Supabase dashboard → Table Editor → claims
#    A row should appear with:
#      id         = CLM-YYYYMMDD-XXXX
#      pnr        = extracted from bag tag
#      status     = PENDING
#      routing_lane = 1 (Lane 1) or 2 (Lane 2)

# 4. Quick Python smoke test
python -c "
import asyncio
from backend.db.supabase_client import SupabaseDBProvider
from backend.config import get_settings

s = get_settings()
db = SupabaseDBProvider(url=s.supabase_url, service_role_key=s.supabase_service_role_key)

async def test():
    count = await db.get_claim_count('TEST01', days=30)
    print('Claim count for TEST01:', count)
    result = await db.get_claim('CLM-DOESNOTEXIST')
    print('get_claim for nonexistent:', result)

asyncio.run(test())
print('Supabase DB smoke test PASSED')
"
```

✅ **Acceptance criteria:**
- After full flow, a row is visible in the Supabase `claims` table with correct data.
- `pytest tests/test_supabase_db.py` → 15 passed, 0 failed.

---

## PR Checklist

- [x] Type hints on all new functions
- [x] Docstrings on all public functions (Google style)
- [x] `.env.example` already has SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY documented
- [x] No hardcoded provider names in agents/ — DB only accessed via DBProvider ABC
- [x] 15 tests written — all passing
- [x] `pytest tests/test_supabase_db.py` passes locally
- [x] PR description filled out on GitHub
- [x] Reviewer (Anoushka) assigned

---

## Notes / Blockers

**Known limitations (POC scope):**
- `image_hashes` table is created but the hash insertion logic (saving new pHash values after a claim is processed) is not implemented in this branch — deferred to Phase 2. A4's `get_recent_hashes()` will return `[]` until hashes are being written.
- `update_claim_status()` is called by A5 and the `/decision` endpoint but the A5 wiring (TODO T-015) is not yet done — this is expected.
- RLS is disabled for POC. In production: enable RLS, create a service-role policy, and never expose the service-role key outside backend.

**Links:**
- Supabase free tier: https://supabase.com/pricing
- supabase-py docs: https://supabase.com/docs/reference/python/introduction
- DBProvider ABC: `backend/db/base.py`