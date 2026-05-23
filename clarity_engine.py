"""
Microsoft Clarity Data Export API — ad-hoc insights, morning sweep, daily digest.
"""
from __future__ import annotations

import html
import json
import logging
import os
import re
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
from flask import jsonify, request

logger = logging.getLogger(__name__)

CLARITY_API_URL = "https://www.clarity.ms/export-data/api/v1/project-live-insights"
CACHE_PATH = Path(os.environ.get("CLARITY_CACHE_PATH", "/tmp/clarity_cache.json"))
STATE_PATH = Path(os.environ.get("CLARITY_STATE_PATH", "/tmp/clarity_state.json"))
REPORTS_DIR = Path(os.environ.get("CLARITY_REPORTS_DIR", "reports/clarity"))
CACHE_TTL_SECONDS = 4 * 60 * 60
SWEEP_PAUSE_SECONDS = 2
MAX_DAILY_API_CALLS = 10
SWEEP_CALL_COUNT = 7

VALID_DIMENSIONS = frozenset(
    {"URL", "Referrer", "Device", "Country", "Browser", "OS", "Source", "Medium", "Campaign", "Channel"}
)

SWEEP_SLICES: list[tuple[str, dict[str, str]]] = [
    ("baseline_24h", {"numOfDays": "1"}),
    ("by_referrer", {"numOfDays": "1", "dimension1": "Referrer"}),
    ("by_device", {"numOfDays": "1", "dimension1": "Device"}),
    ("by_url", {"numOfDays": "1", "dimension1": "URL"}),
    ("referrer_x_url", {"numOfDays": "1", "dimension1": "Referrer", "dimension2": "URL"}),
    ("device_x_url", {"numOfDays": "1", "dimension1": "Device", "dimension2": "URL"}),
    ("by_country", {"numOfDays": "1", "dimension1": "Country"}),
]

_TOKEN_RE = re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]+", re.I)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _today_utc() -> str:
    return _utc_now().date().isoformat()


def _iso(dt: datetime | None = None) -> str:
    return (dt or _utc_now()).replace(microsecond=0).isoformat()


def _redact(text: str) -> str:
    if not text:
        return text
    return _TOKEN_RE.sub(r"\1[REDACTED]", str(text))


def _token() -> str:
    return (os.environ.get("CLARITY_API_TOKEN") or "").strip()


def _digest_recipient() -> str:
    return (os.environ.get("CLARITY_DIGEST_RECIPIENT") or "contactus@wearthactive.com").strip()


def _admin_token() -> str:
    return (
        os.environ.get("ADMIN_TOKEN")
        or os.environ.get("WEARTH_N8N_MAIL_TOKEN")
        or ""
    ).strip()


def _n8n_digest_webhook_url() -> str:
    explicit = (os.environ.get("N8N_CLARITY_DIGEST_WEBHOOK_URL") or "").strip()
    if explicit:
        return explicit
    base = (os.environ.get("N8N_BASE_URL") or "https://wearthactive.app.n8n.cloud").rstrip("/")
    path = (os.environ.get("N8N_CLARITY_DIGEST_WEBHOOK_PATH") or "wearth-clarity-digest").strip("/")
    return f"{base}/webhook/{path}"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _load_state() -> dict[str, Any]:
    state = _read_json(STATE_PATH)
    if state.get("day") != _today_utc():
        state = {
            "day": _today_utc(),
            "calls_today": 0,
            "last_call_at": None,
            "sweep_ran": False,
            "sweep_date": None,
        }
    return state


def _save_state(state: dict[str, Any]) -> None:
    state["day"] = _today_utc()
    _write_json(STATE_PATH, state)


def _record_api_call(state: dict[str, Any]) -> None:
    state["calls_today"] = int(state.get("calls_today") or 0) + 1
    state["last_call_at"] = _iso()
    _save_state(state)


def _cache_signature(params: dict[str, str]) -> str:
    items = sorted((k, v) for k, v in params.items() if v)
    return json.dumps(items, sort_keys=True)


