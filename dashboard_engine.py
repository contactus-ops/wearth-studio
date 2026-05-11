import json
from pathlib import Path

from flask import jsonify, request

from ad_intelligence_engine import _decision_payload


ROOT = Path(__file__).resolve().parent
PENDING_PATH = ROOT / "pending_ads.json"


def _read_pending() -> list[dict]:
    if not PENDING_PATH.exists():
        return []
    try:
        data = json.loads(PENDING_PATH.read_text(encoding="utf-8") or "[]")
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _write_pending(rows: list[dict]) -> None:
    PENDING_PATH.write_text(json.dumps(rows, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


def ads_pending():
    rows = _read_pending()
    if request.method == "GET":
        active_rows = [r for r in rows if str(r.get("status") or "pending") not in {"rejected", "archived"}]
        return jsonify({"ok": True, "ads": active_rows})

    data = request.get_json(force=True, silent=True) or {}
    ad_id = str(data.get("ad_id") or "").strip()
    if not ad_id:
        return jsonify({"ok": False, "error": "ad_id required"}), 400
    existing = next((r for r in rows if str(r.get("ad_id")) == ad_id), None)
    if existing:
        existing.update(data)
    else:
        rows.append({**data, "status": data.get("status") or "pending"})
    _write_pending(rows)
    return jsonify({"ok": True, "ad_id": ad_id})


def ads_edit(ad_id: str):
    rows = _read_pending()
    data = request.get_json(force=True, silent=True) or {}
    for row in rows:
        if str(row.get("ad_id")) == str(ad_id):
            row.update({k: v for k, v in data.items() if k in {"headline", "body", "cta", "video_id", "creative_url"}})
            _write_pending(rows)
            return jsonify({"ok": True, "ad": row})
    return jsonify({"ok": False, "error": "ad not found"}), 404


def ads_set_status(ad_id: str, status: str):
    rows = _read_pending()
    for row in rows:
        if str(row.get("ad_id")) == str(ad_id):
            row["status"] = status
            _write_pending(rows)
            return jsonify({"ok": True, "ad_id": ad_id, "status": status})
    return jsonify({"ok": False, "error": "ad not found"}), 404


def ads_approve(ad_id: str):
    return ads_set_status(ad_id, "approved_pending_launch_gate")


def ads_reject(ad_id: str):
    return ads_set_status(ad_id, "rejected")


def ads_publish(ad_id: str):
    return jsonify({
        "ok": False,
        "error": "Direct dashboard publish is disabled. Launch requires parent creative judge and Meta brain budget gate.",
        "ad_id": ad_id,
    }), 403


def ads_feedback():
    rows = _read_pending()
    data = request.get_json(force=True, silent=True) or {}
    ad_id = str(data.get("ad_id") or "").strip()
    for row in rows:
        if str(row.get("ad_id")) == ad_id:
            row["feedback_worked"] = data.get("what_worked") or ""
            row["feedback_didnt"] = data.get("what_didnt_work") or ""
            _write_pending(rows)
            return jsonify({"ok": True, "ad_id": ad_id})
    return jsonify({"ok": False, "error": "ad not found"}), 404


def ads_improve_copy():
    data = request.get_json(force=True, silent=True) or {}
    field = str(data.get("field") or "headline")
    current = str(data.get("current_text") or "").strip()
    if field == "headline":
        variants = [
            "What you put on your skin matters.",
            "Your body knows polyester.",
            "The fabric upgrade you feel first.",
        ]
    elif field == "cta":
        variants = ["Shop now", "Feel the fabric", "Try WEARTH"]
    else:
        variants = [
            current or "Plant-based fabric that breathes with Indian heat. No synthetic scratch. No trapped heat.",
            "Made for women who notice what touches their skin. Soft, breathable, and built beyond polyester.",
            "Founder-led activewear for the women who stopped settling for plastic-feeling workout clothes.",
        ]
    return jsonify({"ok": True, "variants": variants})


def meta_adsets_live():
    decision = _decision_payload({"date_preset": "last_7d", "target_roas": 4.0, "min_spend_inr": 500}, request.args)
    http_status = int(decision.pop("http_status", 200))
    if http_status != 200 or not decision.get("ok"):
        return jsonify(decision), http_status
    cards = decision.get("scorecards") or []
    adsets = []
    for idx, card in enumerate(cards, start=1):
        adsets.append({
            "label": f"adset {idx}",
            "adset_id": card.get("adset_id"),
            "name": card.get("name"),
            "status": card.get("effective_status") or card.get("status"),
            "spend": card.get("spend_inr"),
            "spend_alltime": card.get("spend_inr"),
            "spend_today": None,
            "impressions_today": None,
            "clicks_today": None,
            "impressions_alltime": card.get("impressions"),
            "clicks_alltime": card.get("clicks"),
            "clicks": card.get("clicks"),
            "impressions": card.get("impressions"),
            "roas": card.get("roas"),
            "cpm": card.get("cpm_inr"),
            "cpc": card.get("cpc_inr"),
            "ads_manager_url": "https://adsmanager.facebook.com/adsmanager/manage/adsets?act=8979315238856807",
        })
    total_spend = sum(float(x.get("spend_inr") or 0) for x in cards)
    weighted_roas_values = [float(x.get("roas") or 0) for x in cards if x.get("roas") is not None]
    return jsonify({
        "ok": True,
        "insights_adset_alltime_preset": "last_7d",
        "insights_adset_today_preset": "not_loaded",
        "campaign": {"name": "WEARTH Meta campaign", "status": "ACTIVE", "effective_status": "ACTIVE"},
        "today_spend": None,
        "weekly_roas": round(sum(weighted_roas_values) / len(weighted_roas_values), 2) if weighted_roas_values else None,
        "active_ads_count": sum(1 for x in cards if x.get("is_active")),
        "adsets": adsets,
        "total_spend_last_7d": round(total_spend, 2),
    })


def meta_ad_live_creative():
    return jsonify({"ok": True, "headline": "", "body": "", "thumbnail_url": None, "video_id": None})


def meta_video_thumbnail():
    return jsonify({"ok": True, "thumbnail_url": None})
