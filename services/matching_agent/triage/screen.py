"""Choose a screener.

Live Model Armor when a template is set. Otherwise fail closed, or use the
marker stand-in for the offline stub. The marker is the red-team phrase.
It is not Model Armor.
"""

from __future__ import annotations

from invoice_mcp.armor import (
    ScreeningVerdict,
    UnavailableScreener,
    prompt_template_from_env,
    screener_from_env,
)

# Same marker as security/stub_screeners.py and scripts/run_all_invoices.py.
INJECTION_MARKER = "Ignore all previous instructions"


class MarkerScreener:
    """Offline stand-in. A paragraph containing the marker is MATCH_FOUND."""

    def __init__(self, marker: str) -> None:
        self.marker = marker.lower()

    def screen_user_prompt(self, text: str) -> ScreeningVerdict:
        if self.marker in text.lower():
            return ScreeningVerdict(
                match_state="MATCH_FOUND",
                invocation_result="SUCCESS",
                filters=("pi_and_jailbreak",),
            )
        return ScreeningVerdict(match_state="NO_MATCH_FOUND", invocation_result="SUCCESS")


def screener_for_run(judge_mode: str):
    """Return ``(screener, name)``.

    A configured template uses Model Armor. A live Gemini judge with no
    template fails closed. The offline stub uses the marker stand-in so
    ``INV-1010`` still escalates without credentials.
    """
    if prompt_template_from_env():
        return screener_from_env(), "model-armor"
    if judge_mode == "gemini":
        return UnavailableScreener(), "fail-closed"
    return MarkerScreener(INJECTION_MARKER), "marker-stand-in"