def _load_cache() -> dict[str, Any]:
    return _read_json(CACHE_PATH)


def _save_cache(cache: dict[str, Any]) -> None:
    _write_json(CACHE_PATH, cache)


def _num(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return 0.0


def _call_clarity(params: dict[str, str], *, state: dict[str, Any] | None = None) -> tuple[int, Any]:
    token = _token()
    if not token:
        return 503, {"error": "CLARITY_API_TOKEN is not configured"}

    if int((state or _load_state()).get("calls_today") or 0) >= MAX_DAILY_API_CALLS:
        return 429, {"error": "Daily Clarity API limit reached (10 calls/day)"}

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    try:
        resp = requests.get(CLARITY_API_URL, params=params, headers=headers, timeout=120)
    except requests.RequestException as exc:
        logger.error("Clarity request failed: %s", _redact(str(exc)))
        return 502, {"error": str(exc)}

    st = state if state is not None else _load_state()
    _record_api_call(st)

    body_text = resp.text or ""
    if resp.status_code >= 400:
        logger.warning(
            "Clarity upstream %s params=%s body=%s",
            resp.status_code,
            params,
            _redact(body_text[:500]),
        )
        return 502, body_text

    try:
        return 200, resp.json()
    except ValueError:
        return 502, body_text


def fetch_clarity_insights(
    params: dict[str, str],
    *,
    use_cache: bool = True,
    state: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any]]:
    """Return (http_status, envelope_dict)."""
    sig = _cache_signature(params)
    if use_cache:
        cache = _load_cache()
        entry = cache.get(sig)
        if isinstance(entry, dict):
            fetched_at = entry.get("fetched_at")
            if fetched_at:
                try:
                    ts = datetime.fromisoformat(str(fetched_at).replace("Z", "+00:00"))
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    age = (_utc_now() - ts.astimezone(timezone.utc)).total_seconds()
                    if age < CACHE_TTL_SECONDS:
                        return 200, {
                            "cached": True,
                            "fetched_at": fetched_at,
                            "data": entry.get("data"),
                        }
                except Exception:
                    pass

    status, payload = _call_clarity(params, state=state)
    if status != 200:
        return status, {"error": payload if isinstance(payload, str) else payload}

    fetched_at = _iso()
    if use_cache:
        cache = _load_cache()
        cache[sig] = {"fetched_at": fetched_at, "data": payload}
        _save_cache(cache)

    return 200, {"cached": False, "fetched_at": fetched_at, "data": payload}


def _metric_map(payload: Any) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    if not isinstance(payload, list):
        return out
    for block in payload:
        if not isinstance(block, dict):
            continue
        name = str(block.get("metricName") or "").strip()
        info = block.get("information")
        if name and isinstance(info, list):
            out[name] = [row for row in info if isinstance(row, dict)]
    return out


def _pick_dim(row: dict[str, Any], *candidates: str) -> str:
    for key in candidates:
        if key in row and row[key] not in (None, ""):
            return str(row[key])
    for key, val in row.items():
        if key in (
            "totalSessionCount",
            "totalBotSessionCount",
            "distantUserCount",
            "PagesPerSessionPercentage",
        ):
            continue
        if val not in (None, ""):
            return str(val)
    return "Unknown"


def _sessions_from_rows(rows: list[dict[str, Any]]) -> float:
    return sum(_num(r.get("totalSessionCount")) for r in rows)


def _pct(part: float, whole: float) -> float:
    if whole <= 0:
        return 0.0
    return 100.0 * part / whole


def _compare_pct(current: float, previous: float) -> str:
    if previous <= 0:
        return "no prior-day baseline saved yet"
    delta = ((current - previous) / previous) * 100.0
    direction = "up" if delta > 0 else "down"
    return f"{direction} {abs(delta):.0f}% from yesterday"


