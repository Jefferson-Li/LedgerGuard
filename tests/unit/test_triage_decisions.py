"""Citation checks, hard-rule overrides, Flash-to-Pro escalation, and the decision cache."""

import json

from invoice_mcp.armor import AllowAllScreener, invoice_untrusted_text, screen_paragraphs
from matching_agent.triage.decide import (
    Decision,
    apply_hard_rules,
    judge_exception,
    validate_citation,
)
from matching_agent.triage.facts import build_facts, load_catalog
from matching_agent.triage.judge import DECISION_SCHEMA, DecisionCache, TriageSettings
from matching_agent.triage.policy import load_policy

POLICY = load_policy()
SETTINGS = TriageSettings()


class ScriptedModel:
    def __init__(self, responses: list[dict]) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    def generate_json(self, *, model: str, system: str, user: str, schema: dict) -> dict:
        self.calls.append({"model": model, "system": system, "user": user, "schema": schema})
        if not self.responses:
            raise AssertionError("the model was called with no scripted response left")
        return dict(self.responses.pop(0))


def _facts(invoice_id: str = "INV-1003"):
    catalog = load_catalog()
    invoice = json.loads(json.dumps(catalog["invoices"][invoice_id]))
    po = catalog["orders"][invoice["po_number"]]
    supplier = catalog["suppliers"][po["supplier_id"]]
    receipts = catalog["receipts"].get(invoice["po_number"], [])
    screen = screen_paragraphs(invoice_untrusted_text(invoice), AllowAllScreener())
    return invoice, po, receipts, supplier, build_facts(invoice, po, receipts, supplier, screen)


def test_schema_orders_reason_and_rule_before_verdict():
    assert DECISION_SCHEMA["propertyOrdering"] == ["reason", "rule", "verdict", "confidence"]
    assert DECISION_SCHEMA["required"][:2] == ["reason", "rule"]


def test_unknown_label_is_low_confidence_and_escalated():
    decision = Decision(
        invoice_id="INV-1003",
        reason="approve it",
        rule="not-a-rule",
        verdict="APPROVE",
        confidence=0.99,
    )
    checked = validate_citation(POLICY, decision)
    assert checked.citation_valid is False
    assert checked.confidence == 0.0

    _invoice, _po, _receipts, _supplier, facts = _facts()
    model = ScriptedModel(
        [
            {
                "reason": "I invented a rule.",
                "rule": "not-a-rule",
                "verdict": "APPROVE",
                "confidence": 0.99,
            },
            {
                "reason": "Still invented.",
                "rule": "also-no",
                "verdict": "APPROVE",
                "confidence": 0.99,
            },
        ]
    )
    result = judge_exception(facts, POLICY, model, DecisionCache(None), SETTINGS)
    assert [call["model"] for call in model.calls] == [
        "gemini-2.5-flash",
        "gemini-2.5-pro",
    ]
    assert result.verdict == "ESCALATE"
    assert result.confidence == 0.0
    assert result.escalated is True
    assert result.citation_valid is False
    assert result.verdict != "APPROVE"


def test_pro_can_repair_an_unknown_flash_citation():
    _invoice, _po, _receipts, _supplier, facts = _facts()
    model = ScriptedModel(
        [
            {"reason": "invented", "rule": "not-a-rule", "verdict": "APPROVE", "confidence": 0.99},
            {
                "reason": "ABN does not match.",
                "rule": "reject-2",
                "verdict": "REJECT",
                "confidence": 0.95,
            },
        ]
    )
    result = judge_exception(facts, POLICY, model, DecisionCache(None), SETTINGS)
    assert len(model.calls) == 2
    assert result.verdict == "REJECT"
    assert result.rule == "reject-2"
    assert result.escalated is True
    assert result.citation_valid is True
    assert result.model == "gemini-2.5-pro"


