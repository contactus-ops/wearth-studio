# -*- coding: utf-8 -*-
"""Flask routes for WEARTH Growth Dashboard pipeline (n8n + manual triggers)."""
from __future__ import annotations

import os
from datetime import datetime, timezone

from flask import jsonify, request

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
    append_rows,
    ensure_growth_sheet,
    ensure_tab_headers,
    growth_sheet_id,
    replace_tab,
    sheet_url,
)
from growth_dashboard.google_client import _google_services
from growth_dashboard.alerts import meta_token_expired_alert, send_gmail_alert
from growth_dashboard.meta_daily import MetaTokenExpiredError, fetch_daily_ad_insights, rows_for_sheet as meta_rows
from growth_dashboard.klaviyo_weekly import fetch_campaigns_last_30d, rows_for_sheet as klaviyo_rows
from growth_dashboard.creative_registry import build_registry_rows
from growth_dashboard.site_snapshots import run_site_audit
from growth_dashboard.clarity_csv import merge_clarity_into_shopify_report, parse_clarity_export_csv
from growth_dashboard.shopify_daily import fetch_daily_report, row_for_sheet as shopify_row


def _admin_ok() -> bool:
    token = (os.environ.get("ADMIN_TOKEN") or os.environ.get("WEARTH_N8N_MAIL_TOKEN") or "").strip()
    if not token:
        return True
    return (request.headers.get("X-Wearth-Admin") or "").strip() == token


def _deny():
    return jsonify({"ok": False, "error": "unauthorized"}), 401


def growth_verify():
    if not _admin_ok():
        return _deny()
    try:
        info, sheets, drive = _google_services()
        setup = ensure_growth_sheet(sheets)
        sid = setup["sheet_id"] or growth_sheet_id()
        meta = sheets.spreadsheets().get(spreadsheetId=sid).execute()
        parent = os.environ.get("GROWTH_DRIVE_ROOT_FOLDER_ID") or os.environ.get("GOOGLE_DRIVE_PARENT_FOLDER_ID")
        return jsonify(
            {
                "ok": True,
                "service_account": info.get("client_email"),
                "sheet_id": sid,
                "sheet_url": sheet_url(sid),
                "sheet_title": (meta.get("properties") or {}).get("title"),
                "tabs": [(s.get("properties") or {}).get("title") for s in meta.get("sheets", [])],
                "drive_parent": parent,
                "meta_insights_token_set": bool(os.environ.get("META_INSIGHTS_TOKEN")),
            }
        )
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


def growth_sync_meta_daily():
    if not _admin_ok():
        return _deny()
    synced = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        _, sheets, _ = _google_services()
        setup = ensure_growth_sheet(sheets)
        sid = setup["sheet_id"]
        ensure_tab_headers(sheets, sid, TAB_META, META_HEADERS)
        insights = fetch_daily_ad_insights(request.args.get("date") or None)
        rows = meta_rows(insights, synced)
        n = append_rows(sheets, sid, TAB_META, rows)
        return jsonify(
            {
                "ok": True,
                "rows_appended": n,
                "report_date": insights[0]["date"] if insights else None,
                "sheet_url": sheet_url(sid),
            }
        )
    except MetaTokenExpiredError as e:
        meta_token_expired_alert(str(e))
        return jsonify({"ok": False, "error": "meta_token_expired", "detail": str(e)}), 401
    except Exception as e:
        send_gmail_alert("WEARTH Growth Dashboard: Meta sync failed", str(e))
        return jsonify({"ok": False, "error": str(e)}), 500


def growth_sync_shopify_daily():
    if not _admin_ok():
        return _deny()
    synced = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        _, sheets, _ = _google_services()
        setup = ensure_growth_sheet(sheets)
        sid = setup["sheet_id"]
        ensure_tab_headers(sheets, sid, TAB_SHOPIFY, SHOPIFY_HEADERS)
        report = fetch_daily_report(request.args.get("date") or None)
        n = append_rows(sheets, sid, TAB_SHOPIFY, [shopify_row(report, synced)])
        return jsonify({"ok": True, "rows_appended": n, "report": report, "sheet_url": sheet_url(sid)})
    except Exception as e:
        send_gmail_alert("WEARTH Growth Dashboard: Shopify sync failed", str(e))
        return jsonify({"ok": False, "error": str(e)}), 500


