# Multi-Agent Research Workforce — Locked Architecture & Workflow Plan

**Status:** Locked · **Stack:** LangGraph + Claude + Streamlit + Chroma + SQLite
**Purpose:** Single source of truth. If code and this document disagree, this document wins until it is deliberately revised.

---

## 0. Locked decisions (no re-litigating these mid-build)

| Decision | Locked value | Rationale |
|---|---|---|
| Orchestration | LangGraph | Rubric-preferred; native state, interrupts, graph viz |
| Reasoning model | Claude (`claude-sonnet-4-6` for agents) | One provider, no failover (out of scope) |
| UI | Streamlit | Rubric-preferred |
| Embeddings | **Chroma default (all-MiniLM-L6-v2, local ONNX)** | No 2nd API key, no per-token cost, offline in demo |
| Web search | Tavily | Simple, reliable |
| Academic | OpenAlex (Crossref fallback) | Free, no key for OpenAlex |
| Vector store | Chroma (persistent, local dir) | Rubric RAG requirement |
| Persistence | SQLite + LangGraph checkpointer | Sessions/logs + resumable state |
| HITL checkpoints | **One: Plan Approval** | Satisfies pause/resume/approve; minimizes Streamlit⇄interrupt surface |
| Critic loop | **Max 2 revisions, then force-pass w/ logged WARNING** | Prevents infinite token burn |
| MCP | **Out of scope** | Not in any spec; diagram (Fig.1) to be updated to remove MCP node |
| Agent count | 7 nodes = Supervisor + 6 specialists | Meets "≥6 specialized agents" |

**Action item before anything else:** update Figure 1 so the diagram shows Web / Academic / RAG / Python tools — not "MCP Server" — so the presentation and code agree.

---

## 1. The graph (supervisor-hub topology)

The Supervisor is the central router. Every specialist returns control to the Supervisor, which decides the next hop. This makes the comms log naturally read `Supervisor → Agent → Supervisor`, and keeps routing logic in exactly one place.

```
                 ┌─────────────┐
   user input ──▶│  SUPERVISOR │◀────────────────┐
                 └──────┬──────┘                 │
                        ▼                         │
                 ┌─────────────┐                  │
                 │   PLANNER   │                  │
                 └──────┬──────┘                  │
                        ▼                          │
            ┌───────────────────────┐             │
            │  ⏸ HITL: PLAN APPROVAL │  (interrupt)│
            └───────────┬───────────┘             │
                        ▼                          │
                 ┌─────────────┐                  │
                 │  SUPERVISOR │ ── routes to ─────┤
                 └─────────────┘   needed agents   │
                        │                          │
        ┌───────────────┼───────────────┬─────────┤
        ▼               ▼               ▼         │
   ┌─────────┐   ┌──────────────┐  ┌──────────┐   │
   │RESEARCH │   │ KNOWLEDGE/RAG│  │DATA      │   │
   │(web+acad)│  │ (Chroma)     │  │ANALYST   │   │
   └────┬────┘   └──────┬───────┘  └────┬─────┘   │
        └───────────────┴───────────────┘         │
                        ▼                          │
                 ┌─────────────┐                  │
                 │   CRITIC    │──REVISE──────────┘
                 └──────┬──────┘  (≤2×)
                        │ PASS
                        ▼
                 ┌─────────────┐
                 │   WRITER    │──▶ final_report ──▶ END
                 └─────────────┘
```

Routing is **dynamic**: the Supervisor invokes only the specialists flagged as needed for the request. A dataset-only task never touches Research or RAG; a research-only task never touches the Data Analyst.

---

## 2. Shared state — the backbone (LOCKED SCHEMA)

Every agent reads and writes **only** this object. Append-only lists use `operator.add` reducers so parallel/sequential writes accumulate instead of overwriting.

```python
# graph/state.py
import operator
from typing import TypedDict, Annotated, Optional

class ResearchState(TypedDict):
    # ---- Input ----
    run_id: str
    user_query: str
    preferences: dict                    # {tone, depth, max_sources, ...}
    uploaded_files: list[dict]           # [{path, type: 'pdf'|'csv', name}]

    # ---- Planning ----
    research_plan: Optional[dict]        # {objectives[], subtasks[], evidence_needs[], success_criteria[]}

    # ---- Routing / control ----
    route_flags: dict                    # {need_web, need_academic, need_rag, need_data} -> bool
    completed_agents: Annotated[list[str], operator.add]
    current_agent: str
    status: str                          # see STATUS enum below

    # ---- Agent outputs ----
    research_results:  Annotated[list[dict], operator.add]  # [{claim, source_url, title, snippet}]
    literature_results:Annotated[list[dict], operator.add]  # [{title, authors, year, doi, abstract}]
    retrieved_context: Annotated[list[dict], operator.add]  # [{text, source_id, page, doc_name}]
    dataset_info: Optional[dict]         # {shape, columns, dtypes, missing, duplicates}
    analysis_results: Optional[dict]     # {stats, findings[], chart_paths[], code}

    # ---- Critic ----
    critic_feedback: Annotated[list[dict], operator.add]  # see FEEDBACK format
    revision_count: int

    # ---- HITL ----
    human_decisions: Annotated[list[dict], operator.add]  # [{checkpoint, decision, edited_payload, ts}]

    # ---- Output ----
    final_report: Optional[str]          # markdown

    # ---- Observability (read by UI panels) ----
    messages: Annotated[list[dict], operator.add]        # COMMS log (see format)
    execution_logs: Annotated[list[dict], operator.add]  # structured logs
    errors: Annotated[list[dict], operator.add]
    token_usage: dict                    # {agent_name: {input, output}, "total": {...}}
    estimated_cost: float
```

