"""Import the ADK entrypoints without calling Gemini or Model Armor."""

import pytest

pytest.importorskip("google.adk")


def test_matching_agent_exports_an_a2a_app():
    from matching_agent.agent import a2a_app, root_agent

    assert root_agent.name == "matching_agent"
    assert a2a_app is not None


def test_orchestrator_exports_an_app():
    from ap_orchestrator.agent import app, root_agent

    assert root_agent.name == "ap_orchestrator"
    assert app.name == "ap_orchestrator"
