# BRANCH: feature/llm-provider-a1-agent

---

## Branch Metadata

```
Branch Name   →  feature/llm-provider-a1-agent
Task ID       →  T-008
Workstream    →  LLM / Conversation
Author        →  Devam
Reviewer      →  Anoushka
Start Date    →  Day 3, Week 1
Target Merge  →  Day 5, Week 1
Actual Merge  →  Day 5, Week 1
Status        →  Merged
```

---

## Objective

**What does this branch do?**
Implements the LLM layer and the passenger-facing conversation agent (A1).
GeminiLLMProvider.chat() replaces the stub with a real Gemini API call.
A1ConversationAgent.handle() replaces the stub with a full conversation
state machine that guides passengers through the 5-step claim flow,
generates empathetic responses, and hands off to the rest of the pipeline.

**Why is it needed?**
Without T-008, the system replied "[A1 stub] Hello!" for every message.
T-008 is what makes the bot actually talk — it is the voice of the entire
system. T-009 (Week 1 integration) cannot be completed until this is merged,
as the integration test verifies A1 generates real LLM replies end-to-end.

---

## Local Setup

```bash
# Activate venv (every new terminal)
source venv/Scripts/activate      # Git Bash on Windows
# OR
source venv/bin/activate          # Mac / Linux

# Install dependencies
pip install -r requirements.txt

# Start server
uvicorn backend.main:app --reload --port 8000
```

---

## Technical Approach

**Files Modified:**
```
backend/llm_provider/gemini_llm.py    →  Replaced chat() stub with real implementation:
                                          - _build_gemini_contents() converts OpenAI-style
                                            messages to Gemini format (role mapping,
                                            system prompt prepend)
                                          - GenerationConfig with temperature + max_tokens
                                          - Safety block detection and AppError raise
                                          - Structured logging on every call

backend/agents/a1_conversation.py     →  Replaced handle() stub with full state machine:
                                          - _get_step_prompt() — picks correct prompt
                                            from a1_conversation.json based on state
                                          - _build_messages() — assembles system + history
                                            + passenger message + step instruction
                                          - _advance_step() — moves conversation forward
                                          - handle() — orchestrates the full A1 flow

tests/test_graph.py                   →  Fixed mock_llm to use AsyncMock for chat()
                                          (required now that A1 awaits chat() for real)
```

**Files Created:**
```
tests/test_a1_agent.py               →  10 unit tests covering:
                                          - GeminiLLMProvider message format conversion
                                          - A1 step progression and state machine
                                          - Error handling
                                          - Conversation history inclusion
                                          - Lane 1/2 result rendering
```

**Files Already Complete (No Changes Needed):**
```
backend/llm_provider/base.py          →  LLMProvider ABC — complete
backend/prompts/a1_conversation.json  →  All 8 prompt steps — complete
backend/core/prompt_loader.py         →  PromptLoader.load() + render() — complete
backend/dependencies.py               →  provide_llm() already wired — complete
```

**Provider / Abstraction Used:**
```
Implements:  LLMProvider ABC (backend/llm_provider/base.py)
Via:         Gemini 2.5 Flash text API (free tier — 1M tokens/day)
Injected by: provide_llm() in dependencies.py
A1 imports:  LLMProvider only — never GeminiLLMProvider directly
```

**Key Design Decisions:**

