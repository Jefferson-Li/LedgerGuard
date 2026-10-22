"""Dry-run by default. Writes synthetic seed documents to Firestore only with --apply.

The running services read the JSON files in data/. This script is the unfinished
bridge to Firestore and is not used by the MCP servers yet.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed Firestore with the synthetic dataset")
    parser.add_argument(
        "--apply", action="store_true", help="Write documents. Default is a dry run."
    )
    parser.add_argument("--collection-prefix", default="ledgerguard")
    args = parser.parse_args()

    seed = ROOT / "data" / "seed"
    invoices = sorted((ROOT / "data" / "invoices").glob("INV-*.json"))
    print(f"Would write {len(list(seed.glob('*.json')))} seed files and {len(invoices)} invoices")
    print(f"Collection prefix: {args.collection_prefix}")
    if not args.apply:
        print("Dry run. Pass --apply to write. The MCP servers do not read Firestore yet.")
        return 0

    try:
        from google.cloud import firestore
    except ImportError:
        print("google-cloud-firestore is not installed.", file=sys.stderr)
        return 1

    client = firestore.Client()
    for path in sorted(seed.glob("*.json")):
        rows = json.loads(path.read_text(encoding="utf-8"))
        collection = f"{args.collection_prefix}_{path.stem}"
        for row in rows:
            doc_id = row.get("po_number") or row.get("grn_number") or row.get("supplier_id")
            client.collection(collection).document(str(doc_id)).set(row)
            print(f"wrote {collection}/{doc_id}")
    for path in invoices:
        row = json.loads(path.read_text(encoding="utf-8"))
        client.collection(f"{args.collection_prefix}_invoices").document(row["invoice_id"]).set(row)
        print(f"wrote invoice {row['invoice_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
