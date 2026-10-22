"""Policy-driven exception triage inside the matching agent.

AI cites a rule. Code computes amounts, GST, variance, and tolerance.
"""

from matching_agent.triage.policy import ParsePolicy, parse_policy

__all__ = ["ParsePolicy", "parse_policy"]
