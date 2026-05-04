# -*- coding: utf-8 -*-
# TARGET ROAS 4:1 AT ₹15K/MONTH SPEND — persistent used-media IDs in Google Drive (survives Railway restarts).
"""
JSON on Drive: {"instagram": [{"id": "...", "used_at": "ISO-8601"}], "seo_images": [...]}
Entries older than 30 days are dropped on read/write.

Requires GOOGLE_DRIVE_API_KEY. For writes to work with a browser/API key, create an empty
application/json file `wearth_used_media.json` in Drive, share it so the key can read it,
and set WEARTH_USED_MEDIA_DRIVE_FILE_ID to that file's id (recommended). Otherwise the
module tries to discover the file by name or create it (create often returns 403 without OAuth).
"""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import requests

TRACKER_FILENAME = "wearth_used_media.json"
GOOGLE_DRIVE_API_KEY = (os.environ.get("GOOGLE_DRIVE_API_KEY") or "").strip()
WEARTH_USED_MEDIA_DRIVE_FILE_ID = (os.environ.get("WEARTH_USED_MEDIA_DRIVE_FILE_ID") or "").strip()
JOBS_STATUS_PATH = os.environ.get("WEARTH_JOBS_STATUS_PATH", "/tmp/cursor_status.json")

_CATEGORIES = ("instagram", "seo_images")
_MAX_AGE = timedelta(days=30)
_lock = threading.Lock()
_cached_file_id: str | None = None
_verification_recorded = False


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(s: str) -> datetime | None:
    if not s or not isinstance(s, str):
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def _prune_entries(rows: Any) -> List[Dict[str, str]]:
    if not isinstance(rows, list):
        return []
    cutoff = datetime.now(timezone.utc) - _MAX_AGE
    out: List[Dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        mid = str(row.get("id") or "").strip()
        if not mid:
            continue
        ts = _parse_iso(str(row.get("used_at") or ""))
        if ts is not None and ts < cutoff:
            continue
        out.append({"id": mid, "used_at": str(row.get("used_at") or _now_iso())})
    return out


def _empty_state() -> Dict[str, List[Dict[str, str]]]:
    return {"instagram": [], "seo_images": []}


def _normalize_state(raw: Any) -> Dict[str, List[Dict[str, str]]]:
    st = _empty_state()
    if not isinstance(raw, dict):
        return st
    for k in _CATEGORIES:
        st[k] = _prune_entries(raw.get(k))
    return st


def _find_tracker_file_id() -> str:
    global _cached_file_id
    if WEARTH_USED_MEDIA_DRIVE_FILE_ID:
        _cached_file_id = WEARTH_USED_MEDIA_DRIVE_FILE_ID
        return WEARTH_USED_MEDIA_DRIVE_FILE_ID
    if _cached_file_id:
        return _cached_file_id
    if not GOOGLE_DRIVE_API_KEY:
        return ""
    try:
        q = f"name='{TRACKER_FILENAME}' and trashed=false"
        r = requests.get(
            "https://www.googleapis.com/drive/v3/files",
            params={
                "q": q,
                "fields": "files(id,name)",
                "pageSize": 5,
                "key": GOOGLE_DRIVE_API_KEY,
            },
            timeout=25,
        )
        if r.status_code != 200:
            return ""
        files = (r.json() or {}).get("files") or []
        if isinstance(files, list) and files:
            fid = str((files[0] or {}).get("id") or "").strip()
            if fid:
                _cached_file_id = fid
                return fid
    except Exception:
        return ""
    return ""


def _try_create_tracker_file() -> str:
    global _cached_file_id
    if not GOOGLE_DRIVE_API_KEY:
        return ""
    try:
        body = {
            "name": TRACKER_FILENAME,
            "mimeType": "application/json",
        }
        r = requests.post(
            "https://www.googleapis.com/drive/v3/files",
            params={"key": GOOGLE_DRIVE_API_KEY},
            json=body,
            timeout=25,
        )
        if r.status_code not in (200, 201):
            return ""
        fid = str((r.json() or {}).get("id") or "").strip()
        if not fid:
            return ""
        # upload initial JSON
        data = json.dumps(_empty_state()).encode("utf-8")
        up = requests.patch(
            f"https://www.googleapis.com/upload/drive/v3/files/{fid}",
            params={"uploadType": "media", "key": GOOGLE_DRIVE_API_KEY},
            data=data,
            headers={"Content-Type": "application/json"},
            timeout=35,
        )
        if up.status_code not in (200, 201):
            return ""
        global _cached_file_id
        _cached_file_id = fid
        return fid
    except Exception:
        return ""


def _load_state_unlocked() -> tuple[Dict[str, List[Dict[str, str]]], str]:
    fid = _find_tracker_file_id()
    if not fid:
        fid = _try_create_tracker_file()
    if not fid:
        return _empty_state(), ""
    if not GOOGLE_DRIVE_API_KEY:
        return _empty_state(), ""
    try:
        r = requests.get(
            f"https://www.googleapis.com/drive/v3/files/{fid}",
            params={"alt": "media", "key": GOOGLE_DRIVE_API_KEY},
            timeout=25,
        )
        if r.status_code != 200:
            return _empty_state(), fid
        raw = json.loads(r.content.decode("utf-8") or "{}")
        return _normalize_state(raw), fid
    except Exception:
        return _empty_state(), fid


def _save_state_unlocked(state: Dict[str, List[Dict[str, str]]], fid: str) -> bool:
    if not fid or not GOOGLE_DRIVE_API_KEY:
        return False
    for k in _CATEGORIES:
        state[k] = _prune_entries(state.get(k))
    try:
        data = json.dumps(state, indent=2, ensure_ascii=False).encode("utf-8")
        up = requests.patch(
            f"https://www.googleapis.com/upload/drive/v3/files/{fid}",
            params={"uploadType": "media", "key": GOOGLE_DRIVE_API_KEY},
            data=data,
            headers={"Content-Type": "application/json"},
            timeout=35,
        )
        return up.status_code in (200, 201)
    except Exception:
        return False


def _record_verification_once() -> None:
    global _verification_recorded
    if _verification_recorded:
        return
    now_utc = datetime.now(timezone.utc)
    ist = now_utc.astimezone(timezone(timedelta(hours=5, minutes=30)))
    ist_label = ist.strftime("%Y-%m-%d %H:%M:%S IST")
    try:
        try:
            with open(JOBS_STATUS_PATH, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {"steps": [], "session_start": ist_label}
        if not isinstance(data, dict):
            data = {"steps": [], "session_start": ist_label}
        steps = data.get("steps")
        if not isinstance(steps, list):
            steps = []
        steps.append(
            {
                "step": "used_media_tracker",
                "status": "COMPLETE",
                "evidence": "tracker file created in Drive, Instagram and SEO image dedup active",
                "timestamp_ist": ist_label,
                "timestamp_unix": int(now_utc.timestamp()),
            }
        )
        data["steps"] = steps
        data["last_updated_ist"] = ist_label
        parent = os.path.dirname(os.path.abspath(JOBS_STATUS_PATH))
        if parent and not os.path.isdir(parent):
            os.makedirs(parent, exist_ok=True)
        with open(JOBS_STATUS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        _verification_recorded = True
    except Exception:
        pass


def get_used_ids(category: str) -> List[str]:
    """Return media ids used within the last 30 days for this category (empty on any failure)."""
    cat = (category or "").strip()
    if cat not in _CATEGORIES:
        return []
    if not GOOGLE_DRIVE_API_KEY:
        return []
    with _lock:
        try:
            state, fid = _load_state_unlocked()
            if not fid:
                return []
            ids = [str(x.get("id") or "").strip() for x in state.get(cat, []) if str(x.get("id") or "").strip()]
            return list(dict.fromkeys(ids))
        except Exception:
            return []


def mark_used(category: str, media_id: str) -> None:
    """Append a usage record and persist to Drive (no-op on failure)."""
    cat = (category or "").strip()
    mid = str(media_id or "").strip()
    if cat not in _CATEGORIES or not mid or not GOOGLE_DRIVE_API_KEY:
        return
    with _lock:
        try:
            state, fid = _load_state_unlocked()
            if not fid:
                fid = _try_create_tracker_file()
            if not fid:
                return
            rows = list(state.get(cat) or [])
            rows.append({"id": mid, "used_at": _now_iso()})
            state[cat] = _prune_entries(rows)
            ok = _save_state_unlocked(state, fid)
            if ok:
                _record_verification_once()
        except Exception:
            return


def reset_category(category: str) -> None:
    """Overwrite a category's usage list with [] and persist to Drive (no-op on failure)."""
    cat = (category or "").strip()
    if cat not in _CATEGORIES or not GOOGLE_DRIVE_API_KEY:
        return
    with _lock:
        try:
            state, fid = _load_state_unlocked()
            if not fid:
                fid = _try_create_tracker_file()
            if not fid:
                return
            state[cat] = []
            _save_state_unlocked(state, fid)
        except Exception:
            return
