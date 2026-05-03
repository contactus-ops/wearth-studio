# -*- coding: utf-8 -*-
"""
Update Instagram workflow "Generate Post Content" node: set x-api-key to ANTHROPIC_API_KEY.
Reads N8N_BASE_URL, N8N_API_KEY (or N8N_API_KEY_FILE), ANTHROPIC_API_KEY from environment (`railway run`).

Test run: POST Webhook URL from first Webhook trigger if present (production webhook path).
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

WORKFLOW_ID = "cGbp1fEkP5DoIIsZ"
TARGET_NODE_SUBSTR = "generate post content"


def _req(
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
        with urllib.request.urlopen(r, timeout=120) as resp:
            return resp.getcode(), resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")


def _patch_x_api_key(obj: Any, new_key: str) -> int:
    """Return count of header entries updated."""
    n = 0
    if isinstance(obj, dict):
        # HTTP Request node: headerParameters.parameters[{name,value}]
        hp = obj.get("headerParameters")
        if isinstance(hp, dict):
            params = hp.get("parameters")
            if isinstance(params, list):
                for item in params:
                    if isinstance(item, dict):
                        nm = (item.get("name") or "").strip().lower().replace("_", "-")
                        if nm != "x-api-key":
                            continue
                        item["value"] = new_key
                        n += 1
        # Generic
        for k, v in list(obj.items()):
            if k == "x-api-key" and isinstance(v, str):
                obj[k] = new_key
                n += 1
            else:
                n += _patch_x_api_key(v, new_key)
    elif isinstance(obj, list):
        for el in obj:
            n += _patch_x_api_key(el, new_key)
    return n


def _find_webhook_path(nodes: List[Dict[str, Any]]) -> Optional[str]:
    for node in nodes:
        if not isinstance(node, dict):
            continue
        t = (node.get("type") or "").lower()
        if "webhook" not in t:
            continue
        p = node.get("parameters") or {}
        if isinstance(p, dict):
            path = (p.get("path") or p.get("pathUuid") or "").strip()
            if path:
                return path.lstrip("/")
    return None


def _load_n8n_api_key() -> str:
    key = (os.environ.get("N8N_API_KEY") or "").strip()
    path = (os.environ.get("N8N_API_KEY_FILE") or "").strip()
    if not key and path:
        with open(path, encoding="utf-8") as f:
            key = f.read().strip()
    return key


# workflowSettings schema (public API) uses additionalProperties: false — strip unknown keys.
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


def _sanitize_settings(s: Any) -> Dict[str, Any]:
    if not isinstance(s, dict):
        return {}
    return {k: v for k, v in s.items() if k in _ALLOWED_WORKFLOW_SETTINGS_KEYS}


def _prune_workflow_put(wf: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k in ("name", "nodes", "connections", "settings", "staticData", "pinData"):
        if k not in wf:
            continue
        if k == "settings":
            out[k] = _sanitize_settings(wf[k])
        else:
            out[k] = wf[k]
    return out


def _prune_minimal_put(wf: Dict[str, Any]) -> Dict[str, Any]:
    """Required properties + sanitized settings (API rejects extra settings.* keys)."""
    return {
        "name": wf["name"],
        "nodes": wf["nodes"],
        "connections": wf["connections"],
        "settings": _sanitize_settings(wf.get("settings")),
    }


def main() -> None:
    base = (os.environ.get("N8N_BASE_URL") or "").rstrip("/")
    n8n_key = _load_n8n_api_key()
    anthropic = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()

    if not base:
        print(json.dumps({"error": "N8N_BASE_URL missing — set to https://wearthactive.app.n8n.cloud"}))
        sys.exit(1)
    if not n8n_key:
        print(
            json.dumps(
                {
                    "error": "N8N_API_KEY missing",
                    "hint": "n8n → Settings → n8n API → Create API key, then: railway variables --set \"N8N_API_KEY=...\" --service web "
                    "(or set N8N_API_KEY_FILE to a local path when running outside Railway)",
                }
            )
        )
        sys.exit(1)
    if not anthropic:
        print(json.dumps({"error": "ANTHROPIC_API_KEY missing"}))
        sys.exit(1)

    wf_url = f"{base}/api/v1/workflows/{WORKFLOW_ID}"
    code, raw = _req("GET", wf_url, n8n_key=n8n_key)
    if code != 200:
        print(json.dumps({"step": "GET workflow", "http": code, "body": raw[:4000]}))
        sys.exit(1)

    wf: Dict[str, Any] = json.loads(raw)
    nodes = wf.get("nodes")
    if not isinstance(nodes, list):
        print(json.dumps({"error": "workflow has no nodes array"}))
        sys.exit(1)

    updated_nodes: List[str] = []
    total_patches = 0
    for node in nodes:
        if not isinstance(node, dict):
            continue
        name = (node.get("name") or "").lower()
        if TARGET_NODE_SUBSTR in name:
            c = _patch_x_api_key(node, anthropic)
            total_patches += c
            if c:
                updated_nodes.append(node.get("name") or "?")

    if total_patches == 0:
        # Fallback: patch any HTTP-like node that has x-api-key header
        for node in nodes:
            if not isinstance(node, dict):
                continue
            c = _patch_x_api_key(node, anthropic)
            if c:
                total_patches += c
                updated_nodes.append(node.get("name") or "?")

    if total_patches == 0:
        print(
            json.dumps(
                {
                    "error": "No x-api-key header found to patch",
                    "node_names": [n.get("name") for n in nodes if isinstance(n, dict)],
                }
            )
        )
        sys.exit(1)

    def _put(payload: Dict[str, Any]) -> Tuple[int, str]:
        return _req(
            "PUT",
            wf_url,
            n8n_key=n8n_key,
            body=json.dumps(payload).encode("utf-8"),
            content_type="application/json",
        )

    wf_send = dict(wf)
    wf_send["settings"] = _sanitize_settings(wf_send.get("settings"))
    code, raw_put = _put(wf_send)
    if code != 200:
        code, raw_put = _put(_prune_workflow_put(wf))
    if code != 200:
        code, raw_put = _put(_prune_minimal_put(wf))
    if code != 200:
        print(json.dumps({"step": "PUT workflow", "http": code, "body": raw_put[:8000]}))
        sys.exit(1)

    result: Dict[str, Any] = {
        "ok": True,
        "workflow_id": WORKFLOW_ID,
        "headers_updated": total_patches,
        "nodes_touched": updated_nodes,
        "put_response": json.loads(raw_put) if raw_put.strip().startswith("{") else raw_put[:500],
    }

    # Optional: trigger via webhook
    wh_path = _find_webhook_path(nodes)
    if wh_path:
        # Test URL (editor) then production webhook
        for label, path_prefix in (("test", "/webhook-test/"), ("production", "/webhook/")):
            wh_url = f"{base}{path_prefix}{wh_path}"
            c2, raw_wh = _req("POST", wh_url, n8n_key=None, body=b"{}", content_type="application/json")
            result[f"webhook_{label}"] = {"url": wh_url, "http": c2, "body_preview": raw_wh[:1500]}
            if c2 in (200, 201, 202):
                break
    else:
        result["webhook_test"] = {
            "skipped": True,
            "reason": "No Webhook trigger with path found — run Test workflow from n8n UI",
        }

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
