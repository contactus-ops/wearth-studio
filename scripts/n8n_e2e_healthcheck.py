# -*- coding: utf-8 -*-
"""
End-to-end checks for WEARTH n8n ↔ Railway web (no n8n edits).

Usage:
  python scripts/n8n_e2e_healthcheck.py
  python scripts/n8n_e2e_healthcheck.py --app-base https://web-production-448c1.up.railway.app

Optional (reads N8N_API_KEY, N8N_BASE_URL from env):
  python scripts/n8n_e2e_healthcheck.py --n8n-list
  python scripts/n8n_e2e_healthcheck.py --trigger-friday-test

Exit 1 if any critical Railway check fails.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, List, Tuple

DEFAULT_APP = "https://web-production-448c1.up.railway.app"
DEFAULT_N8N_BASE = "https://wearthactive.app.n8n.cloud"

EXPECTED_WORKFLOWS = (
    "WEARTH Friday Performance Loop",
    "WEARTH n8n Error Alert",
    "WEARTH SEO Auto-Publisher",
    "WEARTH Instagram Auto",
    "Active Count Guard",
    "WEARTH Monday Ad Generator",
)


def _req(method: str, url: str, *, body: bytes | None = None, headers: Dict[str, str] | None = None, timeout: int = 60) -> Tuple[int, str]:
    h = dict(headers or {})
    if body is not None and "Content-Type" not in h:
        h["Content-Type"] = "application/json"
    r = urllib.request.Request(url, data=body, method=method, headers=h)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.getcode(), resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")


def _json(code: int, raw: str) -> Dict[str, Any]:
    try:
        return {"http": code, "json": json.loads(raw)}
    except Exception:
        return {"http": code, "raw_preview": raw[:2000]}


def check_railway(app: str) -> Tuple[bool, List[Dict[str, Any]]]:
    rows: List[Dict[str, Any]] = []
    ok_all = True

    def add(name: str, code: int, raw: str, ok: bool, detail: Any = None) -> None:
        nonlocal ok_all
        if not ok:
            ok_all = False
        row: Dict[str, Any] = {"check": name, "http": code, "ok": ok}
        if detail is not None:
            row["detail"] = detail
        if not ok and raw:
            row["body_preview"] = raw[:1200]
        rows.append(row)

    c, raw = _req("GET", f"{app.rstrip('/')}/health")
    health_ok = c == 200 and ("status" in raw or '"ok"' in raw)
    add("GET /health", c, raw, health_ok, _json(c, raw).get("json"))

    c2, raw2 = _req("GET", f"{app.rstrip('/')}/api/n8n/health?probe=1")
    j2 = _json(c2, raw2)
    probe_ok = c2 == 200 and isinstance(j2.get("json"), dict) and j2["json"].get("ok") is True
    probe = (j2.get("json") or {}).get("klaviyo_probe") or {}
    if probe_ok and isinstance(probe, dict) and probe.get("ok") is False:
        probe_ok = False
    add("GET /api/n8n/health?probe=1", c2, raw2, probe_ok, j2.get("json"))

    c3, raw3 = _req("GET", f"{app.rstrip('/')}/api/klaviyo/active-count", timeout=45)
    j3 = _json(c3, raw3)
    ac_ok = c3 == 200 and isinstance(j3.get("json"), dict) and j3["json"].get("ok") is True
    add("GET /api/klaviyo/active-count", c3, raw3, ac_ok, j3.get("json"))

    c4, raw4 = _req("GET", f"{app.rstrip('/')}/seo-status", timeout=30)
    add("GET /seo-status", c4, raw4, c4 == 200, _json(c4, raw4).get("json"))

    return ok_all, rows


def check_n8n_list(base: str, api_key: str) -> Tuple[bool, Dict[str, Any]]:
    url = f"{base.rstrip('/')}/api/v1/workflows"
    code, raw = _req("GET", url, headers={"X-N8N-API-KEY": api_key}, timeout=120)
    if code != 200:
        return False, {"http": code, "error": raw[:4000]}
    try:
        data = json.loads(raw)
    except Exception as e:
        return False, {"error": str(e), "raw": raw[:2000]}
    rows = data.get("data") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        return False, {"error": "unexpected list shape"}
    by_name = {str(r.get("name") or ""): r for r in rows if isinstance(r, dict)}
    report: Dict[str, Any] = {"workflow_count": len(rows), "expected": {}}
    all_ok = True
    for name in EXPECTED_WORKFLOWS:
        w = by_name.get(name)
        if not w:
            report["expected"][name] = {"found": False}
            all_ok = False
            continue
        report["expected"][name] = {
            "found": True,
            "active": bool(w.get("active")),
            "id": w.get("id"),
        }
        if not w.get("active"):
            all_ok = False
    return all_ok, report


def trigger_friday_webhook(n8n_base: str) -> Dict[str, Any]:
    path = "wearth-friday-performance-test"
    url = f"{n8n_base.rstrip('/')}/webhook/{path}"
    code, raw = _req("POST", url, body=b"{}", timeout=60)
    return {"url": url, "http": code, "body_preview": raw[:2500]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--app-base", default=os.environ.get("APP_BASE_URL", DEFAULT_APP))
    ap.add_argument("--n8n-list", action="store_true", help="List WEARTH workflows on n8n Cloud (needs N8N_API_KEY)")
    ap.add_argument("--trigger-friday-test", action="store_true", help="POST Friday test webhook (runs full workflow)")
    args = ap.parse_args()

    app = args.app_base.strip()
    print(json.dumps({"step": "railway_checks", "app": app}, indent=2))

    ok, rows = check_railway(app)
    print(json.dumps({"step": "railway_results", "all_ok": ok, "checks": rows}, indent=2, default=str))

    if args.n8n_list:
        key = (os.environ.get("N8N_API_KEY") or "").strip()
        base = (os.environ.get("N8N_BASE_URL") or DEFAULT_N8N_BASE).rstrip("/")
        if not key:
            print(json.dumps({"step": "n8n_list", "error": "N8N_API_KEY not set"}, indent=2))
            ok = False
        else:
            n_ok, rep = check_n8n_list(base, key)
            ok = ok and n_ok
            print(json.dumps({"step": "n8n_list", "all_ok": n_ok, "report": rep}, indent=2, default=str))

    if args.trigger_friday_test:
        base = (os.environ.get("N8N_BASE_URL") or DEFAULT_N8N_BASE).rstrip("/")
        tw = trigger_friday_webhook(base)
        print(json.dumps({"step": "friday_webhook", **tw}, indent=2))
        if tw.get("http") not in (200, 201, 202, 204):
            ok = False

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
