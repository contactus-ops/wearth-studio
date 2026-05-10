import os, io, base64, requests, anthropic
from PIL import Image, ImageEnhance, ImageDraw
from flask import request, jsonify

ANTHROPIC_KEY = os.environ.get('ANTHROPIC_API_KEY', '')

WEARTH_CAPTIONS = [
    'you will never go back to polyester.',
    'fabric grown, not made.',
    'the women who know, dont go back.',
    'worn by women who stopped settling.',
    'plant-based. closed-loop. yours.',
    'this is what happens when you stop wearing polyester.',
    'not performance wear. presence wear.',
]

CLAUDE_PROMPT = (
    'You are a luxury activewear ad creative director for WEARTH Active '
    '(premium plant-based Indian activewear). Analyse this image and respond '
    'ONLY with valid JSON (no markdown): '
    '{"crop": "top or center or bottom", "caption_idx": 0, "brightness": 1.15, "warmth": true, "reasoning": "one line"}. '
    'crop: which third of the image is most compelling for a Meta ad. '
    'caption_idx: 0-6, pick the caption that best matches the mood. '
    'brightness: 1.0 to 1.3. warmth: true to add earthy warm tone.'
)

def _download_drive_image(file_id):
    url = 'https://drive.google.com/uc?export=download&id=' + file_id
    r = requests.get(url, timeout=30, allow_redirects=True)
    if r.status_code != 200:
        return None
    return Image.open(io.BytesIO(r.content)).convert('RGB')

def _claude_analyse(img_b64):
    if not ANTHROPIC_KEY:
        return {'crop': 'center', 'caption_idx': 0, 'brightness': 1.15, 'warmth': True}
    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
        resp = client.messages.create(
            model='claude-opus-4-5',
            max_tokens=300,
            messages=[{
                'role': 'user',
                'content': [
                    {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/jpeg', 'data': img_b64}},
                    {'type': 'text', 'text': CLAUDE_PROMPT}
                ]
            }]
        )
        import json
        text = resp.content[0].text.strip()
        if text.startswith('```'):
            text = text.split('```')[1]
            if text.startswith('json'):
                text = text[4:]
        return json.loads(text.strip())
    except Exception as e:
        return {'crop': 'center', 'caption_idx': 0, 'brightness': 1.15, 'warmth': True, 'error': str(e)}

def _apply_dopamine_lift(img, analysis):
    w, h = img.size
    # Crop to 4:5 ratio (Meta optimal format)
    target_h = int(w * 1.25)
    if target_h > h:
        target_h = h
    crop_pos = analysis.get('crop', 'center')
    if crop_pos == 'top':
        top = 0
    elif crop_pos == 'bottom':
        top = max(0, h - target_h)
    else:
        top = max(0, (h - target_h) // 2)
    img = img.crop((0, top, w, top + target_h))
    # Brightness
    brightness = float(analysis.get('brightness', 1.15))
    img = ImageEnhance.Brightness(img).enhance(brightness)
    # Contrast
    img = ImageEnhance.Contrast(img).enhance(1.1)
    # Warmth — earthy WEARTH tone
    if analysis.get('warmth', True):
        r_ch, g_ch, b_ch = img.split()
        r_ch = ImageEnhance.Brightness(r_ch).enhance(1.08)
        g_ch = ImageEnhance.Brightness(g_ch).enhance(1.03)
        img = Image.merge('RGB', (r_ch, g_ch, b_ch))
    # Subtle dark vignette for luxury feel
    vignette = Image.new('RGB', img.size, (20, 18, 16))
    mask = Image.new('L', img.size, 255)
    draw = ImageDraw.Draw(mask)
    cx, cy = img.width // 2, img.height // 2
    for i in range(min(cx, cy)):
        alpha = int(255 * (i / min(cx, cy)) ** 1.5)
        draw.ellipse([cx-i, cy-i, cx+i, cy+i], fill=alpha)
    img = Image.composite(img, vignette, mask)
    return img

def _add_caption(img, caption):
    draw = ImageDraw.Draw(img)
    w, h = img.size
    # WEARTH wordmark top left — small, letterspace feel
    draw.text((36, 32), 'W E A R T H', fill=(250, 248, 244))
    # Caption bottom left — wrap at 26 chars
    margin = 36
    words = caption.split()
    lines_out = []
    line = ''
    for word in words:
        test = (line + ' ' + word).strip()
        if len(test) > 26:
            if line:
                lines_out.append(line)
            line = word
        else:
            line = test
    if line:
        lines_out.append(line)
    line_h = 28
    y = h - margin - (len(lines_out) * line_h) - 8
    for ln in lines_out:
        # Shadow
        draw.text((margin + 1, y + 1), ln, fill=(0, 0, 0))
        # Text
        draw.text((margin, y), ln, fill=(250, 248, 244))
        y += line_h
    return img

def creative_enhance():
    data = request.get_json(force=True, silent=True) or {}
    file_id = (data.get('file_id') or '').strip()
    caption_override = (data.get('caption') or '').strip()
    if not file_id:
        return jsonify({'error': 'file_id required'}), 400
    img = _download_drive_image(file_id)
    if img is None:
        return jsonify({'error': 'could not download image from Drive'}), 400
    # Resize for Claude (max 1568px long edge)
    buf = io.BytesIO()
    thumb = img.copy()
    thumb.thumbnail((1568, 1568))
    thumb.save(buf, format='JPEG', quality=80)
    img_b64 = base64.b64encode(buf.getvalue()).decode()
    analysis = _claude_analyse(img_b64)
    img = _apply_dopamine_lift(img, analysis)
    caption = caption_override or WEARTH_CAPTIONS[int(analysis.get('caption_idx', 0)) % len(WEARTH_CAPTIONS)]
    img = _add_caption(img, caption)
    out_buf = io.BytesIO()
    img.save(out_buf, format='JPEG', quality=92)
    out_b64 = base64.b64encode(out_buf.getvalue()).decode()
    return jsonify({
        'ok': True,
        'caption': caption,
        'analysis': analysis,
        'image_b64': out_b64,
        'format': 'jpeg',
        'dimensions': list(img.size)
    })
