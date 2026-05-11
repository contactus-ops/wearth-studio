import os
import json
import base64
import tempfile
import subprocess
import requests
import re
from flask import request, jsonify
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

from google_engine import _cell, _google_services, _sheet_id, _sheet_values

OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')
DRIVE_DOWNLOAD = 'https://drive.google.com/uc?export=download&id='
VIDEOS_FOLDER = (os.environ.get("VIDEOS_FOLDER") or os.environ.get("GOOGLE_DRIVE_OUTPUT_FOLDER_ID") or "").strip()
MAX_SOURCE_MB = float(os.environ.get("VIDEO_MAX_SOURCE_MB") or "1200")

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

HOOK_LINES = [
    "Your skin knows the difference.",
    "No synthetic scratch. No trapped heat.",
    "Fabric that breathes with you.",
    "This is not ordinary activewear.",
    "Plant-based comfort, made for movement.",
]

YELLOW_ASS = "&H0000D7FF&"  # warm yellow/gold in ASS BGR format
WHITE_ASS = "&H00FFFFFF&"


def _resolve_ffmpeg() -> str:
    import shutil
    b = shutil.which("ffmpeg")
    if b:
        return b
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe() or ""
    except Exception:
        return ""


def _drive_download_to_path(file_id: str, suffix: str = ".mp4") -> tuple[str | None, dict]:
    """Download via Drive API streaming, safe for large files and private Drive assets."""
    _info, _sheets, drive = _google_services()
    meta = drive.files().get(
        fileId=file_id,
        fields="id,name,mimeType,size,parents,webViewLink",
        supportsAllDrives=True,
    ).execute()
    size_mb = float(meta.get("size") or 0) / (1024 * 1024)
    if size_mb > MAX_SOURCE_MB:
        raise RuntimeError(f"source video {size_mb:.1f}MB exceeds VIDEO_MAX_SOURCE_MB={MAX_SOURCE_MB:.1f}MB")
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.close()
    req = drive.files().get_media(fileId=file_id, supportsAllDrives=True)
    with open(tmp.name, "wb") as fh:
        downloader = MediaIoBaseDownload(fh, req, chunksize=1024 * 1024 * 8)
        done = False
        while not done:
            _status, done = downloader.next_chunk()
    return tmp.name, meta


def _upload_video_to_drive(path: str, name: str, parent_folder_id: str | None = None) -> dict:
    _info, _sheets, drive = _google_services()
    folder_id = (parent_folder_id or VIDEOS_FOLDER or "").strip()
    body = {"name": name, "mimeType": "video/mp4"}
    if folder_id:
        body["parents"] = [folder_id]
    media = MediaFileUpload(path, mimetype="video/mp4", resumable=True, chunksize=1024 * 1024 * 8)
    created = drive.files().create(
        body=body,
        media_body=media,
        fields="id,name,webViewLink,size",
        supportsAllDrives=True,
    ).execute()
    try:
        drive.permissions().create(
            fileId=created["id"],
            body={"type": "anyone", "role": "reader"},
            supportsAllDrives=True,
        ).execute()
    except Exception:
        created["public_warning"] = "could_not_set_anyone_reader"
    created["download_url"] = DRIVE_DOWNLOAD + created["id"]
    return created


def _probe_video(path: str) -> dict:
    ffmpeg = _resolve_ffmpeg()
    if not ffmpeg:
        return {"ok": False, "error": "ffmpeg_not_available"}
    r = subprocess.run([ffmpeg, "-hide_banner", "-i", path], capture_output=True, text=True, timeout=45)
    text = (r.stderr or "") + "\n" + (r.stdout or "")
    import re
    dur = None
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", text)
    if m:
        dur = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    vm = re.search(r"Video:\s*([^,\s]+).*?(\d{3,5})x(\d{3,5}).*?(?:(\d+(?:\.\d+)?)\s*fps)?", text, re.I | re.S)
    am = re.search(r"Audio:\s*([^,\s]+)", text, re.I)
    return {
        "ok": bool(vm),
        "duration_s": round(dur, 2) if dur else None,
        "video_codec": vm.group(1).lower() if vm else "",
        "width": int(vm.group(2)) if vm else 0,
        "height": int(vm.group(3)) if vm else 0,
        "fps": float(vm.group(4)) if vm and vm.group(4) else None,
        "audio_codec": am.group(1).lower() if am else "",
        "has_audio": bool(am),
    }


