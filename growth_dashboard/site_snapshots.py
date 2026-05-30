# -*- coding: utf-8 -*-
"""Website screenshots → Drive + Tab 5 (Playwright headless)."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from growth_dashboard.google_client import (
    SNAPSHOT_HEADERS,
    TAB_SNAPSHOTS,
    _google_services,
    append_rows,
    drive_growth_root_id,
    ensure_drive_folder,
    ensure_tab_headers,
    growth_sheet_id,
    upload_file_to_folder,
)

BASE = "https://www.wearthactive.com"

PAGES = [
    ("homepage", "/"),
    ("mens-everyday-joggers", "/products/mens-everyday-joggers"),
    ("mens-essential-shorts", "/products/mens-essential-shorts"),
    ("essential-shorts-alias", "/products/essential-shorts"),
    ("biker-shorts", "/products/biker-shorts"),
    ("everyday-joggers-women", "/products/everyday-joggers-women"),
    ("cart", "/cart"),
    ("about", "/pages/about"),
]

VIEWPORTS = [
    ("mobile", 390, 844),
    ("desktop", 1440, 900),
]


def run_site_audit(*, out_dir: Path | None = None) -> dict[str, Any]:
    from playwright.sync_api import sync_playwright

    ts = datetime.now(timezone.utc)
    date_label = ts.strftime("%Y-%m-%d")
    stamp = ts.strftime("%Y%m%dT%H%M%SZ")
    root = out_dir or Path(os.environ.get("TEMP", "/tmp")) / f"wearth_site_audit_{stamp}"
    root.mkdir(parents=True, exist_ok=True)

    parent = drive_growth_root_id()
    if not parent:
        raise RuntimeError("GOOGLE_DRIVE_PARENT_FOLDER_ID or GROWTH_DRIVE_ROOT_FOLDER_ID required")

    _info, sheets, drive = _google_services()
    folder = ensure_drive_folder(drive, f"Site Snapshots / {date_label}", parent)

    sheet_id = growth_sheet_id()
    if not sheet_id:
        from growth_dashboard.google_client import ensure_growth_sheet

        sheet_id = ensure_growth_sheet(sheets, drive)["sheet_id"]
    ensure_tab_headers(sheets, sheet_id, TAB_SNAPSHOTS, SNAPSHOT_HEADERS)

    sheet_rows: list[list] = []
    shots: list[dict] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for vp_name, width, height in VIEWPORTS:
            context = browser.new_context(viewport={"width": width, "height": height})
            page = context.new_page()
            for label, path in PAGES:
                url = BASE + path
                safe = f"{label}_{vp_name}.png".replace("/", "-")
                local = root / safe
                try:
                    page.goto(url, wait_until="networkidle", timeout=90000)
                    page.wait_for_timeout(1500)
                    page.screenshot(path=str(local), full_page=True)
                    up = upload_file_to_folder(drive, folder["id"], str(local), "image/png")
                    sheet_rows.append(
                        [
                            stamp.isoformat().replace("+00:00", "Z"),
                            label,
                            url,
                            vp_name,
                            folder["link"],
                            up["link"],
                        ]
                    )
                    shots.append({"label": label, "viewport": vp_name, "url": url, "link": up["link"]})
                except Exception as e:
                    sheet_rows.append(
                        [
                            stamp.isoformat().replace("+00:00", "Z"),
                            label,
                            url,
                            vp_name,
                            folder["link"],
                            f"ERROR: {e}",
                        ]
                    )
            context.close()
        browser.close()

    n = append_rows(sheets, sheet_id, TAB_SNAPSHOTS, sheet_rows)
    return {
        "ok": True,
        "folder": folder,
        "screenshots": len(shots),
        "sheet_rows_appended": n,
        "local_dir": str(root),
    }
