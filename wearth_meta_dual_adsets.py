# -*- coding: utf-8 -*-
# TARGET ROAS 4:1 AT ₹15K/MONTH SPEND. Every change here aims at efficient reach for WEARTH Active:
# premium urban India buyers who pay for quality — align targeting and pacing with measurable purchase ROAS.

"""
WEARTH Meta dual ad-set pipeline: Shopify buyer emails → Custom Audience →
1% India Lookalike → narrow targeting on Women + Men ad sets + creatives.

Requires env: META_ACCESS_TOKEN, META_AD_ACCOUNT_ID, SHOPIFY_TOKEN, SHOPIFY_STORE.

Run: python wearth_meta_dual_adsets.py [--dry-run]

POST /api/meta/weareth-dual-adsets-setup JSON:
  dry_run: true  → preflight only (interests with confidence, cities, seed count).
  dry_run: false → internal preflight then LIVE if no critical_warnings and buyer seed ≥ WEARTH_MIN_SEED (default 95).
  force_live: true → bypass seed gate (dangerous).
  skip_audiences: true → use WEARTH_LOOKALIKE_ID (no Shopify upload).
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import re
import sys
import time
import traceback
from typing import Any, Dict, List, Optional, Tuple

import requests

META_GRAPH_VERSION = os.environ.get("META_GRAPH_VERSION", "v22.0")
META_GRAPH_BASE = f"https://graph.facebook.com/{META_GRAPH_VERSION}"

# TARGET ROAS 4:1 AT ₹15K/MONTH SPEND — IDs tunable via env for staging.
WOMEN_ADSET_ID = os.environ.get("WEARTH_WOMEN_ADSET_ID", "120245108705080305")
MEN_CAMPAIGN_ID = os.environ.get("WEARTH_MEN_CAMPAIGN_ID", "120245108704880305")
SOURCE_CREATIVE_AD_ID = os.environ.get("WEARTH_SOURCE_AD_ID", "120245108707140305")

SHOPIFY_API_VERSION = os.environ.get("SHOPIFY_API_VERSION", "2024-10")
# Default 95: Shopify Customer.orders_count is often stale; order-derived unique emails (~97 here) are the real buyer set.
MIN_SEED_BUYERS = int(os.environ.get("WEARTH_MIN_SEED", "95"))
MAX_INTEREST_IDS = int(os.environ.get("WEARTH_MAX_INTERESTS", "38"))

# Unified demo band: premium urban India 24–42 (north star: ingredient-conscious spenders).
WOMEN_AGE = (24, 42)
MEN_AGE = (24, 42)
MEN_DAILY_BUDGET_INR = 150

# --- Interest stacks (weighted = listed first for resolution / dedupe priority). ---
# TARGET ROAS 4:1 AT ₹15K/MONTH SPEND — broaden affinity beyond yoga/pilates for premium fitness + quality buyers.

MASTER_FITNESS = [
    "yoga", "pilates", "running", "CrossFit", "Hyrox", "functional fitness", "Barre workout",
    "cycling", "swimming", "triathlon", "marathon running", "pickleball", "tennis",
    "squash", "rock climbing", "HIIT", "home workout", "fitness gym", "weightlifting", "calisthenics",
]

MASTER_WELLNESS = [
    "clean eating", "organic food", "nutrition", "Health food", "ayurveda",
    # Meta has no adinterest for "Cryotherapy"/"Pranayama"; these labels index and match the same niches.
    "Meditation", "sleep", "Quantified Self", "cold therapy", "breathing exercises",
]

MASTER_PREMIUM_LIFESTYLE = [
    "international travel", "business travel", "luxury hotel", "fine dining", "wine",
    "whisky", "golf", "Luxury goods", "skin care", "Organic cosmetics", "clean beauty",
]

MASTER_FASHION = [
    "athleisure", "sportswear", "Nike", "Adidas", "sustainable fashion",
    "Luxury goods", "designer clothing",
]

MASTER_PROFESSIONAL = [
    "entrepreneurship", "startup company", "business", "physician", "architecture",
    "creative director", "consulting",
]

MASTER_DIGITAL_BEHAVIOR = [
    "online shopping", "engaged shoppers", "travel",
]

# Women: heavier yoga / pilates / barre / beauty / wellness / organic / fashion / travel.
WOMEN_WEIGHTED_FIRST = [
    "yoga", "pilates", "Barre workout", "clean beauty", "skin care", "wellness", "organic food",
    "Luxury goods", "international travel", "Organic cosmetics", "meditation", "athleisure",
]

# Men: heavier endurance / strength sports / golf / menswear / whisky / entrepreneurship.
MEN_WEIGHTED_FIRST = [
    "running", "CrossFit", "Hyrox", "cycling", "triathlon", "golf", "pickleball",
    "menswear", "whisky", "entrepreneurship", "marathon running", "functional fitness",
]


def _dedupe_ordered(seq: List[str]) -> List[str]:
    seen = set()
    out = []
    for x in seq:
        k = x.strip().lower()
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(x.strip())
    return out


def _build_gender_stack(weighted: List[str], master_lists: List[List[str]]) -> List[str]:
    """TARGET ROAS 4:1 AT ₹15K/MONTH SPEND — ordered broad stack, deduped, capped later."""
    combined = _dedupe_ordered(weighted + [x for lst in master_lists for x in lst])
    return combined


INTERESTS_WOMEN_QUERIES = _build_gender_stack(
    WOMEN_WEIGHTED_FIRST,
    [MASTER_FITNESS, MASTER_WELLNESS, MASTER_PREMIUM_LIFESTYLE, MASTER_FASHION, MASTER_PROFESSIONAL, MASTER_DIGITAL_BEHAVIOR],
)
INTERESTS_MEN_QUERIES = _build_gender_stack(
    MEN_WEIGHTED_FIRST,
    [MASTER_FITNESS, MASTER_WELLNESS, MASTER_PREMIUM_LIFESTYLE, MASTER_FASHION, MASTER_PROFESSIONAL, MASTER_DIGITAL_BEHAVIOR],
)

# Alternate search strings when Meta returns no adinterest match (TARGET ROAS 4:1 AT ₹15K/MONTH SPEND).
INTEREST_FALLBACKS: Dict[str, List[str]] = {
    "hyrox": ["Hyrox", "hybrid training", "functional fitness"],
    "pickleball": ["pickleball"],
    "barre workout": ["Pure Barre", "barre", "barre fitness", "ballet fitness"],
    "clean beauty": ["organic skincare", "natural cosmetics"],
    "menswear": ["men's clothing", "mens fashion"],
    "whisky": ["whiskey", "single malt"],
    "skin care": ["skincare", "beauty"],
    "home workout": ["home exercise", "fitness at home"],
    "fitness gym": ["health club", "gym membership", "fitness center"],
    "health food": ["organic food", "whole foods"],
    "quantified self": [
        "Quantified Self",
        "self-tracking",
        "lifelogging",
        "wearable technology",
        "fitness tracking",
    ],
    "cold therapy": [
        "Cryotherapy",
        "ice bath",
        "cryo",
        "cold plunge",
        "cryo spa",
        "Wim Hof Method",
        # Broad targets last — Meta often has no cold-plunge interest for IN accounts.
        "wellness",
        "spa",
        "sauna",
    ],
    "breathing exercises": [
        "Pranayama",
        "yoga breathing",
        "breathwork",
        "meditation breathing",
        "pranayama yoga",
        "yoga",
        "Meditation",
    ],
    "organic cosmetics": ["natural cosmetics", "organic makeup"],
    "luxury goods": ["luxury retail", "premium goods"],
    "sleep": ["sleep health", "wellness"],
    "luxury hotel": ["luxury travel", "five star hotel"],
    "designer clothing": ["Luxury goods", "premium fashion"],
    "startup company": ["startup", "entrepreneurship"],
    "engaged shoppers": ["online shoppers", "shopping"],
    "travel": ["frequent travelers", "travel enthusiasts"],
}


# Tier 1 = core metros; Tier 2 = secondary expansion (same ad set — Meta has no per-city bid;
# clone ad sets with lower budget for tier-2-only tests to simulate “lower bid”).
CITY_QUERIES: List[Tuple[str, str, int]] = [
    ("Mumbai", "IN", 1),
    ("Delhi", "IN", 1),
    ("Bangalore", "IN", 1),
    ("Pune", "IN", 2),
    ("Hyderabad", "IN", 2),
    ("Chennai", "IN", 2),
    ("Gurgaon", "IN", 2),
    ("Noida", "IN", 2),
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
    # TARGET ROAS 4:1 AT ₹15K/MONTH SPEND — reliable Graph calls for optimization workflows.
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


def _interest_rows_only(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """targetingsearch mixes behaviors/devices with interests — keep rows typed as interests only."""
    out: List[Dict[str, Any]] = []
    for pick in rows:
        t = (pick.get("type") or "").strip().lower()
        if t and t not in ("interests", "interest", "adinterest"):
            continue
        out.append(pick)
    return out


def search_interest_raw(q: str) -> List[Dict[str, Any]]:
    # TARGET ROAS 4:1 AT ₹15K/MONTH SPEND — account targetingsearch returns geo-valid interests; fall back to global /search.
    params = {"type": "adinterest", "q": q.strip(), "limit": 25}
    act = _env_act_id()
    if act:
        try:
            out = meta_request("GET", f"{act}/targetingsearch", params=params)
            data = _interest_rows_only(list(out.get("data") or []))
            if data:
                return data
        except Exception:
            pass
    out = meta_request("GET", "search", params=params)
    # Global /search with type=adinterest returns interest entries; do not filter (types vary by Graph version).
    return list(out.get("data") or [])


def match_confidence(query: str, matched_name: str) -> Tuple[str, float]:
    """Return label high|medium|low and 0..1 score."""
    q = (query or "").lower().strip()
    m = (matched_name or "").lower().strip()
    if not m:
        return "low", 0.0
    if q == "quantified self" and ("quantif" in m or "wearable" in m or "tracker" in m):
        return "medium", 0.62
    if q == "cold therapy" and any(
        x in m
        for x in (
            "cryo",
            "cold therapy",
            "ice bath",
            "cold plunge",
            "wim hof",
            "wellness",
            "spa",
            "sauna",
        )
    ):
        return "medium", 0.62
    if q == "breathing exercises" and any(
        x in m for x in ("pranayama", "breath", "yoga", "meditation")
    ):
        return "medium", 0.62
    if q == m or q in m or m in q:
        return "high", 0.95
    qt = set(re.split(r"[^\w]+", q)) - {"", "the", "and"}
    mt = set(re.split(r"[^\w]+", m)) - {"", "the", "and"}
    if qt and qt <= mt:
        return "high", 0.88
    overlap = len(qt & mt) / max(len(qt), 1)
    if overlap >= 0.45:
        return "medium", 0.55 + 0.25 * overlap
    if overlap > 0:
        return "low", 0.35 + 0.15 * overlap
    return "low", 0.25


def _confidence_rank(label: str) -> int:
    return {"high": 3, "medium": 2, "low": 1, "none": 0}.get(label, 0)


def _interest_tiebreak(label: str, matched_name: str) -> float:
    """Tiny score bump so ties prefer substring / token-in-name hits over unrelated categories."""
    q = (label or "").lower()
    m = (matched_name or "").lower()
    if not q or not m:
        return 0.0
    b = 0.0
    if q in m or m in q:
        b += 0.02
    for tok in re.split(r"[^\w]+", q):
        if len(tok) >= 4 and tok in m:
            b += 0.004
    return b


def resolve_interest_line(label: str) -> Dict[str, Any]:
    """
    TARGET ROAS 4:1 AT ₹15K/MONTH SPEND — resolve one interest with fallbacks + confidence.
    Scores top Meta results for every query variant and keeps the best match (not only the first API hit).
    """
    tries = [label] + INTEREST_FALLBACKS.get(label.lower().strip(), [])
    tried: List[str] = []
    best_pick: Optional[Dict[str, Any]] = None
    best_score = -1.0
    best_effective = -1.0
    best_conf = "low"
    best_match_query = ""

    for t in tries:
        t = t.strip()
        if not t or t in tried:
            continue
        tried.append(t)
        rows = search_interest_raw(t)
        for pick in rows[:25]:
            mid = str(pick.get("id") or "")
            mname = str(pick.get("name") or "")
            if not mid:
                continue
            conf, score = match_confidence(label, mname)
            effective = score + _interest_tiebreak(label, mname)
            rank = _confidence_rank(conf)
            best_rank = _confidence_rank(best_conf)
            replace = False
            if effective > best_effective:
                replace = True
            elif effective == best_effective and (
                score > best_score or (score == best_score and rank > best_rank)
            ):
                replace = True
            if replace:
                best_effective = effective
                best_score = score
                best_conf = conf
                best_pick = pick
                best_match_query = t

    if best_pick and str(best_pick.get("id") or ""):
        return {
            "query": label,
            "resolved": True,
            "interest_id": str(best_pick.get("id") or ""),
            "matched_name": str(best_pick.get("name") or ""),
            "confidence": best_conf,
            "score": round(best_score, 3),
            "attempted_queries": tried,
            "best_match_query": best_match_query,
        }
    sug = INTEREST_FALLBACKS.get(label.lower().strip(), ["related lifestyle interest"])
    return {
        "query": label,
        "resolved": False,
        "interest_id": None,
        "matched_name": None,
        "confidence": "none",
        "score": 0.0,
        "attempted_queries": tried,
        "suggested_replacements": sug[:4],
    }


def resolve_interest_stack_weighted(
    queries: List[str],
    *,
    max_ids: int = MAX_INTEREST_IDS,
) -> Tuple[List[Dict[str, str]], List[Dict[str, Any]], List[str]]:
    """
    Dedupe by Meta interest id; preserve weighted order.
    TARGET ROAS 4:1 AT ₹15K/MONTH SPEND.
    """
    detailed: List[Dict[str, Any]] = []
    warnings: List[str] = []
    seen_ids = set()
    api_objs: List[Dict[str, str]] = []
    for q in queries:
        if len(api_objs) >= max_ids:
            break
        row = resolve_interest_line(q)
        detailed.append(row)
        if row.get("resolved") and row.get("interest_id"):
            iid = str(row["interest_id"])
            if iid not in seen_ids:
                seen_ids.add(iid)
                api_objs.append({"id": iid, "name": row.get("matched_name") or q})
        else:
            warnings.append(f'No Meta adinterest match for "{q}" — try: {row.get("suggested_replacements")}')
    return api_objs, detailed, warnings


def resolve_cities() -> Tuple[List[dict], List[str]]:
    # TARGET ROAS 4:1 AT ₹15K/MONTH SPEND — metro + tier-2 coverage for scale within ROAS guardrails.
    cities = []
    warns: List[str] = []
    tried_keys = set()
    for q, cc, tier in CITY_QUERIES:
        c = search_city(q, cc)
        if not c and q.lower() == "bangalore":
            c = search_city("Bengaluru", cc)
        if not c and q.lower() == "gurgaon":
            c = search_city("Gurugram", cc)
        if c:
            k = c["key"]
            if k not in tried_keys:
                tried_keys.add(k)
                cities.append({"key": k, "name": c["name"], "tier": tier})
        else:
            warns.append(f"City not resolved in Meta geo search: {q}, {cc}")
    return cities, warns


def search_city(name: str, country: str) -> Optional[Dict[str, Any]]:
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


def _email_from_shopify_order(o: Dict[str, Any]) -> str:
    """Best-effort buyer email on an order (REST fields vary by theme/checkout)."""
    cust = o.get("customer") or {}
    bill = o.get("billing_address") or {}
    ship = o.get("shipping_address") or {}
    for raw in (
        o.get("email"),
        o.get("contact_email"),
        cust.get("email"),
        bill.get("email"),
        ship.get("email"),
    ):
        em = (raw or "").strip().lower()
        if em:
            return em
    return ""


def shopify_customer_emails_with_orders() -> Tuple[List[str], Dict[str, Any]]:
    """TARGET ROAS 4:1 AT ₹15K/MONTH SPEND — buyer seed for lookalike quality.

    Prefer emails from **orders** (ground-truth purchasers). Shopify's Customer.orders_count
    on GET customers.json is often stale, so customer-list-only counts undercount badly.
    Union with customers where orders_count >= 1 for overlap coverage.
    """
    store = (os.environ.get("SHOPIFY_STORE") or "").strip().lower()
    token = (os.environ.get("SHOPIFY_TOKEN") or "").strip()
    meta: Dict[str, Any] = {
        "store": store,
        "customer_pages": 0,
        "order_pages": 0,
        "raw_customers": 0,
        "orders_scanned": 0,
    }
    if not store or not token:
        raise RuntimeError("SHOPIFY_STORE and SHOPIFY_TOKEN required")
    host = store.replace("https://", "").replace("http://", "").strip("/")
    headers = {"X-Shopify-Access-Token": token}

    from_orders: set[str] = set()
    ourl = f"https://{host}/admin/api/{SHOPIFY_API_VERSION}/orders.json?status=any&limit=250"
    while ourl:
        r = requests.get(ourl, headers=headers, timeout=90)
        if r.status_code != 200:
            raise RuntimeError(f"Shopify orders {r.status_code}: {r.text[:500]}")
        data = r.json() or {}
        for o in data.get("orders") or []:
            meta["orders_scanned"] += 1
            em = _email_from_shopify_order(o)
            if em:
                from_orders.add(em)
        meta["order_pages"] += 1
        link = r.headers.get("Link", "")
        next_url = ""
        for part in link.split(","):
            if 'rel="next"' in part:
                next_url = part.split(";")[0].strip().strip("<>")
                break
        ourl = next_url
        if meta["order_pages"] > 250:
            break

    from_customers: set[str] = set()
    curl = f"https://{host}/admin/api/{SHOPIFY_API_VERSION}/customers.json?limit=250"
    while curl:
        r = requests.get(curl, headers=headers, timeout=90)
        if r.status_code != 200:
            raise RuntimeError(f"Shopify customers {r.status_code}: {r.text[:500]}")
        data = r.json() or {}
        for c in data.get("customers") or []:
            meta["raw_customers"] += 1
            em = (c.get("email") or "").strip().lower()
            oc = int(c.get("orders_count") or 0)
            if em and oc >= 1:
                from_customers.add(em)
        meta["customer_pages"] += 1
        link = r.headers.get("Link", "")
        next_url = ""
        for part in link.split(","):
            if 'rel="next"' in part:
                next_url = part.split(";")[0].strip().strip("<>")
                break
        curl = next_url
        if meta["customer_pages"] > 250:
            break

    union = from_orders | from_customers
    meta["unique_buyer_emails_from_orders"] = len(from_orders)
    meta["unique_buyer_emails_from_customers_orders_ge_1"] = len(from_customers)
    meta["unique_buyer_emails"] = len(union)
    meta["pages"] = meta["customer_pages"]  # backward compat for logs
    return sorted(union), meta


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
    # TARGET ROAS 4:1 AT ₹15K/MONTH SPEND — lookalike + affinity OR stack + premium placements.
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
    data = {
        "campaign_id": dest_campaign_id,
        "status_option": status_option,
        "deep_copy": "true" if deep_copy else "false",
    }
    out = meta_request("POST", f"{source_adset_id}/copies", data=data)
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


def _compute_critical_warnings(
    cities: List[dict],
    buyer_count: int,
    skip_audiences: bool,
    women_api_count: int,
    men_api_count: int,
    *,
    check_buyer_seed: bool = True,
) -> List[str]:
    # TARGET ROAS 4:1 AT ₹15K/MONTH SPEND — block live spend when seed/geo/affinity unusable.
    cw = []
    if not cities:
        cw.append("CRITICAL: No cities resolved — cannot build geo targeting.")
    if women_api_count < 1:
        cw.append("CRITICAL: Zero women's interests resolved — broaden queries or fix Meta token scopes.")
    if men_api_count < 1:
        cw.append("CRITICAL: Zero men's interests resolved — broaden queries or fix Meta token scopes.")
    if check_buyer_seed and not skip_audiences and buyer_count < MIN_SEED_BUYERS:
        cw.append(
            f"CRITICAL: Buyer seed {buyer_count} < {MIN_SEED_BUYERS} — raise WEARTH_MIN_SEED or grow matched buyers."
        )
    return cw


def run_weareth_dual_adset_pipeline(
    *,
    dry_run: bool = False,
    skip_audiences: bool = False,
    force_live: bool = False,
) -> Dict[str, Any]:
    """
    TARGET ROAS 4:1 AT ₹15K/MONTH SPEND — preflight always; live only when gates pass unless force_live.
    dry_run=True → stop after preflight (no ad set / audience writes).
    """
    result: Dict[str, Any] = {
        "ok": False,
        "dry_run": dry_run,
        "force_live": force_live,
        "warnings": [],
        "critical_warnings": [],
        "optimization_notes": [
            "TARGET ROAS 4:1 AT ₹15K/MONTH SPEND — pace ₹15k/month ≈ ₹500/day; tune budget across ad sets to hit efficiency targets.",
            "Tier-2 cities share one ad set here (Meta cannot bid lower per city in a single ad set). Clone a tier-2-only ad set at 30–50% daily budget to approximate lower bids.",
            "Placement-limited to FB/IG Feed + IG Feed/Reels/Stories (exclude Audience Network for premium brand safety).",
            "advantage_audience: women inherit existing ad set; men forced to 0 for precision testing.",
            "ROAS 4+: optimize for Purchase with enough weekly volume; else test Initiate Checkout + value rules before scaling.",
            "Ingredient-conscious buyers: creative and landing pages should mirror transparency (fabric composition, origin) to lift conversion rate.",
        ],
    }

    if not _env_token() or not _env_act_id():
        raise RuntimeError("META_ACCESS_TOKEN and META_AD_ACCOUNT_ID are required")

    cities, cw_geo = resolve_cities()
    result["warnings"].extend(cw_geo)
    result["cities_resolved"] = cities
    result["cities_tier1"] = [c for c in cities if c.get("tier") == 1]
    result["cities_tier2"] = [c for c in cities if c.get("tier") == 2]

    int_w_objs, int_w_detail, iw_warn = resolve_interest_stack_weighted(INTERESTS_WOMEN_QUERIES)
    int_m_objs, int_m_detail, im_warn = resolve_interest_stack_weighted(INTERESTS_MEN_QUERIES)
    result["warnings"].extend(iw_warn + im_warn)
    result["interests_resolved"] = {
        "women": int_w_detail,
        "men": int_m_detail,
        "women_api_ids_count": len(int_w_objs),
        "men_api_ids_count": len(int_m_objs),
    }

    emails: List[str] = []
    shop_meta: Dict[str, Any] = {}
    buyer_count = 0
    shopify_ok = bool(
        (os.environ.get("SHOPIFY_STORE") or "").strip() and (os.environ.get("SHOPIFY_TOKEN") or "").strip()
    )
    result["shopify_env_configured"] = shopify_ok

    if not skip_audiences:
        if shopify_ok:
            emails, shop_meta = shopify_customer_emails_with_orders()
            buyer_count = len(set(emails))
            result["shopify"] = shop_meta
            result["buyer_hashes_count"] = buyer_count
        else:
            result["shopify"] = {"configured": False, "note": "SHOPIFY_STORE / SHOPIFY_TOKEN missing on server"}
            result["buyer_hashes_count"] = None
            result["warnings"].append(
                "Shopify credentials not set in Railway — buyer seed count skipped. "
                "Add SHOPIFY_STORE + SHOPIFY_TOKEN for seed + lookalike (required for live)."
            )
            buyer_count = 0
    else:
        result["buyer_hashes_count"] = None

    hashes = [sha256_email(e) for e in emails]

    result["critical_warnings"] = _compute_critical_warnings(
        cities,
        buyer_count,
        skip_audiences,
        len(int_w_objs),
        len(int_m_objs),
        check_buyer_seed=(shopify_ok and not skip_audiences),
    )
    # Dry-run without Shopify should not block on seed — user is validating Meta mapping only.
    if dry_run and not skip_audiences and not shopify_ok:
        result["critical_warnings"] = [x for x in result["critical_warnings"] if "Buyer seed" not in x]

    lookalike_id = (os.environ.get("WEARTH_LOOKALIKE_ID") or "").strip()
    seed_id = ""

    creative_id = ""
    try:
        creative_id = get_ad_creative_id(SOURCE_CREATIVE_AD_ID)
        result["source_creative_id"] = creative_id
    except Exception as ex:
        result["warnings"].append(f"Creative fetch failed: {ex}")

    if dry_run:
        lookalike_id = lookalike_id or "DRY_RUN_LAL"
        tw = build_base_targeting(
            genders=[2],
            age_min=WOMEN_AGE[0],
            age_max=WOMEN_AGE[1],
            cities=cities,
            interests=int_w_objs,
            lookalike_id=lookalike_id,
        )
        tm = build_base_targeting(
            genders=[1],
            age_min=MEN_AGE[0],
            age_max=MEN_AGE[1],
            cities=cities,
            interests=int_m_objs,
            lookalike_id=lookalike_id,
        )
        result["ok"] = True
        result["planned"] = {
            "women_targeting": tw,
            "men_targeting": tm,
            "men_daily_budget_minor": int(MEN_DAILY_BUDGET_INR * 100),
            "copy_from_adset": WOMEN_ADSET_ID,
            "men_campaign": MEN_CAMPAIGN_ID,
        }
        result["preflight_only"] = True
        return result

    if not creative_id:
        result["ok"] = False
        result["critical_warnings"].append("CRITICAL: Could not load creative from source ad — fix WEARTH_SOURCE_AD_ID.")
        result["live_skipped"] = True
        return result

    if not skip_audiences and not shopify_ok:
        result["ok"] = False
        result["critical_warnings"].append(
            "CRITICAL: SHOPIFY_STORE and SHOPIFY_TOKEN must be set in Railway for live buyer seed upload."
        )
        result["live_skipped"] = True
        result["hint"] = "Configure Shopify env vars, or use skip_audiences:true with WEARTH_LOOKALIKE_ID."
        tw = build_base_targeting(
            genders=[2],
            age_min=WOMEN_AGE[0],
            age_max=WOMEN_AGE[1],
            cities=cities,
            interests=int_w_objs,
            lookalike_id=lookalike_id or "UNSET",
        )
        tm = build_base_targeting(
            genders=[1],
            age_min=MEN_AGE[0],
            age_max=MEN_AGE[1],
            cities=cities,
            interests=int_m_objs,
            lookalike_id=lookalike_id or "UNSET",
        )
        result["planned_preview"] = {"women_targeting": tw, "men_targeting": tm}
        return result

    def _allowed_live() -> bool:
        # TARGET ROAS 4:1 AT ₹15K/MONTH SPEND — force_live skips only seed-size gate; geo/affinity still required.
        crit = list(result["critical_warnings"])
        if force_live:
            crit = [x for x in crit if "Buyer seed" not in x]
        if crit:
            return False
        if not force_live and not skip_audiences and buyer_count < MIN_SEED_BUYERS:
            return False
        return True

    gate_fail = not _allowed_live()

    if gate_fail:
        result["ok"] = False
        result["live_skipped"] = True
        result["hint"] = "Fix critical_warnings or set force_live:true (not recommended) or skip_audiences with WEARTH_LOOKALIKE_ID."
        tw = build_base_targeting(
            genders=[2],
            age_min=WOMEN_AGE[0],
            age_max=WOMEN_AGE[1],
            cities=cities,
            interests=int_w_objs,
            lookalike_id=lookalike_id or "UNSET",
        )
        tm = build_base_targeting(
            genders=[1],
            age_min=MEN_AGE[0],
            age_max=MEN_AGE[1],
            cities=cities,
            interests=int_m_objs,
            lookalike_id=lookalike_id or "UNSET",
        )
        result["planned_preview"] = {"women_targeting": tw, "men_targeting": tm}
        return result

    if not skip_audiences:
        seed_id = create_customer_audience("WEARTH Buyers")
        upload_hashed_emails(seed_id, hashes)
        poll_audience_ready(seed_id, "seed")
        lookalike_id = create_lookalike_india_1pct(seed_id, "WEARTH Buyers — 1% Lookalike IN")
        poll_audience_ready(lookalike_id, "lookalike", max_wait_s=180)
        result["custom_audience_id"] = seed_id
        result["lookalike_audience_id"] = lookalike_id
    else:
        if not lookalike_id:
            raise RuntimeError("skip_audiences requires WEARTH_LOOKALIKE_ID")
        result["lookalike_audience_id"] = lookalike_id

    tw = build_base_targeting(
        genders=[2],
        age_min=WOMEN_AGE[0],
        age_max=WOMEN_AGE[1],
        cities=cities,
        interests=int_w_objs,
        lookalike_id=lookalike_id,
    )
    tm = build_base_targeting(
        genders=[1],
        age_min=MEN_AGE[0],
        age_max=MEN_AGE[1],
        cities=cities,
        interests=int_m_objs,
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
    men_budget_minor = int(MEN_DAILY_BUDGET_INR * 100)

    pause_if_needed(WOMEN_ADSET_ID, str(women_as.get("status") or ""))
    update_adset_full(
        WOMEN_ADSET_ID,
        targeting=tw,
        status="ACTIVE",
        targeting_automation=ta,
        promoted_object=promoted if isinstance(promoted, dict) else None,
    )

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
    result["live_completed"] = True
    result["summary"] = (
        f"Women ad set {WOMEN_ADSET_ID} ACTIVE with lookalike {lookalike_id}; "
        f"Men ad set {new_men_id} ACTIVE @ ₹{MEN_DAILY_BUDGET_INR}/day."
    )
    return result


def main():
    try:
        dry = "--dry-run" in sys.argv
        out = run_weareth_dual_adset_pipeline(dry_run=dry)
        print(json.dumps(out, indent=2, default=str))
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e), "trace": traceback.format_exc()}, indent=2))


if __name__ == "__main__":
    main()
