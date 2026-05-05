from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

USED_MEDIA_PATH = os.environ.get("USED_MEDIA_PATH", "/tmp/used_media.json")
_CATEGORIES = ("instagram", "instagram_video", "seo_images")
_MAX_AGE = timedelta(days=30)
_RESET_AFTER = timedelta(days=7)
_lock = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(s: str) -> datetime | None:
    if not s or not isinstance(s, str):
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def _prune_entries(rows: Any) -> list[dict[str, str]]:
    if not isinstance(rows, list):
        return []
    cutoff = datetime.now(timezone.utc) - _MAX_AGE
    out: list[dict[str, str]] = []
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


def _empty_state() -> dict[str, list[dict[str, str]]]:
    return {"instagram": [], "instagram_video": [], "seo_images": []}


def _state_file() -> Path:
    return Path(USED_MEDIA_PATH)


def _should_weekly_reset(p: Path) -> bool:
    try:
        if not p.exists():
            return False
        mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
        return (datetime.now(timezone.utc) - mtime) > _RESET_AFTER
    except Exception:
        return False


def _load_state_unlocked() -> dict[str, list[dict[str, str]]]:
    p = _state_file()
    if _should_weekly_reset(p):
        try:
            p.unlink(missing_ok=True)
        except Exception:
            pass
        return _empty_state()
    if not p.exists():
        return _empty_state()
    try:
        raw = json.loads(p.read_text(encoding="utf-8") or "{}")
    except Exception:
        return _empty_state()
    st = _empty_state()
    if isinstance(raw, dict):
        for k in _CATEGORIES:
            st[k] = _prune_entries(raw.get(k))
    return st


def _save_state_unlocked(state: dict[str, list[dict[str, str]]]) -> None:
    p = _state_file()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    out = {k: _prune_entries(state.get(k)) for k in _CATEGORIES}
    p.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")


def get_used_ids(category: str) -> list[str]:
    cat = (category or "").strip()
    if cat not in _CATEGORIES:
        return []
    with _lock:
        state = _load_state_unlocked()
        ids = [str(x.get("id") or "").strip() for x in state.get(cat, []) if str(x.get("id") or "").strip()]
        return list(dict.fromkeys(ids))


def mark_used(category: str, media_id: str) -> None:
    cat = (category or "").strip()
    mid = str(media_id or "").strip()
    if cat not in _CATEGORIES or not mid:
        return
    with _lock:
        state = _load_state_unlocked()
        rows = list(state.get(cat) or [])
        rows.append({"id": mid, "used_at": _now_iso()})
        state[cat] = _prune_entries(rows)
        try:
            _save_state_unlocked(state)
        except Exception:
            return


def reset_category(category: str) -> None:
    cat = (category or "").strip()
    if cat not in _CATEGORIES:
        return
    with _lock:
        state = _load_state_unlocked()
        state[cat] = []
        try:
            _save_state_unlocked(state)
        except Exception:
            return


def debug_state() -> dict:
    with _lock:
        state = _load_state_unlocked()
        return {
            "storage": "local_file",
            "path": USED_MEDIA_PATH,
            "state": state,
            "categories": list(_CATEGORIES),
        }
