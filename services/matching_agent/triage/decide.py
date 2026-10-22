"""Turn computed facts into a verdict. Code overrides the model on hard rules.

Flash answers first. A citation that is not in the policy is treated as
confidence 0 and escalated to Pro. Pro is also used when Flash is below the
configured confidence threshold. A Model Armor match, a screening failure,
a bank-detail change, or bank details found in free text is ESCALATE
whether or not a model was asked.
"""

from __future__ import annotations

from dataclasses import dataclass

from matching_agent.triage.facts import InvoiceFacts
from matching_agent.triage.judge import (
    VERDICTS,
    DecisionCache,
    JSONModel,
    TriageSettings,
    cache_key,
    system_prompt,
    user_prompt,
)
from matching_agent.triage.policy import Policy

_HARD_RULES = {
    "model_armor": (
        "always-escalate-2",
        "Model Armor matched this invoice. Code escalates it. The model does not approve it.",
    ),
    "screening_failed": (
        "always-escalate-3",
        "Screening did not return a successful no-match. Fail closed: the verdict is escalate.",
    ),
    "bank_details": (
        "always-escalate-1",
        "Bank details differ from the supplier master. Code escalates over any model verdict.",
    ),
    "bank_in_free_text": (
        "always-escalate-4",
        "Bank details were found in free text. Code escalates over any model verdict.",
    ),
}


@dataclass
class Decision:
    invoice_id: str
    reason: str
    rule: str
    verdict: str
    confidence: float
    model: str = "code"
    escalated: bool = False
    citation_valid: bool = True
    hard_rule: str | None = None
    judged: bool = False

    def as_dict(self) -> dict:
        return {
            "invoice_id": self.invoice_id,
            "reason": self.reason,
            "rule": self.rule,
            "verdict": self.verdict,
            "confidence": self.confidence,
            "model": self.model,
            "escalated": self.escalated,
            "citation_valid": self.citation_valid,
            "hard_rule": self.hard_rule,
            "judged": self.judged,
        }

    @classmethod
    def from_dict(cls, payload: dict) -> Decision:
        return cls(
            invoice_id=str(payload.get("invoice_id", "")),
            reason=str(payload.get("reason", "")),
            rule=str(payload.get("rule", "")),
            verdict=str(payload.get("verdict", "ESCALATE")),
            confidence=float(payload.get("confidence", 0)),
            model=str(payload.get("model", "")),
            escalated=bool(payload.get("escalated", False)),
            citation_valid=bool(payload.get("citation_valid", False)),
            hard_rule=payload.get("hard_rule"),
            judged=bool(payload.get("judged", False)),
        )


def _confidence(value: object) -> float:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
    if number < 0 or number > 1:
        return 0.0
    return number


def decision_from_model(invoice_id: str, payload: dict, *, model_name: str) -> Decision:
    """Keep reason, rule, verdict, and confidence. Drop any amounts the model added."""
    verdict = str(payload.get("verdict", "")).strip().upper()
    if verdict not in VERDICTS:
        verdict = "ESCALATE"
    return Decision(
        invoice_id=invoice_id,
        reason=str(payload.get("reason", "")).strip(),
        rule=str(payload.get("rule", "")).strip(),
        verdict=verdict,
        confidence=_confidence(payload.get("confidence")),
        model=model_name,
        judged=True,
    )


def validate_citation(policy: Policy, decision: Decision) -> Decision:
    """An unknown label is not a rule. Confidence becomes 0 so the caller escalates."""
    known = decision.rule in policy.lines and decision.verdict in VERDICTS
    decision.citation_valid = known
    if not known:
        decision.confidence = 0.0
    return decision


def _hard_kind(facts: InvoiceFacts) -> str | None:
    if facts.model_armor_flagged:
        return "model_armor"
    if facts.screening_failed:
        return "screening_failed"
    if facts.bank_details_changed:
        return "bank_details"
    if facts.bank_detail_in_free_text:
        return "bank_in_free_text"
    return None


def hard_rule_decision(facts: InvoiceFacts, policy: Policy) -> Decision:
    kind = _hard_kind(facts)
    if kind is None:
        raise ValueError("no hard rule applies")
    label, reason = _HARD_RULES[kind]
    if label not in policy.lines:
        reason = f"{reason} Policy label {label} is not in this policy file."
    return Decision(
        invoice_id=facts.invoice_id,
        reason=reason,
        rule=label,
        verdict="ESCALATE",
        confidence=1.0,
        model="code",
        escalated=False,
        citation_valid=label in policy.lines,
        hard_rule=kind,
        judged=False,
    )


