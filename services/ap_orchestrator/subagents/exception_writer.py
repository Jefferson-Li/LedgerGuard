"""Format an exception packet from a reconcile result.

The formatter copies fields. It does not compute money, and it drops payment-detail
keys if a caller accidentally includes them.
"""

from __future__ import annotations

import json
import os
from typing import Any

from redact import redact_sensitive

INSTRUCTION = """You format exception packets for an accounts payable clerk.
Call format_exception_packet with the reconcile JSON and return its text unchanged.
Do not add amounts, bank details, or payment approvals.
"""


def format_exception_packet(reconcile_json: str) -> str:
    """Render a clerk-facing packet from reconcile JSON. Do not invent amounts.

    Args:
        reconcile_json: JSON object produced by reconcile_invoice_payload.
    """
    parsed: Any = json.loads(reconcile_json)
    data = redact_sensitive(parsed)
    invoice_id = data.get("invoice_id", "(unknown)")
    status = data.get("status", "unknown")
    codes = data.get("exception_codes") or []
    details = data.get("details") or []
    lines = [f"Invoice {invoice_id}", f"Status: {status}"]
    if codes:
        lines.append("Exception codes: " + ", ".join(str(code) for code in codes))
    if details:
        lines.append("Details:")
        lines.extend(f"- {detail}" for detail in details)
    if status == "quarantined":
        lines.append("Do not pay this invoice. The document body was withheld.")
    elif status == "matched":
        lines.append("No exception to route. Amounts above, if any, come from the reconcile tool.")
    else:
        lines.append(
            "Route this exception to a person. Do not approve payment from this packet alone."
        )
    return "\n".join(lines)


def build_exception_writer():
    from google.adk.agents import LlmAgent

    return LlmAgent(
        name="exception_writer",
        model=os.environ.get("LEDGERGUARD_MODEL", "gemini-2.5-flash"),
        description="Formats invoice exception packets for a person to review.",
        instruction=INSTRUCTION,
        tools=[format_exception_packet],
    )
