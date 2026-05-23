import json
import os
from collections import Counter
from pathlib import Path

import requests
from flask import Flask, jsonify, request
from ad_intelligence_engine import meta_roas_decision, meta_roas_execute
from automation_engine import ad_machine_tick
from creative_scan_engine import creative_scan_combo
from dashboard_engine import (
    ads_approve,
    ads_edit,
    ads_feedback,
    ads_improve_copy,
    ads_pending,
    ads_publish,
    ads_reject,
    meta_ad_live_creative,
    meta_adsets_live,
    meta_campaign_dashboard,
    meta_campaign_used_videos,
    meta_video_thumbnail,
)
from seo_engine import generate_article_endpoint, run_seo_engine, seo_job_status, seo_status
from creative_engine import creative_enhance, image_brain_v1, judge_image_candidate, repair_image_v1, repair_image_v2, repair_image_v3
from video_engine import judge_video_candidate, produce_iteration_v2, produce_video_candidate, production_brain_v1, video_output_folder, video_process, video_process_upload, video_upload_source
from meta_engine import (
    launch_ads,
    launch_carousel_ads,
    instagram_auto_post,
    instagram_auto_publish_cycle,
    instagram_post,
    post_reel_async,
    reel_publish,
    retarget_adsets,
    get_adset_targeting_preview,
    apply_hooklab_from_benchmark,
    targetingsearch_household_income,
    ads_status,
)
from facebook_engine import facebook_post, token_debug, find_accounts
from google_engine import google_drive_combos, google_drive_videos, google_pick_next_combo, google_sync_combos, google_verify
from klaviyo_engine import active_count as klaviyo_active_count, hot_profiles as klaviyo_hot_profiles, suppress_cold_run
from clarity_engine import clarity_health, clarity_insights, clarity_sweep_now

app = Flask(__name__)

@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
    return response

