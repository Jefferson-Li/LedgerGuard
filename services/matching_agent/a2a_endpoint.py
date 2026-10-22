"""Advertise the matching agent at the URL other services can reach.

``to_a2a`` always includes the port in the agent-card URL. For Cloud Run the
public URL usually has no explicit port, so https URLs are advertised on 443.
Confirm the card URL on the first deploy; some clients are picky about ``:443``.
"""

from __future__ import annotations

import os
from urllib.parse import urlsplit


def agent_card_url(base: str) -> str:
    cleaned = base.strip().rstrip("/")
    suffix = "/.well-known/agent-card.json"
    if cleaned.endswith("agent-card.json"):
        return cleaned
    return cleaned + suffix


def advertised_endpoint(agent_url: str | None, listen_port: int) -> tuple[str, str, int]:
    """Return protocol, host, and port for the generated agent card."""
    raw = (agent_url or "").strip()
    if not raw:
        return "http", os.environ.get("AGENT_HOST", "localhost"), listen_port
    parsed = urlsplit(raw)
    scheme = parsed.scheme or "http"
    host = parsed.hostname or "localhost"
    if parsed.port:
        port = parsed.port
    elif scheme == "https":
        port = 443
    else:
        port = listen_port
    return scheme, host, port
