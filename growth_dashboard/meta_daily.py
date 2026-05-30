# -*- coding: utf-8 -*-
"""Meta Ads Daily → Growth Dashboard Tab 1."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

META_ACT = "8979315238856807"

ATC_TYPES = frozenset(
    {
        "add_to_cart",
        "offsite_conversion.fb_pixel_add_to_cart",
        "omni_add_to_cart",
        "onsite_web_add_to_cart",
    }
)
PURCHASE_TYPES = frozenset(
    {
        "purchase",
        "offsite_conversion.fb_pixel_purchase",
        "omni_purchase",
        "onsite_web_purchase",
    }
)


def _token() -> str:
    tok = (os.environ.get("META_INSIGHTS_TOKEN") or os.environ.get("META_ACCESS_TOKEN") or "").strip()
    if not tok:
        raise RuntimeError("META_INSIGHTS_TOKEN (or META_ACCESS_TOKEN) is not set")
    return tok


def _graph() -> str:
    ver = (os.environ.get("META_GRAPH_VERSION") or "v22.0").strip()
    if not ver.startswith("v"):
        ver = f"v{ver}"
    return f"https://graph.facebook.com/{ver}"


def _get(path: str, params: dict | None = None) -> dict:
    p = dict(params or {})
    p["access_token"] = _token()
    r = requests.get(f"{_graph()}/{path}", params=p, timeout=120)
    if r.status_code != 200:
        err = (r.text or "")[:800]
        if r.status_code == 401 or "OAuthException" in err or "expired" in err.lower():
            raise MetaTokenExpiredError(err)
        raise RuntimeError(f"Meta GET {path} HTTP {r.status_code}: {err}")
    return r.json() or {}


class MetaTokenExpiredError(RuntimeError):
    pass


def _action_count(actions: list | None, types: frozenset) -> int:
    n = 0
    for a in actions or []:
        if str(a.get("action_type") or "") in types:
            try:
                n += int(float(a.get("value") or 0))
            except (TypeError, ValueError):
                pass
    return n


def _action_value(action_values: list | None, types: frozenset) -> float:
    for a in action_values or []:
        if str(a.get("action_type") or "") in types:
            try:
                return float(a.get("value") or 0)
            except (TypeError, ValueError):
                pass
    return 0.0


def _cost_per_action(costs: list | None, types: frozenset) -> float | None:
    for c in costs or []:
        if str(c.get("action_type") or "") in types:
            try:
                return float(c.get("value") or 0)
            except (TypeError, ValueError):
                pass
    return None


def _yesterday_ist() -> str:
    ist = timezone(timedelta(hours=5, minutes=30))
    d = (datetime.now(ist) - timedelta(days=1)).date()
    return d.isoformat()


def fetch_ad_status_map() -> dict[str, dict]:
    """ad_id -> {status, lifetime_spend}"""
    fields = "id,name,effective_status,insights.date_preset(maximum){spend}"
    out: dict[str, dict] = {}
    data = _get(f"act_{META_ACT}/ads", {"fields": fields, "limit": 200})
    while True:
        for ad in data.get("data") or []:
            aid = str(ad.get("id") or "")
            ins = ((ad.get("insights") or {}).get("data") or [{}])[0]
            out[aid] = {
                "status": ad.get("effective_status") or ad.get("status") or "",
                "lifetime_spend": float(ins.get("spend") or 0),
            }
        url = (data.get("paging") or {}).get("next")
        if not url:
            break
        r = requests.get(url, timeout=120)
        r.raise_for_status()
        data = r.json() or {}
    return out


def fetch_daily_ad_insights(report_date: str | None = None) -> list[dict[str, Any]]:
    """One row per ad for report_date (default yesterday IST)."""
    report_date = report_date or _yesterday_ist()
    fields = (
        "campaign_name,adset_name,ad_name,ad_id,date_start,date_stop,"
        "spend,impressions,reach,cpm,ctr,inline_link_clicks,"
        "cost_per_inline_link_click,actions,action_values,cost_per_action_type"
    )
    params = {
        "level": "ad",
        "time_increment": 1,
        "time_range": json.dumps({"since": report_date, "until": report_date}),
        "fields": fields,
        "limit": 500,
    }
    status_map = fetch_ad_status_map()
    rows: list[dict[str, Any]] = []
    data = _get(f"act_{META_ACT}/insights", params)
    while True:
        for ins in data.get("data") or []:
            aid = str(ins.get("ad_id") or "")
            st = status_map.get(aid, {})
            spend = float(ins.get("spend") or 0)
            link_clicks = int(ins.get("inline_link_clicks") or 0)
            atc = _action_count(ins.get("actions"), ATC_TYPES)
            purchases = _action_count(ins.get("actions"), PURCHASE_TYPES)
            purchase_value = _action_value(ins.get("action_values"), PURCHASE_TYPES)
            roas = round(purchase_value / spend, 4) if spend > 0 and purchase_value else ""
            cplc = ins.get("cost_per_inline_link_click")
            if cplc is None and link_clicks and spend:
                cplc = round(spend / link_clicks, 4)
            cpatc = _cost_per_action(ins.get("cost_per_action_type"), ATC_TYPES)
            if cpatc is None and atc and spend:
                cpatc = round(spend / atc, 4)
            rows.append(
                {
                    "date": ins.get("date_start") or report_date,
                    "campaign_name": ins.get("campaign_name") or "",
                    "ad_set_name": ins.get("adset_name") or "",
                    "ad_name": ins.get("ad_name") or "",
                    "ad_id": aid,
                    "status": st.get("status", ""),
                    "daily_spend_inr": spend,
                    "impressions": int(ins.get("impressions") or 0),
                    "reach": int(ins.get("reach") or 0),
                    "cpm": ins.get("cpm") or "",
                    "ctr": ins.get("ctr") or "",
                    "link_clicks": link_clicks,
                    "cost_per_link_click": cplc or "",
                    "atc_count": atc,
                    "cost_per_atc": cpatc or "",
                    "purchase_count": purchases,
                    "purchase_roas": roas,
                    "amount_spent_to_date_inr": st.get("lifetime_spend", ""),
                }
            )
        url = (data.get("paging") or {}).get("next")
        if not url:
            break
        r = requests.get(url, timeout=120)
        r.raise_for_status()
        data = r.json() or {}
    return rows


def rows_for_sheet(insights: list[dict], synced_at: str) -> list[list]:
    out = []
    for r in insights:
        out.append(
            [
                r.get("date", ""),
                r.get("campaign_name", ""),
                r.get("ad_set_name", ""),
                r.get("ad_name", ""),
                r.get("ad_id", ""),
                r.get("status", ""),
                r.get("daily_spend_inr", ""),
                r.get("impressions", ""),
                r.get("reach", ""),
                r.get("cpm", ""),
                r.get("ctr", ""),
                r.get("link_clicks", ""),
                r.get("cost_per_link_click", ""),
                r.get("atc_count", ""),
                r.get("cost_per_atc", ""),
                r.get("purchase_count", ""),
                r.get("purchase_roas", ""),
                r.get("amount_spent_to_date_inr", ""),
                synced_at,
            ]
        )
    return out
