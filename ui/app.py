"""Streamlit control center — the walking-skeleton shell.

Every rubric-required panel is present and reads from ResearchState, so each
requirement has a visible home before the agents are built for real.
Run:  streamlit run ui/app.py
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import streamlit as st
from graph.workflow import build_graph
from graph.state import new_state
from agents.base_agent import add_usage, estimate_cost
import config

st.set_page_config(page_title="Research Workforce", layout="wide")
st.title("Multi-Agent Research Workforce")

# ---- Sidebar: input + HITL controls ----
with st.sidebar:
    st.header("New run")
    query = st.text_area("Research question",
                         "What factors are associated with customer churn?")
    up = st.file_uploader("Datasets / documents", accept_multiple_files=True)
    auto = st.toggle("Auto-approve plan (skip HITL)", value=True)
    st.caption("Human-in-the-loop controls")
    c1, c2 = st.columns(2)
    start = c1.button("Start", type="primary")
    c2.button("Pause")            # wired to interrupt in the real build
    st.button("Resume"); st.button("Approve"); st.button("Retry")

# ---- Run the graph ----
if start:
    os.environ["AUTO_APPROVE"] = "1" if auto else "0"
    files = []
    for f in up or []:
        kind = "csv" if f.name.endswith(".csv") else "pdf" if f.name.endswith(".pdf") else "other"
        path = os.path.join("data", f.name)
        os.makedirs("data", exist_ok=True)
        with open(path, "wb") as out:
            out.write(f.getbuffer())
        files.append({"path": path, "type": kind, "name": f.name})

    graph = build_graph()
    state = new_state(query, uploaded_files=files)
    with st.spinner("Running workforce..."):
        final = graph.invoke(state, {"configurable": {"thread_id": state["run_id"]}})
    final["estimated_cost"] = estimate_cost(final.get("token_usage", {}))
    st.session_state["final"] = final

final = st.session_state.get("final")

# ---- Panels ----
tabs = st.tabs(["Dashboard", "Execution graph", "Agent trace", "Communication",
                "Memory", "Analysis", "Logs & cost", "Report"])

with tabs[0]:  # Dashboard
    if final:
        st.metric("Status", final["status"])
        st.write("**Run ID:**", final["run_id"])
        st.write("**Completed agents:**", ", ".join(final["completed_agents"]))
        st.write("**Route flags:**", final.get("route_flags", {}))
    else:
        st.info("Start a run from the sidebar.")

with tabs[1]:  # Execution graph (LangGraph viz)
    try:
        png = build_graph().get_graph().draw_mermaid_png()
        st.image(png, caption="Compiled LangGraph workflow")
    except Exception:
        st.code(build_graph().get_graph().draw_mermaid(), language="mermaid")

with tabs[2]:  # Agent trace
    if final:
        st.dataframe(final["execution_logs"], use_container_width=True)

with tabs[3]:  # Communication history
    if final:
        for m in final["messages"]:
            st.write(f"`{m['from_agent']}` → `{m['to_agent']}` "
                     f"**[{m['type']}]** {m['content']}")

with tabs[4]:  # Memory viewer
    if final:
        st.subheader("Current ResearchState")
        st.json({k: v for k, v in final.items() if k != "final_report"})

with tabs[5]:  # Analysis
    if final and final.get("analysis_results"):
        st.write(final["dataset_info"])
        st.write(final["analysis_results"])
    else:
        st.caption("No dataset analysis in this run.")

with tabs[6]:  # Logs & cost
    if final:
        st.subheader("Token usage")
        st.json(final.get("token_usage", {}))
        st.metric("Estimated cost (USD)", f"${final.get('estimated_cost', 0):.4f}")
        st.caption("Locally estimated from the configured price table.")
        st.subheader("Errors")
        st.write(final.get("errors") or "None")

with tabs[7]:  # Final report
    if final and final.get("final_report"):
        st.markdown(final["final_report"])