### STATUS enum (locked)
`INITIALIZING → PLANNING → AWAITING_PLAN_APPROVAL → RESEARCHING → ANALYZING → CRITIQUING → REVISING → WRITING → COMPLETE` (and `ERROR` from any state).

### COMMS message format (the Communication panel reads this verbatim)
```python
{
  "ts": "2026-08-13T10:22:04Z",
  "from_agent": "supervisor",
  "to_agent": "research",
  "type": "delegation",        # delegation | result | feedback | system
  "content": "Retrieve 5 recent sources on churn drivers",
  "run_id": "..."
}
```

### FEEDBACK format (Critic → Supervisor)
```python
{
  "severity": "ERROR",         # INFO | WARNING | ERROR
  "target_agent": "data_analyst",
  "issue": "Correlation reported as causation in finding #3",
  "suggestion": "Reframe as association; note confounders"
}
```

### TOKEN capture (one line per Claude call — never retrofit this)
```python
def record_usage(state, agent, resp):
    u = resp.usage
    state["token_usage"].setdefault(agent, {"input":0,"output":0})
    state["token_usage"][agent]["input"]  += u.input_tokens
    state["token_usage"][agent]["output"] += u.output_tokens
```
Cost is derived at display time from a config price table and **labeled "estimate."**

---

## 3. Agent contracts (reads → writes → tools → emits)

Every specialist is built from **one shared `base_agent` helper** (call Claude, parse structured JSON, record usage, append a comms message, catch/log errors). Only the Data Analyst extends it with Python execution. Distinct prompt + tools + graph node per agent = six real participants in the trace.

| Agent | Reads | Writes | Tools | Emits (comms) |
|---|---|---|---|---|
| **Supervisor** | full state | `route_flags`, `current_agent`, `status`, `completed_agents` | — (pure routing) | `delegation` to each agent |
| **Planner** | `user_query`, `preferences`, `uploaded_files` | `research_plan` | Claude | `result` → supervisor |
| **Research** | `research_plan` | `research_results`, `literature_results` | Tavily, OpenAlex | `result` → supervisor |
| **Knowledge/RAG** | `research_plan`, `uploaded_files` | `retrieved_context` | Chroma (+ PDF loader) | `result` → supervisor |
| **Data Analyst** | `uploaded_files`, `research_plan` | `dataset_info`, `analysis_results` | Pandas/NumPy, Python executor, Matplotlib | `result` → supervisor |
| **Critic** | all agent outputs + `research_plan` | `critic_feedback`, `revision_count` | Claude | `feedback` → supervisor |
| **Writer** | all validated outputs | `final_report` | Claude | `result` → supervisor |

### Supervisor routing logic (the one place routing lives)
```
after PLANNING (approved):
    set route_flags from plan + uploaded_files:
        need_web/need_academic  = plan requires external evidence
        need_rag                = any uploaded_files.type == 'pdf'
        need_data               = any uploaded_files.type == 'csv'
    dispatch, in order, each flagged & not-yet-completed specialist
    when all flagged specialists in completed_agents -> route to CRITIC

after CRITIC:
    if any feedback.severity == ERROR and revision_count < 2:
        revision_count += 1 ; route back to each target_agent ; status=REVISING
    else:
        route to WRITER   # force-pass logs a WARNING if errors remain
```

---

## 4. Memory & RAG (locked pipeline)

- **Short-term:** `ResearchState` via LangGraph checkpointer (`SqliteSaver`) — enables pause/resume.
- **Persistent knowledge:** Chroma (document chunks + embeddings + metadata) at `./artifacts/chroma`.
- **Persistent records:** SQLite tables — `sessions`, `runs`, `agent_logs`, `human_decisions`, `artifacts`.
- **RAG steps:** PDF → extract text+metadata → chunk (≈1000 chars, 150 overlap) → embed (Chroma default) → store with `source_id` → retrieve top-k with provenance → append to `retrieved_context` → log retrieval event.
- **Provenance rule:** every retrieved passage carries `source_id` + `doc_name` + `page`, surfaced in the final report's citations.

---

## 5. Human-in-the-loop (one checkpoint, done well)

