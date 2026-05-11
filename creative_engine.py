import os, io, base64, json, tempfile, requests, anthropic
from PIL import Image, ImageEnhance, ImageDraw, ImageFilter, ImageFont, ImageOps, ImageStat
from flask import request, jsonify

ANTHROPIC_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
ANTHROPIC_MODEL = os.environ.get('ANTHROPIC_MODEL', 'claude-sonnet-4-20250514')
META_IMAGE_MAX_MB = 30
MIN_PREMIUM_DIM = 1080
DRIVE_DOWNLOAD = 'https://drive.google.com/uc?export=download&id='
DRIVE_FOLDER_MIME = 'application/vnd.google-apps.folder'
PROCESSED_CREATIVE_OUTPUTS_FOLDER = (
    os.environ.get('GOOGLE_PROCESSED_CREATIVE_OUTPUTS_FOLDER_ID')
    or os.environ.get('GOOGLE_PROCESSED_DRIVE_FOLDER_ID')
    or os.environ.get('VIDEOS_FOLDER')
    or ''
).strip()

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

def _drive_query_literal(value):
    return str(value or '').replace('\\', '\\\\').replace("'", "\\'")

def _drive_folder_meta(drive, folder_id):
    return drive.files().get(
        fileId=folder_id,
        fields='id,name,mimeType,webViewLink,parents,driveId',
        supportsAllDrives=True,
    ).execute()

def _shared_drive_output_error(root_meta):
    if root_meta.get('driveId'):
        return None
    return 'Configured processed output root is not on a Google Shared Drive.'

def _find_drive_child_folder(drive, parent_folder_id, folder_name):
    q = (
        f"mimeType='{DRIVE_FOLDER_MIME}' and trashed=false "
        f"and name='{_drive_query_literal(folder_name)}' "
        f"and '{_drive_query_literal(parent_folder_id)}' in parents"
    )
    resp = drive.files().list(
        q=q,
        pageSize=10,
        fields='files(id,name,webViewLink,parents,driveId)',
        includeItemsFromAllDrives=True,
        supportsAllDrives=True,
    ).execute()
    rows = resp.get('files') or []
    return rows[0] if rows else None

def _create_drive_child_folder(drive, parent_folder_id, folder_name):
    return drive.files().create(
        body={'name': folder_name, 'mimeType': DRIVE_FOLDER_MIME, 'parents': [parent_folder_id]},
        fields='id,name,webViewLink,parents,driveId',
        supportsAllDrives=True,
    ).execute()

def _ensure_combo_output_folder(drive, root_folder_id, folder_name):
    if not root_folder_id:
        raise RuntimeError('root output folder id required')
    if not folder_name:
        raise RuntimeError('folder_name required')
    root_meta = _drive_folder_meta(drive, root_folder_id)
    err = _shared_drive_output_error(root_meta)
    if err:
        raise RuntimeError(err)
    existing = _find_drive_child_folder(drive, root_folder_id, folder_name)
    if existing:
        existing['created'] = False
        return existing
    created = _create_drive_child_folder(drive, root_folder_id, folder_name)
    created['created'] = True
    return created

def _upload_image_to_drive(path, name, parent_folder_id):
    from google_engine import _google_services
    from googleapiclient.http import MediaFileUpload

    _info, _sheets, drive = _google_services()
    media = MediaFileUpload(path, mimetype='image/jpeg', resumable=True)
    created = drive.files().create(
        body={'name': name, 'mimeType': 'image/jpeg', 'parents': [parent_folder_id]},
        media_body=media,
        fields='id,name,webViewLink,size',
        supportsAllDrives=True,
    ).execute()
    try:
        drive.permissions().create(
            fileId=created['id'],
            body={'type': 'anyone', 'role': 'reader'},
            supportsAllDrives=True,
        ).execute()
    except Exception:
        created['public_warning'] = 'could_not_set_anyone_reader'
    created['download_url'] = DRIVE_DOWNLOAD + created['id']
    return created

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

