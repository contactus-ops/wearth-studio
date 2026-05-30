#!/usr/bin/env python3
"""Pause all ad sets under women's campaign 120246658985870305 (bad geo targeting)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

_env = ROOT / ".env"
if _env.exists():
    for ln in _env.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if ln and not ln.startswith("#") and "=" in ln:
            k, v = ln.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

TOKEN = (os.environ.get("META_ACCESS_TOKEN") or "").strip()
GRAPH = f"https://graph.facebook.com/{(os.environ.get('META_GRAPH_VERSION') or 'v22.0').strip()}"
CAMPAIGN_ID = "120246658985870305"


def main() -> int:
    if not TOKEN:
        print(json.dumps({"ok": False, "error": "META_ACCESS_TOKEN not set"}))
        return 1
    r = requests.get(
        f"{GRAPH}/{CAMPAIGN_ID}/adsets",
        params={"fields": "id,name,status,effective_status", "access_token": TOKEN, "limit": 100},
        timeout=60,
    )
    data = r.json()
    if r.status_code != 200:
        print(json.dumps({"ok": False, "error": data}))
        return 1
    adsets = data.get("data") or []
    paused = []
    for a in adsets:
        aid = a.get("id")
        if not aid:
            continue
        st = (a.get("effective_status") or a.get("status") or "").upper()
        if st in ("PAUSED", "DELETED", "ARCHIVED"):
            paused.append({"id": aid, "name": a.get("name"), "skipped": st})
            continue
        pr = requests.post(
            f"{GRAPH}/{aid}",
            data={"status": "PAUSED", "access_token": TOKEN},
            timeout=60,
        )
        body = pr.json() if pr.text else {}
        paused.append(
            {
                "id": aid,
                "name": a.get("name"),
                "http": pr.status_code,
                "ok": pr.status_code == 200 and body.get("success", True),
                "response": body,
            }
        )
    print(json.dumps({"ok": True, "campaign_id": CAMPAIGN_ID, "adsets": paused}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
