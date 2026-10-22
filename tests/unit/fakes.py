"""Small stand-ins for Model Armor. These are not the cloud filters."""

from __future__ import annotations

from invoice_mcp.armor import ScreeningVerdict


class StaticScreener:
    def __init__(self, verdict: ScreeningVerdict) -> None:
        self.verdict = verdict
        self.calls: list[str] = []

    def screen_user_prompt(self, text: str) -> ScreeningVerdict:
        self.calls.append(text)
        return self.verdict


class MarkerScreener:
    """Match only paragraphs that contain a marker. Other paragraphs pass."""

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
    """Model the codelab observation that a long document can hide a short injection.

    This is a local stand-in used to prove paragraph splitting. It is not Model Armor.
    """

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
