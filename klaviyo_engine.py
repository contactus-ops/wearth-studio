# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import time
import threading
import requests
from datetime import datetime, timezone, timedelta

KLAVIYO_PRIVATE_KEY = os.environ.get("KLAVIYO_PRIVATE_KEY", "")
KLAVIYO_ACTIVE_LIST_ID = os.environ.get("KLAVIYO_ACTIVE_LIST_ID", "")
KLAVIYO_ACTIVE_SEGMENT_ID = os.environ.get("KLAVIYO_ACTIVE_SEGMENT_ID", "")
try:
    KLAVIYO_HOT_TOP_N = max(0, int(os.environ.get("KLAVIYO_HOT_TOP_N", "200")))
except ValueError:
    KLAVIYO_HOT_TOP_N = 200

_DEFAULT_ALWAYS_SUPPRESS = (
    "rahulmohata35@gmail.com,abhinav.bhartia93@gmail.com,"
    "abhinav.bhartia10@gmail.com,grpb55@gmail.com,shailaja.gupta94@gmail.com"
)


def always_suppress_emails() -> set[str]:
    raw = os.environ.get("KLAVIYO_ALWAYS_SUPPRESS_EMAILS", _DEFAULT_ALWAYS_SUPPRESS)
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


_active_count_cache_lock = threading.Lock()
_active_count_cache: dict[str, tuple[float, dict]] = {}
def _dt_parse(value):
    """Best-effort parse for ISO-ish datetimes; returns aware UTC datetime or None."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    try:
        if raw.endswith('Z'):
            return datetime.fromisoformat(raw.replace('Z', '+00:00')).astimezone(timezone.utc)
        dt = datetime.fromisoformat(raw)
        return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
            try:
                return datetime.strptime(raw[:19], fmt).replace(tzinfo=timezone.utc)
            except Exception:
                continue
    return None


def _is_recent(dt_obj, days: int) -> bool:
    if not dt_obj:
        return False
    return dt_obj >= (datetime.now(timezone.utc) - timedelta(days=days))


def _truthy_signal(v) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v > 0
    if isinstance(v, str):
        t = v.strip().lower()
        if t in ('', 'none', 'null', 'false', 'no', '0'):
            return False
        return True
    return bool(v)


def _flatten_key_values(obj, prefix=''):
    """Flatten dict/list payload into (path, value) pairs for fuzzy signal extraction."""
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            nk = f'{prefix}.{k}' if prefix else str(k)
            out.extend(_flatten_key_values(v, nk))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            nk = f'{prefix}[{i}]' if prefix else f'[{i}]'
            out.extend(_flatten_key_values(v, nk))
    else:
        out.append((prefix.lower(), obj))
    return out


def _first_recent_date(flat_pairs, key_substrings):
    """Return first parsed datetime whose flattened key path contains any substring."""
    for key, value in flat_pairs:
        if any(sub in key for sub in key_substrings):
            dt = _dt_parse(value)
            if dt:
                return dt
    return None


def _has_any_signal(flat_pairs, key_substrings):
    for key, value in flat_pairs:
        if any(sub in key for sub in key_substrings) and _truthy_signal(value):
            return True
    return False


def _flatten_klaviyo_attributes(attrs: dict) -> list:
    """Flatten profile attributes; subscriptions/predictive_analytics stay nested."""
    if not isinstance(attrs, dict):
        return []
    return _flatten_key_values(attrs)


def _max_numeric_from_flat(flat_pairs, key_substrings) -> float:
    """Max numeric value among keys whose path contains any substring."""
    best = 0.0
    for key, value in flat_pairs:
        if not any(sub in key for sub in key_substrings):
            continue
        try:
            if isinstance(value, bool):
                if value:
                    best = max(best, 1.0)
            elif isinstance(value, (int, float)):
                best = max(best, float(value))
            elif isinstance(value, str):
                s = value.strip().replace(',', '')
                if s:
                    best = max(best, float(s))
        except (TypeError, ValueError):
            continue
    return best


def _best_open_datetime(flat_pairs, attrs):
    """Resolve last email open time from common Klaviyo / Shopify property keys."""
    dt = _first_recent_date(
        flat_pairs,
        [
            '$last_open',
            'last_open',
            'last_open_date',
            'last_email_open',
            'email_last_open',
            'opens_last',
            'unique_open',
            'last_opened',
        ],
    )
    if dt:
        return dt
    # Klaviyo sometimes nests under properties only ΓÇö scan values that parse as dates
    for key, value in flat_pairs:
        if 'open' not in key:
            continue
        parsed = _dt_parse(value)
        if parsed:
            return parsed
    return None


def _best_click_datetime(flat_pairs):
    return _first_recent_date(
        flat_pairs,
        [
            '$last_click',
            'last_click',
            'last_click_date',
            'email_last_click',
            'clicked_email',
            'last_clicked',
        ],
    )


def _best_site_activity_datetime(attrs, flat_pairs):
    """Prefer native Klaviyo profile timestamps, then fuzzy property matches."""
    for cand in ('last_event_date', 'updated'):
        dt = _dt_parse(attrs.get(cand))
        if dt:
            return dt
    return _first_recent_date(
        flat_pairs,
        [
            'last_active',
            'last_seen',
            'last_visit',
            'active_on_site',
            'site_activity',
            'viewed_product',
            'page_view',
        ],
    )


def _placed_order_signal(flat_pairs, attrs: dict) -> bool:
    if _max_numeric_from_flat(
        flat_pairs,
        ['historic_clv', 'average_order', 'total_ordered', 'order_count', 'orders_count',
         'number_of_orders', 'placed_order', 'lifetime_value', 'total_spent', 'shopify'],
    ) > 0:
        return True
    pa = attrs.get('predictive_analytics') if isinstance(attrs.get('predictive_analytics'), dict) else {}
    try:
        for hk in ('historic_clv', 'historic_clv_currency'):
            v = pa.get(hk)
            if v is not None and float(v) > 0:
                return True
    except (TypeError, ValueError):
        pass
    return _has_any_signal(
        flat_pairs,
        ['placed_order', 'ordered', 'purchase', 'checkout_complete', 'fulfilled'],
    )


def _cart_signal(flat_pairs) -> bool:
    if _max_numeric_from_flat(flat_pairs, ['cart', 'checkout', 'added_to_cart']) > 0:
        return True
    return _has_any_signal(
        flat_pairs,
        ['added_to_cart', 'add_to_cart', 'started_checkout', 'checkout_started', 'cart_abandon'],
    )


def _opened_email_signal(last_open_dt, flat_pairs) -> bool:
    if last_open_dt:
        return True
    if _max_numeric_from_flat(
        flat_pairs,
        ['$opens', 'unique_open', 'total_open', 'opens_count', 'email_open', 'received_email'],
    ) > 0:
        return True
    return False


def _clicked_email_signal(last_click_dt, flat_pairs) -> bool:
    if last_click_dt:
        return True
    if _max_numeric_from_flat(
        flat_pairs,
        ['$clicks', 'unique_click', 'total_click', 'clicks_count', 'email_click'],
    ) > 0:
        return True
    return False


def _klaviyo_profile_is_hot(profile: dict) -> bool:
    """
    HOT if any: placed order ever, cart ever, opened email ever, clicked email ever,
    site activity in last 30 days, or profile created within last 55 days.
    """
    attrs = profile.get('attributes', {}) if isinstance(profile, dict) else {}
    flat = _flatten_klaviyo_attributes(attrs)
    created_dt = _dt_parse(attrs.get('created'))
    if created_dt and _is_recent(created_dt, 55):
        return True
    if _placed_order_signal(flat, attrs):
        return True
    if _cart_signal(flat):
        return True
    last_open_dt = _best_open_datetime(flat, attrs)
    if _opened_email_signal(last_open_dt, flat):
        return True
    last_click_dt = _best_click_datetime(flat)
    if _clicked_email_signal(last_click_dt, flat):
        return True
    last_active_dt = _best_site_activity_datetime(attrs, flat)
    if _is_recent(last_active_dt, 30):
        return True
    return False


def _klaviyo_api_post_json(url: str, json_body: dict, max_retries: int = 5):
    """POST JSON:API body to Klaviyo; returns requests.Response."""
    if not KLAVIYO_PRIVATE_KEY:
        raise Exception('KLAVIYO_PRIVATE_KEY not set')
    headers = {
        'Authorization': f'Klaviyo-API-Key {KLAVIYO_PRIVATE_KEY}',
        'Accept': 'application/json',
        'Content-Type': 'application/vnd.api+json',
        'revision': '2024-10-15',
    }
    retries = 0
    while True:
        resp = requests.post(url, headers=headers, json=json_body, timeout=120)
        if resp.status_code == 429 and retries < max_retries:
            wait_sec = 1.0 + retries
            try:
                wait_sec = max(wait_sec, float(resp.headers.get('Retry-After', '0') or 0))
            except Exception:
                pass
            time.sleep(min(wait_sec, 15.0))
            retries += 1
            continue
        return resp


def _klaviyo_api_patch_json(url: str, json_body: dict, max_retries: int = 5):
    """PATCH JSON:API body to Klaviyo; returns requests.Response."""
    if not KLAVIYO_PRIVATE_KEY:
        raise Exception('KLAVIYO_PRIVATE_KEY not set')
    headers = {
        'Authorization': f'Klaviyo-API-Key {KLAVIYO_PRIVATE_KEY}',
        'Accept': 'application/json',
        'Content-Type': 'application/vnd.api+json',
        'revision': '2024-10-15',
    }
    retries = 0
    while True:
        resp = requests.patch(url, headers=headers, json=json_body, timeout=60)
        if resp.status_code == 429 and retries < max_retries:
            wait_sec = 1.0 + retries
            try:
                wait_sec = max(wait_sec, float(resp.headers.get('Retry-After', '0') or 0))
            except Exception:
                pass
            time.sleep(min(wait_sec, 15.0))
            retries += 1
            continue
        return resp


def _klaviyo_api_get(
    url: str,
    params=None,
    max_retries: int = 5,
    http_timeout: float = 45,
    connect_timeout: float | None = None,
) -> dict:
    if not KLAVIYO_PRIVATE_KEY:
        raise Exception('KLAVIYO_PRIVATE_KEY not set')
    headers = {
        'Authorization': f'Klaviyo-API-Key {KLAVIYO_PRIVATE_KEY}',
        'accept': 'application/json',
        'revision': '2024-10-15'
    }
    timeouts = (
        (float(connect_timeout), float(http_timeout))
        if connect_timeout is not None
        else float(http_timeout)
    )
    retries = 0
    while True:
        resp = requests.get(url, params=params, headers=headers, timeout=timeouts)
        if resp.status_code == 429 and retries < max_retries:
            wait_sec = 1.0 + retries
            try:
                wait_sec = max(wait_sec, float(resp.headers.get('Retry-After', '0') or 0))
            except Exception:
                pass
            time.sleep(min(wait_sec, 10.0))
            retries += 1
            continue
        if resp.status_code != 200:
            txt = resp.text[:800]
            raise Exception(f'Klaviyo API {resp.status_code}: {txt}')
        return resp.json()


def _klaviyo_collect_data_pages(url: str, params=None, max_pages: int = 200):
    """Follow JSON:API links.next; returns merged list from data[] across pages."""
    items = []
    next_url = url
    first_params = dict(params) if params else None
    first = True
    for _ in range(max_pages):
        if not next_url:
            break
        payload = _klaviyo_api_get(next_url, params=first_params if first else None)
        first = False
        chunk = payload.get('data') or []
        if isinstance(chunk, list):
            items.extend(chunk)
        nxt = (payload.get('links') or {}).get('next')
        next_url = (str(nxt).strip() if nxt else '') or None
        if next_url:
            time.sleep(0.12)
    return items


def _klaviyo_profile_id_by_email(email: str) -> str:
    em = (email or '').strip().lower()
    if not em:
        return ''
    j = _klaviyo_api_get(
        'https://a.klaviyo.com/api/profiles/',
        params={'filter': f'equals(email,"{em}")', 'page[size]': 1},
    )
    rows = j.get('data') or []
    if isinstance(rows, list) and rows:
        return str(rows[0].get('id') or '').strip()
    return ''


def _fetch_all_klaviyo_profiles(include_predictive: bool = True) -> list:
    """Page through /api/profiles/ until exhausted. Adds a small delay per page."""
    all_profiles = []
    next_url = 'https://a.klaviyo.com/api/profiles/'
    params = {'page[size]': 100}
    if include_predictive:
        params['additional-fields[profile]'] = 'predictive_analytics'
    while next_url:
        payload = _klaviyo_api_get(next_url, params=params)
        params = None  # next_url already contains cursor params
        batch = payload.get('data', [])
        if isinstance(batch, list):
            all_profiles.extend(batch)
        links = payload.get('links', {}) if isinstance(payload, dict) else {}
        next_url = links.get('next') if isinstance(links, dict) else None
        time.sleep(0.2)  # gentle pacing for rate limits
    return all_profiles


def _fetch_paged_profile_emails(resource_url: str) -> set:
    """Collect lowercase emails from any Klaviyo paginated /profiles/ style URL."""
    keep = set()
    next_url = resource_url
    params = {'page[size]': 100}
    while next_url:
        payload = _klaviyo_api_get(next_url, params=params)
        params = None
        for p in payload.get('data', []) or []:
            attrs = p.get('attributes', {}) if isinstance(p, dict) else {}
            em = str(attrs.get('email') or '').strip().lower()
            if em:
                keep.add(em)
        links = payload.get('links', {}) if isinstance(payload, dict) else {}
        next_url = links.get('next') if isinstance(links, dict) else None
        time.sleep(0.15)
    return keep


def _fetch_segment_keep_emails(segment_id: str) -> set:
    """All lowercase emails currently in the segment (profiles to keep unsuppressed)."""
    return _fetch_paged_profile_emails(f'https://a.klaviyo.com/api/segments/{segment_id}/profiles/')


def _fetch_list_keep_emails(list_id: str) -> set:
    """All lowercase emails on the Klaviyo list (profiles to keep unsuppressed)."""
    return _fetch_paged_profile_emails(f'https://a.klaviyo.com/api/lists/{list_id}/profiles/')


def _klaviyo_profile_by_id(profile_id: str) -> dict:
    if not profile_id:
        return {}
    return _klaviyo_api_get(
        f'https://a.klaviyo.com/api/profiles/{profile_id}/',
        params={'additional-fields[profile]': 'predictive_analytics'},
    )


def _klaviyo_first_placed_order_event_payload() -> dict:
    """
    Best-effort retrieval of a placed-order event payload.
    Tries the user-requested filter literal first, then resolves metric id.
    """
    # As requested by user (literal metric_id filter value)
    payload = _klaviyo_api_get(
        'https://a.klaviyo.com/api/events/',
        params={'filter': 'equals(metric_id,"PLACED_ORDER")', 'page[size]': 1}
    )
    if isinstance(payload, dict) and payload.get('data'):
        return payload

    # Fallback: discover placed-order metric id, then fetch events by that id.
    metrics = _klaviyo_api_get(
        'https://a.klaviyo.com/api/metrics/',
        params={'filter': 'contains(name,"Placed Order")', 'page[size]': 20}
    )
    metric_id = ''
    for m in metrics.get('data', []) if isinstance(metrics, dict) else []:
        attrs = m.get('attributes', {}) if isinstance(m, dict) else {}
        name = str(attrs.get('name') or '').strip().lower()
        if 'placed order' in name:
            metric_id = str(m.get('id') or '').strip()
            if metric_id:
                break
    if not metric_id:
        return payload

    return _klaviyo_api_get(
        'https://a.klaviyo.com/api/events/',
        params={'filter': f'equals(metric_id,"{metric_id}")', 'page[size]': 1}
    )


def _score_klaviyo_profile(profile: dict) -> dict:
    """
    Score using Klaviyo v3 profile shape: native fields, properties, subscriptions,
    and optional predictive_analytics (request additional-fields on list/get).
    """
    attrs = profile.get('attributes', {}) if isinstance(profile, dict) else {}
    flat = _flatten_klaviyo_attributes(attrs)

    created_dt = _dt_parse(attrs.get('created'))
    last_open_dt = _best_open_datetime(flat, attrs)
    last_click_dt = _best_click_datetime(flat)
    last_active_dt = _best_site_activity_datetime(attrs, flat)

    subscribed_dt = _first_recent_date(
        flat,
        [
            'consent_timestamp',
            'consent',
            'subscribed',
            'date_consent',
            'opted_in',
            'accepts_marketing',
            'signup',
            'joined',
            'subscribed_at',
        ],
    )
    if not subscribed_dt:
        subscribed_dt = created_dt

    added_to_cart = _cart_signal(flat)
    placed_order = _placed_order_signal(flat, attrs)
    opened_ever = _opened_email_signal(last_open_dt, flat)
    clicked_ever = _clicked_email_signal(last_click_dt, flat)

    opened_last_30 = _is_recent(last_open_dt, 30)
    opened_last_90 = _is_recent(last_open_dt, 90)
    active_last_30 = _is_recent(last_active_dt, 30)
    subscribed_last_60 = _is_recent(subscribed_dt, 60)
    created_over_90 = bool(created_dt and created_dt <= (datetime.now(timezone.utc) - timedelta(days=90)))

    # Do not treat "missing engagement data" as never opened ΓÇö only explicit zero open metrics.
    open_max = _max_numeric_from_flat(
        flat,
        ['$opens', 'opens', 'unique_open', 'total_open', 'email_open', 'received_email', 'recipients'],
    )
    has_open_metric_keys = any(
        any(
            s in k
            for s in [
                '$opens',
                'unique_open',
                'email_open',
                'total_open',
                'open_rate',
            ]
        )
        for k, _ in flat
    )
    explicit_zero_opens = has_open_metric_keys and open_max <= 0 and not last_open_dt
    never_opened_any = bool(explicit_zero_opens and not opened_ever)

    score = 0
    if added_to_cart:
        score += 40
    if placed_order:
        score += 50
    if opened_last_30:
        score += 30
    if clicked_ever:
        score += 20
    if active_last_30:
        score += 25
    if subscribed_last_60:
        score += 15
    if opened_last_90:
        score += 10
    if never_opened_any:
        score -= 20
    if created_over_90 and never_opened_any:
        score -= 30

    first_name = str(attrs.get('first_name') or '').strip()
    last_name = str(attrs.get('last_name') or '').strip()
    full_name = f'{first_name} {last_name}'.strip()
    email = str(attrs.get('email') or '').strip()

    key_signals = {
        'added_to_cart_ever': added_to_cart,
        'placed_order_ever': placed_order,
        'opened_email_ever': opened_ever,
        'opened_email_last_30d': opened_last_30,
        'clicked_email_ever': clicked_ever,
        'active_on_site_last_30d': active_last_30,
        'subscribed_last_60d': subscribed_last_60,
        'opened_email_last_90d': opened_last_90,
        'never_opened_any_email': never_opened_any,
        'created_more_than_90d_ago': created_over_90,
        'last_open_at': last_open_dt.isoformat() if last_open_dt else None,
        'last_click_at': last_click_dt.isoformat() if last_click_dt else None,
        'last_active_at': last_active_dt.isoformat() if last_active_dt else None,
        'subscribed_at': subscribed_dt.isoformat() if subscribed_dt else None,
    }

    return {
        'profile_id': profile.get('id'),
        'email': email,
        'name': full_name or None,
        'score': score,
        'key_signals': key_signals
    }


def _score_breakdown(scores: list) -> dict:
    return {
        'above_80': len([s for s in scores if s > 80]),
        'above_60': len([s for s in scores if s > 60]),
        'above_40': len([s for s in scores if s > 40]),
        'above_20': len([s for s in scores if s > 20]),
        'above_0': len([s for s in scores if s > 0]),
    }


def _klaviyo_top_scored_email_set(profiles: list, top_n: int) -> set:
    """
    Lowercase emails for the top_n profiles by laundry score (deterministic tie-break on email).
    Matches ranking used by GET /api/klaviyo/hot-profiles.
    """
    if top_n <= 0 or not profiles:
        return set()
    scored = [_score_klaviyo_profile(p) for p in profiles]
    scored.sort(key=lambda x: (-(x.get('score') or 0), x.get('email') or ''))
    out = set()
    for row in scored:
        em = str(row.get('email') or '').strip().lower()
        if not em or em in out:
            continue
        out.add(em)
        if len(out) >= top_n:
            break
    return out


def _build_segment_filter_text(top_profiles: list) -> str:
    if not top_profiles:
        return (
            'No hot profiles detected. Start with a baseline segment: users who opened email in last 90 days '
            'OR clicked any email OR placed order at least once.'
        )
    n = max(1, len(top_profiles))
    sig = lambda key: len([p for p in top_profiles if p.get('key_signals', {}).get(key)]) / n
    p_order = sig('placed_order_ever')
    p_cart = sig('added_to_cart_ever')
    p_open30 = sig('opened_email_last_30d')
    p_click = sig('clicked_email_ever')
    p_active30 = sig('active_on_site_last_30d')
    p_never = sig('never_opened_any_email')

    lines = [
        f'Suggested Klaviyo segment filters to approximate the top {n} hot profiles:',
        f'1) Include people who are high-intent: Placed Order at least once ({p_order:.0%} of top {n}) OR Added to Cart at least once ({p_cart:.0%}).',
        f'2) AND who are currently engaged: Opened Email in last 30 days ({p_open30:.0%}) OR Clicked Email at least once ({p_click:.0%}) OR Active on site in last 30 days ({p_active30:.0%}).',
        f'3) Exclude very cold records: Never opened any email ({p_never:.0%}) AND profile created more than 90 days ago.',
        '4) Optional quality gate: score > 60 equivalent (approx. order/cart + at least one engagement signal).',
    ]
    return '\n'.join(lines)


def _klaviyo_resolve_keep_emails(payload_in: dict | None = None):
    payload_in = payload_in or {}
    list_id = str(payload_in.get('list_id') or '').strip() or str(KLAVIYO_ACTIVE_LIST_ID or '').strip()
    segment_id = str(payload_in.get('segment_id') or '').strip() or str(KLAVIYO_ACTIVE_SEGMENT_ID or '').strip()
    if list_id:
        return _fetch_list_keep_emails(list_id), 'list', list_id
    if segment_id:
        return _fetch_segment_keep_emails(segment_id), 'segment', segment_id
    raise ValueError(
        'Set KLAVIYO_ACTIVE_LIST_ID or KLAVIYO_ACTIVE_SEGMENT_ID, '
        'or pass list_id / segment_id in the request body.'
    )


def _submit_suppression_batches(cold_emails: list[str], dry_run: bool) -> tuple[list[str], list[str], int]:
    job_ids: list[str] = []
    errors: list[str] = []
    suppressed_submitted = 0
    if dry_run or not cold_emails:
        return job_ids, errors, suppressed_submitted
    for i in range(0, len(cold_emails), 100):
        batch = cold_emails[i:i + 100]
        body = {
            'data': {
                'type': 'profile-suppression-bulk-create-job',
                'attributes': {
                    'profiles': {
                        'data': [
                            {'type': 'profile', 'attributes': {'email': e}}
                            for e in batch
                        ]
                    }
                }
            }
        }
        r = _klaviyo_api_post_json(
            'https://a.klaviyo.com/api/profile-suppression-bulk-create-jobs/',
            body,
        )
        if r.status_code in (200, 202):
            suppressed_submitted += len(batch)
            try:
                jd = r.json()
                jid = jd.get('data', {}).get('id')
                if jid:
                    job_ids.append(jid)
            except Exception:
                pass
        else:
            errors.append(f'batch {i // 100 + 1}: HTTP {r.status_code} {r.text[:500]}')
        time.sleep(0.25)
    return job_ids, errors, suppressed_submitted


def suppress_cold_run(dry_run: bool, payload_in: dict | None = None) -> dict:
    if not KLAVIYO_PRIVATE_KEY:
        return {'ok': False, 'error': 'KLAVIYO_PRIVATE_KEY not set'}

    payload_in = dict(payload_in or {})
    sa_raw = payload_in.get('suppress_all')
    if isinstance(sa_raw, str):
        suppress_all = sa_raw.strip().lower() in ('1', 'true', 'yes', 'on')
    else:
        suppress_all = bool(sa_raw)

    leg_raw = payload_in.get('legacy_segment_cold_only')
    if isinstance(leg_raw, str):
        legacy_cold_only = leg_raw.strip().lower() in ('1', 'true', 'yes', 'on')
    else:
        legacy_cold_only = bool(leg_raw)

    forced = always_suppress_emails()

    warm_keep_only = payload_in.get('warm_keep_only')
    if warm_keep_only is None:
        warm_keep_only = os.environ.get('KLAVIYO_WARM_KEEP_ONLY', 'true').strip().lower() in (
            '1', 'true', 'yes', 'on',
        )
    elif isinstance(warm_keep_only, str):
        warm_keep_only = warm_keep_only.strip().lower() in ('1', 'true', 'yes', 'on')
    else:
        warm_keep_only = bool(warm_keep_only)

    if suppress_all:
        keep_emails = set()
        audience_type = 'suppress_all'
        audience_id = ''
    elif warm_keep_only:
        keep_emails = set()
        audience_type = 'top_warm'
        audience_id = str(KLAVIYO_HOT_TOP_N)
    else:
        keep_emails, audience_type, audience_id = _klaviyo_resolve_keep_emails(payload_in)

    use_smart = not suppress_all and not legacy_cold_only
    all_profiles = _fetch_all_klaviyo_profiles(include_predictive=use_smart)

    top_score_emails = set()
    if use_smart and KLAVIYO_HOT_TOP_N > 0:
        top_score_emails = _klaviyo_top_scored_email_set(all_profiles, KLAVIYO_HOT_TOP_N)

    cold_emails: list[str] = []
    seen_cold_email: set[str] = set()
    protected_top_score: set[str] = set()
    protected_hot_signal: set[str] = set()
    forced_suppressed: set[str] = set()

    for p in all_profiles:
        attrs = p.get('attributes', {}) if isinstance(p, dict) else {}
        em = str(attrs.get('email') or '').strip().lower()
        if not em:
            continue
        if em in forced:
            if em not in seen_cold_email:
                seen_cold_email.add(em)
                cold_emails.append(em)
                forced_suppressed.add(em)
            continue
        if suppress_all:
            if em not in seen_cold_email:
                seen_cold_email.add(em)
                cold_emails.append(em)
            continue
        if em in keep_emails:
            continue
        if use_smart and em in top_score_emails:
            protected_top_score.add(em)
            continue
        if use_smart and _klaviyo_profile_is_hot(p):
            protected_hot_signal.add(em)
            continue
        if em not in seen_cold_email:
            seen_cold_email.add(em)
            cold_emails.append(em)

    for em in forced:
        if em not in seen_cold_email:
            seen_cold_email.add(em)
            cold_emails.append(em)
            forced_suppressed.add(em)

    job_ids, errors, suppressed_submitted = _submit_suppression_batches(cold_emails, dry_run)

    return {
        'ok': True,
        'dry_run': dry_run,
        'suppress_all': suppress_all,
        'legacy_segment_cold_only': legacy_cold_only,
        'smart_cold_detection': use_smart,
        'klaviyo_hot_top_n': KLAVIYO_HOT_TOP_N,
        'hot_top_score_pool_count': len(top_score_emails),
        'protected_top_score_count': len(protected_top_score),
        'protected_hot_signal_count': len(protected_hot_signal),
        'hot_profiles_protected_count': len(protected_top_score | protected_hot_signal),
        'forced_suppress_count': len(forced_suppressed),
        'warm_keep_only': warm_keep_only,
        'audience_type': audience_type,
        'audience_id': audience_id,
        'total_profiles': len(all_profiles),
        'keep_in_audience_count': len(keep_emails),
        'cold_to_suppress_count': len(cold_emails),
        'profiles_submitted_to_suppression_jobs': suppressed_submitted if not dry_run else 0,
        'bulk_job_ids': job_ids,
        'errors': errors,
    }


def hot_profiles(top_n: int | None = None) -> dict:
    if not KLAVIYO_PRIVATE_KEY:
        return {'ok': False, 'error': 'KLAVIYO_PRIVATE_KEY not set'}
    profiles = _fetch_all_klaviyo_profiles()
    scored = [_score_klaviyo_profile(p) for p in profiles]
    scored.sort(key=lambda x: (-(x.get('score') or 0), x.get('email') or ''))
    limit = top_n if top_n is not None else (KLAVIYO_HOT_TOP_N if KLAVIYO_HOT_TOP_N > 0 else 200)
    top_profiles = scored[:limit]
    return {
        'ok': True,
        'source': 'klaviyo_v3_profiles',
        'hot_top_n': limit,
        'profiles_fetched': len(profiles),
        'profiles_scored': len(scored),
        'top_profiles': top_profiles,
        'score_breakdown': _score_breakdown([p.get('score', 0) for p in scored]),
        'segment_filters': _build_segment_filter_text(top_profiles),
    }


def active_count(
    list_id: str = '',
    segment_id: str = '',
    bypass_cache: bool = False,
) -> dict:
    if not KLAVIYO_PRIVATE_KEY:
        return {'ok': False, 'error': 'KLAVIYO_PRIVATE_KEY not set'}

    list_id = (list_id or '').strip() or str(KLAVIYO_ACTIVE_LIST_ID or '').strip()
    segment_id = (segment_id or '').strip() or str(KLAVIYO_ACTIVE_SEGMENT_ID or '').strip()
    cache_key = f'L:{list_id}' if list_id else (f'S:{segment_id}' if segment_id else '')
    now = time.time()
    cache_ttl = float(os.environ.get('KLAVIYO_ACTIVE_COUNT_CACHE_TTL', '60'))
    read_timeout = float(os.environ.get('KLAVIYO_ACTIVE_COUNT_HTTP_TIMEOUT', '12'))
    connect_timeout = float(os.environ.get('KLAVIYO_ACTIVE_COUNT_CONNECT_TIMEOUT', '5'))

    if cache_key and not bypass_cache:
        with _active_count_cache_lock:
            hit = _active_count_cache.get(cache_key)
            if hit and hit[0] > now:
                return {
                    **hit[1],
                    'cached': True,
                    'cache_ttl_remaining_sec': max(0, int(hit[0] - now)),
                }

    if list_id:
        j = _klaviyo_api_get(
            f'https://a.klaviyo.com/api/lists/{list_id}/',
            params={'additional-fields[list]': 'profile_count'},
            http_timeout=read_timeout,
            connect_timeout=connect_timeout,
            max_retries=1,
        )
        attrs = (j.get('data') or {}).get('attributes') or {}
        payload = {
            'ok': True,
            'active_profile_count': attrs.get('profile_count'),
            'source': 'list',
            'resource_id': list_id,
            'cached': False,
        }
        with _active_count_cache_lock:
            _active_count_cache[cache_key] = (now + cache_ttl, dict(payload))
        return payload

    if segment_id:
        j = _klaviyo_api_get(
            f'https://a.klaviyo.com/api/segments/{segment_id}/',
            params={'additional-fields[segment]': 'profile_count'},
            http_timeout=read_timeout,
            connect_timeout=connect_timeout,
            max_retries=1,
        )
        attrs = (j.get('data') or {}).get('attributes') or {}
        payload = {
            'ok': True,
            'active_profile_count': attrs.get('profile_count'),
            'source': 'segment',
            'resource_id': segment_id,
            'cached': False,
        }
        with _active_count_cache_lock:
            _active_count_cache[cache_key] = (now + cache_ttl, dict(payload))
        return payload

    return {
        'ok': False,
        'error': 'Pass list_id or segment_id, or set KLAVIYO_ACTIVE_LIST_ID / KLAVIYO_ACTIVE_SEGMENT_ID',
    }