def _yesterday_raw_path(for_day: date) -> Path:
    prev = for_day - timedelta(days=1)
    return REPORTS_DIR / f"clarity_raw_{prev.isoformat()}.json"


def _load_yesterday_baseline(for_day: date) -> dict[str, Any] | None:
    path = _yesterday_raw_path(for_day)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        base = data.get("baseline_24h")
        return base if isinstance(base, list) else None
    except Exception:
        return None


def _headline_metrics(baseline_payload: Any, yesterday_payload: Any | None) -> dict[str, float]:
    metrics = _metric_map(baseline_payload)
    traffic_rows = metrics.get("Traffic") or []
    sessions = _sessions_from_rows(traffic_rows)

    page_views = 0.0
    for name in ("Popular Pages", "Traffic"):
        for row in metrics.get(name) or []:
            page_views += _num(row.get("totalPageViewCount") or row.get("pageViewCount"))

    engagement_seconds = 0.0
    engagement_rows = metrics.get("Engagement Time") or metrics.get("Active time") or []
    if engagement_rows:
        total = sum(_num(r.get("activeTime") or r.get("engagementTime") or r.get("averageEngagementTime")) for r in engagement_rows)
        engagement_seconds = total / max(len(engagement_rows), 1)

    scroll = 0.0
    scroll_rows = metrics.get("Scroll Depth") or []
    if scroll_rows:
        scroll = sum(_num(r.get("scrollDepth") or r.get("averageScrollDepth")) for r in scroll_rows) / max(
            len(scroll_rows), 1
        )

    rage = 0.0
    rage_rows = metrics.get("Rage Click Count") or []
    if rage_rows:
        rage = sum(_num(r.get("rageClickCount") or r.get("totalRageClickCount")) for r in rage_rows)

    dead = 0.0
    dead_rows = metrics.get("Dead Click Count") or []
    if dead_rows:
        dead = sum(_num(r.get("deadClickCount") or r.get("totalDeadClickCount")) for r in dead_rows)

    js_errors = 0.0
    err_rows = metrics.get("Script Error Count") or metrics.get("Error Click Count") or []
    if err_rows:
        js_errors = sum(_num(r.get("scriptErrorCount") or r.get("errorCount")) for r in err_rows)

    prev_sessions = 0.0
    if yesterday_payload:
        prev_sessions = _sessions_from_rows(
            _metric_map(yesterday_payload).get("Traffic") or []
        )

    return {
        "sessions": sessions,
        "prev_sessions": prev_sessions,
        "page_views": page_views,
        "engagement_seconds": engagement_seconds,
        "scroll_depth": scroll,
        "rage_clicks": rage,
        "dead_clicks": dead,
        "js_errors": js_errors,
    }


def _rows_by_dimension(payload: Any, dim_names: tuple[str, ...]) -> list[tuple[str, dict[str, float]]]:
    metrics = _metric_map(payload)
    traffic = metrics.get("Traffic") or []
    engagement = { _pick_dim(r, *dim_names): r for r in (metrics.get("Engagement Time") or []) }
    scroll = { _pick_dim(r, *dim_names): r for r in (metrics.get("Scroll Depth") or []) }
    rage = { _pick_dim(r, *dim_names): r for r in (metrics.get("Rage Click Count") or []) }

    buckets: dict[str, dict[str, float]] = {}
    for row in traffic:
        label = _pick_dim(row, *dim_names)
        buckets.setdefault(label, {})
        buckets[label]["sessions"] = buckets[label].get("sessions", 0.0) + _num(row.get("totalSessionCount"))

    for label, row in engagement.items():
        buckets.setdefault(label, {})
        buckets[label]["engagement"] = _num(row.get("activeTime") or row.get("engagementTime"))

    for label, row in scroll.items():
        buckets.setdefault(label, {})
        buckets[label]["scroll"] = _num(row.get("scrollDepth") or row.get("averageScrollDepth"))

    for label, row in rage.items():
        buckets.setdefault(label, {})
        buckets[label]["rage"] = _num(row.get("rageClickCount") or row.get("totalRageClickCount"))

    ranked = sorted(buckets.items(), key=lambda x: x[1].get("sessions", 0.0), reverse=True)
    return ranked


