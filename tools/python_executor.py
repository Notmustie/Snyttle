"""Controlled Python execution for the Data Analyst.

Runs generated code in a SUBPROCESS with a timeout and a scrubbed environment,
inside a per-run working directory. Captures stdout/stderr/exit status and
collects any chart files the code writes.

NOT a security sandbox. A determined adversary can escape a subprocess. This is
appropriate for a trusted single-user demo; production would need containers,
seccomp, or a dedicated execution service. See ARCHITECTURE.md §15.
"""
from __future__ import annotations
import os
import subprocess
import sys
import tempfile
import time

# Env vars never exposed to generated code.
_SECRET_PREFIXES = ("ANTHROPIC", "TAVILY", "OPENAI", "AWS", "GOOGLE", "AZURE",
                    "HF_", "HUGGING", "OPENALEX", "API_KEY", "SECRET", "TOKEN")


def _safe_env() -> dict:
    """Copy the environment minus anything that looks like a credential."""
    env = {}
    for k, v in os.environ.items():
        up = k.upper()
        if any(up.startswith(p) or p in up for p in _SECRET_PREFIXES):
            continue
        env[k] = v
    env["MPLBACKEND"] = "Agg"          # headless matplotlib
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def run_python(code: str, run_id: str, timeout: int = 30,
               workdir: str | None = None) -> dict:
    """Execute `code`. Returns {stdout, stderr, exit_code, artifacts, timed_out}."""
    workdir = workdir or os.path.join("artifacts", f"run_{run_id}")
    os.makedirs(workdir, exist_ok=True)

    # Use a start-time watermark rather than a before/after directory diff.
    # The revision loop can call this multiple times against the SAME workdir,
    # and if a regenerated script reuses a chart filename (e.g. "chart.png"
    # every cycle), a pure set-difference sees it as "already existed" and
    # silently drops it from artifacts. mtime correctly catches both new AND
    # overwritten files from this run.
    run_start = time.time()

    with tempfile.NamedTemporaryFile("w", suffix=".py", dir=workdir,
                                     delete=False) as f:
        f.write(code)
        script = f.name

    timed_out = False
    try:
        proc = subprocess.run(
            [sys.executable, os.path.basename(script)],
            cwd=workdir, env=_safe_env(), capture_output=True,
            text=True, timeout=timeout,
        )
        stdout, stderr, code_rc = proc.stdout, proc.stderr, proc.returncode
    except subprocess.TimeoutExpired:
        timed_out = True
        stdout, stderr, code_rc = "", f"Execution exceeded {timeout}s timeout", -1
    finally:
        try:
            os.remove(script)
        except OSError:
            pass

    artifacts = []
    for n in sorted(os.listdir(workdir)):
        if not n.lower().endswith((".png", ".jpg", ".svg", ".csv")):
            continue
        path = os.path.join(workdir, n)
        try:
            if os.path.getmtime(path) >= run_start - 0.5:  # small clock-skew buffer
                artifacts.append(path)
        except OSError:
            continue

    return {
        "stdout": stdout[-8000:],
        "stderr": stderr[-4000:],
        "exit_code": code_rc,
        "artifacts": artifacts,
        "timed_out": timed_out,
    }