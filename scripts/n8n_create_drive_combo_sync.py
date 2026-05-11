# -*- coding: utf-8 -*-
"""
Create/update the n8n workflow that syncs new Drive combo folders into the
WEARTH Ad Intelligence Google Sheet.

Requires:
  N8N_API_KEY
Optional:
  N8N_BASE_URL (default: https://wearthactive.app.n8n.cloud)
  APP_BASE_URL (default: https://web-production-448c1.up.railway.app)
  GOOGLE_DRIVE_PARENT_FOLDER_ID (default: META COMBINATION folder)

Usage:
  python scripts/n8n_create_drive_combo_sync.py
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from n8n_api_common import load_n8n_api_key, upsert_workflow  # noqa: E402


WORKFLOW_NAME = "WEARTH Drive Combo Queue Sync"
DEFAULT_N8N_BASE = "https://wearthactive.app.n8n.cloud"
DEFAULT_APP_BASE = "https://web-production-448c1.up.railway.app"
DEFAULT_PARENT_FOLDER_ID = "1elkhg3tG7ggC0e62IbfBSzaLCO6sm97o"


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def build_workflow(app_base: str, parent_folder_id: str) -> Dict[str, Any]:
    sync_body = {
        "folder_id": parent_folder_id,
        "used_folder_names": [],
        "used_status": "used",
        "used_note": "Already launched before queue sync.",
    }

    n_schedule = _id("schedule")
    n_webhook = _id("webhook")
    n_sync = _id("sync")

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
                                "expression": "*/15 * * * *",
                            }
                        ]
                    },
                    "timezone": "Asia/Kolkata",
                },
                "id": n_schedule,
                "name": "Every 15 Minutes",
                "type": "n8n-nodes-base.scheduleTrigger",
                "typeVersion": 1.2,
                "position": [0, 0],
            },
            {
                "parameters": {
                    "multipleMethods": False,
                    "httpMethod": "POST",
                    "path": "wearth-drive-combo-sync-test",
                    "responseMode": "onReceived",
                    "options": {},
                },
                "id": n_webhook,
                "name": "Manual Sync Webhook",
                "type": "n8n-nodes-base.webhook",
                "typeVersion": 2.1,
                "position": [0, 220],
            },
            {
                "parameters": {
                    "method": "POST",
                    "url": f"{app_base.rstrip()}/api/google/sync-combos",
                    "authentication": "none",
                    "sendHeaders": True,
                    "headerParameters": {
                        "parameters": [
                            {"name": "Content-Type", "value": "application/json"}
                        ]
                    },
                    "sendBody": True,
                    "specifyBody": "json",
                    "jsonBody": json.dumps(sync_body),
                    "options": {"timeout": 120000},
                },
                "id": n_sync,
                "name": "Sync Drive Combos To Sheet",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [320, 100],
            },
        ],
        "connections": {
            "Every 15 Minutes": {
                "main": [[{"node": "Sync Drive Combos To Sheet", "type": "main", "index": 0}]]
            },
            "Manual Sync Webhook": {
                "main": [[{"node": "Sync Drive Combos To Sheet", "type": "main", "index": 0}]]
            },
        },
        "settings": {
            "timezone": "Asia/Kolkata",
            "saveDataSuccessExecution": "all",
            "saveDataErrorExecution": "all",
            "executionTimeout": 180,
        },
    }


def main() -> int:
    n8n_key = load_n8n_api_key()
    if not n8n_key:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "N8N_API_KEY is not set",
                    "hint": "Create an n8n API key, then run this script with N8N_API_KEY in env.",
                },
                indent=2,
            )
        )
        return 2

    n8n_base = (os.environ.get("N8N_BASE_URL") or DEFAULT_N8N_BASE).rstrip("/")
    app_base = (os.environ.get("APP_BASE_URL") or DEFAULT_APP_BASE).rstrip("/")
    parent_folder_id = (
        os.environ.get("GOOGLE_DRIVE_PARENT_FOLDER_ID") or DEFAULT_PARENT_FOLDER_ID
    ).strip()

    wf = build_workflow(app_base, parent_folder_id)
    wf_id, activated = upsert_workflow(n8n_base, n8n_key, wf, WORKFLOW_NAME)
    print(
        json.dumps(
            {
                "ok": True,
                "workflow_name": WORKFLOW_NAME,
                "workflow_id": wf_id,
                "activated": activated,
                "schedule": "*/15 * * * * Asia/Kolkata",
                "sync_url": f"{app_base}/api/google/sync-combos",
                "parent_folder_id": parent_folder_id,
                "manual_webhook": f"{n8n_base}/webhook/wearth-drive-combo-sync-test",
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