def _cross_dimension_narrative(payload: Any, dim1: str, dim2: str, *, top_n: int = 3) -> list[str]:
    metrics = _metric_map(payload)
    traffic = metrics.get("Traffic") or []
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in traffic:
        a = _pick_dim(row, dim1, dim1.replace(" ", ""))
        b = _pick_dim(row, dim2, dim2.replace(" ", ""), "URL")
        key = f"{a} → {b}"
        groups.setdefault(key, []).append(row)

    ranked = sorted(
        groups.items(),
        key=lambda kv: sum(_num(r.get("totalSessionCount")) for r in kv[1]),
        reverse=True,
    )[: top_n * 4]

    lines: list[str] = []
    seen_primary: set[str] = set()
    for key, rows in ranked:
        primary = key.split(" → ", 1)[0]
        if primary not in seen_primary and len(seen_primary) >= top_n:
            continue
        seen_primary.add(primary)
        sessions = sum(_num(r.get("totalSessionCount")) for r in rows)
        if sessions <= 0:
            continue
        scroll_vals = [_num(r.get("scrollDepth") or r.get("averageScrollDepth")) for r in rows]
        avg_scroll = sum(scroll_vals) / max(len(scroll_vals), 1)
        lines.append(
            f"{key}: {int(sessions)} sessions, scroll depth about {avg_scroll:.0f}%."
        )
    return lines


