"""CLI: plan, apply, and reset exception triage.

``plan`` writes a JSON plan and prints a table. It does not record decisions.
``apply`` records the plan in the local store. Firestore stays a dry run
unless ``--firestore-apply`` is passed. ``reset`` previews unless ``-yes``.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from matching_agent.triage.judge import DecisionCache
from matching_agent.triage.plan import (
    apply_plan,
    build_plan,
    format_table,
    read_plan,
    reset_decisions,
    write_plan,
)
from matching_agent.triage.store import FirestoreSink, LocalDecisionStore


def default_plan_path() -> Path:
    return Path(os.environ.get("LEDGERGUARD_TRIAGE_PLAN", "tmp/triage-plan.json"))


def default_store_path() -> Path:
    return Path(os.environ.get("LEDGERGUARD_TRIAGE_STORE", "tmp/triage-decisions.json"))


def default_cache_dir() -> Path:
    return Path(os.environ.get("LEDGERGUARD_TRIAGE_CACHE", "tmp/triage-cache"))


def _sink(collection: str, firestore_apply: bool) -> FirestoreSink | None:
    name = collection or os.environ.get("LEDGERGUARD_FIRESTORE_DECISIONS", "").strip()
    if not name:
        return None
    return FirestoreSink(name, apply_writes=firestore_apply)


def _print_apply(result: dict, firestore_apply: bool) -> None:
    print(f"Recorded {result['stored']} decisions in {result['store']}")
    if not result["firestore_collection"]:
        print("Firestore was not configured. The local store is the only record.")
        return
    if firestore_apply and result["firestore_applied"]:
        print(
            f"Wrote {len(result['firestore_preview'])} documents to "
            f"{result['firestore_collection']}."
        )
        return
    print(
        f"Firestore dry run for {result['firestore_collection']}: "
        f"{len(result['firestore_preview'])} documents would be written. "
        "Pass --firestore-apply to write them."
    )


def _print_reset(result: dict, firestore_apply: bool) -> None:
    if not result["applied"]:
        preview = result["preview"]
        print(f"Would remove {len(preview)} decisions. Pass -yes to remove them.")
        for invoice_id in preview:
            print(f"  {invoice_id}")
        return
    print(f"Removed {len(result['removed'])} decisions.")
    collection = result.get("firestore_collection") or ""
    if not collection:
        return
    if firestore_apply and result["firestore_applied"]:
        print(f"Deleted those documents from {collection}.")
        return
    print(
        f"Firestore dry run for {collection}: {len(result['removed'])} documents would be deleted. "
        "Pass -yes and --firestore-apply together to delete them."
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="triage", description="Accounts-payable exception triage")
    sub = parser.add_subparsers(dest="command", required=True)

    plan_cmd = sub.add_parser("plan", help="Write a reviewable plan. Changes nothing.")
    plan_cmd.add_argument("--out", type=Path, default=None)
    plan_cmd.add_argument("--policy", type=Path, default=None)
    plan_cmd.add_argument("--cache", type=Path, default=None)
    plan_cmd.add_argument("--data", type=Path, default=None)

    apply_cmd = sub.add_parser("apply", help="Record the plan in the local store.")
    apply_cmd.add_argument("--plan", type=Path, default=None)
    apply_cmd.add_argument("--store", type=Path, default=None)
    apply_cmd.add_argument("--firestore-collection", default="")
    apply_cmd.add_argument(
        "--firestore-apply",
        action="store_true",
        help="Write the Firestore collection. Default is a dry run.",
    )

    reset_cmd = sub.add_parser("reset", help="Undo apply. Previews unless -yes is passed.")
    reset_cmd.add_argument("-yes", action="store_true", help="Delete the recorded decisions.")
    reset_cmd.add_argument("--store", type=Path, default=None)
    reset_cmd.add_argument("--firestore-collection", default="")
    reset_cmd.add_argument(
        "--firestore-apply",
        action="store_true",
        help="Also delete Firestore documents. Requires -yes. Default is a dry run.",
    )

    args = parser.parse_args(argv)
    if args.command == "plan":
        from matching_agent.triage.policy import load_policy

        policy = load_policy(args.policy)
        cache_dir = args.cache or default_cache_dir()
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            cache = DecisionCache(None)
        else:
            cache = DecisionCache(cache_dir)
        plan = build_plan(policy=policy, data_dir=args.data, cache=cache)
        out = args.out or default_plan_path()
        write_plan(plan, out)
        print(format_table(plan.rows))
        print()
        print(f"Wrote {out}. The decision store was not changed.")
        if plan.screener == "marker-stand-in" or plan.judge == "stub":
            print("Offline stand-in. This run did not call Model Armor or Gemini.")
        return 0

    if args.command == "apply":
        plan_path = args.plan or default_plan_path()
        if not plan_path.is_file():
            print(f"No plan at {plan_path}. Run plan first.")
            return 1
        plan = read_plan(plan_path)
        store = LocalDecisionStore(args.store or default_store_path())
        sink = _sink(args.firestore_collection, args.firestore_apply)
        result = apply_plan(plan, store, sink)
        _print_apply(result, args.firestore_apply)
        return 0

    store = LocalDecisionStore(args.store or default_store_path())
    sink = _sink(args.firestore_collection, args.firestore_apply and args.yes)
    result = reset_decisions(store, yes=args.yes, sink=sink)
    _print_reset(result, args.firestore_apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
