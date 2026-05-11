import base64
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
from typing import Any, Dict, List, Optional, Tuple

import requests
from flask import jsonify, request
from PIL import Image, ImageStat

from google_engine import _cell, _google_services, _sheet_id, _sheet_values


ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")

META_IMAGE_MAX_MB = 30
META_VIDEO_MAX_MB = 4096
MIN_PREMIUM_DIM = 1080

WEARTH_ANGLES = [
    "no synthetic scratch / skin-first comfort",
    "plant-based luxury fabric / quiet status",
    "cooler movement in Indian heat",
    "closed-loop botanical fibre / conscious premium",
    "presence wear, not generic performance wear",
]


def _drive_file_meta_and_bytes(file_id: str) -> Tuple[Dict[str, Any], bytes]:
    from googleapiclient.http import MediaIoBaseDownload

    _info, _sheets, drive = _google_services()
    meta = (
        drive.files()
        .get(
            fileId=file_id,
            fields="id,name,mimeType,size,webViewLink",
            supportsAllDrives=True,
        )
        .execute()
    )
    fh = io.BytesIO()
    request_media = drive.files().get_media(fileId=file_id, supportsAllDrives=True)
    downloader = MediaIoBaseDownload(fh, request_media)
    done = False
    while not done:
        _status, done = downloader.next_chunk()
    return meta, fh.getvalue()


def _mb(n_bytes: int) -> float:
    return round(n_bytes / (1024 * 1024), 2)


def _aspect_label(w: int, h: int) -> str:
    if not w or not h:
        return "unknown"
    ratio = w / h
    known = {
        "9:16": 9 / 16,
        "4:5": 4 / 5,
        "1:1": 1,
        "16:9": 16 / 9,
        "1.91:1": 1.91,
    }
    best = min(known.items(), key=lambda kv: abs(kv[1] - ratio))
    if abs(best[1] - ratio) <= 0.04:
        return best[0]
    return f"{ratio:.2f}:1"


def _image_metrics(image_bytes: bytes, meta: Dict[str, Any]) -> Dict[str, Any]:
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    w, h = img.size
    stat = ImageStat.Stat(img.resize((64, 64)))
    brightness = round(sum(stat.mean) / 3, 2)
    contrast = round(sum(stat.stddev) / 3, 2)
    fmt = (meta.get("mimeType") or "").split("/")[-1].lower()
    issues = []
    actions = []
    if _mb(len(image_bytes)) > META_IMAGE_MAX_MB:
        issues.append("image_file_over_30mb")
        actions.append("compress_to_jpeg_or_png_under_30mb")
    if min(w, h) < MIN_PREMIUM_DIM:
        issues.append("image_under_1080_short_side")
        actions.append("upscale_or_replace_image")
    if fmt not in {"jpeg", "jpg", "png"}:
        issues.append("non_meta_preferred_image_format")
        actions.append("convert_to_jpeg_or_png")
    if brightness < 80:
        issues.append("image_too_dark_for_mobile_feed")
        actions.append("lift_exposure_selectively")
    if contrast < 35:
        issues.append("low_visual_separation")
        actions.append("increase_contrast_or_subject_separation")
    return {
        "file_name": meta.get("name"),
        "mime_type": meta.get("mimeType"),
        "size_mb": _mb(len(image_bytes)),
        "width": w,
        "height": h,
        "aspect_ratio": _aspect_label(w, h),
        "brightness": brightness,
        "contrast": contrast,
        "meta_compliance": {
            "image_file_size_ok": _mb(len(image_bytes)) <= META_IMAGE_MAX_MB,
            "format_ok": fmt in {"jpeg", "jpg", "png"},
            "premium_resolution_ok": min(w, h) >= MIN_PREMIUM_DIM,
        },
        "detected_issues": issues,
        "recommended_actions": actions,
    }


def _resolve_ffmpeg() -> str:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        return ffmpeg
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe() or ""
    except Exception:
        return ""


