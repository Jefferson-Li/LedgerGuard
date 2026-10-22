"""Plan value type, kept separate so the store can import it without a cycle."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Plan:
    policy_version: str
    policy_sha256: str
    confidence_threshold: float
    screener: str
    judge: str
    rows: list[dict]

    def as_dict(self) -> dict:
        return {
            "policy_version": self.policy_version,
            "policy_sha256": self.policy_sha256,
            "confidence_threshold": self.confidence_threshold,
            "screener": self.screener,
            "judge": self.judge,
            "variance_computed_by": "code",
            "rows": self.rows,
        }
