"""Mock Jira ticket creation tool."""

import json
import uuid

from langchain_core.tools import tool


@tool
def create_jira_ticket(summary: str, description: str) -> str:
    """Create a mock Jira ticket and return its key, summary, and URL."""
    ticket_key = f"OPS-{uuid.uuid4().hex[:6].upper()}"
    return json.dumps(
        {
            "key": ticket_key,
            "summary": summary,
            "description": description,
            "url": f"https://jira.example.com/browse/{ticket_key}",
        }
    )
