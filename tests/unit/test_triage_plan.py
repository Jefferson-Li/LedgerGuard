"""Plan, apply, and reset. INV-1010 is escalated and never approved."""

import json

from invoice_mcp.armor import UnavailableScreener
from matching_agent.triage.__main__ import main
from matching_agent.triage.facts import load_catalog
from matching_agent.triage.gemini import StubGeminiModel
from matching_agent.triage.judge import DecisionCache
from matching_agent.triage.plan import (
    apply_plan,
    build_plan,
    plan_invoice,
    read_plan,
    reset_decisions,
)
from matching_agent.triage.screen import INJECTION_MARKER, MarkerScreener
from matching_agent.triage.store import FirestoreSink, LocalDecisionStore


class ApproveAll:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def generate_json(self, *, model: str, system: str, user: str, schema: dict) -> dict:
        self.calls.append({"model": model, "user": user, "schema": schema})
        return {
            "reason": "Looks payable.",
            "rule": "auto-approve-1",
            "verdict": "APPROVE",
            "confidence": 0.99,
            "variance": "999.00",
        }


class FakeClient:
    def __init__(self) -> None:
        self.docs: dict[str, dict] = {}

    def collection(self, _name: str):
        return self

    def document(self, doc_id: str):
        client = self

        class _Doc:
            def set(self, document: dict) -> None:
                client.docs[doc_id] = document

            def delete(self) -> None:
                client.docs.pop(doc_id, None)

        return _Doc()


def _by_id(plan) -> dict[str, dict]:
    return {row["invoice_id"]: row for row in plan.rows}


def test_inv_1010_is_escalated_and_never_approved():
    model = ApproveAll()
    plan = build_plan(
        model=model,
        screener=MarkerScreener(INJECTION_MARKER),
        screener_name="marker-stand-in",
        cache=DecisionCache(None),
    )
    row = _by_id(plan)["INV-1010"]
    assert row["verdict"] == "ESCALATE"
    assert row["verdict"] != "APPROVE"
    assert row["hard_rule"] == "model_armor"
    assert row["rule"] == "always-escalate-2"
    assert row["judged"] is False
    blob = json.dumps(plan.as_dict())
    assert INJECTION_MARKER not in blob
    assert all(INJECTION_MARKER not in call["user"] for call in model.calls)
    judged = {item["invoice_id"] for item in plan.rows if item["judged"]}
    assert judged == {"INV-1002", "INV-1003", "INV-1004", "INV-1005", "INV-1007", "INV-1008"}
    assert "INV-1001" not in judged
    assert "INV-1006" not in judged


def test_offline_stub_uses_code_variance_and_policy_labels():
    model = StubGeminiModel()
    plan = build_plan(
        model=model,
        screener=MarkerScreener(INJECTION_MARKER),
        screener_name="marker-stand-in",
        cache=DecisionCache(None),
    )
    rows = _by_id(plan)
    assert rows["INV-1003"]["variance"] == "1.50"
    assert rows["INV-1003"]["verdict"] == "REJECT"
    assert rows["INV-1003"]["rule"] == "reject-3"
    assert rows["INV-1003"]["judged"] is True
    assert "999" not in rows["INV-1003"]["variance"]
    assert rows["INV-1006"]["variance"] == "0.40"
    assert rows["INV-1006"]["verdict"] == "APPROVE"
    assert rows["INV-1006"]["rule"] == "auto-approve-1"
    assert rows["INV-1006"]["model"] == "code"
    assert rows["INV-1006"]["judged"] is False
    assert rows["INV-1002"]["verdict"] == "HOLD"
    assert rows["INV-1002"]["rule"] == "hold-2"
    assert rows["INV-1004"]["rule"] == "reject-4"
    assert rows["INV-1008"]["rule"] == "reject-2"
    assert rows["INV-1010"]["verdict"] == "ESCALATE"
    assert plan.as_dict()["variance_computed_by"] == "code"


def test_screening_failure_fails_closed():
    model = ApproveAll()
    plan = build_plan(
        model=model,
        screener=UnavailableScreener(),
        screener_name="fail-closed",
        cache=DecisionCache(None),
    )
    assert model.calls == []
    assert plan.rows
    assert {row["verdict"] for row in plan.rows} == {"ESCALATE"}
    assert all(row["verdict"] != "APPROVE" for row in plan.rows)


