from typing import TypedDict

from langchain_anthropic import ChatAnthropic
from langgraph.graph import StateGraph, START, END


class State(TypedDict):
    message: str


llm = ChatAnthropic(
    model="claude-haiku-4-5-20251001",
    temperature=0
)


def supervisor(state: State):

    response = llm.invoke(
        f"""
        You are the Supervisor Agent of a research system.

        The user has submitted this research request:

        {state["message"]}

        Explain what should happen next in the research workflow.
        """
    )

    return {
        "message": response.content
    }


builder = StateGraph(State)

builder.add_node("supervisor", supervisor)

builder.add_edge(START, "supervisor")
builder.add_edge("supervisor", END)

graph = builder.compile()