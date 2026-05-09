"""
WEARTH Behavioural Commerce Engine
POST /api/klaviyo/create-personalised-discount
Auto-registered in app.py — do not delete.
"""

import os
import re
import random
import string
import secrets
import requests
import traceback
from datetime import datetime, timezone, timedelta
from flask import request, jsonify


def _bce_generate_code(first_name):
    clean = re.sub(r'[^A-Z]', '', first_name.upper())[:6]
    suffix = secrets.token_hex(2).upper()
    return f"{clean}_{suffix}"


def create_personalised_discount():
    """
    POST /api/klaviyo/create-personalised-discount
    Body: { email, first_name, cart_items (list), cart_value (float) }
    Creates unique Shopify 20%-off pair-bundle code (24h expiry),
    updates Klaviyo profile, fires Personalised Offer Created event.
    """
    data = request.get_json(force=True, silent=True) or {}
    email = (data.get('email') or '').strip().lower()
    first_name = (data.get('first_name') or '').strip()
    cart_items = data.get('cart_items') or []
    cart_value = float(data.get('cart_value') or 0)

    if not email or not first_name:
        return jsonify({'ok': False, 'error': 'email and first_name are required'}), 400

    try:
        SHOPIFY_STORE = os.environ.get('SHOPIFY_STORE', '')
        SHOPIFY_TOKEN_VAL = os.environ.get('SHOPIFY_TOKEN', '')
        KLAVIYO_KEY = os.environ.get('KLAVIYO_PRIVATE_KEY', '')

        code = _bce_generate_code(first_name)
        starts_at = datetime.now(timezone.utc).isoformat()
        ends_at = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()

        # 1. Shopify price rule — 20% off, 2+ items, 1 use, 24h
        sh_h = {'X-Shopify-Access-Token': SHOPIFY_TOKEN_VAL, 'Content-Type': 'application/json'}
        rule_resp = requests.post(
            f'https://{SHOPIFY_STORE}/admin/api/2024-01/price_rules.json',
            json={'price_rule': {
                'title': f'PERSONALISED_{code}',
                'target_type': 'line_item', 'target_selection': 'all',
                'allocation_method': 'across', 'value_type': 'percentage',
                'value': '-20.0', 'customer_selection': 'all',
                'starts_at': starts_at, 'ends_at': ends_at,
                'usage_limit': 1, 'once_per_customer': True,
                'prerequisite_quantity_range': {'greater_than_or_equal_to': 2},
            }},
            headers=sh_h, timeout=30
        )
        rule_resp.raise_for_status()
        rule_id = rule_resp.json()['price_rule']['id']

        # 2. Shopify discount code
        requests.post(
            f'https://{SHOPIFY_STORE}/admin/api/2024-01/price_rules/{rule_id}/discount_codes.json',
            json={'discount_code': {'code': code}},
            headers=sh_h, timeout=30
        ).raise_for_status()

        # 3. Klaviyo profile lookup + property update
        kv_h = {
            'Authorization': f'Klaviyo-API-Key {KLAVIYO_KEY}',
            'revision': '2024-10-15',
            'Content-Type': 'application/vnd.api+json',
            'Accept': 'application/vnd.api+json',
        }
        expiry_dt = datetime.fromisoformat(ends_at)
        expiry_display = expiry_dt.strftime('%-d %b, %-I%p').replace('AM', 'am').replace('PM', 'pm')

        profile_id = None
        prof_resp = requests.get(
            'https://a.klaviyo.com/api/profiles/',
            headers=kv_h,
            params={'filter': f'equals(email,"{email}")', 'fields[profile]': 'id'},
            timeout=15
        )
        if prof_resp.status_code == 200:
            pdata = prof_resp.json().get('data', [])
            if pdata:
                profile_id = pdata[0]['id']
                requests.patch(
                    f'https://a.klaviyo.com/api/profiles/{profile_id}/',
                    json={'data': {'type': 'profile', 'id': profile_id,
                                  'attributes': {'properties': {
                                      'custom_code': code,
                                      'discount_expiry': expiry_display,
                                      'discount_pct': '20',
                                  }}}},
                    headers=kv_h, timeout=15
                )

        # 4. Klaviyo event — triggers Personalised Offer Created flow
        items = cart_items or []
        product_hint = (
            items[0] if len(items) == 1 else
            f"{items[0]} and {items[1]}" if len(items) >= 2 else
            'What you left in your cart'
        )
        requests.post(
            'https://a.klaviyo.com/api/events/',
            json={'data': {'type': 'event', 'attributes': {
                'metric': {'data': {'type': 'metric', 'attributes': {'name': 'Personalised Offer Created'}}},
                'profile': {'data': {'type': 'profile', 'attributes': {'email': email, 'first_name': first_name}}},
                'properties': {
                    'discount_code': code, 'expiry_date': expiry_display,
                    'product_hint': product_hint, 'cart_value': cart_value,
                    'cart_items': items,
                },
                'time': datetime.now(timezone.utc).isoformat(),
                'unique_id': f'{email}_{code}',
            }}},
            headers=kv_h, timeout=15
        )

        return jsonify({
            'ok': True, 'code': code, 'expiry': expiry_display,
            'shopify_rule_id': rule_id,
            'klaviyo_profile_found': profile_id is not None,
        })

    except requests.HTTPError as e:
        status = e.response.status_code if e.response else 500
        detail = (e.response.text if e.response else str(e))[:500]
        return jsonify({'ok': False, 'error': f'HTTP {status}', 'detail': detail}), 500
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e), 'trace': traceback.format_exc()}), 500
