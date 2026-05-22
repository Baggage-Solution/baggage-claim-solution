# BRANCH: feature/langgraph-skeleton

---

## Branch Metadata

```
Branch Name   →  feature/langgraph-skeleton
Task ID       →  T-005
Workstream    →  LangGraph / Orchestration
Author        →  Aditya
Reviewer      →  Anoushka
Start Date    →  Day 2, Week 1
Target Merge  →  Day 3, Week 1
Actual Merge  →  Day 3, Week 1
Status        →  Merged
```

---

## Objective

**What does this branch do?**
Completes the LangGraph orchestration layer by wiring `MemorySaver` as the session
checkpointer and passing `thread_id = session_id` into every `ainvoke()` call. Adds a
`pytest.ini` for async test configuration and three smoke tests that confirm the graph
compiles, all 5 nodes execute in order, and the checkpointer doesn't break multi-turn
sessions.

**Why is it needed?**
T-005 is the orchestration foundation that T-008 (LLM provider + A1 agent) builds
directly on top of. Without a compiled, tested graph, T-008 has nothing to plug into.
The `MemorySaver` checkpointer is also the mechanism that gives every passenger
conversation session continuity across multiple webhook calls — without it each message
would be stateless and A1 couldn't track conversation steps.

---

## Local Setup — Run This First

```bash
# 1. Create and activate virtual environment
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS / Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Copy env file (no keys needed for graph smoke tests)
cp .env.example .env

# 4. Run all tests
pytest tests/ -v

# 5. Verify graph compiles in isolation
python -c "
from backend.graph.orchestrator import get_graph
g = get_graph()
print('Graph compiled:', g)
"
```

---

## Technical Approach

**Files Modified:**

| File | What changed |
|---|---|
| `backend/graph/orchestrator.py` | Added `from langgraph.checkpoint.memory import MemorySaver`. Added module-level `_checkpointer: MemorySaver = MemorySaver()` singleton. Changed `graph.compile()` → `graph.compile(checkpointer=_checkpointer)`. Added `logger.info("graph_compiled", ...)` with node list, flow description, and Phase 2 swap path. Added `config = {"configurable": {"thread_id": session_id}}` and passed it into `ainvoke()`. Added Google-style docstring to `ClaimOrchestrator.run()`. |

**Files Created:**

| File | Purpose |
|---|---|
| `tests/test_graph.py` | 3 smoke tests: graph compiles, full 5-node pipeline with mocked providers, session continuity across 2 invocations with same session_id |
| `pytest.ini` | `asyncio_mode = auto` — required for pytest-asyncio 0.24+ to handle async test functions without per-test decorators |

**Already complete in starter kit (zero changes needed):**

| File | What was already there |
|---|---|
| `backend/graph/state.py` | `ClaimState` dataclass — all fields for A1–A5, helper methods, `is_lane1_eligible()` |
| `backend/agents/base_agent.py` | `BaseAgent` ABC — `handle()` abstract method, provider injection pattern |
| `backend/agents/a1_conversation.py` | A1 stub — sets `a1_response` to placeholder, logs step |
| `backend/agents/a2_vision.py` | A2 stub — short-circuits on empty `image_paths` |
| `backend/agents/a3_ocr.py` | A3 stub — short-circuits when no tag image found |
| `backend/agents/a4_decision.py` | A4 stub — generates `claim_id`, sets `routing_lane` via `is_lane1_eligible()` |
| `backend/agents/a5_notification.py` | A5 stub — sets `voucher_code` (Lane 1) or `hitl_queued` (Lane 2) |
| `tests/test_state.py` | 7 `ClaimState` unit tests — all passing before T-005 started |

**Provider / Abstraction Used:**

```
No new AI providers introduced in T-005.
MemorySaver is a LangGraph built-in (langgraph==0.2.55) — no external service.
All 5 agent nodes lazy-import their providers at call time via dependencies.py.
No provider is imported directly in orchestrator.py — only provider factory
functions (provide_llm, provide_vision, provide_ocr, provide_db) are referenced,
and only inside the node closures.
```

**Key Design Decisions:**

