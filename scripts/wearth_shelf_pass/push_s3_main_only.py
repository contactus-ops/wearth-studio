#!/usr/bin/env python3
"""Push only main-product.liquid for S3 (CSS already live)."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "wearth_pdp_v2"))
sys.path.insert(0, str(ROOT / "scripts" / "wearth_shelf_pass"))
from theme_api import ThemeApi
from push_s3_sticky_bag import backup_and_diff, patch_main_product

LIVE = "140256739508"


def main() -> int:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    api = ThemeApi(LIVE)
    key = "sections/main-product.liquid"
    live = api.get_asset(key)
    patched = patch_main_product(live)
    backup_and_diff(key, live, patched, stamp)
    api.put_asset(key, patched)
    print(f"PUSHED {key} ({len(live)} -> {len(patched)})")
    report = {
        "step": "S3",
        "stamp": stamp,
        "note": "main-product only; foundation CSS already pushed",
        "files": [{"file": key, "bytes_before": len(live), "bytes_after": len(patched)}],
    }
    path = ROOT / "data" / "wearth_shelf_pass" / f"report_S3_main_{stamp}.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
