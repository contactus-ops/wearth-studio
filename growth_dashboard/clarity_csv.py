# -*- coding: utf-8 -*-
"""Parse Microsoft Clarity session export CSV → Shopify Daily metrics."""
from __future__ import annotations

import csv
import io
import os
import re
from collections import Counter
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

# Clarity export preamble rows before the session table.
_SESSION_HEADER_MARKERS = ("Clarity user ID", "Entry URL", "Session duration")

# Paid traffic: Meta / Instagram ads (matches wearth-intro + daily reviews).
_PAID_RE = re.compile(
    r"utm_medium=paid|fbclid=|utm_source=(?:facebook|fb|ig|instagram)|campaign_id=",
    re.I,
)

# Bounce proxy: very short engagement (Clarity has no explicit bounce flag in export).
_BOUNCE_MAX_SECONDS = 10

_DEEP_MIN_SECONDS = 60

_DURATION_RE = re.compile(r"(?:(\d+):)?(\d{2}):(\d{2})")


def _parse_duration_seconds(raw: str) -> int:
    s = (raw or "").strip()
    if not s:
        return 0
    m = _DURATION_RE.match(s)
    if not m:
        return 0
    h = int(m.group(1) or 0)
    mi = int(m.group(2))
    sec = int(m.group(3))
    return h * 3600 + mi * 60 + sec


def _is_paid_session(row: dict[str, str]) -> bool:
    entry = (row.get("Entry URL") or row.get("Entry URL ") or "").strip()
    ref = (row.get("Referrer:") or row.get("Referrer") or "").strip()
    blob = f"{entry} {ref}"
    return bool(_PAID_RE.search(blob))


def _path_key(url: str) -> str:
    u = (url or "").strip()
    if not u:
        return ""
    try:
        p = urlparse(u)
        path = p.path or "/"
        if p.query:
            return f"{path}?{p.query[:80]}"
        return path
    except Exception:
        return u[:120]


def _exclude_user_ids(rows: list[dict[str, str]]) -> frozenset[str]:
    explicit = (os.environ.get("CLARITY_EXCLUDE_USER_IDS") or "").strip()
    out: set[str] = {x.strip() for x in explicit.split(",") if x.strip()}
    by_user: dict[str, list[dict[str, str]]] = {}
    for r in rows:
        uid = (r.get("Clarity user ID") or "").strip()
        if uid:
            by_user.setdefault(uid, []).append(r)
    # Repeat visitors with no paid sessions in the export → treat as internal (Abhi QA).
    for uid, sessions in by_user.items():
        if len(sessions) < 2:
            continue
        if not any(_is_paid_session(s) for s in sessions):
            out.add(uid)
    return frozenset(out)


def _find_session_header_line(text: str) -> int:
    for i, line in enumerate(text.splitlines()):
        if "Clarity user ID" in line and "Entry URL" in line:
            return i
    raise ValueError("Clarity CSV: session table header not found")


def parse_clarity_export_csv(text: str) -> dict[str, Any]:
    """
    Parse Clarity recordings export (100-session format).
    Returns aggregate metrics for paid visitor sessions after exclusions.
    """
    header_idx = _find_session_header_line(text)
    reader = csv.DictReader(io.StringIO("\n".join(text.splitlines()[header_idx:])))
    all_rows = [dict(r) for r in reader if any((v or "").strip() for v in r.values())]

    exclude = _exclude_user_ids(all_rows)
    sessions: list[dict[str, Any]] = []
    for r in all_rows:
        uid = (r.get("Clarity user ID") or "").strip()
        if uid and uid in exclude:
            continue
        if not _is_paid_session(r):
            continue
        dur = _parse_duration_seconds(r.get("Session duration") or "")
        country = (r.get("Country") or "").strip()
        sessions.append(
            {
                "user_id": uid,
                "duration_sec": dur,
                "entry": _path_key(r.get("Entry URL") or ""),
                "exit": _path_key(r.get("Exit URL") or ""),
                "country": country,
                "clicks": int((r.get("Session clicks") or "0").strip() or 0),
                "date": (r.get("Date") or "").strip(),
            }
        )

    n = len(sessions)
    if n == 0:
        return {
            "sessions": 0,
            "unique_visitors": 0,
            "bounce_rate": "",
            "avg_duration_sec": "",
            "deep_sessions_60s_plus": 0,
            "india_sessions": 0,
            "non_india_sessions": 0,
            "top_5_landing_pages": "",
            "top_5_exit_pages": "",
            "excluded_user_ids": sorted(exclude),
            "raw_total_rows": len(all_rows),
            "report_date": "",
        }

    visitors = len({s["user_id"] for s in sessions if s["user_id"]})
    bounces = sum(
        1
        for s in sessions
        if s["duration_sec"] < _BOUNCE_MAX_SECONDS or (s["duration_sec"] < 15 and s["clicks"] == 0)
    )
    deep = sum(1 for s in sessions if s["duration_sec"] >= _DEEP_MIN_SECONDS)
    india = sum(1 for s in sessions if s["country"].lower() == "india")
    avg_dur = round(sum(s["duration_sec"] for s in sessions) / n, 1)

    land = Counter(s["entry"] for s in sessions if s["entry"])
    ex = Counter(s["exit"] for s in sessions if s["exit"])
    top_land = "; ".join(f"{p} ({c})" for p, c in land.most_common(5))
    top_exit = "; ".join(f"{p} ({c})" for p, c in ex.most_common(5))

    dates = [s["date"] for s in sessions if s["date"]]
    report_date = max(dates) if dates else ""

    return {
        "sessions": n,
        "unique_visitors": visitors,
        "bounce_rate": round(100.0 * bounces / n, 1),
        "avg_duration_sec": avg_dur,
        "deep_sessions_60s_plus": deep,
        "india_sessions": india,
        "non_india_sessions": n - india,
        "top_5_landing_pages": top_land,
        "top_5_exit_pages": top_exit,
        "excluded_user_ids": sorted(exclude),
        "raw_total_rows": len(all_rows),
        "report_date": report_date,
    }


def clarity_date_to_iso(raw: str) -> str:
    """Clarity export uses MM/DD/YYYY."""
    s = (raw or "").strip()
    if not s:
        return ""
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return ""


def merge_clarity_into_shopify_report(shopify: dict[str, Any], clarity: dict[str, Any]) -> dict[str, Any]:
    """Overlay Clarity session metrics onto Shopify daily row (orders fields preserved)."""
    out = dict(shopify)
    if clarity.get("sessions"):
        out["sessions"] = clarity["sessions"]
        out["unique_visitors"] = clarity.get("unique_visitors", "")
        out["bounce_rate"] = clarity.get("bounce_rate", "")
        if clarity.get("top_5_landing_pages"):
            out["top_5_landing_pages"] = clarity["top_5_landing_pages"]
        if clarity.get("top_5_exit_pages"):
            out["top_5_exit_pages"] = clarity["top_5_exit_pages"]
    note = out.get("data_source_note") or ""
    extra = (
        f"clarity_csv:sessions={clarity.get('sessions')}"
        f",bounce={clarity.get('bounce_rate')}%"
        f",avg_dur={clarity.get('avg_duration_sec')}s"
        f",deep60={clarity.get('deep_sessions_60s_plus')}"
        f",IN={clarity.get('india_sessions')}"
        f",nonIN={clarity.get('non_india_sessions')}"
    )
    out["data_source_note"] = f"{note} | {extra}".strip(" |")
    return out
