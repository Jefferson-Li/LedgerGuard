"""Value scan for bank details that are not stored under a payment key."""

import json

from redact import BANK_TOKEN, contains_bank_detail, mask_bank_values, redact_sensitive

BSB = "062-199"
ACCOUNT = "90817263"
IBAN = "GB29NWBK60161331926819"


def _digits_gone(text: str, *needles: str) -> bool:
    masked = mask_bank_values(text)
    return BANK_TOKEN in masked and all(needle not in masked for needle in needles)


def test_labelled_bsb_and_account_are_masked():
    assert _digits_gone(f"BSB {BSB}", BSB)
    assert _digits_gone("BSB: 062000", "062000")
    assert _digits_gone("bank state branch 062 000", "062 000")
    assert _digits_gone("Account Number 12345678", "12345678")
    assert _digits_gone("Acct No. 123456", "123456")
    assert _digits_gone("A/C 90817263", "90817263")


def test_bsb_near_an_account_is_masked_in_either_order():
    assert _digits_gone(f"pay {BSB} {ACCOUNT}", BSB, ACCOUNT)
    assert _digits_gone(f"{ACCOUNT} ref {BSB}", BSB, ACCOUNT)
    assert _digits_gone("062199 90817263", "062199", "90817263")


def test_iban_shape_is_masked():
    assert _digits_gone(f"iban {IBAN}", IBAN)
    spaced = "DE89 3704 0044 0532 0130 00"
    assert _digits_gone(spaced, "3704", "0532")


def test_nested_notes_are_masked_and_payment_keys_are_still_dropped():
    record = {
        "supplier_id": "SUP-NOTES",
        "notes": f"Remit BSB {BSB} account number {ACCOUNT}.",
        "bank": {"bsb": "062-000", "account_number": "55555555", "account_name": "Notes Pty Ltd"},
        "lines": [{"description": f"see {IBAN}"}],
    }
    redacted = redact_sensitive(record)
    blob = json.dumps(redacted)
    assert "bank" not in redacted
    assert "55555555" not in blob
    assert "062-000" not in blob
    assert BSB not in blob
    assert ACCOUNT not in blob
    assert IBAN not in blob
    assert BANK_TOKEN in blob
    assert contains_bank_detail(record) is True


def test_structured_bank_key_alone_is_not_a_free_text_hit():
    record = {"bank": {"bsb": "062-000", "account_number": "11111111"}}
    assert contains_bank_detail(record) is False
    assert "11111111" not in json.dumps(redact_sensitive(record))


def test_ordinary_business_strings_are_not_masked():
    samples = [
        "ABN 51824753556",
        "ABN 51 824 753 556",
        "Invoice INV-1001 against PO-1001 and docket DD-1010",
        "INV-100001",
        "PO-100001",
        "Amount $1,234.56 and 12.50 and 180.00 and AUD 250.00",
        "Dated 2026-10-02, 16/10/2026, and 16 October 2026.",
        "Call 0412 345 678 or (07) 3333 4444 or +61 412 345 678.",
        "Landline 0733334444",
        "Quantity 100000 units",
        "Reference 062-000 on its own",
        "123456 654321",
    ]
    for sample in samples:
        assert mask_bank_values(sample) == sample, sample


def test_labelled_bsb_does_not_take_a_phone_number_with_it():
    text = "BSB 062-199 call 0412345678"
    masked = mask_bank_values(text)
    assert "062-199" not in masked
    assert "0412345678" in masked
