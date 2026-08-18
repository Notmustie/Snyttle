"""Data Analyst: CSV -> Pandas EDA -> Python executor -> charts. Skeleton = dummy stats.

This is the ONE agent that extends base beyond an LLM call (it runs Python).
"""
from agents.base_agent import stub_node

data_analyst_node = stub_node(
    "data_analyst", "supervisor", "Profiled dataset, ran EDA, saved 2 charts (stub)",
    produces={
        "dataset_info": {"shape": [100, 5], "columns": ["a", "b"], "missing": 0, "duplicates": 0},
        "analysis_results": {"stats": {"mean_a": 1.0}, "findings": ["stub finding"],
                             "chart_paths": ["artifacts/stub_chart.png"], "code": "# stub"},
    },
)
