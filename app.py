import os
from flask import Flask, jsonify
from seo_engine import run_seo_engine
from creative_engine import creative_enhance
from video_engine import video_process
from meta_engine import (
    launch_ads,
    launch_carousel_ads,
    post_reel_async,
    reel_publish,
    retarget_adsets,
    get_adset_targeting_preview,
    apply_hooklab_from_benchmark,
    ads_status,
)
from facebook_engine import facebook_post, token_debug, find_accounts

app = Flask(__name__)

app.add_url_rule('/api/seo/generate', view_func=run_seo_engine, methods=['POST'])
app.add_url_rule('/api/creative/enhance', view_func=creative_enhance, methods=['POST'])
app.add_url_rule('/api/video/process', view_func=video_process, methods=['POST'])
app.add_url_rule('/api/meta/launch-carousel', view_func=launch_carousel_ads, methods=['POST'])
app.add_url_rule('/api/meta/launch-ads', view_func=launch_ads, methods=['POST'])
app.add_url_rule('/api/meta/retarget-adsets', view_func=retarget_adsets, methods=['POST'])
app.add_url_rule('/api/meta/adset-targeting-preview', view_func=get_adset_targeting_preview, methods=['GET'])
app.add_url_rule('/api/meta/apply-hooklab-from-benchmark', view_func=apply_hooklab_from_benchmark, methods=['POST'])
app.add_url_rule('/api/meta/ads-status', view_func=ads_status, methods=['GET'])
app.add_url_rule('/api/instagram/reel', view_func=post_reel_async, methods=['POST'])
app.add_url_rule('/api/instagram/reel-publish/<creation_id>', view_func=reel_publish, methods=['POST'])
app.add_url_rule('/api/facebook/post', view_func=facebook_post, methods=['POST'])
app.add_url_rule('/api/meta/token-debug', view_func=token_debug, methods=['GET'])
app.add_url_rule('/api/meta/find-accounts', view_func=find_accounts, methods=['GET'])

@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'service': 'wearth-studio'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
