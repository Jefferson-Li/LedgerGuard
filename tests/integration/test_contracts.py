"""Live contract checks. Skipped unless LEDGERGUARD_INTEGRATION=1.

In-process tool names are covered by the service tests. These checks hit the
compose network and do not call Gemini.
"""

from __future__ import annotations

import json
import os
import urllib.request

import pytest

pytestmark = pytest.mark.integration


def _enabled() -> bool:
    return os.environ.get("LEDGERGUARD_INTEGRATION") == "1"


def _get(url: str) -> tuple[int, str]:
    with urllib.request.urlopen(url, timeout=10) as response:
        return response.status, response.read().decode("utf-8")


@pytest.mark.skipif(not _enabled(), reason="Set LEDGERGUARD_INTEGRATION=1 with docker compose up")
def test_mcp_health_endpoints():
    for url in (
        os.environ.get("ERP_HEALTH_URL", "http://127.0.0.1:8090/health"),
        os.environ.get("INVOICE_HEALTH_URL", "http://127.0.0.1:8091/health"),
    ):
        status, body = _get(url)
        assert status == 200
        assert json.loads(body)["status"] == "healthy"


@pytest.mark.skipif(not _enabled(), reason="Set LEDGERGUARD_INTEGRATION=1 with docker compose up")
def test_matching_agent_card():
    url = os.environ.get(
        "MATCHING_CARD_URL",
        "http://127.0.0.1:8081/.well-known/agent-card.json",
    )
    status, body = _get(url)
    assert status == 200
    card = json.loads(body)
    assert card["name"] == "matching_agent"
    urls = [card["url"]] if isinstance(card.get("url"), str) else []
    urls.extend(
        interface["url"]
        for interface in card.get("supportedInterfaces") or []
        if isinstance(interface, dict) and isinstance(interface.get("url"), str)
    )
    assert urls
