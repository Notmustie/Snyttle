"""Home page: user input, HITL approval, final report + PDF download.

Everything else (execution graph, trace, comms, memory, logs/cost, charts) lives
on the Dashboard page. Session state (graph/final/pending) is shared across
Streamlit's multipage app automatically, so the running checkpointer survives
navigating between pages.
Run:  streamlit run ui/app.py
"""
import os, sys, json
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import streamlit as st
from langgraph.types import Command
from graph.workflow import build_graph
from graph.state import new_state
from agents.base_agent import estimate_cost
from tools.report_export import export_report_pdf
import config

st.set_page_config(page_title="Research Workforce", page_icon="📋", layout="centered")

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


def _resume(decision, edited_plan=None):
    cfg = st.session_state.pending["cfg"]
    result = graph.invoke(
        Command(resume={"decision": decision, "edited_plan": edited_plan}), cfg)
    intr = result.get("__interrupt__")
    if intr:  # a revision loop could in principle re-pause; handle it, don't crash
        payload = intr[0].value if isinstance(intr, (list, tuple)) else intr.value
        st.session_state.pending = {"cfg": cfg, "payload": payload}
        st.session_state.final = None
    else:
        _finish(result)


def _retry():
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


st.title("📋 Multi-Agent Research Workforce")
st.caption("Ask a research question, optionally attach data or documents, and "
           "get a cited report — built by a Supervisor coordinating six "
           "specialist agents.")

# ---------------------------------------------------------------- Input form
with st.form("run_form", clear_on_submit=False):
    query = st.text_area("Research question", height=90,
                         placeholder="What factors are associated with customer churn?")
    up = st.file_uploader("Datasets / documents (optional)",
                          accept_multiple_files=True,
                          type=["csv", "xlsx", "xls", "json", "parquet", "pdf", "txt", "md"])
    auto = st.toggle("Auto-approve the research plan (skip human review)", value=False)

    with st.expander("Advanced settings"):
        c1, c2 = st.columns(2)
        effort_choice = c1.selectbox("Reasoning effort",
            ["Per-agent default", "low", "medium", "high"])
        model_choice = c2.selectbox("Model",
            ["Per-agent default", "claude-sonnet-4-6", "claude-opus-4-8"])

    submitted = st.form_submit_button("Run", type="primary", use_container_width=True)

if submitted:
    if not query.strip():
        st.error("Enter a research question first.")
    else:
        files = []
        for f in up or []:
            ext = os.path.splitext(f.name)[1].lstrip(".").lower()
            kind = ext if ext in {"csv", "xlsx", "xls", "json", "parquet", "pdf", "txt", "md"} else "other"
            os.makedirs("data", exist_ok=True)
            path = os.path.join("data", f.name)
            with open(path, "wb") as out:
                out.write(f.getbuffer())
            files.append({"path": path, "type": kind, "name": f.name})

        prefs = {
            "auto_approve": auto,
            "effort_override": None if effort_choice == "Per-agent default" else effort_choice,
            "model_override": None if model_choice == "Per-agent default" else model_choice,
        }
        state = new_state(query, uploaded_files=files, preferences=prefs)
        cfg = {"configurable": {"thread_id": state["run_id"]}}
        with st.spinner("Running the workforce..."):
            _run_until_pause(state, cfg)
        st.rerun()

# ---------------------------------------------------------------- HITL approval
pending = st.session_state.get("pending")
if pending:
    st.divider()
    st.warning("⏸ **Human review required** — approve, edit, or reject the "
               "research plan before the workforce continues.")
    plan = pending["payload"].get("plan", {})
    edited = st.text_area("Research plan (JSON — edit before approving if needed)",
                          value=json.dumps(plan, indent=2), height=220)
    c1, c2, c3 = st.columns(3)
    if c1.button("✅ Approve", type="primary", use_container_width=True):
        with st.spinner("Resuming..."):
            _resume("approve")
        st.rerun()
    if c2.button("✏️ Approve edited plan", use_container_width=True):
        try:
            parsed = json.loads(edited)
        except Exception:
            st.error("The edited plan is not valid JSON.")
        else:
            with st.spinner("Resuming with your edits..."):
                _resume("edit", edited_plan=parsed)
            st.rerun()
    if c3.button("❌ Reject", use_container_width=True):
        with st.spinner("Stopping the run..."):
            _resume("reject")
        st.rerun()

# ---------------------------------------------------------------- Final report
final = st.session_state.get("final")
if final:
    st.divider()
    status = final.get("status")
    if status == "COMPLETE":
        st.success(f"Run complete — {len(final.get('completed_agents', []))} agent step(s), "
                   f"${final.get('estimated_cost', 0):.4f} estimated cost.")
    elif status == "ERROR":
        st.error("The plan was rejected or the run ended in an error state.")
    else:
        st.info(f"Status: {status}")

    if final.get("final_report"):
        st.subheader("Final Report")
        with st.container(border=True):
            st.markdown(final["final_report"])

        dl1, dl2 = st.columns(2)
        pdf_path = os.path.join("artifacts", f"report_{final['run_id']}.pdf")
        try:
            export_report_pdf(final, pdf_path)
            with open(pdf_path, "rb") as fh:
                dl1.download_button("⬇️ Download PDF", fh.read(),
                                    file_name=f"research_report_{final['run_id']}.pdf",
                                    mime="application/pdf", use_container_width=True,
                                    type="primary")
        except Exception as e:  # noqa: BLE001
            dl1.error(f"PDF export failed: {e}")
        dl2.download_button("⬇️ Download Markdown", final["final_report"],
                            file_name=f"research_report_{final['run_id']}.md",
                            mime="text/markdown", use_container_width=True)

    st.caption("For the execution graph, agent trace, communication history, "
               "memory, and cost breakdown, see the **Dashboard** page in the sidebar.")

if not final and not pending and not submitted:
    st.info("Fill in a research question above and click **Run** to start.")