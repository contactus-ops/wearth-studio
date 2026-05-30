#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Full Meta campaign audit: JSON dump, consulting report, creatives → Google Drive."""
from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_env = ROOT / ".env"
if _env.exists():
    for ln in _env.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if ln and not ln.startswith("#") and "=" in ln:
            k, v = ln.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

CAMPAIGN_ID = (os.environ.get("META_CAMPAIGN_AUDIT_ID") or "120246893576740305").strip()
ACT = (os.environ.get("META_AD_ACCOUNT_ID") or "8979315238856807").strip().replace("act_", "")
TOKEN = (os.environ.get("META_ACCESS_TOKEN") or "").strip()
GRAPH = f"https://graph.facebook.com/{(os.environ.get('META_GRAPH_VERSION') or 'v22.0').strip()}"
OUT_ROOT = ROOT / "data" / "meta_campaign_audit" / CAMPAIGN_ID
REPORT_MD = OUT_ROOT / "META_CAMPAIGN_CONSULTING_REPORT.md"
RAW_JSON = OUT_ROOT / "campaign_raw.json"

ADSET_FIELDS = (
    "id,name,status,effective_status,configured_status,"
    "targeting,optimization_goal,billing_event,bid_strategy,"
    "daily_budget,lifetime_budget,promoted_object,attribution_spec,"
    "destination_type,pacing_type,learning_stage_info,"
    "created_time,updated_time,start_time,end_time,campaign_id"
)
AD_FIELDS = (
    "id,name,status,effective_status,configured_status,"
    "creative{id,name,thumbnail_url,object_story_spec,asset_feed_spec,"
    "effective_object_story_id,image_url,image_hash,video_id},"
    "tracking_specs,conversion_specs,created_time,updated_time,adset_id"
)
CAMP_FIELDS = (
    "id,name,status,effective_status,objective,buying_type,"
    "daily_budget,lifetime_budget,bid_strategy,budget_rebalance_flag,"
    "smart_promotion_type,is_adset_budget_sharing_enabled,special_ad_categories,"
    "created_time,updated_time,start_time,stop_time"
)
CREATIVE_FIELDS = (
    "id,name,thumbnail_url,image_url,image_hash,video_id,"
    "object_story_spec,asset_feed_spec,effective_object_story_id"
)


def _get(path: str, params: dict | None = None) -> dict:
    p = dict(params or {})
    p["access_token"] = TOKEN
    r = requests.get(f"{GRAPH}/{path}", params=p, timeout=120)
    data = r.json() if r.text else {}
    if r.status_code != 200:
        raise RuntimeError(f"GET {path} {r.status_code}: {json.dumps(data)[:800]}")
    return data


def _paginate(path: str, params: dict) -> list[dict]:
    out: list[dict] = []
    data = _get(path, params)
    while True:
        out.extend(data.get("data") or [])
        url = (data.get("paging") or {}).get("next")
        if not url:
            break
        r = requests.get(url, timeout=120)
        r.raise_for_status()
        data = r.json() or {}
    return out


def _safe_name(s: str, max_len: int = 80) -> str:
    s = re.sub(r"[^\w\-]+", "_", (s or "unnamed").strip())[:max_len]
    return s.strip("_") or "unnamed"


def _download(url: str, dest: Path) -> bool:
    if not url:
        return False
    try:
        r = requests.get(url, timeout=90)
        if r.status_code != 200:
            return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(r.content)
        return True
    except Exception:
        return False