def generate_clarity_markdown_report(snapshot: dict[str, Any], report_day: date) -> str:
    day_str = report_day.isoformat()
    baseline = snapshot.get("baseline_24h")
    yesterday = _load_yesterday_baseline(report_day)
    h = _headline_metrics(baseline, yesterday)

    session_cmp = _compare_pct(h["sessions"], h["prev_sessions"])
    rage_rate = _pct(h["rage_clicks"], max(h["sessions"], 1))
    lines: list[str] = [
        f"# Clarity daily report — {day_str}",
        "",
        "## Headline numbers",
        "",
    ]

    lines.append(
        f"**Sessions:** {int(h['sessions'])} ({session_cmp}). "
        f"Roughly {int(h['page_views'])} page views in the last 24 hours."
    )
    lines.append(
        f"**Engagement:** average active time about {h['engagement_seconds']:.0f}s per segment — "
        "longer is usually healthier on product and story pages."
    )
    lines.append(
        f"**Scroll depth:** {h['scroll_depth']:.0f}% on average — "
        "below 30% on key landing pages means most visitors never see the offer."
    )
    lines.append(
        f"**Rage clicks:** {rage_rate:.1f}% of session-weighted signal ({int(h['rage_clicks'])} events) — "
        "anything sustained above 5% deserves a UX check."
    )
    lines.append(
        f"**Dead clicks:** {int(h['dead_clicks'])} — often a broken button or overlay blocking taps."
    )
    lines.append(
        f"**JS errors:** {int(h['js_errors'])} — watch for spikes after theme or app deploys."
    )
    lines.append("")

    # By referrer
    lines.append("## By referrer")
    lines.append("")
    ref_rows = _rows_by_dimension(snapshot.get("by_referrer"), ("Referrer", "Referrer URL", "Source"))
    if not ref_rows:
        err = snapshot.get("by_referrer")
        if isinstance(err, dict) and err.get("error"):
            lines.append(f"Referrer breakdown unavailable ({err.get('error')}).")
        else:
            lines.append("Referrer breakdown unavailable.")
    else:
        top3 = ref_rows[:3]
        for label, stats in top3:
            lines.append(
                f"- **{label}:** {int(stats.get('sessions', 0))} sessions, "
                f"engagement {stats.get('engagement', 0):.0f}s, scroll {stats.get('scroll', 0):.0f}%."
            )
        labels = [x[0].lower() for x in ref_rows[:8]]
        ig = any("instagram" in x for x in labels)
        fb = any("facebook" in x for x in labels)
        if ig and fb:
            ig_sess = next((s.get("sessions", 0) for l, s in ref_rows if "instagram" in l.lower()), 0)
            fb_sess = next((s.get("sessions", 0) for l, s in ref_rows if "facebook" in l.lower()), 0)
            if ig_sess >= fb_sess * 1.2:
                lines.append(
                    "Instagram is sending more sessions than Facebook right now. "
                    "Compare landing scroll on the top IG landing URLs — social traffic often bounces when the hero loads slowly on mobile."
                )
            elif fb_sess >= ig_sess * 1.2:
                lines.append(
                    "Facebook is outperforming Instagram on session volume. "
                    "Check whether FB visitors reach product pages or stall on the homepage — paid/social audiences behave differently on depth metrics."
                )
            else:
                lines.append(
                    "Instagram and Facebook are both meaningful referrers today. "
                    "Split landing-page performance by source before changing ad spend."
                )
        else:
            lines.append(
                f"Top source is **{top3[0][0]}** with {int(top3[0][1].get('sessions', 0))} sessions — "
                "prioritise UX on the pages that source sends to most."
            )
    lines.append("")

    # By device
    lines.append("## By device")
    lines.append("")
    dev_rows = _rows_by_dimension(snapshot.get("by_device"), ("Device", "OS"))
    if dev_rows:
        worst_scroll = min(dev_rows, key=lambda x: x[1].get("scroll", 999))
        best_scroll = max(dev_rows, key=lambda x: x[1].get("scroll", 0))
        for label, stats in dev_rows[:5]:
            lines.append(
                f"- **{label}:** {int(stats.get('sessions', 0))} sessions, scroll {stats.get('scroll', 0):.0f}%, "
                f"rage signal {stats.get('rage', 0):.0f}."
            )
        w_scroll = worst_scroll[1].get("scroll", 0) or 0.01
        b_scroll = best_scroll[1].get("scroll", 0)
        if b_scroll >= 2 * w_scroll:
            lines.append(
                f"**{best_scroll[0]}** scroll depth is more than 2× **{worst_scroll[0]}** — "
                "treat that as a likely layout or performance bug on the weaker device, not audience preference."
            )
        ios = next((s for l, s in dev_rows if "ios" in l.lower() or "iphone" in l.lower()), None)
        android = next((s for l, s in dev_rows if "android" in l.lower()), None)
        desktop = next((s for l, s in dev_rows if "desktop" in l.lower() or "pc" in l.lower()), None)
        if ios and android:
            lines.append(
                f"iOS ({int(ios.get('sessions', 0))} sessions) vs Android ({int(android.get('sessions', 0))} sessions) — "
                "compare the same product URLs on both; mismatched scroll usually means mobile CSS or image weight."
            )
        elif desktop and (ios or android):
            mob = ios or android
            lines.append(
                f"Desktop ({int(desktop.get('sessions', 0))}) vs mobile ({int(mob.get('sessions', 0))}) split is visible — "
                "ensure checkout and size selectors work on the dominant mobile OS."
            )
    else:
        lines.append("Device breakdown unavailable.")
    lines.append("")

    # By page
    lines.append("## By page")
    lines.append("")
    url_rows = _rows_by_dimension(snapshot.get("by_url"), ("URL",))
    flagged: list[str] = []
    for label, stats in url_rows[:5]:
        scroll = stats.get("scroll", 0)
        rage = stats.get("rage", 0)
        sess = int(stats.get("sessions", 0))
        flag_parts = []
        if scroll and scroll < 30:
            flag_parts.append("low scroll")
        rage_rate_page = _pct(rage, max(sess, 1))
        if rage_rate_page > 7:
            flag_parts.append("high rage")
        flag_txt = f" ⚠ {', '.join(flag_parts)}" if flag_parts else ""
        if flag_parts:
            flagged.append(label)
        lines.append(
            f"- **{label}** — {sess} sessions, scroll {scroll:.0f}%, rage rate ~{rage_rate_page:.1f}%{flag_txt}."
        )
    if not url_rows:
        lines.append("No URL-level traffic in the export.")
    lines.append("")

    # Referrer x page
    lines.append("## Referrer x page")
    lines.append("")
    rx = _cross_dimension_narrative(snapshot.get("referrer_x_url"), "Referrer", "URL")
    if rx:
        lines.append(
            "Cross-traffic patterns (where a referrer lands and how deep users scroll):"
        )
        lines.append("")
        for item in rx[:6]:
            lines.append(f"- {item}")
        lines.append("")
        lines.append(
            "Watch for social visitors who land on a product URL but show shallow scroll — "
            "that often means ad creative promised something the page does not deliver above the fold. "
            "Deep scroll without add-to-cart on the same URL may be research traffic; pair with Clarity recordings for those sessions."
        )
    else:
        lines.append("Referrer × URL cross-tab did not return usable rows today.")
    lines.append("")

    # Device x page
    lines.append("## Device x page")
    lines.append("")
    dx = _cross_dimension_narrative(snapshot.get("device_x_url"), "Device", "URL")
    if dx:
        for item in dx[:6]:
            lines.append(f"- {item}")
        lines.append("")
        lines.append(
            "When one device shows much worse scroll on the same URL, suspect responsive layout, "
            "sticky bars covering CTAs, or heavier images on that OS — fix before optimising copy."
        )
    else:
        lines.append("Device × URL cross-tab did not return usable rows today.")
    lines.append("")

    # Country
    lines.append("## Country sanity check")
    lines.append("")
    country_rows = _rows_by_dimension(snapshot.get("by_country"), ("Country", "Country/Region"))
    if country_rows:
        top = country_rows[0]
        india = next((c for c in country_rows if "india" in c[0].lower()), None)
        if india and india[0] == top[0]:
            lines.append(
                f"India is the dominant traffic source ({int(india[1].get('sessions', 0))} sessions), as expected for this store. "
                "No geo anomaly flagged."
            )
        elif india:
            lines.append(
                f"India has {int(india[1].get('sessions', 0))} sessions but **{top[0]}** leads with "
                f"{int(top[1].get('sessions', 0))} — worth confirming ads/geo targeting if unintended."
            )
        else:
            lines.append(
                f"Top country is **{top[0]}** ({int(top[1].get('sessions', 0))} sessions) and India is not in the top slice — "
                "double-check campaign geography."
            )
    else:
        lines.append("Country breakdown unavailable.")
    lines.append("")

    lines.append("## Three things worth investigating today")
    lines.append("")
    investigations: list[str] = []
    if rage_rate > 5:
        investigations.append(
            f"Site-wide rage-click rate is {rage_rate:.1f}%. "
            "That pattern usually means frustrated tapping on non-clickable elements or slow UI — review recordings on the busiest URLs first."
        )
    if flagged:
        investigations.append(
            f"Pages flagged for low scroll or high rage: {', '.join(flagged[:3])}. "
            "These URLs are leaking attention before the offer — test hero load and CTA visibility on mobile."
        )
    if dev_rows and len(dev_rows) >= 2:
        worst = min(dev_rows, key=lambda x: x[1].get("scroll", 999))
        best = max(dev_rows, key=lambda x: x[1].get("scroll", 0))
        if (best[1].get("scroll", 0) or 0) >= 2 * (worst[1].get("scroll", 0) or 0.01):
            investigations.append(
                f"Scroll on **{worst[0]}** lags **{best[0]}** by more than 2×. "
                "Device-specific breakage is more likely than content quality — reproduce on a real device."
            )
    if h["js_errors"] > 0:
        investigations.append(
            f"There were {int(h['js_errors'])} script errors in the window. "
            "Even small JS faults can break add-to-cart on certain browsers — check the browser console on top pages."
        )
    if len(investigations) < 3 and url_rows:
        investigations.append(
            f"**{url_rows[0][0]}** is the top page by sessions ({int(url_rows[0][1].get('sessions', 0))}). "
            "Make sure its LCP image and variant picker match the traffic source sending users there."
        )
    fallbacks = [
        (
            "Session volume is low or missing in today's export — confirm the Clarity Data Export token is valid and the daily API quota has not been exhausted. "
            "Without a successful baseline call, treat this digest as a wiring check only."
        ),
        (
            "Open Clarity's dashboard for the last 24 hours and compare session count to this email once the API responds again. "
            "That sanity check catches token expiry before you rely on automation."
        ),
        (
            "When API data returns, prioritise recordings on the homepage and the top product URL from paid social. "
            "Qualitative review still catches issues aggregates miss."
        ),
    ]
    while len(investigations) < 3:
        investigations.append(fallbacks[len(investigations) % len(fallbacks)])
    for item in investigations[:3]:
        lines.append(f"- {item}")
    lines.append("")

    return "\n".join(lines)


