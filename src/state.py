"""Shared state schema for the operations supervisor graph."""

from typing import Annotated, Literal, TypedDict

from langchain_core.messages import AnyMessage, HumanMessage
from langgraph.graph.message import add_messages

Route = Literal["analyze", "create_ticket", "analyze_and_ticket", "respond"]


class OpsState(TypedDict, total=False):
    """Data passed between graph nodes; messages accumulate across turns."""

    messages: Annotated[list[AnyMessage], add_messages]
    route: Route
    routing_reason: str
    direct_answer: str
    analysis: str
    log_findings: dict[str, object]
    health_checks: list[dict[str, object]]
    ticket: dict[str, object]
    notification: dict[str, str]
    response: str


def latest_user_request(messages: list[AnyMessage]) -> str:
    """Return the newest human message in the accumulated conversation."""
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            content = message.content
            return content if isinstance(content, str) else str(content)
    raise ValueError("The conversation does not contain a user request.")
