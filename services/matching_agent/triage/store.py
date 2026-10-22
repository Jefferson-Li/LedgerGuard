"""Local decision store and an optional Firestore sink.

Firestore writes are dry-run unless ``apply_writes`` is set. The local JSON
file is the record ``apply`` and ``reset`` use in tests and on a laptop.
"""

from __future__ import annotations

import json
from pathlib import Path

from matching_agent.triage.plan_types import Plan


class LocalDecisionStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> dict:
        if not self.path.is_file():
            return {"decisions": {}}
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        payload.setdefault("decisions", {})
        return payload

    def save_plan(self, plan: Plan) -> dict:
        decisions = {row["invoice_id"]: row for row in plan.rows}
        payload = {
            "policy_sha256": plan.policy_sha256,
            "policy_version": plan.policy_version,
            "decisions": decisions,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return payload

    def clear(self) -> list[str]:
        current = self.load()
        ids = sorted(current.get("decisions", {}))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"decisions": {}}, indent=2) + "\n", encoding="utf-8")
        return ids


class FirestoreSink:
    """Preview every write. Call the client only when ``apply_writes`` is true."""

    def __init__(self, collection: str, *, apply_writes: bool, client=None) -> None:
        self.collection = collection
        self.apply_writes = apply_writes
        self.client = client
        self.preview: list[dict] = []

    def write(self, invoice_id: str, document: dict) -> None:
        self.preview.append({"op": "set", "invoice_id": invoice_id})
        if not self.apply_writes:
            return
        self._collection().document(invoice_id).set(document)

    def delete(self, invoice_id: str) -> None:
        self.preview.append({"op": "delete", "invoice_id": invoice_id})
        if not self.apply_writes:
            return
        self._collection().document(invoice_id).delete()

    def _collection(self):
        client = self.client
        if client is None:
            from google.cloud import firestore

            client = firestore.Client()
            self.client = client
        return client.collection(self.collection)
