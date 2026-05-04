# -*- coding: utf-8 -*-
"""POST wearth-friday-performance-test webhook and poll n8n executions until success or error."""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

FRIDAY_WORKFLOW_ID = "3GUAuIiPvyxZK09s"
WEBHOOK_PATH = "wearth-friday-performance-test"


def _key() -> str:
    k = (os.environ.get("N8N_API_KEY") or "").strip()
    if not k:
        print(json.dumps({"error": "N8N_API_KEY missing"}))
        sys.exit(1)
    return k


def _get(base: str, path: str, key: str) -> tuple[int, str]:
    req = urllib.request.Request(
        f"{base.rstrip('/')}{path}",
        headers={"X-N8N-API-KEY": key, "Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")


def _post_webhook(base: str, path: str) -> tuple[int, str]:
    url = f"{base.rstrip('/')}/webhook/{path.lstrip('/')}"
    req = urllib.request.Request(url, data=b"{}", method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")


def _parse_iso(s: str):
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def main() -> int:
    base = (os.environ.get("N8N_BASE_URL") or "https://wearthactive.app.n8n.cloud").rstrip("/")
    key = _key()
    t_before = datetime.now(timezone.utc) - timedelta(seconds=3)
    code, body = _post_webhook(base, WEBHOOK_PATH)
    print(json.dumps({"step": "webhook_post", "http": code, "body_preview": body[:400]}, indent=2))
    if code not in (200, 201):
        return 1
    deadline = time.time() + 120
    last = None
    while time.time() < deadline:
        time.sleep(3)
        q = f"/api/v1/executions?workflowId={FRIDAY_WORKFLOW_ID}&limit=15"
        c2, raw = _get(base, q, key)
        if c2 != 200:
            print(json.dumps({"step": "executions_list", "http": c2, "raw": raw[:500]}))
            time.sleep(2)
            continue
        try:
            data = json.loads(raw)
        except Exception:
            print(raw[:500])
            return 1
        rows = data.get("data") if isinstance(data, dict) else data
        if not isinstance(rows, list) or not rows:
            continue
        fresh = []
        for ex in rows:
            if not isinstance(ex, dict):
                continue
            st_iso = ex.get("startedAt") or ex.get("createdAt") or ""
            ts = _parse_iso(str(st_iso))
            if ts and ts >= t_before:
                fresh.append(ex)
        if not fresh:
            continue
        fresh.sort(key=lambda x: str(x.get("id") or ""), reverse=True)
        ex = fresh[0]
        last = ex
        st = str(ex.get("status") or "")
        fid = str(ex.get("finished") or "")
        print(
            json.dumps(
                {
                    "step": "poll",
                    "execution_id": ex.get("id"),
                    "status": st,
                    "finished": fid,
                    "startedAt": ex.get("startedAt"),
                }
            )
        )
        if st in ("success", "error", "crashed", "canceled"):
            ok = st == "success"
            print(json.dumps({"final_status": st, "pass": ok}, indent=2))
            return 0 if ok else 1
    print(json.dumps({"error": "timeout", "last": last}, indent=2))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
