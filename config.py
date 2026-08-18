"""Central configuration. All tunables live here so nothing is hardcoded in logic."""
import os

# ---- Models ----
AGENT_MODEL = "claude-sonnet-4-6"           # reasoning agents
PLANNER_MODEL = "claude-sonnet-4-6"

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
