"""Mock log parsing and database status tools."""

import json
import os
import re
import socket
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from langchain_core.tools import tool

ERROR_PATTERN = re.compile(r"\b(error|fatal|exception|critical)\b", re.IGNORECASE)
WARNING_PATTERN = re.compile(r"\b(warn|warning)\b", re.IGNORECASE)


def parse_log_lines(log_text: str) -> dict[str, object]:
    """Extract error and warning lines from plain-text application logs."""
    lines = [line.strip() for line in log_text.splitlines() if line.strip()]
    errors = [line for line in lines if ERROR_PATTERN.search(line)]
    warnings = [
        line
        for line in lines
        if WARNING_PATTERN.search(line) and not ERROR_PATTERN.search(line)
    ]
    return {
        "line_count": len(lines),
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors,
        "warnings": warnings,
        "severity": "high" if errors else "medium" if warnings else "low",
    }


@tool
def analyze_logs(log_text: str) -> str:
    """Parse application log text and return counts and matching error lines."""
    return json.dumps(parse_log_lines(log_text))


@tool
def get_database_status() -> str:
    """Fetch the mock database health status."""
    return json.dumps(
        {
            "service": "mock-primary-database",
            "status": "healthy",
            "latency_ms": 12,
            "active_connections": 8,
            "checked_by": "mock status API",
        }
    )


def check_configured_endpoints() -> list[dict[str, object]]:
    """Check only the HTTP(S) endpoints explicitly configured by the operator."""
    configured_urls = [
        item.strip()
        for item in os.getenv("HEALTHCHECK_URLS", "").split(",")
        if item.strip()
    ]
    results = []
    for url in configured_urls:
        parsed = urlsplit(url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            raise ValueError(
                "Each HEALTHCHECK_URLS entry must be a valid HTTP(S) URL without "
                "embedded credentials."
            )
        endpoint = f"{parsed.scheme}://{parsed.hostname}"
        if parsed.port is not None:
            endpoint = f"{endpoint}:{parsed.port}"
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "langgraph-ops-supervisor/1.0"},
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                status_code = response.status
            results.append(
                {
                    "endpoint": endpoint,
                    "status": "healthy" if 200 <= status_code < 300 else "unhealthy",
                    "http_status": status_code,
                }
            )
        except urllib.error.HTTPError as error:
            results.append(
                {
                    "endpoint": endpoint,
                    "status": "unhealthy",
                    "http_status": error.code,
                }
            )
        except (urllib.error.URLError, TimeoutError, socket.timeout):
            results.append(
                {
                    "endpoint": endpoint,
                    "status": "unhealthy",
                    "detail": "Connection failed or timed out.",
                }
            )
    return results

