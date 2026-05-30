# -*- coding: utf-8 -*-
"""Klaviyo campaigns (last 30d) → Tab 3 full replace weekly."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

KLAVIYO_BASE = "https://a.klaviyo.com/api"
REVISION = "2024-10-15"


def _key() -> str:
    k = (os.environ.get("KLAVIYO_PRIVATE_KEY") or "").strip()
    if not k:
        raise RuntimeError("KLAVIYO_PRIVATE_KEY is not set")
    return k


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Klaviyo-API-Key {_key()}",
        "revision": REVISION,
        "accept": "application/json",
    }


def _get(path: str, params: dict | None = None) -> dict:
    r = requests.get(f"{KLAVIYO_BASE}{path}", headers=_headers(), params=params or {}, timeout=120)
    if r.status_code != 200:
        raise RuntimeError(f"Klaviyo GET {path} HTTP {r.status_code}: {(r.text or '')[:500]}")
    return r.json() or {}


def _campaign_metrics(campaign_id: str) -> dict[str, Any]:
    try:
        stats = _get(
            f"/campaigns/{campaign_id}/campaign-messages/",
            {"include": "template"},
        )
    except Exception:
        stats = {}
    # Reporting API for aggregates
    try:
        report = requests.post(
            f"{KLAVIYO_BASE}/campaign-values-reports/",
            headers={**_headers(), "Content-Type": "application/json"},
            json={
                "data": {
                    "type": "campaign-values-report",
                    "attributes": {
                        "statistics": [
                            "opens",
                            "open_rate",
                            "clicks",
                            "click_rate",
                            "recipients",
                            "unsubscribe_rate",
                            "conversion_value",
                        ],
                        "timeframe": {"key": "last_30_days"},
                        "conversion_metric_id": None,
                        "filter": f'equals(campaign_id,"{campaign_id}")',
                    },
                }
            },
            timeout=120,
        )
        rep_data = report.json() if report.text else {}
    except Exception as e:
        rep_data = {"error": str(e)}

    return {"messages": stats, "report": rep_data}


def fetch_campaigns_last_30d() -> list[dict[str, Any]]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
    rows: list[dict[str, Any]] = []
    path = "/campaigns"
    params = {"filter": "equals(messages.channel,'email')"}
    data = _get(path, params)
    while True:
        for item in data.get("data") or []:
            attrs = item.get("attributes") or {}
            send_time = (attrs.get("send_time") or attrs.get("scheduled_at") or "")[:10]
            if send_time and send_time < cutoff:
                continue
            cid = item.get("id") or ""
            name = attrs.get("name") or ""
            recipients = opens = open_rate = clicks = click_rate = revenue = unsub = ""
            try:
                rep = requests.post(
                    f"{KLAVIYO_BASE}/campaign-values-reports/",
                    headers={**_headers(), "Content-Type": "application/json"},
                    json={
                        "data": {
                            "type": "campaign-values-report",
                            "attributes": {
                                "statistics": [
                                    "recipients",
                                    "open_rate",
                                    "click_rate",
                                    "unsubscribe_rate",
                                    "conversion_value",
                                ],
                                "timeframe": {"key": "last_30_days"},
                                "filter": f'equals(campaign_id,"{cid}")',
                            },
                        }
                    },
                    timeout=120,
                )
                if rep.status_code == 200:
                    results = (rep.json().get("data") or {}).get("attributes", {}).get("results") or []
                    if results:
                        stats = (results[0].get("statistics") or {})
                        recipients = stats.get("recipients", "")
                        open_rate = stats.get("open_rate", "")
                        click_rate = stats.get("click_rate", "")
                        unsub = stats.get("unsubscribe_rate", "")
                        revenue = stats.get("conversion_value", "")
            except Exception:
                pass
            rows.append(
                {
                    "campaign_name": name,
                    "send_date": send_time,
                    "recipients": recipients,
                    "open_rate": open_rate,
                    "click_rate": click_rate,
                    "revenue_attributed_inr": revenue,
                    "unsubscribe_rate": unsub,
                }
            )
        next_url = (data.get("links") or {}).get("next")
        if not next_url:
            break
        r = requests.get(next_url, headers=_headers(), timeout=120)
        r.raise_for_status()
        data = r.json() or {}
    return rows


def rows_for_sheet(campaigns: list[dict], synced_at: str) -> list[list]:
    return [
        [
            c.get("campaign_name", ""),
            c.get("send_date", ""),
            c.get("recipients", ""),
            c.get("open_rate", ""),
            c.get("click_rate", ""),
            c.get("revenue_attributed_inr", ""),
            c.get("unsubscribe_rate", ""),
            synced_at,
        ]
        for c in campaigns
    ]