```
1. CONVERSATION STATE MACHINE (not intent detection)
   A1 is NOT an intent classifier. It doesn't ask "what does the passenger want?"
   It asks "what step are we on, and what should I say next?"
   The flow is predefined: greeting → damage_photos → tag_photo → confirm → result
   The LLM's job is only to phrase the right message empathetically.
   This is simpler, more reliable, and easier to test than intent detection.

2. GEMINI ROLE MAPPING
   Gemini uses "model" instead of "assistant" — _build_gemini_contents() handles this.
   Gemini has no native "system" role — system prompt is prepended to the first
   user message automatically. All downstream code uses OpenAI-style format;
   the conversion is fully contained inside GeminiLLMProvider.

3. STEP PRIORITY ORDER IN _get_step_prompt()
   Priority: re_request_tag > re_request_damage > result_lane1/2 > normal step
   Retry requests take highest priority because a passenger who just sent a blurry
   photo should always get the retry message, regardless of what step they're on.

4. NEVER CRASH — ALWAYS CATCH
   A1.handle() wraps all logic in try/except. If anything fails (API timeout,
   JSON parse error, network issue), state.error is set and execution continues.
   The pipeline never hard-crashes on A1 failure — this is the BaseAgent contract.

5. TEMPERATURE 0.3 FOR A1
   A1 uses temperature=0.3 (slightly higher than default 0.2) to allow
   some natural variation in phrasing while staying factual and consistent.
   Higher temperature = more human-sounding, lower = more robotic.

6. CONVERSATION HISTORY WINDOW
   Only the last 6 turns of history are included in each LLM call.
   This keeps token usage low while giving A1 enough context to
   understand the conversation flow.

7. test_graph.py FIX
   Aditya's original mock_llm used MagicMock() which is not awaitable.
   Now that A1 actually calls await self._llm.chat(), the test needed
   mock_llm.chat = AsyncMock(...). This is a correct fix — it proves
   the real A1 code path is being exercised in graph tests.
```

**Future Swap Path:**
```
To swap Gemini for Claude in Phase 2:
1. Create backend/llm_provider/claude_llm.py
2. Implement LLMProvider ABC (chat() method only)
3. Add to dependencies.py: if s.llm_provider == "claude": return ClaudeLLMProvider(...)
4. Set LLM_PROVIDER=claude in .env
5. Zero changes needed in A1 agent, orchestrator, or any other file

Same pattern works for Ollama (local), OpenAI, or any other LLM.
```

---

## Conversation Flow (What A1 Does Step by Step)

```
Passenger: "hi my bag is damaged"
        ↓
ClaimState.conversation_step = "greeting"
        ↓
_get_step_prompt() → picks "greeting" prompt from a1_conversation.json
  "Greet the passenger and ask them to describe the damage. Keep it to 2 sentences."
        ↓
_build_messages() → assembles:
  [system: "You are a helpful empathetic airline assistant..."]
  [user: "hi my bag is damaged"]
  [user: "[INSTRUCTION]: Greet the passenger and ask them to describe the damage."]
        ↓
LLM.chat() → Gemini generates:
  "Hi there, I'm so sorry to hear about your damaged bag.
   Could you please describe what kind of damage it sustained?"
        ↓
state.a1_response = "Hi there, I'm so sorry..."
state.conversation_step = "damage_photos"  ← advanced
        ↓
Next message → A1 picks up at "damage_photos" step
```

---

## Dependencies

```
Depends On          →  T-005 (LangGraph skeleton — orchestrator must exist)
External Libraries  →  google-generativeai (already in requirements.txt)
Environment Vars    →  GEMINI_API_KEY
                       GEMINI_MODEL=gemini-2.5-flash
                       LLM_PROVIDER=gemini
                       LLM_DEFAULT_TEMPERATURE=0.2
                       LLM_MAX_OUTPUT_TOKENS=1024
```

---

## Testing

**Automated Tests (No Real API Calls):**
```bash
pytest tests/test_a1_agent.py -v

# Expected:
# test_build_gemini_contents_converts_roles    PASSED
# test_build_gemini_contents_no_system         PASSED
# test_a1_greeting_sets_response               PASSED
# test_a1_advances_step                        PASSED
# test_a1_does_not_advance_past_result         PASSED
# test_a1_re_request_tag_does_not_advance      PASSED
# test_a1_jumps_to_result_when_lane_set        PASSED
# test_a1_sets_error_on_llm_failure            PASSED
# test_a1_includes_conversation_history        PASSED
# test_a1_lane1_result_includes_voucher        PASSED
# 10 passed

# Full suite:
pytest tests/ -v
# Expected: 28 passed (10 new + 18 existing)
```

