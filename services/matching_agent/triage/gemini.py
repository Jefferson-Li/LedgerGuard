"""Gemini judge and the offline stub.

The stub is the default so pytest and CI do not need credentials. It mirrors
the Model Armor stand-in: it never calls Vertex AI. Live mode is selected
with ``LEDGERGUARD_TRIAGE_JUDGE=gemini``.
"""

from __future__ import annotations

import json
import os

# Prefer reject over hold, matching triage rule 4. Labels are the ones in
# policy/ap-policy.md. The stub does not calculate money.
_STUB_BY_CODE: tuple[tuple[str, str, str, float], ...] = (
    ("abn_invalid", "REJECT", "reject-1", 0.95),
    ("unknown_supplier", "REJECT", "reject-2", 0.94),
    ("abn_mismatch", "REJECT", "reject-2", 0.93),
    ("missing_purchase_order", "REJECT", "reject-2", 0.93),
    ("price_mismatch", "REJECT", "reject-3", 0.92),
    ("line_amount_mismatch", "REJECT", "reject-3", 0.9),
    ("sku_not_on_purchase_order", "REJECT", "reject-2", 0.9),
    ("gst_mismatch", "REJECT", "reject-4", 0.91),
    ("total_mismatch", "REJECT", "reject-4", 0.9),
    ("missing_goods_receipt", "HOLD", "hold-1", 0.9),
    ("quantity_mismatch", "HOLD", "hold-2", 0.9),
    ("over_receipt", "HOLD", "hold-2", 0.86),
    ("currency_mismatch", "HOLD", "hold-1", 0.85),
)


def _facts_from_user(user: str) -> dict:
    start = user.find("COMPUTED_FACTS\n")
    end = user.find("\nEND_COMPUTED_FACTS")
    if start < 0 or end < 0:
        return {}
    raw = user[start + len("COMPUTED_FACTS\n") : end]
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


class StubGeminiModel:
    """Deterministic stand-in. ``offline_stub`` tells the decider to label the model."""

    offline_stub = True

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def generate_json(self, *, model: str, system: str, user: str, schema: dict) -> dict:
        self.calls.append({"model": model, "system": system, "user": user, "schema": schema})
        facts = _facts_from_user(user)
        codes = set(facts.get("exception_codes") or [])
        for code, verdict, label, confidence in _STUB_BY_CODE:
            if code in codes:
                return {
                    "reason": (
                        f"The code-computed exception list includes {code}. "
                        f"Policy label {label} applies. This stub did not calculate amounts."
                    ),
                    "rule": label,
                    "verdict": verdict,
                    "confidence": confidence,
                }
        return {
            "reason": "No exception code was present. This stub did not calculate amounts.",
            "rule": "auto-approve-1",
            "verdict": "APPROVE",
            "confidence": 0.99,
        }


class GeminiJSONModel:
    """Vertex Gemini structured output. Constructed only in live mode."""

    offline_stub = False

    def __init__(self) -> None:
        self._client = None

    def generate_json(self, *, model: str, system: str, user: str, schema: dict) -> dict:
        client = self._client or self._build()
        self._client = client
        from google.genai import types

        response = client.models.generate_content(
            model=model,
            contents=user,
            config=types.GenerateContentConfig(
                system_instruction=system,
                temperature=0,
                response_mime_type="application/json",
                response_schema=schema,
            ),
        )
        text = getattr(response, "text", None) or ""
        payload = json.loads(text)
        if not isinstance(payload, dict):
            raise TypeError("Gemini did not return a JSON object")
        return payload

    def _build(self):
        from google import genai

        project = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
        location = os.environ.get("GOOGLE_CLOUD_LOCATION", "global")
        if not project:
            raise RuntimeError(
                "LEDGERGUARD_TRIAGE_JUDGE=gemini needs GOOGLE_CLOUD_PROJECT. "
                "Leave the judge on stub for offline runs."
            )
        return genai.Client(vertexai=True, project=project, location=location)


def model_from_env():
    mode = os.environ.get("LEDGERGUARD_TRIAGE_JUDGE", "stub").strip().lower()
    if mode in {"", "stub", "offline"}:
        return StubGeminiModel()
    if mode == "gemini":
        return GeminiJSONModel()
    raise ValueError(f"Unknown LEDGERGUARD_TRIAGE_JUDGE={mode!r}. Use stub or gemini.")


def judge_name(model: object) -> str:
    if getattr(model, "offline_stub", False):
        return "stub"
    return "gemini"
