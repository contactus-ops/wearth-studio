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
        {'id': '6004039008462', 'name': 'Fitness and wellness'},
    ],
    'publisher_platforms': ['facebook', 'instagram'],
    'facebook_positions': ['feed'],
    'instagram_positions': ['stream', 'story', 'reels'],
}

def _h():
    return {'Authorization': f'Bearer {META_TOKEN}'}

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

def _creative_video(video_url, variant):
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
                'call_to_action': {'type': 'SHOP_NOW', 'value': {'ink': 'https://wearthactive.com'}},
            },
        },
    }, timeout=60)
    if r2.status_code not in [200, 201]:
        return None, r2.text
    return r2.json().get('id'), None

def _ad_set(name):
    r = requests.post(f'{GRAPH}/act_{META_AD_ACCOUNT}/adsets', headers=_h(), json={
        'name': name,
        'campaign_id': META_CAMPAIGN_ID,
        'daily_budget': 35000,  # ₹350 in paise
        'bid_strategy': 'LOWEST_COST_WITHOUT_CAP',
        'billing_event': 'IMPRESSIONS',
        'optimization_goal': 'LINK_CLICKS',
        'targeting': TARGETING,
        'status': 'ACTIVE',
        'start_time': int(time.time()),
    }, timeout=60)
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
    if not image_b64:
        return jsonify({'error': 'image_b64 required'}), 400
    ad_sets, ads, errors = [], [], []
    img_hash, err = _upload_image_b64(image_b64)
    if err:
        return jsonify({'error': f'img upload: {err}'}), 500
    for i, v in enumerate(COPY_VARIANTS):
        if i == 2 and video_url:
            cid, err = _creative_video(video_url, v)
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
    caption = data.get("caption", "fabric grown, not made.

WEARTH Active.
Shop wearthactive.com

#WEARTH #plantbased #activewear")
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
