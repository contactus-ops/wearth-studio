from flask import Flask, send_file, request, jsonify
import os
import requests
import base64
import json

app = Flask(__name__)

IMGBB_KEY = 'e1b80ca6ca87d1afe6a114b80e21cbe3'
COMPOSITOR_URL = 'https://web-production-48b5f.up.railway.app/compose'

WEARTH_PROMPT = """You are writing Instagram content for WEARTH — Indian activewear made from plant-based eucalyptus. Founded by Shai in India.

The WEARTH tribe: wakes up early because they want to. reads ingredient labels without being asked. switched to natural products quietly, no announcement. moves because it feels good, not for content. done with synthetic, done with fast, done with things that look good but feel wrong.

Mood today: {mood}

Generate ONE Instagram post.

HEADLINE (goes on the image):
- Maximum 6 words
- All lowercase
- Ends with a period
- Pure feeling or truth — no product mentions
- Examples: 'your skin breathes differently here.' / 'soft. breathable. from trees.' / 'made to move with you.'

TAGLINE (sits below headline on image):
- 2-4 words only
- Format exactly: [words] · wearth
- Examples: 'move greener · wearth' / 'plant-based · wearth' / 'eucalyptus · wearth'
- Never use TENCEL or lyocell

CAPTION (Instagram post text):
- 100-150 words
- Real person thinking out loud — not a brand, not a copywriter, not an AI
- Short sentences. Uneven rhythm.
- No em dashes, no rhetorical questions
- No words: sacred, ritual, intentional, conscious, shift, journey
- No tricolon patterns, no exclamation marks
- Weave in eucalyptus fabric truth naturally
- End with: #WearthActive #PlantBasedActivewear #IndianActivewear #NoPolyester #EucalyptusActivewear #MoveWithIntention #ActivewearIndia #WorthTheSwitch

CRITICAL: Return ONLY valid JSON. Start with { and end with }.
{"headline": "your headline here", "tagline": "your tagline here", "caption": "your full caption here"}"""


@app.route('/')
def index():
    return send_file('index.html')


@app.route('/manifest.json')
def manifest():
    return send_file('manifest.json')


@app.route('/sw.js')
def sw():
    return send_file('sw.js')


@app.route('/api/generate', methods=['POST'])
def generate():
    try:
        data = request.json
        mood = data.get('mood', '')
        image_url = data.get('image_url', '')

        # Step 1: Generate headline, tagline, caption from Claude
        resp = requests.post(
            'https://api.anthropic.com/v1/messages',
            headers={
                'Content-Type': 'application/json',
                'x-api-key': os.environ.get('ANTHROPIC_API_KEY', ''),
                'anthropic-version': '2023-06-01'
            },
            json={
                'model': 'claude-sonnet-4-20250514',
                'max_tokens': 1500,
                'messages': [{'role': 'user', 'content': WEARTH_PROMPT.format(mood=mood)}]
            },
            timeout=30
        )
        raw = resp.json()['content'][0]['text']
        cleaned = raw.replace('```json', '').replace('```', '').strip()
        parsed = json.loads(cleaned)

        # Step 2: Send to Railway compositor
        comp_resp = requests.post(
            COMPOSITOR_URL,
            json={
                'photo_url': image_url,
                'main_text': parsed['headline'],
                'sub_text': parsed['tagline'],
                'logo_base64': ''
            },
            timeout=60
        )
        comp_data = comp_resp.json()
        stable_url = comp_data.get('url', image_url)

        return jsonify({
            'image_url': stable_url,
            'headline': parsed['headline'],
            'tagline': parsed['tagline'],
            'caption': parsed['caption']
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/<path:path>')
def static_files(path):
    try:
        return send_file(path)
    except Exception:
        return '', 404


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
