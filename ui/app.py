import os, sys
from dotenv import load_dotenv  
load_dotenv()
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import streamlit as st
from langgraph.types import Command
from graph.workflow import build_graph
from graph.state import new_state
from agents.base_agent import estimate_cost
from agents.base_agent import estimate_cost
from memory.database import list_runs, get_run, db_stats
import config

import config



st.set_page_config(page_title="Research Workforce", layout="wide")
st.title("Multi-Agent Research Workforce")

if "graph" not in st.session_state:
    st.session_state.graph = build_graph()
graph = st.session_state.graph


def _finish(result):
    result["estimated_cost"] = estimate_cost(result.get("token_usage", {}))
    st.session_state.final = result
    st.session_state.pending = None


def _run_until_pause(state, cfg):
    st.session_state.last_cfg = cfg
    result = graph.invoke(state, cfg)
    intr = result.get("__interrupt__")
    if intr:
        payload = intr[0].value if isinstance(intr, (list, tuple)) else intr.value
        st.session_state.pending = {"cfg": cfg, "payload": payload}
        st.session_state.final = None
    else:
        _finish(result)

def _retry():
    """Re-invoke the graph on the SAME thread_id. LangGraph resumes from the last
    checkpoint, so a run that failed mid-way retries the failed step rather than
    restarting from scratch."""
    last = st.session_state.get("last_cfg")
    if not last:
        return
    result = graph.invoke(None, last)
    intr = result.get("__interrupt__")
    if intr:
        payload = intr[0].value if isinstance(intr, (list, tuple)) else intr.value
        st.session_state.pending = {"cfg": last, "payload": payload}
        st.session_state.final = None
    else:
        _finish(result)

def _resume(decision, edited_plan=None):
    cfg = st.session_state.pending["cfg"]
    result = graph.invoke(
        Command(resume={"decision": decision, "edited_plan": edited_plan}), cfg)
    _finish(result)


with st.sidebar:
    st.header("New run")
    query = st.text_area("Research question",
                         "What factors are associated with customer churn?")
    up = st.file_uploader("Datasets / documents", accept_multiple_files=True)
    auto = st.toggle("Auto-approve plan (skip HITL)", value=False)
    effort_choice = st.selectbox(
        "Reasoning effort",
        ["Per-agent default", "low", "medium", "high"],
        help="Override every agent's effort for this run. Higher effort = more "
             "reasoning tokens = higher cost.")
    start = st.button("Start", type="primary")

    st.divider()
    st.caption("Run controls")
    if st.button("Retry last run", disabled=not st.session_state.get("last_cfg")):
        with st.spinner("Retrying from last checkpoint..."):
            _retry()
        st.rerun()
    if st.button("Clear session"):
        for k in ("final", "pending", "last_cfg"):
            st.session_state.pop(k, None)
        st.rerun()
    st.caption("Pause is handled by the plan-approval checkpoint: turn off "
               "auto-approve and the graph halts there until you decide.")

    
    

if start:
    os.environ["AUTO_APPROVE"] = "1" if auto else "0"
    files = []
    for f in up or []:
        kind = "csv" if f.name.endswith(".csv") else "pdf" if f.name.endswith(".pdf") else "other"
        os.makedirs("data", exist_ok=True)
        path = os.path.join("data", f.name)
        with open(path, "wb") as out:
            out.write(f.getbuffer())
        files.append({"path": path, "type": kind, "name": f.name})

    override = None if effort_choice == "Per-agent default" else effort_choice
    state = new_state(query, uploaded_files=files, preferences={"effort_override": override})
    cfg = {"configurable": {"thread_id": state["run_id"]}}
    with st.spinner("Running workforce..."):
        _run_until_pause(state, cfg)

