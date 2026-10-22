"""Run exception triage from the repository root.

Examples:
  uv run python scripts/triage.py plan
  uv run python scripts/triage.py apply
  uv run python scripts/triage.py reset
  uv run python scripts/triage.py reset -yes
"""

from __future__ import annotations


def main() -> int:
    import sys
    from pathlib import Path

    services = Path(__file__).resolve().parents[1] / "services"
    if str(services) not in sys.path:
        sys.path.insert(0, str(services))
    from matching_agent.triage.__main__ import main as triage_main

    return triage_main()


if __name__ == "__main__":
    raise SystemExit(main())
