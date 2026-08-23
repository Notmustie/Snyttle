"""SQLite persistence: sessions, runs, agent logs, human decisions, artifacts.

This is the durable record layer (LangGraph's checkpointer holds live state;
this holds the history you can browse after the process exits). Every write is
best-effort: a persistence failure must never crash a run.
"""
from __future__ import annotations
import json
import os
import sqlite3
from datetime import datetime, timezone
import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs(
    run_id TEXT PRIMARY KEY,
    query TEXT,
    status TEXT,
    started_at TEXT,
    finished_at TEXT,
    revision_count INTEGER,
    input_tokens INTEGER,
    output_tokens INTEGER,
    estimated_cost REAL,
    final_report TEXT
);
CREATE TABLE IF NOT EXISTS agent_logs(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT, ts TEXT, agent TEXT, event TEXT,
    status TEXT, tool TEXT, duration REAL, error TEXT
);
CREATE TABLE IF NOT EXISTS messages(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT, ts TEXT, from_agent TEXT, to_agent TEXT,
    type TEXT, content TEXT
);
CREATE TABLE IF NOT EXISTS human_decisions(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT, ts TEXT, checkpoint TEXT, decision TEXT
);
CREATE TABLE IF NOT EXISTS artifacts(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT, kind TEXT, path TEXT
);
CREATE INDEX IF NOT EXISTS idx_logs_run ON agent_logs(run_id);
CREATE INDEX IF NOT EXISTS idx_msgs_run ON messages(run_id);
"""


def _connect(path: str = config.SQLITE_DB) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    con = sqlite3.connect(path, timeout=10)
    con.row_factory = sqlite3.Row
    return con


def init_db(path: str = config.SQLITE_DB) -> None:
    con = _connect(path)
    try:
        con.executescript(SCHEMA)
        con.commit()
    finally:
        con.close()


def persist_run(state: dict, path: str = config.SQLITE_DB) -> bool:
    """Write a completed (or failed) run and all its records. Best-effort."""
    try:
        init_db(path)
        con = _connect(path)
        rid = state.get("run_id")
        tu = state.get("token_usage", {}).get("total", {"input": 0, "output": 0})
        now = datetime.now(timezone.utc).isoformat()

        with con:
            con.execute(
                "INSERT OR REPLACE INTO runs VALUES(?,?,?,?,?,?,?,?,?,?)",
                (rid, state.get("user_query"), state.get("status"),
                 (state.get("execution_logs") or [{}])[0].get("ts", now), now,
                 state.get("revision_count", 0), tu.get("input", 0),
                 tu.get("output", 0), state.get("estimated_cost", 0.0),
                 state.get("final_report")))

            # Replace child rows so re-persisting the same run isn't duplicated.
            for t in ("agent_logs", "messages", "human_decisions", "artifacts"):
                con.execute(f"DELETE FROM {t} WHERE run_id=?", (rid,))

            con.executemany(
                "INSERT INTO agent_logs(run_id,ts,agent,event,status,tool,duration,error) "
                "VALUES(?,?,?,?,?,?,?,?)",
                [(rid, l.get("ts"), l.get("agent"), l.get("event"), l.get("status"),
                  l.get("tool"), l.get("duration"), l.get("error"))
                 for l in state.get("execution_logs", [])])

            con.executemany(
                "INSERT INTO messages(run_id,ts,from_agent,to_agent,type,content) "
                "VALUES(?,?,?,?,?,?)",
                [(rid, m.get("ts"), m.get("from_agent"), m.get("to_agent"),
                  m.get("type"), m.get("content"))
                 for m in state.get("messages", [])])

            con.executemany(
                "INSERT INTO human_decisions(run_id,ts,checkpoint,decision) VALUES(?,?,?,?)",
                [(rid, now, d.get("checkpoint"), d.get("decision"))
                 for d in state.get("human_decisions", [])])

            charts = (state.get("analysis_results") or {}).get("chart_paths", [])
            con.executemany("INSERT INTO artifacts(run_id,kind,path) VALUES(?,?,?)",
                            [(rid, "chart", c) for c in charts])
        con.close()
        return True
    except Exception:  # noqa: BLE001 — persistence must never break a run
        return False


# ---- Read helpers for the Memory viewer ----
def list_runs(limit: int = 25, path: str = config.SQLITE_DB) -> list[dict]:
    try:
        init_db(path)
        con = _connect(path)
        rows = con.execute(
            "SELECT run_id, query, status, finished_at, revision_count, "
            "input_tokens, output_tokens, estimated_cost FROM runs "
            "ORDER BY finished_at DESC LIMIT ?", (limit,)).fetchall()
        con.close()
        return [dict(r) for r in rows]
    except Exception:  # noqa: BLE001
        return []


def get_run(run_id: str, path: str = config.SQLITE_DB) -> dict:
    """Full persisted record for one run (for the Memory viewer detail pane)."""
    try:
        con = _connect(path)
        run = con.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if not run:
            con.close()
            return {}
        out = dict(run)
        for t, key in (("agent_logs", "logs"), ("messages", "messages"),
                       ("human_decisions", "decisions"), ("artifacts", "artifacts")):
            rows = con.execute(f"SELECT * FROM {t} WHERE run_id=?", (run_id,)).fetchall()
            out[key] = [dict(r) for r in rows]
        con.close()
        return out
    except Exception:  # noqa: BLE001
        return {}


def db_stats(path: str = config.SQLITE_DB) -> dict:
    try:
        init_db(path)
        con = _connect(path)
        s = {t: con.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()["c"]
             for t in ("runs", "agent_logs", "messages", "human_decisions", "artifacts")}
        con.close()
        return s
    except Exception:  # noqa: BLE001
        return {}