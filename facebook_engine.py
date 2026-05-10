import os
import requests
from flask import request, jsonify

META_TOKEN = os.environ.get('META_ACCESS_TOKEN', '')
META_PAGE_ID = os.environ.get('META_PAGE_ID', '')
GRAPH = 'https://graph.facebook.com/v22.0'


def _h():
    return {'Authorization': f'Bearer {META_TOKEN}'}


def facebook_post():
    data = request.get_json(force=True, silent=True) or {}
    image_b64 = data.get('image_b64', '')
    caption = data.get('caption', '')
    if not image_b64 or not META_PAGE_ID:
        return jsonify({'error': 'image_b64 and META_PAGE_ID required'}), 400
    r = requests.post(
        f'{GRAPH}/{META_PAGE_ID}/photos',
        headers=_h(),
        data={'source': image_b64, 'caption': caption, 'published': 'true'},
        timeout=60
    )
    if r.status_code not in [200, 201]:
        r2 = requests.post(f'{GRAPH}/{META_PAGE_ID}/feed', headers=_h(), json={'message': caption}, timeout=30)
        if r2.status_code not in [200, 201]:
            return jsonify({'error': f'page post failed: {r.text[:200]}'}), 500
        return jsonify({'ok': True, 'post_id': r2.json().get('id'), 'method': 'text_only'})
    return jsonify({'ok': True, 'post_id': r.json().get('id', r.json().get('post_id')), 'method': 'photo'})


def token_debug():
    r = requests.get(f'{GRAPH}/debug_token', params={'input_token': META_TOKEN, 'access_token': META_TOKEN}, timeout=15)
    if r.status_code != 200:
        return jsonify({'error': r.text[:200]}), r.status_code
    d = r.json().get('data', {})
    return jsonify({'ok': True, 'app_id': d.get('app_id'), 'type': d.get('type'), 'expires_at': d.get('expires_at', 'never - system user token'), 'is_valid': d.get('is_valid'), 'scopes': d.get('scopes', [])})
