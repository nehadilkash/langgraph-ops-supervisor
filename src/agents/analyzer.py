"""Log analysis specialist node."""

import json

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.prebuilt import create_react_agent

from src.llm import get_chat_model
from src.state import OpsState, latest_user_request
from src.tools.log_tools import (
    analyze_logs,
    check_configured_endpoints,
    get_database_status,
    parse_log_lines,
)


def analyzer_node(state: OpsState) -> dict[str, object]:
    """Analyze logs and run configured health checks for deterministic actions."""
    request = latest_user_request(state["messages"])
    log_findings = parse_log_lines(request)
    health_checks = check_configured_endpoints()
    agent = create_react_agent(
        get_chat_model(),
        tools=[analyze_logs, get_database_status],
    )
    result = agent.invoke(
        {
            "messages": [
                SystemMessage(
                    content=(
                        "You are the Log Analyzer Agent. Use analyze_logs for log "
                        "or incident investigations. Use get_database_status when "
                        "database health is relevant. Base your concise report on "
                        "the tool results; distinguish observed facts from "
                        "recommendations. The deterministic log scan and configured "
                        "health-check results below are observed data and should "
                        "not be changed or inferred differently."
                    )
                ),
                HumanMessage(
                    content=(
                        f"Request:\n{request}\n\n"
                        f"Deterministic log scan:\n{json.dumps(log_findings)}\n\n"
                        f"Configured health checks:\n{json.dumps(health_checks)}"
                    )
                ),
            ]
        }
    )
    answer = next(
        (
            message.content
            for message in reversed(result["messages"])
            if isinstance(message, AIMessage) and isinstance(message.content, str)
        ),
        None,
    )
    if not answer:
        raise RuntimeError("The log analyzer did not return a report.")
    return {
        "analysis": answer,
        "log_findings": log_findings,
        "health_checks": health_checks,
    }
