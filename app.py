from flask import Flask, send_file, request, jsonify
import os
import requests

app = Flask(__name__)

WEARTH_PROMPT = """You are writing Instagram captions for WEARTH — Indian activewear made from plant-based eucalyptus. Founded by Shai in India.

The WEARTH tribe: wakes up early because they want to. reads ingredient labels without being asked. switched to natural products quietly, no announcement. moves because it feels good, not for content. done with synthetic, done with fast, done with things that look good but feel wrong.

Mood today: {mood}

Write 3 different captions. Each 100-150 words. Rules:
- Real person thinking out loud — not a brand, not a copywriter, not an AI
- Short sentences. Uneven rhythm. Like someone texting a friend who gets it.
- Specific and grounded. Real sensations. Real moments.
- No em dashes used for dramatic effect
- No rhetorical questions
- No words: sacred, ritual, intentional, conscious, frequency, shift, journey, game-changer
- No tricolon rhythm patterns (word. word. word.) — dead giveaway
- No exclamation marks ever
- No sentences starting with There's a or It's not
- Weave in eucalyptus fabric truth naturally — not as a lecture
- End with one blank line then exactly: #WearthActive #PlantBasedActivewear #IndianActivewear #NoPolyester #EucalyptusActivewear #MoveWithIntention #ActivewearIndia #WorthTheSwitch

Return ONLY a valid JSON array of 3 strings. No markdown. No explanation. Start with ["""


@app.route('/')
def index():
    return send_file('index.html')


@app.route('/manifest.json')
def manifest():
    return send_file('manifest.json')


@app.route('/sw.js')
def sw():
    return send_file('sw.js')


IMGBB_KEY = 'e1b80ca6ca87d1afe6a114b80e21cbe3'

@app.route('/api/upload-image', methods=['POST'])
def upload_image():
    try:
        data = request.json
        image_url = data.get('image_url')
        r = requests.get(image_url, timeout=30)
        import base64
        b64 = base64.b64encode(r.content).decode('utf-8')
        resp = requests.post(
            'https://api.imgbb.com/1/upload',
            data={'key': IMGBB_KEY, 'image': b64}
        )
        result = resp.json()
        all_urls = {
            'url': result['data'].get('url'),
            'display_url': result['data'].get('display_url'),
            'image_url': result['data'].get('image', {}).get('url'),
            'thumb_url': result['data'].get('thumb', {}).get('url'),
        }
        return jsonify({'url': result['data'].get('image', {}).get('url'), 'debug': all_urls})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/captions', methods=['POST'])
def captions():
    try:
        data = request.json
        mood = data.get('mood', '')

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
                'messages': [{
                    'role': 'user',
                    'content': WEARTH_PROMPT.format(mood=mood)
                }]
            },
            timeout=30
        )
        return jsonify(resp.json())
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
