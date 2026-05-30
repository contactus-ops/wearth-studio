# -*- coding: utf-8 -*-
"""Creative Registry tab — Drive folders + live Meta ad mapping."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import requests

from google_engine import DRIVE_FOLDER_MIME, _google_services, _list_drive_children
from growth_dashboard import meta_daily as meta_mod
from growth_dashboard.google_client import drive_growth_root_id


def _meta_ads_live() -> list[dict[str, Any]]:
    try:
        meta_mod._token()
    except Exception:
        return []
    fields = "id,name,effective_status,campaign{name},adset{name},creative{thumbnail_url,object_story_spec}"
    try:
        data = meta_mod._get(f"act_{meta_mod.META_ACT}/ads", {"fields": fields, "limit": 200})
    except Exception:
        return []
    rows = []
    for ad in data.get("data") or []:
        cr = ad.get("creative") or {}
        spec = cr.get("object_story_spec") or {}
        fmt = "static"
        if spec.get("video_data"):
            fmt = "video"
        if spec.get("link_data", {}).get("child_attachments"):
            fmt = "carousel"
        rows.append(
            {
                "ad_id": ad.get("id"),
                "ad_name": ad.get("name"),
                "status": ad.get("effective_status") or "",
                "campaign": (ad.get("campaign") or {}).get("name") or "",
                "adset": (ad.get("adset") or {}).get("name") or "",
                "format": fmt,
            }
        )
    return rows


def _files_in_parent(drive, parent_id: str) -> list[dict]:
    out = []
    for folder in _list_drive_children(drive, parent_id, DRIVE_FOLDER_MIME):
        fid = folder["id"]
        link = folder.get("webViewLink") or f"https://drive.google.com/drive/folders/{fid}"
        files = _list_drive_children(drive, fid)
        images = [f for f in files if (f.get("mimeType") or "").startswith("image/")]
        videos = [f for f in files if (f.get("mimeType") or "").startswith("video/")]
        if images and videos:
            fmt = "carousel"
            primary = images[0]
        elif videos:
            fmt = "video"
            primary = videos[0]
        elif images:
            fmt = "static"
            primary = images[0]
        else:
            fmt = "unknown"
            primary = folder
        out.append(
            {
                "creative_filename": primary.get("name") or folder.get("name"),
                "google_drive_link": primary.get("webViewLink") or link,
                "folder_name": folder.get("name"),
                "date_uploaded": (primary.get("modifiedTime") or "")[:10],
                "format": fmt,
            }
        )
    # Also loose image/video files directly in parent
    for f in _list_drive_children(drive, parent_id):
        mt = f.get("mimeType") or ""
        if mt.startswith("image/") or mt.startswith("video/"):
            out.append(
                {
                    "creative_filename": f.get("name"),
                    "google_drive_link": f.get("webViewLink") or "",
                    "folder_name": "",
                    "date_uploaded": (f.get("modifiedTime") or "")[:10],
                    "format": "video" if mt.startswith("video/") else "static",
                }
            )
    return out


def build_registry_rows() -> list[list]:
    parent = drive_growth_root_id()
    drive_items: list[dict] = []
    if parent:
        _info, _sheets, drive = _google_services()
        drive_items = _files_in_parent(drive, parent)

    live_ads = _meta_ads_live()
    synced = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def match_ad(item: dict) -> dict:
        name = (item.get("folder_name") or item.get("creative_filename") or "").lower()
        for ad in live_ads:
            an = (ad.get("ad_name") or "").lower()
            if name and (name in an or an in name):
                return ad
        return {}

    rows = []
    for item in drive_items:
        ad = match_ad(item)
        status = "live" if (ad.get("status") or "").upper() in ("ACTIVE", "PAUSED") else "testing"
        if ad.get("status", "").upper() == "PAUSED":
            status = "paused"
        rows.append(
            [
                item.get("creative_filename", ""),
                item.get("google_drive_link", ""),
                ad.get("campaign", ""),
                ad.get("adset", ""),
                item.get("date_uploaded", ""),
                item.get("format", ""),
                status,
                ad.get("ad_id", ""),
                "",
            ]
        )

    # Meta ads without drive match
    matched_ids = {r[7] for r in rows if r[7]}
    for ad in live_ads:
        if ad.get("ad_id") in matched_ids:
            continue
        st = "paused" if (ad.get("status") or "").upper() == "PAUSED" else "live"
        rows.append(
            [
                ad.get("ad_name", ""),
                "",
                ad.get("campaign", ""),
                ad.get("adset", ""),
                "",
                ad.get("format", ""),
                st,
                ad.get("ad_id", ""),
                "no_drive_folder_match",
            ]
        )
    return rows