def _choose_clip_window(duration: float | None, target: float = 24.0) -> tuple[float, float]:
    if not duration or duration <= 0:
        return 0.0, target
    if duration <= target:
        return 0.0, max(1.0, duration)
    # First pass uses a conservative scroll-edit: skip a tiny lead-in, preserve natural UGC.
    start = min(max(0.0, duration * 0.06), max(0.0, duration - target))
    return round(start, 2), min(target, duration - start)


def _extract_audio(input_path: str, audio_path: str, start_s: float, duration_s: float) -> bool:
    ffmpeg = _resolve_ffmpeg()
    if not ffmpeg:
        return False
    r = subprocess.run([
        ffmpeg, "-y", "-ss", str(start_s), "-t", str(duration_s), "-i", input_path,
        "-vn", "-ar", "16000", "-ac", "1", "-b:a", "64k", audio_path
    ], capture_output=True, text=True, timeout=180)
    return r.returncode == 0 and os.path.exists(audio_path) and os.path.getsize(audio_path) > 1024


def _ass_time(secs: float) -> str:
    h = int(secs // 3600)
    m = int((secs % 3600) // 60)
    s = secs % 60
    return f"{h:d}:{m:02d}:{s:05.2f}"


def _ass_escape(text: str) -> str:
    return (text or "").replace("\\", "\\\\").replace("{", "").replace("}", "").replace("\n", " ").strip()


def _build_hook_ass(hook: str, duration_s: float, play_res: tuple[int, int]) -> str:
    w, h = play_res
    header = _ass_header(w, h, font_size=64 if h >= 1600 else 46, margin_v=int(h * 0.14))
    hook = _ass_escape(hook)
    return header + f"Dialogue: 0,0:00:00.00,{_ass_time(min(2.8, duration_s))},Hook,,0,0,0,,{hook}\n"


def _ass_header(play_w: int, play_h: int, font_size: int = 58, margin_v: int = 180) -> str:
    return f"""[Script Info]
ScriptType: v4.00+
PlayResX: {play_w}
PlayResY: {play_h}
WrapStyle: 1

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,{font_size},{WHITE_ASS},{YELLOW_ASS},&H00000000,&H88000000,-1,0,0,0,100,100,0,0,1,4,1,2,90,90,{margin_v},1
Style: Hook,Arial,{font_size + 6},{WHITE_ASS},{YELLOW_ASS},&H00000000,&H88000000,-1,0,0,0,100,100,0,0,1,4,1,8,90,90,{max(90, int(play_h * 0.1))},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _build_caption_ass(transcript_data, highlight_words, start_offset: float, clip_duration: float, play_res: tuple[int, int], hook: str) -> str | None:
    words = []
    if transcript_data and isinstance(transcript_data, dict) and "words" in transcript_data:
        words = transcript_data["words"]
    elif transcript_data and isinstance(transcript_data, dict) and "segments" in transcript_data:
        for seg in transcript_data["segments"]:
            words.extend(seg.get("words") or [])
    filtered = []
    for w in words:
        try:
            st = float(w.get("start", 0)) - start_offset
            en = float(w.get("end", st + 0.4)) - start_offset
        except Exception:
            continue
        if en < 0 or st > clip_duration:
            continue
        ww = dict(w)
        ww["start"] = max(0, st)
        ww["end"] = min(clip_duration, en)
        filtered.append(ww)
    if not filtered:
        return _build_hook_ass(hook, clip_duration, play_res)

    w_res, h_res = play_res
    lines = [_ass_header(w_res, h_res, font_size=64 if h_res >= 1600 else 46, margin_v=int(h_res * 0.16))]
    lines.append(f"Dialogue: 0,0:00:00.00,{_ass_time(min(2.2, clip_duration))},Hook,,0,0,0,,{_ass_escape(hook)}")
    groups, group = [], []
    for item in filtered:
        group.append(item)
        word = (item.get("word") or "").strip()
        if len(group) >= 4 or word.endswith((".", "?", "!")):
            groups.append(group)
            group = []
    if group:
        groups.append(group)
    for group in groups:
        start = float(group[0].get("start", 0))
        end = max(start + 0.6, float(group[-1].get("end", start + 1)))
        text_parts = []
        for w in group:
            word_text = _ass_escape((w.get("word") or "").strip())
            if not word_text:
                continue
            is_highlight = any(hw in word_text.lower() for hw in highlight_words)
            if is_highlight:
                text_parts.append("{\\c" + YELLOW_ASS + "}" + word_text + "{\\c" + WHITE_ASS + "}")
            else:
                text_parts.append(word_text)
        if text_parts:
            lines.append(f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Default,,0,0,0,,{' '.join(text_parts)}")
    return "\n".join(lines) + "\n"


def _safe_ass_filter_path(path: str) -> str:
    return path.replace("\\", "/").replace(":", "\\:")


def _fit_filter(target: str, ass_path: str | None) -> str:
    if target == "9:16":
        base = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1"
    elif target == "1:1":
        base = "scale=1080:1080:force_original_aspect_ratio=increase,crop=1080:1080,setsar=1"
    else:
        base = "scale=1080:1350:force_original_aspect_ratio=increase,crop=1080:1350,setsar=1"
    # Lightweight premium grade: warmer, clearer, slightly lifted shadows.
    base += ",eq=contrast=1.06:brightness=0.015:saturation=1.06"
    if ass_path:
        base += f",ass='{_safe_ass_filter_path(ass_path)}'"
    return base


def _render_export(input_path: str, output_path: str, start_s: float, duration_s: float, target: str, ass_path: str | None) -> tuple[bool, str]:
    ffmpeg = _resolve_ffmpeg()
    if not ffmpeg:
        return False, "ffmpeg_not_available"
    cmd = [
        ffmpeg, "-y", "-ss", str(start_s), "-t", str(duration_s), "-i", input_path,
        "-vf", _fit_filter(target, ass_path),
        "-c:v", "libx264", "-profile:v", "high", "-level", "4.1", "-pix_fmt", "yuv420p",
        "-preset", "veryfast", "-crf", "21",
        "-c:a", "aac", "-b:a", "160k", "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
        "-movflags", "+faststart", output_path,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    return r.returncode == 0, r.stderr[-1000:]


def _find_processing_or_scanned_combo(sheets, sheet_id: str) -> dict | None:
    rows = _sheet_values(sheets, sheet_id, "combos!A2:N")
    for row_num, row in enumerate(rows, start=2):
        if _cell(row, 5).lower() not in {"processing", "scanned"}:
            continue
        if not (_cell(row, 2) and _cell(row, 3)):
            continue
        return {
            "row_number": row_num,
            "folder_id": _cell(row, 0),
            "folder_name": _cell(row, 1),
            "image_file_id": _cell(row, 2),
            "video_file_id": _cell(row, 3),
            "combo_label": _cell(row, 4),
        }
    return None


def _update_sheet_video_result(sheets, sheet_id: str, row_number: int, summary: dict) -> None:
    payload = {
        "status": "video_candidate_ready",
        "exports": {k: v.get("download_url") for k, v in (summary.get("exports") or {}).items()},
        "actions": summary.get("actions_applied") or [],
        "source_duration_s": summary.get("source", {}).get("duration_s"),
    }
    sheets.spreadsheets().values().batchUpdate(
        spreadsheetId=sheet_id,
        body={
            "valueInputOption": "RAW",
            "data": [
                {"range": f"combos!F{row_number}", "values": [["video_candidate_ready"]]},
                {"range": f"combos!M{row_number}", "values": [["produce_video_candidate"]]},
                {"range": f"combos!N{row_number}", "values": [[json.dumps(payload, ensure_ascii=True)]]},
            ],
        },
    ).execute()

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


def produce_video_candidate():
    """
    POST /api/video/produce-candidate
    Deterministic production candidate:
    - Drive API streaming download (large-file safe)
    - trim window
    - optional Whisper captions
    - 9:16 and 1:1 H.264/AAC exports
    - upload outputs to Drive; no large base64 response
    """
    data = request.get_json(force=True, silent=True) or {}
    sheet_id = _sheet_id()
    row_number = data.get("row_number")
    video_file_id = (data.get("video_file_id") or "").strip()
    combo_label = (data.get("combo_label") or "").strip()
    folder_name = (data.get("folder_name") or "").strip()
    hook = (data.get("hook") or HOOK_LINES[0]).strip()
    target_duration = float(data.get("target_duration_s") or 24.0)
    output_folder_id = (data.get("output_folder_id") or VIDEOS_FOLDER or "").strip()

    input_path = audio_path = ass_916 = ass_11 = None
    outputs: list[str] = []
    try:
        _info, sheets, _drive = _google_services()
        if not video_file_id:
            if not sheet_id:
                return jsonify({"ok": False, "error": "GOOGLE_SHEET_ID required when no video_file_id supplied"}), 400
            combo = _find_processing_or_scanned_combo(sheets, sheet_id)
            if not combo:
                return jsonify({"ok": False, "error": "No processing/scanned combo found and no video_file_id supplied"}), 404
            row_number = combo["row_number"]
            video_file_id = combo["video_file_id"]
            combo_label = combo_label or combo.get("combo_label") or f"Drive folder {combo.get('folder_name')}"
            folder_name = folder_name or combo.get("folder_name") or ""

        input_path, source_meta = _drive_download_to_path(video_file_id, ".mp4")
        source_probe = _probe_video(input_path)
        duration = source_probe.get("duration_s") or 0
        start_s, clip_duration = _choose_clip_window(duration, target_duration)

        transcript = None
        actions = [
            "stream_downloaded_from_drive",
            "trimmed_to_scroll_safe_window",
            "converted_to_h264_aac",
            "audio_loudness_normalized",
            "exported_9_16_reels_stories",
            "exported_1_1_carousel",
        ]

        if source_probe.get("has_audio"):
            audio_path = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3").name
            if _extract_audio(input_path, audio_path, start_s, clip_duration):
                transcript = _transcribe_whisper(audio_path)
        else:
            actions.append("no_source_audio_detected")

        if transcript:
            actions.append("whisper_transcribed")
            actions.append("burned_in_highlight_captions")
        else:
            actions.append("burned_in_hook_title_card")

        ass_916 = tempfile.NamedTemporaryFile(delete=False, suffix="_916.ass").name
        with open(ass_916, "w", encoding="utf-8") as f:
            f.write(_build_caption_ass(transcript, HIGHLIGHT_WORDS, start_s, clip_duration, (1080, 1920), hook) or _build_hook_ass(hook, clip_duration, (1080, 1920)))

        ass_11 = tempfile.NamedTemporaryFile(delete=False, suffix="_11.ass").name
        with open(ass_11, "w", encoding="utf-8") as f:
            f.write(_build_caption_ass(transcript, HIGHLIGHT_WORDS, start_s, clip_duration, (1080, 1080), hook) or _build_hook_ass(hook, clip_duration, (1080, 1080)))

        safe_label = re.sub(r"[^a-zA-Z0-9_-]+", "-", combo_label or f"folder-{folder_name}" or "wearth-video").strip("-")[:60]
        out_916 = tempfile.NamedTemporaryFile(delete=False, suffix="_9x16.mp4").name
        out_11 = tempfile.NamedTemporaryFile(delete=False, suffix="_1x1.mp4").name
        outputs.extend([out_916, out_11])

        ok_916, err_916 = _render_export(input_path, out_916, start_s, clip_duration, "9:16", ass_916)
        if not ok_916:
            return jsonify({"ok": False, "error": "9:16 render failed", "detail": err_916}), 500
        ok_11, err_11 = _render_export(input_path, out_11, start_s, clip_duration, "1:1", ass_11)
        if not ok_11:
            return jsonify({"ok": False, "error": "1:1 render failed", "detail": err_11}), 500

        upload_916 = _upload_video_to_drive(out_916, f"{safe_label}_WEARTH_9x16_candidate.mp4", output_folder_id)
        upload_11 = _upload_video_to_drive(out_11, f"{safe_label}_WEARTH_1x1_candidate.mp4", output_folder_id)

        result = {
            "ok": True,
            "row_number": row_number,
            "combo_label": combo_label,
            "folder_name": folder_name,
            "source": {
                "file_id": video_file_id,
                "name": source_meta.get("name"),
                "size_mb": round(float(source_meta.get("size") or 0) / (1024 * 1024), 2),
                **source_probe,
            },
            "clip": {"start_s": start_s, "duration_s": round(clip_duration, 2), "hook": hook},
            "actions_applied": actions,
            "transcript_preview": (transcript or {}).get("text", "")[:500] if isinstance(transcript, dict) else "",
            "exports": {
                "reels_stories_9_16": upload_916,
                "carousel_1_1": upload_11,
            },
            "next_step": "judge_candidate_before_launch",
            "launch_gate": {
                "can_launch_without_judge": False,
                "reason": "Production candidate must pass creative judge and Meta compliance gate first.",
            },
        }
        if sheet_id and row_number:
            _update_sheet_video_result(sheets, sheet_id, int(row_number), result)
            result["sheet_updated"] = True
        else:
            result["sheet_updated"] = False
        return jsonify(result)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500
    finally:
        for p in [input_path, audio_path, ass_916, ass_11, *outputs]:
            if p and os.path.exists(p):
                try:
                    os.unlink(p)
                except Exception:
                    pass
