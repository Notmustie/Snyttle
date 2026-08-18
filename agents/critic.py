"""Critic: checks evidence/reasoning/methodology. Skeleton PASSES (no ERROR feedback).

Real version emits ERROR severity to trigger the bounded revision loop.
"""
from agents.base_agent import stub_node
from graph.state import feedback

critic_node = stub_node(
    "critic", "supervisor", "Reviewed outputs — PASS (stub)",
    produces={"critic_feedback": [feedback("INFO", "writer", "Looks coherent", "Proceed")]},
)
