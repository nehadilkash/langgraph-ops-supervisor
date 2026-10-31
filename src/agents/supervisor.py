"""Supervisor routing node."""

from __future__ import annotations

from typing import Literal, Optional

from langchain_core.messages import SystemMessage
from pydantic import BaseModel, Field

from src.llm import get_chat_model
from src.state import OpsState, latest_user_request


class RouteDecision(BaseModel):
    """Structured supervisor decision for the current user request."""

    route: Literal["analyze", "create_ticket", "analyze_and_ticket", "respond"] = (
        Field(description="The specialist workflow to run.")
    )
    reason: str = Field(description="Briefly explain the routing decision.")
    response: Optional[str] = Field(
        default=None,
        description="A direct answer, required when route is respond.",
    )


def supervisor_node(state: OpsState) -> dict[str, object]:
    """Choose which specialist should handle the latest request."""
    model = get_chat_model().with_structured_output(RouteDecision)
    decision = model.invoke(
        [
            SystemMessage(
                content=(
                    "You are an operations supervisor. Classify only the most "
                    "recent user message, using earlier turns only as context. "
                    "Route requests about logs, "
                    "incidents, or database health to analyze. Route requests to "
                    "open/create/file a Jira ticket to create_ticket. If a request "
                    "needs investigation and a ticket, choose analyze_and_ticket. "
                    "For other requests, choose respond and provide a concise "
                    "response. Never claim a ticket was created unless the ticket "
                    "creator agent runs."
                )
            ),
            *state["messages"],
        ]
    )
    if not isinstance(decision, RouteDecision):
        raise TypeError("The supervisor model returned an invalid routing result.")
    if decision.route == "respond" and not decision.response:
        raise ValueError("The supervisor must provide a response for route=respond.")
    return {
        "route": decision.route,
        "routing_reason": decision.reason,
        "direct_answer": decision.response if decision.route == "respond" else "",
        "analysis": "",
        "log_findings": {},
        "health_checks": [],
        "ticket": {},
        "notification": {},
        "response": "",
    }