app.add_url_rule('/api/seo/generate', view_func=run_seo_engine, methods=['POST'])
app.add_url_rule('/generate-article', view_func=generate_article_endpoint, methods=['POST'])
app.add_url_rule('/api/seo/generate-article', view_func=generate_article_endpoint, methods=['POST'])
app.add_url_rule('/seo-job/<job_id>', view_func=seo_job_status, methods=['GET'])
app.add_url_rule('/seo-status', view_func=seo_status, methods=['GET'])
app.add_url_rule('/api/creative/enhance', view_func=creative_enhance, methods=['POST'])
app.add_url_rule('/api/creative/image-brain-v1', view_func=image_brain_v1, methods=['POST'])
app.add_url_rule('/api/creative/repair-image-v1', view_func=repair_image_v1, methods=['POST'])
app.add_url_rule('/api/creative/repair-image-v2', view_func=repair_image_v2, methods=['POST'])
app.add_url_rule('/api/creative/repair-image-v3', view_func=repair_image_v3, methods=['POST'])
app.add_url_rule('/api/creative/judge-image-candidate', view_func=judge_image_candidate, methods=['POST'])
app.add_url_rule('/api/creative/scan-combo', view_func=creative_scan_combo, methods=['POST'])
app.add_url_rule('/api/video/process', view_func=video_process, methods=['POST'])
app.add_url_rule('/api/video/upload-source', view_func=video_upload_source, methods=['POST'])
app.add_url_rule('/api/video/process-upload', view_func=video_process_upload, methods=['POST'])
app.add_url_rule('/api/video/output-folder', view_func=video_output_folder, methods=['POST'])
app.add_url_rule('/api/video/production-brain-v1', view_func=production_brain_v1, methods=['POST'])
app.add_url_rule('/api/video/produce-candidate', view_func=produce_video_candidate, methods=['POST'])
app.add_url_rule('/api/video/produce-iteration-v2', view_func=produce_iteration_v2, methods=['POST'])
app.add_url_rule('/api/video/judge-candidate', view_func=judge_video_candidate, methods=['POST'])
app.add_url_rule('/api/meta/launch-carousel', view_func=launch_carousel_ads, methods=['POST'])
app.add_url_rule('/api/meta/launch-ads', view_func=launch_ads, methods=['POST'])
app.add_url_rule('/api/meta/retarget-adsets', view_func=retarget_adsets, methods=['POST'])
app.add_url_rule('/api/meta/adset-targeting-preview', view_func=get_adset_targeting_preview, methods=['GET'])
app.add_url_rule('/api/meta/targetingsearch-household-income', view_func=targetingsearch_household_income, methods=['GET'])
app.add_url_rule('/api/meta/apply-hooklab-from-benchmark', view_func=apply_hooklab_from_benchmark, methods=['POST'])
app.add_url_rule('/api/meta/ads-status', view_func=ads_status, methods=['GET'])
app.add_url_rule('/api/meta/roas-decision', view_func=meta_roas_decision, methods=['GET', 'POST'])
app.add_url_rule('/api/meta/roas-execute', view_func=meta_roas_execute, methods=['POST'])
app.add_url_rule('/api/automation/ad-machine-tick', view_func=ad_machine_tick, methods=['POST'])
app.add_url_rule('/api/ads/pending', view_func=ads_pending, methods=['GET', 'POST'])
app.add_url_rule('/api/ads/edit/<ad_id>', view_func=ads_edit, methods=['PUT'])
app.add_url_rule('/api/ads/approve/<ad_id>', view_func=ads_approve, methods=['POST'])
app.add_url_rule('/api/ads/reject/<ad_id>', view_func=ads_reject, methods=['POST'])
app.add_url_rule('/api/ads/publish/<ad_id>', view_func=ads_publish, methods=['POST'])
app.add_url_rule('/api/ads/feedback', view_func=ads_feedback, methods=['POST'])
app.add_url_rule('/api/ads/improve-copy', view_func=ads_improve_copy, methods=['POST'])
app.add_url_rule('/api/meta/adsets-live', view_func=meta_adsets_live, methods=['GET'])
app.add_url_rule('/api/meta/campaign-dashboard', view_func=meta_campaign_dashboard, methods=['GET'])
app.add_url_rule('/api/meta/campaign-used-videos', view_func=meta_campaign_used_videos, methods=['GET'])
app.add_url_rule('/api/meta/ad-live-creative', view_func=meta_ad_live_creative, methods=['GET'])
app.add_url_rule('/api/meta/video-thumbnail', view_func=meta_video_thumbnail, methods=['GET'])
app.add_url_rule('/api/instagram/reel', view_func=post_reel_async, methods=['POST'])
app.add_url_rule('/api/instagram/post', view_func=instagram_post, methods=['POST'])
app.add_url_rule('/api/instagram/auto-post', view_func=instagram_auto_post, methods=['POST'])
app.add_url_rule('/api/instagram/auto-publish-cycle', view_func=instagram_auto_publish_cycle, methods=['POST'])
app.add_url_rule('/api/instagram/reel-publish/<creation_id>', view_func=reel_publish, methods=['POST'])
app.add_url_rule('/api/facebook/post', view_func=facebook_post, methods=['POST'])
app.add_url_rule('/api/meta/token-debug', view_func=token_debug, methods=['GET'])
app.add_url_rule('/api/meta/find-accounts', view_func=find_accounts, methods=['GET'])
app.add_url_rule('/api/google/verify', view_func=google_verify, methods=['GET'])
app.add_url_rule('/api/drive/videos', view_func=google_drive_videos, methods=['GET'])
app.add_url_rule('/api/google/drive-combos', view_func=google_drive_combos, methods=['GET'])
app.add_url_rule('/api/google/sync-combos', view_func=google_sync_combos, methods=['POST'])
app.add_url_rule('/api/google/pick-next-combo', view_func=google_pick_next_combo, methods=['POST'])

