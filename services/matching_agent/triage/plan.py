"""Build a reviewable triage plan. ``plan`` changes nothing.

``apply`` records the plan in the local store and, when a Firestore
collection is configured, previews that write unless asked to perform it.
``reset`` previews the undo unless ``-yes`` is passed.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from invoice_mcp.armor import Screener, invoice_untrusted_text, screen_paragraphs
from matching_agent.triage.decide import Decision, judge_exception
from matching_agent.triage.facts import InvoiceFacts, build_facts, load_catalog
from matching_agent.triage.gemini import judge_name, model_from_env
from matching_agent.triage.judge import DecisionCache, JSONModel, TriageSettings
from matching_agent.triage.plan_types import Plan
from matching_agent.triage.policy import Policy, load_policy
from matching_agent.triage.screen import screener_for_run
from matching_agent.triage.store import FirestoreSink, LocalDecisionStore


def format_table(rows: list[dict]) -> str:
    """Text table: invoice, code-computed variance, verdict, cited rule, reason."""
    lines = [
        "Variance is the maximum absolute unit-price difference in AUD, computed by code.",
        f"{'INVOICE':<12} {'VARIANCE':>10} {'VERDICT':<10} {'RULE':<20} REASON",
    ]
    for row in rows:
        lines.append(
            f"{row['invoice_id']:<12} {row['variance']:>10} {row['verdict']:<10} "
            f"{row['rule']:<20} {row['reason']}"
        )
    return "\n".join(lines)


def _row(facts: InvoiceFacts, decision: Decision) -> dict:
    body = decision.as_dict()
    body["variance"] = facts.variance
    body["exception_codes"] = list(facts.exception_codes)
    body["match_status"] = facts.match_status
    return body


def build_plan(
    *,
    policy: Policy | None = None,
    data_dir: Path | None = None,
    screener: Screener | None = None,
    screener_name: str | None = None,
    model: JSONModel | None = None,
    cache: DecisionCache | None = None,
    settings: TriageSettings | None = None,
    invoice_ids: list[str] | None = None,
) -> Plan:
    """Triage the synthetic set. Only three-way-match exceptions are sent to a model."""
    active_policy = policy or load_policy()
    active_settings = settings or TriageSettings.from_env()
    active_model = model if model is not None else model_from_env()
    if screener is None:
        mode = "stub" if getattr(active_model, "offline_stub", False) else "gemini"
        screener, default_name = screener_for_run(mode)
        name = screener_name or default_name
    else:
        name = screener_name or "injected"
    catalog = load_catalog(data_dir)
    ids = invoice_ids or sorted(catalog["invoices"])
    rows: list[dict] = []
    for invoice_id in ids:
        invoice = catalog["invoices"].get(invoice_id)
        if invoice is None:
            rows.append(
                {
                    "invoice_id": invoice_id,
                    "reason": "Invoice file was not found. Fail closed: escalate.",
                    "rule": "always-escalate-3",
                    "verdict": "ESCALATE",
                    "confidence": 1.0,
                    "model": "code",
                    "escalated": False,
                    "citation_valid": True,
                    "hard_rule": "not_found",
                    "judged": False,
                    "variance": "0.00",
                    "exception_codes": [],
                    "match_status": "not_found",
                }
            )
            continue
        po = catalog["orders"].get(invoice.get("po_number"))
        supplier = catalog["suppliers"].get(po.get("supplier_id")) if po else None
        receipts = catalog["receipts"].get(invoice.get("po_number"), [])
        screen = screen_paragraphs(invoice_untrusted_text(invoice), screener)
        facts = build_facts(invoice, po, receipts, supplier, screen)
        decision = judge_exception(facts, active_policy, active_model, cache, active_settings)
        rows.append(_row(facts, decision))
    digest = hashlib.sha256(active_policy.text.encode("utf-8")).hexdigest()
    return Plan(
        policy_version=active_policy.version,
        policy_sha256=digest,
        confidence_threshold=active_settings.confidence_threshold,
        screener=name,
        judge=judge_name(active_model),
        rows=rows,
    )


def write_plan(plan: Plan, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plan.as_dict(), indent=2) + "\n", encoding="utf-8")


def plan_invoice(invoice_id: str) -> dict:
    """Triage one invoice for the matching-agent tool. Does not record a decision.

    Screening uses the invoice-mcp environment screener and fails closed when
    no Model Armor template is configured. The returned row has no invoice text.
    """
    from invoice_mcp.armor import prompt_template_from_env, screener_from_env

    screener = screener_from_env()
    allow = os.environ.get("MODEL_ARMOR_ALLOW_UNSCREENED", "").strip().lower()
    if prompt_template_from_env():
        name = "model-armor"
    elif allow in {"1", "true", "yes"}:
        name = "allow-unscreened"
    else:
        name = "fail-closed"
    plan = build_plan(
        invoice_ids=[invoice_id],
        screener=screener,
        screener_name=name,
        cache=DecisionCache(None),
    )
    return plan.rows[0]


def read_plan(path: Path) -> Plan:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return Plan(
        policy_version=str(payload.get("policy_version", "")),
        policy_sha256=str(payload.get("policy_sha256", "")),
        confidence_threshold=float(payload.get("confidence_threshold", 0)),
        screener=str(payload.get("screener", "")),
        judge=str(payload.get("judge", "")),
        rows=list(payload.get("rows") or []),
    )


def apply_plan(plan: Plan, store: LocalDecisionStore, sink: FirestoreSink | None = None) -> dict:
    """Record decisions locally. Firestore is previewed unless the sink applies writes."""
    store.save_plan(plan)
    preview: list[str] = []
    if sink is not None:
        for row in plan.rows:
            sink.write(row["invoice_id"], row)
            preview.append(row["invoice_id"])
    return {
        "stored": len(plan.rows),
        "store": str(store.path),
        "firestore_preview": preview,
        "firestore_applied": bool(sink and sink.apply_writes),
        "firestore_collection": sink.collection if sink else "",
    }


def reset_decisions(
    store: LocalDecisionStore,
    *,
    yes: bool,
    sink: FirestoreSink | None = None,
) -> dict:
    """Preview the local undo. ``yes`` deletes it. Firestore follows the sink flag."""
    ids = sorted(store.load().get("decisions", {}))
    if not yes:
        return {
            "applied": False,
            "preview": ids,
            "removed": [],
            "firestore_applied": False,
        }
    removed = store.clear()
    if sink is not None:
        for invoice_id in removed:
            sink.delete(invoice_id)
    return {
        "applied": True,
        "preview": [],
        "removed": removed,
        "firestore_applied": bool(sink and sink.apply_writes),
        "firestore_collection": sink.collection if sink else "",
    }
