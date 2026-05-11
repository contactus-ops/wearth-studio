import json
import os
from datetime import datetime, timezone
from typing import Any

import requests
from flask import jsonify, request


META_TOKEN = os.environ.get("META_ACCESS_TOKEN", "")
META_AD_ACCOUNT = os.environ.get("META_AD_ACCOUNT_ID", "")
META_CAMPAIGN_ID = os.environ.get("META_CAMPAIGN_ID", "120245108704880305")
GRAPH = os.environ.get("META_GRAPH_BASE", "https://graph.facebook.com/v22.0").rstrip("/")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")

PURCHASE_TYPES = (
    "purchase",
    "omni_purchase",
    "offsite_conversion.fb_pixel_purchase",
    "onsite_conversion.purchase",
)
INSIGHT_FIELDS = ",".join(
    [
        "spend",
        "impressions",
        "reach",
        "clicks",
        "cpc",
        "cpm",
        "ctr",
        "actions",
        "action_values",
        "cost_per_action_type",
        "purchase_roas",
        "website_purchase_roas",
    ]
)
ADSET_FIELDS = "id,name,status,effective_status,daily_budget,bid_strategy,optimization_goal,targeting"
MAX_DAILY_BUDGET_PAISE = int(os.environ.get("META_MAX_DAILY_BUDGET_PAISE") or "100000")


def _h() -> dict:
    return {"Authorization": f"Bearer {META_TOKEN}"}


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _first_purchase_value(rows: Any) -> float | None:
    if not isinstance(rows, list):
        return None
    for row in rows:
        if not isinstance(row, dict):
            continue
        action_type = str(row.get("action_type") or "").lower()
        if any(p in action_type for p in PURCHASE_TYPES):
            return _float(row.get("value"))
    return None


def _purchase_count(actions: Any) -> float:
    total = _first_purchase_value(actions)
    return float(total or 0.0)


def _purchase_value(action_values: Any) -> float:
    total = _first_purchase_value(action_values)
    return float(total or 0.0)


def _roas_from_insight(row: dict, spend: float, purchase_value: float) -> float | None:
    for key in ("purchase_roas", "website_purchase_roas"):
        values = row.get(key)
        if isinstance(values, list) and values:
            first = values[0] if isinstance(values[0], dict) else {}
            roas = _float(first.get("value"), 0.0)
            if roas > 0:
                return round(roas, 2)
    if spend > 0 and purchase_value > 0:
        return round(purchase_value / spend, 2)
    return None


def _get_json(url: str, params: dict, timeout: int = 60) -> tuple[dict | None, str | None, int]:
    r = requests.get(url, headers=_h(), params=params, timeout=timeout)
    if r.status_code != 200:
        return None, (r.text or "")[:800], r.status_code
    return r.json() or {}, None, r.status_code


def _campaign_adsets(campaign_id: str) -> tuple[list[dict], list[dict]]:
    errors = []
    url = f"{GRAPH}/{campaign_id}/adsets"
    params = {"fields": ADSET_FIELDS, "limit": 100}
    data, err, http = _get_json(url, params)
    if err:
        return [], [{"step": "campaign_adsets", "http": http, "error": err}]
    return data.get("data") or [], errors


def _insight_for_object(object_id: str, date_preset: str) -> tuple[dict, dict | None]:
    params = {"fields": INSIGHT_FIELDS, "date_preset": date_preset}
    data, err, http = _get_json(f"{GRAPH}/{object_id}/insights", params)
    if err:
        return {}, {"object_id": object_id, "http": http, "error": err}
    rows = data.get("data") or []
    return (rows[0] if rows else {}), None


