import json
from pathlib import Path


def test_evalset_has_the_draft_cases():
    path = Path(__file__).resolve().parents[2] / "evals" / "ap.evalset.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["eval_set_id"] == "ledgerguard-ap"
    ids = [case["eval_id"] for case in payload["eval_cases"]]
    assert ids == ["acme-exceptions", "do-not-leak-quarantined-invoice"]
    for case in payload["eval_cases"]:
        turn = case["conversation"][0]
        assert turn["user_content"]["parts"][0]["text"]
        assert turn["final_response"]["parts"][0]["text"]
        assert case["session_input"]["app_name"] == "ap_orchestrator"
