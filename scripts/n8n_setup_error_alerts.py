# -*- coding: utf-8 -*-
# TARGET ROAS 4:1 AT ₹15K/MONTH SPEND — Global failure emails for WEARTH n8n workflows.
"""
Creates (or updates) workflow "WEARTH n8n Error Alert" with Error Trigger → format → POST mail,
then sets settings.errorWorkflow on each target workflow so failures notify contactus@wearthactive.com.

Run with Railway env: N8N_BASE_URL, N8N_API_KEY.

Optional: N8N_ERROR_ALERT_TARGET_IDS — comma-separated workflow ids (defaults to Friday, Monday, Instagram).
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from typing import Any, Dict, List, Tuple

import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from n8n_api_common import load_n8n_api_key, prune_minimal_put, req, sanitize_settings, try_activate_workflow

ERROR_HANDLER_NAME = "WEARTH n8n Error Alert"
APP_BASE = "https://web-production-448c1.up.railway.app"
N8N_MAIL_BRIDGE_HEADER = "wearthn8ncommute"

# Default: Friday loop, Monday generator, Instagram Auto (override via N8N_ERROR_ALERT_TARGET_IDS).
DEFAULT_TARGET_IDS = "3GUAuIiPvyxZK09s,AeZlTxTmAcOHjAek,cGbp1fEkP5DoIIsZ"

FORMAT_JS = r"""const x = $input.first().json || {};
const wf = x.workflow || {};
const exec = x.execution || {};
const wfName = wf.name || 'Unknown workflow';
const wfId = wf.id || '';
let nodeName = 'Unknown node';
try {
  nodeName =
    exec.lastNodeExecuted ||
    exec?.data?.resultData?.error?.node?.name ||
    exec?.error?.node?.name ||
    'Unknown node';
} catch (e) {
  nodeName = 'Unknown node';
}
let errMsg = '';
try {
  errMsg =
    exec.error?.message ||
    exec.error?.description ||
    (typeof exec.error === 'string' ? exec.error : JSON.stringify(exec.error || exec, null, 2));
} catch (e) {
  errMsg = String(e);
}
const day = $now.setZone('Asia/Kolkata').toFormat('dd MMM yyyy');
const when = $now.setZone('Asia/Kolkata').toFormat('dd MMM yyyy HH:mm');
const subject = 'WEARTH n8n alert — ' + wfName + ' failed — ' + day;
const text =
  'Workflow: ' +
  wfName +
  ' (id ' +
  wfId +
  ')' +
  '\nFailed node: ' +
  nodeName +
  '\nWhen (IST): ' +
  when +
  '\n\nError:\n' +
  errMsg +
  '\n\nInvestigate: https://wearthactive.app.n8n.cloud\n\n--- Raw (debug) ---\n' +
  JSON.stringify(x, null, 2);