def _markdown_to_html(md: str) -> str:
    parts: list[str] = []
    in_list = False
    for raw in md.splitlines():
        line = raw.rstrip()
        if line.startswith("# "):
            if in_list:
                parts.append("</ul>")
                in_list = False
            parts.append(f"<h1>{html.escape(line[2:].strip())}</h1>")
        elif line.startswith("## "):
            if in_list:
                parts.append("</ul>")
                in_list = False
            parts.append(f"<h2>{html.escape(line[3:].strip())}</h2>")
        elif line.startswith("- "):
            if not in_list:
                parts.append("<ul>")
                in_list = True
            text = line[2:].strip()
            text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html.escape(text))
            # unescape strong tags
            text = text.replace("&lt;strong&gt;", "<strong>").replace("&lt;/strong&gt;", "</strong>")
            parts.append(f"<li>{text}</li>")
        elif not line.strip():
            if in_list:
                parts.append("</ul>")
                in_list = False
            parts.append("<br/>")
        else:
            if in_list:
                parts.append("</ul>")
                in_list = False
            text = html.escape(line)
            text = re.sub(r"\*\*(.+?)\*\*", lambda m: f"<strong>{html.escape(m.group(1))}</strong>", line)
            parts.append(f"<p>{text}</p>")
    if in_list:
        parts.append("</ul>")
    body = "\n".join(parts)
    return f"<html><body style='font-family:Georgia,serif;line-height:1.5;color:#1a1714'>{body}</body></html>"


