import os
from flask import Flask
from seo_engine import generate_and_publish_article
from creative_engine import enhance_image
from video_engine import process_video
from meta_engine import launch_ads, post_reel_async, reel_publish, token_debug
from facebook_engine import facebook_post, find_accounts

app = Flask(__name__)

# SEO
app.add_url_rule("/api/seo/generate", view_func=generate_and_publish_article, methods=["POST"])

# Creative (image enhancement)
app.add_url_rule("/api/creative/enhance", view_func=enhance_image, methods=["POST"])

# Video (FFmpeg + Whisper captions)
app.add_url_rule("/api/video/process", view_func=process_video, methods=["POST"])

# Meta Ads
app.add_url_rule("/api/meta/launch-ads", view_func=launch_ads, methods=["POST"])

# Instagram Reels (async: create container, then publish separately)
app.add_url_rule("/api/instagram/reel", view_func=post_reel_async, methods=["POST"])
app.add_url_rule("/api/instagram/reel-publish/<creation_id>", view_func=reel_publish, methods=["POST"])

# Facebook page
app.add_url_rule("/api/facebook/post", view_func=facebook_post, methods=["POST"])

# Meta diagnostics
app.add_url_rule("/api/meta/token-debug", view_func=token_debug, methods=["GET"])
app.add_url_rule("/api/meta/find-accounts", view_func=find_accounts, methods=["GET"])

@app.route("/health")
def health():
    from flask import jsonify
    return jsonify({"status": "ok", "service": "wearth-studio"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
