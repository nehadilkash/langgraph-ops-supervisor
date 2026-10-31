"""LangGraph workflow construction and checkpointer wiring."""

import hashlib
import json

from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph

from src.agents.analyzer import analyzer_node
from src.agents.supervisor import supervisor_node
from src.agents.ticket_creator import ticket_creator_node
from src.state import OpsState
from src.tools.github_tools import create_issue
from src.tools.teams_tools import send_teams_alert


def _has_incident(state: OpsState) -> bool:
    findings = state.get("log_findings", {})
    checks = state.get("health_checks", [])
    return bool(findings.get("error_count", 0)) or any(
        check.get("status") == "unhealthy" for check in checks
    )


def _supervisor_route(state: OpsState) -> str:
    return state["route"]


def _after_analysis(state: OpsState) -> str:
    if state["route"] == "analyze_and_ticket":
        return "ticket_creator"
    return "automatic_issue" if _has_incident(state) else "finalize"


def _after_ticket_creation(state: OpsState) -> str:
    return "incident_notification" if _has_incident(state) else "finalize"


def _automatic_issue(state: OpsState) -> dict[str, object]:
    findings = state.get("log_findings", {})
    errors = findings.get("errors", [])
    failed_checks = [
        check
        for check in state.get("health_checks", [])
        if check.get("status") == "unhealthy"
    ]
    fingerprint_data = json.dumps(
        {"errors": errors, "failed_health_checks": failed_checks},
        sort_keys=True,
    )
    fingerprint = hashlib.sha256(fingerprint_data.encode("utf-8")).hexdigest()
    title = (
        "Automated incident: "
        f"{len(errors)} log error(s), {len(failed_checks)} failed health check(s)"
    )
    details = [
        "This issue was created automatically by the LangGraph Ops Supervisor.",
        "",
        f"Log severity: {findings.get('severity', 'unknown')}",
        f"Error count: {findings.get('error_count', 0)}",
    ]
    if errors:
        details.extend(["", "Matching log lines:", *[f"- `{line[:500]}`" for line in errors[:20]]])
    if failed_checks:
        details.extend(["", "Failed health checks:"])
        for check in failed_checks:
            detail = check.get("detail") or "HTTP {}".format(
                check.get("http_status", "unknown")
            )
            details.append(
                f"- {check.get('endpoint', 'unknown endpoint')}: {detail}"
            )
    issue = create_issue(title, "\n".join(details), fingerprint=fingerprint)
    return {"ticket": issue}


def _incident_notification(state: OpsState) -> dict[str, dict[str, str]]:
    issue = state.get("ticket", {})
    if issue.get("created") is not True:
        return {
            "notification": {
                "status": "skipped_duplicate",
                "detail": "An open matching issue already exists; no repeat alert sent.",
            }
        }
    notification = send_teams_alert(
        f"Operations incident: {issue.get('title', 'Incident')}\n"
        f"GitHub issue #{issue.get('number')}: {issue.get('url')}"
    )
    return {"notification": notification}


def _finalize(state: OpsState) -> dict[str, object]:
    sections = []
    analysis = state.get("analysis", "")
    ticket = state.get("ticket", {})
    direct_answer = state.get("direct_answer", "")
    if direct_answer:
        sections.append(direct_answer)
    if analysis:
        sections.append(analysis)
    if ticket:
        action = "Created" if ticket.get("created") else "Existing open issue"
        sections.append(
            f"{action} GitHub issue #{ticket['number']}: "
            f"{ticket['title']}\n{ticket['url']}"
        )
    notification = state.get("notification", {})
    if notification.get("status") == "sent":
        sections.append("Microsoft Teams alert sent.")
    elif notification.get("status") == "skipped_duplicate":
        sections.append(notification["detail"])
    elif notification:
        sections.append(
            "Teams notification "
            f"{notification['status']}: {notification['detail']}"
        )
    response = "\n\n".join(sections)
    if not response:
        raise RuntimeError("The workflow completed without producing a response.")
    return {"response": response, "messages": [AIMessage(content=response)]}


def build_graph(checkpointer=None):
    """Compile the workflow, using the supplied checkpointer if provided."""
    builder = StateGraph(OpsState)
    builder.add_node("supervisor", supervisor_node)
    builder.add_node("analyzer", analyzer_node)
    builder.add_node("ticket_creator", ticket_creator_node)
    builder.add_node("automatic_issue", _automatic_issue)
    builder.add_node("incident_notification", _incident_notification)
    builder.add_node("finalize", _finalize)

    builder.add_edge(START, "supervisor")
    builder.add_conditional_edges(
        "supervisor",
        _supervisor_route,
        {
            "analyze": "analyzer",
            "create_ticket": "ticket_creator",
            "analyze_and_ticket": "analyzer",
            "respond": "finalize",
        },
    )
    builder.add_conditional_edges(
        "analyzer",
        _after_analysis,
        {
            "ticket_creator": "ticket_creator",
            "automatic_issue": "automatic_issue",
            "finalize": "finalize",
        },
    )
    builder.add_conditional_edges(
        "ticket_creator",
        _after_ticket_creation,
        {"incident_notification": "incident_notification", "finalize": "finalize"},
    )
    builder.add_edge("automatic_issue", "incident_notification")
    builder.add_edge("incident_notification", "finalize")
    builder.add_edge("finalize", END)
    return builder.compile(checkpointer=checkpointer)


graph = build_graph()