def _apply_wearth_warmth(img):
    img = ImageEnhance.Brightness(img).enhance(1.04)
    img = ImageEnhance.Contrast(img).enhance(1.12)
    img = ImageEnhance.Color(img).enhance(1.04)
    r_ch, g_ch, b_ch = img.split()
    r_ch = ImageEnhance.Brightness(r_ch).enhance(1.035)
    g_ch = ImageEnhance.Brightness(g_ch).enhance(1.012)
    b_ch = ImageEnhance.Brightness(b_ch).enhance(0.985)
    return Image.merge('RGB', (r_ch, g_ch, b_ch))

def _apply_subtle_vignette(img):
    rgba = img.convert('RGBA')
    w, h = rgba.size
    mask = Image.new('L', (w, h), 0)
    draw = ImageDraw.Draw(mask)
    max_r = int((w ** 2 + h ** 2) ** 0.5 / 2)
    cx, cy = w // 2, h // 2
    for i in range(max_r, 0, -12):
        alpha = int(105 * (1 - i / max_r) ** 1.8)
        draw.ellipse((cx - i, cy - i, cx + i, cy + i), fill=alpha)
    shade = Image.new('RGBA', (w, h), (18, 15, 12, 0))
    shade.putalpha(mask)
    return Image.alpha_composite(rgba, shade).convert('RGB')

def _fit_image_canvas(img, target_size):
    target_w, target_h = target_size
    bg = img.copy()
    bg = bg.resize(target_size, Image.Resampling.LANCZOS)
    bg = bg.filter(ImageFilter.GaussianBlur(radius=24))
    bg = ImageEnhance.Brightness(bg).enhance(0.92)
    bg = ImageEnhance.Color(bg).enhance(0.88)
    fg = img.copy()
    fg.thumbnail((int(target_w * 0.96), int(target_h * 0.96)), Image.Resampling.LANCZOS)
    canvas = bg.convert('RGB')
    x = (target_w - fg.width) // 2
    y = (target_h - fg.height) // 2
    canvas.paste(fg, (x, y))
    return canvas

def _crop_or_fit_4x5(img):
    w, h = img.size
    ratio = w / h if h else 0
    target_ratio = 4 / 5
    if abs(ratio - target_ratio) <= 0.035 and w >= 1080 and h >= 1350:
        return img.resize((1080, 1350), Image.Resampling.LANCZOS)
    return _fit_image_canvas(img, (1080, 1350))

def _wrap_text(draw, text, font, max_width):
    words = str(text or '').split()
    lines, line = [], ''
    for word in words:
        test = f'{line} {word}'.strip()
        box = draw.textbbox((0, 0), test, font=font)
        if box[2] - box[0] > max_width and line:
            lines.append(line)
            line = word
        else:
            line = test
    if line:
        lines.append(line)
    return lines

def _font(size=44):
    try:
        return ImageFont.truetype('arial.ttf', size)
    except Exception:
        return ImageFont.load_default()

