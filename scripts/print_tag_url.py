"""Print the Cloud Run URL for a tagged revision.

Usage: python scripts/print_tag_url.py SERVICE REGION [TAG]
"""

from __future__ import annotations

import json
import subprocess
import sys


def main() -> int:
    service, region = sys.argv[1], sys.argv[2]
    tag = sys.argv[3] if len(sys.argv) > 3 else "green"
    raw = subprocess.check_output(
        ["gcloud", "run", "services", "describe", service, "--region", region, "--format=json"],
        text=True,
    )
    payload = json.loads(raw)
    for item in payload.get("status", {}).get("traffic", []):
        if item.get("tag") == tag and item.get("url"):
            print(item["url"])
            return 0
    print(f"No URL for tag {tag} on {service}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
