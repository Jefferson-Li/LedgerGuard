import pytest

from gcp_auth import origin_of
from matching_agent.a2a_endpoint import advertised_endpoint, agent_card_url


def test_agent_card_url():
    assert agent_card_url("http://matching-agent:8081") == (
        "http://matching-agent:8081/.well-known/agent-card.json"
    )
    assert agent_card_url("http://localhost:8081/.well-known/agent-card.json").endswith(
        "agent-card.json"
    )


def test_advertised_endpoint_uses_443_for_https_without_a_port():
    assert advertised_endpoint("https://matching-abc.a.run.app", 8080) == (
        "https",
        "matching-abc.a.run.app",
        443,
    )
    assert advertised_endpoint("http://matching-agent:8081", 8080) == (
        "http",
        "matching-agent",
        8081,
    )
    assert advertised_endpoint(None, 8081)[2] == 8081


def test_origin_of_drops_the_path():
    assert origin_of("https://erp-abc.a.run.app/mcp") == "https://erp-abc.a.run.app"
    with pytest.raises(ValueError):
        origin_of("not a url")
