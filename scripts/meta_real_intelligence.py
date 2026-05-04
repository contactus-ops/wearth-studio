# -*- coding: utf-8 -*-
# TARGET ROAS 4:1 — Meta adset insights with fallbacks until non-zero spend (or best effort).
from __future__ import annotations

import json
import os
import sys

import requests

APP_BASE = "https://web-production-448c1.up.railway.app"
WOMEN = "120245108705080305"
MEN = "120245228295720305"
CAMPAIGN = "120245108704880305"
META_GRAPH = (os.environ.get("META_GRAPH_BASE") or "https://graph.facebook.com/v22.0").rstrip("/")
FIELDS = "spend,clicks,impressions,reach,cpc,cpm,actions,cost_per_action_type"
PURCHASE_TYPES = frozenset(
    ("purchase", "offsite_conversion.fb_pixel_purchase", "omni_purchase")
)


def update_status(step: str, status: str, evidence) -> None:
    ev = evidence if isinstance(evidence, str) else json.dumps(evidence, ensure_ascii=False)
    ev = str(ev)[:1800]
    h = {"Content-Type": "application/json"}
    tok = (os.environ.get("WEARTH_JOBS_STATUS_TOKEN") or "").strip()
    if tok:
        h["X-Wearth-Status-Token"] = tok
    try:
        r = requests.post(
            f"{APP_BASE}/api/jobs/status/append",
            json={"step": step, "status": status, "evidence": ev},
            headers=h,
            timeout=45,
        )
        print(f"[status] {step} {r.status_code}")
    except Exception as e:
        print(f"[status] {step} FAIL {e}")


def purchase_count(actions) -> float:
    if not isinstance(actions, list):
        return 0.0
    n = 0.0
    for a in actions:
        if not isinstance(a, dict):
            continue
        if str(a.get("action_type") or "") in PURCHASE_TYPES:
            try:
                n += float(a.get("value") or 0)
            except (TypeError, ValueError):
                pass
    return n


def fetch_insights(object_id: str, token: str, date_preset: str, extra: dict | None = None) -> dict:
    params = {
        "fields": FIELDS,
        "date_preset": date_preset,
        "access_token": token,
    }
    if extra:
        params.update(extra)
    r = requests.get(f"{META_GRAPH}/{object_id}/insights", params=params, timeout=60)
    out = {"http": r.status_code, "raw": r.text[:1500]}
    if r.status_code != 200:
        return out
    try:
        data = r.json().get("data") or []
        out["data"] = data
        if data:
            out["first"] = data[0]
    except Exception as e:
        out["parse_error"] = str(e)
    return out


def main() -> int:
    token = (os.environ.get("META_ACCESS_TOKEN") or "").strip()
    if not token:
        print("META_ACCESS_TOKEN missing")
        update_status("meta_real_intelligence", "ERROR", "no token")
        return 1

    adset_fields = "name,status,daily_budget,effective_status,bid_strategy,optimization_goal"
    best: dict | None = None
    best_label = ""
    for aid, lab in ((WOMEN, "women"), (MEN, "men")):
        print(f"\n========== {lab.upper()} ADSET {aid} ==========")
        ar = requests.get(
            f"{META_GRAPH}/{aid}",
            params={"fields": adset_fields, "access_token": token},
            timeout=45,
        )
        print("adset GET", ar.status_code, ar.text[:400])
        ad = ar.json() if ar.status_code == 200 else {}
        if lab == "women":
            best = None
            best_label = ""
            spend = 0.0
            ins_first = None
            for preset, extra in (
                ("maximum", {"level": "adset"}),
                ("maximum", {}),
                ("last_30d", {"level": "adset"}),
                ("last_30d", {}),
                ("last_90d", {"level": "adset"}),
                ("last_90d", {}),
            ):
                res = fetch_insights(aid, token, preset, extra)
                print(f"  insights {preset} extra={extra} http={res.get('http')}")
                first = (res.get("first") or {}) if isinstance(res.get("first"), dict) else {}
                try:
                    sp = float(first.get("spend") or 0)
                except (TypeError, ValueError):
                    sp = 0.0
                print(f"    spend={sp} clicks={first.get('clicks')} imps={first.get('impressions')}")
                if sp > 0 or ins_first is None:
                    ins_first = first
                    spend = sp
                if sp > 0:
                    best = {"preset": preset, "extra": extra, "first": first, "ad": ad}
                    best_label = f"adset {preset} {extra}"
                    break
            if best is None or float((best.get("first") or {}).get("spend") or 0) == 0:
                print("  trying campaign-level insights with adset filter…")
                filt = json.dumps(
                    [{"field": "adset.id", "operator": "IN", "value": [aid]}]
                )
                for preset in ("maximum", "last_30d", "last_90d"):
                    r = requests.get(
                        f"{META_GRAPH}/{CAMPAIGN}/insights",
                        params={
                            "fields": FIELDS,
                            "date_preset": preset,
                            "level": "adset",
                            "filtering": filt,
                            "access_token": token,
                        },
                        timeout=60,
                    )
                    print(f"  campaign insights {preset} http={r.status_code}")
                    if r.status_code != 200:
                        continue
                    data = (r.json() or {}).get("data") or []
                    if not data:
                        continue
                    first = data[0]
                    try:
                        sp = float(first.get("spend") or 0)
                    except (TypeError, ValueError):
                        sp = 0.0
                    print(f"    spend={sp}")
                    if sp > 0 or best is None:
                        best = {"preset": preset, "extra": {"campaign_filtered": True}, "first": first, "ad": ad}
                        best_label = f"campaign>{preset}"
                    if sp > 0:
                        break

            first = (best or {}).get("first") or {}
            spend = float(first.get("spend") or 0)
            clicks = float(first.get("clicks") or 0)
            imps = float(first.get("impressions") or 0)
            pur = purchase_count(first.get("actions"))
            cpa = (spend / pur) if pur > 0 else None
            gap = (cpa - 900.0) if cpa is not None else None
            status_line = "ON TRACK" if (cpa is not None and cpa <= 1000) else "BEHIND"
            if cpa is not None and cpa > 2500:
                status_line = "CRITICAL"
            print(
                f"\nROAS scorecard ({best_label}): spend ₹{spend:.2f} · clicks {int(clicks)} · "
                f"purchases {int(pur)} · CPA ₹{cpa if cpa is not None else 'N/A'} · "
                f"gap to ₹800 target: ₹{gap if gap is not None else 'N/A'} · {status_line}"
            )
            update_status(
                "meta_real_intelligence",
                "COMPLETE",
                {
                    "spend": spend,
                    "purchases": int(pur),
                    "cpa": cpa,
                    "gap_to_target": gap,
                    "source": best_label,
                },
            )
        else:
            print(
                "men adset:",
                ad.get("name"),
                "daily_budget",
                ad.get("daily_budget"),
                "bid_strategy",
                ad.get("bid_strategy"),
                "optimization_goal",
                ad.get("optimization_goal"),
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
