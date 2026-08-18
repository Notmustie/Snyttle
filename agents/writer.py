"""Writer: synthesizes validated findings into the final markdown report."""
from graph.state import comms, log, Status


def writer_node(state):
    rid = state["run_id"]
    report = (
        f"# Research Report\n\n**Question:** {state['user_query']}\n\n"
        f"## Summary\n(stub) Synthesis of {len(state.get('research_results', []))} web "
        f"and {len(state.get('literature_results', []))} academic sources.\n\n"
        f"## Findings\n(stub)\n\n## References\n(stub)\n\n"
        f"_Run {rid} — skeleton output._\n"
    )
    return {
        "current_agent": "writer",
        "final_report": report,
        "completed_agents": ["writer"],
        "status": Status.COMPLETE,
        "messages": [comms("writer", "supervisor", "result", "Final report generated", rid)],
        "execution_logs": [log(rid, "writer", "report written")],
    }
