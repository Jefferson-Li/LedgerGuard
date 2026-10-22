"""Cloud Run ID-token helpers shared by the agent services.

Cloud Run rejects unauthenticated calls when a service does not grant
``allUsers`` the invoker role. Callers send a Google-signed ID token whose
audience is the target service origin. Tokens are fetched at request time so
they are not baked into images or source.
"""

from __future__ import annotations

from urllib.parse import urlsplit


def origin_of(url: str) -> str:
    """Return ``scheme://host[:port]`` for use as an ID-token audience."""
    parsed = urlsplit(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"Cannot derive an ID token audience from {url!r}")
    return f"{parsed.scheme}://{parsed.netloc}"


def id_token_headers(audience: str) -> dict[str, str]:
    """Fetch an ID token with Application Default Credentials.

    Importing the Google auth libraries is deferred so unit tests that only
    parse URLs do not need those packages, and so a missing credential fails
    the request instead of starting the process.
    """
    from google.auth.transport.requests import Request
    from google.oauth2 import id_token

    token = id_token.fetch_id_token(Request(), audience)
    return {"Authorization": f"Bearer {token}"}
