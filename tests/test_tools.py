"""Unit tests for local mock tools."""

import json
import os
import unittest
from unittest.mock import MagicMock, Mock, patch

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from src.graph import build_graph
from src.llm import get_chat_model
from src.tools.github_tools import create_issue
from src.tools.jira_tools import create_jira_ticket
from src.tools.log_tools import check_configured_endpoints, parse_log_lines
from src.tools.teams_tools import send_teams_alert


class ChatModelConfigTests(unittest.TestCase):
    def test_defaults_to_local_ollama_without_an_api_key(self) -> None:
        model = Mock()
        with (
            patch("src.llm.load_dotenv"),
            patch.dict(os.environ, {}, clear=True),
            patch("src.llm.ChatOpenAI", return_value=model) as chat_openai,
        ):
            result = get_chat_model()

        self.assertIs(result, model)
        chat_openai.assert_called_once_with(
            model="llama3.2",
            base_url="http://localhost:11434/v1",
            api_key="ollama",
            temperature=0,
        )

    def test_openai_provider_requires_a_real_api_key(self) -> None:
        with (
            patch("src.llm.load_dotenv"),
            patch.dict(
                os.environ,
                {"LLM_PROVIDER": "openai", "OPENAI_API_KEY": "replace-me"},
                clear=True,
            ),
        ):
            with self.assertRaisesRegex(ValueError, "requires a valid OPENAI_API_KEY"):
                get_chat_model()

    def test_openai_provider_uses_configured_model_and_key(self) -> None:
        with (
            patch("src.llm.load_dotenv"),
            patch.dict(
                os.environ,
                {
                    "LLM_PROVIDER": "openai",
                    "OPENAI_API_KEY": "test-key",
                    "OPENAI_MODEL": "gpt-test",
                },
                clear=True,
            ),
            patch("src.llm.ChatOpenAI") as chat_openai,
        ):
            get_chat_model()

        chat_openai.assert_called_once_with(
            model="gpt-test",
            api_key="test-key",
            temperature=0,
        )

    def test_rejects_unknown_provider(self) -> None:
        with (
            patch("src.llm.load_dotenv"),
            patch.dict(os.environ, {"LLM_PROVIDER": "other"}, clear=True),
        ):
            with self.assertRaisesRegex(ValueError, "choose 'ollama' or 'openai'"):
                get_chat_model()


class LogToolTests(unittest.TestCase):
    def test_parse_log_lines_counts_errors_and_warnings(self) -> None:
        result = parse_log_lines(
            "INFO startup complete\n"
            "WARN retrying request\n"
            "ERROR database timeout\n"
            "exception during shutdown"
        )

        self.assertEqual(result["line_count"], 4)
        self.assertEqual(result["error_count"], 2)
        self.assertEqual(result["warning_count"], 1)
        self.assertEqual(result["severity"], "high")

    def test_parse_empty_logs(self) -> None:
        self.assertEqual(
            parse_log_lines(" \n"),
            {
                "line_count": 0,
                "error_count": 0,
                "warning_count": 0,
                "errors": [],
                "warnings": [],
                "severity": "low",
            },
        )


class JiraToolTests(unittest.TestCase):
    def test_mock_ticket_has_key_and_url(self) -> None:
        result = json.loads(
            create_jira_ticket.invoke(
                {"summary": "Database timeout", "description": "Connection timed out"}
            )
        )

        self.assertRegex(result["key"], r"^OPS-[0-9A-F]{6}$")
        self.assertEqual(
            result["url"], f"https://jira.example.com/browse/{result['key']}"
        )
        self.assertEqual(result["summary"], "Database timeout")