**Manual Smoke Tests (Real Gemini API):**
```bash
# Test 1 — LLM provider directly
python -c "
import asyncio
from backend.dependencies import provide_llm
async def test():
    llm = provide_llm()
    messages = [
        {'role': 'system', 'content': 'You are a helpful airline assistant.'},
        {'role': 'user', 'content': 'Hi, my bag was damaged on my flight.'}
    ]
    reply = await llm.chat(messages)
    print('Reply:', reply)
asyncio.run(test())
"
# Expected: real empathetic Gemini response

# Test 2 — Full A1 agent
python -c "
import asyncio
from backend.agents.a1_conversation import A1ConversationAgent
from backend.dependencies import provide_llm
from backend.graph.state import ClaimState
async def test():
    agent = A1ConversationAgent(llm=provide_llm())
    state = ClaimState(session_id='s1', passenger_message='hi my bag is damaged', conversation_step='greeting')
    result = await agent.handle(state, [])
    print('A1 Response:', result.a1_response)
    print('Next step:', result.conversation_step)
asyncio.run(test())
"
# Expected:
# A1 Response: Hi there, I'm so sorry to hear about your damaged bag...
# Next step: damage_photos

# Test 3 — Full webhook end-to-end
# Start server: uvicorn backend.main:app --reload --port 8000
curl -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -d "{\"session_id\": \"s1\", \"message\": \"hi my bag is damaged\"}"
# Expected: real A1 reply in JSON response (not stub text)
```

**Acceptance Criteria:**
```
✅ GeminiLLMProvider.chat() calls real Gemini API with correct message format
✅ "assistant" role correctly converted to "model" for Gemini API
✅ System prompt prepended to first user message
✅ Safety blocks handled gracefully — AppError raised, not crash
✅ A1 detects conversation step and picks correct prompt
✅ A1 advances: greeting → damage_photos → tag_photo → confirm → result
✅ A1 stays on same step when re_request_tag or re_request_damage is True
✅ A1 jumps to result when routing_lane is set by A4
✅ A1 catches all exceptions — sets state.error, never hard crashes
✅ No hardcoded provider names in agents/ — only LLMProvider ABC used
✅ Type hints on all functions
✅ Google-style docstrings on all public functions
✅ black + isort run clean
✅ 10 unit tests pass — all LLM calls mocked
✅ pytest tests/ → 28 passed, 0 failures
```

---

## PR Checklist

```
[x] PR title includes Task ID — [T-008] feat(llm): ...
[x] PR description filled out on GitHub
[x] Base branch set to develop (not main)
[x] Reviewer assigned — Anoushka
[x] Type hints on all new/modified functions
[x] Google-style docstrings on all public functions
[x] No hardcoded provider names in agents/
[x] No hardcoded API keys — all via os.getenv / Settings
[x] black backend/ → clean
[x] isort backend/ → clean
[x] pytest tests/ → 28 passed, 0 failures
[x] test_graph.py fixed — mock_llm.chat uses AsyncMock
[x] Squash merged to develop
[x] Feature branch deleted after merge
```

---

## Notes / Blockers

```
Known Issues  →  pytest shows deprecation warnings from pytest-asyncio and
                 langgraph internals. Library-level, not our code. Safe to ignore.

Fix Applied   →  tests/test_graph.py updated: mock_llm.chat = AsyncMock(...)
                 Aditya's original MagicMock() was not awaitable. Now that A1
                 actually calls await self._llm.chat(), AsyncMock is required.
                 This is correct — it proves the real A1 code path is exercised.

Next Task     →  T-009 (Week 1 Integration) — depends on T-008 ✅ + T-007 ✅

Blockers      →  None — T-008 complete

Links         →  Gemini API docs:     https://ai.google.dev/gemini-api/docs
                 Gemini pricing:      https://ai.google.dev/pricing
                 LLMProvider ABC:     backend/llm_provider/base.py
                 Prompt templates:    backend/prompts/a1_conversation.json
                 Future Claude swap:  implement backend/llm_provider/claude_llm.py
```
