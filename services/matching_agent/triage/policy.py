"""Parse a trusted accounts-payable policy into citable labels.

``parse_policy`` follows ParsePolicy in the Algorithmic Triage reference
(https://github.com/geekaara/algorithmic-triage, MIT). Every line a model
might cite gets a stable label such as ``reject-2``. A label that is not in
the parsed set is not a rule.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

_NUMBERED = re.compile(r"^\d+\.\s+(.*)$")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_VERSION = re.compile(r"(?m)^Version:\s*(\S+)\s*$")

_KINDS = {
    "auto-approve": "Auto-approve",
    "hold": "Hold",
    "reject": "Reject",
    "always-escalate": "Always escalate",
    "rule": "Triage rule",
}


@dataclass
class Policy:
    """Citable lines of a policy file. ``text`` is the trusted source."""

    version: str
    lines: dict[str, str]
    order: list[str] = field(default_factory=list)
    text: str = ""

    def describe(self, label: str) -> str:
        text = self.lines.get(label)
        if text is None:
            return label
        prefix = label.rsplit("-", 1)[0]
        kind = _KINDS.get(prefix, prefix)
        return f"{kind}: {text}"

    def label_block(self) -> str:
        return "\n".join(f"{label}: {self.lines[label]}" for label in self.order)


def section_prefix(heading: str) -> str:
    """Map a markdown heading to a label prefix. Empty means not citable."""
    lowered = heading.lower()
    if "auto-approve" in lowered or "auto approve" in lowered:
        return "auto-approve"
    if "always-escalate" in lowered or "always escalate" in lowered:
        return "always-escalate"
    if "reject" in lowered:
        return "reject"
    if re.search(r"\bhold\b", lowered):
        return "hold"
    if "rule" in lowered:
        return "rule"
    return ""


def parse_policy(md: str) -> Policy:
    """Read auto-approve, hold, reject, always-escalate, and triage-rule lines.

    Wrapped list items are joined so each bullet is one label. Numbering is
    per prefix, in document order, starting at 1 (``reject-2`` is the second
    reject bullet).
    """
    policy = Policy(version="", lines={}, order=[], text=md)
    version = _VERSION.search(md)
    if version:
        policy.version = version.group(1)

    items: list[str] = []
    for line in md.split("\n"):
        stripped = line.strip()
        if stripped.startswith("#") or stripped == "":
            items.append(stripped)
        elif stripped.startswith("- ") or _NUMBERED.match(stripped):
            items.append(stripped)
        elif items and items[-1] != "" and not items[-1].startswith("#"):
            items[-1] += " " + stripped
        else:
            items.append(stripped)

    section = ""

    def add(prefix: str, text: str) -> None:
        text = _BOLD.sub(r"\1", text).strip()
        if not text:
            return
        number = 1 + sum(1 for label in policy.order if label.startswith(prefix + "-"))
        label = f"{prefix}-{number}"
        policy.lines[label] = text
        policy.order.append(label)

    for item in items:
        if item.startswith("#"):
            section = section_prefix(item)
            continue
        numbered = _NUMBERED.match(item)
        if numbered:
            text = numbered.group(1)
        elif item.startswith("- "):
            text = item[2:]
        else:
            continue
        if section:
            add(section, text)
    return policy


# The reference implementation names this ParsePolicy. Keep that name importable.
ParsePolicy = parse_policy


def default_policy_path() -> Path:
    env = os.environ.get("LEDGERGUARD_POLICY_PATH")
    if env:
        return Path(env)
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "policy" / "ap-policy.md"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        "policy/ap-policy.md was not found. Set LEDGERGUARD_POLICY_PATH to the trusted policy file."
    )


def load_policy(path: Path | None = None) -> Policy:
    policy_path = path or default_policy_path()
    return parse_policy(policy_path.read_text(encoding="utf-8"))
