from flask import Flask, send_file, request, jsonify
import os
import requests
import json
import traceback

app = Flask(__name__)

COMPOSITOR_URL = 'https://web-production-48b5f.up.railway.app/compose'
ANTHROPIC_KEY = os.environ.get('ANTHROPIC_API_KEY', '')

WEARTH_PROMPT = (
    "You are writing Instagram content for WEARTH — Indian activewear made from plant-based eucalyptus. Founded by Shai in India.\n\n"
    "The WEARTH tribe: wakes up early because they want to. reads ingredient labels without being asked. "
    "switched to natural products quietly, no announcement. moves because it feels good, not for content. "
    "done with synthetic, done with fast, done with things that look good but feel wrong.\n\n"
    "Mood today: MOOD_PLACEHOLDER\n\n"
    "Generate ONE Instagram post with the following parts.\n\n"
    "HEADLINE (goes on the image):\n"
    "- Maximum 6 words, all lowercase, ends with a period\n"
    "- Pure feeling or truth, no product mentions\n"
    "- Examples: your skin breathes differently here. / made to move with you.\n\n"
    "TAGLINE (sits below headline on image):\n"
    "- 2-4 words only, format: words dot wearth like: plant-based · wearth\n"
    "- Never use TENCEL or lyocell\n\n"
    "THREE CAPTIONS (Instagram post text options for Shai to choose from):\n"
    "- Each 100-150 words\n"
    "- Real person thinking out loud, not a brand, not a copywriter, not AI\n"
    "- Short sentences. Uneven rhythm. Like texting a friend who gets it.\n"
    "- No em dashes, no rhetorical questions, no exclamation marks\n"
    "- No words: sacred, ritual, intentional, conscious, shift, journey, game-changer\n"
    "- No tricolon patterns like word. word. word.\n"
    "- Weave in eucalyptus fabric truth naturally, never as a lecture\n"
    "- Each must end with: #WearthActive #PlantBasedActivewear #IndianActivewear #NoPolyester #EucalyptusActivewear #MoveWithIntention #ActivewearIndia #WorthTheSwitch\n\n"
    "Return ONLY a JSON object. No markdown. No code fences. No explanation.\n"
    "Start with { and end with }.\n"
    "Use exactly these keys: headline, tagline, captions (array of 3 strings).\n"
    "Example structure: {\"headline\": \"...\", \"tagline\": \"...\", \"captions\": [\"caption1\", \"caption2\", \"caption3\"]}"
)


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

        prompt = WEARTH_PROMPT.replace('MOOD_PLACEHOLDER', mood)

        claude_resp = requests.post(
            'https://api.anthropic.com/v1/messages',
            headers={
                'Content-Type': 'application/json',
                'x-api-key': ANTHROPIC_KEY,
                'anthropic-version': '2023-06-01'
            },
            json={
                'model': 'claude-sonnet-4-20250514',
                'max_tokens': 2000,
                'messages': [{'role': 'user', 'content': prompt}]
            },
            timeout=40
        )

        claude_data = claude_resp.json()
        raw_text = claude_data['content'][0]['text'].strip()

        if '```' in raw_text:
            parts = raw_text.split('```')
            raw_text = parts[1] if len(parts) > 1 else parts[0]
            if raw_text.startswith('json'):
                raw_text = raw_text[4:]
            raw_text = raw_text.strip()

        parsed = json.loads(raw_text)
        headline = parsed.get('headline', 'move with intention.')
        tagline = parsed.get('tagline', 'plant-based · wearth')
        captions = parsed.get('captions', [parsed.get('caption', '')])
        if not isinstance(captions, list):
            captions = [captions]

        comp_resp = requests.post(
            COMPOSITOR_URL,
            json={
                'photo_url': image_url,
                'main_text': headline,
                'sub_text': tagline,
                'logo_base64': ''
            },
            timeout=60
        )

        comp_data = comp_resp.json()
        stable_url = comp_data.get('url', image_url)

        return jsonify({
            'image_url': stable_url,
            'headline': headline,
            'tagline': tagline,
            'captions': captions
        })

    except Exception as e:
        return jsonify({
            'error': str(e),
            'trace': traceback.format_exc()
        }), 500


@app.route('/<path:path>')
def static_files(path):
    try:
        return send_file(path)
    except Exception:
        return '', 404


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
