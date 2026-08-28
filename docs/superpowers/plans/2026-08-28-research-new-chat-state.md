# Research New-Chat + Explicit-State Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Execute every ChatGPT research turn in a fresh conversation, carry explicit bounded research state between turns, strengthen discovery guidance, and retry one failed ChatGPT turn once without changing legacy JSON contracts.

**Architecture:** Keep all legacy runners untouched. Add prompt enrichment/state ownership to `RemoteChatGPTBrowserSession`, pass workflow kind from `workflows.py` through `browser_selector.py`, and add fresh-chat + retry helpers to the Windows worker. Existing broker request/reply semantics remain unchanged.

**Tech Stack:** Python 3, FastAPI backend, Playwright async API, httpx, unittest.

**Spec:** `docs/superpowers/specs/2026-08-28-research-new-chat-state-design.md`

## Global Constraints

- Preserve existing legacy research runners and JSON output contracts.
- Preserve existing price verifier behavior.
- No OpenAI API replacement.
- CDP remains local-only at `127.0.0.1:9222`.
- Retry a failed ChatGPT ask at most once.
- Research state must be bounded before being appended to subsequent prompts.

---

### Task 1: Remote prompt enrichment and explicit state

**Files:**
- Modify: `backend/app/remote_browser.py`
- Modify: `backend/app/browser_selector.py`
- Modify: `backend/app/workflows.py`
- Create: `backend/tests/test_remote_research_state.py`

**Interfaces:**
- Consumes: existing `RemoteChatGPTBrowserSession.ask(*args, **kwargs)` and `BROKER.submit(...)`.
- Produces: `RemoteChatGPTBrowserSession(progress=None, research_kind=None)` with per-session bounded prior-response state; `chatgpt_session(progress=None, research_kind=None)`.

- [ ] **Step 1: Write failing tests**

Test that a prices session adds pass-specific guidance to the first prompt, includes the previous result in `STECH_RESEARCH_STATE` on the second prompt, preserves non-string arguments, and bounds stored state.

- [ ] **Step 2: Run focused tests and confirm RED**

Run: `python -m unittest backend.tests.test_remote_research_state -v`
Expected: failures because `research_kind` and state enrichment do not exist.

- [ ] **Step 3: Implement minimal prompt enrichment/state**

Add compact guidance constants for `prices`, `characteristics`, `images`, and `videos`. For prices, vary guidance by call index: identity/recall, seller/alias expansion, long-tail recovery. Append prior successful responses as a bounded JSON/text state block and explicitly preserve the original output schema.

- [ ] **Step 4: Pass workflow kind into the session selector**

Update calls in `workflows.py` to use `chatgpt_session(progress=progress, research_kind='<kind>')`; update `browser_selector.py` to forward the optional kind in remote mode and ignore it in server mode.

- [ ] **Step 5: Run focused + existing broker/API tests**

Run:
`python -m unittest backend.tests.test_remote_research_state backend.tests.test_research_broker backend.tests.test_remote_worker_api -v`
Expected: PASS.

- [ ] **Step 6: Commit**

Commit message: `feat: carry explicit research state across ChatGPT turns`

---

### Task 2: Fresh chat before every worker ask

**Files:**
- Modify: `tools/research_worker_windows.py`
- Create: `backend/tests/test_worker_fresh_chat.py`
- Existing test: `backend/tests/test_worker_page_recovery.py`

**Interfaces:**
- Consumes: existing `recover_chatgpt_page(session)`.
- Produces: `open_fresh_chat(session)` and `ask_with_fresh_chat_retry(session, args, kwargs, max_attempts=2)`.

- [ ] **Step 1: Write failing tests**

Test that `open_fresh_chat` navigates the live page to `https://chatgpt.com/`; test that a first ask failure causes exactly one second attempt after a second fresh-chat navigation; test that two failures propagate the second error.

- [ ] **Step 2: Run focused tests and confirm RED**

Run: `python -m unittest backend.tests.test_worker_fresh_chat -v`
Expected: failure because helpers do not exist.

- [ ] **Step 3: Implement fresh-chat helper**

Use `recover_chatgpt_page(session)`, navigate to root with `wait_until='domcontentloaded'`, assign `session.page`, and emit a concise progress note.

- [ ] **Step 4: Implement one retry**

Wrap only `session.ask(...)`. On first exception emit a retry note, reopen a fresh chat, and call the same ask again. Do not retry posting the completed result to Render.

- [ ] **Step 5: Replace direct worker ask**

Change the worker loop from `recover_chatgpt_page + session.ask` to `ask_with_fresh_chat_retry`.

- [ ] **Step 6: Run worker tests**

Run:
`python -m unittest backend.tests.test_worker_fresh_chat backend.tests.test_worker_page_recovery -v`
Expected: PASS.

- [ ] **Step 7: Commit**

Commit message: `feat: isolate worker research in fresh ChatGPT chats`

---

### Task 3: Final regression verification

**Files:**
- No new production files expected.

**Interfaces:**
- Verifies Tasks 1-2 together.

- [ ] **Step 1: Compile changed Python modules**

Run: `python -m py_compile backend/app/remote_browser.py backend/app/browser_selector.py backend/app/workflows.py tools/research_worker_windows.py`
Expected: exit 0.

- [ ] **Step 2: Run focused regression suite**

Run:
`python -m unittest backend.tests.test_remote_research_state backend.tests.test_research_broker backend.tests.test_remote_worker_api backend.tests.test_worker_page_recovery backend.tests.test_worker_fresh_chat -v`
Expected: all PASS.

- [ ] **Step 3: Production smoke procedure**

On PC020: pull latest main, restart worker, run one prices job. Expected log for each pass: worker receives job → fresh ChatGPT chat note → prompt sent → JSON detected → completed. A failed first ChatGPT attempt should show one retry in a fresh chat. Render should complete all three price passes and then run the existing web verifier.
