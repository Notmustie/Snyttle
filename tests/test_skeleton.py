"""Smoke tests for the walking skeleton. Run: AUTO_APPROVE=1 pytest -q"""
import os
os.environ["AUTO_APPROVE"] = "1"
from graph.workflow import build_graph
from graph.state import new_state
import config


def _run(query, files=None):
    g = build_graph()
    s = new_state(query, uploaded_files=files or [])
    return g.invoke(s, {"configurable": {"thread_id": s["run_id"]}})


def test_end_to_end_completes():
    final = _run("test query")
    assert final["status"] == "COMPLETE"
    assert final["final_report"]


def test_dynamic_routing_skips_unneeded_agents():
    # No files -> no RAG, no data analyst
    final = _run("research only")
    done = " ".join(final["completed_agents"])
    assert "research@0" in done
    assert "knowledge@0" not in done
    assert "data_analyst@0" not in done


def test_csv_triggers_data_analyst():
    final = _run("analyze", files=[{"path": "x.csv", "type": "csv", "name": "x.csv"}])
    assert "data_analyst@0" in final["completed_agents"]


def test_comms_log_has_six_agent_identities():
    final = _run("q", files=[{"path": "x.csv", "type": "csv", "name": "x.csv"},
                             {"path": "y.pdf", "type": "pdf", "name": "y.pdf"}])
    actors = {m["from_agent"] for m in final["messages"]}
    # planner, research, knowledge, data_analyst, critic, writer all appear
    for a in ("planner", "research", "knowledge", "data_analyst", "critic", "writer"):
        assert a in actors, f"{a} missing from comms log"
