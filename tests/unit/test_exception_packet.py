import json

from ap_orchestrator.subagents.exception_writer import format_exception_packet


def test_packet_lists_codes_and_drops_bank_fields():
    raw = json.dumps(
        {
            "invoice_id": "INV-1002",
            "status": "exception",
            "exception_codes": ["quantity_mismatch"],
            "details": ["BRK-01: invoiced quantity 120, received 100, ordered 100."],
            "bank": {"account_number": "11111111", "bsb": "062-000"},
        }
    )
    text = format_exception_packet(raw)
    assert "INV-1002" in text
    assert "quantity_mismatch" in text
    assert "11111111" not in text
    assert "062-000" not in text
    assert "Route this exception" in text


def test_quarantine_packet_says_not_to_pay():
    text = format_exception_packet(
        json.dumps(
            {
                "invoice_id": "INV-1010",
                "status": "quarantined",
                "exception_codes": ["quarantined"],
                "details": ["withheld"],
            }
        )
    )
    assert "Do not pay" in text
