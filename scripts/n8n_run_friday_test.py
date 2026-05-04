# -*- coding: utf-8 -*-
"""POST the Friday loop test webhook, poll until the run finishes, print execution JSON (includeData)."""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

FRIDAY_WF = "3GUAuIiPvyxZK09s"
WEBHOOK_PATH = "wearth-friday-performance-test"
POLL_SEC = 5
MAX_WAIT_SEC = 900


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
        with urllib.request.urlopen(r, timeout=300) as resp:
            return resp.getcode(), resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")


def _list_items(raw: str) -> List[Dict[str, Any]]:
    try:
        data = json.loads(raw)
    except Exception:
        return []
    if isinstance(data, dict) and isinstance(data.get("data"), list):
        return [x for x in data["data"] if isinstance(x, dict)]
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    return []


def _parse_ts(s: Any) -> Optional[datetime]:
    if not s or not isinstance(s, str):
        return None
    try:
        # "2025-05-03T12:00:00.000Z"
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def _mail_status(exec_blob: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {"send_mail_node_found": False}
    rd = exec_blob.get("data") or exec_blob
    result = rd.get("resultData") or {}
    run_data = result.get("runData") or {}
    mail = run_data.get("Send Report Email")
    if not mail:
        out["note"] = "No Send Report Email in runData keys: " + ",".join(
            sorted(run_data.keys())[:12]
        )
        return out
    out["send_mail_node_found"] = True
    try:
        last = mail[-1]
        dat = last.get("data") or []
        first = dat[0] if dat else {}
        j = first.get("json") if isinstance(first, dict) else {}
        out["mail_json_summary"] = j
        # HTTP Request node often puts statusCode / statusMessage on json
        out["http_status_code"] = j.get("statusCode") or j.get("status")
        out["error"] = j.get("error") or j.get("message")
    except Exception as e:
        out["parse_error"] = str(e)
    return out


def main() -> None:
    base = (os.environ.get("N8N_BASE_URL") or "https://wearthactive.app.n8n.cloud").rstrip("/")
    n8n_key = (os.environ.get("N8N_API_KEY") or "").strip()
    if not n8n_key:
        print(json.dumps({"error": "N8N_API_KEY missing"}))
        sys.exit(1)

    hook = f"{base}/webhook/{WEBHOOK_PATH}"
    trigger_before = datetime.now(timezone.utc)
    code, raw_hook = _req("POST", hook, body=b"{}", content_type="application/json")
    print(
        json.dumps(
            {
                "step": "webhook_post",
                "url": hook,
                "http": code,
                "body_preview": raw_hook[:2000],
            },
            indent=2,
        )
    )
    if code not in (200, 201, 202, 204):
        sys.exit(1)

    deadline = time.time() + MAX_WAIT_SEC
    while time.time() < deadline:
        list_url = (
            f"{base}/api/v1/executions"
            f"?workflowId={FRIDAY_WF}&limit=15&includeData=true"
        )
        code_l, raw_l = _req("GET", list_url, n8n_key=n8n_key)
        if code_l != 200:
            print(json.dumps({"step": "list_executions", "http": code_l, "body": raw_l[:2000]}))
            time.sleep(POLL_SEC)
            continue
        rows = _list_items(raw_l)
        cand: Optional[Dict[str, Any]] = None
        for row in rows:
            started = _parse_ts(row.get("startedAt"))
            if started and started >= trigger_before:
                cand = row
                break
        if not cand:
            time.sleep(POLL_SEC)
            continue
        eid = str(cand.get("id") or "")
        st = (cand.get("status") or "").lower()
        if st in ("success", "error", "crashed", "canceled"):
            code_g, raw_g = _req(
                "GET", f"{base}/api/v1/executions/{eid}?includeData=true", n8n_key=n8n_key
            )
            if code_g == 200:
                try:
                    full = json.loads(raw_g)
                except Exception:
                    full = {"raw": raw_g[:50_000]}
                if isinstance(full, dict) and "data" in full:
                    blob = full["data"]
                else:
                    blob = full
                mail = _mail_status(blob if isinstance(blob, dict) else {})
                print(
                    json.dumps(
                        {
                            "step": "execution_finished",
                            "execution_id": eid,
                            "status": st,
                            "startedAt": cand.get("startedAt"),
                            "email_node": mail,
                            "execution_data": blob,
                        },
                        indent=2,
                        default=str,
                    )[:200_000]
                )
            else:
                print(json.dumps({"step": "get_execution", "http": code_g, "body": raw_g[:8000]}))
            return
        time.sleep(POLL_SEC)

    print(
        json.dumps(
            {
                "error": "timeout waiting for terminal execution state",
                "trigger_before": trigger_before.isoformat(),
            }
        )
    )


if __name__ == "__main__":
    main()
