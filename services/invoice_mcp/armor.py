"""Paragraph-level Model Armor screening for untrusted invoice text.

ADK 2.12's ``ModelArmorPlugin`` can screen tool output when
``tool_output_template_name`` is set, but two gaps remain:

* The plugin runs in the agent process, after the tool result has already
  crossed the network from ``invoice-mcp``.
* It screens character windows of the serialised result (65,536 characters),
  not paragraphs. A short injection sitting inside a long, ordinary invoice
  can be diluted below the filter threshold. The Model Armor codelab showed
  the same effect when a whole document was screened at once.

This module screens each paragraph with ``sanitizeUserPrompt`` and, on any
match or any screening failure, withholds the whole document. Model Armor
itself does not block; the verdict is enforced here.

Inputs shorter than about three words are still sent. The prompt-injection
filter is documented to return ``NO_MATCH_FOUND`` for those, which is a
product limitation, not something this code special-cases.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from dataclasses import dataclass
from typing import Protocol

logger = logging.getLogger(__name__)

_TEMPLATE_RE = re.compile(r"^projects/[^/]+/locations/([^/]+)/templates/[^/]+$")
_ALLOW_VALUES = {"1", "true", "yes"}
_bypass_warned = False


@dataclass(frozen=True)
class ScreeningVerdict:
    match_state: str
    invocation_result: str
    filters: tuple[str, ...] = ()
    skipped: bool = False
    sanitized_text: str | None = None


@dataclass(frozen=True)
class ParagraphFinding:
    index: int
    sha256_12: str
    match_state: str
    invocation_result: str
    filters: tuple[str, ...]
    skipped: bool


@dataclass(frozen=True)
class ScreenResult:
    blocked: bool
    reason: str
    findings: tuple[ParagraphFinding, ...]
    paragraph_count: int

    def public_dict(self) -> dict[str, object]:
        return {
            "blocked": self.blocked,
            "reason": self.reason,
            "paragraph_count": self.paragraph_count,
            "findings": [
                {
                    "index": finding.index,
                    "sha256_12": finding.sha256_12,
                    "match_state": finding.match_state,
                    "invocation_result": finding.invocation_result,
                    "filters": list(finding.filters),
                    "skipped": finding.skipped,
                }
                for finding in self.findings
            ],
        }


class Screener(Protocol):
    def screen_user_prompt(self, text: str) -> ScreeningVerdict:
        """Return a verdict for one chunk of untrusted text."""


class AllowAllScreener:
    """Local-only bypass. Do not enable this on Cloud Run."""

    def screen_user_prompt(self, text: str) -> ScreeningVerdict:
        del text
        return ScreeningVerdict(match_state="NO_MATCH_FOUND", invocation_result="SUCCESS")


class UnavailableScreener:
    """Fail closed when no Model Armor template is configured."""

    def screen_user_prompt(self, text: str) -> ScreeningVerdict:
        del text
        return ScreeningVerdict(
            match_state="NO_MATCH_FOUND",
            invocation_result="FAILURE",
            skipped=True,
        )


def should_block(verdict: ScreeningVerdict, *, block_on_failure: bool = True) -> bool:
    if verdict.match_state == "MATCH_FOUND":
        return True
    failed = verdict.skipped or verdict.invocation_result in {"PARTIAL", "FAILURE"}
    return failed and block_on_failure


def split_paragraphs(text: str) -> list[str]:
    if not text or not text.strip():
        return []
    return [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]


def invoice_untrusted_text(invoice: dict) -> str:
    """Text plus any line description that is not already inside that text.

    This is the untrusted string ``invoice-mcp`` screens before a body is
    released. Callers outside that server import it from here so they do not
    have to load the FastMCP process.
    """
    chunks = [str(invoice.get("text") or "")]
    blob = chunks[0]
    for line in invoice.get("lines") or []:
        description = str(line.get("description") or "").strip()
        if description and description not in blob:
            chunks.append(description)
    return "\n\n".join(chunk for chunk in chunks if chunk.strip())


def _fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def _finding(index: int, text: str, verdict: ScreeningVerdict) -> ParagraphFinding:
    return ParagraphFinding(
        index=index,
        sha256_12=_fingerprint(text),
        match_state=verdict.match_state,
        invocation_result=verdict.invocation_result,
        filters=verdict.filters,
        skipped=verdict.skipped,
    )


def screen_paragraphs(
    text: str,
    screener: Screener,
    *,
    block_on_failure: bool = True,
) -> ScreenResult:
    """Screen each blank-line-separated paragraph. One hit quarantines the lot."""
    paragraphs = split_paragraphs(text)
    if not paragraphs:
        return ScreenResult(blocked=False, reason="allowed", findings=(), paragraph_count=0)

    findings: list[ParagraphFinding] = []
    matched = False
    for index, paragraph in enumerate(paragraphs):
        try:
            verdict = screener.screen_user_prompt(paragraph)
        except Exception:
            logger.exception("Model Armor paragraph screening failed index=%s", index)
            if not block_on_failure:
                raise
            findings.append(
                ParagraphFinding(
                    index=index,
                    sha256_12=_fingerprint(paragraph),
                    match_state="NO_MATCH_FOUND",
                    invocation_result="FAILURE",
                    filters=(),
                    skipped=True,
                )
            )
            return ScreenResult(
                blocked=True,
                reason="screening_failed",
                findings=tuple(findings),
                paragraph_count=len(paragraphs),
            )
        findings.append(_finding(index, paragraph, verdict))
        if verdict.skipped or verdict.invocation_result in {"PARTIAL", "FAILURE"}:
            if block_on_failure:
                return ScreenResult(
                    blocked=True,
                    reason="screening_failed",
                    findings=tuple(findings),
                    paragraph_count=len(paragraphs),
                )
        if verdict.match_state == "MATCH_FOUND":
            matched = True

    if matched:
        return ScreenResult(
            blocked=True,
            reason="match",
            findings=tuple(findings),
            paragraph_count=len(paragraphs),
        )
    return ScreenResult(
        blocked=False,
        reason="allowed",
        findings=tuple(findings),
        paragraph_count=len(paragraphs),
    )


def screen_whole_document(
    text: str, screener: Screener, *, block_on_failure: bool = True
) -> ScreenResult:
    """Screen the document as a single chunk. Used to show dilution, not in the request path."""
    collapsed = "\n".join(split_paragraphs(text))
    return screen_paragraphs(collapsed, screener, block_on_failure=block_on_failure)


def prompt_template_from_env() -> str:
    return (
        os.environ.get("MODEL_ARMOR_PROMPT_TEMPLATE")
        or os.environ.get("MODEL_ARMOR_TEMPLATE")
        or ""
    )


def screener_from_env() -> Screener:
    """Build the process-wide screener from the environment.

    A configured template uses Model Armor. ``MODEL_ARMOR_ALLOW_UNSCREENED`` is
    a local opt-in that lets every document through. Anything else fails closed.
    """
    global _bypass_warned
    template = prompt_template_from_env()
    if template:
        if not _TEMPLATE_RE.match(template):
            raise ValueError(
                "MODEL_ARMOR_PROMPT_TEMPLATE must look like "
                "projects/{project}/locations/{location}/templates/{template}"
            )
        return GoogleModelArmorScreener(template)
    allow = os.environ.get("MODEL_ARMOR_ALLOW_UNSCREENED", "").strip().lower()
    if allow in _ALLOW_VALUES:
        if not _bypass_warned:
            logger.warning(
                "MODEL_ARMOR_ALLOW_UNSCREENED is set; invoice text is not screened. "
                "Do not set this on Cloud Run."
            )
            _bypass_warned = True
        return AllowAllScreener()
    return UnavailableScreener()


def _enum_name(value: object) -> str:
    if value is None:
        return ""
    name = getattr(value, "name", None)
    if isinstance(name, str) and name:
        return name
    text = str(value)
    if "." in text:
        return text.rsplit(".", 1)[-1]
    return text


def verdict_from_sanitization(result: object) -> ScreeningVerdict:
    """Adapt a Model Armor ``SanitizationResult`` (or a similarly shaped fake)."""
    match_state = _enum_name(getattr(result, "filter_match_state", "")) or "NO_MATCH_FOUND"
    invocation = _enum_name(getattr(result, "invocation_result", "SUCCESS")) or "SUCCESS"
    filters: list[str] = []
    skipped = invocation in {"PARTIAL", "FAILURE"}
    filter_results = getattr(result, "filter_results", None) or {}
    for name, filter_result in dict(filter_results).items():
        matched, filter_skipped = _filter_flags(filter_result)
        if matched:
            filters.append(str(name))
        if filter_skipped:
            skipped = True
    return ScreeningVerdict(
        match_state=match_state,
        invocation_result=invocation,
        filters=tuple(filters),
        skipped=skipped,
    )


def _filter_flags(filter_result: object) -> tuple[bool, bool]:
    matched = _enum_name(getattr(filter_result, "match_state", "")) == "MATCH_FOUND"
    skipped = _enum_name(getattr(filter_result, "execution_state", "")) == "EXECUTION_SKIPPED"
    for child_name in (
        "rai_filter_result",
        "pi_and_jailbreak_filter_result",
        "sdp_filter_result",
        "malicious_uri_filter_result",
        "csam_filter_filter_result",
        "csam_filter_result",
    ):
        child = getattr(filter_result, child_name, None)
        if not child:
            continue
        child_matched, child_skipped = _filter_flags(child)
        matched = matched or child_matched
        skipped = skipped or child_skipped
    return matched, skipped


class GoogleModelArmorScreener:
    """Call ``sanitizeUserPrompt`` on the regional Model Armor endpoint.

    The global endpoint cannot sanitise. The location is taken from the
    template resource name, and the client uses
    ``modelarmor.{location}.rep.googleapis.com``.
    """

    def __init__(self, template_name: str) -> None:
        match = _TEMPLATE_RE.match(template_name)
        if not match:
            raise ValueError(f"Not a Model Armor template resource: {template_name}")
        self.template_name = template_name
        self.location = match.group(1)
        self._client = None

    def screen_user_prompt(self, text: str) -> ScreeningVerdict:
        client = self._client or self._build_client()
        self._client = client
        response = client.sanitize_user_prompt(
            request={
                "name": self.template_name,
                "user_prompt_data": {"text": text},
            }
        )
        return verdict_from_sanitization(response.sanitization_result)

    def _build_client(self):
        from google.api_core.client_options import ClientOptions
        from google.cloud import modelarmor_v1

        return modelarmor_v1.ModelArmorClient(
            transport="rest",
            client_options=ClientOptions(
                api_endpoint=f"modelarmor.{self.location}.rep.googleapis.com"
            ),
        )