```
1. MODULE-LEVEL CHECKPOINTER SINGLETON
   _checkpointer: MemorySaver = MemorySaver() is defined at module level,
   not inside _build_graph() or ClaimOrchestrator.run().
   Reason: a new MemorySaver() per request would lose all checkpoint data
   on the next call. The singleton lives for the process lifetime so
   session state persists across multiple webhook calls from the same passenger.
   One line change in Phase 2: swap MemorySaver for AsyncPostgresSaver.

2. THREAD_ID = SESSION_ID
   LangGraph's checkpointer is keyed by configurable["thread_id"].
   Using session_id as the thread_id means every passenger conversation
   gets its own isolated checkpoint namespace. Two passengers sending
   messages simultaneously never interfere with each other's state.
   Without this config key, LangGraph raises ValueError: "Missing required
   'thread_id'" when a checkpointer is present — caught in smoke test 2.

3. LAZY NODE IMPORTS
   All node closures (a1_node, a2_node, etc.) do:
       from backend.dependencies import provide_llm
   inside the async function body, not at module level.
   This is the Proj A pattern: missing implementations fail loudly at
   call time, not at import time. Safe during early dev when T-006/T-008
   stubs are incomplete. Also makes the providers patchable in tests.

4. MOCKED PROVIDERS IN SMOKE TESTS
   GeminiLLMProvider.__init__ calls genai.GenerativeModel() which requires
   a real API key. Patching backend.dependencies.provide_llm (and others)
   replaces the factory function entirely, so node closures get a MagicMock
   instead. Tests run in CI, on teammates' machines, and without .env.
   The mocks are minimal — just enough to satisfy agent constructors.

5. PYTEST.INI ASYNCIO MODE
   pytest-asyncio 0.24+ defaults to strict mode (requires @pytest.mark.asyncio
   on every async test). asyncio_mode = auto in pytest.ini removes this
   boilerplate while keeping the same runtime behaviour. Added at project
   level so all future async tests (T-020 test suite) benefit automatically.

6. ADDABLEVALUESDICT CONVERSION
   LangGraph's ainvoke() returns AddableValuesDict, not ClaimState.
   The existing conversion block in ClaimOrchestrator.run() handles this:
       if not isinstance(result, ClaimState):
           state = ClaimState(**{k: v for k, v in result.items() ...})
   This pattern was already in the starter — T-005 preserves it unchanged.
```

**Future Swap Path:**

```
MemorySaver → AsyncPostgresSaver (Phase 2)
  Change _checkpointer = MemorySaver()
  To     _checkpointer = AsyncPostgresSaver(conn)
  Add    POSTGRES_CHECKPOINT_URL to .env.example
  Zero agent code changes required.

Stub agents → real implementations (T-008 through T-015)
  Each agent's handle() method gets replaced task by task.
  The graph structure (nodes, edges, entry point) stays identical.
  T-005's orchestrator.py is not touched again until T-009 integration.
```

---

## What Happens When ClaimOrchestrator.run() Is Called

```
POST /webhook (T-004)
        ↓
ClaimOrchestrator.run(session_id, message, image_paths, ...)
        ↓
ClaimState built with session inputs
        ↓
config = {"configurable": {"thread_id": session_id}}   ← T-005 addition
        ↓
get_graph().ainvoke(state, config=config)
        ↓
MemorySaver loads checkpoint for this thread_id (empty on first call)
        ↓
    A1 node  →  sets a1_response (stub until T-008)
    A2 node  →  skips if no image_paths (stub until T-010)
    A3 node  →  skips if no tag image (stub until T-011)
    A4 node  →  generates claim_id, sets routing_lane (stub until T-012)
    A5 node  →  sets voucher_code or hitl_queued (stub until T-015)
        ↓
MemorySaver saves checkpoint for this thread_id
        ↓
AddableValuesDict → ClaimState conversion
        ↓
state.execution_completed = True
        ↓
ClaimState returned to webhook route
```

---

## Dependencies

```
Depends On          →  T-004 (FastAPI base must be merged — imports from
                       backend.dependencies rely on backend.config which
                       requires the full app structure T-004 established)

External Libraries  →  langgraph==0.2.55       (MemorySaver, StateGraph, END)
                       langchain-core==0.3.21   (transitive langgraph dep)
                       pytest-asyncio==0.24.0   (asyncio_mode = auto)
                       All already in requirements.txt — no new deps added.

Environment Vars    →  None new. Graph smoke tests require zero env vars.
                       (GEMINI_API_KEY etc. needed only when real providers
                       replace the stubs in T-008, T-010, T-011.)
```

---

## Testing

**How to Test (Manual):**

