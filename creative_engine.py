import os, io, base64, json, requests, anthropic
from PIL import Image, ImageEnhance, ImageDraw, ImageStat
from flask import request, jsonify

ANTHROPIC_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
ANTHROPIC_MODEL = os.environ.get('ANTHROPIC_MODEL', 'claude-sonnet-4-20250514')
META_IMAGE_MAX_MB = 30
MIN_PREMIUM_DIM = 1080

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

def _drive_image_meta_and_bytes(file_id):
    from google_engine import _google_services
    from googleapiclient.http import MediaIoBaseDownload

    _info, _sheets, drive = _google_services()
    meta = drive.files().get(
        fileId=file_id,
        fields='id,name,mimeType,size,webViewLink',
        supportsAllDrives=True,
    ).execute()
    fh = io.BytesIO()
    req = drive.files().get_media(fileId=file_id, supportsAllDrives=True)
    downloader = MediaIoBaseDownload(fh, req)
    done = False
    while not done:
        _status, done = downloader.next_chunk()
    return meta, fh.getvalue()

def _image_brain_metrics(image_bytes, meta):
    img = Image.open(io.BytesIO(image_bytes)).convert('RGB')
    w, h = img.size
    thumb = img.resize((64, 64))
    stat = ImageStat.Stat(thumb)
    brightness = round(sum(stat.mean) / 3, 2)
    contrast = round(sum(stat.stddev) / 3, 2)
    mime = (meta.get('mimeType') or '').lower()
    size_mb = round(len(image_bytes) / (1024 * 1024), 2)
    issues = []
    if size_mb > META_IMAGE_MAX_MB:
        issues.append('image_file_over_30mb')
    if min(w, h) < MIN_PREMIUM_DIM:
        issues.append('image_under_1080_short_side')
    if not any(x in mime for x in ('jpeg', 'jpg', 'png')):
        issues.append('non_meta_preferred_image_format')
    if brightness < 80:
        issues.append('too_dark_for_mobile_feed')
    if contrast < 35:
        issues.append('low_subject_separation')
    return {
        'file_name': meta.get('name'),
        'mime_type': meta.get('mimeType'),
        'size_mb': size_mb,
        'width': w,
        'height': h,
        'brightness': brightness,
        'contrast': contrast,
        'aspect_ratio': round(w / h, 3) if h else None,
        'meta_compliance': {
            'file_size_ok': size_mb <= META_IMAGE_MAX_MB,
            'format_ok': any(x in mime for x in ('jpeg', 'jpg', 'png')),
            'premium_resolution_ok': min(w, h) >= MIN_PREMIUM_DIM,
        },
        'detected_issues': issues,
    }

def _image_thumb_b64(image_bytes):
    img = Image.open(io.BytesIO(image_bytes)).convert('RGB')
    img.thumbnail((1400, 1400))
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=84)
    return base64.b64encode(buf.getvalue()).decode()

def _heuristic_image_brain(metrics, note=''):
    issues = metrics.get('detected_issues') or []
    needs_overlay = True
    quality_actions = []
    if 'too_dark_for_mobile_feed' in issues:
        quality_actions.append('lift_exposure_selectively')
    if 'low_subject_separation' in issues:
        quality_actions.append('increase_contrast_and_subject_separation')
    if metrics.get('meta_compliance', {}).get('premium_resolution_ok') is False:
        quality_actions.append('upscale_or_choose_higher_resolution_source')
    if not quality_actions:
        quality_actions.append('apply_light_premium_grade')
    return {
        'ok': True,
        'model': 'heuristic',
        'launch_readiness': 'repair_then_judge',
        'image_score_0_10': 6.5,
        'luxury_fit_0_10': 6.5,
        'mobile_hook_0_10': 6.0,
        'text_plan': {
            'has_existing_text': 'unknown',
            'text_readability': 'unknown',
            'needs_hook_overlay': needs_overlay,
            'hook_overlay': 'I did everything right except this.',
            'safe_zone': 'bottom-left or top-left with product/face preserved',
        },
        'quality_plan': {
            'actions_to_apply_now': quality_actions,
            'meta_compatible_after_repair': not any(x in issues for x in ('image_file_over_30mb', 'non_meta_preferred_image_format')),
        },
        'background_plan': {
            'mode': 'keep_or_subtle_cleanup',
            'risk_of_artificiality': 'medium',
            'acceptable_directions': [
                'Bandra tree-lined street',
                'warm Bandra or SoBo cafe',
                'minimal Mumbai balcony with plants and high-rises',
                'quiet Pilates or yoga studio',
                'premium living room with linen, plants, books, warm lamp',
            ],
            'rule': 'Avoid full replacement unless lighting and subject mask are natural.',
        },
        'caption_plan': {
            'primary_text': 'Your skin knows the difference.',
            'headline': 'A softer standard.',
            'cta': 'Shop now',
        },
        'repair_decision': {
            'repairable': True,
            'requires_external_ai_tool': ['optional_background_cleanup_or_replace'] if issues else [],
            'reshoot_required': False,
        },
        'risks': issues + ([note] if note else []),
    }

