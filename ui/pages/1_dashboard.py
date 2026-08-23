"""Dashboard: execution graph, agent trace, communication history, memory,
data analysis charts, and logs/cost. Reads the same session state Home writes
to — start a run on Home first.
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import streamlit as st
from graph.workflow import build_graph
from memory.database import list_runs, get_run, db_stats
import config

st.set_page_config(page_title="Dashboard — Research Workforce", page_icon="📊", layout="wide")
st.title("📊 Dashboard")

if "graph" not in st.session_state:
    st.session_state.graph = build_graph()
graph = st.session_state.graph

final = st.session_state.get("final")
pending = st.session_state.get("pending")

if not final and not pending:
    st.info("No active or completed run yet. Start one on the **Home** page.")

# ---------------------------------------------------------------- Status stepper
STEP_ORDER = ["planner", "research", "knowledge", "data_analyst", "critic", "writer"]
STEP_LABELS = {"planner": "Plan", "research": "Research", "knowledge": "RAG",
              "data_analyst": "Analyze", "critic": "Critique", "writer": "Write"}

if final or pending:
    done = set()
    for a in (final or {}).get("completed_agents", []):
        done.add(a.split("@")[0])
    current = (final or {}).get("current_agent") or "planner"
    cols = st.columns(len(STEP_ORDER))
    for i, step in enumerate(STEP_ORDER):
        label = STEP_LABELS[step]
        if step in done:
            cols[i].markdown(f"✅ **{label}**")
        elif step == current and pending:
            cols[i].markdown(f"⏸ **{label}**")
        elif step == current:
            cols[i].markdown(f"🔄 **{label}**")
        else:
            cols[i].markdown(f"⚪ {label}")
    st.divider()

tabs = st.tabs(["Execution graph", "Agent trace", "Communication",
                "Memory", "Analysis & Charts", "Logs & cost"])

# ---------------------------------------------------------------- Execution graph
with tabs[0]:
    status_line = ""
    if final:
        status_line = f"**Status:** {final['status']} — **Run:** `{final['run_id']}`"
    elif pending:
        status_line = "**Status:** paused for plan approval"
    if status_line:
        st.markdown(status_line)
    try:
        png = graph.get_graph().draw_mermaid_png()
        st.image(png, caption="Compiled LangGraph workflow", use_container_width=True)
    except Exception:
        st.code(graph.get_graph().draw_mermaid(), language="mermaid")

# ---------------------------------------------------------------- Agent trace
with tabs[1]:
    if final:
        st.dataframe(final["execution_logs"], use_container_width=True, height=420)
    else:
        st.caption("No trace yet.")

# ---------------------------------------------------------------- Communication
with tabs[2]:
    if final:
        for m in final["messages"]:
            icon = {"delegation": "➡️", "result": "✅", "feedback": "🔁", "system": "👤"}.get(m["type"], "•")
            st.markdown(f"{icon} `{m['from_agent']}` → `{m['to_agent']}` "
                       f"**[{m['type']}]** {m['content']}")
    else:
        st.caption("No communication log yet.")

# ---------------------------------------------------------------- Memory
with tabs[3]:
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
                st.caption("Messages")
                st.dataframe(rec.get("messages", []), use_container_width=True)
            with m2:
                st.caption("Human decisions")
                st.dataframe(rec.get("decisions", []), use_container_width=True)
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

# ---------------------------------------------------------------- Analysis & Charts
with tabs[4]:
    if final and final.get("dataset_info"):
        ds = final["dataset_info"]
        ana = final.get("analysis_results") or {}
        st.subheader("Dataset")
        c1, c2, c3 = st.columns(3)
        c1.metric("Rows", ds["shape"][0])
        c2.metric("Columns", ds["shape"][1])
        c3.metric("Duplicate rows", ds.get("duplicates", 0))
        if ds.get("missing"):
            st.caption("Missing values by column")
            st.json(ds["missing"])

        if ana.get("cleaning_notes"):
            st.subheader("Cleaning applied")
            for note in ana["cleaning_notes"]:
                st.markdown(f"- {note}")

        if ana.get("findings"):
            st.subheader("Findings")
            for f_ in ana["findings"]:
                st.markdown(f"- {f_}")

        charts = ana.get("chart_paths") or []
        if charts:
            st.subheader("Charts")
            cols = st.columns(2)
            for i, path in enumerate(charts):
                if os.path.exists(path):
                    label = os.path.basename(path).rsplit(".", 1)[0].replace("_", " ").title()
                    cols[i % 2].image(path, caption=label, use_container_width=True)
        else:
            st.caption("No charts were generated for this run.")
    elif final:
        st.caption("No dataset was analyzed in this run.")
    else:
        st.caption("No active run.")

# ---------------------------------------------------------------- Logs & cost
with tabs[5]:
    if final:
        st.subheader("Reasoning effort & model (this run)")
        prefs = final.get("preferences") or {}
        eff_ov, model_ov = prefs.get("effort_override"), prefs.get("model_override")
        rows = [{"agent": a,
                "effort": eff_ov or config.effort_for(a),
                "model": model_ov or config.model_for(a),
                "source": "override" if (eff_ov or model_ov) else "config default"}
               for a in config.ALL_AGENTS]
        st.dataframe(rows, use_container_width=True)

        st.subheader("Token usage")
        st.json(final.get("token_usage", {}))
        st.metric("Estimated cost (USD)", f"${final.get('estimated_cost', 0):.4f}")
        st.caption("Estimated from the price table, priced per agent's resolved "
                   "model. Thinking tokens (driven by effort) bill as output tokens.")

        st.subheader("Errors")
        errs = final.get("errors") or []
        if errs:
            st.dataframe(errs, use_container_width=True)
        else:
            st.caption("None")
    else:
        st.caption("No active run.")