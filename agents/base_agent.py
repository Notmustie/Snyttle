
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


def estimate_cost(token_usage: dict) -> float:
    """Sum ESTIMATED cost per agent, each priced at its own resolved model."""
    total = 0.0
    for agent, counts in token_usage.items():
        if agent == "total":
            continue
        model = config.model_for(agent)
        price = config.price_for(model)
        total += counts.get("input", 0) / 1e6 * price["input"]
        total += counts.get("output", 0) / 1e6 * price["output"]
    return round(total, 6)


def call_claude(system: str, user: str, model: str = config.AGENT_MODEL,
                max_tokens: int | None = None, effort: str | None = "medium"):
    """Real Claude call. Returns (text, input_tokens, output_tokens).

    `effort` controls reasoning token spend on Claude 4.6+ via adaptive thinking.
    Pass effort=None to disable thinking (cheapest). "high" == default/max effort.
    max_tokens defaults from the effort tier so thinking has headroom.
    Requires ANTHROPIC_API_KEY. Used once you replace the stubs.
    """
    if _client is None:
        raise RuntimeError("anthropic client unavailable — set ANTHROPIC_API_KEY "
                           "and `pip install anthropic`")
    if max_tokens is None:
        max_tokens = config.MAX_TOKENS_BY_EFFORT.get(effort, 1500)

    kwargs = dict(model=model, max_tokens=max_tokens, system=system,
                  messages=[{"role": "user", "content": user}])
    if effort:  # enable adaptive thinking at the requested effort level
        kwargs["thinking"] = {"type": "adaptive"}
        kwargs["output_config"] = {"effort": effort}

    resp = _client.messages.create(**kwargs)
    # Thinking blocks are billed as output tokens; we only read the text blocks.
    text = "".join(b.text for b in resp.content if b.type == "text")
    return text, resp.usage.input_tokens, resp.usage.output_tokens

def resolve_model(state, agent: str) -> str:
    """Model for this agent: a per-run override (from preferences) wins,
    otherwise the per-agent default from config."""
    override = (state.get("preferences") or {}).get("model_override")
    if override in (None, "", "default"):
        return config.model_for(agent)
    return override

def resolve_effort(state, agent: str) -> str | None:
    """Effort for this agent: a per-run override (from preferences) wins,
    otherwise the per-agent default from config. Used by real agents and shown
    in the trace so the UI toggle is meaningful even in skeleton mode."""
    override = (state.get("preferences") or {}).get("effort_override")
    if override in (None, "", "default"):
        return config.effort_for(agent)
    return override


def stub_node(agent: str, to_agent: str, msg: str, produces: dict | None = None):
    """Build a stub node function for the skeleton.

    Returns a callable(state)->partial-update that logs, emits a comms message,
    marks the agent completed, and merges any `produces` (dummy outputs).
    """
    def _node(state):
        t0 = time.time()
        rid = state["run_id"]
        rev = state.get("revision_count", 0)
        eff = resolve_effort(state, agent)
        entry = log(rid, agent, f"{agent} stub ran (effort={eff})",
                    duration=round(time.time() - t0, 4))
        entry["effort"] = eff
        update = {
            "current_agent": agent,
            "completed_agents": [f"{agent}@{rev}"],  # cycle-stamped for revision re-runs
            "messages": [comms(agent, to_agent, "result", msg, rid)],
            "execution_logs": [entry],
        }
        if produces:
            update.update(produces)
        return update
    return _node