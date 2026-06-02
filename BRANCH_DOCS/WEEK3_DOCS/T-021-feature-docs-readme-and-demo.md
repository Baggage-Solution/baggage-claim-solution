# BRANCH: docs/readme-and-demo

---

## Branch Metadata

```
Branch Name   →  docs/readme-and-demo
Task ID       →  T-021
Workstream    →  Documentation
Author        →  Anoushka 
Reviewer      →  Aditya
Start Date    →  Day 13, Week 3
Target Merge  →  Day 14, Week 3
Actual Merge  →  Day 14, Week 3
Status        →  Merged
```

---

## Objective

**What does this branch do?**
Fills the README.md skeleton with a complete local-run walkthrough and
creates docs/demo_script.md — a step-by-step mentor demo guide covering
all 3 test scenarios with exact test data filenames, technical Q&A prep,
and a pre-demo checklist.

**Why is it needed?**
T-021 is the documentation gate before T-022 (Final Integration). The
acceptance criterion is: a new team member can set up the project from
README alone in under 15 minutes. The demo script ensures the mentor
presentation runs smoothly with no surprises — all 3 scenarios rehearsed
with exact file names and expected outputs documented.

---

## Local Setup

```bash
# Activate venv
source venv/Scripts/activate      # Git Bash on Windows
source venv/bin/activate          # Mac / Linux

# Run backend
uvicorn backend.main:app --reload --port 8000

# Run frontend
cd frontend && npm run dev

# Run tests
pytest tests/ -v
```

---

## Technical Approach

**Files Modified:**
```
README.md                   →  Complete rewrite of skeleton:
                                - Quick Start (7 steps, <15 min)
                                - System Architecture (full tree)
                                - API Reference table (all 8 endpoints)
                                - Claim Routing Logic explanation
                                - 3 Test Scenarios with exact fixture filenames
                                - Swap Any Provider section
                                - QR Code mobile demo instructions
                                - Environment Variables reference table
                                - Make Commands reference
```

**Files Created:**
```
docs/demo_script.md         →  Step-by-step mentor demo walkthrough:
                                - Pre-demo setup checklist
                                - Opening narrative (2 min)
                                - Scenario A: Lane 1 standard bag (4 min)
                                - Scenario B: Lane 2 luxury bag + dashboard (4 min)
                                - Scenario C: Blurry tag retry (3 min)
                                - Technical Q&A prep (5 questions with answers)
                                - Demo checklist
                                - Timing guide
```

**Files Already Complete (No Changes Needed):**
```
CONTRIBUTING.md             →  Git standards — complete from T-001
GIT_WORKFLOW.md             →  Git reference — complete from T-001
BRANCH_DOCS/TEMPLATE.md     →  Branch doc template — complete from T-001
.env.example                →  All vars documented with descriptions
```

---

## What the README Covers

```
Section 1  — What This Is (system overview + 5-agent pipeline)
Section 2  — Quick Start (7-step setup, <15 min target)
Section 3  — System Architecture (full folder tree)
Section 4  — API Reference (all 8 endpoints tabulated)
Section 5  — Claim Routing Logic (Lane 1/2 thresholds + fraud checks)
Section 6  — Test Scenarios (3 demo scenarios with exact fixture filenames)
Section 7  — Swap Any Provider (env var pattern explained)
Section 8  — QR Code Mobile Demo (ngrok instructions)
Section 9  — Environment Variables Reference (all vars with defaults)
Section 10 — Make Commands
Section 11 — Contributing (branch pattern + links)
```

---

## What the Demo Script Covers

