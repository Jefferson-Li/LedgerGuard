"""Strip payment details before a record leaves a service.

Two layers run on every call to ``redact_sensitive``. The first drops the keys
``bank``, ``bsb``, ``account_number``, ``account_name``, and ``bank_account``.
The second masks bank-like values inside every remaining string, including a
supplier or purchase-order ``notes`` field. A match is replaced with
``[REDACTED:BANK]``.

The value scan is deterministic and local. It does not call Sensitive Data
Protection. The inspect template declared in Terraform is attached to the
Model Armor response template only, and this module does not invoke it.

Known limits:

- Only strings are scanned. A JSON number is left as it is.
- An unlabelled BSB counts only when an account number is within
  ``_NEAR_CHARS`` of it. ``BSB 062-000`` and ``Account 12345678`` are masked
  on their own because of the label.
- A compact 6-digit BSB is paired only with a separate 7-10 digit account.
  Two bare 6-digit numbers side by side are not treated as a pair. A BSB
  written with a hyphen or a space can pair with a 6-10 digit account.
- Left in place when the scanner recognizes the shape: an 11-digit ABN and
  the grouped form ``XX XXX XXX XXX``, ``INV-``, ``PO-``, and ``DD-`` tokens,
  amounts with a cents suffix, a ``$`` sign, or an ``AUD`` prefix, ISO dates,
  ``dd/mm/yyyy`` dates, ``16 October 2026`` style dates, and common Australian
  mobile and landline spellings.
- An ABN or phone number with unusual spacing can still be masked. A
  whole-dollar amount of 6-10 digits written next to a BSB can be masked.
- An unlabelled account number with no BSB nearby is left in place.
- IBAN detection checks the shape (2 letters, 2 digits, then 11-30 more
  alphanumeric characters, spaces allowed). It does not check the IBAN checksum.
- Structured ``bank`` objects are removed by the key layer and are not this
  scan. ``bank_details_changed`` still compares those fields before they are
  dropped, and it returns a boolean rather than the number.
"""

from __future__ import annotations

import re
from typing import Any

SENSITIVE_KEYS = frozenset({"bank", "bsb", "account_number", "account_name", "bank_account"})
BANK_TOKEN = "[REDACTED:BANK]"

# Gap allowed between an unlabelled BSB and an account number, in characters.
_NEAR_CHARS = 40

_MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"

# Spans the value scan must not treat as a bank number.
_PROTECTED = (
    re.compile(r"(?<!\d)\d{11}(?!\d)"),
    re.compile(r"(?<!\d)\d{2}\s\d{3}\s\d{3}\s\d{3}(?!\d)"),
    re.compile(r"\d{4}-\d{2}-\d{2}"),
    re.compile(r"(?<!\d)\d{1,2}/\d{1,2}/\d{2,4}(?!\d)"),
    re.compile(rf"(?i)(?<!\d)\d{{1,2}}\s+(?:{_MONTHS})\s+\d{{4}}\b"),
    re.compile(r"(?i)(?:AUD|A\$|\$)\s?\d{1,3}(?:,\d{3})*(?:\.\d{2})?"),
    re.compile(r"(?<!\d)\d+\.\d{2}(?!\d)"),
    re.compile(r"(?i)\b(?:INV|PO|DD)-\d+\b"),
    re.compile(r"(?<!\d)(?:\+?61[\s-]?|0)4\d{2}[\s-]?\d{3}[\s-]?\d{3}(?!\d)"),
    re.compile(r"(?<!\d)(?:\+?61[\s-]?|0)[2378][\s-]?\d{4}[\s-]?\d{4}(?!\d)"),
    re.compile(r"\(\s?0[2378]\s?\)[\s-]?\d{4}[\s-]?\d{4}"),
)

# Lookbehinds are fixed-width, which is what the ``re`` engine allows.
_NOT_DOC_NUMBER = r"(?<!INV-)(?<!inv-)(?<!PO-)(?<!po-)(?<!DD-)(?<!dd-)"
_ACCOUNT = re.compile(_NOT_DOC_NUMBER + r"(?<!\d)\d{6,10}(?!\.\d)(?!\d)")
_SEPARATED_BSB = re.compile(r"(?<!\d)\d{3}[-\s]\d{3}(?!\d)")
_COMPACT_BSB = re.compile(r"(?<!\d)\d{6}(?!\d)")
_LABELLED_BSB = re.compile(
    r"(?i)\b(?:bsb|bank\s+state\s+branch)\b(?:\s+number)?\s*[:#-]?\s*"
    r"((?<!\d)\d{3}[-\s]?\d{3}(?!\d))"
)
_LABELLED_ACCOUNT = re.compile(
    r"(?i)\b(?:a/c|acct|account)(?:\s+(?:no\.?|number|#))?\s*[:#-]?\s*"
    r"(" + _NOT_DOC_NUMBER + r"(?<!\d)\d{6,10}(?!\.\d)(?!\d))"
)
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]){11,30}\b")


