"""Ticket creation specialist node."""

import json

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langgraph.prebuilt import create_react_agent

from src.llm import get_chat_model
from src.state import OpsState, latest_user_request
from src.tools.github_tools import create_github_issue


def ticket_creator_node(state: OpsState) -> dict[str, dict[str, object]]:
    """Draft and create a GitHub issue using the issue tool."""
    request = latest_user_request(state["messages"])
    context = state.get("analysis", "")
    agent = create_react_agent(get_chat_model(), tools=[create_github_issue])
    result = agent.invoke(
        {
            "messages": [
                SystemMessage(
                    content=(
                        "You are the Ticket Creator Agent. Create a useful, "
                        "concise GitHub issue from the request and any investigation "
                        "report. You must call create_github_issue exactly once. "
                        "After the tool succeeds, briefly confirm the issue number."
                    )
                ),
                HumanMessage(
                    content=f"Request:\n{request}\n\nInvestigation:\n{context or 'None'}"
                ),
            ]
        }
    )
    tool_result = next(
        (
            message.content
            for message in reversed(result["messages"])
            if isinstance(message, ToolMessage)
            and message.name == "create_github_issue"
        ),
        None,
    )
    if not isinstance(tool_result, str):
        raise RuntimeError("The ticket creator did not invoke the GitHub issue tool.")
    ticket = json.loads(tool_result)
    if not isinstance(ticket, dict) or not all(
        isinstance(ticket.get(field), str) for field in ("number", "title", "url")
    ):
        raise ValueError("The GitHub issue tool returned an invalid issue.")
    return {"ticket": ticket}
