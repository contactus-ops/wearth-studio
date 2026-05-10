import os
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

def _h():
    return {'Authorization': f'Bearer {META_TOKEN}'}


def _with_advantage_audience(targeting: dict, enabled: int = 1) -> dict:
    """
    Meta requires targeting_automation.advantage_audience (0 or 1) on ad set targeting.
    """
    t = dict(targeting or {})
    ta = dict(t.get('targeting_automation') or {})
    ta['advantage_audience'] = int(enabled)
    t['targeting_automation'] = ta
    return t


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
    targeting = _with_advantage_audience(targeting, 1)

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
            }, 1)
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
            "targeting": _with_advantage_audience(COHORT_TARGETING[cohort], 1),
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
        targeting = _with_advantage_audience(targeting, 1)

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
