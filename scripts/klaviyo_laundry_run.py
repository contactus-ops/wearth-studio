# -*- coding: utf-8 -*-
"""Run Klaviyo laundry immediately (suppress cold; protect top warm 200)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

for ln in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
    ln = ln.strip()
    if ln and not ln.startswith("#") and "=" in ln:
        k, v = ln.split("=", 1)
        os.environ[k] = v

os.environ.setdefault("KLAVIYO_HOT_TOP_N", "200")

from klaviyo_engine import active_count, always_suppress_emails, suppress_cold_run


def main() -> int:
    forced = sorted(always_suppress_emails())
    print("forced_suppress_count", len(forced))
    before = active_count(bypass_cache=True)
    print("active_count_before", json.dumps(before, indent=2))
    result = suppress_cold_run(dry_run=False, payload_in={})
    print("laundry_result", json.dumps(result, indent=2))
    after = active_count(bypass_cache=True)
    print("active_count_after", json.dumps(after, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
