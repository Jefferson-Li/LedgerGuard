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
    raise ValueError(f"Unknown channel {channel}")


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
