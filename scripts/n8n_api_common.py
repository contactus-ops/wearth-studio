# -*- coding: utf-8 -*-
# TARGET ROAS 4:1 AT ₹15K/MONTH SPEND — small shared helpers for n8n Cloud REST.
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

_ALLOWED_WORKFLOW_SETTINGS_KEYS = frozenset(
    {
        "saveExecutionProgress",
        "saveManualExecutions",
        "saveDataErrorExecution",
        "saveDataSuccessExecution",
        "executionTimeout",
        "errorWorkflow",
        "timezone",
        "executionOrder",
        "callerPolicy",
        "callerIds",
        "timeSavedPerExecution",
        "availableInMCP",
        "sharedWorkflow",
    }
)


def sanitize_settings(s: Any) -> Dict[str, Any]:
    if not isinstance(s, dict):
        return {}
    return {k: v for k, v in s.items() if k in _ALLOWED_WORKFLOW_SETTINGS_KEYS}


def prune_minimal_put(wf: Dict[str, Any]) -> Dict[str, Any]:
    o: Dict[str, Any] = {
        "name": wf["name"],
        "nodes": wf["nodes"],
        "connections": wf["connections"],
        "settings": sanitize_settings(wf.get("settings")),
    }
    if "active" in wf:
        o["active"] = wf["active"]
    return o


def req(
    method: str,
    url: str,
    *,
    n8n_key: Optional[str] = None,
    body: Optional[bytes] = None,
    content_type: Optional[str] = None,
) -> Tuple[int, str]:
    headers: Dict[str, str] = {"Accept": "application/json"}
    if n8n_key:
        headers["X-N8N-API-KEY"] = n8n_key
    if content_type:
        headers["Content-Type"] = content_type
    r = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(r, timeout=180) as resp:
            return resp.getcode(), resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")


def load_n8n_api_key() -> str:
    key = (os.environ.get("N8N_API_KEY") or "").strip()
    path = (os.environ.get("N8N_API_KEY_FILE") or "").strip()
    if not key and path:
        with open(path, encoding="utf-8") as f:
            key = f.read().strip()
    return key


def try_activate_workflow(base: str, wf_id: str, n8n_key: str) -> bool:
    act_url = f"{base}/api/v1/workflows/{wf_id}"
    for method, aurl, body, ctype in (
        ("POST", f"{base}/api/v1/workflows/{wf_id}/activate", None, None),
        ("PATCH", act_url, json.dumps({"active": True}).encode("utf-8"), "application/json"),
    ):
        code, _ = req(method, aurl, n8n_key=n8n_key, body=body, content_type=ctype)
        if code in (200, 201, 204):
            return True
    return False


def upsert_workflow(base: str, n8n_key: str, wf: Dict[str, Any], workflow_name: str) -> Tuple[str, bool]:
    list_url = f"{base}/api/v1/workflows"
    code, raw_list = req("GET", list_url, n8n_key=n8n_key)
    if code != 200:
        raise RuntimeError(f"list workflows http {code}: {raw_list[:2000]}")

    existing_id: Optional[str] = None
    try:
        arr = json.loads(raw_list)
        rows = arr.get("data") if isinstance(arr, dict) else arr
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict) and row.get("name") == workflow_name:
                    existing_id = row.get("id")
                    break
    except Exception:
        pass

    body_payload = {k: v for k, v in wf.items() if k != "active"}

    if existing_id:
        put_url = f"{base}/api/v1/workflows/{existing_id}"
        cg, rawg = req("GET", put_url, n8n_key=n8n_key)
        if cg == 200:
            try:
                cur = json.loads(rawg)
                cur_s = sanitize_settings(cur.get("settings") or {})
                new_s = sanitize_settings(body_payload.get("settings") or {})
                body_payload["settings"] = {**cur_s, **new_s}
            except Exception:
                pass

    payload = json.dumps(body_payload).encode("utf-8")

    if existing_id:
        code, raw_put = req("PUT", put_url, n8n_key=n8n_key, body=payload, content_type="application/json")
        if code != 200:
            code, raw_put = req(
                "PUT",
                put_url,
                n8n_key=n8n_key,
                body=json.dumps(prune_minimal_put(body_payload)).encode("utf-8"),
                content_type="application/json",
            )
        if code != 200:
            raise RuntimeError(f"PUT workflow http {code}: {raw_put[:8000]}")
        wf_id = str(existing_id)
    else:
        code, raw_post = req("POST", list_url, n8n_key=n8n_key, body=payload, content_type="application/json")
        if code not in (200, 201):
            code, raw_post = req(
                "POST",
                list_url,
                n8n_key=n8n_key,
                body=json.dumps(prune_minimal_put(body_payload)).encode("utf-8"),
                content_type="application/json",
            )
        if code not in (200, 201):
            raise RuntimeError(f"POST workflow http {code}: {raw_post[:8000]}")
        created = json.loads(raw_post)
        wf_id = str(created.get("id") or (created.get("data") or {}).get("id") or "")
        if not wf_id:
            raise RuntimeError("could not parse workflow id")

    activated = try_activate_workflow(base, wf_id, n8n_key)
    return wf_id, activated