def _send_digest_email_via_n8n(subject: str, markdown_body: str) -> dict[str, Any]:
    url = _n8n_digest_webhook_url()
    payload = {
        "to": _digest_recipient(),
        "subject": subject,
        "text": markdown_body,
        "html": _markdown_to_html(markdown_body),
    }
    try:
        resp = requests.post(url, json=payload, timeout=60)
        ok = 200 <= resp.status_code < 300
        return {
            "ok": ok,
            "http_status": resp.status_code,
            "webhook": _redact(url),
            "body_preview": _redact((resp.text or "")[:300]),
        }
    except requests.RequestException as exc:
        logger.error("n8n clarity digest webhook failed: %s", _redact(str(exc)))
        return {"ok": False, "error": _redact(str(exc)), "webhook": _redact(url)}


def clarity_morning_sweep(*, force: bool = False) -> dict[str, Any]:
    report_day = _utc_now().date()
    day_str = report_day.isoformat()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = REPORTS_DIR / f"clarity_raw_{day_str}.json"
    md_path = REPORTS_DIR / f"clarity_daily_{day_str}.md"

    state = _load_state()
    if state.get("sweep_ran") and state.get("sweep_date") == day_str and not force:
        return {
            "ok": True,
            "skipped": True,
            "reason": "sweep already ran today",
            "raw_path": str(raw_path),
            "markdown_path": str(md_path) if md_path.exists() else None,
        }

    if not _token():
        return {"ok": False, "error": "CLARITY_API_TOKEN is not configured"}

    remaining = MAX_DAILY_API_CALLS - int(state.get("calls_today") or 0)
    if remaining < SWEEP_CALL_COUNT:
        return {
            "ok": False,
            "error": f"Not enough Clarity quota left today ({remaining} remaining, need {SWEEP_CALL_COUNT})",
        }

    snapshot: dict[str, Any] = {
        "generated_at": _iso(),
        "report_day": day_str,
        "slices": {},
    }

    for idx, (label, params) in enumerate(SWEEP_SLICES):
        if idx > 0:
            time.sleep(SWEEP_PAUSE_SECONDS)
        logger.info("Clarity sweep start label=%s params=%s", label, params)
        status, payload = _call_clarity(params, state=state)
        if status == 200:
            snapshot[label] = payload
            logger.info("Clarity sweep finish label=%s status=200", label)
        else:
            err_body = payload if isinstance(payload, str) else json.dumps(payload)
            snapshot[label] = {"error": f"{status}: {err_body[:500]}"}
            logger.warning("Clarity sweep finish label=%s status=%s", label, status)

    raw_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    markdown = generate_clarity_markdown_report(snapshot, report_day)
    md_path.write_text(markdown, encoding="utf-8")

    state["sweep_ran"] = True
    state["sweep_date"] = day_str
    _save_state(state)

    subject = f"Wearth Clarity — {day_str}"
    email_result = _send_digest_email_via_n8n(subject, markdown)

    return {
        "ok": True,
        "raw_path": str(raw_path),
        "markdown_path": str(md_path),
        "email": email_result,
        "calls_today": state.get("calls_today"),
    }