def growth_sync_klaviyo_weekly():
    if not _admin_ok():
        return _deny()
    synced = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        _, sheets, _ = _google_services()
        setup = ensure_growth_sheet(sheets)
        sid = setup["sheet_id"]
        ensure_tab_headers(sheets, sid, TAB_KLAVIYO, KLAVIYO_HEADERS)
        campaigns = fetch_campaigns_last_30d()
        replace_tab(sheets, sid, TAB_KLAVIYO, KLAVIYO_HEADERS, klaviyo_rows(campaigns, synced))
        return jsonify(
            {
                "ok": True,
                "campaigns": len(campaigns),
                "sheet_url": sheet_url(sid),
            }
        )
    except Exception as e:
        send_gmail_alert("WEARTH Growth Dashboard: Klaviyo sync failed", str(e))
        return jsonify({"ok": False, "error": str(e)}), 500


def growth_sync_creative_registry():
    if not _admin_ok():
        return _deny()
    try:
        _, sheets, _ = _google_services()
        setup = ensure_growth_sheet(sheets)
        sid = setup["sheet_id"]
        ensure_tab_headers(sheets, sid, TAB_CREATIVE, CREATIVE_HEADERS)
        rows = build_registry_rows()
        replace_tab(sheets, sid, TAB_CREATIVE, CREATIVE_HEADERS, rows)
        return jsonify({"ok": True, "rows": len(rows), "sheet_url": sheet_url(sid)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


def growth_run_site_audit():
    if not _admin_ok():
        return _deny()
    try:
        result = run_site_audit()
        _, sheets, _ = _google_services()
        sid = growth_sheet_id() or ensure_growth_sheet(sheets)["sheet_id"]
        return jsonify({**result, "sheet_url": sheet_url(sid)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


def growth_sync_clarity_csv():
    """POST multipart file `file` or raw CSV body — enriches Tab 2 (Shopify Daily)."""
    if not _admin_ok():
        return _deny()
    synced = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        raw = ""
        if request.files and request.files.get("file"):
            raw = request.files["file"].read().decode("utf-8-sig", errors="replace")
        elif request.data:
            raw = request.data.decode("utf-8-sig", errors="replace")
        else:
            return jsonify({"ok": False, "error": "upload CSV as multipart field file"}), 400

        clarity = parse_clarity_export_csv(raw)
        report_date = (request.args.get("date") or clarity.get("report_date") or "").strip() or None
        shopify = fetch_daily_report(report_date)
        merged = merge_clarity_into_shopify_report(shopify, clarity)

        _, sheets, _ = _google_services()
        setup = ensure_growth_sheet(sheets)
        sid = setup["sheet_id"]
        ensure_tab_headers(sheets, sid, TAB_SHOPIFY, SHOPIFY_HEADERS)
        n = append_rows(sheets, sid, TAB_SHOPIFY, [shopify_row(merged, synced)])
        return jsonify(
            {
                "ok": True,
                "rows_appended": n,
                "clarity": clarity,
                "report": merged,
                "sheet_url": sheet_url(sid),
            }
        )
    except Exception as e:
        send_gmail_alert("WEARTH Growth Dashboard: Clarity CSV sync failed", str(e))
        return jsonify({"ok": False, "error": str(e)}), 500


def growth_sync_all_daily():
    """Single n8n hit: Meta + Shopify (8am IST)."""
    if not _admin_ok():
        return _deny()
    results: dict = {}
    for name, handler in (("meta", growth_sync_meta_daily), ("shopify", growth_sync_shopify_daily)):
        resp = handler()
        if isinstance(resp, tuple):
            body, code = resp
            results[name] = {**(body.get_json() or {}), "_http": code}
        else:
            results[name] = resp.get_json()
    ok = results.get("meta", {}).get("ok") and results.get("shopify", {}).get("ok")
    sid = growth_sheet_id()
    return jsonify({"ok": ok, "results": results, "sheet_url": sheet_url(sid) if sid else ""})
