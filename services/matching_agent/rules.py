"""Deterministic three-way match for Australian tax invoices.

Money is calculated here, not by a model. GST is 10 percent of the GST-exclusive
amount, rounded half-up to the cent (the usual ATO cash rounding). A unit price
matches when the absolute difference is within the larger of AUD 0.50 and 2
percent of the purchase-order price.

Amounts in the synthetic data are GST-exclusive on each line, with GST stored
separately. This module does not reverse-calculate tax from a GST-inclusive total.
"""

from __future__ import annotations

import json
import re
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from redact import redact_sensitive

GST_RATE = Decimal("0.10")
CENT = Decimal("0.01")
PRICE_TOLERANCE_ABS = Decimal("0.50")
PRICE_TOLERANCE_RATE = Decimal("0.02")
ABN_WEIGHTS = (10, 1, 3, 5, 7, 9, 11, 13, 15, 17, 19)


def D(value: object) -> Decimal:
    return Decimal(str(value))


def quantize(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def gst_component(ex_gst: Decimal) -> Decimal:
    """GST on a GST-exclusive amount, rounded half-up to the nearest cent."""
    return quantize(ex_gst * GST_RATE)


def price_within_tolerance(invoice_price: Decimal, po_price: Decimal) -> bool:
    diff = abs(invoice_price - po_price)
    percent_limit = quantize(abs(po_price) * PRICE_TOLERANCE_RATE)
    limit = max(PRICE_TOLERANCE_ABS, percent_limit)
    return diff <= limit


def normalise_abn(value: object) -> str:
    return re.sub(r"\D", "", str(value or ""))


def is_valid_abn(value: object) -> bool:
    """Australian Business Number checksum (modulus 89)."""
    digits = normalise_abn(value)
    if len(digits) != 11:
        return False
    vals = [int(char) for char in digits]
    vals[0] -= 1
    return sum(val * weight for val, weight in zip(vals, ABN_WEIGHTS, strict=True)) % 89 == 0


def _as_receipts(
    goods_receipts: list[dict[str, Any]] | dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if goods_receipts is None:
        return []
    if isinstance(goods_receipts, dict):
        if goods_receipts.get("error"):
            return []
        nested = goods_receipts.get("goods_receipts", [])
        return list(nested) if isinstance(nested, list) else []
    return list(goods_receipts)


def _usable(record: dict[str, Any] | None) -> dict[str, Any] | None:
    if not record or record.get("error"):
        return None
    return record


def reconcile(
    invoice: dict[str, Any],
    purchase_order: dict[str, Any] | None,
    goods_receipts: list[dict[str, Any]] | dict[str, Any] | None,
    supplier: dict[str, Any] | None,
) -> dict[str, Any]:
    """Match one invoice to its purchase order, receipts, and supplier master.

    The return value is JSON-serialisable. Money fields are decimal strings.
    """
    invoice = redact_sensitive(invoice)
    purchase_order = _usable(redact_sensitive(purchase_order) if purchase_order else None)
    supplier = _usable(redact_sensitive(supplier) if supplier else None)
    receipts = _as_receipts(redact_sensitive(goods_receipts) if goods_receipts else None)

    codes: set[str] = set()
    details: list[str] = []
    invoice_id = str(invoice.get("invoice_id", ""))
    po_number = str(invoice.get("po_number", ""))

    if purchase_order is None:
        codes.add("missing_purchase_order")
        missing = po_number or "no PO"
        details.append(
            f"{invoice_id} references {missing}, which is not in the purchase-order set."
        )
        return _result(invoice_id, po_number, codes, details)

    if str(purchase_order.get("po_number")) != po_number:
        codes.add("missing_purchase_order")
        recorded = purchase_order.get("po_number")
        details.append(
            f"{invoice_id} po_number {po_number} does not equal purchase order {recorded}."
        )

    if supplier is None:
        codes.add("unknown_supplier")
        details.append(
            f"No supplier master record for purchase order {purchase_order.get('po_number')}."
        )
    else:
        invoice_abn = normalise_abn(invoice.get("supplier_abn"))
        master_abn = normalise_abn(supplier.get("abn"))
        if not is_valid_abn(invoice_abn):
            codes.add("abn_invalid")
            details.append(f"Invoice ABN {invoice.get('supplier_abn')!r} failed the ABN checksum.")
        if invoice_abn != master_abn:
            codes.add("abn_mismatch")
            shown = invoice_abn or "(blank)"
            supplier_id = supplier.get("supplier_id")
            details.append(
                f"Invoice ABN {shown} does not match supplier {supplier_id} ABN {master_abn}."
            )

    invoice_currency = str(invoice.get("currency", ""))
    po_currency = str(purchase_order.get("currency", ""))
    if invoice_currency != "AUD" or po_currency != "AUD" or invoice_currency != po_currency:
        codes.add("currency_mismatch")
        details.append(
            f"Invoice currency {invoice_currency} / PO currency {po_currency}; expected AUD."
        )

    po_lines = {str(line["sku"]): line for line in purchase_order.get("lines", [])}
    received_by_sku: dict[str, Decimal] = {}
    ordered_checked = False
    if not receipts:
        codes.add("missing_goods_receipt")
        details.append(f"No goods receipt for purchase order {purchase_order.get('po_number')}.")
    else:
        for receipt in receipts:
            for line in receipt.get("lines", []):
                sku = str(line["sku"])
                received_by_sku[sku] = received_by_sku.get(sku, Decimal(0)) + D(
                    line["quantity_received"]
                )
        for sku, received in received_by_sku.items():
            po_line = po_lines.get(sku)
            if po_line is None:
                continue
            ordered = D(po_line["quantity"])
            if received > ordered:
                codes.add("over_receipt")
                details.append(f"{sku}: received {received}, which is more than ordered {ordered}.")

    header_ex = D(invoice["subtotal_ex_gst"])
    header_gst = D(invoice["gst"])
    header_total = D(invoice["total_inc_gst"])
    sum_ex = Decimal(0)
    sum_gst = Decimal(0)
    sum_total = Decimal(0)

    for line in invoice.get("lines", []):
        sku = str(line["sku"])
        qty = D(line["quantity"])
        unit = D(line["unit_price_ex_gst"])
        line_ex = D(line["line_ex_gst"])
        line_gst = D(line["gst"])
        line_total = D(line["line_total"])
        sum_ex += line_ex
        sum_gst += line_gst
        sum_total += line_total

        expected_ex = quantize(qty * unit)
        if expected_ex != quantize(line_ex):
            codes.add("line_amount_mismatch")
            details.append(
                f"{sku}: quantity times unit price is {expected_ex}, line amount is {line_ex}."
            )

        expected_gst = gst_component(line_ex)
        if quantize(line_gst) != expected_gst:
            codes.add("gst_mismatch")
            details.append(f"{sku}: GST {line_gst} is not 10% of {line_ex} ({expected_gst}).")

        po_line = po_lines.get(sku)
        if po_line is None:
            codes.add("sku_not_on_purchase_order")
            details.append(f"{sku} is not on purchase order {purchase_order.get('po_number')}.")
            continue

        po_unit = D(po_line["unit_price_ex_gst"])
        if not price_within_tolerance(unit, po_unit):
            codes.add("price_mismatch")
            details.append(
                f"{sku}: invoice unit price {unit} is outside tolerance of PO price {po_unit}."
            )
        elif unit != po_unit:
            details.append(
                f"{sku}: invoice unit price {unit} is within tolerance of PO price {po_unit}."
            )

        if receipts:
            ordered = D(po_line["quantity"])
            received = received_by_sku.get(sku, Decimal(0))
            ordered_checked = True
            if received != qty:
                codes.add("quantity_mismatch")
                details.append(
                    f"{sku}: invoiced quantity {qty}, received {received}, ordered {ordered}."
                )

    if quantize(header_gst) != gst_component(header_ex):
        codes.add("gst_mismatch")
        expected_gst = gst_component(header_ex)
        details.append(
            f"Header GST {header_gst} is not 10% of subtotal {header_ex} ({expected_gst})."
        )
    if (
        quantize(sum_ex) != quantize(header_ex)
        or quantize(sum_gst) != quantize(header_gst)
        or quantize(sum_total) != quantize(header_total)
    ):
        codes.add("total_mismatch")
        details.append(
            f"Header {header_ex} + {header_gst} = {header_total} does not equal the sum of lines."
        )

    if ordered_checked is False and receipts:
        details.append("Goods receipts were present but no invoice line was checked against them.")

    return _result(invoice_id, po_number, codes, details)


def reconcile_from_tool_payload(
    invoice_json: str,
    purchase_order_json: str,
    goods_receipt_json: str,
    supplier_json: str,
) -> dict[str, Any]:
    """Match from JSON strings returned by the MCP tools.

    A quarantined invoice is not matched. The document body is not required
    and is not invented.
    """
    invoice = json.loads(invoice_json)
    if invoice.get("blocked") or invoice.get("status") == "quarantined":
        return {
            "invoice_id": invoice.get("invoice_id"),
            "po_number": invoice.get("po_number"),
            "status": "quarantined",
            "exception_codes": ["quarantined"],
            "details": [
                "Invoice was quarantined before matching. Do not pay it or request the body."
            ],
        }
    body = invoice.get("invoice", invoice)
    return reconcile(
        body,
        json.loads(purchase_order_json),
        json.loads(goods_receipt_json),
        json.loads(supplier_json),
    )


def _result(invoice_id: str, po_number: str, codes: set[str], details: list[str]) -> dict[str, Any]:
    ordered = sorted(codes)
    return {
        "invoice_id": invoice_id,
        "po_number": po_number,
        "status": "exception" if ordered else "matched",
        "exception_codes": ordered,
        "details": details,
    }