```
Pre-Demo   — terminal setup, browser tabs, test images checklist
Opening    — 2-minute system narrative for mentor
Scenario A — Lane 1 standard bag step-by-step with exact narration
             Image: tests/fixtures/damaged/damaged_01.jpg
             Image: tests/fixtures/bag_tags/clear_tag_01.jpg
             Expected: voucher VCH-XXXXXXXX, status=APPROVED in Supabase
Scenario B — Lane 2 luxury bag + staff dashboard approve
             Image: tests/fixtures/damaged/luxury_01.jpg
             Image: tests/fixtures/bag_tags/clear_tag_01.jpg
             Expected: Under Review card, dashboard approval, status=RESOLVED
Scenario C — Blurry tag retry then recovery
             Image: tests/fixtures/damaged/damaged_02.jpg
             Image: any unclear image as tag
             Expected: re_request_tag=True, retry prompt, re-upload recovers
Q&A Prep   — 5 likely technical questions with scripted answers:
             Provider swap architecture
             Graceful failure handling
             Fraud detection explanation
             Cost breakdown
             Phase 2 roadmap
Checklist  — 10-point pre-demo verification list
Timing     — 18 minutes total with per-section breakdown
```

---

## Dependencies

```
Depends On          →  T-016 (Week 2 integration — all features must be working
                       before README can be verified end-to-end)
                       T-017 (Dashboard — demo Scenario B uses it)
                       T-018 (QR code — QR section of README documents it)
                       T-019 (Cleanup — README reflects final codebase)
                       T-020 (Test suite — README references pytest)
External Libraries  →  None new
Environment Vars    →  None new
```

---

## Testing

**How to Verify README (Manual):**
```bash
# Fresh terminal — follow README exactly from Step 1:
git clone <repo-url>
cd baggage-claim-solution
python -m venv venv && source venv/Scripts/activate
pip install -r requirements.txt
cp .env.example .env
# Fill GEMINI_API_KEY, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
uvicorn backend.main:app --reload --port 8000
# Open http://localhost:8000/health → {"status":"ok","configured":{"gemini":true,"supabase":true}}
# Target: setup complete in < 15 minutes from git clone ✓
```

**How to Verify Demo Script (Manual):**
```bash
# Run all 3 scenarios end-to-end:
# Scenario A: damage_01.jpg + clear_tag_01.jpg → Lane 1 voucher ✓
# Scenario B: luxury_01.jpg + clear_tag_01.jpg → Lane 2 Under Review → Dashboard approve ✓
# Scenario C: damage_02.jpg + blurry image → retry prompt → clear_tag → pipeline ✓
```

**Automated Tests:**
```bash
# No new test files — T-021 is documentation only
# All existing tests must still pass after README changes
pytest tests/ -v
# Expected: all tests passing, 0 failures
```

**Acceptance Criteria:**
```
✅ README.md covers all 7 setup steps in correct order
✅ New team member can set up from README alone in < 15 min
✅ API reference covers all 8 endpoints
✅ Routing logic documented with thresholds
✅ All 3 test scenarios have exact fixture filenames
✅ Provider swap section explains the pattern
✅ QR code mobile demo instructions included
✅ docs/demo_script.md exists with all 3 scenarios + Q&A prep
✅ Demo checklist included in script
✅ pytest tests/ → 0 failures (no regressions from doc changes)
```

---

## PR Checklist

```
[x] PR title includes Task ID — [T-021] docs(readme): ...
[x] PR description filled out on GitHub
[x] Base branch set to develop (not main)
[x] Reviewer assigned — Aditya
[x] README.md complete with all sections
[x] docs/demo_script.md created with all 3 scenarios
[x] All 3 demo scenarios manually verified end-to-end
[x] pytest tests/ → 0 failures
[x] Squash merged to develop
[x] Feature branch deleted after merge
```

---

## Notes / Blockers

```
Known Issues  →  None

Co-authorship →  T-021 is listed as Anoushka + Devam jointly in the tracker.
                 README prose and architecture sections authored by Devam.
                 Demo script scenarios and narration authored collaboratively.

Blockers      →  None — T-021 complete and merged

Next Task     →  T-022 (Final Integration, Bug Fixes & Demo Prep) — Devam
                 All Week 3 PRs must be merged before T-022 begins.

Links         →  README.md:          repo root
                 demo_script.md:     docs/demo_script.md
                 FastAPI Swagger:    http://localhost:8000/docs
                 Test fixtures:      tests/fixtures/damaged/ + tests/fixtures/bag_tags/
```