def _add_image_hook_overlay(img, text, safe_zone='bottom-left'):
    text = (text or '').strip()
    if not text:
        return img
    rgba = img.convert('RGBA')
    overlay = Image.new('RGBA', rgba.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font = _font(46 if img.height >= 1300 else 38)
    margin = 54 if img.height >= 1300 else 42
    max_width = img.width - margin * 2
    lines = _wrap_text(draw, text, font, max_width)
    line_h = int((draw.textbbox((0, 0), 'Ag', font=font)[3] + 12) * 1.15)
    block_h = line_h * len(lines) + 26
    zone = str(safe_zone or '').lower()
    y = margin if 'top' in zone else img.height - margin - block_h
    x = margin
    draw.rounded_rectangle((x - 18, y - 14, x + max_width + 18, y + block_h), radius=18, fill=(20, 18, 15, 118))
    yy = y
    for line in lines:
        draw.text((x + 2, yy + 2), line, font=font, fill=(0, 0, 0, 170))
        draw.text((x, yy), line, font=font, fill=(250, 247, 239, 255))
        yy += line_h
    return Image.alpha_composite(rgba, overlay).convert('RGB')

def _repair_image_exports(image_bytes, image_brain):
    src = Image.open(io.BytesIO(image_bytes)).convert('RGB')
    repaired = _apply_wearth_warmth(src)
    repaired = _apply_subtle_vignette(repaired)
    text_plan = image_brain.get('text_plan') or {}
    if text_plan.get('needs_hook_overlay'):
        repaired = _add_image_hook_overlay(
            repaired,
            text_plan.get('hook_overlay') or 'Your skin knows the difference.',
            text_plan.get('safe_zone') or 'bottom-left',
        )
    feed = _crop_or_fit_4x5(repaired)
    square = _fit_image_canvas(repaired, (1080, 1080))
    return {'feed_4_5': feed, 'carousel_1_1': square}

def _save_jpeg_temp(img, suffix):
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.close()
    img.save(tmp.name, format='JPEG', quality=92, optimize=True)
    return tmp.name

def _premium_polish_v2(img):
    img = img.convert('RGB')
    denoised = img.filter(ImageFilter.MedianFilter(size=3)).filter(ImageFilter.SMOOTH)
    img = Image.blend(img, denoised, 0.22)
    img = ImageOps.autocontrast(img, cutoff=1)
    img = ImageEnhance.Brightness(img).enhance(1.025)
    img = ImageEnhance.Contrast(img).enhance(1.08)
    img = ImageEnhance.Color(img).enhance(1.035)
    return img.filter(ImageFilter.UnsharpMask(radius=1.1, percent=105, threshold=4))

def _clean_square_canvas_v2(img):
    target_size = (1080, 1080)
    foreground = img.convert('RGB')
    foreground.thumbnail((930, 930), Image.Resampling.LANCZOS)
    base = img.resize(target_size, Image.Resampling.LANCZOS).filter(ImageFilter.GaussianBlur(radius=56))
    base = ImageEnhance.Brightness(base).enhance(0.72)
    base = ImageEnhance.Color(base).enhance(0.55)
    warm = Image.new('RGB', target_size, (74, 65, 55))
    canvas = Image.blend(base, warm, 0.62)
    shadow = Image.new('RGBA', target_size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(shadow)
    x = (target_size[0] - foreground.width) // 2
    y = (target_size[1] - foreground.height) // 2
    draw.rounded_rectangle(
        (x - 10, y - 8, x + foreground.width + 10, y + foreground.height + 14),
        radius=18,
        fill=(0, 0, 0, 46),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=18))
    rgba = canvas.convert('RGBA')
    rgba.alpha_composite(shadow)
    rgba.paste(foreground, (x, y))
    return rgba.convert('RGB')

def repair_image_v1():
    data = request.get_json(force=True, silent=True) or {}
    file_id = (data.get('image_file_id') or data.get('file_id') or '').strip()
    folder_name = (data.get('folder_name') or '').strip()
    combo_label = (data.get('combo_label') or f'Drive folder {folder_name}').strip()
    output_folder_id = (data.get('output_folder_id') or PROCESSED_CREATIVE_OUTPUTS_FOLDER or '').strip()
    provided_brain = data.get('image_brain') if isinstance(data.get('image_brain'), dict) else None
    if not file_id:
        return jsonify({'ok': False, 'error': 'image_file_id or file_id required'}), 400
    if not folder_name:
        return jsonify({'ok': False, 'error': 'folder_name required so repaired image lands in the correct processed folder'}), 400
    paths = []
    try:
        from google_engine import _google_services
        _info, _sheets, drive = _google_services()
        output_folder = _ensure_combo_output_folder(drive, output_folder_id, folder_name)
        upload_parent = output_folder['id']
        meta, image_bytes = _drive_image_meta_and_bytes(file_id)
        metrics = _image_brain_metrics(image_bytes, meta)
        image_brain = provided_brain or _claude_image_brain(_image_thumb_b64(image_bytes), metrics)
        exports = _repair_image_exports(image_bytes, image_brain)
        safe_label = ''.join(ch if ch.isalnum() or ch in '-_' else '-' for ch in (combo_label or f'folder-{folder_name}')).strip('-')[:60]
        uploads = {}
        for key, img in exports.items():
            path = _save_jpeg_temp(img, f'_{key}.jpg')
            paths.append(path)
            uploads[key] = _upload_image_to_drive(path, f'{safe_label}_WEARTH_{key}_image_v1.jpg', upload_parent)
        external_pending = []
        repair_decision = image_brain.get('repair_decision') or {}
        for item in repair_decision.get('requires_external_ai_tool') or []:
            if 'background' in str(item).lower():
                external_pending.append(item)
        result = {
            'ok': True,
            'source': {
                'file_id': file_id,
                'name': meta.get('name'),
                'webViewLink': meta.get('webViewLink'),
                **metrics,
            },
            'image_brain': image_brain,
            'actions_applied': [
                'applied_wearth_warmth_grade',
                'applied_subtle_vignette',
                'rendered_feed_4_5',
                'rendered_carousel_1_1_with_blurred_canvas',
                'uploaded_to_processed_shared_drive',
            ] + (['added_hook_overlay'] if (image_brain.get('text_plan') or {}).get('needs_hook_overlay') else []),
            'external_actions_pending': external_pending,
            'exports': uploads,
            'output_root_folder_id': output_folder_id,
            'output_folder_id': upload_parent,
            'output_folder': output_folder,
            'launch_gate': {
                'can_launch_without_judge': False,
                'reason': 'Repaired image must pass parent image/creative judge before Meta launch.',
            },
            'next_step': 'parent_image_judge_before_launch',
        }
        return jsonify(result)
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500
    finally:
        for path in paths:
            try:
                os.unlink(path)
            except Exception:
                pass

def repair_image_v2():
    data = request.get_json(force=True, silent=True) or {}
    feed_id = (data.get('feed_4_5_file_id') or data.get('feed_file_id') or '').strip()
    square_id = (data.get('carousel_1_1_file_id') or data.get('square_file_id') or '').strip()
    folder_name = (data.get('folder_name') or '').strip()
    combo_label = (data.get('combo_label') or f'Drive folder {folder_name}').strip()
    output_folder_id = (data.get('output_folder_id') or PROCESSED_CREATIVE_OUTPUTS_FOLDER or '').strip()
    judge = data.get('judge') if isinstance(data.get('judge'), dict) else {}
    if not (feed_id and square_id):
        return jsonify({'ok': False, 'error': 'feed_4_5_file_id and carousel_1_1_file_id required'}), 400
    if not folder_name:
        return jsonify({'ok': False, 'error': 'folder_name required so v2 outputs land in the correct processed folder'}), 400
    paths = []
    try:
        from google_engine import _google_services
        _info, _sheets, drive = _google_services()
        output_folder = _ensure_combo_output_folder(drive, output_folder_id, folder_name)
        upload_parent = output_folder['id']

        feed_meta, feed_bytes = _drive_image_meta_and_bytes(feed_id)
        square_meta, square_bytes = _drive_image_meta_and_bytes(square_id)
        feed_src = Image.open(io.BytesIO(feed_bytes)).convert('RGB')
        square_src = Image.open(io.BytesIO(square_bytes)).convert('RGB')

        feed_v2 = _premium_polish_v2(feed_src.resize((1080, 1350), Image.Resampling.LANCZOS))
        square_base = feed_v2 if feed_v2.height >= feed_v2.width else _premium_polish_v2(square_src)
        square_v2 = _premium_polish_v2(_clean_square_canvas_v2(square_base))

        safe_label = ''.join(ch if ch.isalnum() or ch in '-_' else '-' for ch in (combo_label or f'folder-{folder_name}')).strip('-')[:60]
        exports = {'feed_4_5': feed_v2, 'carousel_1_1': square_v2}
        uploads = {}
        for key, img in exports.items():
            path = _save_jpeg_temp(img, f'_{key}_v2.jpg')
            paths.append(path)
            uploads[key] = _upload_image_to_drive(path, f'{safe_label}_WEARTH_{key}_image_v2.jpg', upload_parent)

        return jsonify({
            'ok': True,
            'inputs': {
                'feed_4_5': {'file_id': feed_id, 'name': feed_meta.get('name')},
                'carousel_1_1': {'file_id': square_id, 'name': square_meta.get('name')},
            },
            'actions_applied': [
                'denoised_with_light_blend',
                'applied_autocontrast_and_premium_lighting',
                'applied_controlled_sharpening',
                'rebuilt_square_on_clean_warm_luxury_canvas',
                'uploaded_v2_to_processed_shared_drive',
            ],
            'judge_notes_used': judge.get('iteration_brief') or data.get('iteration_brief') or [],
            'exports': uploads,
            'output_root_folder_id': output_folder_id,
            'output_folder_id': upload_parent,
            'output_folder': output_folder,
            'launch_gate': {
                'can_launch_without_judge': False,
                'reason': 'Image v2 must pass parent image judge before Meta launch.',
            },
            'next_step': 'run_parent_image_judge_on_v2',
        })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500
    finally:
        for path in paths:
            try:
                os.unlink(path)
            except Exception:
                pass

def _heuristic_parent_image_judge(image_metrics, reason=''):
    issues = []
    for label, metrics in image_metrics.items():
        meta = metrics.get('meta_compliance') or {}
        if not meta.get('file_size_ok'):
            issues.append(f'{label}_file_over_meta_limit')
        if not meta.get('format_ok'):
            issues.append(f'{label}_format_not_preferred')
        if not meta.get('premium_resolution_ok'):
            issues.append(f'{label}_resolution_below_premium_floor')
    passed = not issues
    return {
        'pass_to_publish': passed,
        'decision': 'approved_for_launch' if passed else 'repair_again',
        'overall_score_0_10': 7.0 if passed else 5.0,
        'luxury_fit_0_10': 6.5,
        'mobile_hook_0_10': 6.5,
        'text_readability': 'unknown',
        'framing_ok': passed,
        'meta_compliance': passed,
        'iteration_brief': [] if passed else ['Fix technical image compliance before launch.'],
        'risks': issues + ([reason] if reason else []),
        'reasoning': 'Fallback image judge used because parent model was unavailable.',
        'model': 'heuristic',
    }

def _parent_image_judge(image_items, image_metrics, context):
    if not ANTHROPIC_KEY:
        return _heuristic_parent_image_judge(image_metrics, 'ANTHROPIC_API_KEY missing')
    prompt = {
        'task': 'You are WEARTH Active parent image creative judge. Decide if these repaired image outputs can be used in Meta ads or must be repaired again.',
        'brand': 'WEARTH Active: premium lyocell / plant-based activewear for Indian women. Quiet luxury, sensory fabric, skin comfort, premium but founder-led and authentic.',
        'hard_rules': [
            'Do not pass if text is unreadable or cluttered on mobile.',
            'Do not pass if image feels cheap, fake, careless, or off-brand for accessible luxury activewear.',
            'Do not pass if background repair looks artificial.',
            'Do not pass if product/body framing is poor or the main garment is unclear.',
            'Do not pass if Meta compatibility is false.',
            'Founder/raw authenticity can pass only when it increases trust and does not feel low-effort.',
        ],
        'context': context,
        'image_metrics': image_metrics,
        'required_json_schema': {
            'pass_to_publish': 'boolean',
            'decision': 'approved_for_launch|repair_again|reshoot_required',
            'overall_score_0_10': 'number',
            'luxury_fit_0_10': 'number',
            'mobile_hook_0_10': 'number',
            'text_readability': 'high|medium|low|none|unknown',
            'framing_ok': 'boolean',
            'meta_compliance': 'boolean',
            'iteration_brief': ['specific repair edits if not approved'],
            'risks': ['string'],
            'reasoning': 'short paragraph',
        },
    }
    content = [{'type': 'text', 'text': json.dumps(prompt, ensure_ascii=True)}]
    for item in image_items:
        content.append({'type': 'text', 'text': f"Image: {item['label']}"})
        content.append({'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/jpeg', 'data': item['b64']}})
    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
        resp = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=1200,
            temperature=0.15,
            messages=[{'role': 'user', 'content': content}],
        )
        text = (resp.content[0].text or '').strip()
        if text.startswith('```'):
            text = text.replace('```json', '').replace('```', '').strip()
        parsed = json.loads(text)
        parsed['model'] = ANTHROPIC_MODEL
        return parsed
    except Exception as e:
        return _heuristic_parent_image_judge(image_metrics, f'parent_image_judge_failed: {e}')

