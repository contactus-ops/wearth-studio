import os
import json
import base64
import tempfile
import subprocess
import requests
from flask import request, jsonify

OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')
DRIVE_DOWNLOAD = 'https://drive.google.com/uc?export=download&id='

WEARTH_CAPTIONS = [
    'you will never go back to polyester.',
    'fabric grown, not made.',
    'the women who know, dont go back.',
    'worn by women who stopped settling.',
    'plant-based. closed-loop. yours.',
    'this is what happens when you stop wearing polyester.',
    'not performance wear. presence wear.',
]

HIGHLIGHT_WORDS = [
    'wearth', 'eucalyptus', 'plant', 'fabric', 'grow', 'grown', 'polyester',
    'back', 'different', 'skin', 'breathe', 'cool', 'soft', 'natural',
    'closed-loop', 'sustainable', 'feel', 'never', 'women', 'settle',
    'presence', 'performance', 'move', 'wear',
]

def _download_drive_file(file_id, suffix='.mp4'):
    session = requests.Session()
    url = DRIVE_DOWNLOAD + file_id
    resp = session.get(url, stream=True, timeout=60)
    for key, value in resp.cookies.items():
        if key.startswith('download_warning'):
            url = url + '&confirm=' + value
            resp = session.get(url, stream=True, timeout=120)
            break
    if resp.status_code != 200:
        return None
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    for chunk in resp.iter_content(chunk_size=1024 * 1024):
        if chunk:
            tmp.write(chunk)
    tmp.flush()
    tmp.close()
    return tmp.name

def _get_video_duration(path):
    try:
        r = subprocess.run(
            ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', path],
            capture_output=True, text=True, timeout=30
        )
        info = json.loads(r.stdout)
        return float(info['format']['duration'])
    except Exception:
        return 60.0

def _find_best_clip(duration, target=28):
    if duration <= target:
        return 0.0, duration
    start = duration * 0.20
    max_start = duration - target
    start = min(start, max_start)
    return round(start, 2), target

def _transcribe_whisper(audio_path):
    if not OPENAI_API_KEY:
        return None
    try:
        with open(audio_path, 'rb') as f:
            resp = requests.post(
                'https://api.openai.com/v1/audio/transcriptions',
                headers={'Authorization': f'Bearer {OPENAI_API_KEY}'},
                files={'file': ('audio.mp3', f, 'audio/mpeg')},
                data={'model': 'whisper-1', 'response_format': 'verbose_json', 'timestamp_granularities[]': 'word'},
                timeout=120
            )
        if resp.status_code == 200:
            return resp.json()
        return None
    except Exception:
        return None

def _build_ass_subtitles(transcript_data, highlight_words):
    ass_header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 1

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Montserrat,68,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,1,2,80,80,200,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [ass_header]
    words = []
    if transcript_data and 'words' in transcript_data:
        words = transcript_data['words']
    elif transcript_data and 'segments' in transcript_data:
        for seg in transcript_data['segments']:
            if 'words' in seg:
                words.extend(seg['words'])
    if not words:
        return None
    groups, group = [], []
    for w in words:
        group.append(w)
        if len(group) >= 5:
            groups.append(group)
            group = []
    if group:
        groups.append(group)
    def ts(secs):
        h = int(secs // 3600)
        m = int((secs % 3600) // 60)
        s = secs % 60
        return f"{h:d}:{m:02d}:{s:05.2f}"
    for group in groups:
        if not group:
            continue
        start = group[0].get('start', 0)
        end = group[-1].get('end', start + 1)
        text_parts = []
        for w in group:
            word_text = w.get('word', '').strip()
            is_highlight = any(hw in word_text.lower() for hw in highlight_words)
            if is_highlight:
                text_parts.append('{\\c&H0000FFFF&}' + word_text + '{\\c&H00FFFFFF&}')
            else:
                text_parts.append(word_text)
        lines.append(f"Dialogue: 0,{ts(start)},{ts(end)},Default,,0,0,0,,{' '.join(text_parts)}")
    return '\n'.join(lines)

def _process_video(input_path, output_path, start_time, duration, ass_path=None):
    w, h = 1080, 1920
    cmd = ['ffmpeg', '-y', '-ss', str(start_time), '-t', str(duration), '-i', input_path]
    video_filter = f'crop=ih*9/16:ih,scale={w}:{h},setsar=1'
    if ass_path:
        safe_ass = ass_path.replace('\\', '/').replace(':', '\\:')
        video_filter += f",ass='{safe_ass}'"
    cmd += ['-vf', video_filter, '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
            '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', output_path]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    return result.returncode == 0, result.stderr

def video_process():
    data = request.get_json(force=True, silent=True) or {}
    file_id = (data.get('file_id') or '').strip()
    caption_idx = data.get('caption_idx')
    if not file_id:
        return jsonify({'error': 'file_id required'}), 400
    input_path = _download_drive_file(file_id, '.mp4')
    if not input_path:
        return jsonify({'error': 'could not download video from Drive'}), 400
    audio_path = None
    ass_path = None
    output_path = None
    try:
        duration = _get_video_duration(input_path)
        start_time, clip_duration = _find_best_clip(duration)
        audio_path = input_path.replace('.mp4', '_audio.mp3')
        subprocess.run(['ffmpeg', '-y', '-i', input_path, '-ss', str(start_time), '-t', str(clip_duration),
                       '-vn', '-ar', '16000', '-ac', '1', audio_path], capture_output=True, timeout=120)
        transcript_data = None
        if os.path.exists(audio_path):
            transcript_data = _transcribe_whisper(audio_path)
            if transcript_data:
                ass_content = _build_ass_subtitles(transcript_data, HIGHLIGHT_WORDS)
                if ass_content:
                    ass_path = input_path.replace('.mp4', '_subs.ass')
                    with open(ass_path, 'w', encoding='utf-8') as f:
                        f.write(ass_content)
        output_path = input_path.replace('.mp4', '_processed.mp4')
        ok, err = _process_video(input_path, output_path, start_time, clip_duration, ass_path)
        if not ok:
            return jsonify({'error': 'ffmpeg failed', 'detail': err[-500:]}), 500
        with open(output_path, 'rb') as f:
            video_b64 = base64.b64encode(f.read()).decode()
        caption = WEARTH_CAPTIONS[int(caption_idx or 0) % len(WEARTH_CAPTIONS)]
        return jsonify({'ok': True, 'video_b64': video_b64, 'caption': caption,
                        'transcript': transcript_data.get('text', '') if transcript_data else '',
                        'duration_s': clip_duration, 'start_s': start_time})
    finally:
        for p in [input_path, audio_path, ass_path, output_path]:
            if p and os.path.exists(p):
                try:
                    os.unlink(p)
                except Exception:
                    pass