def _claude_image_brain(image_b64, metrics):
    if not ANTHROPIC_KEY:
        return _heuristic_image_brain(metrics, 'ANTHROPIC_API_KEY missing')
    prompt = {
        'task': 'You are WEARTH Active image production brain v1. Diagnose this founder-supplied image and produce a last-mile Meta ad repair plan.',
        'brand': 'WEARTH Active: premium lyocell / plant-based activewear for Indian women. Quiet luxury, skin comfort, fabric science, accessible premium, not discount.',
        'rules': [
            'Do not reject too early; first decide whether the image is repairable.',
            'If no strong readable text exists, recommend a short hook overlay.',
            'Preserve founder authenticity, but remove low-trust or cheap cues.',
            'Background upgrades must be subtle and lighting-consistent. Fake luxury is worse than simple honesty.',
            'Prefer Indian premium cues: Bandra/SoBo cafe, tree-lined Mumbai street, balcony with plants/high-rises, quiet studio, warm living room.',
            'Respect Meta image compatibility and mobile readability.',
        ],
        'metrics': metrics,
        'required_json_schema': {
            'launch_readiness': 'launch_as_is|repair_then_judge|reshoot_required',
            'image_score_0_10': 'number',
            'luxury_fit_0_10': 'number',
            'mobile_hook_0_10': 'number',
            'text_plan': {
                'has_existing_text': 'boolean',
                'text_readability': 'high|medium|low|none',
                'needs_hook_overlay': 'boolean',
                'hook_overlay': 'short hook or empty string',
                'safe_zone': 'where to place overlay',
            },
            'quality_plan': {
                'actions_to_apply_now': ['crop/grade/contrast/upscale/compress actions'],
                'meta_compatible_after_repair': 'boolean',
            },
            'background_plan': {
                'mode': 'keep|subtle_cleanup|subtle_replace|reshoot',
                'risk_of_artificiality': 'low|medium|high',
                'recommended_background_direction': 'string',
                'rule': 'short note',
            },
            'caption_plan': {
                'primary_text': 'short Meta primary text',
                'headline': 'short headline',
                'cta': 'Shop now or similar',
            },
            'repair_decision': {
                'repairable': 'boolean',
                'requires_external_ai_tool': ['string'],
                'reshoot_required': 'boolean',
            },
            'risks': ['string'],
            'reasoning': 'short paragraph',
        },
    }
    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
        resp = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=1400,
            temperature=0.15,
            messages=[{
                'role': 'user',
                'content': [
                    {'type': 'text', 'text': json.dumps(prompt, ensure_ascii=True)},
                    {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/jpeg', 'data': image_b64}},
                ],
            }],
        )
        text = (resp.content[0].text or '').strip()
        if text.startswith('```'):
            text = text.replace('```json', '').replace('```', '').strip()
        parsed = json.loads(text)
        parsed['ok'] = True
        parsed['model'] = ANTHROPIC_MODEL
        return parsed
    except Exception as e:
        return _heuristic_image_brain(metrics, f'anthropic_failed: {e}')

def image_brain_v1():
    data = request.get_json(force=True, silent=True) or {}
    file_id = (data.get('image_file_id') or data.get('file_id') or '').strip()
    if not file_id:
        return jsonify({'ok': False, 'error': 'image_file_id or file_id required'}), 400
    try:
        meta, image_bytes = _drive_image_meta_and_bytes(file_id)
        metrics = _image_brain_metrics(image_bytes, meta)
        brain = _claude_image_brain(_image_thumb_b64(image_bytes), metrics)
        return jsonify({
            'ok': True,
            'source': {
                'file_id': file_id,
                'name': meta.get('name'),
                'webViewLink': meta.get('webViewLink'),
                **metrics,
            },
            'image_brain': brain,
            'next_step': 'image_repair_executor_then_parent_judge' if brain.get('launch_readiness') != 'launch_as_is' else 'parent_image_judge_or_launch_gate',
        })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

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
