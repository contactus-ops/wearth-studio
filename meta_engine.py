import os
import copy
import json
import time
import base64
import requests
from flask import request, jsonify

META_TOKEN = os.environ.get('META_ACCESS_TOKEN', '')
META_AD_ACCOUNT = os.environ.get('META_AD_ACCOUNT_ID', '')
META_PAGE_ID = os.environ.get('META_PAGE_ID', '')
META_CAMPAIGN_ID = os.environ.get('META_CAMPAIGN_ID', '120245108704880305')
META_PIXEL_ID = os.environ.get('META_PIXEL_ID', '')
IG_USER_ID = os.environ.get('IG_USER_ID', '')
GRAPH = 'https://graph.facebook.com/v22.0'
DRIVE_DL = 'https://drive.google.com/uc?export=download&id='

COPY_VARIANTS = [
    {
        'message': 'you will never go back to polyester.\n\nWEARTH — fabric grown, not made.\nShop wearthactive.com',
        'headline': 'fabric grown, not made.',
        'description': "India's first plant-based activewear.",
    },
    {
        'message': 'worn by women who stopped settling.\n\nWEARTH — closed-loop botanical fabric.\nShop wearthactive.com',
        'headline': 'not performance wear. presence wear.',
        'description': 'Move in what the earth actually made.',
    },
    {
        'message': 'this is what happens when you stop wearing polyester.\n\nWEARTH Active. Plant-based. Made for Mumbai.\nShop wearthactive.com',
        'headline': 'what you put on your skin matters.',
        'description': 'fabric grown, not made.',
    },
]

TARGETING = {
    'age_min': 25, 'age_max': 40, 'genders': [2],
    'geo_locations': {
        'cities': [
            {'key': '2147252', 'name': 'Mumbai', 'region_id': '3850', 'country': 'IN'},
            {'key': '2147300', 'name': 'Delhi', 'region_id': '3843', 'country': 'IN'},
            {'key': '2147284', 'name': 'Bengaluru', 'region_id': '3852', 'country': 'IN'},
        ]
    },
    'interests': [
        {'id': '6003107902433', 'name': 'Yoga'},
    ],
    'publisher_platforms': ['facebook', 'instagram'],
    'facebook_positions': ['feed'],
    'instagram_positions': ['stream', 'story', 'reels'],
}

COHORT_TARGETING = {
    # Women 23-34: mindfulness / performance vibe via younger skew + IG-heavy placements.
    "mindful_performance": {
        "age_min": 23,
        "age_max": 34,
        "genders": [2],
        "geo_locations": {"countries": ["IN"]},
    },
    # Women 30-45: premium-conscious cohort, broader delivery with mature age bracket.
    "premium_conscious": {
        "age_min": 30,
        "age_max": 45,
        "genders": [2],
        "geo_locations": {"countries": ["IN"]},
    },
    # Women 25-40: urban broad discovery (no narrow interests).
    "urban_active_broad": {
        "age_min": 25,
        "age_max": 40,
        "genders": [2],
        "geo_locations": {"countries": ["IN"]},
    },
}

# Keyword hints to split a benchmark interest list into two WEARTH-relevant cohorts (names are lowercased).
# Cohort A skew: purchase authority + material/conscious luxury (aligned with premium plant-based positioning).
_LUXURY_CONSCIOUS_HINTS = (
    "luxury", "wine", "whisky", "hotel", "travel", "skin care", "skin care brands",
    "fine dining", "finedining", "organic food", "vegan", "clean eating", "meditation",
    "sleep", "small luxury", "wellness", "spa", "sustainab", "eco", "natural food",
    "conscious", "mindful", "beauty", "cosmetic", "boutique", "department store",
    "shopping", "retail fashion", "air travel", "business travel",
)
# Cohort B skew: training modality + sport participation (premium fabric as performance upgrade).
_PERFORMANCE_HINTS = (
    "running", "cycling", "crossfit", "hiit", "pilates", "yoga", "swimming", "tennis",
    "golf", "pickleball", "squash", "triathlon", "weightlifting", "calisthenics",
    "climbing", "sportswear", "athleisure", "fitness", "track", "field", "olympic",
    "pure barre", "wearable", "marathon", "trail", "workout", "gym", "strength",
    "rowing", "boxing", "badminton", "basketball", "football", "soccer", "outdoor",
)

def _h():
    return {'Authorization': f'Bearer {META_TOKEN}'}


def _dedupe_interests(rows: list) -> list:
    seen = set()
    out = []
    for x in rows or []:
        if not isinstance(x, dict):
            continue
        iid = str(x.get("id") or "").strip()
        if iid and iid not in seen:
            seen.add(iid)
            out.append({"id": iid, "name": x.get("name") or ""})
    return out


def _extract_interests_from_targeting(targeting: dict) -> list:
    """Flatten interests from flexible_spec[] and legacy top-level interests."""
    if not isinstance(targeting, dict):
        return []
    out = []
    for fs in targeting.get("flexible_spec") or []:
        if not isinstance(fs, dict):
            continue
        for i in fs.get("interests") or []:
            if isinstance(i, dict) and i.get("id"):
                out.append({"id": str(i["id"]), "name": i.get("name") or ""})
    for i in targeting.get("interests") or []:
        if isinstance(i, dict) and i.get("id"):
            out.append({"id": str(i["id"]), "name": i.get("name") or ""})
    return _dedupe_interests(out)


