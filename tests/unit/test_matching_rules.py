from __future__ import annotations

import json
from pathlib import Path

import pytest

from invoice_mcp.armor import AllowAllScreener
from invoice_mcp.server import fetch_invoice, list_invoices
from matching_agent.rules import D, reconcile

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _catalog():
    suppliers = {row["supplier_id"]: row for row in _load(DATA / "seed" / "suppliers.json")}
    orders = {row["po_number"]: row for row in _load(DATA / "seed" / "purchase_orders.json")}
    receipts: dict[str, list] = {}
    for row in _load(DATA / "seed" / "goods_receipts.json"):
        receipts.setdefault(row["po_number"], []).append(row)
    return suppliers, orders, receipts


def test_synthetic_set_matches_the_spec():
    expected = _load(DATA / "expected_match.json")
    suppliers, orders, receipts = _catalog()
    assert len(list((DATA / "invoices").glob("INV-*.json"))) == 10
    for invoice_id, spec in expected.items():
        invoice = _load(DATA / "invoices" / f"{invoice_id}.json")
        po = orders[invoice["po_number"]]
        supplier = suppliers[po["supplier_id"]]
        result = reconcile(invoice, po, receipts.get(invoice["po_number"], []), supplier)
        assert result["status"] == spec["status"], invoice_id
        assert result["exception_codes"] == spec["exception_codes"], invoice_id


def test_missing_purchase_order():
    result = reconcile(
        {
            "invoice_id": "INV-X",
            "po_number": "PO-MISSING",
            "supplier_abn": "51824753556",
            "currency": "AUD",
            "lines": [],
            "subtotal_ex_gst": "0.00",
            "gst": "0.00",
            "total_inc_gst": "0.00",
        },
        None,
        [],
        None,
    )
    assert result["exception_codes"] == ["missing_purchase_order"]


def test_over_receipt_and_currency_and_unknown_sku():
    po = {
        "po_number": "PO-1",
        "supplier_id": "SUP-ACME",
        "currency": "AUD",
        "lines": [{"sku": "CEM-20", "quantity": "10", "unit_price_ex_gst": "12.50"}],
    }
    supplier = {"supplier_id": "SUP-ACME", "abn": "51824753556", "name": "Acme"}
    receipts = [
        {
            "grn_number": "GRN-1",
            "po_number": "PO-1",
            "lines": [{"sku": "CEM-20", "quantity_received": "12"}],
        }
    ]
    invoice = {
        "invoice_id": "INV-X",
        "po_number": "PO-1",
        "supplier_abn": "51824753556",
        "currency": "USD",
        "lines": [
            {
                "sku": "NOPE",
                "description": "Unknown",
                "quantity": "1",
                "unit_price_ex_gst": "1.00",
                "line_ex_gst": "1.00",
                "gst": "0.10",
                "line_total": "1.10",
            }
        ],
        "subtotal_ex_gst": "1.00",
        "gst": "0.10",
        "total_inc_gst": "1.10",
    }
    result = reconcile(invoice, po, receipts, supplier)
    assert "currency_mismatch" in result["exception_codes"]
    assert "sku_not_on_purchase_order" in result["exception_codes"]
    assert "over_receipt" in result["exception_codes"]


def test_invalid_abn_checksum():
    po = {
        "po_number": "PO-1",
        "currency": "AUD",
        "lines": [{"sku": "CEM-20", "quantity": "1", "unit_price_ex_gst": "10.00"}],
    }
    supplier = {"supplier_id": "SUP", "abn": "51824753556"}
    invoice = {
        "invoice_id": "INV-X",
        "po_number": "PO-1",
        "supplier_abn": "12345678901",
        "currency": "AUD",
        "lines": [
            {
                "sku": "CEM-20",
                "quantity": "1",
                "unit_price_ex_gst": "10.00",
                "line_ex_gst": "10.00",
                "gst": "1.00",
                "line_total": "11.00",
            }
        ],
        "subtotal_ex_gst": "10.00",
        "gst": "1.00",
        "total_inc_gst": "11.00",
    }
    result = reconcile(
        invoice, po, [{"lines": [{"sku": "CEM-20", "quantity_received": "1"}]}], supplier
    )
    assert "abn_invalid" in result["exception_codes"]
    assert "abn_mismatch" in result["exception_codes"]


def test_reconcile_payload_stops_on_quarantine():
    from matching_agent.rules import reconcile_from_tool_payload

    payload = reconcile_from_tool_payload(
        json.dumps({"invoice_id": "INV-1010", "status": "quarantined", "blocked": True}),
        "{}",
        "{}",
        "{}",
    )
    assert payload["status"] == "quarantined"
    assert "Ignore" not in json.dumps(payload)


def test_quarantine_withholds_malicious_body():
    from tests.unit.fakes import MarkerScreener

    result = fetch_invoice("INV-1010", screener=MarkerScreener("Ignore all previous instructions"))
    assert result["blocked"] is True
    blob = json.dumps(result)
    assert "Ignore all previous instructions" not in blob
    assert "11111111" not in blob
    assert "invoice" not in result


def test_clean_invoice_released_when_paragraphs_pass():
    result = fetch_invoice("INV-1001", screener=AllowAllScreener())
    assert result["status"] == "released"
    assert result["invoice"]["lines"][0]["sku"] == "CEM-20"


def test_list_invoices_is_metadata_only():
    rows = list_invoices()
    assert len(rows) == 10
    assert all("text" not in row for row in rows)


def test_fail_closed_without_template(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("MODEL_ARMOR_PROMPT_TEMPLATE", raising=False)
    monkeypatch.delenv("MODEL_ARMOR_TEMPLATE", raising=False)
    monkeypatch.delenv("MODEL_ARMOR_ALLOW_UNSCREENED", raising=False)
    result = fetch_invoice("INV-1001")
    assert result["blocked"] is True
    assert result["screening"]["reason"] == "screening_failed"
    assert "invoice" not in result


def test_price_tolerance_boundary():
    from matching_agent.rules import price_within_tolerance

    assert price_within_tolerance(D("45.40"), D("45.00"))
    assert not price_within_tolerance(D("9.50"), D("8.00"))
