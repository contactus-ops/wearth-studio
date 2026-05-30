# -*- coding: utf-8 -*-
"""Google Sheets + Drive helpers for WEARTH Growth Dashboard."""
from __future__ import annotations

import os
from typing import Any

from google_engine import (
    DRIVE_FOLDER_MIME,
    _google_services,
    _list_drive_children,
    _sheet_values,
)

GROWTH_SHEET_TITLE = "WEARTH Growth Dashboard"

TAB_META = "Meta Ads Daily"
TAB_SHOPIFY = "Shopify Daily"
TAB_KLAVIYO = "Klaviyo Campaigns"
TAB_CREATIVE = "Creative Registry"
TAB_SNAPSHOTS = "Website Snapshots Log"
TAB_CLARITY = "Clarity Heatmaps Log"

META_HEADERS = [
    "date",
    "campaign_name",
    "ad_set_name",
    "ad_name",
    "ad_id",
    "status",
    "daily_spend_inr",
    "impressions",
    "reach",
    "cpm",
    "ctr",
    "link_clicks",
    "cost_per_link_click",
    "atc_count",
    "cost_per_atc",
    "purchase_count",
    "purchase_roas",
    "amount_spent_to_date_inr",
    "synced_at_utc",
]

SHOPIFY_HEADERS = [
    "date",
    "sessions",
    "unique_visitors",
    "bounce_rate",
    "top_5_landing_pages",
    "top_5_exit_pages",
    "conversion_rate",
    "atc_rate",
    "checkout_initiation_rate",
    "purchase_rate",
    "revenue_inr",
    "average_order_value_inr",
    "top_5_products_by_views",
    "top_5_products_by_atc",
    "data_source_note",
    "synced_at_utc",
]

KLAVIYO_HEADERS = [
    "campaign_name",
    "send_date",
    "recipients",
    "open_rate",
    "click_rate",
    "revenue_attributed_inr",
    "unsubscribe_rate",
    "synced_at_utc",
]

CREATIVE_HEADERS = [
    "creative_filename",
    "google_drive_link",
    "campaign_assigned_to",
    "ad_set_assigned_to",
    "date_uploaded",
    "format",
    "current_status",
    "meta_ad_id",
    "notes",
]

SNAPSHOT_HEADERS = [
    "timestamp_utc",
    "page_label",
    "url",
    "viewport",
    "drive_folder",
    "screenshot_link",
]

CLARITY_HEADERS = [
    "timestamp_utc",
    "page_name",
    "page_url",
    "drive_folder",
    "heatmap_link",
    "scroll_depth_link",
    "notes",
]


def growth_sheet_id() -> str:
    return (os.environ.get("GROWTH_DASHBOARD_SHEET_ID") or os.environ.get("GOOGLE_SHEET_ID") or "").strip()


def drive_growth_root_id() -> str:
    return (
        os.environ.get("GROWTH_DRIVE_ROOT_FOLDER_ID")
        or os.environ.get("GOOGLE_DRIVE_PARENT_FOLDER_ID")
        or os.environ.get("DRIVE_PARENT_FOLDER_ID")
        or ""
    ).strip()


def tab_title_to_range(title: str) -> str:
    safe = title.replace("'", "''")
    return f"'{safe}'"


def ensure_growth_sheet(sheets) -> dict[str, Any]:
    """Create spreadsheet + tabs if GROWTH_DASHBOARD_SHEET_ID unset; return sheet id + tab map."""
    sid = growth_sheet_id()
    if sid:
        meta = sheets.spreadsheets().get(spreadsheetId=sid).execute()
        return {"sheet_id": sid, "title": (meta.get("properties") or {}).get("title"), "created": False}

    body = {
        "properties": {"title": GROWTH_SHEET_TITLE},
        "sheets": [
            {"properties": {"title": t}}
            for t in (
                TAB_META,
                TAB_SHOPIFY,
                TAB_KLAVIYO,
                TAB_CREATIVE,
                TAB_SNAPSHOTS,
                TAB_CLARITY,
            )
        ],
    }
    created = sheets.spreadsheets().create(body=body).execute()
    sid = created["spreadsheetId"]
    return {"sheet_id": sid, "title": GROWTH_SHEET_TITLE, "created": True}


def ensure_tab_headers(sheets, sheet_id: str, tab: str, headers: list[str]) -> None:
    rng = f"{tab_title_to_range(tab)}!1:1"
    rows = _sheet_values(sheets, sheet_id, rng)
    if rows and rows[0][: len(headers)] == headers:
        return
    sheets.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=rng,
        valueInputOption="RAW",
        body={"values": [headers]},
    ).execute()


def append_rows(sheets, sheet_id: str, tab: str, rows: list[list]) -> int:
    if not rows:
        return 0
    sheets.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range=f"{tab_title_to_range(tab)}!A:A",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": rows},
    ).execute()
    return len(rows)


def replace_tab(sheets, sheet_id: str, tab: str, headers: list[str], rows: list[list]) -> None:
    rng = tab_title_to_range(tab)
    sheets.spreadsheets().values().clear(spreadsheetId=sheet_id, range=f"{rng}!A:Z").execute()
    sheets.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=f"{rng}!1:1",
        valueInputOption="RAW",
        body={"values": [headers]},
    ).execute()
    if rows:
        append_rows(sheets, sheet_id, tab, rows)


def ensure_drive_folder(drive, name: str, parent_id: str) -> dict[str, str]:
    children = _list_drive_children(drive, parent_id, DRIVE_FOLDER_MIME)
    for c in children:
        if (c.get("name") or "").strip() == name:
            return {"id": c["id"], "name": name, "link": c.get("webViewLink") or f"https://drive.google.com/drive/folders/{c['id']}"}
    meta = {
        "name": name,
        "mimeType": DRIVE_FOLDER_MIME,
        "parents": [parent_id],
    }
    folder = drive.files().create(body=meta, fields="id, webViewLink", supportsAllDrives=True).execute()
    return {
        "id": folder["id"],
        "name": name,
        "link": folder.get("webViewLink") or f"https://drive.google.com/drive/folders/{folder['id']}",
    }


def upload_file_to_folder(drive, folder_id: str, local_path: str, mime: str) -> dict[str, str]:
    from pathlib import Path

    p = Path(local_path)
    meta = {"name": p.name, "parents": [folder_id]}
    media = None
    from googleapiclient.http import MediaFileUpload

    media = MediaFileUpload(str(p), mimetype=mime, resumable=True)
    f = (
        drive.files()
        .create(body=meta, media_body=media, fields="id, webViewLink, webContentLink", supportsAllDrives=True)
        .execute()
    )
    fid = f["id"]
    link = f.get("webViewLink") or f"https://drive.google.com/file/d/{fid}/view"
    return {"id": fid, "link": link, "name": p.name}


def sheet_url(sheet_id: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit"
