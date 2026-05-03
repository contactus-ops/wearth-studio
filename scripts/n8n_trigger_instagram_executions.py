# -*- coding: utf-8 -*-
# TARGET ROAS 4:1 AT ₹15K/MONTH SPEND — Fire manual Instagram workflow runs spaced apart.
"""
Triggers WEARTH Instagram Auto (default workflow id cGbp1fEkP5DoIIsZ) via production webhook POST.

Requires N8N_BASE_URL, N8N_API_KEY. Optionally WEBHOOK_PATH if GET workflow fails to resolve path.

Usage: python scripts/n8n_trigger_instagram_executions.py [--minutes 10]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_WF = "cGbp1fEkP5DoIIsZ"


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


def _load_key() -> str:
    k = (os.environ.get("N8N_API_KEY") or "").strip()
    p = (os.environ.get("N8N_API_KEY_FILE") or "").strip()
    if not k and p:
        with open(p, encoding="utf-8") as f:
            k = f.read().strip()
    return k


def _find_webhook_path(nodes: List[Any]) -> Optional[str]:
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=10.0, help="Spacing between runs")
    ap.add_argument("--workflow-id", default=os.environ.get("N8N_INSTAGRAM_WORKFLOW_ID", DEFAULT_WF))
    args = ap.parse_args()

    base = (os.environ.get("N8N_BASE_URL") or "https://wearthactive.app.n8n.cloud").rstrip("/")
    key = _load_key()
    if not key:
        print(json.dumps({"error": "N8N_API_KEY missing"}))
        sys.exit(1)

    path = (os.environ.get("N8N_INSTAGRAM_WEBHOOK_PATH") or "").strip()
    if not path:
        code, raw = _req("GET", f"{base}/api/v1/workflows/{args.workflow_id}", n8n_key=key)
        if code != 200:
            print(json.dumps({"error": "GET workflow failed", "http": code, "body": raw[:2000]}))
            sys.exit(1)
        wf = json.loads(raw)
        nodes = wf.get("nodes") or []
        path = _find_webhook_path(nodes) or ""
        if not path:
            print(
                json.dumps(
                    {
                        "error": "No webhook path on workflow — set N8N_INSTAGRAM_WEBHOOK_PATH",
                        "hint": "Add a Webhook trigger or export path from n8n UI",
                    }
                )
            )
            sys.exit(1)

    url = f"{base}/webhook/{path}"
    out: List[Dict[str, Any]] = []
    for i in range(3):
        if i:
            time.sleep(args.minutes * 60.0)
        code, raw = _req(
            "POST",
            url,
            n8n_key=None,
            body=b"{}",
            content_type="application/json",
        )
        execution_id = None
        try:
            jd = json.loads(raw)
            if isinstance(jd, dict):
                execution_id = jd.get("executionId") or jd.get("execution_id")
        except Exception:
            pass
        if execution_id is None and raw:
            m = re.search(r'"executionId"\s*:\s*"([^"]+)"', raw)
            if m:
                execution_id = m.group(1)
        out.append(
            {
                "run_index": i + 1,
                "http": code,
                "execution_id": execution_id,
                "body_preview": raw[:1200],
            }
        )

    print(json.dumps({"ok": True, "webhook_url": url, "runs": out}, indent=2))


if __name__ == "__main__":
    main()
