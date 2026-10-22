"""Stand-in screeners for the offline red-team runner. Not Model Armor."""

from __future__ import annotations

from invoice_mcp.armor import ScreeningVerdict


class MarkerScreener:
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


class DilutionStandIn:
    def __init__(self, marker: str, word_limit: int) -> None:
        self.marker = marker.lower()
        self.word_limit = word_limit

    def screen_user_prompt(self, text: str) -> ScreeningVerdict:
        if self.marker not in text.lower():
            return ScreeningVerdict(match_state="NO_MATCH_FOUND", invocation_result="SUCCESS")
        if len(text.split()) > self.word_limit:
            return ScreeningVerdict(match_state="NO_MATCH_FOUND", invocation_result="SUCCESS")
        return ScreeningVerdict(
            match_state="MATCH_FOUND",
            invocation_result="SUCCESS",
            filters=("pi_and_jailbreak",),
        )