def _creative_media_urls(creative: dict) -> list[tuple[str, str]]:
    """Return [(label, url), ...] for images/videos."""
    urls: list[tuple[str, str]] = []
    if creative.get("thumbnail_url"):
        urls.append(("thumbnail", creative["thumbnail_url"]))
    if creative.get("image_url"):
        urls.append(("image", creative["image_url"]))

    oss = creative.get("object_story_spec") or {}
    link_data = oss.get("link_data") or {}
    if link_data.get("picture"):
        urls.append(("link_picture", link_data["picture"]))
    if link_data.get("image_hash"):
        urls.append(("image_hash_ref", link_data["image_hash"]))
    video_data = oss.get("video_data") or {}
    if video_data.get("image_url"):
        urls.append(("video_poster", video_data["image_url"]))

    vid = creative.get("video_id") or video_data.get("video_id")
    if vid:
        try:
            vd = _get(
                vid,
                {"fields": "source,picture,thumbnails,title,length,format"},
            )
            if vd.get("source"):
                urls.append(("video_source", vd["source"]))
            if vd.get("picture"):
                urls.append(("video_picture", vd["picture"]))
        except Exception:
            pass

    # full-size from adimages if hash
    ih = creative.get("image_hash") or link_data.get("image_hash")
    if ih:
        try:
            imgs = _get(f"act_{ACT}/adimages", {"hashes": json.dumps([ih]), "fields": "hash,url,permalink_url"})
            for row in imgs.get("data") or []:
                u = row.get("url") or row.get("permalink_url")
                if u:
                    urls.append(("adimage_full", u))
        except Exception:
            pass

    # dedupe urls
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for label, u in urls:
        if u not in seen:
            seen.add(u)
            out.append((label, u))
    return out


def _targeting_report(t: dict) -> list[str]:
    lines: list[str] = []
    if not t:
        return ["- *(no targeting)*"]
    adv = (t.get("targeting_automation") or {}).get("advantage_audience")
    lines.append(f"- **Advantage+ audience:** {'ON ⚠️' if adv == 1 else 'OFF ✓' if adv == 0 else adv}")
    g = t.get("genders") or []
    gmap = {0: "All", 1: "Men", 2: "Women"}
    genders = ", ".join(gmap.get(int(x), str(x)) for x in g) if g else "All"
    lines.append(f"- **Gender:** {genders}")
    if t.get("age_range"):
        lines.append(f"- **Age range (Advantage):** {t['age_range']}")
    lines.append(f"- **Age min/max:** {t.get('age_min', '—')} / {t.get('age_max', '—')}")
    geo = t.get("geo_locations") or {}
    if geo.get("countries"):
        lines.append(f"- **Countries:** {', '.join(geo['countries'])}")
    cities = geo.get("cities") or []
    if cities:
        lines.append(f"- **Cities:** {', '.join(c.get('name', '') for c in cities[:12])}{'…' if len(cities) > 12 else ''}")
    lines.append(f"- **Location types:** {', '.join(geo.get('location_types') or [])}")
    cas = t.get("custom_audiences") or []
    if cas:
        lines.append("- **Custom audiences (included):**")
        for c in cas:
            lines.append(f"  - {c.get('name', c.get('id'))}")
    ex = t.get("excluded_custom_audiences") or []
    if ex:
        lines.append("- **Custom audiences (excluded):**")
        for c in ex:
            lines.append(f"  - {c.get('name', c.get('id'))}")
    for spec in t.get("flexible_spec") or []:
        if spec.get("interests"):
            lines.append(f"- **Interests:** {len(spec['interests'])} bands")
        if spec.get("behaviors"):
            lines.append("- **Behaviors:** " + "; ".join(b.get("name", "") for b in spec["behaviors"][:8]))
        if spec.get("user_adclusters"):
            lines.append("- **Income/lifestyle clusters:** " + "; ".join(
                u.get("name", "") for u in spec["user_adclusters"][:6]
            ))
    lines.append(f"- **Publisher platforms:** {', '.join(t.get('publisher_platforms') or ['(default)'])}")
    lines.append(f"- **Device platforms:** {', '.join(t.get('device_platforms') or ['(default)'])}")
    return lines


def _fetch_insights_7d(object_id: str, level: str) -> dict:
    try:
        since = (datetime.now(timezone.utc).date()).isoformat()
        # last 7d
        from datetime import timedelta

        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=7)
        params = {
            "fields": "spend,impressions,reach,ctr,cpc,cpm,inline_link_clicks,actions,cost_per_action_type",
            "time_range": json.dumps({"since": start.isoformat(), "until": end.isoformat()}),
            "level": level,
        }
        if level == "ad":
            params["filtering"] = json.dumps(
                [{"field": "ad.id", "operator": "EQUAL", "value": object_id}]
            )
        data = _get(f"{object_id}/insights", params)
        rows = data.get("data") or []
        return rows[0] if rows else {}
    except Exception as e:
        return {"error": str(e)[:200]}


