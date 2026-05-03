# -*- coding: utf-8 -*-
"""
WEARTH Meta dual ad-set pipeline: Shopify buyer emails → Custom Audience →
1% India Lookalike → narrow targeting on Women + Men ad sets + creatives.

Requires env: META_ACCESS_TOKEN, META_AD_ACCOUNT_ID, SHOPIFY_TOKEN, SHOPIFY_STORE.
Strongly recommended: META_PIXEL_ID (read from existing ad sets for conversion optimization).

Run once from Railway or locally:
  python wearth_meta_dual_adsets.py

This module is imported by app.py POST /api/meta/weareth-dual-adsets-setup
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import sys
import time
import traceback
from typing import Any, Dict, List, Optional, Tuple

import requests

META_GRAPH_VERSION = os.environ.get("META_GRAPH_VERSION", "v22.0")
META_GRAPH_BASE = f"https://graph.facebook.com/{META_GRAPH_VERSION}"

# --- IDs from campaign brief (override via env if needed) ---
WOMEN_ADSET_ID = os.environ.get("WEARTH_WOMEN_ADSET_ID", "120245108705080305")
MEN_CAMPAIGN_ID = os.environ.get("WEARTH_MEN_CAMPAIGN_ID", "120245108704880305")
SOURCE_CREATIVE_AD_ID = os.environ.get("WEARTH_SOURCE_AD_ID", "120245108707140305")

SHOPIFY_API_VERSION = os.environ.get("SHOPIFY_API_VERSION", "2024-10")

# Targeting brief
WOMEN_AGE = (24, 40)
MEN_AGE = (26, 42)
MEN_DAILY_BUDGET_INR = 150

INTERESTS_WOMEN = [
    "yoga", "pilates", "running", "premium fitness", "organic food",
    "international travel", "premium fashion", "athleisure",
]
INTERESTS_MEN = [
    "running", "CrossFit", "gym", "premium fitness", "cycling", "triathlon",
    "international travel", "menswear", "whisky", "golf",
]

CITY_QUERIES = [
    ("Mumbai", "IN"),
    ("Delhi", "IN"),
    ("Bangalore", "IN"),
]


def _env_token() -> str:
    return (os.environ.get("META_ACCESS_TOKEN") or "").strip()


def _env_act_id() -> str:
    x = (os.environ.get("META_AD_ACCOUNT_ID") or "").strip()
    if not x:
        return ""
    return x if x.startswith("act_") else f"act_{x}"


def _meta_error(resp: requests.Response) -> str:
    try:
        j = resp.json()
        err = j.get("error") or {}
        parts = [err.get("message"), err.get("error_user_msg"), str(err.get("code"))]
        return " | ".join(p for p in parts if p)
    except Exception:
        return (resp.text or "")[:800]


def meta_request(method: str, path: str, *, params=None, data=None, files=None) -> dict:
    """Graph API call; path like 'act_123/campaigns' or full edge."""
    token = _env_token()
    if not token:
        raise RuntimeError("META_ACCESS_TOKEN is not set")
    params = dict(params or {})
    params["access_token"] = token
    url = f"{META_GRAPH_BASE}/{path.lstrip('/')}"
    r = requests.request(method, url, params=params, data=data, files=files, timeout=120)
    if r.status_code not in (200, 201):
        raise RuntimeError(_meta_error(r))
    try:
        return r.json()
    except Exception:
        return {}


def act_path(tail: str) -> str:
    return f"{_env_act_id()}/{tail.lstrip('/')}"


def search_interest(q: str) -> Optional[Dict[str, Any]]:
    try:
        out = meta_request(
            "GET",
            "search",
            params={"type": "adinterest", "q": q.strip(), "limit": 5},
        )
        rows = out.get("data") or []
        if rows:
            return {"id": str(rows[0].get("id")), "name": rows[0].get("name", q)}
    except Exception:
        pass
    return None


def search_city(name: str, country: str) -> Optional[Dict[str, Any]]:
    """Resolve Meta geolocation key for a city (India)."""
    try:
        out = meta_request(
            "GET",
            "search",
            params={
                "type": "adgeolocation",
                "q": name,
                "location_types": json.dumps(["city"]),
                "country_code": country,
                "limit": 5,
            },
        )
        for row in out.get("data") or []:
            key = row.get("key")
            if key and row.get("type") == "city":
                return {
                    "key": str(key),
                    "name": row.get("name", name),
                    "country": row.get("country_code", country),
                    "region": row.get("region_id"),
                }
    except Exception:
        pass
    return None


def resolve_interests(labels: List[str]) -> Tuple[List[Dict[str, str]], List[str]]:
    resolved = []
    warnings = []
    for lb in labels:
        m = search_interest(lb)
        if m:
            resolved.append({"id": m["id"], "name": m.get("name") or lb})
        else:
            warnings.append(f'No Meta interest match for "{lb}"')
    return resolved, warnings


def resolve_cities() -> Tuple[List[dict], List[str]]:
    cities = []
    warns: List[str] = []
    tried_keys = set()
    for q, cc in CITY_QUERIES:
        c = search_city(q, cc)
        if not c and q.lower() == "bangalore":
            c = search_city("Bengaluru", cc)
        if c:
            k = c["key"]
            if k not in tried_keys:
                tried_keys.add(k)
                cities.append({"key": k, "name": c["name"]})
        else:
            warns.append(f"City not resolved in Meta geo search: {q}, {cc}")
    return cities, warns


def shopify_customer_emails_with_orders() -> Tuple[List[str], Dict[str, Any]]:
    """Emails from Shopify customers with at least one order (buyers)."""
    store = (os.environ.get("SHOPIFY_STORE") or "").strip().lower()
    token = (os.environ.get("SHOPIFY_TOKEN") or "").strip()
    meta: Dict[str, Any] = {"store": store, "pages": 0, "raw_customers": 0}
    if not store or not token:
        raise RuntimeError("SHOPIFY_STORE and SHOPIFY_TOKEN required")
    host = store.replace("https://", "").replace("http://", "").strip("/")
    emails: List[str] = []
    url = f"https://{host}/admin/api/{SHOPIFY_API_VERSION}/customers.json?limit=250"
    headers = {"X-Shopify-Access-Token": token}
    while url:
        r = requests.get(url, headers=headers, timeout=90)
        if r.status_code != 200:
            raise RuntimeError(f"Shopify customers {r.status_code}: {r.text[:500]}")
        data = r.json() or {}
        for c in data.get("customers") or []:
            meta["raw_customers"] += 1
            em = (c.get("email") or "").strip().lower()
            oc = int(c.get("orders_count") or 0)
            if em and oc >= 1:
                emails.append(em)
        meta["pages"] += 1
        link = r.headers.get("Link", "")
        next_url = ""
        for part in link.split(","):
            if 'rel="next"' in part:
                next_url = part.split(";")[0].strip().strip("<>")
                break
        url = next_url
        if meta["pages"] > 200:
            break
    dedup = sorted(set(emails))
    meta["unique_buyer_emails"] = len(dedup)
    return dedup, meta


def sha256_email(email: str) -> str:
    e = email.strip().lower()
    return hashlib.sha256(e.encode("utf-8")).hexdigest()


def create_customer_audience(name: str) -> str:
    data = {
        "name": name,
        "subtype": "CUSTOM",
        "customer_file_source": "USER_PROVIDED",
        "description": "WEARTH Shopify buyers",
    }
    out = meta_request("POST", act_path("customaudiences"), data=data)
    cid = str(out.get("id") or "")
    if not cid:
        raise RuntimeError(f"Custom audience create failed: {out}")
    return cid


def upload_hashed_emails(audience_id: str, hashes: List[str]) -> None:
    """Batch upload EMAIL_SHA256 rows (session protocol)."""
    if not hashes:
        raise RuntimeError("No emails to upload")
    session_id = random.randint(1, 2**63 - 1)
    batch_size = 8000
    total = len(hashes)
    seq = 0
    for i in range(0, total, batch_size):
        seq += 1
        chunk = hashes[i : i + batch_size]
        rows = [[h] for h in chunk]
        payload = {"schema": "EMAIL_SHA256", "data": rows}
        session = {
            "session_id": session_id,
            "batch_seq": seq,
            "last_batch_flag": i + batch_size >= total,
            "estimated_num_total": total,
        }
        body = {
            "session": json.dumps(session),
            "payload": json.dumps(payload),
        }
        meta_request("POST", f"{audience_id}/users", data=body)


def poll_audience_ready(audience_id: str, label: str, max_wait_s: int = 180) -> Dict[str, Any]:
    """Best-effort poll; lookalikes can take hours — we only wait briefly."""
    t0 = time.time()
    last: Dict[str, Any] = {}
    while time.time() - t0 < max_wait_s:
        try:
            last = meta_request(
                "GET",
                audience_id,
                params={"fields": "name,approximate_count_lower_bound,delivery_status,operation_status"},
            )
        except Exception:
            time.sleep(8)
            continue
        op = last.get("operation_status")
        if isinstance(op, dict):
            code = op.get("code")
            if code in (200, "200"):
                return {"ok": True, "status": last, "label": label}
        time.sleep(8)
    return {"ok": False, "status": last, "label": label, "note": "still processing or timeout — safe to proceed; delivery catches up"}


def create_lookalike_india_1pct(seed_audience_id: str, name: str) -> str:
    spec = {"type": "similarity", "country": "IN", "ratio": 0.01}
    data = {
        "name": name,
        "subtype": "LOOKALIKE",
        "origin_audience_id": seed_audience_id,
        "lookalike_spec": json.dumps(spec),
    }
    out = meta_request("POST", act_path("customaudiences"), data=data)
    lid = str(out.get("id") or "")
    if not lid:
        raise RuntimeError(f"Lookalike create failed: {out}")
    return lid


def build_base_targeting(
    *,
    genders: List[int],
    age_min: int,
    age_max: int,
    cities: List[dict],
    interests: List[Dict[str, str]],
    lookalike_id: str,
) -> Dict[str, Any]:
    """
    Stack: lookalike seed pool + geo + demo + affinity interests + premium placements.
    Note: Meta cannot express 'Samsung Galaxy S only' natively; we use mobile iOS+Android
    and recommend exclusions in Ads Manager for Audience Network / Messenger if needed.
    """
    city_objs = [{"key": c["key"]} for c in cities if c.get("key")]
    interest_objs = [{"id": x["id"]} for x in interests if x.get("id")]
    t: Dict[str, Any] = {
        "genders": genders,
        "age_min": age_min,
        "age_max": age_max,
        "geo_locations": {"cities": city_objs},
        "custom_audiences": [{"id": lookalike_id}],
        "publisher_platforms": ["facebook", "instagram"],
        "facebook_positions": ["feed"],
        "instagram_positions": ["stream", "story", "reels"],
        "device_platforms": ["mobile"],
        "user_os": ["iOS", "Android"],
    }
    if interest_objs:
        t["flexible_spec"] = [{"interests": interest_objs}]
    return t


def get_ad_creative_id(ad_id: str) -> str:
    out = meta_request("GET", ad_id, params={"fields": "creative{id}"})
    cr = out.get("creative") or {}
    cid = str(cr.get("id") or "")
    if not cid:
        raise RuntimeError(f"No creative on ad {ad_id}: {out}")
    return cid


def get_adset(adset_id: str) -> dict:
    fields = (
        "id,name,status,campaign_id,daily_budget,billing_event,optimization_goal,"
        "bid_strategy,promoted_object,targeting,targeting_automation,start_time,end_time"
    )
    return meta_request("GET", adset_id, params={"fields": fields})


def pause_if_needed(adset_id: str, current_status: str) -> bool:
    if (current_status or "").upper() == "ACTIVE":
        meta_request("POST", adset_id, data={"status": "PAUSED"})
        return True
    return False


def update_adset_full(
    adset_id: str,
    *,
    name: Optional[str] = None,
    targeting: Optional[dict] = None,
    daily_budget_minor: Optional[int] = None,
    status: Optional[str] = None,
    targeting_automation: Optional[dict] = None,
    promoted_object: Optional[dict] = None,
) -> dict:
    data: Dict[str, str] = {}
    if name:
        data["name"] = name
    if targeting is not None:
        data["targeting"] = json.dumps(targeting)
    if daily_budget_minor is not None:
        data["daily_budget"] = str(daily_budget_minor)
    if status:
        data["status"] = status
    if targeting_automation is not None:
        data["targeting_automation"] = json.dumps(targeting_automation)
    if promoted_object is not None:
        data["promoted_object"] = json.dumps(promoted_object)
    return meta_request("POST", adset_id, data=data)


def copy_adset(
    source_adset_id: str,
    dest_campaign_id: str,
    *,
    status_option: str = "PAUSED",
    deep_copy: bool = False,
) -> str:
    """POST /{ad-set-id}/copies — returns new ad set id."""
    data = {
        "campaign_id": dest_campaign_id,
        "status_option": status_option,
        "deep_copy": "true" if deep_copy else "false",
    }
    out = meta_request("POST", f"{source_adset_id}/copies", data=data)
    # Response shapes vary by API version (sync vs async job).
    for key in ("copied_adset_ids", "adset_ids", "ids"):
        ids = out.get(key)
        if isinstance(ids, list) and ids:
            return str(ids[0])
    for key in ("copied_adset_id", "adset_id", "id"):
        aid = out.get(key)
        if aid and str(aid).isdigit():
            return str(aid)
    if out.get("success") and out.get("copied_adsets"):
        ca = out["copied_adsets"]
        if isinstance(ca, list) and ca and ca[0].get("id"):
            return str(ca[0]["id"])
    raise RuntimeError(f"Unexpected ad set /copies response: {out}")


def list_ads(adset_id: str) -> List[dict]:
    out = meta_request(
        "GET",
        f"{adset_id}/ads",
        params={"fields": "id,name,status,creative{id}", "limit": 50},
    )
    return list(out.get("data") or [])


def set_ad_status(ad_id: str, status: str) -> dict:
    return meta_request("POST", ad_id, data={"status": status})


def create_ad(adset_id: str, name: str, creative_id: str, status: str = "ACTIVE") -> str:
    body = {
        "name": name,
        "adset_id": adset_id,
        "status": status,
        "creative": json.dumps({"creative_id": creative_id}),
    }
    out = meta_request("POST", act_path("ads"), data=body)
    return str(out.get("id") or "")


def run_weareth_dual_adset_pipeline(
    *,
    dry_run: bool = False,
    skip_audiences: bool = False,
) -> Dict[str, Any]:
    """
    Execute full pipeline. dry_run=True returns planned actions only.
    skip_audiences=True uses WEARTH_LOOKALIKE_ID only (no Shopify seed upload).
    """
    result: Dict[str, Any] = {
        "ok": False,
        "dry_run": dry_run,
        "warnings": [],
        "optimization_notes": [
            "Placement-limited to FB/IG Feed + IG Feed/Reels/Stories (no Audience Network) for premium brand suitability.",
            "Advantage Audience disabled on these ad sets for tighter control; monitor frequency & CPA weekly.",
            "For ROAS 4+: prioritize Purchase optimization with sufficient weekly conversions; otherwise test InitiateCheckout + value rules.",
            "Consider Advantage+ shopping catalog campaigns once pixel fires 50+ purchases / week.",
            "Device-level 'Galaxy S only' is not fully available via API; mobile + OS split is the practical ceiling.",
        ],
    }

    if not _env_token() or not _env_act_id():
        raise RuntimeError("META_ACCESS_TOKEN and META_AD_ACCOUNT_ID are required")

    creative_id = get_ad_creative_id(SOURCE_CREATIVE_AD_ID)
    result["source_creative_id"] = creative_id

    cities, cw = resolve_cities()
    result["warnings"].extend(cw)

    int_w, iw = resolve_interests(INTERESTS_WOMEN)
    int_m, im = resolve_interests(INTERESTS_MEN)
    result["warnings"].extend(iw + im)
    result["interests_resolved"] = {"women": int_w, "men": int_m}
    result["cities_resolved"] = cities

    lookalike_id = (os.environ.get("WEARTH_LOOKALIKE_ID") or "").strip()

    shop_meta = {}
    seed_id = ""
    if not skip_audiences:
        emails, shop_meta = shopify_customer_emails_with_orders()
        result["shopify"] = shop_meta
        hashes = [sha256_email(e) for e in emails]
        result["buyer_hashes_count"] = len(hashes)
        if len(hashes) < 100:
            result["warnings"].append(
                "Seed audience has <100 matched buyers — Meta may reject lookalike creation "
                f"(got {len(hashes)}). Consider importing more historical orders or relax filters."
            )
        if dry_run:
            seed_id = "DRY_RUN_SEED"
            lookalike_id = lookalike_id or "DRY_RUN_LAL"
        else:
            seed_id = create_customer_audience("WEARTH Buyers")
            upload_hashed_emails(seed_id, hashes)
            poll_audience_ready(seed_id, "seed")
            lookalike_id = create_lookalike_india_1pct(seed_id, "WEARTH Buyers — 1% Lookalike IN")
            poll_audience_ready(lookalike_id, "lookalike", max_wait_s=180)
        result["custom_audience_id"] = seed_id
        result["lookalike_audience_id"] = lookalike_id
    else:
        if not lookalike_id:
            if dry_run:
                lookalike_id = "DRY_RUN_LAL"
            else:
                raise RuntimeError("skip_audiences requires WEARTH_LOOKALIKE_ID")
        result["lookalike_audience_id"] = lookalike_id

    tw = build_base_targeting(
        genders=[2],
        age_min=WOMEN_AGE[0],
        age_max=WOMEN_AGE[1],
        cities=cities,
        interests=int_w,
        lookalike_id=lookalike_id,
    )
    tm = build_base_targeting(
        genders=[1],
        age_min=MEN_AGE[0],
        age_max=MEN_AGE[1],
        cities=cities,
        interests=int_m,
        lookalike_id=lookalike_id,
    )

    women_as = get_adset(WOMEN_ADSET_ID)
    promoted = women_as.get("promoted_object")
    if isinstance(promoted, str):
        try:
            promoted = json.loads(promoted)
        except Exception:
            promoted = None
    ta = women_as.get("targeting_automation")
    if isinstance(ta, str):
        try:
            ta = json.loads(ta)
        except Exception:
            ta = None
    if not isinstance(ta, dict):
        ta = {"advantage_audience": 0}

    result["women_adset_before"] = {"id": women_as.get("id"), "status": women_as.get("status")}

    men_budget_minor = int(MEN_DAILY_BUDGET_INR * 100)  # paise

    if dry_run:
        result["ok"] = True
        result["planned"] = {
            "women_targeting": tw,
            "men_targeting": tm,
            "men_daily_budget_minor": men_budget_minor,
            "copy_from_adset": WOMEN_ADSET_ID,
            "men_campaign": MEN_CAMPAIGN_ID,
        }
        return result

    # --- Women ad set ---
    pause_if_needed(WOMEN_ADSET_ID, str(women_as.get("status") or ""))
    update_adset_full(
        WOMEN_ADSET_ID,
        targeting=tw,
        status="ACTIVE",
        targeting_automation=ta,
        promoted_object=promoted if isinstance(promoted, dict) else None,
    )
    # Activate ads in women ad set & align creative
    ad_notes = []
    for ad in list_ads(WOMEN_ADSET_ID):
        aid = str(ad.get("id"))
        if not aid:
            continue
        try:
            set_ad_status(aid, "ACTIVE")
            meta_request("POST", aid, data={"creative": json.dumps({"creative_id": creative_id})})
        except Exception as ex:
            ad_notes.append({"ad_id": aid, "warning": str(ex)})
    if ad_notes:
        result["warnings"].extend([str(x) for x in ad_notes])

    # --- Men ad set: copy then specialize ---
    new_men_id = copy_adset(WOMEN_ADSET_ID, MEN_CAMPAIGN_ID, status_option="PAUSED", deep_copy=False)
    result["men_adset_id"] = new_men_id

    update_adset_full(
        new_men_id,
        name="WEARTH — Men Premium",
        targeting=tm,
        daily_budget_minor=men_budget_minor,
        status="ACTIVE",
        targeting_automation={"advantage_audience": 0},
        promoted_object=promoted if isinstance(promoted, dict) else None,
    )

    men_ad_id = create_ad(new_men_id, "WEARTH — Men — creative clone", creative_id, status="ACTIVE")
    if not men_ad_id:
        result["warnings"].append("Men ad create returned no id — check Ads Manager.")
    else:
        result["men_ad_id"] = men_ad_id

    result["ok"] = True
    result["women_adset_id"] = WOMEN_ADSET_ID
    result["summary"] = (
        f"Women ad set {WOMEN_ADSET_ID} ACTIVE with lookalike {lookalike_id}; "
        f"Men ad set {new_men_id} ACTIVE @ ₹{MEN_DAILY_BUDGET_INR}/day."
    )
    return result


def main():
    try:
        out = run_weareth_dual_adset_pipeline(dry_run="--dry-run" in sys.argv)
        print(json.dumps(out, indent=2, default=str))
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e), "trace": traceback.format_exc()}, indent=2))


if __name__ == "__main__":
    main()
