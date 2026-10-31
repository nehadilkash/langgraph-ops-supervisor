"""GitHub Issues integration with deterministic duplicate detection."""

import hashlib
import json
import os
import re
from typing import Optional
import urllib.error
import urllib.parse
import urllib.request

from langchain_core.tools import tool

DEFAULT_REPOSITORY = "nehadilkash/langgraph-ops-supervisor"
REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
GITHUB_API = "https://api.github.com"


def _repository() -> str:
    repository = os.getenv("GITHUB_REPOSITORY", DEFAULT_REPOSITORY).strip()
    if not REPOSITORY_PATTERN.fullmatch(repository):
        raise ValueError(
            "GITHUB_REPOSITORY must have the form owner/repository."
        )
    return repository


def _github_request(
    path: str,
    payload: Optional[dict[str, str]] = None,
) -> object:
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if not token:
        raise ValueError(
            "Set GITHUB_TOKEN with Issues read/write access before creating issues."
        )
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        f"{GITHUB_API}{path}",
        data=data,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "langgraph-ops-supervisor",
            **({"Content-Type": "application/json"} if data is not None else {}),
        },
        method="POST" if data is not None else "GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        response_body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"GitHub API request failed with HTTP {error.code}: "
            f"{response_body[:500]}"
        ) from error
    except urllib.error.URLError as error:
        raise RuntimeError("Could not connect to the GitHub API.") from error


def create_issue(
    title: str,
    body: str,
    fingerprint: Optional[str] = None,
) -> dict[str, object]:
    """Find an existing open issue with this fingerprint, or create one."""
    repository = _repository()
    fingerprint = fingerprint or hashlib.sha256(
        f"{title}\n{body}".encode("utf-8")
    ).hexdigest()
    marker = f"ops-supervisor-fingerprint-{fingerprint}"
    query = urllib.parse.urlencode(
        {"q": f"repo:{repository} is:issue is:open {marker} in:body"}
    )
    matches = _github_request(f"/search/issues?{query}")
    if not isinstance(matches, dict) or not isinstance(matches.get("items"), list):
        raise RuntimeError("GitHub returned an invalid issue-search response.")
    if matches["items"]:
        existing = matches["items"][0]
        return {
            "number": str(existing["number"]),
            "title": str(existing["title"]),
            "url": str(existing["html_url"]),
            "created": False,
        }

    created_issue = _github_request(
        f"/repos/{repository}/issues",
        {
            "title": title,
            "body": f"{body.rstrip()}\n\n<!-- {marker} -->",
        },
    )
    if not isinstance(created_issue, dict) or not all(
        key in created_issue for key in ("number", "title", "html_url")
    ):
        raise RuntimeError("GitHub returned an invalid issue-creation response.")
    return {
        "number": str(created_issue["number"]),
        "title": str(created_issue["title"]),
        "url": str(created_issue["html_url"]),
        "created": True,
    }


@tool
def create_github_issue(title: str, body: str) -> str:
    """Create a GitHub issue, reusing an existing matching open issue if found."""
    return json.dumps(create_issue(title, body))