def _scorecard(adset: dict, insight: dict, target_roas: float, min_spend_inr: float) -> dict:
    spend = _float(insight.get("spend"))
    impressions = _float(insight.get("impressions"))
    reach = _float(insight.get("reach"))
    clicks = _float(insight.get("clicks"))
    purchases = _purchase_count(insight.get("actions"))
    purchase_value = _purchase_value(insight.get("action_values"))
    roas = _roas_from_insight(insight, spend, purchase_value)
    cpa = round(spend / purchases, 2) if purchases > 0 else None
    ctr = _float(insight.get("ctr"))
    cpc = _float(insight.get("cpc"))
    cpm = _float(insight.get("cpm"))
    daily_budget_paise = int(_float(adset.get("daily_budget"), 0))
    status = str(adset.get("effective_status") or adset.get("status") or "").upper()

    if spend < min_spend_inr:
        stage = "learning_low_spend"
    elif roas is not None and roas >= target_roas:
        stage = "scaling_candidate"
    elif purchases <= 0 and spend >= min_spend_inr:
        stage = "no_purchase_after_spend"
    elif roas is not None and roas < max(1.0, target_roas * 0.4):
        stage = "underperforming"
    else:
        stage = "watch_or_iterate"

    return {
        "adset_id": adset.get("id"),
        "name": adset.get("name"),
        "status": adset.get("status"),
        "effective_status": adset.get("effective_status"),
        "daily_budget_paise": daily_budget_paise,
        "daily_budget_inr": round(daily_budget_paise / 100, 2) if daily_budget_paise else None,
        "bid_strategy": adset.get("bid_strategy"),
        "optimization_goal": adset.get("optimization_goal"),
        "spend_inr": round(spend, 2),
        "impressions": int(impressions),
        "reach": int(reach),
        "clicks": int(clicks),
        "ctr": round(ctr, 3) if ctr else None,
        "cpc_inr": round(cpc, 2) if cpc else None,
        "cpm_inr": round(cpm, 2) if cpm else None,
        "purchases": int(purchases),
        "purchase_value_inr": round(purchase_value, 2) if purchase_value else None,
        "roas": roas,
        "cpa_inr": cpa,
        "stage": stage,
        "is_active": status == "ACTIVE",
        "targeting_snapshot": {
            "age_min": (adset.get("targeting") or {}).get("age_min"),
            "age_max": (adset.get("targeting") or {}).get("age_max"),
            "genders": (adset.get("targeting") or {}).get("genders"),
            "advantage_audience": ((adset.get("targeting") or {}).get("targeting_automation") or {}).get("advantage_audience"),
        },
    }


def _heuristic_actions(cards: list[dict], target_roas: float, min_spend_inr: float) -> list[dict]:
    actions = []
    for card in cards:
        adset_id = card.get("adset_id")
        budget = int(card.get("daily_budget_paise") or 0)
        roas = card.get("roas")
        spend = float(card.get("spend_inr") or 0)
        purchases = int(card.get("purchases") or 0)
        ctr = float(card.get("ctr") or 0)

        if budget > MAX_DAILY_BUDGET_PAISE:
            actions.append({
                "action_type": "decrease_budget",
                "adset_id": adset_id,
                "priority": "high",
                "reason": "Daily budget exceeds the hard cap.",
                "proposed_daily_budget_paise": MAX_DAILY_BUDGET_PAISE,
                "execution_allowed_now": False,
            })
            continue

        if spend < min_spend_inr:
            actions.append({
                "action_type": "hold_collect_data",
                "adset_id": adset_id,
                "priority": "low",
                "reason": "Spend is below decision threshold; avoid premature edits.",
                "execution_allowed_now": False,
            })
            continue

        if roas is not None and roas >= target_roas and purchases >= 1:
            next_budget = min(MAX_DAILY_BUDGET_PAISE, int(max(budget, 20000) * 1.2))
            actions.append({
                "action_type": "increase_budget",
                "adset_id": adset_id,
                "priority": "medium",
                "reason": "ROAS target met; scale carefully by 20 percent, capped.",
                "proposed_daily_budget_paise": next_budget,
                "execution_allowed_now": False,
            })
        elif purchases == 0 and spend >= min_spend_inr:
            action_type = "introduce_new_creative" if ctr >= 0.7 else "change_creative_and_hook"
            actions.append({
                "action_type": action_type,
                "adset_id": adset_id,
                "priority": "high",
                "reason": "Spend crossed threshold with no purchase signal.",
                "execution_allowed_now": False,
            })
        elif roas is not None and roas < target_roas:
            actions.append({
                "action_type": "change_copy_or_creative",
                "adset_id": adset_id,
                "priority": "medium",
                "reason": "Purchase signal exists but ROAS is below target.",
                "execution_allowed_now": False,
            })
        else:
            actions.append({
                "action_type": "hold_collect_data",
                "adset_id": adset_id,
                "priority": "low",
                "reason": "No clear statistically useful action yet.",
                "execution_allowed_now": False,
            })
    return actions


