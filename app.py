import os
from flask import Flask, jsonify
from ad_intelligence_engine import meta_roas_decision, meta_roas_execute
from creative_scan_engine import creative_scan_combo
from seo_engine import run_seo_engine
from creative_engine import creative_enhance, image_brain_v1, judge_image_candidate, repair_image_v1
from video_engine import judge_video_candidate, produce_iteration_v2, produce_video_candidate, production_brain_v1, video_output_folder, video_process
from meta_engine import (
    launch_ads,
    launch_carousel_ads,
    post_reel_async,
    reel_publish,
    retarget_adsets,
    get_adset_targeting_preview,
    apply_hooklab_from_benchmark,
    targetingsearch_household_income,
    ads_status,
)
from facebook_engine import facebook_post, token_debug, find_accounts
from google_engine import google_drive_combos, google_pick_next_combo, google_sync_combos, google_verify

app = Flask(__name__)

app.add_url_rule('/api/seo/generate', view_func=run_seo_engine, methods=['POST'])
app.add_url_rule('/api/creative/enhance', view_func=creative_enhance, methods=['POST'])
app.add_url_rule('/api/creative/image-brain-v1', view_func=image_brain_v1, methods=['POST'])
app.add_url_rule('/api/creative/repair-image-v1', view_func=repair_image_v1, methods=['POST'])
app.add_url_rule('/api/creative/judge-image-candidate', view_func=judge_image_candidate, methods=['POST'])
app.add_url_rule('/api/creative/scan-combo', view_func=creative_scan_combo, methods=['POST'])
app.add_url_rule('/api/video/process', view_func=video_process, methods=['POST'])
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
app.add_url_rule('/api/instagram/reel', view_func=post_reel_async, methods=['POST'])
app.add_url_rule('/api/instagram/reel-publish/<creation_id>', view_func=reel_publish, methods=['POST'])
app.add_url_rule('/api/facebook/post', view_func=facebook_post, methods=['POST'])
app.add_url_rule('/api/meta/token-debug', view_func=token_debug, methods=['GET'])
app.add_url_rule('/api/meta/find-accounts', view_func=find_accounts, methods=['GET'])
app.add_url_rule('/api/google/verify', view_func=google_verify, methods=['GET'])
app.add_url_rule('/api/google/drive-combos', view_func=google_drive_combos, methods=['GET'])
app.add_url_rule('/api/google/sync-combos', view_func=google_sync_combos, methods=['POST'])
app.add_url_rule('/api/google/pick-next-combo', view_func=google_pick_next_combo, methods=['POST'])

@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'service': 'wearth-studio'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
