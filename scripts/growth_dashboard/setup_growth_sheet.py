#!/usr/bin/env python3
"""Create WEARTH Growth Dashboard sheet + headers; print sheet ID for Railway env."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from growth_dashboard.google_client import (
    CLARITY_HEADERS,
    CREATIVE_HEADERS,
    KLAVIYO_HEADERS,
    META_HEADERS,
    SHOPIFY_HEADERS,
    TAB_CLARITY,
    TAB_CREATIVE,
    TAB_KLAVIYO,
    TAB_META,
    TAB_SHOPIFY,
    TAB_SNAPSHOTS,
    SNAPSHOT_HEADERS,
    _google_services,
    ensure_growth_sheet,
    ensure_tab_headers,
    sheet_url,
)


def main() -> int:
    _, sheets, drive = _google_services()
    setup = ensure_growth_sheet(sheets, drive)
    sid = setup["sheet_id"]
    for tab, headers in (
        (TAB_META, META_HEADERS),
        (TAB_SHOPIFY, SHOPIFY_HEADERS),
        (TAB_KLAVIYO, KLAVIYO_HEADERS),
        (TAB_CREATIVE, CREATIVE_HEADERS),
        (TAB_SNAPSHOTS, SNAPSHOT_HEADERS),
        (TAB_CLARITY, CLARITY_HEADERS),
    ):
        ensure_tab_headers(sheets, sid, tab, headers)
    print(
        json.dumps(
            {
                "ok": True,
                "created": setup.get("created"),
                "GROWTH_DASHBOARD_SHEET_ID": sid,
                "sheet_url": sheet_url(sid),
                "railway_note": "Set GROWTH_DASHBOARD_SHEET_ID on Railway to this value",
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
