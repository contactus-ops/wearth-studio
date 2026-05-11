# -*- coding: utf-8 -*-
"""
Create/update the n8n workflow that wakes the WEARTH autonomous ad machine.

The workflow runs daily, but the Railway router enforces a not-before window so
current Meta ads are observed for 5-7 days before any next branch is recommended.

Requires:
  N8N_API_KEY
Optional:
  N8N_BASE_URL (default: https://wearthactive.app.n8n.cloud)
  APP_BASE_URL (default: https://web-production-448c1.up.railway.app)
  WEARTH_AD_MACHINE_INTERVAL_DAYS (default: 6)
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, str(Path(__file__).resolve().parent))

from n8n_api_common import load_n8n_api_key, upsert_workflow  # noqa: E402


WORKFLOW_NAME = "WEARTH Autonomous Ad Machine Loop"
DEFAULT_N8N_BASE = "https://wearthactive.app.n8n.cloud"
DEFAULT_APP_BASE = "https://web-production-448c1.up.railway.app"


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def build_workflow(app_base: str, *, interval_days: int, started_at: datetime) -> Dict[str, Any]:
    not_before = started_at + timedelta(days=interval_days)
    tick_body = {
        "started_at_utc": started_at.isoformat(),
        "not_before_utc": not_before.isoformat(),
        "interval_days": interval_days,
        "target_roas": 4,
        "date_preset": "last_7d",
        "min_spend_inr": 500,
        "total_daily_budget_inr": 2500,
        "max_new_ads_per_cycle": 3,
    }

    n_schedule = _id("schedule")
    n_webhook = _id("webhook")
    n_tick = _id("tick")
    n_summary = _id("summary")

    summarize_js = """const tick = $input.first().json;
return [{
  json: {
    ok: tick.ok,
    generated_at: tick.generated_at,
    eligible_to_act: tick.eligible_to_act,
    route: tick.route,
    sleep_window: tick.sleep_window,
    budget_guardrails: tick.budget_guardrails,
    safe_plan_summary: tick.safe_plan_summary,
    creative_queue_preview: tick.creative_queue_preview,
    guardrails: tick.guardrails,
    summary: tick.eligible_to_act
      ? `Route: ${tick.route?.route || 'unknown'} / ${tick.route?.action || 'unknown'}`
      : `Sleeping until ${tick.sleep_window?.not_before_utc}`,
  }
}];"""

    return {
        "name": WORKFLOW_NAME,
        "active": True,
        "nodes": [
            {
                "parameters": {
                    "rule": {
                        "interval": [
                            {
                                "field": "cronExpression",
                                "expression": "15 8 * * *",
                            }
                        ]
                    },
                    "timezone": "Asia/Kolkata",
                },
                "id": n_schedule,
                "name": "Daily 8:15am IST",
                "type": "n8n-nodes-base.scheduleTrigger",
                "typeVersion": 1.2,
                "position": [0, 0],
            },
            {
                "parameters": {
                    "multipleMethods": False,
                    "httpMethod": "POST",
                    "path": "wearth-ad-machine-test",
                    "responseMode": "onReceived",
                    "options": {},
                },
                "id": n_webhook,
                "name": "Manual Test Webhook",
                "type": "n8n-nodes-base.webhook",
                "typeVersion": 2.1,
                "position": [0, 220],
            },
            {
                "parameters": {
                    "method": "POST",
                    "url": f"{app_base.rstrip('/')}/api/automation/ad-machine-tick",
                    "authentication": "none",
                    "sendHeaders": True,
                    "headerParameters": {
                        "parameters": [{"name": "Content-Type", "value": "application/json"}]
                    },
                    "sendBody": True,
                    "specifyBody": "json",
                    "jsonBody": json.dumps(tick_body),
                    "options": {"timeout": 180000},
                },
                "id": n_tick,
                "name": "Wake Safe Ad Machine Router",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [320, 100],
            },
            {
                "parameters": {"language": "javaScript", "jsCode": summarize_js},
                "id": n_summary,
                "name": "Summarize Router Output",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [640, 100],
            },
        ],
        "connections": {
            "Daily 8:15am IST": {
                "main": [[{"node": "Wake Safe Ad Machine Router", "type": "main", "index": 0}]]
            },
            "Manual Test Webhook": {
                "main": [[{"node": "Wake Safe Ad Machine Router", "type": "main", "index": 0}]]
            },
            "Wake Safe Ad Machine Router": {
                "main": [[{"node": "Summarize Router Output", "type": "main", "index": 0}]]
            },
        },
        "settings": {
            "timezone": "Asia/Kolkata",
            "saveDataSuccessExecution": "all",
            "saveDataErrorExecution": "all",
            "executionTimeout": 240,
        },
    }


def main() -> int:
    n8n_key = load_n8n_api_key()
    if not n8n_key:
        print(json.dumps({"ok": False, "error": "N8N_API_KEY is not set"}, indent=2))
        return 2

    n8n_base = (os.environ.get("N8N_BASE_URL") or DEFAULT_N8N_BASE).rstrip("/")
    app_base = (os.environ.get("APP_BASE_URL") or DEFAULT_APP_BASE).rstrip("/")
    interval_days = int(os.environ.get("WEARTH_AD_MACHINE_INTERVAL_DAYS") or "6")
    started_at = datetime.now(timezone.utc).replace(microsecond=0)

    wf = build_workflow(app_base, interval_days=interval_days, started_at=started_at)
    try:
        wf_id, activated = upsert_workflow(n8n_base, n8n_key, wf, WORKFLOW_NAME)
    except RuntimeError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 1

    tick_body = json.loads(wf["nodes"][2]["parameters"]["jsonBody"])
    print(
        json.dumps(
            {
                "ok": True,
                "workflow_id": wf_id,
                "workflow_name": WORKFLOW_NAME,
                "active": activated,
                "schedule": "Daily 8:15am IST",
                "manual_test_path": "wearth-ad-machine-test",
                "router_endpoint": f"{app_base}/api/automation/ad-machine-tick",
                "tick_body": tick_body,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
