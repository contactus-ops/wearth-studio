import json
from pathlib import Path

import requests
from flask import jsonify, request

from ad_intelligence_engine import (
    GRAPH,
    INSIGHT_FIELDS,
    META_CAMPAIGN_ID,
    _decision_payload,
    _float,
    _get_json,
    _h,
    _insight_for_object,
    _purchase_count,
    _purchase_value,
    _roas_from_insight,
)


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


def _metric_card_from_insight(row: dict) -> dict:
    spend = _float(row.get("spend"))
    clicks = _float(row.get("clicks"))
    impressions = _float(row.get("impressions"))
    purchases = _purchase_count(row.get("actions"))
    purchase_value = _purchase_value(row.get("action_values"))
    return {
        "spend_inr": round(spend, 2),
        "impressions": int(impressions),
        "clicks": int(clicks),
        "ctr": round(_float(row.get("ctr")), 3) if row.get("ctr") is not None else None,
        "cpc_inr": round(_float(row.get("cpc")), 2) if row.get("cpc") is not None else None,
        "cpm_inr": round(_float(row.get("cpm")), 2) if row.get("cpm") is not None else None,
        "purchases": int(purchases),
        "purchase_value_inr": round(purchase_value, 2) if purchase_value else None,
        "roas": _roas_from_insight(row, spend, purchase_value),
    }


def _creative_summary(creative: dict | None) -> dict:
    creative = creative or {}
    story = creative.get("object_story_spec") or {}
    link_data = story.get("link_data") or {}
    video_data = story.get("video_data") or {}
    title = creative.get("title") or link_data.get("name") or video_data.get("title") or ""
    body = creative.get("body") or link_data.get("message") or video_data.get("message") or ""
    return {
        "id": creative.get("id"),
        "name": creative.get("name"),
        "title": title,
        "body": body,
        "thumbnail_url": creative.get("thumbnail_url") or video_data.get("image_url") or link_data.get("picture"),
        "image_url": creative.get("image_url") or link_data.get("picture"),
        "video_id": creative.get("video_id") or video_data.get("video_id"),
        "object_story_spec": story,
    }


def _ads_for_adset(adset_id: str, date_preset: str) -> tuple[list[dict], list[dict]]:
    fields = (
        "id,name,status,effective_status,created_time,updated_time,"
        "creative{id,name,title,body,thumbnail_url,image_url,video_id,object_story_spec}"
    )
    data, err, http = _get_json(f"{GRAPH}/{adset_id}/ads", {"fields": fields, "limit": 100}, timeout=60)
    if err:
        return [], [{"step": "adset_ads", "adset_id": adset_id, "http": http, "error": err}]
    errors = []
    ads = []
    for ad in data.get("data") or []:
        insight, insight_err = _insight_for_object(str(ad.get("id")), date_preset)
        if insight_err:
            errors.append({"step": "ad_insight", **insight_err})
        ads.append({
            "id": ad.get("id"),
            "name": ad.get("name"),
            "status": ad.get("status"),
            "effective_status": ad.get("effective_status"),
            "created_time": ad.get("created_time"),
            "updated_time": ad.get("updated_time"),
            "creative": _creative_summary(ad.get("creative")),
            "metrics": _metric_card_from_insight(insight),
            "ads_manager_url": f"https://adsmanager.facebook.com/adsmanager/manage/ads/edit?act=8979315238856807&selected_ad_ids={ad.get('id')}",
        })
    return ads, errors


def meta_campaign_dashboard():
    campaign_id = (request.args.get("campaign_id") or META_CAMPAIGN_ID or "").strip()
    date_preset = (request.args.get("date_preset") or "last_7d").strip()
    decision = _decision_payload({"campaign_id": campaign_id, "date_preset": date_preset, "target_roas": 4.0, "min_spend_inr": 500}, request.args)
    http_status = int(decision.pop("http_status", 200))
    if http_status != 200 or not decision.get("ok"):
        return jsonify(decision), http_status

    campaign_data, campaign_err, campaign_http = _get_json(
        f"{GRAPH}/{campaign_id}",
        {"fields": "id,name,status,effective_status,daily_budget,lifetime_budget,buying_type,objective,created_time,updated_time"},
        timeout=60,
    )
    errors = list(decision.get("errors") or [])
    if campaign_err:
        errors.append({"step": "campaign", "http": campaign_http, "error": campaign_err})
        campaign_data = {"id": campaign_id, "name": "WEARTH Meta campaign"}

    scorecards = decision.get("scorecards") or []
    adsets = []
    totals = {
        "spend_inr": 0.0,
        "impressions": 0,
        "clicks": 0,
        "purchases": 0,
        "purchase_value_inr": 0.0,
        "active_ads": 0,
        "active_adsets": 0,
    }
    for card in scorecards:
        adset_id = str(card.get("adset_id") or "")
        ads, ad_errors = _ads_for_adset(adset_id, date_preset) if adset_id else ([], [])
        errors.extend(ad_errors)
        active_ads = sum(1 for ad in ads if str(ad.get("effective_status") or ad.get("status") or "").upper() == "ACTIVE")
        totals["spend_inr"] += float(card.get("spend_inr") or 0)
        totals["impressions"] += int(card.get("impressions") or 0)
        totals["clicks"] += int(card.get("clicks") or 0)
        totals["purchases"] += int(card.get("purchases") or 0)
        totals["purchase_value_inr"] += float(card.get("purchase_value_inr") or 0)
        totals["active_ads"] += active_ads
        totals["active_adsets"] += 1 if card.get("is_active") else 0
        adsets.append({
            **card,
            "ads": ads,
            "ad_count": len(ads),
            "active_ad_count": active_ads,
            "ads_manager_url": f"https://adsmanager.facebook.com/adsmanager/manage/adsets/edit?act=8979315238856807&selected_adset_ids={adset_id}",
        })

    totals["spend_inr"] = round(totals["spend_inr"], 2)
    totals["purchase_value_inr"] = round(totals["purchase_value_inr"], 2)
    totals["roas"] = round(totals["purchase_value_inr"] / totals["spend_inr"], 2) if totals["spend_inr"] and totals["purchase_value_inr"] else None
    totals["cpc_inr"] = round(totals["spend_inr"] / totals["clicks"], 2) if totals["clicks"] else None
    totals["cpm_inr"] = round(totals["spend_inr"] / totals["impressions"] * 1000, 2) if totals["impressions"] else None
    totals["ctr"] = round(totals["clicks"] / totals["impressions"] * 100, 3) if totals["impressions"] else None

    return jsonify({
        "ok": True,
        "mode": "founder_campaign_cockpit",
        "date_preset": date_preset,
        "campaign": campaign_data,
        "totals": totals,
        "adsets": adsets,
        "brain": {
            "summary": (decision.get("ai_plan") or {}).get("summary"),
            "recommended_actions": (decision.get("ai_plan") or {}).get("recommended_actions") or decision.get("heuristic_actions") or [],
            "urgency": (decision.get("ai_plan") or {}).get("urgency"),
        },
        "guardrails": {
            "dashboard_direct_publish_enabled": False,
            "mutation_requires_gate": True,
            "source": "Meta Marketing API",
        },
        "errors": errors,
    })