def apply_hard_rules(decision: Decision, facts: InvoiceFacts, policy: Policy) -> Decision:
    """Hard rules win even when the model returned APPROVE with high confidence."""
    if _hard_kind(facts) is None:
        return decision
    forced = hard_rule_decision(facts, policy)
    forced.model = decision.model or forced.model
    forced.escalated = decision.escalated
    return forced


def _code_match(facts: InvoiceFacts, policy: Policy) -> Decision:
    if facts.within_tolerance and not facts.exception_codes and "auto-approve-1" in policy.lines:
        label = "auto-approve-1"
    elif "auto-approve-2" in policy.lines:
        label = "auto-approve-2"
    else:
        label = "auto-approve-1"
    text = policy.lines.get(label, "The three-way match did not raise an exception.")
    return Decision(
        invoice_id=facts.invoice_id,
        reason=(
            f"Three-way match status is {facts.match_status}. "
            f"Code applied {label}: {text} The model was not asked."
        ),
        rule=label,
        verdict="APPROVE",
        confidence=1.0,
        model="code",
        citation_valid=label in policy.lines,
        judged=False,
    )


def _call_model(
    model: JSONModel,
    *,
    model_name: str,
    policy: Policy,
    facts: InvoiceFacts,
) -> Decision:
    try:
        payload = model.generate_json(
            model=model_name,
            system=system_prompt(policy),
            user=user_prompt(facts),
            schema=_schema(),
        )
    except Exception as exc:
        return Decision(
            invoice_id=facts.invoice_id,
            reason=f"The judge could not be called ({type(exc).__name__}). Fail closed: escalate.",
            rule="always-escalate-3" if "always-escalate-3" in policy.lines else "",
            verdict="ESCALATE",
            confidence=0.0,
            model=model_name,
            citation_valid=False,
            hard_rule="judge_unavailable",
            judged=False,
        )
    if not isinstance(payload, dict):
        payload = {}
    recorded = f"stub:{model_name}" if getattr(model, "offline_stub", False) else model_name
    return validate_citation(
        policy,
        decision_from_model(facts.invoice_id, payload, model_name=recorded),
    )


def _schema() -> dict:
    from matching_agent.triage.judge import DECISION_SCHEMA

    return DECISION_SCHEMA


def _acceptable(decision: Decision, threshold: float) -> bool:
    return (
        decision.citation_valid
        and decision.verdict in VERDICTS
        and decision.confidence >= threshold
        and decision.hard_rule is None
    )


def _two_tier(
    facts: InvoiceFacts,
    policy: Policy,
    model: JSONModel,
    settings: TriageSettings,
) -> Decision:
    """Flash first. Pro when Flash is unsure or cited a label that does not exist."""
    flash = _call_model(model, model_name=settings.flash_model, policy=policy, facts=facts)
    if _acceptable(flash, settings.confidence_threshold):
        flash.escalated = False
        return flash

    pro = _call_model(model, model_name=settings.pro_model, policy=policy, facts=facts)
    pro.escalated = True
    if pro.hard_rule == "judge_unavailable":
        pro.verdict = "ESCALATE"
        pro.confidence = 0.0
        return pro
    if not pro.citation_valid:
        pro.verdict = "ESCALATE"
        pro.confidence = 0.0
        pro.reason = (
            "The cited rule is not a label in the policy, so this decision is escalated. "
            + pro.reason
        )
    # A valid Pro citation stands, including a low-confidence one. Pro is the
    # second tier, not a third person. Unknown labels do not stand.
    return pro


def judge_exception(
    facts: InvoiceFacts,
    policy: Policy,
    model: JSONModel,
    cache: DecisionCache | None,
    settings: TriageSettings,
) -> Decision:
    """Judge one exception, using the cache when the facts and policy are unchanged."""
    if facts.hard_blocked:
        return hard_rule_decision(facts, policy)
    if facts.match_status != "exception":
        return _code_match(facts, policy)

    facts_json = facts.canonical_json()
    key = cache_key(facts_json, policy.text, settings.confidence_threshold)
    store = cache or DecisionCache(None)
    cached = store.get(key)
    if cached is not None:
        decision = Decision.from_dict(cached)
        decision.invoice_id = facts.invoice_id
        return apply_hard_rules(decision, facts, policy)

    if facts.released_text is None:
        return Decision(
            invoice_id=facts.invoice_id,
            reason="Invoice text was not released. Fail closed: escalate.",
            rule="always-escalate-3" if "always-escalate-3" in policy.lines else "",
            verdict="ESCALATE",
            confidence=1.0,
            model="code",
            hard_rule="screening_failed",
            citation_valid="always-escalate-3" in policy.lines,
            judged=False,
        )

    decision = _two_tier(facts, policy, model, settings)
    decision = apply_hard_rules(decision, facts, policy)
    if decision.hard_rule is None:
        store.put(key, decision.as_dict())
    return decision