def clarity_insights():
    try:
        num_days = int(request.args.get("numOfDays", 1))
    except (TypeError, ValueError):
        return jsonify({"error": "numOfDays must be an integer"}), 400
    if num_days not in (1, 2, 3):
        return jsonify({"error": "numOfDays must be 1, 2, or 3"}), 400

    params: dict[str, str] = {"numOfDays": str(num_days)}
    for dim_key in ("dimension1", "dimension2", "dimension3"):
        val = (request.args.get(dim_key) or "").strip()
        if val:
            if val not in VALID_DIMENSIONS:
                return jsonify({"error": f"Invalid {dim_key}: {val}"}), 400
            params[dim_key] = val

    status, envelope = fetch_clarity_insights(params, use_cache=True)
    if status == 502:
        return jsonify({"error": "Clarity upstream error", "upstream": envelope}), 502
    if status == 503:
        return jsonify(envelope), 503
    if status == 429:
        return jsonify(envelope), 429
    return jsonify(envelope), status


def clarity_health():
    state = _load_state()
    cache = _load_cache()
    return jsonify(
        {
            "token_present": bool(_token()),
            "last_call_at": state.get("last_call_at"),
            "calls_today": int(state.get("calls_today") or 0),
            "cache_entries": len(cache),
            "sweep_ran_today": bool(state.get("sweep_ran") and state.get("sweep_date") == _today_utc()),
        }
    )


def clarity_sweep_now():
    expected = _admin_token()
    if not expected:
        return jsonify({"ok": False, "error": "ADMIN_TOKEN is not configured on server"}), 503
    provided = (request.headers.get("X-Wearth-Admin") or "").strip()
    if provided != expected:
        return jsonify({"ok": False, "error": "Unauthorized"}), 401

    force = (request.args.get("force") or "").strip().lower() in ("1", "true", "yes")
    result = clarity_morning_sweep(force=force)
    code = 200 if result.get("ok") else 500
    if result.get("error") == "CLARITY_API_TOKEN is not configured":
        code = 503
    return jsonify(result), code
