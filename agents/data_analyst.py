"""Data Analyst: profile, analyze and visualize uploaded datasets.

DAY 6: the one agent that goes beyond an LLM call — it executes Python.
Two stages:
  1. Deterministic profiling with Pandas (never generated code) — always reliable.
  2. Claude writes analysis/plot code, run via the controlled executor. If codegen
     or execution fails, the profile still stands and the agent degrades cleanly.
"""
from __future__ import annotations
import json
import os
from graph.state import comms, log
from agents.base_agent import call_claude, add_usage, resolve_effort, resolve_model
from tools.python_executor import run_python
import config

CODEGEN_SYSTEM = (
    "You write Python data-analysis scripts. Output ONLY executable Python — no "
    "prose, no markdown fences. A variable DATA_PATH is ALREADY DEFINED for you; "
    "use pd.read_csv(DATA_PATH) for CSV or pd.read_excel(DATA_PATH) for Excel, "
    "etc. — Pandas auto-detects many formats. Use matplotlib with the Agg backend; "
    "save each plot with plt.savefig('<name>.png') into the current working "
    "directory; print concise findings with print(). No network calls, no writes "
    "outside the working directory, no input(). Keep it under 60 lines and make "
    "it robust to missing or non-numeric columns."
)

# Injected above every generated script so the path is always correct and the
# model can never break execution by hardcoding a relative path.
PRELUDE = (
    "import matplotlib\n"
    "matplotlib.use('Agg')\n"
    "import pandas as pd, numpy as np\n"
    "import matplotlib.pyplot as plt\n"
    "DATA_PATH = {data_path!r}\n"
)


def _strip_path_assignment(code: str) -> str:
    """Drop any DATA_PATH reassignment the model emitted anyway."""
    return "\n".join(l for l in code.splitlines()
                     if not l.strip().startswith("DATA_PATH"))


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        t = t.rsplit("```", 1)[0]
    return t.strip()


def profile_dataset(path: str) -> dict:
    """Deterministic profile — auto-detect format and load."""
    import pandas as pd
    ext = os.path.splitext(path)[1].lower()
    
    if ext == ".xlsx" or ext == ".xls":
        df = pd.read_excel(path)
    elif ext == ".json":
        df = pd.read_json(path)
    elif ext == ".parquet":
        df = pd.read_parquet(path)
    else:  # default to CSV (includes .csv and unknown extensions)
        df = pd.read_csv(path)
    
    num = df.select_dtypes("number")
    return {
        "path": path,
        "shape": list(df.shape),
        "columns": list(df.columns)[:50],
        "dtypes": {c: str(t) for c, t in list(df.dtypes.items())[:50]},
        "missing": {c: int(n) for c, n in df.isna().sum().items() if n > 0},
        "duplicates": int(df.duplicated().sum()),
        "describe": json.loads(num.describe().to_json()) if not num.empty else {},
        "head": df.head(3).to_dict("records"),
    }


def data_analyst_node(state):
    rid = state["run_id"]
    rev = state.get("revision_count", 0)
    eff = resolve_effort(state, "data_analyst")
    model = resolve_model(state, "data_analyst")
    logs, errors = [], []
    token_usage = state.get("token_usage", {})

    datasets = [f for f in state.get("uploaded_files", []) 
            if f.get("type") in {"csv", "xlsx", "xls", "json", "parquet", "other"}]
    if not datasets:
        return {
            "current_agent": "data_analyst",
            "completed_agents": [f"data_analyst@{rev}"],
            "messages": [comms("data_analyst", "supervisor", "result",
                               "No dataset provided", rid)],
            "execution_logs": [log(rid, "data_analyst", "no dataset; skipped")],
        }

    ds = datasets[0]

    # --- Stage 1: deterministic profile ---
    try:
        info = profile_dataset(ds["path"])
        logs.append(log(rid, "data_analyst",
                        f"profiled {ds['name']}: {info['shape'][0]}x{info['shape'][1]}",
                        tool="pandas"))
    except Exception as e:  # noqa: BLE001 — unreadable dataset ends this agent
        return {
            "current_agent": "data_analyst",
            "completed_agents": [f"data_analyst@{rev}"],
            "errors": [{"agent": "data_analyst", "tool": "pandas", "error": str(e)}],
            "messages": [comms("data_analyst", "supervisor", "result",
                               f"Could not read dataset: {e}", rid)],
            "execution_logs": [log(rid, "data_analyst", "profiling failed",
                                   status="degraded", tool="pandas", error=str(e))],
        }

    # --- Stage 2: Claude writes analysis code, executor runs it ---
    analysis = {"stats": info.get("describe", {}), "findings": [],
                "chart_paths": [], "code": "", "stdout": ""}
    feedback = [f["issue"] for f in state.get("critic_feedback", [])
                if f.get("target_agent") == "data_analyst"]
    try:
        user = (f"Research question: {state['user_query']}\n"
                "DATA_PATH is already defined (absolute path to the CSV).\n"
                f"Columns/dtypes: {json.dumps(info['dtypes'])}\n"
                f"Missing values: {json.dumps(info['missing'])}\n"
                f"Rows: {info['shape'][0]}\n"
                + (f"Address this critic feedback: {feedback}\n" if feedback else "")
                + "Write the analysis script body.")
        raw, itok, otok = call_claude(CODEGEN_SYSTEM, user, model=model, effort=eff)
        body = _strip_path_assignment(_strip_fences(raw))
        code = PRELUDE.format(data_path=os.path.abspath(ds["path"])) + body
        token_usage = add_usage(token_usage, "data_analyst", itok, otok)
        logs.append(log(rid, "data_analyst", "analysis code generated", tool="claude"))

        res = run_python(code, run_id=rid, timeout=60)
        analysis["code"] = code
        analysis["stdout"] = res["stdout"]
        analysis["chart_paths"] = res["artifacts"]
        analysis["findings"] = [l for l in res["stdout"].splitlines() if l.strip()][:20]

        if res["exit_code"] == 0:
            logs.append(log(rid, "data_analyst",
                            f"analysis ran: {len(res['artifacts'])} chart(s)",
                            tool="python"))
        else:
            logs.append(log(rid, "data_analyst", "analysis script failed",
                            status="degraded", tool="python",
                            error=(res["stderr"] or "")[:300]))
            errors.append({"agent": "data_analyst", "tool": "python",
                           "error": (res["stderr"] or "")[:300]})
    except Exception as e:  # noqa: BLE001 — keep the profile, drop the analysis
        logs.append(log(rid, "data_analyst", "codegen/execution unavailable",
                        status="degraded", error=str(e)))
        errors.append({"agent": "data_analyst", "tool": "claude", "error": str(e)})

    msg = (f"Profiled {ds['name']} ({info['shape'][0]} rows); "
           f"{len(analysis['findings'])} finding(s), "
           f"{len(analysis['chart_paths'])} chart(s)")
    if errors:
        msg += f" ({len(errors)} failure(s))"

    return {
        "current_agent": "data_analyst",
        "completed_agents": [f"data_analyst@{rev}"],
        "dataset_info": info,
        "analysis_results": analysis,
        "token_usage": token_usage,
        "errors": errors,
        "messages": [comms("data_analyst", "supervisor", "result", msg, rid)],
        "execution_logs": logs,
    }