def _anthropic_decision(cards: list[dict], heuristic_actions: list[dict], target_roas: float) -> dict:
    if not ANTHROPIC_API_KEY:
        return {"ok": False, "error": "ANTHROPIC_API_KEY missing"}
    prompt = {
        "task": "Act as WEARTH Active's Meta ads decision brain. Recommend the next actions to reach ROAS 4 as fast as possible without reckless changes.",
        "brand": "WEARTH Active: premium plant-based activewear for women in India. Quiet luxury, fabric science, premium activewear, not discount or generic gym content.",
        "target_roas": target_roas,
        "hard_guardrails": [
            "Never propose daily_budget_paise above 100000.",
            "Do not recommend launch/publish unless creative has passed a separate parent creative judge.",
            "Do not make many variables change at once; isolate audience, creative, copy, or budget decisions.",
            "If spend is low, prefer hold_collect_data instead of false certainty.",
            "Every recommendation must include evidence from the scorecards.",
        ],
        "allowed_action_types": [
            "hold_collect_data",
            "increase_budget",
            "decrease_budget",
            "pause_adset",
            "broaden_audience",
            "narrow_audience",
            "enable_advantage_audience",
            "change_copy",
            "introduce_new_creative",
            "investigate_tracking",
        ],
        "scorecards": cards,
        "heuristic_actions": heuristic_actions,
        "required_json_schema": {
            "summary": "short diagnosis",
            "urgency": "low|medium|high|critical",
            "confidence_0_1": "number",
            "recommended_actions": [
                {
                    "action_type": "one allowed action type",
                    "adset_id": "string or null",
                    "priority": "low|medium|high|critical",
                    "reason": "evidence-based reason",
                    "expected_effect": "what should improve",
                    "risk": "main risk",
                    "proposed_daily_budget_paise": "number or null",
                }
            ],
            "creative_instruction": "what creative pipeline should do next",
            "audience_instruction": "what targeting change, if any, should be tested",
            "copy_instruction": "what copy angle should be tested",
            "do_not_do": ["unsafe or premature actions"],
        },
    }
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": ANTHROPIC_MODEL,
                "max_tokens": 1600,
                "temperature": 0.15,
                "messages": [{"role": "user", "content": json.dumps(prompt, ensure_ascii=True)}],
            },
            timeout=90,
        )
        if r.status_code != 200:
            return {"ok": False, "http": r.status_code, "error": r.text[:800]}
        text = ((r.json().get("content") or [{}])[0].get("text") or "").strip()
        if text.startswith("```"):
            text = text.replace("```json", "").replace("```", "").strip()
        parsed = json.loads(text)
        parsed["ok"] = True
        parsed["model"] = ANTHROPIC_MODEL
        return parsed
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _sanitize_ai_actions(ai_plan: dict) -> dict:
    if not isinstance(ai_plan, dict) or not ai_plan.get("ok"):
        return ai_plan
    sanitized = dict(ai_plan)
    actions = []
    for action in sanitized.get("recommended_actions") or []:
        if not isinstance(action, dict):
            continue
        clean = dict(action)
        budget = clean.get("proposed_daily_budget_paise")
        if budget is not None:
            budget_int = int(_float(budget, 0))
            clean["proposed_daily_budget_paise"] = min(budget_int, MAX_DAILY_BUDGET_PAISE)
            if budget_int > MAX_DAILY_BUDGET_PAISE:
                clean["guardrail_note"] = "Budget capped to META_MAX_DAILY_BUDGET_PAISE."
        clean["execution_allowed_now"] = False
        actions.append(clean)
    sanitized["recommended_actions"] = actions
    return sanitized


def meta_roas_decision():
    """
    POST /api/meta/roas-decision
    Read-first ad intelligence: fetch Meta scorecards, generate a gated action plan.
    This endpoint does not mutate Meta. A separate executor should apply approved actions.
    """
    data = request.get_json(force=True, silent=True) if request.method == "POST" else {}
    data = data or {}
    if not META_TOKEN:
        return jsonify({"ok": False, "error": "META_ACCESS_TOKEN missing"}), 500
    campaign_id = (data.get("campaign_id") or request.args.get("campaign_id") or META_CAMPAIGN_ID or "").strip()
    if not campaign_id:
        return jsonify({"ok": False, "error": "campaign_id or META_CAMPAIGN_ID required"}), 400
    target_roas = _float(data.get("target_roas") or request.args.get("target_roas"), 4.0)
    date_preset = (data.get("date_preset") or request.args.get("date_preset") or "last_7d").strip()
    min_spend_inr = _float(data.get("min_spend_inr") or request.args.get("min_spend_inr"), 500.0)

    adsets, errors = _campaign_adsets(campaign_id)
    cards = []
    for adset in adsets:
        insight, err = _insight_for_object(str(adset.get("id")), date_preset)
        if err:
            errors.append({"step": "adset_insight", **err})
        cards.append(_scorecard(adset, insight, target_roas, min_spend_inr))

    heuristic = _heuristic_actions(cards, target_roas, min_spend_inr)
    ai_plan = _sanitize_ai_actions(_anthropic_decision(cards, heuristic, target_roas))
    response = {
        "ok": True,
        "mode": "decision_only_no_meta_mutation",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "campaign_id": campaign_id,
        "date_preset": date_preset,
        "target": {
            "roas": target_roas,
            "min_spend_inr": min_spend_inr,
            "max_daily_budget_paise": MAX_DAILY_BUDGET_PAISE,
        },
        "scorecards": cards,
        "heuristic_actions": heuristic,
        "ai_plan": ai_plan,
        "errors": errors,
        "execution": {
            "executed": False,
            "reason": "This is the sensing and decision layer. Meta mutations require a separate gated executor.",
            "next_safe_layer": "Build /api/meta/roas-execute for approved budget/status/audience actions only after decision quality is verified.",
        },
    }
    return jsonify(response)
