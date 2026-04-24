from flask import Flask, send_file, request, jsonify
import os
import requests
import json
import time
import base64
import traceback

app = Flask(__name__)

COMPOSITOR_URL = 'https://web-production-48b5f.up.railway.app/compose'
ANTHROPIC_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
FAL_API_KEY = os.environ.get('FAL_API_KEY', 'c9d35e47-26a0-4a74-b24b-4075ecc4b1c0:cf04ed86e9925a8d27fc7f93b7cb7c19')
IMGBB_API_KEY = os.environ.get('IMGBB_API_KEY', 'e1b80ca6ca87d1afe6a114b80e21cbe3')

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


@app.route('/api/tryon', methods=['POST'])
def tryon():
    """
    Virtual try-on using FASHN v1.6 on FAL.
    Expects JSON: { garment_b64, garment_category, mood }
    Returns: { image_url, model_url }
    """
    try:
        data = request.json
        garment_b64 = data.get('garment_b64', '')
        category = data.get('garment_category', 'tops')
        mood = data.get('mood', 'editorial activewear, natural light')

        if not garment_b64:
            return jsonify({'error': 'garment_b64 required'}), 400

        # Step 1: Upload garment to imgbb
        upload_resp = requests.post(
            'https://api.imgbb.com/1/upload',
            data={'key': IMGBB_API_KEY, 'image': garment_b64},
            timeout=30
        )
        upload_resp.raise_for_status()
        garment_url = upload_resp.json()['data']['url']

        # Step 2: Generate model image with FAL Flux
        model_prompt = (
            f"professional fashion model, full body, standing pose, {mood}, "
            "neutral expression, studio lighting, clean minimal background, "
            "wearing plain fitted athletic wear, no logos, high quality photo"
        )
        flux_resp = requests.post(
            'https://fal.run/fal-ai/flux/dev',
            headers={
                'Authorization': f'Key {FAL_API_KEY}',
                'Content-Type': 'application/json'
            },
            json={
                'prompt': model_prompt,
                'image_size': 'portrait_4_3',
                'num_inference_steps': 28,
                'guidance_scale': 3.5,
                'num_images': 1
            },
            timeout=60
        )
        flux_data = flux_resp.json()
        model_url = flux_data.get('images', [{}])[0].get('url', '')

        if not model_url:
            return jsonify({'error': 'Failed to generate model image', 'raw': flux_data}), 500

        # Step 3: Submit FASHN try-on job
        fal_headers = {
            'Authorization': f'Key {FAL_API_KEY}',
            'Content-Type': 'application/json'
        }

        submit_resp = requests.post(
            'https://queue.fal.run/fal-ai/fashn/tryon/v1.6',
            headers=fal_headers,
            json={
                'input': {
                    'model_image': model_url,
                    'garment_image': garment_url,
                    'category': category,
                    'flat_lay': False
                }
            },
            timeout=30
        )
        submit_resp.raise_for_status()
        request_id = submit_resp.json()['request_id']

        # Step 4: Poll for result (max 90s)
        for _ in range(30):
            time.sleep(3)
            status_resp = requests.get(
                f'https://queue.fal.run/fal-ai/fashn/tryon/v1.6/requests/{request_id}/status',
                headers=fal_headers,
                timeout=15
            )
            status = status_resp.json().get('status', '')

            if status == 'COMPLETED':
                result_resp = requests.get(
                    f'https://queue.fal.run/fal-ai/fashn/tryon/v1.6/requests/{request_id}',
                    headers=fal_headers,
                    timeout=15
                )
                result = result_resp.json()
                images = result.get('images', [])
                if not images:
                    images = result.get('output', {}).get('images', [])
                if images:
                    img_url = images[0].get('url') if isinstance(images[0], dict) else images[0]
                    return jsonify({'image_url': img_url, 'model_url': model_url})
                return jsonify({'error': 'No images in result', 'raw': result}), 500

            elif status in ('FAILED', 'ERROR'):
                return jsonify({'error': f'Try-on failed: {status}', 'raw': status_resp.json()}), 500

        return jsonify({'error': 'Try-on timed out after 90 seconds'}), 500

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
