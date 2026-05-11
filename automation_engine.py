import os
from datetime import datetime, timedelta, timezone
from typing import Any

from flask import jsonify, request

from ad_intelligence_engine import _decision_payload, _safe_execution_plan
from google_engine import _cell, _ensure_combos_headers, _google_services, _sheet_id, _sheet_values


DEFAULT_INTERVAL_DAYS = int(os.environ.get("WEARTH_AD_MACHINE_INTERVAL_DAYS") or "6")
DEFAULT_TOTAL_DAILY_BUDGET_INR = int(os.environ.get("WEARTH_AD_MACHINE_DAILY_BUDGET_INR") or "2500")
MIN_TOTAL_DAILY_BUDGET_INR = 2000
MAX_TOTAL_DAILY_BUDGET_INR = 3000


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_utc(value: str) -> datetime | None:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        parsed = datetime.fromisoformat(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _budget_guardrail(value: Any) -> int:
    try:
        budget = int(float(value))
    except (TypeError, ValueError):
        budget = DEFAULT_TOTAL_DAILY_BUDGET_INR
    return max(MIN_TOTAL_DAILY_BUDGET_INR, min(MAX_TOTAL_DAILY_BUDGET_INR, budget))


def _safe_plan_summary(safe_plan: list[dict]) -> dict:
    kinds: dict[str, int] = {}
    action_types: dict[str, int] = {}
    for item in safe_plan:
        kind = str(item.get("execution_kind") or "unknown")
        kinds[kind] = kinds.get(kind, 0) + 1
        action = item.get("action") or {}
        action_type = str(action.get("action_type") or "unknown")
        action_types[action_type] = action_types.get(action_type, 0) + 1
    return {"execution_kinds": kinds, "action_types": action_types}


def _first_queued_combo_preview() -> dict:
    sheet_id = _sheet_id()
    if not sheet_id:
        return {"ok": False, "error": "GOOGLE_SHEET_ID is not set"}
    _info, sheets, _drive = _google_services()
    _ensure_combos_headers(sheets, sheet_id)
    rows = _sheet_values(sheets, sheet_id, "combos!A2:N")
    for row_num, row in enumerate(rows, start=2):
        if _cell(row, 5).lower() != "queued":
            continue
        if not (_cell(row, 0) and _cell(row, 1) and _cell(row, 2) and _cell(row, 3)):
            continue
        return {
            "ok": True,
            "available": True,
            "row_number": row_num,
            "folder_id": _cell(row, 0),
            "folder_name": _cell(row, 1),
            "image_file_id": _cell(row, 2),
            "video_file_id": _cell(row, 3),
            "combo_label": _cell(row, 4),
            "status": _cell(row, 5),
        }
    return {"ok": True, "available": False, "message": "No queued complete image/video combo found."}


def _choose_route(decision: dict, safe_plan: list[dict], eligible_to_act: bool) -> dict:
    if not eligible_to_act:
        return {
            "route": "sleep_window",
            "action": "hold_current_meta_ads",
            "reason": "Automation is installed but the 5-7 day observation window has not elapsed.",
        }
    if not decision.get("ok"):
        return {
            "route": "blocked",
            "action": "fix_data_access",
            "reason": decision.get("error") or "Meta decision brain could not produce scorecards.",
        }
    creative_items = [x for x in safe_plan if x.get("execution_kind") == "creative_queue"]
    budget_items = [x for x in safe_plan if x.get("execution_kind") == "meta_budget_update"]
    hold_items = [x for x in safe_plan if x.get("execution_kind") == "no_mutation"]
    if creative_items:
        return {
            "route": "creative_branch",
            "action": "prepare_next_judged_creative",
            "reason": "Meta brain wants creative iteration. Produce and judge creative before any launch.",
            "item_count": len(creative_items),
        }
    if budget_items:
        return {
            "route": "budget_safety_branch",
            "action": "budget_plan_only",
            "reason": "Budget movement is planned but Meta mutation remains off in this router layer.",
            "item_count": len(budget_items),
        }
    return {
        "route": "hold",
        "action": "collect_more_data",
        "reason": "No useful intervention yet." if not hold_items else "Scorecards indicate hold/learn.",
    }


def ad_machine_tick():
    """
    POST /api/automation/ad-machine-tick
    Safe router for n8n. It senses Meta, decides the branch, previews creative queue,
    and returns the next phase plan. It does not mutate live Meta ads.
    """
    data = request.get_json(force=True, silent=True) or {}
    now = _utc_now()
    interval_days = int(data.get("interval_days") or DEFAULT_INTERVAL_DAYS)
    not_before = _parse_utc(
        data.get("not_before_utc")
        or os.environ.get("WEARTH_AD_MACHINE_NOT_BEFORE_UTC")
        or ""
    )
    if not_before is None and data.get("started_at_utc"):
        started = _parse_utc(str(data.get("started_at_utc")))
        if started:
            not_before = started + timedelta(days=interval_days)
    eligible_to_act = not_before is None or now >= not_before
    total_daily_budget_inr = _budget_guardrail(data.get("total_daily_budget_inr"))

    decision = _decision_payload(
        {
            "campaign_id": data.get("campaign_id"),
            "target_roas": data.get("target_roas") or 4.0,
            "date_preset": data.get("date_preset") or "last_7d",
            "min_spend_inr": data.get("min_spend_inr") or 500,
        },
        request.args,
    )
    http_status = int(decision.pop("http_status", 200))
    safe_plan = _safe_execution_plan(decision) if http_status == 200 and decision.get("ok") else []
    route = _choose_route(decision, safe_plan, eligible_to_act)

    combo_preview = None
    if route.get("route") == "creative_branch":
        try:
            combo_preview = _first_queued_combo_preview()
        except Exception as exc:
            combo_preview = {"ok": False, "error": str(exc)}

    return jsonify({
        "ok": http_status == 200 and bool(decision.get("ok")),
        "mode": "safe_router_no_meta_mutation",
        "generated_at": now.isoformat(),
        "eligible_to_act": eligible_to_act,
        "sleep_window": {
            "interval_days": interval_days,
            "not_before_utc": not_before.isoformat() if not_before else None,
            "remaining_seconds": max(0, int((not_before - now).total_seconds())) if not_before else 0,
        },
        "budget_guardrails": {
            "requested_total_daily_budget_inr": data.get("total_daily_budget_inr"),
            "planned_total_daily_budget_inr": total_daily_budget_inr,
            "min_total_daily_budget_inr": MIN_TOTAL_DAILY_BUDGET_INR,
            "max_total_daily_budget_inr": MAX_TOTAL_DAILY_BUDGET_INR,
            "max_new_ads_per_cycle": int(data.get("max_new_ads_per_cycle") or 3),
        },
        "route": route,
        "safe_plan_summary": _safe_plan_summary(safe_plan),
        "creative_queue_preview": combo_preview,
        "recommended_phase_sequence": [
            "meta_decision_brain",
            "if_creative_needed: google_sync_combos",
            "if_creative_needed: pick_next_combo",
            "if_creative_needed: image_brain_repair_judge",
            "if_creative_needed: video_brain_produce_judge",
            "combo_parent_judge",
            "meta_recheck_cost_benefit",
            "prepare_launch_plan_with_budget_guardrails",
        ],
        "guardrails": {
            "current_meta_ads_mutated": False,
            "live_launch_enabled_in_this_endpoint": False,
            "budget_increase_enabled_in_this_endpoint": False,
            "audience_mutation_enabled_in_this_endpoint": False,
            "requires_parent_creative_judge": True,
        },
        "decision": decision,
        "safe_plan": safe_plan,
    }), http_status