def test_plan_apply_reset_are_idempotent(tmp_path):
    cache = DecisionCache(tmp_path / "cache")
    model = StubGeminiModel()
    screener = MarkerScreener(INJECTION_MARKER)
    plan = build_plan(model=model, screener=screener, cache=cache)
    calls = len(model.calls)
    again = build_plan(model=model, screener=screener, cache=cache)
    assert len(model.calls) == calls
    assert plan.as_dict() == again.as_dict()

    store = LocalDecisionStore(tmp_path / "decisions.json")
    assert not store.path.exists()
    apply_plan(plan, store)
    first = store.path.read_text(encoding="utf-8")
    apply_plan(plan, store)
    assert store.path.read_text(encoding="utf-8") == first
    assert set(store.load()["decisions"]) == set(load_catalog()["invoices"])

    preview = reset_decisions(store, yes=False)
    assert preview["applied"] is False
    assert preview["removed"] == []
    assert store.path.read_text(encoding="utf-8") == first

    undone = reset_decisions(store, yes=True)
    assert undone["applied"] is True
    assert store.load()["decisions"] == {}
    again_reset = reset_decisions(store, yes=True)
    assert again_reset["removed"] == []
    assert store.load()["decisions"] == {}


def test_firestore_apply_is_dry_run_unless_requested(tmp_path):
    plan = build_plan(
        model=StubGeminiModel(),
        screener=MarkerScreener(INJECTION_MARKER),
        cache=DecisionCache(tmp_path / "cache"),
    )
    client = FakeClient()
    store = LocalDecisionStore(tmp_path / "decisions.json")
    dry = FirestoreSink("ledgerguard_triage_decisions", apply_writes=False, client=client)
    result = apply_plan(plan, store, dry)
    assert result["firestore_applied"] is False
    assert client.docs == {}
    assert len(dry.preview) == len(plan.rows)

    live = FirestoreSink("ledgerguard_triage_decisions", apply_writes=True, client=client)
    apply_plan(plan, store, live)
    apply_plan(plan, store, live)
    assert set(client.docs) == {row["invoice_id"] for row in plan.rows}
    assert client.docs["INV-1003"]["variance"] == "1.50"
    assert client.docs["INV-1010"]["verdict"] == "ESCALATE"

    reset_decisions(store, yes=True, sink=dry)
    assert "INV-1010" in client.docs
    reset_decisions(store, yes=False, sink=live)
    assert "INV-1010" in client.docs
    # The previous -yes already cleared the local store, so reload and delete for real.
    apply_plan(plan, store)
    reset_decisions(store, yes=True, sink=live)
    assert client.docs == {}


def test_cli_plan_apply_reset(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("MODEL_ARMOR_PROMPT_TEMPLATE", raising=False)
    monkeypatch.delenv("MODEL_ARMOR_TEMPLATE", raising=False)
    monkeypatch.setenv("LEDGERGUARD_TRIAGE_JUDGE", "stub")
    plan_path = tmp_path / "plan.json"
    store_path = tmp_path / "decisions.json"
    cache_path = tmp_path / "cache"
    assert main(["plan", "--out", str(plan_path), "--cache", str(cache_path)]) == 0
    printed = capsys.readouterr().out
    assert "INV-1010" in printed
    assert "ESCALATE" in printed
    assert "1.50" in printed
    assert "VARIANCE" in printed
    assert not store_path.exists()
    payload = json.loads(plan_path.read_text(encoding="utf-8"))
    assert INJECTION_MARKER not in plan_path.read_text(encoding="utf-8")
    assert read_plan(plan_path).rows[0]["invoice_id"].startswith("INV-")

    assert main(["apply", "--plan", str(plan_path), "--store", str(store_path)]) == 0
    first = store_path.read_text(encoding="utf-8")
    assert main(["apply", "--plan", str(plan_path), "--store", str(store_path)]) == 0
    assert store_path.read_text(encoding="utf-8") == first

    assert main(["reset", "--store", str(store_path)]) == 0
    assert store_path.read_text(encoding="utf-8") == first
    assert main(["reset", "-yes", "--store", str(store_path)]) == 0
    assert json.loads(store_path.read_text(encoding="utf-8"))["decisions"] == {}
    assert payload["rows"]


def test_agent_tool_fails_closed_on_inv_1010(monkeypatch):
    monkeypatch.delenv("MODEL_ARMOR_PROMPT_TEMPLATE", raising=False)
    monkeypatch.delenv("MODEL_ARMOR_TEMPLATE", raising=False)
    monkeypatch.delenv("MODEL_ARMOR_ALLOW_UNSCREENED", raising=False)
    monkeypatch.setenv("LEDGERGUARD_TRIAGE_JUDGE", "stub")
    row = plan_invoice("INV-1010")
    assert row["verdict"] == "ESCALATE"
    assert row["verdict"] != "APPROVE"
    assert INJECTION_MARKER not in json.dumps(row)
    assert plan_invoice("INV-1001")["verdict"] == "ESCALATE"