def _resolve_ffprobe() -> str:
    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        return ffprobe
    ffmpeg = _resolve_ffmpeg()
    if ffmpeg:
        candidate = os.path.join(os.path.dirname(ffmpeg), "ffprobe.exe")
        if os.path.exists(candidate):
            return candidate
        candidate = os.path.join(os.path.dirname(ffmpeg), "ffprobe")
        if os.path.exists(candidate):
            return candidate
    return ""


def _run_ffprobe(path: str) -> Dict[str, Any]:
    ffprobe = _resolve_ffprobe()
    if not ffprobe:
        return {"ok": False, "error": "ffprobe_not_available"}
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            path,
        ],
        capture_output=True,
        text=True,
        timeout=45,
    )
    if result.returncode != 0:
        return {"ok": False, "error": result.stderr[-500:]}
    try:
        out = json.loads(result.stdout or "{}")
        out["ok"] = True
        return out
    except Exception as exc:
        return {"ok": False, "error": f"ffprobe_json_parse_failed: {exc}"}


def _video_metrics(video_bytes: bytes, meta: Dict[str, Any]) -> Tuple[Dict[str, Any], List[bytes]]:
    suffix = ".mp4"
    name = (meta.get("name") or "").lower()
    if name.endswith(".mov"):
        suffix = ".mov"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(video_bytes)
    tmp.flush()
    tmp.close()
    frames: List[bytes] = []
    try:
        probe = _run_ffprobe(tmp.name)
        streams = probe.get("streams") or []
        v = next((s for s in streams if s.get("codec_type") == "video"), {})
        a = next((s for s in streams if s.get("codec_type") == "audio"), {})
        sub_streams = [s for s in streams if s.get("codec_type") == "subtitle"]
        fmt = probe.get("format") or {}
        duration = float(fmt.get("duration") or v.get("duration") or 0)
        width = int(v.get("width") or 0)
        height = int(v.get("height") or 0)
        fps = _parse_fps(v.get("avg_frame_rate") or v.get("r_frame_rate") or "")
        video_codec = v.get("codec_name") or ""
        audio_codec = a.get("codec_name") or ""
        issues = []
        actions = []
        size_mb = _mb(len(video_bytes))
        if size_mb > META_VIDEO_MAX_MB:
            issues.append("video_file_over_4gb")
            actions.append("compress_h264_aac_under_4gb")
        if width and height and min(width, height) < MIN_PREMIUM_DIM:
            issues.append("video_under_1080_short_side")
            actions.append("upscale_or_select_higher_resolution_video")
        if video_codec and video_codec not in {"h264", "hevc"}:
            issues.append("video_codec_not_meta_preferred")
            actions.append("transcode_to_h264")
        if not audio_codec:
            issues.append("no_audio_stream_detected")
        elif audio_codec not in {"aac", "mp3", "opus"}:
            issues.append("audio_codec_not_meta_preferred")
            actions.append("transcode_audio_to_aac")
        if not sub_streams:
            actions.append("generate_burned_in_subtitles_if_speech_present")
        if duration and duration > 35:
            actions.append("trim_to_strongest_15_to_30_seconds")
        if _aspect_label(width, height) != "9:16":
            actions.append("create_9_16_reels_stories_export")
        if _aspect_label(width, height) != "1:1":
            actions.append("create_1_1_carousel_export")

        frames = _extract_sample_frames(tmp.name, duration)
        return (
            {
                "file_name": meta.get("name"),
                "mime_type": meta.get("mimeType"),
                "size_mb": size_mb,
                "duration_s": round(duration, 2) if duration else None,
                "width": width,
                "height": height,
                "aspect_ratio": _aspect_label(width, height),
                "fps": fps,
                "video_codec": video_codec,
                "audio_codec": audio_codec,
                "has_audio": bool(audio_codec),
                "has_subtitle_stream": bool(sub_streams),
                "sample_frame_count": len(frames),
                "meta_compliance": {
                    "video_file_size_ok": size_mb <= META_VIDEO_MAX_MB,
                    "format_ok": (meta.get("mimeType") or "") in {"video/mp4", "video/quicktime"},
                    "premium_resolution_ok": min(width or 0, height or 0) >= MIN_PREMIUM_DIM,
                    "codec_ok": video_codec in {"h264", "hevc", ""},
                    "audio_ok": bool(audio_codec),
                },
                "detected_issues": issues,
                "recommended_actions": actions,
                "probe_ok": probe.get("ok") is True,
                "probe_error": probe.get("error"),
            },
            frames,
        )
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass


