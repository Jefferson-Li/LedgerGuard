import json

from erp_mcp.server import get_goods_receipt, get_purchase_order, get_supplier


def test_purchase_order_round_trip():
    po = get_purchase_order("PO-1001")
    assert po["po_number"] == "PO-1001"
    assert po["lines"][0]["sku"] == "CEM-20"


def test_missing_purchase_order():
    assert get_purchase_order("PO-NOPE")["error"] == "not_found"


def test_goods_receipt_missing_is_an_empty_list():
    body = get_goods_receipt("PO-1005")
    assert body["goods_receipts"] == []


def test_supplier_payload_has_no_bank_fields():
    supplier = get_supplier("SUP-ACME")
    assert supplier["abn"] == "51824753556"
    blob = json.dumps(supplier)
    assert "bank" not in supplier
    assert "11111111" not in blob
    assert "062-000" not in blob
