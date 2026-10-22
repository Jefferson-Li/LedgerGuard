"""Strip payment-detail keys from records before they leave a service."""

from __future__ import annotations

from typing import Any

SENSITIVE_KEYS = frozenset({"bank", "bsb", "account_number", "account_name", "bank_account"})


def redact_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: redact_sensitive(item) for key, item in value.items() if key not in SENSITIVE_KEYS
        }
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    return value