def _parse_fps(raw: str) -> Optional[float]:
    if not raw or "/" not in raw:
        return None
    try:
        a, b = raw.split("/", 1)
        return round(float(a) / float(b), 2) if float(b) else None
    except Exception:
        return None


def _extract_sample_frames(path: str, duration: float) -> List[bytes]:
    ffmpeg = _resolve_ffmpeg()
    if not ffmpeg:
        return []
    if not duration or duration <= 0:
        times = [0.5]
    else:
        times = [max(0.2, duration * x) for x in (0.08, 0.35, 0.7)]
    frames = []
    for idx, t in enumerate(times):
        out = tempfile.NamedTemporaryFile(delete=False, suffix=f"_{idx}.jpg")
        out.close()
        try:
            result = subprocess.run(
                [
                    ffmpeg,
                    "-y",
                    "-ss",
                    str(round(t, 2)),
                    "-i",
                    path,
                    "-frames:v",
                    "1",
                    "-vf",
                    "scale='min(900,iw)':-2",
                    "-q:v",
                    "3",
                    out.name,
                ],
                capture_output=True,
                text=True,
                timeout=45,
            )
            if result.returncode == 0 and os.path.exists(out.name):
                with open(out.name, "rb") as f:
                    frames.append(f.read())
        finally:
            try:
                os.unlink(out.name)
            except Exception:
                pass
    return frames


def _jpeg_b64_from_image_bytes(image_bytes: bytes, max_size=(1200, 1200)) -> str:
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    img.thumbnail(max_size)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=82)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _jpeg_b64(raw_jpeg: bytes) -> str:
    return base64.b64encode(raw_jpeg).decode("utf-8")


