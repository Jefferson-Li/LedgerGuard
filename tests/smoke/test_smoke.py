"""Post-deploy checks against a tagged Cloud Run URL.

Health and, when requested, the agent card. A Gemini reconciliation call is not
part of this smoke test.
"""

from __future__ import annotations

import json
import os
import urllib.request

import pytest

pytestmark = pytest.mark.smoke


def _base(request: pytest.FixtureRequest) -> str:
    return request.config.getoption("--base-url") or os.environ.get("SMOKE_BASE_URL", "")


def _open(url: str) -> tuple[int, str]:
    request = urllib.request.Request(url)
    token = os.environ.get("SMOKE_ID_TOKEN", "")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.status, response.read().decode("utf-8")


def test_health(request: pytest.FixtureRequest):
    base = _base(request).rstrip("/")
    if not base:
        pytest.skip("Set SMOKE_BASE_URL or --base-url")
    status, body = _open(base + "/health")
    assert status == 200
    assert json.loads(body)["status"] == "healthy"


def test_agent_card_when_requested(request: pytest.FixtureRequest):
    if os.environ.get("SMOKE_EXPECT_CARD") != "1":
        pytest.skip("Set SMOKE_EXPECT_CARD=1 for the matching agent")
    base = _base(request).rstrip("/")
    if not base:
        pytest.skip("Set SMOKE_BASE_URL or --base-url")
    status, body = _open(base + "/.well-known/agent-card.json")
    assert status == 200
    card = json.loads(body)
    assert card.get("name")
    assert card.get("url")
