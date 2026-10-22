"""Facts the judge may see. Every amount in here is computed by code."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from invoice_mcp.armor import ScreenResult, invoice_untrusted_text
from matching_agent.rules import (
    D,
    gst_component,
    is_valid_abn,
    normalise_abn,
    price_within_tolerance,
    quantize,
    reconcile,
    tolerance_limit,
)
from redact import contains_bank_detail, mask_bank_values, redact_sensitive

_BANK_KEYS = ("bsb", "account_number", "account_name", "bank_account")


def money(value: Decimal) -> str:
    return f"{quantize(value):.2f}"


def data_dir() -> Path:
    env = os.environ.get("LEDGERGUARD_DATA_DIR")
    if env:
        return Path(env)
    for parent in Path(__file__).resolve().parents:
        if (parent / "data" / "invoices").is_dir():
            return parent / "data"
    raise FileNotFoundError(
        "Set LEDGERGUARD_DATA_DIR to the directory that contains seed/ and invoices/."
    )


def _bank_tuple(record: dict[str, Any] | None) -> tuple[str, str, str] | None:
    if not record:
        return None
    nested = record.get("bank") if isinstance(record.get("bank"), dict) else {}
    bsb = record.get("bsb") or nested.get("bsb") or ""
    account = record.get("account_number") or nested.get("account_number") or ""
    account = account or record.get("bank_account") or ""
    name = record.get("account_name") or nested.get("account_name") or ""
    if not any(str(part).strip() for part in (bsb, account, name)):
        return None
    return (str(bsb).strip(), str(account).strip(), str(name).strip())


def bank_details_changed(invoice: dict[str, Any], supplier: dict[str, Any] | None) -> bool:
    """True when the invoice states payment details that are not the supplier master.

    The comparison result is a boolean. Account numbers are not returned.
    """
    if invoice.get("bank_details_changed") is True:
        return True
    stated = _bank_tuple(invoice)
    if stated is None:
        return False
    return stated != _bank_tuple(supplier)


@dataclass
class InvoiceFacts:
    """Computed match facts. ``public_dict`` is what a model is allowed to read."""

    invoice_id: str
    match_status: str
    exception_codes: list[str]
    code_details: list[str]
    variance: str
    within_tolerance: bool
    supplier_known: bool
    abn_checksum_valid: bool
    abn_matches_master: bool
    bank_details_changed: bool
    bank_detail_in_free_text: bool
    model_armor_flagged: bool
    screening_failed: bool
    screening_reason: str
    text_sha256: str
    released_text: str | None
    payload: dict[str, Any]

    @property
    def hard_blocked(self) -> bool:
        return (
            self.model_armor_flagged
            or self.screening_failed
            or self.bank_details_changed
            or self.bank_detail_in_free_text
        )

    def public_dict(self) -> dict[str, Any]:
        """Facts for the model. No bank numbers and no unreleased invoice text."""
        body = {
            "invoice_id": self.invoice_id,
            "match_status": self.match_status,
            "exception_codes": list(self.exception_codes),
            "code_details": list(self.code_details),
            "variance": self.variance,
            "variance_computed_by": "code",
            "within_tolerance": self.within_tolerance,
            "supplier_known": self.supplier_known,
            "abn_checksum_valid": self.abn_checksum_valid,
            "abn_matches_master": self.abn_matches_master,
            "bank_details_changed": self.bank_details_changed,
            "bank_detail_in_free_text": self.bank_detail_in_free_text,
            "model_armor_flagged": self.model_armor_flagged,
            "screening_failed": self.screening_failed,
            "screening_reason": self.screening_reason,
            "text_sha256": self.text_sha256,
            "lines": self.payload["lines"],
            "gst": self.payload["gst"],
            "currency": self.payload["currency"],
        }
        redacted = redact_sensitive(body)
        for key in _BANK_KEYS:
            redacted.pop(key, None)
        return redacted

    def canonical_json(self) -> str:
        return json.dumps(self.public_dict(), sort_keys=True, separators=(",", ":"))


def _line_variances(
    invoice: dict[str, Any], purchase_order: dict[str, Any] | None
) -> list[dict[str, Any]]:
    po_lines = {}
    if purchase_order and not purchase_order.get("error"):
        po_lines = {str(line["sku"]): line for line in purchase_order.get("lines", [])}
    rows: list[dict[str, Any]] = []
    for line in invoice.get("lines") or []:
        sku = str(line.get("sku", ""))
        unit = D(line.get("unit_price_ex_gst", "0"))
        po_line = po_lines.get(sku)
        if po_line is None:
            rows.append(
                {
                    "sku": sku,
                    "invoice_unit_price": money(unit),
                    "po_unit_price": None,
                    "abs_delta": None,
                    "within_tolerance": False,
                    "tolerance_limit": None,
                    "comparable": False,
                }
            )
            continue
        po_unit = D(po_line["unit_price_ex_gst"])
        delta = abs(unit - po_unit)
        limit = tolerance_limit(po_unit)
        rows.append(
            {
                "sku": sku,
                "invoice_unit_price": money(unit),
                "po_unit_price": money(po_unit),
                "abs_delta": money(delta),
                "within_tolerance": price_within_tolerance(unit, po_unit),
                "tolerance_limit": money(limit),
                "comparable": True,
            }
        )
    return rows


def build_facts(
    invoice: dict[str, Any],
    purchase_order: dict[str, Any] | None,
    goods_receipts: list[dict[str, Any]] | dict[str, Any] | None,
    supplier: dict[str, Any] | None,
    screen: ScreenResult,
) -> InvoiceFacts:
    """Reconcile one invoice and attach the screening result. Does not call a model."""
    result = reconcile(invoice, purchase_order, goods_receipts, supplier)
    lines = _line_variances(invoice, purchase_order)
    comparable = [
        row["abs_delta"] for row in lines if row["comparable"] and row["abs_delta"] is not None
    ]
    if comparable:
        variance = max(comparable, key=D)
        within = all(row["within_tolerance"] for row in lines if row["comparable"])
    else:
        variance = "0.00"
        within = not result["exception_codes"]
    header_ex = D(invoice.get("subtotal_ex_gst", "0"))
    header_gst = D(invoice.get("gst", "0"))
    expected_gst = gst_component(header_ex)
    invoice_abn = normalise_abn(invoice.get("supplier_abn"))
    supplier_known = bool(supplier) and not supplier.get("error")
    master_abn = normalise_abn(supplier.get("abn")) if supplier_known else ""
    untrusted = invoice_untrusted_text(invoice)
    blocked = bool(screen.blocked)
    # Fingerprint the original text. The copy a model can read has bank values masked.
    released = None if blocked else mask_bank_values(untrusted)
    free_text_bank = any(
        contains_bank_detail(record)
        for record in (invoice, purchase_order, goods_receipts, supplier)
        if record is not None
    )
    payload = {
        "lines": lines,
        "gst": {
            "header_gst": money(header_gst),
            "expected_header_gst": money(expected_gst),
            "header_gst_matches": quantize(header_gst) == expected_gst,
        },
        "currency": str(invoice.get("currency", "")),
    }
    return InvoiceFacts(
        invoice_id=str(invoice.get("invoice_id", result.get("invoice_id", ""))),
        match_status=str(result["status"]),
        exception_codes=list(result["exception_codes"]),
        code_details=list(result["details"]),
        variance=variance,
        within_tolerance=within,
        supplier_known=supplier_known,
        abn_checksum_valid=is_valid_abn(invoice_abn),
        abn_matches_master=bool(supplier_known and invoice_abn == master_abn and invoice_abn != ""),
        bank_details_changed=bank_details_changed(invoice, supplier),
        bank_detail_in_free_text=free_text_bank,
        model_armor_flagged=blocked and screen.reason == "match",
        screening_failed=blocked and screen.reason != "match",
        screening_reason=screen.reason,
        text_sha256=hashlib.sha256(untrusted.encode("utf-8")).hexdigest(),
        released_text=released,
        payload=payload,
    )


def load_catalog(root: Path | None = None) -> dict[str, Any]:
    base = root or data_dir()
    suppliers = {
        row["supplier_id"]: row
        for row in json.loads((base / "seed" / "suppliers.json").read_text(encoding="utf-8"))
    }
    orders = {
        row["po_number"]: row
        for row in json.loads((base / "seed" / "purchase_orders.json").read_text(encoding="utf-8"))
    }
    receipts: dict[str, list] = {}
    for row in json.loads((base / "seed" / "goods_receipts.json").read_text(encoding="utf-8")):
        receipts.setdefault(row["po_number"], []).append(row)
    invoices = {}
    for path in sorted((base / "invoices").glob("INV-*.json")):
        invoice = json.loads(path.read_text(encoding="utf-8"))
        invoices[invoice["invoice_id"]] = invoice
    return {"suppliers": suppliers, "orders": orders, "receipts": receipts, "invoices": invoices}
