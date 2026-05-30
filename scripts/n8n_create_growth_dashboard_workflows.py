#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Create n8n workflows for WEARTH Growth Dashboard.

1) WEARTH Growth Daily Sync — cron 8:00 IST → POST /api/growth/sync-daily
2) WEARTH Growth Klaviyo Weekly — cron Mon 8:00 IST → POST /api/growth/sync-klaviyo-weekly
3) WEARTH Growth Meta Token Alert — on failure email via workflow error (daily sync uses Railway Gmail)

Run: railway run -- python scripts/n8n_create_growth_dashboard_workflows.py
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, str(Path(__file__).resolve().parent))
from n8n_api_common import load_n8n_api_key, upsert_workflow  # noqa: E402

DAILY_NAME = "WEARTH Growth Daily Sync"
WEEKLY_NAME = "WEARTH Growth Klaviyo Weekly"
DEFAULT_N8N_BASE = "https://wearthactive.app.n8n.cloud"
DEFAULT_APP_BASE = "https://web-production-448c1.up.railway.app"


def _nid() -> str:
    return str(uuid.uuid4())


def _http_node(name: str, url: str, admin_token: str, pos: list) -> Dict[str, Any]:
    headers = [{"name": "Content-Type", "value": "application/json"}]
    if admin_token:
        headers.append({"name": "X-Wearth-Admin", "value": admin_token})
    return {
        "parameters": {
            "method": "POST",
            "url": url,
            "authentication": "none",
            "sendHeaders": True,
            "headerParameters": {"parameters": headers},
            "options": {"timeout": 600000},
        },
        "id": _nid(),
        "name": name,
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": pos,
    }


def build_daily_workflow(app_base: str, admin_token: str) -> Dict[str, Any]:
    n_sched = _nid()
    n_http = _http_node(
        "Growth Daily Sync",
        f"{app_base.rstrip('/')}/api/growth/sync-daily",
        admin_token,
        [320, 0],
    )
    return {
        "name": DAILY_NAME,
        "active": True,
        "nodes": [
            {
                "parameters": {
                    "rule": {
                        "interval": [{"field": "cronExpression", "expression": "0 8 * * *"}]
                    },
                    "timezone": "Asia/Kolkata",
                },
                "id": n_sched,
                "name": "Daily 8:00am IST",
                "type": "n8n-nodes-base.scheduleTrigger",
                "typeVersion": 1.2,
                "position": [0, 0],
            },
            n_http,
        ],
        "connections": {
            "Daily 8:00am IST": {
                "main": [[{"node": "Growth Daily Sync", "type": "main", "index": 0}]]
            }
        },
        "settings": {
            "timezone": "Asia/Kolkata",
            "saveDataSuccessExecution": "all",
            "saveDataErrorExecution": "all",
            "executionTimeout": 600,
        },
    }


def build_weekly_workflow(app_base: str, admin_token: str) -> Dict[str, Any]:
    n_sched = _nid()
    n_http = _http_node(
        "Klaviyo Weekly Sync",
        f"{app_base.rstrip('/')}/api/growth/sync-klaviyo-weekly",
        admin_token,
        [320, 0],
    )
    return {
        "name": WEEKLY_NAME,
        "active": True,
        "nodes": [
            {
                "parameters": {
                    "rule": {
                        "interval": [{"field": "cronExpression", "expression": "0 8 * * 1"}]
                    },
                    "timezone": "Asia/Kolkata",
                },
                "id": n_sched,
                "name": "Monday 8:00am IST",
                "type": "n8n-nodes-base.scheduleTrigger",
                "typeVersion": 1.2,
                "position": [0, 0],
            },
            n_http,
        ],
        "connections": {
            "Monday 8:00am IST": {
                "main": [[{"node": "Klaviyo Weekly Sync", "type": "main", "index": 0}]]
            }
        },
        "settings": {
            "timezone": "Asia/Kolkata",
            "saveDataSuccessExecution": "all",
            "saveDataErrorExecution": "all",
            "executionTimeout": 600,
        },
    }


def main() -> int:
    n8n_key = load_n8n_api_key()
    if not n8n_key:
        print(json.dumps({"ok": False, "error": "N8N_API_KEY missing"}, indent=2))
        return 2
    n8n_base = (os.environ.get("N8N_BASE_URL") or DEFAULT_N8N_BASE).rstrip("/")
    app_base = (os.environ.get("APP_BASE_URL") or DEFAULT_APP_BASE).rstrip("/")
    admin_token = (os.environ.get("ADMIN_TOKEN") or os.environ.get("WEARTH_N8N_MAIL_TOKEN") or "").strip()
    if not admin_token:
        print(json.dumps({"ok": False, "error": "ADMIN_TOKEN missing"}, indent=2))
        return 2

    daily_id, daily_active = upsert_workflow(n8n_base, n8n_key, build_daily_workflow(app_base, admin_token), DAILY_NAME)
    weekly_id, weekly_active = upsert_workflow(
        n8n_base, n8n_key, build_weekly_workflow(app_base, admin_token), WEEKLY_NAME
    )
    print(
        json.dumps(
            {
                "ok": True,
                "daily": {"id": daily_id, "active": daily_active, "cron": "0 8 * * * IST"},
                "weekly": {"id": weekly_id, "active": weekly_active, "cron": "0 8 * * 1 IST"},
                "endpoints": {
                    "daily": f"{app_base}/api/growth/sync-daily",
                    "klaviyo": f"{app_base}/api/growth/sync-klaviyo-weekly",
                    "site_audit": f"{app_base}/api/growth/run-site-audit",
                },
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