```bash
# 1. Verify graph compiles
python -c "
from backend.graph.orchestrator import get_graph
g = get_graph()
print('Graph compiled successfully:', type(g).__name__)
print('T-005 core acceptance criterion: PASSED')
"

# 2. Run full test suite
pytest tests/ -v

# 3. Verify server still starts (graph builds on startup)
uvicorn backend.main:app --reload --port 8000
# Look for: {"event": "graph_compiled", "nodes": ["a1","a2","a3","a4","a5"], ...}
# in the structured log output
```

**Automated Tests:**

```
tests/test_graph.py::test_graph_compiles                  — graph builds, not None
tests/test_graph.py::test_orchestrator_smoke_no_images    — all 5 nodes, mocked providers
tests/test_graph.py::test_orchestrator_session_continuity — 2 calls, same session_id, both pass

tests/test_state.py::test_default_state                   — ClaimState defaults
tests/test_state.py::test_set_error                       — error propagation
tests/test_state.py::test_add_debug                       — debug dict
tests/test_state.py::test_lane1_eligible_low_value        — routing logic
tests/test_state.py::test_lane1_ineligible_high_value     — routing logic
tests/test_state.py::test_lane1_ineligible_luxury         — routing logic
tests/test_state.py::test_lane1_ineligible_high_fraud     — routing logic
```

**Expected pytest output:**
```
10 passed, 0 failed
```

**Test Data:** No fixture files needed — all tests use in-memory `ClaimState` objects and `MagicMock` provider instances.

**Acceptance Criteria:**

```
✅ from backend.graph.orchestrator import get_graph; get_graph() → no errors
✅ "graph_compiled" appears in structured logs when server starts
✅ MemorySaver wired — thread_id = session_id in every ainvoke() call
✅ pytest tests/test_state.py → 7 passed (pre-existing, must not regress)
✅ pytest tests/test_graph.py → 3 passed (new smoke tests)
✅ pytest tests/ → 10 passed total, 0 failures
✅ black backend/ tests/ → 0 errors
✅ isort backend/ tests/ → 0 errors
✅ Type hints on all modified / new functions
✅ Google-style docstrings on ClaimOrchestrator.run() and _build_graph()
✅ No hardcoded provider names in orchestrator.py
✅ No API keys or secrets in any file
```

---

## PR Checklist

```
[x] PR title includes Task ID — [T-005] feat(langgraph): ...
[x] PR description filled out on GitHub
[x] Base branch set to develop (not main)
[x] Reviewer assigned — Anoushka
[x] Squash merged to develop
[x] Feature branch deleted after merge

[x] Type hints on all new/modified functions
[x] Google-style docstrings on _build_graph() and ClaimOrchestrator.run()
[~] .env.example — no changes needed (no new env vars in T-005)
[x] No hardcoded provider names in orchestrator / agents
[x] No hardcoded API keys
[x] pytest tests/ → 10 passed, 0 failures
[x] black backend/ tests/ → clean
[x] isort backend/ tests/ → clean
```

---

## Notes / Blockers

```
Known Issues  →  pytest-asyncio and langgraph internals emit ~200 deprecation
                 warnings about asyncio.iscoroutinefunction and get_event_loop_policy
                 for Python 3.13+ compatibility. These are library-level warnings —
                 nothing in our code triggers them. Safe to ignore for POC.
                 Will resolve when langgraph and pytest-asyncio release compat updates.

Scope Note    →  T-005 does NOT implement agent logic. All 5 agents remain stubs:
                 A1 → T-008 (Devam, feature/llm-provider-a1-agent)
                 A2 → T-010 (Anoushka, feature/agent-a2-vision)
                 A3 → T-011 (Anoushka, feature/agent-a3-ocr)
                 A4 → T-012 (Devam, feature/agent-a4-decision)
                 A5 → T-015 (Devam, feature/agent-a5-notification)
                 Graph structure (nodes, edges, entry point) is FROZEN after T-005.
                 No further changes to orchestrator.py until T-009 integration.

Blockers      →  None — T-005 complete.

Links         →  LangGraph MemorySaver:   https://langchain-ai.github.io/langgraph/reference/checkpoints/#langgraph.checkpoint.memory.MemorySaver
                 LangGraph StateGraph:    https://langchain-ai.github.io/langgraph/reference/graphs/#langgraph.graph.state.StateGraph
                 pytest-asyncio modes:   https://pytest-asyncio.readthedocs.io/en/latest/reference/modes/index.html
```

---

*Branch opened: Day 2, Week 1 — Aditya*
*Merged to develop: Day 3, Week 1*