def _split_interests_hooklab_dual(interests: list) -> tuple:
    """
    Split benchmark interests into two complementary cohorts:
    - A: luxury / conscious / premium lifestyle skew
    - B: performance / training / sport skew
    """
    if not interests:
        return [], []
    luxury_conscious = []
    performance = []
    neutral = []
    for i in interests:
        name = (i.get("name") or "").lower()
        if any(h in name for h in _LUXURY_CONSCIOUS_HINTS):
            luxury_conscious.append(i)
        elif any(h in name for h in _PERFORMANCE_HINTS):
            performance.append(i)
        else:
            neutral.append(i)
    half = (len(neutral) + 1) // 2
    cohort_a = _dedupe_interests(luxury_conscious + neutral[:half])
    cohort_b = _dedupe_interests(performance + neutral[half:])
    if len(cohort_a) < 4 or len(cohort_b) < 4:
        mid = max(1, len(interests) // 2)
        cohort_a = _dedupe_interests(interests[:mid])
        cohort_b = _dedupe_interests(interests[mid:])
    return cohort_a, cohort_b


def _targeting_replace_flexible_interests(base_targeting: dict, interests_subset: list) -> dict:
    """Deep-copy benchmark targeting and replace flexible_spec interests (Advantage off)."""
    t = copy.deepcopy(base_targeting)
    t.pop("interests", None)
    if interests_subset:
        t["flexible_spec"] = [{"interests": interests_subset}]
    else:
        t["flexible_spec"] = []
    return _with_advantage_audience(t, 0)


def _with_advantage_audience(targeting: dict, enabled: int = 0) -> dict:
    """
    Meta requires targeting_automation.advantage_audience (0 or 1) on ad set targeting.
    0 = Advantage audience OFF (stick to your targeting spec — matches pre-Advantage behavior).
    1 = Advantage audience ON (Meta may expand beyond your spec).
    """
    t = dict(targeting or {})
    ta = dict(t.get('targeting_automation') or {})
    ta['advantage_audience'] = int(enabled)
    t['targeting_automation'] = ta
    return t


def _act_id_clean() -> str:
    return (META_AD_ACCOUNT or "").strip().replace("act_", "")


def _income_demographics_class_search():
    """
    Meta /search with type=adTargetingCategory&class=income returns income / household-income bands.
    (act_/targetingsearch with limit_type alone often returns unrelated interests — see Marketing API targeting search.)
    """
    r = requests.get(
        f"{GRAPH}/search",
        headers=_h(),
        params={"type": "adTargetingCategory", "class": "income", "limit": 500},
        timeout=55,
    )
    if r.status_code != 200:
        return None, (r.text or "")[:700]
    return r.json() or {}, None


def _household_income_search(q: str):
    """Backward-compatible wrapper: filter income class results by substring q if provided."""
    data, err = _income_demographics_class_search()
    if err:
        return None, err
    rows = (data or {}).get("data") or []
    if not (q or "").strip():
        return {"data": rows}, None
    ql = q.strip().lower()
    filt = [x for x in rows if ql in _norm_target_name(x.get("name", ""))]
    return {"data": filt if filt else rows}, None


def _norm_target_name(s: str) -> str:
    return (s or "").lower().strip()


def _resolve_india_household_income_pair():
    """
    Pick two non-overlapping India household-income tiers for HookLab A vs B:
    - Tier A: highest bucket (Top 10% / equivalent wording)
    - Tier B: next bucket (commonly Top 11–20%)
    Names vary by locale; match heuristically on returned targetingsearch rows.
    """
    data, err = _income_demographics_class_search()
    if err:
        return None, None, {"error": err}
    merged_rows = (data or {}).get("data") or []
    if not merged_rows:
        return None, None, {"error": "income_class_search_returned_empty", "hint": "Account may not have India income segments or token lacks targeting permissions."}

    india_rows = []
    for row in merged_rows:
        name = _norm_target_name(row.get("name", ""))
        if "india" in name or "भारत" in (row.get("name") or ""):
            india_rows.append(row)

    if len(india_rows) < 2:
        india_rows = merged_rows

    def score_top10(row):
        n = _norm_target_name(row.get("name", ""))
        if "11" in n and "20" in n:
            return -100
        if "top 10" in n or "top10" in n:
            return 50
        if "first" in n and "10" in n:
            return 40
        if "10%" in n and "11" not in n and "20%" not in n:
            return 30
        if "decile" in n and "1" in n:
            return 25
        return 0

    def score_1120(row):
        n = _norm_target_name(row.get("name", ""))
        if "top 10" in n or "top10" in n:
            return -100
        if ("11" in n and "20" in n) or "11-20" in n or "11–20" in n:
            return 50
        if "second" in n and "decile" in n:
            return 40
        return 0

    tier_top = max(india_rows, key=score_top10) if india_rows else None
    rest_diff = [x for x in india_rows if tier_top and str(x.get("id")) != str(tier_top.get("id"))]
    rest_sorted = sorted(rest_diff, key=score_1120, reverse=True)
    tier_next = rest_sorted[0] if rest_sorted else None

    if not tier_top or not tier_next:
        sample = [{"id": x.get("id"), "name": x.get("name")} for x in india_rows[:25]]
        sample_all = [{"id": x.get("id"), "name": x.get("name")} for x in merged_rows[:40]]
        return None, None, {
            "error": "could_not_resolve_two_distinct_india_income_tiers",
            "india_row_count": len(india_rows),
            "merged_row_count": len(merged_rows),
            "sample_india_filtered": sample,
            "sample_all_queries": sample_all,
        }

    return tier_top, tier_next, {
        "tier_a_name": tier_top.get("name"),
        "tier_a_id": tier_top.get("id"),
        "tier_b_name": tier_next.get("name"),
        "tier_b_id": tier_next.get("id"),
    }


def _merge_income_into_first_flexible_spec(targeting: dict, income_row) -> dict:
    """Add Meta `income` segment alongside interests in the first flexible_spec clause (AND within that clause)."""
    if not income_row or not income_row.get("id"):
        return targeting
    t = copy.deepcopy(targeting)
    fs = t.get("flexible_spec")
    if not fs:
        t["flexible_spec"] = [{}]
        fs = t["flexible_spec"]
    if not isinstance(fs[0], dict):
        fs[0] = {}
    first = copy.deepcopy(fs[0])
    first["income"] = [{"id": str(income_row["id"]), "name": income_row.get("name") or ""}]
    fs[0] = first
    t["flexible_spec"] = fs
    return _with_advantage_audience(t, 0)


def _strip_income_from_targeting(targeting: dict) -> dict:
    t = copy.deepcopy(targeting)
    fs = t.get("flexible_spec") or []
    if fs and isinstance(fs[0], dict) and "income" in fs[0]:
        fs[0] = {k: v for k, v in fs[0].items() if k != "income"}
        t["flexible_spec"] = fs
    return _with_advantage_audience(t, 0)


def targetingsearch_household_income():
    """
    GET /api/meta/targetingsearch-household-income?q=
    Uses Marketing API class=income (adTargetingCategory). Omit q or q empty for full list; use q=India to filter names.
    """
    q = (request.args.get("q") or "").strip()
    data, err = _household_income_search(q)
    if err:
        return jsonify({"ok": False, "error": err}), 200
    rows = (data or {}).get("data") or []
    slim = [{"id": x.get("id"), "name": x.get("name"), "type": x.get("type")} for x in rows[:80]]
    return jsonify({"ok": True, "q": q, "count": len(rows), "data": slim})


def _campaign_adset_template():
    """
    Reuse a currently accepted adset configuration from the campaign to avoid
    account-specific audience validation failures.
    """
    try:
        r = requests.get(
            f"{GRAPH}/{META_CAMPAIGN_ID}/adsets",
            headers=_h(),
            params={
                "fields": "id,effective_status,daily_budget,bid_strategy,billing_event,optimization_goal,targeting,promoted_object",
                "limit": 10,
            },
            timeout=40,
        )
        if r.status_code != 200:
            return None
        rows = (r.json() or {}).get("data") or []
        for row in rows:
            if str(row.get("effective_status") or "").upper() in {"ACTIVE", "PAUSED"}:
                return row
        return rows[0] if rows else None
    except Exception:
        return None

def _upload_image_b64(image_b64):
    r = requests.post(f'{GRAPH}/act_{META_AD_ACCOUNT}/adimages', headers=_h(),
        data={'bytes': image_b64, 'name': 'wearth.jpg'}, timeout=60)
    if r.status_code != 200:
        return None, r.text
    imgs = r.json().get('images', {})
    if imgs:
        k = list(imgs.keys())[0]
        return imgs[k].get('hash'), None
    return None, 'no hash'

def _creative_image(img_hash, variant):
    r = requests.post(f'{GRAPH}/act_{META_AD_ACCOUNT}/adcreatives', headers=_h(), json={
        'name': f'WEARTH — {variant["headline"][:40]}',
        'object_story_spec': {
            'page_id': META_PAGE_ID,
            'link_data': {
                'image_hash': img_hash,
                'link': 'https://wearthactive.com',
                'message': variant['message'],
                'name': variant['headline'],
                'description': variant['description'],
                'call_to_action': {'type': 'SHOP_NOW', 'value': {'link': 'https://wearthactive.com'}},
            },
        },
    }, timeout=60)
    if r.status_code not in [200, 201]:
        return None, r.text
    return r.json().get('id'), None

def _creative_video(video_url, variant, image_hash=None):
    r = requests.post(f'{GRAPH}/act_{META_AD_ACCOUNT}/advideos', headers=_h(),
        json={'name': 'WEARTH UGC', 'file_url': video_url}, timeout=120)
    if r.status_code not in [200, 201]:
        return None, r.text
    vid_id = r.json().get('id')
    if not vid_id:
        return None, 'no video id'
    r2 = requests.post(f'{GRAPH}/act_{META_AD_ACCOUNT}/adcreatives', headers=_h(), json={
        'name': f'WEARTH Video — {variant["headline"][:30]}',
        'object_story_spec': {
            'page_id': META_PAGE_ID,
            'video_data': {
                'video_id': vid_id,
                'message': variant['message'],
                'title': variant['headline'],
                **({'image_hash': image_hash} if image_hash else {}),
                'call_to_action': {'type': 'SHOP_NOW', 'value': {'link': 'https://wearthactive.com'}},
            },
        },
    }, timeout=60)
    if r2.status_code not in [200, 201]:
        return None, r2.text
    return r2.json().get('id'), None

def _ad_set(name):
    template = _campaign_adset_template() or {}
    template_id = str(template.get("id") or "").strip()
    if template_id:
        try:
            rc = requests.post(
                f"{GRAPH}/{template_id}/copies",
                headers=_h(),
                json={
                    "rename_options": {"rename_strategy": "DEEP_RENAME"},
                    "deep_copy": True,
                },
                timeout=60,
            )
            if rc.status_code in [200, 201]:
                jd = rc.json() or {}
                copied_id = (
                    jd.get("copied_adset_id")
                    or jd.get("id")
                    or ((jd.get("data") or {}).get("id") if isinstance(jd.get("data"), dict) else None)
                )
                copied_id = str(copied_id or "").strip()
                if copied_id:
                    # Rename and activate the duplicated adset.
                    requests.post(
                        f"{GRAPH}/{copied_id}",
                        headers=_h(),
                        json={
                            "name": name,
                            "daily_budget": int(template.get("daily_budget") or 35000),
                            "status": "ACTIVE",
                        },
                        timeout=40,
                    )
                    return copied_id, None
        except Exception:
            pass

    targeting = template.get("targeting") if isinstance(template, dict) else None
    if not isinstance(targeting, dict):
        targeting = TARGETING
    # Keep women-focused mandate.
    targeting = dict(targeting)
    targeting["genders"] = [2]
    targeting = _with_advantage_audience(targeting, 0)

    payload = {
        'name': name,
        'campaign_id': META_CAMPAIGN_ID,
        'daily_budget': int(template.get('daily_budget') or 35000),  # ₹350 in paise default
        'bid_strategy': template.get('bid_strategy') or 'LOWEST_COST_WITHOUT_CAP',
        'billing_event': template.get('billing_event') or 'IMPRESSIONS',
        'optimization_goal': template.get('optimization_goal') or 'LINK_CLICKS',
        'targeting': targeting,
        'status': 'ACTIVE',
        'start_time': int(time.time()),
    }
    promoted = template.get("promoted_object")
    if isinstance(promoted, dict) and promoted:
        payload["promoted_object"] = promoted
    r = requests.post(f'{GRAPH}/act_{META_AD_ACCOUNT}/adsets', headers=_h(), json=payload, timeout=60)
    if r.status_code not in [200, 201]:
        txt = r.text or ''
        # Meta can reject narrow audiences. Retry with broad women-only India targeting.
        if 'configured audience is not valid' in txt.lower() or 'broaden your audience' in txt.lower():
            broad = dict(payload)
            broad['targeting'] = _with_advantage_audience({
                'age_min': 23,
                'age_max': 52,
                'genders': [2],
                'geo_locations': {'countries': ['IN']},
                'publisher_platforms': ['facebook', 'instagram'],
                'facebook_positions': ['feed'],
                'instagram_positions': ['stream', 'story', 'reels'],
            }, 0)
            r = requests.post(f'{GRAPH}/act_{META_AD_ACCOUNT}/adsets', headers=_h(), json=broad, timeout=60)
    if r.status_code not in [200, 201]:
        return None, r.text
    return r.json().get('id'), None

def _ad(name, adset_id, creative_id):
    r = requests.post(f'{GRAPH}/act_{META_AD_ACCOUNT}/ads', headers=_h(), json={
        'name': name, 'adset_id': adset_id,
        'creative': {'creative_id': creative_id}, 'status': 'ACTIVE',
    }, timeout=60)
    if r.status_code not in [200, 201]:
        return None, r.text
    return r.json().get('id'), None

def launch_ads():
    data = request.get_json(force=True, silent=True) or {}
    image_b64 = data.get('image_b64', '')
    video_url = data.get('video_url', '')
    combo_name = data.get('combo_name', 'WEARTH')
    try:
        max_variants = int(data.get('max_variants', 3))
    except Exception:
        max_variants = 3
    max_variants = max(1, min(max_variants, len(COPY_VARIANTS)))
    if not image_b64:
        return jsonify({'error': 'image_b64 required'}), 400
    ad_sets, ads, errors = [], [], []
    img_hash, err = _upload_image_b64(image_b64)
    if err:
        return jsonify({'error': f'img upload: {err}'}), 500
    video_slot = 1 if (video_url and max_variants <= 2) else 2
    for i, v in enumerate(COPY_VARIANTS[:max_variants]):
        if i == video_slot and video_url:
            cid, err = _creative_video(video_url, v, image_hash=img_hash)
        else:
            cid, err = _creative_image(img_hash, v)
        if err:
            errors.append(f'creative {i+1}: {err}')
            continue
        asid, err = _ad_set(f'{combo_name} V{i+1} — {v["headline"][:25]}')
        if err:
            errors.append(f'adset {i+1}: {err}')
            continue
        aid, err = _ad(f'{combo_name} Ad V{i+1}', asid, cid)
        if err:
            errors.append(f'ad {i+1}: {err}')
        else:
            ad_sets.append(asid)
            ads.append(aid)
    return jsonify({'ok': True, 'ad_set_ids': ad_sets, 'ad_ids': ads, 'errors': errors})


def retarget_adsets():
    """
    POST /api/meta/retarget-adsets
    Body:
      {
        "items": [
          {"adset_id": "...", "cohort": "premium_conscious", "name_suffix": "Cohort B"},
          {"adset_id": "...", "cohort": "urban_active_broad", "name_suffix": "Cohort C"}
        ]
      }
    """
    data = request.get_json(force=True, silent=True) or {}
    items = data.get("items") or []
    if not isinstance(items, list) or not items:
        return jsonify({"ok": False, "error": "items[] required"}), 400

    results = []
    for item in items:
        adset_id = str((item or {}).get("adset_id") or "").strip()
        cohort = str((item or {}).get("cohort") or "").strip()
        suffix = str((item or {}).get("name_suffix") or "").strip()
        if not adset_id or cohort not in COHORT_TARGETING:
            results.append(
                {
                    "ok": False,
                    "adset_id": adset_id,
                    "cohort": cohort,
                    "error": "invalid adset_id or cohort",
                }
            )
            continue

        # Read current adset name for friendly rename.
        current_name = adset_id
        try:
            rg = requests.get(
                f"{GRAPH}/{adset_id}",
                headers=_h(),
                params={"fields": "name"},
                timeout=30,
            )
            if rg.status_code == 200:
                current_name = (rg.json() or {}).get("name") or current_name
        except Exception:
            pass

        new_name = f"{current_name} | {suffix or cohort}"
        payload = {
            "name": new_name[:240],
            "targeting": _with_advantage_audience(COHORT_TARGETING[cohort], 0),
            "status": "ACTIVE",
        }
        r = requests.post(f"{GRAPH}/{adset_id}", headers=_h(), json=payload, timeout=40)
        if r.status_code not in [200, 201]:
            results.append(
                {
                    "ok": False,
                    "adset_id": adset_id,
                    "cohort": cohort,
                    "http": r.status_code,
                    "error": r.text[:500],
                }
            )
            continue
        results.append({"ok": True, "adset_id": adset_id, "cohort": cohort, "name": new_name[:240]})

    return jsonify({"ok": all(x.get("ok") for x in results), "results": results})


def get_adset_targeting_preview():
    """
    GET /api/meta/adset-targeting-preview?adset_id=...
    Optional: &split=1 — include proposed HookLab cohort A/B interest names (no writes).

    Read-only: returns name + targeting for an ad set (use Plastic Feel as benchmark).
    """
    adset_id = (request.args.get("adset_id") or "").strip()
    want_split = str(request.args.get("split") or "").strip() in ("1", "true", "yes")
    if not adset_id:
        return jsonify({"ok": False, "error": "adset_id query param required"}), 400
    r = requests.get(
        f"{GRAPH}/{adset_id}",
        headers=_h(),
        params={"fields": "id,name,targeting"},
        timeout=40,
    )
    if r.status_code != 200:
        return jsonify({"ok": False, "error": r.text[:800]}), 200
    j = r.json() or {}
    t = j.get("targeting") or {}
    interests = _extract_interests_from_targeting(t)
    n_int = len(interests)
    out = {
        "ok": True,
        "id": j.get("id"),
        "name": j.get("name"),
        "interest_count": n_int,
        "can_split_for_hooklab": n_int >= 4,
        "targeting": t,
    }
    if want_split:
        ca, cb = _split_interests_hooklab_dual(interests)
        out["hooklab_split_preview"] = {
            "cohort_a_count": len(ca),
            "cohort_b_count": len(cb),
            "cohort_a_sample_names": [x.get("name") or x.get("id") for x in ca[:12]],
            "cohort_b_sample_names": [x.get("name") or x.get("id") for x in cb[:12]],
            "note": "Same geo/age/gender/lookalike as benchmark; only flexible_spec interests differ per HookLab ad set.",
        }
    return jsonify(out)


def apply_hooklab_from_benchmark():
    """
    POST /api/meta/apply-hooklab-from-benchmark
    Clone geo/age/gender/lookalike/placements from a working ad set, split interests thematically
    into two cohorts, PATCH two HookLab ad sets.

    Body (JSON):
      { "benchmark_adset_id": "<e.g. Plastic Feel Women ad set id>",
        "hooklab_adset_ids": ["<hooklab ad set 1>", "<hooklab ad set 2>"],
        "name_suffixes": ["Luxury+Conscious", "Performance+Sport"],   // optional
        "household_income_split": true   // optional (default true): India HH tiers — Top ~10% on HookLab 1, next band on HookLab 2
      }
    Benchmark ad set is never modified.
    """
    data = request.get_json(force=True, silent=True) or {}
    benchmark_id = str(data.get("benchmark_adset_id") or "").strip()
    hook_ids = data.get("hooklab_adset_ids") or []
    suffixes = data.get("name_suffixes") or []
    if not benchmark_id:
        return jsonify({"ok": False, "error": "benchmark_adset_id required"}), 400
    if not isinstance(hook_ids, list) or len(hook_ids) != 2:
        return jsonify({"ok": False, "error": "hooklab_adset_ids must be an array of exactly 2 ad set ids"}), 400

    rg = requests.get(
        f"{GRAPH}/{benchmark_id}",
        headers=_h(),
        params={"fields": "id,name,targeting"},
        timeout=45,
    )
    if rg.status_code != 200:
        return jsonify({"ok": False, "error": "benchmark GET failed: " + (rg.text or "")[:800]}), 200
    bj = rg.json() or {}
    base_targeting = bj.get("targeting") or {}
    if not base_targeting:
        return jsonify({"ok": False, "error": "benchmark ad set has no targeting payload"}), 400

    interests = _extract_interests_from_targeting(base_targeting)
    if len(interests) < 4:
        return jsonify(
            {
                "ok": False,
                "error": "not enough interests on benchmark to split; benchmark needs at least 4 interest IDs (flexible_spec or interests)",
                "interest_count": len(interests),
            }
        ), 400

    cohort_a, cohort_b = _split_interests_hooklab_dual(interests)
    payloads = [
        _targeting_replace_flexible_interests(base_targeting, cohort_a),
        _targeting_replace_flexible_interests(base_targeting, cohort_b),
    ]

    use_inc = data.get("household_income_split")
    if use_inc is None:
        use_inc = True

    income_resolution = {
        "household_income_split_requested": bool(use_inc),
        "household_income_applied": False,
    }
    if use_inc:
        tier_hi, tier_next, inc_detail = _resolve_india_household_income_pair()
        if tier_hi and tier_next:
            # Luxury/conscious cohort → highest income band; performance cohort → next band (mutually exclusive HH tiers).
            payloads[0] = _merge_income_into_first_flexible_spec(payloads[0], tier_hi)
            payloads[1] = _merge_income_into_first_flexible_spec(payloads[1], tier_next)
            income_resolution.update(
                {
                    "household_income_applied": True,
                    "hooklab_0_income_id": tier_hi.get("id"),
                    "hooklab_0_income_name": tier_hi.get("name"),
                    "hooklab_1_income_id": tier_next.get("id"),
                    "hooklab_1_income_name": tier_next.get("name"),
                    "resolver_detail": inc_detail,
                }
            )
        else:
            income_resolution["resolve_failed"] = inc_detail

    results = []
    for idx, adset_id in enumerate(hook_ids):
        adset_id = str(adset_id or "").strip()
        if not adset_id:
            results.append({"ok": False, "error": "empty adset id"})
            continue
        suf = ""
        if isinstance(suffixes, list) and len(suffixes) > idx:
            suf = str(suffixes[idx] or "").strip()
        name_extra = ""
        try:
            rg2 = requests.get(
                f"{GRAPH}/{adset_id}",
                headers=_h(),
                params={"fields": "name"},
                timeout=25,
            )
            if rg2.status_code == 200:
                name_extra = (rg2.json() or {}).get("name") or ""
        except Exception:
            pass
        new_name = name_extra
        if suf:
            new_name = f"{name_extra} | WEARTH {suf}"[:240]

        targeting_send = payloads[idx]
        body = {"targeting": targeting_send, "status": "ACTIVE"}
        if new_name:
            body["name"] = new_name[:240]

        r = requests.post(f"{GRAPH}/{adset_id}", headers=_h(), json=body, timeout=50)
        ok_post = r.status_code in [200, 201]
        retried_no_income = False
        if not ok_post and use_inc and income_resolution.get("household_income_applied"):
            body_fb = {"targeting": _strip_income_from_targeting(payloads[idx]), "status": "ACTIVE"}
            if new_name:
                body_fb["name"] = new_name[:240]
            r = requests.post(f"{GRAPH}/{adset_id}", headers=_h(), json=body_fb, timeout=50)
            ok_post = r.status_code in [200, 201]
            retried_no_income = ok_post

        results.append(
            {
                "ok": ok_post,
                "adset_id": adset_id,
                "http": r.status_code,
                "interests_in_cohort": len(cohort_a) if idx == 0 else len(cohort_b),
                "retried_without_household_income": retried_no_income,
                "error": None if ok_post else (r.text or "")[:600],
            }
        )

    return jsonify(
        {
            "ok": all(x.get("ok") for x in results),
            "benchmark_name": bj.get("name"),
            "benchmark_interest_count": len(interests),
            "split_sizes": [len(cohort_a), len(cohort_b)],
            "household_income": income_resolution,
            "results": results,
            "note": "Benchmark unchanged. HookLabs: same geo/age/gender/lookalike as benchmark; interests split; optional India household_income bands for exclusivity between HookLabs.",
        }
    )


def ads_status():
    """
    GET /api/meta/ads-status?ad_ids=1,2,3
    """
    ad_ids_raw = (request.args.get("ad_ids") or "").strip()
    ad_ids = [x.strip() for x in ad_ids_raw.split(",") if x.strip()]
    if not ad_ids:
        return jsonify({"ok": False, "error": "ad_ids query param required"}), 400
    out = []
    for ad_id in ad_ids:
        r = requests.get(
            f"{GRAPH}/{ad_id}",
            headers=_h(),
            params={"fields": "id,name,status,effective_status,adset_id,campaign_id"},
            timeout=30,
        )
        if r.status_code != 200:
            out.append({"id": ad_id, "ok": False, "http": r.status_code, "error": r.text[:400]})
            continue
        out.append({"ok": True, **(r.json() or {})})
    return jsonify({"ok": True, "ads": out})

def post_reel():
    data = request.get_json(force=True, silent=True) or {}
    video_url = data.get('video_url', '')
    caption = data.get('caption', 'fabric grown, not made. 🌿\n\nWEARTH Active — India\'s first plant-based activewear.\nShop wearthactive.com\n\n#WEARTH #plantbased #activewear #sustainablefashion')
    if not video_url:
        return jsonify({'error': 'video_url required'}), 400
    if not IG_USER_ID:
        return jsonify({'error': 'IG_USER_ID not set'}), 500
    r = requests.post(f'{GRAPH}/{IG_USER_ID}/media', headers=_h(), json={
        'media_type': 'REELS', 'video_url': video_url,
        'caption': caption, 'share_to_feed': True,
    }, timeout=120)
    if r.status_code not in [200, 201]:
        return jsonify({'error': f'container: {r.text}'}), 500
    creation_id = r.json().get('id')
    for _ in range(24):
        time.sleep(5)
        s = requests.get(f'{GRAPH}/{creation_id}', headers=_h(),
            params={'fields': 'status_code'}, timeout=30).json()
        sc = s.get('status_code', '')
        if sc == 'FINISHED':
            break
        if sc == 'ERROR':
            return jsonify({'error': 'IG video processing error'}), 500
    r2 = requests.post(f'{GRAPH}/{IG_USER_ID}/media_publish', headers=_h(),
        json={'creation_id': creation_id}, timeout=60)
    if r2.status_code not in [200, 201]:
        return jsonify({'error': f'publish: {r2.text}'}), 500
    return jsonify({'ok': True, 'media_id': r2.json().get('id')})

def make_drive_public():
    data = request.get_json(force=True, silent=True) or {}
    file_id = data.get('file_id', '')
    if not file_id:
        return jsonify({'error': 'file_id required'}), 400
    sa_json = os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON', '')
    if not sa_json:
        return jsonify({'ok': True, 'url': f'{DRIVE_DL}{file_id}', 'note': 'no service account'})
    try:
        import google.oauth2.service_account as sa
        from googleapiclient.discovery import build
        creds = sa.Credentials.from_service_account_info(
            json.loads(sa_json), scopes=['https://www.googleapis.com/auth/drive'])
        svc = build('drive', 'v3', credentials=creds)
        svc.permissions().create(fileId=file_id, body={'type': 'anyone', 'role': 'reader'}).execute()
        return jsonify({'ok': True, 'url': f'{DRIVE_DL}{file_id}'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def post_reel_async():
    data = request.get_json(force=True, silent=True) or {}
    video_url = data.get("video_url", "")
    _default_caption = (
        "fabric grown, not made.\n\n"
        "WEARTH Active.\n"
        "Shop wearthactive.com\n\n"
        "#WEARTH #plantbased #activewear"
    )
    caption = data.get("caption", _default_caption)
    if not video_url: return jsonify({"error": "video_url required"}), 400
    if not IG_USER_ID: return jsonify({"error": "IG_USER_ID not set"}), 500
    r = requests.post(f"{GRAPH}/{IG_USER_ID}/media", headers=_h(), json={
        "media_type": "REELS", "video_url": video_url, "caption": caption, "share_to_feed": True,
    }, timeout=60)
    if r.status_code not in [200, 201]: return jsonify({"error": f"container: {r.text[:300]}"}), 500
    creation_id = r.json().get("id")
    return jsonify({"ok": True, "creation_id": creation_id, "next": f"/api/instagram/reel-publish/{creation_id}"})

def reel_publish(creation_id):
    for _ in range(36):
        time.sleep(5)
        s = requests.get(f"{GRAPH}/{creation_id}", headers=_h(), params={"fields": "status_code"}, timeout=20).json()
        sc = s.get("status_code", "")
        if sc == "FINISHED": break
        if sc == "ERROR": return jsonify({"error": "IG video error"}), 500
    r2 = requests.post(f"{GRAPH}/{IG_USER_ID}/media_publish", headers=_h(), json={"creation_id": creation_id}, timeout=30)
    if r2.status_code not in [200, 201]: return jsonify({"error": f"publish: {r2.text[:200]}"}), 500
    return jsonify({"ok": True, "media_id": r2.json().get("id"), "url": "https://www.instagram.com/wearth_active/"})



def launch_carousel_ads():
    """POST /api/meta/launch-carousel
    2 carousel ad sets: image card (hook) then video card (proof).
    Tribe A: Mindful Mover 25-38  |  Tribe B: Conscious Luxury 30-48
    Women only, Mumbai/Delhi/Bengaluru. Different from default tribes.
    Body: { image_b64, video_url, combo_name }
    Uses LINK_CLICKS optimization for reliable bootstrap publishing.
    """
    data = request.get_json(force=True, silent=True) or {}
    image_b64 = data.get("image_b64", "")
    video_url  = data.get("video_url", "")
    combo_name = data.get("combo_name", "WEARTH Carousel")[:40]

    if not image_b64: return jsonify({"error": "image_b64 required"}), 400
    if not video_url:  return jsonify({"error": "video_url required"}), 400
    img_hash, err = _upload_image_b64(image_b64)
    if err: return jsonify({"error": "image upload: " + str(err)}), 500

    r_vid = requests.post(
        GRAPH + "/act_" + META_AD_ACCOUNT + "/advideos",
        headers=_h(),
        json={"file_url": video_url, "title": combo_name},
        timeout=120
    )
    if r_vid.status_code not in [200, 201]:
        return jsonify({"error": "video upload: " + r_vid.text[:300]}), 500
    video_id = r_vid.json().get("id")
    if not video_id:
        return jsonify({"error": "video_id missing"}), 500

    CAMPAIGN_ID = (os.environ.get("META_CAMPAIGN_ID") or "").strip() or META_CAMPAIGN_ID

    TRIBES = [
        {
            "key": "mindful_mover",
            "name": "Mindful Mover",
            "age_min": 25, "age_max": 38,
            "interests": [],
            "headline": "your body deserves better than polyester",
            "body": "Women who practice yoga know: what touches your skin matters.\nWEARTH is fabric grown from trees, not made from petroleum.\nBreathe it. Move in it. Never go back.",
            "swipe_hint": "swipe to feel the difference",
        },
        {
            "key": "conscious_luxury",
            "name": "Conscious Luxury",
            "age_min": 30, "age_max": 48,
            "interests": [],
            "headline": "the last activewear you will ever need to upgrade",
            "body": "Not fast fashion. Not synthetic.\nWEARTH is closed-loop, plant-based, built to outlast everything else in your wardrobe.\nI literally live in WEARTH now. It is hard to go back. - Nidhi, Bandra",
            "swipe_hint": "see it in motion",
        },
    ]

    ad_sets, ad_ids, errors = [], [], []

    for tribe in TRIBES:
        adset_name = combo_name + " -- " + tribe["name"] + " Carousel"
        targeting = {
            "age_min": tribe["age_min"],
            "age_max": tribe["age_max"],
            "genders": [2],
            "geo_locations": TARGETING["geo_locations"],
            "publisher_platforms": TARGETING["publisher_platforms"],
            "facebook_positions": TARGETING["facebook_positions"],
            "instagram_positions": TARGETING["instagram_positions"],
        }
        if tribe["interests"]:
            targeting["interests"] = tribe["interests"]
        targeting = _with_advantage_audience(targeting, 0)

        r_as = requests.post(
            GRAPH + "/act_" + META_AD_ACCOUNT + "/adsets",
            headers=_h(),
            json={
                "name": adset_name,
                "campaign_id": CAMPAIGN_ID,
                "billing_event": "IMPRESSIONS",
                "optimization_goal": "LINK_CLICKS",
                "daily_budget": 35000,
                "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
                "targeting": targeting,
                "status": "ACTIVE",
            },
            timeout=30
        )
        if r_as.status_code not in [200, 201]:
            errors.append("adset " + tribe["key"] + ": " + r_as.text[:200])
            continue
        asid = r_as.json().get("id")
        ad_sets.append(asid)

        r_c = requests.post(
            GRAPH + "/act_" + META_AD_ACCOUNT + "/adcreatives",
            headers=_h(),
            json={
                "name": combo_name + " Carousel -- " + tribe["name"],
                "object_story_spec": {
                    "page_id": META_PAGE_ID,
                    "link_data": {
                        "link": "https://wearthactive.com",
                        "message": tribe["body"],
                        "multi_share_end_card": False,
                        "child_attachments": [
                            {
                                "link": "https://wearthactive.com",
                                "image_hash": img_hash,
                                "name": tribe["headline"],
                                "description": tribe["swipe_hint"],
                                "call_to_action": {"type": "SHOP_NOW", "value": {"link": "https://wearthactive.com"}},
                            },
                            {
                                "link": "https://wearthactive.com",
                                "video_id": video_id,
                                "name": "plant-based. closed-loop. yours.",
                                "description": "Shop wearthactive.com",
                                "call_to_action": {"type": "SHOP_NOW", "value": {"link": "https://wearthactive.com"}},
                            },
                        ],
                    },
                },
            },
            timeout=30
        )
        if r_c.status_code not in [200, 201]:
            errors.append("creative " + tribe["key"] + ": " + r_c.text[:200])
            continue
        creative_id = r_c.json().get("id")
        ad_name = combo_name + " Carousel Ad -- " + tribe["name"]
        aid, err = _ad(ad_name, asid, creative_id)
        if err:
            errors.append("ad " + tribe["key"] + ": " + str(err))
        else:
            ad_ids.append(aid)

    return jsonify({"ok": True, "ad_set_ids": ad_sets, "ad_ids": ad_ids, "errors": errors, "format": "carousel"})
