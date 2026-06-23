# CLAUDE.md
> This file is for Claude Code sessions. The full operating manual is **[AGENTS.md](./AGENTS.md)** — read it first.
> This file is kept because Claude Code looks for `CLAUDE.md` by convention. It mirrors AGENTS.md and adds a few Claude-Code-specific notes.

---

## TL;DR for Claude

Before you do anything in this repo:

1. **Read [AGENTS.md](./AGENTS.md) in full.** It's the authoritative operating manual.
2. **Read [CONTRIBUTING.md](./CONTRIBUTING.md) §1, §6, §7** before any code change. The agnosticism rules in §7 are non-negotiable.
3. **Read the relevant SKILL.md** if you have one for skills like `xlsx`, `docx`, `pdf`, `pptx` — those are environment-specific.

---

## The 3 rules you must never break

```
1. CLOUD-AGNOSTIC    — agents/graph/api/core MUST NOT import boto3 or any cloud SDK
2. CHANNEL-AGNOSTIC  — agents/graph/api/core MUST NOT mention WhatsApp/Meta/Telegram
3. MODEL-AGNOSTIC    — agents/graph/api/core MUST NOT hardcode model IDs
```

If a proposed change violates any of these, STOP, redesign, then proceed.

---

## When making changes

1. Open `BRANCH_DOCS/AWS_PHASE/TEMPLATE.md` first — your work needs to fit this template.
2. Use `Edit` / `str_replace` to modify existing files, `Create` only for genuinely new files.
3. Keep new files under 300 lines. Type hints + Google-style docstrings on every function.
4. Run `pytest tests/<relevant>.py -v` after each provider/agent change.
5. Run `black backend/ tests/ && isort backend/ tests/` before suggesting the user commit.
6. Run the cloud-agnostic + channel-agnostic greps before you say "done":

```bash
grep -rn "boto3\|aws_\|import anthropic\|import google\|supabase" \
  backend/agents/ backend/graph/ backend/api/ backend/core/

grep -rni "whatsapp\|meta\|telegram\|twilio\|sms" \
  backend/agents/ backend/graph/ backend/api/ backend/core/
```

Both must return zero lines. If either has a hit, fix it before declaring the task complete.

---

## What NOT to do in this repo

```
❌ Don't create new top-level folders without explicit user approval
❌ Don't introduce new dependencies in requirements.txt without flagging it
❌ Don't change config.py defaults silently — call them out
❌ Don't call real AWS / Meta APIs in tests
❌ Don't write or print secret values, even masked
❌ Don't suggest docker build commands — GitHub Actions is the only builder
❌ Don't propose merges to develop or main — only develop-aws during this phase
```

---

## Tracker

The sprint tracker is `AWS_Phase_Tracker.xlsx` at repo root. Every code change is tied to a P-XXX task. When the user asks you to "do P-XYZ", read that row's Pick Up steps, Deliverable, and Acceptance Criteria — they're authoritative.

---

*Last updated: AWS Production Phase Day 1*