def _anthropic_creative_judgement(image_b64: str, frame_b64s: List[str], image_metrics: Dict[str, Any], video_metrics: Dict[str, Any]) -> Dict[str, Any]:
    if not ANTHROPIC_KEY:
        return _heuristic_creative_judgement(image_metrics, video_metrics, "ANTHROPIC_API_KEY missing")
    prompt = {
        "role": "system",
        "task": "You are the senior creative strategy director and media buyer for WEARTH Active, a luxury premium plant-based activewear brand in India.",
        "brand_rules": [
            "Quiet luxury, science-backed, sensory, premium, women-first.",
            "Avoid generic gym-bro or discount language.",
            "Do not use TENCEL or lyocell.",
            "Decide like a real Meta performance creative team optimizing for online sales.",
        ],
        "return_only_valid_json": True,
        "required_schema": {
            "creative_score_0_10": "number",
            "luxury_fit_0_10": "number",
            "mobile_hook_0_10": "number",
            "launch_recommendation": "launch_as_is|improve_then_launch|do_not_launch",
            "image": {
                "has_prominent_text": "boolean",
                "text_readability": "high|medium|low|none",
                "needs_overlay": "boolean",
                "overlay_hook": "string",
                "image_actions": ["string"],
            },
            "video": {
                "first_2s_strength": "high|medium|low|unknown",
                "needs_subtitles": "boolean",
                "caption_style": "string",
                "video_actions": ["string"],
            },
            "strategy": {
                "primary_angle": "string",
                "secondary_angle": "string",
                "primary_text": "string under 125 chars",
                "headline": "string under 40 chars",
                "cta": "string",
                "audience_note": "string",
            },
            "risks": ["string"],
            "reasoning": "one concise paragraph",
        },
        "image_metrics": image_metrics,
        "video_metrics": video_metrics,
    }
    content: List[Dict[str, Any]] = [
        {"type": "text", "text": json.dumps(prompt, ensure_ascii=True)}
    ]
    content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_b64}})
    for f in frame_b64s[:3]:
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": f}})
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
        resp = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=1200,
            temperature=0.2,
            messages=[{"role": "user", "content": content}],
        )
        text = (resp.content[0].text or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?", "", text).strip()
            text = re.sub(r"```$", "", text).strip()
        parsed = json.loads(text)
        parsed["model"] = ANTHROPIC_MODEL
        return parsed
    except Exception as exc:
        return _heuristic_creative_judgement(image_metrics, video_metrics, f"anthropic_failed: {exc}")


def _heuristic_creative_judgement(image_metrics: Dict[str, Any], video_metrics: Dict[str, Any], note: str = "") -> Dict[str, Any]:
    img_issues = image_metrics.get("detected_issues") or []
    vid_issues = video_metrics.get("detected_issues") or []
    vid_actions = video_metrics.get("recommended_actions") or []
    score = 8.0 - min(3.0, 0.5 * len(img_issues) + 0.35 * len(vid_issues))
    if "generate_burned_in_subtitles_if_speech_present" in vid_actions:
        score -= 0.4
    recommendation = "improve_then_launch" if img_issues or vid_actions else "launch_as_is"
    if score < 5.5:
        recommendation = "do_not_launch"
    return {
        "creative_score_0_10": round(max(0, score), 1),
        "luxury_fit_0_10": 7.2,
        "mobile_hook_0_10": 6.8,
        "launch_recommendation": recommendation,
        "image": {
            "has_prominent_text": None,
            "text_readability": "unknown",
            "needs_overlay": True,
            "overlay_hook": "you will never go back to polyester.",
            "image_actions": image_metrics.get("recommended_actions") or ["model_review_needed"],
        },
        "video": {
            "first_2s_strength": "unknown",
            "needs_subtitles": not video_metrics.get("has_subtitle_stream"),
            "caption_style": "burned-in white captions with yellow keyword emphasis",
            "video_actions": vid_actions,
        },
        "strategy": {
            "primary_angle": WEARTH_ANGLES[0],
            "secondary_angle": WEARTH_ANGLES[1],
            "primary_text": "You will never go back to polyester.",
            "headline": "Fabric grown, not made.",
            "cta": "Shop now",
            "audience_note": "Premium women in Indian metros with high-value commerce intent.",
        },
        "risks": img_issues + vid_issues + ([note] if note else []),
        "reasoning": "Fallback heuristic used; model judgement unavailable.",
        "model": "heuristic",
    }


def _meta_placement_plan(image_metrics: Dict[str, Any], video_metrics: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "strict_rule": "Do not launch until production exports satisfy Meta format/size/resolution checks.",
        "carousel_feed_export": {
            "required": True,
            "target": "1:1 square cards, 1080x1080 or higher, image JPG/PNG under 30MB, video MP4/H.264/AAC under 4GB.",
        },
        "feed_export": {
            "recommended": True,
            "target": "4:5 1080x1350 for feed where available.",
        },
        "reels_stories_export": {
            "recommended": True,
            "target": "9:16 1080x1920 with text/logo outside unsafe top/bottom zones.",
        },
        "source_image_current_aspect": image_metrics.get("aspect_ratio"),
        "source_video_current_aspect": video_metrics.get("aspect_ratio"),
        "requires_multi_aspect_renders_for_100_percent_placement": True,
    }


def _find_processing_combo(sheets, sheet_id: str) -> Optional[Dict[str, Any]]:
    rows = _sheet_values(sheets, sheet_id, "combos!A2:N")
    for row_num, row in enumerate(rows, start=2):
        if _cell(row, 5).lower() != "processing":
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


def _update_scan_result(sheets, sheet_id: str, row_number: int, scan: Dict[str, Any]) -> None:
    summary = {
        "score": scan.get("creative_score_0_10"),
        "recommendation": scan.get("launch_recommendation"),
        "angle": ((scan.get("strategy") or {}).get("primary_angle") or ""),
        "image_actions": ((scan.get("image") or {}).get("image_actions") or [])[:3],
        "video_actions": ((scan.get("video") or {}).get("video_actions") or [])[:3],
    }
    updates = [
        {"range": f"combos!F{row_number}", "values": [["scanned"]]},
        {"range": f"combos!M{row_number}", "values": [["creative_scan"]]},
        {"range": f"combos!N{row_number}", "values": [[json.dumps(summary, ensure_ascii=True)]]},
    ]
    sheets.spreadsheets().values().batchUpdate(
        spreadsheetId=sheet_id,
        body={"valueInputOption": "RAW", "data": updates},
    ).execute()


def creative_scan_combo():
    """
    POST /api/creative/scan-combo
    Body can include image_file_id/video_file_id, or omit them to scan the first Sheet row with status=processing.
    """
    data = request.get_json(force=True, silent=True) or {}
    sheet_id = _sheet_id()
    try:
        _info, sheets, _drive = _google_services()
        row_number = data.get("row_number")
        combo = {
            "row_number": row_number,
            "folder_name": str(data.get("folder_name") or ""),
            "image_file_id": str(data.get("image_file_id") or ""),
            "video_file_id": str(data.get("video_file_id") or ""),
            "combo_label": str(data.get("combo_label") or ""),
        }
        if not (combo["image_file_id"] and combo["video_file_id"]):
            if not sheet_id:
                return jsonify({"ok": False, "error": "GOOGLE_SHEET_ID required when no file IDs are supplied"}), 400
            picked = _find_processing_combo(sheets, sheet_id)
            if not picked:
                return jsonify({"ok": False, "error": "No processing combo found and no file IDs supplied"}), 404
            combo = picked
            row_number = picked.get("row_number")

        image_meta, image_bytes = _drive_file_meta_and_bytes(combo["image_file_id"])
        video_meta, video_bytes = _drive_file_meta_and_bytes(combo["video_file_id"])
        image_metrics = _image_metrics(image_bytes, image_meta)
        video_metrics, frames = _video_metrics(video_bytes, video_meta)

        image_b64 = _jpeg_b64_from_image_bytes(image_bytes)
        frame_b64s = [_jpeg_b64(f) for f in frames]
        judgement = _anthropic_creative_judgement(image_b64, frame_b64s, image_metrics, video_metrics)

        scan = {
            "ok": True,
            "combo": combo,
            "creative_score_0_10": judgement.get("creative_score_0_10"),
            "luxury_fit_0_10": judgement.get("luxury_fit_0_10"),
            "mobile_hook_0_10": judgement.get("mobile_hook_0_10"),
            "launch_recommendation": judgement.get("launch_recommendation"),
            "image": {**image_metrics, **(judgement.get("image") or {})},
            "video": {**video_metrics, **(judgement.get("video") or {})},
            "strategy": judgement.get("strategy") or {},
            "risks": judgement.get("risks") or [],
            "reasoning": judgement.get("reasoning"),
            "model": judgement.get("model"),
            "meta_placement_plan": _meta_placement_plan(image_metrics, video_metrics),
        }

        if sheet_id and row_number:
            _update_scan_result(sheets, sheet_id, int(row_number), scan)
            scan["sheet_updated"] = True
        else:
            scan["sheet_updated"] = False

        return jsonify(scan)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500
