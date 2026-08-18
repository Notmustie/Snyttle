"""SQLite persistence (stub): sessions, runs, agent_logs, decisions, artifacts."""
import sqlite3, config
SCHEMA = """
CREATE TABLE IF NOT EXISTS runs(run_id TEXT PRIMARY KEY, query TEXT, status TEXT, ts TEXT);
CREATE TABLE IF NOT EXISTS agent_logs(id INTEGER PRIMARY KEY, run_id TEXT, agent TEXT, event TEXT, ts TEXT);
CREATE TABLE IF NOT EXISTS human_decisions(id INTEGER PRIMARY KEY, run_id TEXT, decision TEXT, ts TEXT);
"""
def init_db(path: str = config.SQLITE_DB):
    con = sqlite3.connect(path); con.executescript(SCHEMA); con.commit(); con.close()
def save_run(run_id: str, query: str, status: str, ts: str, path: str = config.SQLITE_DB):
    con = sqlite3.connect(path)
    con.execute("INSERT OR REPLACE INTO runs VALUES(?,?,?,?)", (run_id, query, status, ts))
    con.commit(); con.close()
