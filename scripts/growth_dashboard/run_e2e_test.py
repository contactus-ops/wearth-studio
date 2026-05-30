#!/usr/bin/env python3
"""End-to-end test: Meta row, Shopify row, Klaviyo tab, one site screenshot."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

_env = ROOT / ".env"
if _env.exists():
    for ln in _env.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if ln and not ln.startswith("#") and "=" in ln:
            k, v = ln.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

from flask import Flask

from growth_dashboard.google_client import (
    _google_services,
    _sheet_values,
    ensure_growth_sheet,
    growth_sheet_id,
    sheet_url,
)
from growth_dashboard_engine import (
    growth_run_site_audit,
    growth_sync_klaviyo_weekly,
    growth_sync_meta_daily,
    growth_sync_shopify_daily,
)

app = Flask(__name__)


def _json_resp(resp):
    if isinstance(resp, tuple):
        return resp[0].get_json(), resp[1]
    return resp.get_json(), 200


def main() -> int:
    report: dict = {"steps": []}
    _, sheets, _ = _google_services()
    setup = ensure_growth_sheet(sheets)
    os.environ["GROWTH_DASHBOARD_SHEET_ID"] = setup["sheet_id"]
    sid = growth_sheet_id()
    report["sheet_url"] = sheet_url(sid)
    headers = {"X-Wearth-Admin": os.environ.get("ADMIN_TOKEN", "")}

    with app.test_request_context(headers=headers):
        for label, fn in (
            ("meta", growth_sync_meta_daily),
            ("shopify", growth_sync_shopify_daily),
            ("klaviyo", growth_sync_klaviyo_weekly),
        ):
            body, code = _json_resp(fn())
            report["steps"].append({"name": label, "ok": body.get("ok"), "http": code, "body": body})

        from growth_dashboard import site_snapshots as ss

        orig_pages, orig_vp = ss.PAGES, ss.VIEWPORTS
        try:
            ss.PAGES = [("homepage", "/")]
            ss.VIEWPORTS = [("mobile", 390, 844)]
            body, code = _json_resp(growth_run_site_audit())
            report["steps"].append({"name": "site_audit", "ok": body.get("ok"), "http": code, "body": body})
        finally:
            ss.PAGES, ss.VIEWPORTS = orig_pages, orig_vp

    meta_rows = _sheet_values(sheets, sid, "'Meta Ads Daily'!A2:Z")
    shop_rows = _sheet_values(sheets, sid, "'Shopify Daily'!A2:Z")
    klav_rows = _sheet_values(sheets, sid, "'Klaviyo Campaigns'!A2:Z")
    snap_rows = _sheet_values(sheets, sid, "'Website Snapshots Log'!A2:Z")

    report["verify"] = {
        "meta_rows": len(meta_rows),
        "shopify_rows": len(shop_rows),
        "klaviyo_rows": len(klav_rows),
        "snapshot_rows": len(snap_rows),
    }
    report["ok"] = (
        report["verify"]["meta_rows"] >= 1
        and report["verify"]["shopify_rows"] >= 1
        and report["verify"]["snapshot_rows"] >= 1
    )
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