@app.route('/api/klaviyo/hot-profiles', methods=['GET'])
def klaviyo_hot_profiles_route():
    try:
        return jsonify(klaviyo_hot_profiles())
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/klaviyo/active-count', methods=['GET'])
def klaviyo_active_count_route():
    try:
        bypass = (request.args.get('bypass_cache') or '').strip().lower() in ('1', 'true', 'yes')
        return jsonify(
            klaviyo_active_count(
                list_id=request.args.get('list_id', ''),
                segment_id=request.args.get('segment_id', ''),
                bypass_cache=bypass,
            )
        )
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/klaviyo/suppress-cold-dry-run', methods=['POST'])
def klaviyo_suppress_cold_dry_run_route():
    try:
        payload = request.get_json(silent=True) or {}
        return jsonify(suppress_cold_run(dry_run=True, payload_in=payload))
    except ValueError as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/klaviyo/suppress-cold', methods=['POST'])
def klaviyo_suppress_cold_route():
    try:
        payload = request.get_json(silent=True) or {}
        return jsonify(suppress_cold_run(dry_run=False, payload_in=payload))
    except ValueError as e:
        return jsonify({'ok': False, 'error': str(e), 'reason': 'validation'}), 200
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 200

@app.route('/api/clarity/insights', methods=['GET'])
def clarity_insights_route():
    return clarity_insights()

@app.route('/api/clarity/health', methods=['GET'])
def clarity_health_route():
    return clarity_health()

@app.route('/api/clarity/sweep-now', methods=['POST'])
def clarity_sweep_now_route():
    return clarity_sweep_now()


def _chatwoot_config():
    api_token = os.environ.get('CHATWOOT_API_TOKEN')
    if not api_token:
        return None, jsonify({'error': 'CHATWOOT_API_TOKEN not set'}), 500
    account_id = os.environ.get('CHATWOOT_ACCOUNT_ID', '31')
    inbox_id = os.environ.get('CHATWOOT_INBOX_ID', '409')
    base_url = (os.environ.get('CHATWOOT_BASE_URL') or 'https://lnchat.vocallabs.ai').rstrip('/')
    headers = {'api_access_token': api_token, 'Content-Type': 'application/json'}
    return (api_token, account_id, inbox_id, base_url, headers), None, None


@app.route('/api/whatsapp/inbox', methods=['GET'])
def whatsapp_inbox_info():
    """Return WhatsApp business number from Chatwoot inbox/channel config."""
    cfg, err_resp, err_code = _chatwoot_config()
    if err_resp is not None:
        return err_resp, err_code
    _token, account_id, inbox_id, base_url, headers = cfg

    inbox_res = requests.get(
        f'{base_url}/api/v1/accounts/{account_id}/inboxes/{inbox_id}',
        headers=headers,
        timeout=30,
    )
    body = inbox_res.json() if inbox_res.content else {}
    payload = body.get('payload') if isinstance(body.get('payload'), dict) else body

    phone = (
        payload.get('phone_number')
        or (payload.get('channel') or {}).get('phone_number')
        or (payload.get('channel') or {}).get('provider_config', {}).get('phone_number')
        or (payload.get('channel') or {}).get('provider_config', {}).get('business_account_id')
    )

    return jsonify({
        'account_id': account_id,
        'inbox_id': inbox_id,
        'inbox_name': payload.get('name'),
        'channel_type': payload.get('channel_type'),
        'business_phone_number': phone,
        'channel': payload.get('channel'),
    })


