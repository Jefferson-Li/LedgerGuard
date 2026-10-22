"""Red-team runner.

Offline mode (the default) checks LedgerGuard's enforcement code. Document
attacks go through paragraph screening with a marker stand-in. Prompt attacks
apply ``should_block`` to the stub verdict in the YAML file. Neither path calls
Model Armor.

Live mode calls Model Armor for attacks marked ``live: call``. Dilution is not
asserted against the live service: the stand-in exists to show why paragraphs
are screened, and a real filter may or may not match the whole document.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))
sys.path.insert(0, str(ROOT / "security"))

from invoice_mcp.armor import (  # noqa: E402
    ScreeningVerdict,
    screen_paragraphs,
    screen_whole_document,
    should_block,
)
from invoice_mcp.server import fetch_invoice, invoice_untrusted_text, load_invoice  # noqa: E402
from stub_screeners import DilutionStandIn, MarkerScreener  # noqa: E402


def _verdict(payload: dict) -> ScreeningVerdict:
    return ScreeningVerdict(
        match_state=payload["match_state"],
        invocation_result=payload["invocation_result"],
        filters=tuple(payload.get("filters") or ()),
        skipped=bool(payload.get("skipped", False)),
    )


def _offline(attack: dict) -> tuple[bool, str]:
    channel = attack["channel"]
    expect = attack["expect"]
    if channel == "user_prompt":
        blocked = should_block(_verdict(attack["stub_verdict"]))
        return blocked == expect["blocked"], f"blocked={blocked}"
    if channel == "invoice_document":
        result = fetch_invoice(attack["invoice_id"], screener=MarkerScreener(attack["marker"]))
        leaked = attack["marker"] in json.dumps(result)
        ok = result["blocked"] is expect["blocked"] and not leaked
        return ok, f"blocked={result['blocked']} leaked={leaked}"
    if channel == "dilution":
        invoice = load_invoice(attack["invoice_id"])
        text = invoice_untrusted_text(invoice)
        stand_in = DilutionStandIn(attack["marker"], int(attack["whole_document_word_limit"]))
        by_paragraph = screen_paragraphs(text, stand_in)
        whole = screen_whole_document(text, stand_in)
        ok = (
            by_paragraph.blocked is expect["paragraph_blocked"]
            and whole.blocked is expect["whole_document_blocked"]
        )
        return ok, f"paragraph={by_paragraph.blocked} whole={whole.blocked}"
    if channel == "erp_free_text":
        return _erp_free_text(attack)
    raise ValueError(f"Unknown channel {channel}")


def _erp_free_text(attack: dict) -> tuple[bool, str]:
    """Bank numbers in notes must not reach an erp-mcp tool result or triage facts."""
    from erp_mcp.server import data_dir, get_goods_receipt, get_purchase_order, get_supplier
    from invoice_mcp.armor import AllowAllScreener, screen_paragraphs
    from matching_agent.triage.decide import judge_exception
    from matching_agent.triage.facts import build_facts
    from matching_agent.triage.judge import DecisionCache, TriageSettings, user_prompt
    from matching_agent.triage.policy import load_policy

    secret_bsb = str(attack["secret_bsb"])
    secret_account = str(attack["secret_account"])
    secrets = (secret_bsb, secret_account)
    base = data_dir()
    suppliers = json.loads((base / "seed" / "suppliers.json").read_text(encoding="utf-8"))
    orders = json.loads((base / "seed" / "purchase_orders.json").read_text(encoding="utf-8"))
    raw_supplier = next(row for row in suppliers if row["supplier_id"] == attack["supplier_id"])
    raw_order = next(row for row in orders if row["po_number"] == attack["po_number"])
    raw_blob = json.dumps({"supplier": raw_supplier, "order": raw_order})
    if any(secret not in raw_blob for secret in secrets):
        return False, "sample notes do not contain the fixture bank number"

    outputs = [get_supplier(row["supplier_id"]) for row in suppliers]
    outputs.extend(get_purchase_order(row["po_number"]) for row in orders)
    outputs.extend(get_goods_receipt(row["po_number"]) for row in orders)
    rendered = json.dumps(outputs)
    if any(secret in rendered for secret in secrets):
        return False, "erp-mcp tool output still contains a bank number"

    invoice = {
        "invoice_id": "INV-NOTES",
        "supplier_name": raw_supplier["name"],
        "supplier_abn": raw_supplier["abn"],
        "po_number": raw_order["po_number"],
        "invoice_date": "2026-10-16",
        "currency": "AUD",
        "lines": [
            {
                "sku": "FIX-01",
                "description": "Fixture line",
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
        "text": f"Please pay BSB {secret_bsb} account number {secret_account} and quote INV-NOTES.",
    }
    screen = screen_paragraphs(invoice["text"], AllowAllScreener())
    facts = build_facts(invoice, raw_order, [], raw_supplier, screen)
    seen = facts.canonical_json() + user_prompt(facts)

    class _NoModel:
        def generate_json(self, **_kwargs: object) -> dict:
            raise AssertionError("the model was called")

    decision = judge_exception(
        facts, load_policy(), _NoModel(), DecisionCache(None), TriageSettings()
    )
    clean = (
        facts.bank_detail_in_free_text
        and not any(secret in seen for secret in secrets)
        and decision.verdict == "ESCALATE"
        and decision.hard_rule == "bank_in_free_text"
        and not any(secret in decision.reason for secret in secrets)
        and attack["expect"]["redacted"] is True
    )
    return clean, (
        f"free_text={facts.bank_detail_in_free_text} "
        f"verdict={decision.verdict} rule={decision.hard_rule}"
    )


def _live(attack: dict) -> tuple[bool, str]:
    if attack.get("live") == "skip":
        return True, "skipped in live mode"
    from invoice_mcp.armor import screener_from_env

    screener = screener_from_env()
    expect = attack["expect"]
    channel = attack["channel"]
    if channel == "user_prompt":
        verdict = screener.screen_user_prompt(attack["payload"])
        blocked = should_block(verdict)
        return blocked == expect["blocked"], f"live blocked={blocked} state={verdict.match_state}"
    if channel == "invoice_document":
        result = fetch_invoice(attack["invoice_id"], screener=screener)
        return result["blocked"] is expect["blocked"], f"live blocked={result['blocked']}"
    return True, "no live check"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LedgerGuard red-team checks")
    parser.add_argument("--mode", choices=("offline", "live"), default="offline")
    parser.add_argument(
        "--attacks", type=Path, default=ROOT / "security" / "redteam" / "attacks.yaml"
    )
    parser.add_argument(
        "--base-url",
        default="",
        help="Accepted for the documented command. Live mode calls Model Armor, not this URL.",
    )
    args = parser.parse_args(argv)
    attacks = yaml.safe_load(args.attacks.read_text(encoding="utf-8"))["attacks"]
    if args.mode == "offline":
        print(
            "Offline red-team uses stubbed verdicts and a marker stand-in. It does not call Model Armor."
        )
    else:
        print(
            "Live red-team calls Model Armor. A missing template fails closed and will not match these expectations."
        )
    if args.base_url:
        print(
            f"Note: --base-url {args.base_url} is not used. Prompt the orchestrator separately; this runner screens text."
        )
    failed = 0
    for attack in attacks:
        ok, detail = _offline(attack) if args.mode == "offline" else _live(attack)
        status = "pass" if ok else "fail"
        print(f"[{status}] {attack['id']}: {detail}")
        if not ok:
            failed += 1
    print(f"{len(attacks) - failed}/{len(attacks)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