def _overlaps(left: tuple[int, int], right: tuple[int, int]) -> bool:
    return left[0] < right[1] and right[0] < left[1]


def _overlaps_any(span: tuple[int, int], others: list[tuple[int, int]]) -> bool:
    return any(_overlaps(span, other) for other in others)


def _near(left: tuple[int, int], right: tuple[int, int]) -> bool:
    if _overlaps(left, right):
        return False
    gap = left[0] - right[1] if left[0] >= right[1] else right[0] - left[1]
    return gap <= _NEAR_CHARS


def _protected_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for pattern in _PROTECTED:
        spans.extend(match.span() for match in pattern.finditer(text))
    return spans


def _keep(span: tuple[int, int], protected: list[tuple[int, int]]) -> bool:
    return not _overlaps_any(span, protected)


def _iban_spans(text: str, protected: list[tuple[int, int]]) -> list[tuple[int, int]]:
    found: list[tuple[int, int]] = []
    for match in _IBAN.finditer(text):
        body = re.sub(r"\s", "", match.group(0))
        if not 15 <= len(body) <= 34:
            continue
        span = match.span()
        if _keep(span, protected):
            found.append(span)
    return found


def _pair_spans(text: str, protected: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Unlabelled BSB next to an account number. Either order counts."""
    accounts = [match.span() for match in _ACCOUNT.finditer(text) if _keep(match.span(), protected)]
    separated = [
        match.span() for match in _SEPARATED_BSB.finditer(text) if _keep(match.span(), protected)
    ]
    compact = [
        match.span() for match in _COMPACT_BSB.finditer(text) if _keep(match.span(), protected)
    ]
    found: list[tuple[int, int]] = []
    for bsb in separated:
        for account in accounts:
            if _near(bsb, account):
                found.extend((bsb, account))
    for bsb in compact:
        for account in accounts:
            # A 6-digit token is both shapes. Pair it only with a longer account.
            if account[1] - account[0] < 7:
                continue
            if _overlaps(bsb, account):
                continue
            if _near(bsb, account):
                found.extend((bsb, account))
    return found


def bank_spans(text: str) -> list[tuple[int, int]]:
    """Character spans a value scan would mask. Empty means the string is unchanged."""
    protected = _protected_spans(text)
    spans: list[tuple[int, int]] = []
    for pattern in (_LABELLED_BSB, _LABELLED_ACCOUNT):
        for match in pattern.finditer(text):
            span = match.span()
            if _keep(span, protected):
                spans.append(span)
    spans.extend(_iban_spans(text, protected))
    spans.extend(_pair_spans(text, protected))
    return _merge(spans)


def _merge(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not spans:
        return []
    ordered = sorted(spans)
    merged = [ordered[0]]
    for start, end in ordered[1:]:
        prev_start, prev_end = merged[-1]
        if start <= prev_end:
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))
    return merged


def mask_bank_values(text: str) -> str:
    """Replace bank-like spans. Returns the same string when nothing matches."""
    spans = bank_spans(text)
    if not spans:
        return text
    pieces: list[str] = []
    pos = 0
    for start, end in spans:
        pieces.append(text[pos:start])
        pieces.append(BANK_TOKEN)
        pos = end
    pieces.append(text[pos:])
    return "".join(pieces)


def contains_bank_detail(value: Any) -> bool:
    """True when a string outside a stripped payment key matches a bank pattern.

    Keys in ``SENSITIVE_KEYS`` are ignored here. Those fields are the structured
    bank record, and the key layer removes them. This function is the free-text
    signal used by triage.
    """
    if isinstance(value, dict):
        return any(
            contains_bank_detail(item) for key, item in value.items() if key not in SENSITIVE_KEYS
        )
    if isinstance(value, list):
        return any(contains_bank_detail(item) for item in value)
    if isinstance(value, str):
        return bool(bank_spans(value))
    return False


def redact_sensitive(value: Any) -> Any:
    """Drop payment keys, then mask bank-like strings that remain."""
    if isinstance(value, dict):
        return {
            key: redact_sensitive(item) for key, item in value.items() if key not in SENSITIVE_KEYS
        }
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    if isinstance(value, str):
        return mask_bank_values(value)
    return value
