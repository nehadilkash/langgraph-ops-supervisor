"""Microsoft Teams webhook notifications."""

import json
import os
import urllib.error
import urllib.request
from urllib.parse import urlsplit


def send_teams_alert(message: str) -> dict[str, str]:
    """Post an Adaptive Card to a configured Microsoft Teams workflow webhook."""
    webhook_url = os.getenv("TEAMS_WEBHOOK_URL", "").strip()
    if not webhook_url:
        return {
            "status": "not_configured",
            "detail": "Set TEAMS_WEBHOOK_URL to enable Microsoft Teams alerts.",
        }
    parsed = urlsplit(webhook_url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise ValueError("TEAMS_WEBHOOK_URL must be an HTTPS webhook URL.")
    payload = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.4",
                    "body": [{"type": "TextBlock", "text": message, "wrap": True}],
                },
            }
        ],
    }
    request = urllib.request.Request(
        webhook_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            if not 200 <= response.status < 300:
                return {
                    "status": "failed",
                    "detail": f"Teams webhook returned HTTP {response.status}.",
                }
    except urllib.error.HTTPError as error:
        return {
            "status": "failed",
            "detail": f"Teams webhook returned HTTP {error.code}.",
        }
    except urllib.error.URLError:
        return {
            "status": "failed",
            "detail": "Could not connect to the Teams webhook.",
        }
    return {"status": "sent", "detail": "Teams alert delivered."}