@app.route('/api/whatsapp/send', methods=['POST'])
def send_whatsapp():
    data = request.get_json(silent=True) or {}
    phone = (data.get('phone') or '').replace('+', '').replace(' ', '')
    message = data.get('message') or ''
    if not phone or not message:
        return jsonify({'error': 'phone and message required'}), 400

    cfg, err_resp, err_code = _chatwoot_config()
    if err_resp is not None:
        return err_resp, err_code
    _token, account_id, inbox_id, base_url, headers = cfg

    contact_res = requests.post(
        f'{base_url}/api/v1/accounts/{account_id}/contacts',
        headers=headers,
        json={'phone_number': f'+{phone}', 'name': data.get('name', phone)},
        timeout=60,
    )
    contact_body = contact_res.json() if contact_res.content else {}
    contact_id = contact_body.get('id') or (contact_body.get('payload') or {}).get('contact', {}).get('id')
    if not contact_id:
        return jsonify({'error': 'contact creation failed', 'detail': contact_body}), 502

    conv_res = requests.post(
        f'{base_url}/api/v1/accounts/{account_id}/conversations',
        headers=headers,
        json={'inbox_id': int(inbox_id), 'contact_id': contact_id},
        timeout=60,
    )
    conv_body = conv_res.json() if conv_res.content else {}
    conv_id = conv_body.get('id')
    if not conv_id:
        return jsonify({'error': 'conversation creation failed', 'detail': conv_body}), 502

    msg_res = requests.post(
        f'{base_url}/api/v1/accounts/{account_id}/conversations/{conv_id}/messages',
        headers=headers,
        json={'content': message, 'message_type': 'outgoing', 'private': False},
        timeout=60,
    )
    msg_body = msg_res.json() if msg_res.content else {}

    if not msg_res.ok:
        return jsonify({'error': 'message send failed', 'detail': msg_body}), 502

    out = {'success': True, 'message_id': msg_body.get('id')}

    image_url = (data.get('image_url') or '').strip()
    if image_url:
        img_res = requests.get(image_url, timeout=60)
        if not img_res.ok:
            return jsonify({
                'success': True,
                'message_id': msg_body.get('id'),
                'error': 'image fetch failed',
                'image_url': image_url,
            }), 502

        img_ct = (img_res.headers.get('Content-Type') or 'image/png').split(';')[0].strip()
        img_name = 'intro.png' if 'png' in img_ct else 'intro.jpg'
        img_res_post = requests.post(
            f'{base_url}/api/v1/accounts/{account_id}/conversations/{conv_id}/messages',
            headers={'api_access_token': api_token},
            files={'attachments[]': (img_name, img_res.content, img_ct)},
            data={'message_type': 'outgoing', 'private': 'false'},
            timeout=120,
        )
        img_msg_body = img_res_post.json() if img_res_post.content else {}
        if not img_res_post.ok:
            return jsonify({
                'success': True,
                'message_id': msg_body.get('id'),
                'error': 'image attachment failed',
                'detail': img_msg_body,
            }), 502
        out['image_message_id'] = img_msg_body.get('id')

    return jsonify(out)


@app.route('/api/js-errors', methods=['POST'])
def js_errors_endpoint():
    """Receive and log JS errors from live site."""
    try:
        data = request.get_json(force=True, silent=True) or {}
        log_path = Path('/data/js_errors.jsonl')
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(data) + '\n')
        return '', 204
    except Exception:
        return '', 204


@app.route('/api/js-errors/recent', methods=['GET'])
def js_errors_recent():
    """View recent JS errors (admin only)."""
    token = request.headers.get('X-Wearth-Admin', '')
    if token != os.getenv('WEARTH_N8N_MAIL_TOKEN', ''):
        return jsonify({'error': 'unauthorized'}), 401
    log_path = Path('/data/js_errors.jsonl')
    if not log_path.exists():
        return jsonify({'errors': [], 'count': 0})
    lines = log_path.read_text(encoding='utf-8').strip().split('\n')[-200:]
    errors = [json.loads(l) for l in lines if l.strip()]
    summary = Counter()
    for e in errors:
        ua = e.get('ua', '')
        family = 'Instagram' if 'Instagram' in ua else \
                 'Facebook' if 'FBAN' in ua or 'FBAV' in ua else \
                 'Chrome' if 'Chrome' in ua else \
                 'Safari' if 'Safari' in ua else 'Other'
        summary[(e.get('msg', '')[:80], family)] += 1
    return jsonify({
        'count': len(errors),
        'summary': [{'msg': k[0], 'browser': k[1], 'hits': v}
                    for k, v in summary.most_common(30)],
        'recent': errors[-10:]
    })


@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'service': 'wearth-studio'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
