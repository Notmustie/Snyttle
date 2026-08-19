"""Central configuration. All tunables live here so nothing is hardcoded in logic."""
import os

# ---- Models ----
AGENT_MODEL = "claude-sonnet-5"           # reasoning agents
PLANNER_MODEL = "claude-sonnet-5"

# ---- Reasoning effort (adaptive thinking) ----
# On Claude 4.6+, token spend on reasoning is controlled by adaptive thinking
# (thinking={"type":"adaptive"}) + an effort level, NOT budget_tokens (deprecated).
# Levels: "low" | "medium" | "high"  ("high" == default/max effort).
# Set an agent's effort to None to disable thinking entirely (cheapest).
# effort is soft guidance; max_tokens is the hard cap on thinking + text.
DEFAULT_EFFORT = "medium"

# Spend reasoning where it pays off; stay cheap where it doesn't.
AGENT_EFFORT = {
    "planner": "high",         # task decomposition benefits from reasoning
    "research": "low",         # mostly retrieval + light synthesis
    "knowledge": "low",        # retrieval + provenance
    "data_analyst": "medium",  # interpreting stats
    "critic": "high",          # methodology / consistency checks benefit most
    "writer": "medium",        # structured synthesis
}

# Give higher-effort agents more headroom so thinking doesn't crowd out the answer.
MAX_TOKENS_BY_EFFORT = {"low": 1500, "medium": 3000, "high": 6000, None: 1500}


def effort_for(agent: str) -> str | None:
    return AGENT_EFFORT.get(agent, DEFAULT_EFFORT)


# ---- Price table (USD per 1M tokens) — used only for ESTIMATED cost display ----
PRICE_TABLE = {
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00},
}

# ---- Control constants ----
MAX_REVISIONS = 2                            # Critic loop guard (locked)
AUTO_APPROVE = os.getenv("AUTO_APPROVE", "0") == "1"  # skip HITL interrupt (CLI/tests)

# ---- RAG ----
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150
RETRIEVE_K = 4
CHROMA_DIR = "./artifacts/chroma"            # Chroma default embeddings (all-MiniLM-L6-v2)

# ---- Persistence ----
SQLITE_DB = "./artifacts/workforce.db"

# ---- Tools ----
TAVILY_MAX_RESULTS = 5
OPENALEX_MAX_RESULTS = 5

# The six specialist agents (Supervisor is the 7th orchestrator node)
SPECIALISTS = ["research", "knowledge", "data_analyst"]
ALL_AGENTS = ["planner", "research", "knowledge", "data_analyst", "critic", "writer"]


def price_for(model: str) -> dict:
    return PRICE_TABLE.get(model, {"input": 0.0, "output": 0.0})