Single interrupt after the Planner:
```python
# in supervisor, before dispatch
decision = interrupt({"checkpoint": "plan_approval", "plan": state["research_plan"]})
# Streamlit resumes with Command(resume={"decision": "approve"|"edit"|"reject", "edited_plan": ...})
```
Streamlit controls: **Approve · Request Changes (edit plan) · Reject (restart) · Pause · Resume**. Approve/edit/reject all write to `human_decisions`. This one checkpoint satisfies the rubric's pause/resume/approve/retry requirement in full.

---

## 6. Streamlit panels → state field mapping (so the UI is just a view)

| Panel (required) | Data source |
|---|---|
| Dashboard (agent status, controls) | `current_agent`, `status`, `completed_agents` |
| Execution graph | `graph.get_graph().draw_mermaid_png()` |
| Live agent trace | `execution_logs` |
| Communication history | `messages` (filtered) |
| Memory viewer | `st.json(state)` + Chroma/SQLite record views |
| Analysis | `dataset_info`, `analysis_results.chart_paths` |
| Logs & cost | `execution_logs`, `errors`, `token_usage`, `estimated_cost` |
| Final report | `final_report` (markdown) |

Every required UI element maps to a field that already exists in the schema — no panel needs data the graph doesn't already produce.

---

## 7. Repository structure (locked)

```
multi-agent-research-workforce/
├── agents/        # base_agent.py + supervisor, planner, researcher,
│                  #   knowledge, data_analyst, critic, writer
├── graph/         # state.py, workflow.py (nodes, edges, routing)
├── tools/         # web_search.py, academic_search.py, rag.py, python_executor.py
├── memory/        # vector_store.py (Chroma), database.py (SQLite)
├── ui/            # app.py (Streamlit)
├── config.py      # models, price table, k, chunk sizes, MAX_REVISIONS=2
├── tests/  data/  artifacts/
├── .env.example  requirements.txt  main.py  README.md  ARCHITECTURE.md
```

---

## 8. The 9-day plan (walking-skeleton first)

The order is deliberately inverted from the original: **integration is finished on day 1**, then each node gets smarter without ever breaking a runnable, demoable system.

| Day | Deliverable | Why here |
|---|---|---|
| 0 (½) | Repo, env, `config.py`, Claude smoke test | ✅ mostly done — you have repo + API + base supervisor |
| 1 | `state.py` complete + **full graph, all 7 nodes stubbed** (log, append comms msg, pass state), hardcoded routing, dummy report reaches END | Integration done day 1 |
| 2 | Streamlit shell wired to the skeleton: input → run → status, trace, graph PNG, dummy report | Demoable from here on |
| 3 | Real Supervisor (dynamic routing) + Planner + `base_agent` helper + **HITL plan-approval interrupt** | Do the interrupt while graph is simple |
| 4 | Research Agent: Tavily + OpenAlex, structured evidence w/ source metadata | Mostly API glue on base_agent |
| 5 | Knowledge/RAG: PDF → chunk → Chroma → retrieve w/ provenance | Riskiest external piece gets a full day |
| 6 | Data Analyst: CSV → Pandas EDA → Python executor (subprocess, timeout, capture, charts by `run_id`) | The one custom agent |
| 7 | Critic (with revision guard) + Writer; close the loop | Both reuse base_agent |
| 8 | Cost panel, logs/errors/retries, SQLite persistence, memory + comms panels, UI cleanup | Comms panel = filtered event log (near free) |
| 9 | README, screenshots, **reconcile Fig.1 diagram**, rehearse churn demo, record backup video | Buffer + safety net |

### Release valve (cut in this order if a day slips — each keeps the system runnable)
1. Drop OpenAlex, keep Tavily only.
2. Memory viewer → raw `st.json(state)` (still compliant).
3. Skip SQLite, rely on LangGraph checkpointer alone (lose cross-session persistence; live demo unaffected).

**Never cut:** token+cost panels, execution graph, memory viewer, HITL, the six distinct agents — all are graded.

---

## 9. Demo scenario (locked)

> "Investigate the factors associated with customer churn using the uploaded dataset. Find relevant research, analyze the dataset, identify important factors, critique the analysis, and produce a research report."

Exercises every capability: mixed routing (Research + RAG + Data Analyst), critic revision, HITL plan approval, all UI panels. Prepare the dataset + a backup recording by day 9.

---

## 10. Definition of Done (rubric-mapped)

- [ ] Supervisor dynamically routes tasks
- [ ] 6 specialists, distinct node + prompt + tools + comms identity
- [ ] Agent-to-agent comms via shared state (`messages`)
- [ ] Web + academic search, RAG, Python execution all work
- [ ] Shared memory (state + Chroma + SQLite)
- [ ] HITL pause/resume/approve/reject
- [ ] UI: dashboard, trace, comms, graph, token+cost, logs/errors, memory viewer, report viewer
- [ ] Critic can reject and trigger bounded revision
- [ ] Logging + error handling with retries
- [ ] README reproduces the project