class GraphStateTests(unittest.TestCase):
    def test_conversation_messages_persist_across_invocations(self) -> None:
        def respond(_state):
            return {
                "route": "respond",
                "direct_answer": "Acknowledged.",
                "analysis": "",
                "ticket": {},
                "response": "",
            }

        with patch("src.graph.supervisor_node", respond):
            graph = build_graph(checkpointer=MemorySaver())
        config = {"configurable": {"thread_id": "state-test"}}

        graph.invoke({"messages": [HumanMessage(content="First turn")]}, config=config)
        result = graph.invoke(
            {"messages": [HumanMessage(content="Second turn")]},
            config=config,
        )

        self.assertEqual(len(result["messages"]), 4)
        self.assertEqual(result["messages"][-2].content, "Second turn")
        self.assertEqual(result["response"], "Acknowledged.")

    def test_detected_incident_creates_issue_and_sends_teams_alert(self) -> None:
        issue = {
            "number": "42",
            "title": "Automated incident",
            "url": "https://github.com/owner/repo/issues/42",
            "created": True,
        }
        with (
            patch(
                "src.graph.supervisor_node",
                return_value={
                    "route": "analyze",
                    "analysis": "",
                    "log_findings": {},
                    "health_checks": [],
                    "ticket": {},
                    "notification": {},
                },
            ),
            patch(
                "src.graph.analyzer_node",
                return_value={
                    "analysis": "Two database errors detected.",
                    "log_findings": {
                        "errors": ["ERROR database timeout"],
                        "error_count": 1,
                        "severity": "high",
                    },
                    "health_checks": [],
                },
            ),
            patch("src.graph.create_issue", return_value=issue) as create_issue,
            patch(
                "src.graph.send_teams_alert",
                return_value={"status": "sent", "detail": "Alert delivered."},
            ) as send_alert,
        ):
            graph = build_graph()
            result = graph.invoke(
                {"messages": [HumanMessage(content="ERROR database timeout")]},
                config={"configurable": {"thread_id": "incident-test"}},
            )

        create_issue.assert_called_once()
        send_alert.assert_called_once()
        self.assertIn("Created GitHub issue #42", result["response"])

    def test_studio_graph_has_visible_agent_and_action_nodes(self) -> None:
        from src.graph import graph

        node_names = set(graph.get_graph().nodes)
        self.assertTrue(
            {
                "supervisor",
                "analyzer",
                "ticket_creator",
                "automatic_issue",
                "incident_notification",
            }.issubset(node_names)
        )


class ServiceIntegrationTests(unittest.TestCase):
    def test_health_checks_are_empty_when_no_urls_are_configured(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(check_configured_endpoints(), [])

    def test_health_check_rejects_non_http_urls(self) -> None:
        with (
            patch.dict(os.environ, {"HEALTHCHECK_URLS": "file:///etc/passwd"}),
            self.assertRaisesRegex(ValueError, "HTTP\\(S\\) URL"),
        ):
            check_configured_endpoints()

    def test_health_check_reports_http_status(self) -> None:
        response = MagicMock()
        response.status = 503
        response.__enter__.return_value = response
        with patch.dict(
            os.environ,
            {"HEALTHCHECK_URLS": "https://service.example/health?token=hidden"},
            clear=True,
        ), patch("src.tools.log_tools.urllib.request.urlopen", return_value=response):
            results = check_configured_endpoints()

        self.assertEqual(
            results,
            [
                {
                    "endpoint": "https://service.example",
                    "status": "unhealthy",
                    "http_status": 503,
                }
            ],
        )

    def test_teams_alert_reports_missing_webhook(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            result = send_teams_alert("incident")
        self.assertEqual(result["status"], "not_configured")

    def test_teams_alert_posts_an_adaptive_card(self) -> None:
        response = MagicMock()
        response.status = 202
        response.__enter__.return_value = response
        with patch.dict(
            os.environ,
            {"TEAMS_WEBHOOK_URL": "https://teams.example/webhook"},
            clear=True,
        ), patch(
            "src.tools.teams_tools.urllib.request.urlopen",
            return_value=response,
        ) as urlopen:
            result = send_teams_alert("Incident created")

        self.assertEqual(result["status"], "sent")
        request = urlopen.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(
            payload["attachments"][0]["contentType"],
            "application/vnd.microsoft.card.adaptive",
        )

    def test_github_issue_creation_uses_duplicate_search_before_create(self) -> None:
        with patch.dict(
            os.environ,
            {"GITHUB_TOKEN": "test-token", "GITHUB_REPOSITORY": "owner/repo"},
        ), patch(
            "src.tools.github_tools._github_request",
            side_effect=[
                {"items": []},
                {
                    "number": 42,
                    "title": "Incident",
                    "html_url": "https://github.com/owner/repo/issues/42",
                },
            ],
        ) as github_request:
            result = create_issue("Incident", "Observed failure", "abc123")

        self.assertTrue(result["created"])
        self.assertEqual(result["number"], "42")
        self.assertEqual(github_request.call_count, 2)

    def test_github_issue_creation_reuses_open_duplicate(self) -> None:
        with patch.dict(
            os.environ,
            {"GITHUB_TOKEN": "test-token", "GITHUB_REPOSITORY": "owner/repo"},
        ), patch(
            "src.tools.github_tools._github_request",
            return_value={
                "items": [
                    {
                        "number": 42,
                        "title": "Incident",
                        "html_url": "https://github.com/owner/repo/issues/42",
                    }
                ]
            },
        ) as github_request:
            result = create_issue("Incident", "Observed failure", "abc123")

        self.assertFalse(result["created"])
        self.assertEqual(result["number"], "42")
        github_request.assert_called_once()


if __name__ == "__main__":
    unittest.main()
