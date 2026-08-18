"""Shared machinery for every agent.

In SKELETON mode the agents don't call Claude — each stub logs, emits a comms
message, and passes state through. This lets the whole graph run end-to-end with
ZERO API keys or external services. Swap `stub_produce` for `call_claude` as you
build each agent for real (days 3-7).
"""
from __future__ import annotations
import time
from graph.state import comms, log
import config

try:
    import anthropic  # optional until you build real agents
    _client = anthropic.Anthropic() if anthropic.__name__ else None
except Exception:  # noqa: BLE001
    anthropic = None
    _client = None


def add_usage(token_usage: dict, agent: str, in_tok: int, out_tok: int) -> dict:
    """Accumulate per-agent + total token usage. Call once per Claude response."""
    tu = {k: dict(v) for k, v in token_usage.items()}  # shallow copy
    tu.setdefault(agent, {"input": 0, "output": 0})
    tu.setdefault("total", {"input": 0, "output": 0})
    tu[agent]["input"] += in_tok
    tu[agent]["output"] += out_tok
    tu["total"]["input"] += in_tok
    tu["total"]["output"] += out_tok
    return tu


def estimate_cost(token_usage: dict, model: str = config.AGENT_MODEL) -> float:
    """Derive an ESTIMATED USD cost from the price table. Label as estimate in UI."""
    price = config.price_for(model)
    total = token_usage.get("total", {"input": 0, "output": 0})
    return round(total["input"] / 1e6 * price["input"]
                 + total["output"] / 1e6 * price["output"], 6)


def call_claude(system: str, user: str, model: str = config.AGENT_MODEL,
                max_tokens: int = 1500):
    """Real Claude call. Returns (text, input_tokens, output_tokens).

    Used once you replace the stubs. Requires ANTHROPIC_API_KEY.
    """
    if _client is None:
        raise RuntimeError("anthropic client unavailable — set ANTHROPIC_API_KEY "
                           "and `pip install anthropic`")
    resp = _client.messages.create(
        model=model, max_tokens=max_tokens,
        system=system, messages=[{"role": "user", "content": user}],
    )
    text = "".join(b.text for b in resp.content if b.type == "text")
    return text, resp.usage.input_tokens, resp.usage.output_tokens


def stub_node(agent: str, to_agent: str, msg: str, produces: dict | None = None):
    """Build a stub node function for the skeleton.

    Returns a callable(state)->partial-update that logs, emits a comms message,
    marks the agent completed, and merges any `produces` (dummy outputs).
    """
    def _node(state):
        t0 = time.time()
        rid = state["run_id"]
        rev = state.get("revision_count", 0)
        update = {
            "current_agent": agent,
            "completed_agents": [f"{agent}@{rev}"],  # cycle-stamped for revision re-runs
            "messages": [comms(agent, to_agent, "result", msg, rid)],
            "execution_logs": [log(rid, agent, f"{agent} stub ran",
                                   duration=round(time.time() - t0, 4))],
        }
        if produces:
            update.update(produces)
        return update
    return _node