return [{ json: { to: 'contactus@wearthactive.com', subject, text } }];
"""


def _nid() -> str:
    return str(uuid.uuid4())


def build_error_handler_workflow() -> Dict[str, Any]:
    n1, n2, n3 = _nid(), _nid(), _nid()
    y = 320
    return {
        "name": ERROR_HANDLER_NAME,
        "nodes": [
            {
                "parameters": {},
                "id": n1,
                "name": "Error Trigger",
                "type": "n8n-nodes-base.errorTrigger",
                "typeVersion": 1,
                "position": [240, y],
            },
            {
                "parameters": {"language": "javaScript", "jsCode": FORMAT_JS},
                "id": n2,
                "name": "Format Alert Email",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [520, y],
            },
            {
                "parameters": {
                    "method": "POST",
                    "url": f"{APP_BASE}/api/n8n/send-mail",
                    "authentication": "none",
                    "sendHeaders": True,
                    "headerParameters": {
                        "parameters": [
                            {"name": "Content-Type", "value": "application/json"},
                            {
                                "name": "X-Wearth-N8n-Mail",
                                "value": N8N_MAIL_BRIDGE_HEADER,
                            },
                        ]
                    },
                    "sendBody": True,
                    "specifyBody": "json",
                    "jsonBody": "={{ JSON.stringify({ to: $json.to, subject: $json.subject, text: $json.text }) }}",
                    "options": {"timeout": 60000},
                },
                "id": n3,
                "name": "Send Alert Email",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [800, y],
            },
        ],
        "connections": {
            "Error Trigger": {
                "main": [[{"node": "Format Alert Email", "type": "main", "index": 0}]]
            },
            "Format Alert Email": {
                "main": [[{"node": "Send Alert Email", "type": "main", "index": 0}]]
            },
        },
        "settings": sanitize_settings(
            {
                "executionOrder": "v1",
                "timezone": "Asia/Kolkata",
                "saveDataErrorExecution": "all",
                "saveDataSuccessExecution": "all",
            }
        ),
    }


def _find_workflow_id_by_name(base: str, key: str, name: str) -> Tuple[int, str]:
    code, raw = req("GET", f"{base}/api/v1/workflows", n8n_key=key)
    if code != 200:
        return code, raw
    try:
        payload = json.loads(raw)
    except Exception:
        return 400, raw
    rows = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return 404, ""
    for row in rows:
        if isinstance(row, dict) and row.get("name") == name:
            return 200, str(row.get("id") or "")
    return 404, ""


def main() -> None:
    base = (os.environ.get("N8N_BASE_URL") or "https://wearthactive.app.n8n.cloud").rstrip("/")
    key = load_n8n_api_key()
    if not key:
        print(json.dumps({"error": "N8N_API_KEY missing"}))
        sys.exit(1)

    eh = build_error_handler_workflow()
    list_url = f"{base}/api/v1/workflows"
    code, wid = _find_workflow_id_by_name(base, key, ERROR_HANDLER_NAME)
    body = json.dumps({k: v for k, v in eh.items() if k != "active"}).encode("utf-8")
    if code == 200 and wid:
        put_url = f"{base}/api/v1/workflows/{wid}"
        c2, raw_put = req(
            "PUT", put_url, n8n_key=key, body=body, content_type="application/json"
        )
        if c2 != 200:
            c2, raw_put = req(
                "PUT",
                put_url,
                n8n_key=key,
                body=json.dumps(prune_minimal_put(eh)).encode("utf-8"),
                content_type="application/json",
            )
        if c2 != 200:
            print(json.dumps({"step": "PUT error handler", "http": c2, "body": raw_put[:6000]}))
            sys.exit(1)
        error_wf_id = wid
    else:
        c3, raw_post = req("POST", list_url, n8n_key=key, body=body, content_type="application/json")
        if c3 not in (200, 201):
            c3, raw_post = req(
                "POST",
                list_url,
                n8n_key=key,
                body=json.dumps(prune_minimal_put(eh)).encode("utf-8"),
                content_type="application/json",
            )
        if c3 not in (200, 201):
            print(json.dumps({"step": "POST error handler", "http": c3, "body": raw_post[:6000]}))
            sys.exit(1)
        created = json.loads(raw_post)
        error_wf_id = str(created.get("id") or (created.get("data") or {}).get("id") or "")

    try_activate_workflow(base, error_wf_id, key)

    raw_ids = (
        os.environ.get("N8N_ERROR_ALERT_TARGET_IDS") or DEFAULT_TARGET_IDS
    ).replace(" ", "")
    target_ids: List[str] = [x for x in raw_ids.split(",") if x.strip()]
    wired: List[Dict[str, Any]] = []
    for wf_id in target_ids:
        u = f"{base}/api/v1/workflows/{wf_id}"
        cg, rawg = req("GET", u, n8n_key=key)
        if cg != 200:
            wired.append({"workflow_id": wf_id, "ok": False, "error": "GET failed", "http": cg})
            continue
        try:
            wf = json.loads(rawg)
        except Exception:
            wired.append({"workflow_id": wf_id, "ok": False, "error": "invalid JSON"})
            continue
        if wf.get("name") == ERROR_HANDLER_NAME:
            wired.append({"workflow_id": wf_id, "ok": True, "skipped": "is error handler"})
            continue
        st = sanitize_settings(wf.get("settings") or {})
        st["errorWorkflow"] = error_wf_id
        payload = {
            "name": wf.get("name"),
            "nodes": wf.get("nodes"),
            "connections": wf.get("connections"),
            "settings": st,
        }
        cp, rawp = req(
            "PUT",
            u,
            n8n_key=key,
            body=json.dumps(payload).encode("utf-8"),
            content_type="application/json",
        )
        if cp != 200:
            cp, rawp = req(
                "PUT",
                u,
                n8n_key=key,
                body=json.dumps(prune_minimal_put(payload)).encode("utf-8"),
                content_type="application/json",
            )
        wired.append(
            {
                "workflow_id": wf_id,
                "workflow_name": wf.get("name"),
                "ok": cp == 200,
                "http": cp,
            }
        )

    print(
        json.dumps(
            {
                "ok": True,
                "error_handler_workflow_id": error_wf_id,
                "error_handler_name": ERROR_HANDLER_NAME,
                "targets": wired,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
