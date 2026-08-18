"""Sandboxed-ish Python executor (stub).

Real: run in a controlled working dir via subprocess, timeout, capture
stdout/stderr/exit, save plots by run_id. Never exec untrusted code in prod.
"""
def run_python(code: str, run_id: str, timeout: int = 30) -> dict:
    return {"stdout": "", "stderr": "", "exit_code": 0, "artifacts": []}