pending = st.session_state.get("pending")
if pending:
    import json
    st.warning("Human-in-the-loop: review the research plan before execution.")
    plan = pending["payload"].get("plan", {})
    edited = st.text_area("Plan (edit before approving if needed)",
                          value=json.dumps(plan, indent=2), height=240)
    c1, c2, c3 = st.columns(3)
    if c1.button("Approve", type="primary"):
        _resume("approve"); st.rerun()
    if c2.button("Request changes"):
        try:
            _resume("edit", edited_plan=json.loads(edited))
        except Exception:
            st.error("Edited plan is not valid JSON.")
        else:
            st.rerun()
    if c3.button("Reject"):
        _resume("reject"); st.rerun()

final = st.session_state.get("final")

tabs = st.tabs(["Dashboard", "Execution graph", "Agent trace", "Communication",
                "Memory", "Analysis", "Logs & cost", "Report"])

with tabs[0]:
    if final:
        st.metric("Status", final["status"])
        st.write("**Run ID:**", final["run_id"])
        st.write("**Completed agents:**", ", ".join(final["completed_agents"]))
        st.write("**Route flags:**", final.get("route_flags", {}))
    elif pending:
        st.info("Paused for plan approval — see the banner above.")
    else:
        st.info("Start a run from the sidebar.")

with tabs[1]:
    try:
        st.image(graph.get_graph().draw_mermaid_png(), caption="Compiled LangGraph workflow")
    except Exception:
        st.code(graph.get_graph().draw_mermaid(), language="mermaid")

with tabs[2]:
    if final:
        st.dataframe(final["execution_logs"], use_container_width=True)

with tabs[3]:
    if final:
        for m in final["messages"]:
            st.write(f"`{m['from_agent']}` → `{m['to_agent']}` **[{m['type']}]** {m['content']}")

with tabs[4]:
    st.subheader("Persistent memory (SQLite)")
    stats = db_stats()
    if stats:
        c = st.columns(len(stats))
        for i, (k, v) in enumerate(stats.items()):
            c[i].metric(k, v)

    runs = list_runs()
    if runs:
        st.caption("Past runs")
        st.dataframe(runs, use_container_width=True)
        pick = st.selectbox("Inspect a run", [r["run_id"] for r in runs])
        if pick:
            rec = get_run(pick)
            st.write(f"**Query:** {rec.get('query')}  |  **Status:** {rec.get('status')}"
                     f"  |  **Revisions:** {rec.get('revision_count')}")
            m1, m2 = st.columns(2)
            with m1:
                st.caption("Messages"); st.dataframe(rec.get("messages", []),
                                                     use_container_width=True)
            with m2:
                st.caption("Human decisions"); st.dataframe(rec.get("decisions", []),
                                                            use_container_width=True)
    else:
        st.info("No persisted runs yet — complete a run to populate memory.")

    st.divider()
    st.subheader("Knowledge base (Chroma)")
    try:
        from memory.vector_store import VectorStore
        st.metric("Indexed chunks", VectorStore().count())
    except Exception as e:  # noqa: BLE001
        st.caption(f"Vector store unavailable: {e}")

    st.divider()
    st.subheader("Live state (current run)")
    if final:
        st.json({k: v for k, v in final.items() if k != "final_report"})
    else:
        st.caption("No active run.")

with tabs[5]:
    if final and final.get("analysis_results"):
        st.write(final["dataset_info"]); st.write(final["analysis_results"])
    else:
        st.caption("No dataset analysis in this run.")

with tabs[6]:
    if final:
        st.subheader("Reasoning effort (this run)")
        ov = (final.get("preferences") or {}).get("effort_override")
        st.dataframe([{"agent": a, "effort": ov if ov else config.effort_for(a),
                       "source": "override" if ov else "config default"}
                      for a in config.ALL_AGENTS], use_container_width=True)
        st.subheader("Token usage")
        st.json(final.get("token_usage", {}))
        st.metric("Estimated cost (USD)", f"${final.get('estimated_cost', 0):.4f}")
        st.caption("Estimated from the price table. Thinking tokens (driven by "
                   "effort) bill as output tokens.")
        st.subheader("Errors"); st.write(final.get("errors") or "None")

with tabs[7]:
    if final and final.get("final_report"):
        st.markdown(final["final_report"])