def _upload_to_drive(local_files: list[Path], folder_name: str) -> dict[str, Any]:
    try:
        from google_engine import _google_services
        from video_engine import _drive_folder_meta, _ensure_combo_output_folder, _shared_drive_output_error

        _, _, drive = _google_services()
        parent = (
            os.environ.get("META_AUDIT_DRIVE_FOLDER_ID")
            or os.environ.get("VIDEOS_FOLDER")
            or os.environ.get("DRIVE_VIDEOS_FOLDER")
            or os.environ.get("GOOGLE_DRIVE_PARENT_FOLDER_ID")
            or ""
        ).strip()
        if not parent:
            return {"ok": False, "error": "No Drive parent folder ID in env"}
        root_meta = _drive_folder_meta(drive, parent)
        sd_err = _shared_drive_output_error(root_meta)
        if sd_err:
            return {"ok": False, "error": sd_err, "parent_id": parent}
        folder = _ensure_combo_output_folder(drive, parent, folder_name)
        links: list[dict] = []
        from googleapiclient.http import MediaFileUpload

        for p in local_files:
            if not p.exists():
                continue
            mime = "application/json" if p.suffix == ".json" else "text/markdown"
            if p.suffix.lower() == ".mp4":
                mime = "video/mp4"
            elif p.suffix.lower() in (".jpg", ".jpeg"):
                mime = "image/jpeg"
            elif p.suffix.lower() == ".png":
                mime = "image/png"
            media = MediaFileUpload(str(p), mimetype=mime, resumable=True)
            created = (
                drive.files()
                .create(
                    body={"name": p.name, "parents": [folder["id"]]},
                    media_body=media,
                    fields="id,webViewLink",
                    supportsAllDrives=True,
                )
                .execute()
            )
            links.append({"file": p.name, "link": created.get("webViewLink")})
        return {"ok": True, "folder_link": folder.get("webViewLink"), "folder_id": folder["id"], "files": links}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _flag_ad(ad: dict, adset: dict, siblings: list[dict]) -> list[str]:
    flags: list[str] = []
    name = (ad.get("name") or "").lower()
    if "copy" in name or "duplicate" in name or "v2" in name and "v1" in " ".join(
        (s.get("name") or "").lower() for s in siblings
    ):
        flags.append("DUPLICATE_NAME_PATTERN")
    if ad.get("effective_status") in ("DISAPPROVED", "WITH_ISSUES"):
        flags.append(f"DELIVERY_BLOCKED:{ad.get('effective_status')}")
    cr = ad.get("creative") or {}
    oss = cr.get("object_story_spec") or {}
    if not oss and not cr.get("asset_feed_spec"):
        flags.append("MISSING_CREATIVE_SPEC")
    link = (oss.get("link_data") or {})
    msg = (link.get("message") or "").lower()
    if len(msg) < 20:
        flags.append("WEAK_PRIMARY_TEXT")
    if "hooklab" in name and "test" in name:
        flags.append("LEGACY_TEST_NAMING")
    po = adset.get("promoted_object") or {}
    if po.get("custom_event_type") == "PURCHASE" and adset.get("optimization_goal") == "OFFSITE_CONVERSIONS":
        flags.append("OPTIMIZE_PURCHASE_COLD_TRAFFIC_RISK")
    return flags


