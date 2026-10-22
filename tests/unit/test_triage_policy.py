"""Parser labels for the trusted accounts-payable policy."""

from matching_agent.triage.policy import ParsePolicy, load_policy, parse_policy


def test_parse_policy_is_the_reference_name():
    assert ParsePolicy is parse_policy


def test_shipped_policy_has_stable_labels():
    policy = load_policy()
    assert policy.version == "1"
    assert policy.order[0] == "auto-approve-1"
    assert "within tolerance" in policy.lines["auto-approve-1"]
    assert policy.lines["reject-1"].startswith("An ABN checksum failure")
    assert "unknown supplier" in policy.lines["reject-2"]
    assert "supplier master" in policy.lines["reject-2"]
    assert "outside tolerance" in policy.lines["reject-3"]
    assert "bank-detail" in policy.lines["always-escalate-1"]
    assert "Model Armor" in policy.lines["always-escalate-2"]
    assert policy.lines["always-escalate-3"].startswith("Screening")
    assert "free text" in policy.lines["always-escalate-4"]
    assert "free text" in policy.lines["rule-3"]
    assert [label for label in policy.order if label.startswith("reject-")] == [
        "reject-1",
        "reject-2",
        "reject-3",
        "reject-4",
    ]
    assert "rule-1" in policy.lines
    assert "rule-5" in policy.lines
    assert len(policy.lines) == len(policy.order)


def test_wrapped_bullets_bold_and_non_rules_are_not_labels():
    policy = parse_policy(
        """
Version: 9

This sentence is trusted prose and is not a citable rule.

## Notes

- A bullet outside the fixed headings is not a label.

## Reject conditions

- An **ABN** checksum failure
  continued here.
- Second reject line.

## Hold conditions

- Hold for a person.
"""
    )
    assert policy.version == "9"
    assert policy.lines["reject-1"] == "An ABN checksum failure continued here."
    assert policy.lines["reject-2"] == "Second reject line."
    assert policy.lines["hold-1"] == "Hold for a person."
    assert policy.describe("reject-2") == "Reject: Second reject line."
    assert "notes-1" not in policy.lines
    assert all(not label.startswith("notes") for label in policy.order)