def judge_image_candidate():
    data = request.get_json(force=True, silent=True) or {}
    feed_id = (data.get('feed_4_5_file_id') or data.get('feed_file_id') or '').strip()
    square_id = (data.get('carousel_1_1_file_id') or data.get('square_file_id') or '').strip()
    if not (feed_id and square_id):
        return jsonify({'ok': False, 'error': 'feed_4_5_file_id and carousel_1_1_file_id required'}), 400
    try:
        feed_meta, feed_bytes = _drive_image_meta_and_bytes(feed_id)
        square_meta, square_bytes = _drive_image_meta_and_bytes(square_id)
        feed_metrics = _image_brain_metrics(feed_bytes, feed_meta)
        square_metrics = _image_brain_metrics(square_bytes, square_meta)
        image_items = [
            {'label': '4:5 feed image', 'b64': _image_thumb_b64(feed_bytes)},
            {'label': '1:1 carousel image', 'b64': _image_thumb_b64(square_bytes)},
        ]
        context = {
            'combo_label': data.get('combo_label') or '',
            'folder_name': data.get('folder_name') or '',
            'notes': data.get('notes') or '',
            'source_image_brain': data.get('image_brain') or {},
        }
        meta_ok = (
            feed_metrics.get('meta_compliance', {}).get('file_size_ok')
            and feed_metrics.get('meta_compliance', {}).get('format_ok')
            and feed_metrics.get('meta_compliance', {}).get('premium_resolution_ok')
            and square_metrics.get('meta_compliance', {}).get('file_size_ok')
            and square_metrics.get('meta_compliance', {}).get('format_ok')
            and square_metrics.get('meta_compliance', {}).get('premium_resolution_ok')
        )
        metrics = {'feed_4_5': feed_metrics, 'carousel_1_1': square_metrics}
        judge = _parent_image_judge(image_items, metrics, context)
        if not meta_ok:
            judge['pass_to_publish'] = False
            judge['meta_compliance'] = False
            judge['decision'] = 'repair_again'
            judge.setdefault('risks', []).append('Meta technical image precheck failed.')
        return jsonify({
            'ok': True,
            'feed_4_5': {'file_id': feed_id, 'name': feed_meta.get('name'), 'metrics': feed_metrics},
            'carousel_1_1': {'file_id': square_id, 'name': square_meta.get('name'), 'metrics': square_metrics},
            'judge': judge,
            'launch_gate': {
                'can_launch': bool(judge.get('pass_to_publish') and judge.get('decision') == 'approved_for_launch'),
                'reason': 'Image candidate must be approved by parent judge before Meta launch.',
            },
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
