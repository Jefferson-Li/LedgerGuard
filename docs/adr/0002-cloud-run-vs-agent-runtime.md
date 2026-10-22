# ADR 0002: Cloud Run, not Agent Runtime

## Status

Accepted for this scaffold. Agent Runtime is not wired.

## Context

ADK can run on Cloud Run, on GKE, or on Agent Runtime. The orchestrator is an `adk web` app plus a remote A2A agent and two MCP servers. Those MCP servers are ordinary HTTP services with their own service accounts. The deploy workflow needs a tagged revision with no traffic, a smoke test, and a traffic shift. That flow is a Cloud Run feature.

Agent Runtime would change how the orchestrator is deployed and how its URL and identity are managed. It would not remove the need for the MCP services or for paragraph screening.

## Decision

Keep all four services on Cloud Run. Leave Agent Runtime as a comparison, not a module.

## Consequences

- One deploy path covers agents and tools.
- Operators use Cloud Run revisions, IAM invoker bindings, and ID tokens.
- Moving only the orchestrator later means revisiting `MATCHING_AGENT_URL`, the agent card port (`:443`), and whether Agent Runtime can perform the same no-traffic rollout. That work is not started.
