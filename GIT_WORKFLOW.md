# Git Workflow Reference
### ABC Airline — Baggage Claim AI POC
> Quick reference for all common Git situations. No need to ask — just find your scenario below.

---

## Table of Contents

1. [Starting a New Task](#1-starting-a-new-task)
2. [Daily Routine](#2-daily-routine)
3. [Merging Your Branch to Develop](#3-merging-your-branch-to-develop)
4. [Someone Else Merged While You Were Working](#4-someone-else-merged-while-you-were-working)
5. [Handling Rebase Conflicts](#5-handling-rebase-conflicts)
6. [Oops — I Committed to Wrong Branch](#6-oops--i-committed-to-wrong-branch)
7. [Oops — I Committed Bad Code](#7-oops--i-committed-bad-code)
8. [Checking What's Going On](#8-checking-whats-going-on)
9. [After Your PR is Merged](#9-after-your-pr-is-merged)
10. [PR Description Template](#10-pr-description-template)
11. [Commit Message Cheatsheet](#11-commit-message-cheatsheet)
12. [The Golden Rules](#12-the-golden-rules)

---

## 1. Starting a New Task

**Always branch off the latest develop — never off main, never off someone else's branch.**

```bash
# Step 1 — sync develop first
git checkout develop
git pull origin develop

# Step 2 — create your task branch
git checkout -b feature/T-XXX-short-desc

# Step 3 — activate venv (every new terminal)
source venv/Scripts/activate      # Git Bash on Windows
# OR
source venv/bin/activate           # Mac / Linux

# Step 4 — confirm you're on the right branch
git branch
# Should show: * feature/T-XXX-short-desc
```

**Branch naming:**
```
feature/T-006-vision-provider-gemini   ← new feature
chore/repo-setup                       ← setup / config
docs/readme-and-demo                   ← documentation
integration/week1-backend-llm          ← integration task
```

---

## 2. Daily Routine

### Morning — Start of Day
```bash
# Always sync develop before starting work
git checkout develop
git pull origin develop

# Switch back to your task branch
git checkout feature/T-XXX-name
```

### During the Day — Commit Often
```bash
git add .
git commit -m "feat(scope): what you just built"
```

### End of Day — Push WIP (even if not done)
```bash
git add .
git commit -m "WIP: T-XXX brief description of where you left off"
git push origin feature/T-XXX-name
```

> **Rule: never leave uncommitted work overnight.**
> If your laptop dies, your work is safe on GitHub.

---

## 3. Merging Your Branch to Develop

**Full flow every time you finish a task:**

```bash
# Step 1 — run tests first, must be green before anything else
pytest tests/ -v

# Step 2 — format code
black backend/
isort backend/

# Step 3 — sync develop
git checkout develop
git pull origin develop

# Step 4 — rebase your branch on top of develop
git checkout feature/T-XXX-name
git rebase develop

# Step 5 — run tests again after rebase (confirm nothing broke)
pytest tests/ -v

# Step 6 — push your branch
git push origin feature/T-XXX-name
# If you rebased, you may need:
git push origin feature/T-XXX-name --force-with-lease

# Step 7 — open PR on GitHub
#   Base branch : develop  ← IMPORTANT, never main
#   Title       : [T-XXX] type(scope): description
#   Reviewer    : assign the right person (see CONTRIBUTING.md)

# Step 8 — after approval on GitHub
#   Click: Squash and merge
#   Click: Delete branch

# Step 9 — clean up locally
git checkout develop
git pull origin develop
git branch -d feature/T-XXX-name

# Step 10 — notify team
# Post in group chat: "T-XXX merged to develop ✓"
```

---

## 4. Someone Else Merged While You Were Working

**This is the most common situation in parallel work.**

```
SITUATION:
You are working on T-006.
Aditya merges T-005 to develop while you are mid-task.
Your branch is now behind develop.

YOUR BRANCH:   T001 → T002 → [your work]
DEVELOP:       T001 → T002 → T005

YOU NEED:      T001 → T002 → T005 → [your work]
```

**Fix — rebase your branch on top of latest develop:**

```bash
# Step 1 — pull the new changes into develop
git checkout develop
git pull origin develop

# Step 2 — rebase your branch on top
git checkout feature/T-XXX-name
git rebase develop

# Step 3 — run tests to confirm nothing broke
pytest tests/ -v

# Step 4 — push (force needed because rebase rewrote history)
git push origin feature/T-XXX-name --force-with-lease

# Result:
# YOUR BRANCH:  T001 → T002 → T005 → [your work]  ✅
```

**Why rebase and not merge?**
```
merge creates:   T001 → T002 → T005 → [your work] → merge-commit
rebase creates:  T001 → T002 → T005 → [your work]

Rebase = cleaner history, no unnecessary merge commits.
Our project uses rebase. Always.
```

**When to do this:**
```
✅ Teammate posts "T-XXX merged to develop ✓" in group chat → rebase immediately
✅ Before opening any PR → always rebase first
✅ You haven't synced in 2+ days → rebase
```

---

## 5. Handling Rebase Conflicts

**A conflict means two people edited the same lines in the same file.**

```bash
git rebase develop
# OUTPUT:
# CONFLICT (content): Merge conflict in backend/config.py
# error: could not apply abc1234... your commit message
```

**Step by step fix:**

```bash
# Step 1 — see which files have conflicts
git status
# Shows: "both modified: backend/config.py"

# Step 2 — open the conflicted file in VS Code
# Look for conflict markers:
<<<<<<< HEAD
their version of the code (from develop)
=======
your version of the code
>>>>>>> your commit message

# Step 3 — edit the file to keep the RIGHT version
# Delete the markers and keep what makes sense
# Usually: keep BOTH changes combined

# Step 4 — mark the conflict as resolved
git add backend/config.py

# Step 5 — continue the rebase
git rebase --continue

# Step 6 — if more conflicts appear, repeat steps 2-5
# Step 7 — when done, run tests
pytest tests/ -v
```

**If you make a mess and want to start over:**
```bash
git rebase --abort
# This puts you back to exactly where you were before rebase started
```

**How to avoid conflicts in the first place:**
```
✅ Rebase on develop every morning before starting work
✅ Don't edit config.py, requirements.txt, or main.py unless your task requires it
✅ Communicate in group chat before touching shared files
✅ Keep your task branch short-lived — open PR as soon as task is done
```

---

## 6. Oops — I Committed to Wrong Branch

```bash
# SITUATION: you committed to develop instead of your feature branch

# Step 1 — create the feature branch from where you are
git checkout -b feature/T-XXX-name

# Step 2 — go back to develop and undo the commit there
git checkout develop
git reset --hard origin/develop
# This resets develop to match what's on GitHub (removes your local commit)

# Your work is safe on feature/T-XXX-name ✅
```

---

## 7. Oops — I Committed Bad Code

**Scenario A — not pushed yet (easy fix):**
```bash
# Undo last commit but KEEP your file changes
git reset --soft HEAD~1
# Now fix the code, then commit again
```

**Scenario B — pushed but PR not merged yet:**
```bash
# Fix the code, then add a new commit
git add .
git commit -m "fix(scope): correct the issue"
git push origin feature/T-XXX-name
# The PR will automatically update with the new commit
```

**Scenario C — need to completely undo last commit and changes:**
```bash
# WARNING: this deletes your changes permanently
git reset --hard HEAD~1
git push origin feature/T-XXX-name --force-with-lease
```

---

## 8. Checking What's Going On

```bash
# Where am I? What branch? Any uncommitted changes?
git status

# See all branches (local + remote)
git branch -a

# See recent commit history (clean one-line view)
git log --oneline -10

# See what changed in a file
git diff backend/vision_provider/gemini_vision.py

# See all commits on your branch that aren't on develop yet
git log develop..HEAD --oneline

# Check if your branch is ahead or behind develop
git fetch origin
git status
# Shows: "Your branch is behind 'origin/develop' by 2 commits"
```

---

## 9. After Your PR is Merged

```bash
# Step 1 — switch to develop and pull the merged code
git checkout develop
git pull origin develop

# Step 2 — delete your local feature branch (already deleted on GitHub)
git branch -d feature/T-XXX-name

# Step 3 — start next task immediately
git checkout -b feature/T-YYY-next-task

# Step 4 — notify team
# "T-XXX merged ✓ — starting T-YYY now"
```

---

## 10. PR Description Template

**Copy this every time you open a PR:**

```
## What changed
- [bullet: main thing you built]
- [bullet: second thing]
- [bullet: tests written]

## How to test
1. [exact command to run]
2. [what to check]
3. Expected result: [what you should see]

## Smoke test results (if applicable)
- [input] → [output] ✅

## Task
T-XXX — Task Name
```

**PR Title format:**
```
[T-006] feat(vision): Gemini Vision provider — damage analysis + brand classification
  ↑        ↑              ↑
task ID   type(scope)    short description (max 72 chars)
```

**Reviewer assignment:**
```
Devam     →  assign Anoushka
Anoushka  →  assign Devam
Aditya    →  assign Devam
```

---

## 11. Commit Message Cheatsheet

```
FORMAT:  <type>(<scope>): <short description>
LIMIT:   72 characters max
TENSE:   present tense ("add feature" not "added feature")

TYPES:
feat      → new feature
fix       → bug fix
chore     → setup, config, tooling
docs      → documentation only
test      → adding/updating tests
refactor  → restructure, no behaviour change
style     → formatting only (black/isort ran)
WIP       → end-of-day push, not ready to merge

GOOD EXAMPLES:
feat(vision): add Gemini Flash damage analysis wrapper
fix(a4-decision): correct severity formula weight calculation
chore(config): upgrade Gemini model from 1.5-flash to 2.5-flash
test(vision): add 8 unit tests with mocked Gemini responses
docs(T-006): add branch doc for feature/vision-provider-gemini
WIP: T-006 testing image loading and JSON parsing

BAD EXAMPLES:
fixed stuff          ❌
update               ❌
ok now it works      ❌
changes              ❌
```

---

## 12. The Golden Rules

```
RULE 1 — Never push directly to main or develop
         Always use a feature branch + PR

RULE 2 — Always rebase before opening a PR
         git checkout develop && git pull
         git checkout feature/T-XXX && git rebase develop

RULE 3 — Always run tests before pushing
         pytest tests/ -v  →  must be green

RULE 4 — Always format before committing
         black backend/ && isort backend/

RULE 5 — Never leave uncommitted work overnight
         WIP commit + push at end of every day

RULE 6 — One task = one branch = one PR
         Never mix two tasks in one branch

RULE 7 — Squash merge only
         Keeps develop history clean — one commit per task

RULE 8 — Delete branch after merge
         On GitHub: click "Delete branch" after squash merge
         Locally: git branch -d feature/T-XXX-name

RULE 9 — Notify team after every merge
         "T-XXX merged to develop ✓" in group chat

RULE 10 — When in doubt, rebase
          Rebase is always safer than merge for feature branches
          If rebase goes wrong: git rebase --abort to start over
```

---

## Quick Decision Tree

```
Need to start a new task?
→ Section 1

End of day, saving progress?
→ Section 2 (Daily Routine)

Task done, ready to merge?
→ Section 3

Teammate merged to develop while I was working?
→ Section 4

Got conflict during rebase?
→ Section 5

Committed to wrong branch?
→ Section 6

Committed bad code?
→ Section 7

Just want to check what's happening?
→ Section 8
```

---

*Reference guide created: Week 1, Day 4*
*Team: Anoushka · Aditya · Devam*