def main() -> int:
    if not TOKEN:
        print(json.dumps({"ok": False, "error": "META_ACCESS_TOKEN missing"}))
        return 1

    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    camp = _get(CAMPAIGN_ID, {"fields": CAMP_FIELDS})
    adsets = _paginate(f"{CAMPAIGN_ID}/adsets", {"fields": ADSET_FIELDS, "limit": 50})

    # archived adsets in same campaign
    act_adsets = _paginate(
        f"act_{ACT}/adsets",
        {
            "fields": ADSET_FIELDS,
            "limit": 100,
            "filtering": json.dumps(
                [{"field": "campaign.id", "operator": "EQUAL", "value": CAMPAIGN_ID}]
            ),
            "effective_status": json.dumps(["ARCHIVED", "PAUSED", "ACTIVE", "CAMPAIGN_PAUSED"]),
        },
    )
    by_id = {a["id"]: a for a in adsets}
    for a in act_adsets:
        by_id.setdefault(a["id"], a)
    adsets = list(by_id.values())

    tree: dict[str, Any] = {"campaign": camp, "adsets": [], "exported_at": stamp}
    all_local: list[Path] = []
    md: list[str] = []

    md.append("# WEARTH Meta Campaign — Full Consulting Audit")
    md.append("")
    md.append(f"**Generated:** {stamp} UTC  ")
    md.append(f"**Campaign ID:** `{CAMPAIGN_ID}`  ")
    md.append(f"**Campaign name:** {camp.get('name', '')}  ")
    md.append(f"**Ads Manager:** [Open campaign](https://adsmanager.facebook.com/adsmanager/manage/campaigns?act={ACT}&selected_campaign_ids={CAMPAIGN_ID})  ")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## Executive summary (strategy failing — hypothesis)")
    md.append("")
    md.append(
        "This document is built for Claude review: every toggle, targeting corner, creative file, "
        "and delivery flag. Use the **Google Drive folder** (below) for visual creative review."
    )
    md.append("")

  # Campaign level
    daily = camp.get("daily_budget")
    daily_inr = f"₹{int(daily)/100:,.0f}/day" if daily else "—"
    md.append("## 1. Campaign level")
    md.append("")
    md.append(f"| Field | Value |")
    md.append(f"|-------|-------|")
    for k in [
        "name",
        "status",
        "effective_status",
        "objective",
        "buying_type",
        "bid_strategy",
        "smart_promotion_type",
        "budget_rebalance_flag",
        "is_adset_budget_sharing_enabled",
    ]:
        md.append(f"| {k} | `{camp.get(k, '')}` |")
    md.append(f"| daily_budget (API units) | `{daily}` → **{daily_inr}** |")
    md.append("")
    md.append("### Campaign-level Advantage / budget notes")
    md.append("")
    md.append("- **Campaign budget optimization (CBO):** " + ("Yes — budget at campaign" if daily else "No / ad set budgets"))
    md.append(f"- **smart_promotion_type:** `{camp.get('smart_promotion_type')}` (GUIDED_CREATION = standard flow; not Advantage+ sales catalog)")
    md.append("- **Advantage+ campaign budget (UI):** Confirm in Ads Manager right panel — should be **Off** for strict control.")
    md.append("")

    for adset in sorted(adsets, key=lambda x: x.get("name", "")):
        asid = adset["id"]
        ads = _paginate(f"{asid}/ads", {"fields": AD_FIELDS, "limit": 50})
        ins = _fetch_insights_7d(asid, "adset")
        as_node = {"adset": adset, "ads": [], "insights_7d": ins}
        md.append(f"## 2. Ad set: {adset.get('name')} (`{asid}`)")
        md.append("")
        md.append(f"**Status:** `{adset.get('effective_status')}`  ")
        md.append(f"**Optimization:** `{adset.get('optimization_goal')}`  ")
        po = adset.get("promoted_object") or {}
        md.append(f"**Promoted object:** pixel `{po.get('pixel_id')}` → event `{po.get('custom_event_type')}`  ")
        md.append(f"**Bid strategy:** `{adset.get('bid_strategy', '—')}`  ")
        md.append("")
        md.append("### Targeting (every corner)")
        md.append("")
        md.extend(_targeting_report(adset.get("targeting") or {}))
        md.append("")
        md.append("### Attribution")
        md.append("")
        for spec in adset.get("attribution_spec") or []:
            md.append(f"- {spec.get('event_type')}: {spec.get('window_days')} day window")
        md.append("")
        if ins and not ins.get("error"):
            md.append("### Last 7 days performance (ad set)")
            md.append("")
            md.append(f"- Spend: {ins.get('spend', '0')}")
            md.append(f"- Impressions: {ins.get('impressions', '0')}")
            md.append(f"- CTR: {ins.get('ctr', '—')}")
        md.append("")

        as_dir = OUT_ROOT / "creatives" / _safe_name(f"{asid}_{adset.get('name', '')}")
        as_dir.mkdir(parents=True, exist_ok=True)

        for ad in ads:
            aid = ad["id"]
            cr_id = (ad.get("creative") or {}).get("id")
            cr_full = _get(cr_id, {"fields": CREATIVE_FIELDS}) if cr_id else {}
            ad["creative"] = cr_full
            flags = _flag_ad(ad, adset, ads)
            ad_ins = _fetch_insights_7d(aid, "ad")
            ad_node = {"ad": ad, "flags": flags, "insights_7d": ad_ins}
            as_node["ads"].append(ad_node)

            md.append(f"### 3. Ad: {ad.get('name')} (`{aid}`)")
            md.append("")
            md.append(f"| | |")
            md.append(f"|---|---|")
            md.append(f"| Status | `{ad.get('effective_status')}` |")
            md.append(f"| Creative ID | `{cr_id}` |")
            if flags:
                md.append(f"| **FLAGS** | **{', '.join(flags)}** |")
            else:
                md.append("| FLAGS | *(none — still verify creative visually)* |")
            md.append("")

            oss = cr_full.get("object_story_spec") or {}
            link = oss.get("link_data") or {}
            if link:
                md.append("**Primary text:**")
                md.append("```")
                md.append((link.get("message") or "")[:2000])
                md.append("```")
                md.append(f"**Headline:** {link.get('name', '—')}  ")
                md.append(f"**Description:** {link.get('description', '—')}  ")
                md.append(f"**CTA:** {link.get('call_to_action', {}).get('type', '—')}  ")
                md.append(f"**Landing URL:** {link.get('link', '—')}  ")
                md.append("")

            prefix = _safe_name(f"{aid}_{ad.get('name', '')}")
            for label, url in _creative_media_urls(cr_full):
                ext = ".jpg"
                if "video" in label:
                    ext = ".mp4"
                dest = as_dir / f"{prefix}__{label}{ext}"
                if _download(url, dest):
                    all_local.append(dest)
                    md.append(f"- **Creative file:** `{dest.name}` ← {label}")

            md.append("")

        tree["adsets"].append(as_node)

    RAW_JSON.write_text(json.dumps(tree, indent=2, default=str), encoding="utf-8")

    folder_name = f"Meta Audit {camp.get('name', '')[:40]} {stamp[:8]}"
    drive_result = _upload_to_drive(all_local, folder_name)

    if drive_result.get("ok"):
        md.insert(
            6,
            f"**Google Drive folder (Claude review):** {drive_result['folder_link']}  ",
        )
        md.insert(7, "")
    else:
        md.insert(6, f"**Google Drive:** Upload failed — `{drive_result.get('error')}`  ")
        md.insert(7, f"**Local export:** `{OUT_ROOT}`  ")
        md.insert(8, "")

    md.append("## 4. Creative assets on Google Drive")
    md.append("")
    if drive_result.get("ok"):
        for f in drive_result.get("files") or []:
            md.append(f"- [{f['file']}]({f['link']})")
        # upload report + json to same folder
        try:
            from growth_dashboard.google_client import upload_file_to_folder
            from google_engine import _google_services

            _, _, drive = _google_services()
            fid = drive_result["folder_id"]
            up_r = upload_file_to_folder(drive, fid, str(REPORT_MD), "text/markdown")
            up_j = upload_file_to_folder(drive, fid, str(RAW_JSON), "application/json")
            md.append(f"- [META_CAMPAIGN_CONSULTING_REPORT.md]({up_r['link']})")
            md.append(f"- [campaign_raw.json]({up_j['link']})")
            REPORT_MD.write_text("\n".join(md), encoding="utf-8")
            upload_file_to_folder(drive, fid, str(REPORT_MD), "text/markdown")
        except Exception as e:
            md.append(f"- Report upload error: {e}")
    else:
        md.append("- *(see local `creatives/` and `META_CAMPAIGN_CONSULTING_REPORT.md`)*")

    REPORT_MD.write_text("\n".join(md), encoding="utf-8")

    print(
        json.dumps(
            {
                "ok": True,
                "campaign_id": CAMPAIGN_ID,
                "report": str(REPORT_MD),
                "raw_json": str(RAW_JSON),
                "drive": drive_result,
                "adsets": len(adsets),
                "creatives_downloaded": len(all_local),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