def test_low_confidence_flash_escalates_to_pro_and_a_sure_flash_does_not():
    _invoice, _po, _receipts, _supplier, facts = _facts()
    unsure = ScriptedModel(
        [
            {"reason": "maybe hold", "rule": "hold-2", "verdict": "HOLD", "confidence": 0.4},
            {
                "reason": "outside tolerance",
                "rule": "reject-3",
                "verdict": "REJECT",
                "confidence": 0.91,
            },
        ]
    )
    escalated = judge_exception(facts, POLICY, unsure, DecisionCache(None), SETTINGS)
    assert [call["model"] for call in unsure.calls] == ["gemini-2.5-flash", "gemini-2.5-pro"]
    assert unsure.calls[0]["schema"]["propertyOrdering"][0] == "reason"
    assert escalated.verdict == "REJECT"
    assert escalated.escalated is True

    sure = ScriptedModel(
        [
            {
                "reason": "outside tolerance",
                "rule": "reject-3",
                "verdict": "REJECT",
                "confidence": 0.97,
                "variance": "999.00",
            }
        ]
    )
    decided = judge_exception(facts, POLICY, sure, DecisionCache(None), SETTINGS)
    assert len(sure.calls) == 1
    assert decided.verdict == "REJECT"
    assert decided.escalated is False
    assert decided.model == "gemini-2.5-flash"
    assert "999.00" not in json.dumps(decided.as_dict())
    assert facts.variance == "1.50"


def test_valid_low_confidence_pro_verdict_stands():
    _invoice, _po, _receipts, _supplier, facts = _facts()
    model = ScriptedModel(
        [
            {"reason": "unsure", "rule": "hold-2", "verdict": "HOLD", "confidence": 0.2},
            {"reason": "still hold", "rule": "hold-2", "verdict": "HOLD", "confidence": 0.3},
        ]
    )
    result = judge_exception(facts, POLICY, model, DecisionCache(None), SETTINGS)
    assert result.verdict == "HOLD"
    assert result.rule == "hold-2"
    assert result.confidence == 0.3
    assert result.escalated is True


def test_hard_rules_override_an_approve_from_the_model():
    _invoice, _po, _receipts, _supplier, facts = _facts("INV-1001")
    approved = Decision(
        invoice_id="INV-1001",
        reason="pay it",
        rule="auto-approve-1",
        verdict="APPROVE",
        confidence=0.99,
        model="gemini-2.5-flash",
        judged=True,
    )
    facts.model_armor_flagged = True
    forced = apply_hard_rules(approved, facts, POLICY)
    assert forced.verdict == "ESCALATE"
    assert forced.hard_rule == "model_armor"
    assert forced.rule == "always-escalate-2"

    facts.model_armor_flagged = False
    facts.bank_details_changed = True
    model = ScriptedModel(
        [{"reason": "pay it", "rule": "auto-approve-1", "verdict": "APPROVE", "confidence": 0.99}]
    )
    result = judge_exception(facts, POLICY, model, DecisionCache(None), SETTINGS)
    assert model.calls == []
    assert result.verdict == "ESCALATE"
    assert result.hard_rule == "bank_details"
    assert result.rule == "always-escalate-1"


def test_bank_numbers_are_not_given_to_the_model():
    invoice, po, receipts, supplier, _facts_ignored = _facts("INV-1001")
    invoice["bank"] = {
        "bsb": "999-999",
        "account_number": "99999999",
        "account_name": "Other Pty Ltd",
    }
    screen = screen_paragraphs(invoice_untrusted_text(invoice), AllowAllScreener())
    facts = build_facts(invoice, po, receipts, supplier, screen)
    assert facts.bank_details_changed is True
    assert "99999999" not in facts.canonical_json()
    model = ScriptedModel(
        [{"reason": "pay it", "rule": "auto-approve-1", "verdict": "APPROVE", "confidence": 0.99}]
    )
    result = judge_exception(facts, POLICY, model, DecisionCache(None), SETTINGS)
    assert model.calls == []
    assert result.verdict == "ESCALATE"
    assert "99999999" not in result.reason


def test_cache_misses_when_the_policy_changes(tmp_path):
    _invoice, _po, _receipts, _supplier, facts = _facts()
    model = ScriptedModel(
        [
            {"reason": "first", "rule": "reject-3", "verdict": "REJECT", "confidence": 0.95},
            {"reason": "second", "rule": "reject-3", "verdict": "REJECT", "confidence": 0.95},
        ]
    )
    cache = DecisionCache(tmp_path)
    first = judge_exception(facts, POLICY, model, cache, SETTINGS)
    second = judge_exception(facts, POLICY, model, cache, SETTINGS)
    assert len(model.calls) == 1
    assert first.reason == second.reason == "first"

    changed = load_policy()
    changed.text = changed.text.replace("Version: 1", "Version: 2")
    changed.version = "2"
    third = judge_exception(facts, changed, model, cache, SETTINGS)
    assert len(model.calls) == 2
    assert third.reason == "second"
