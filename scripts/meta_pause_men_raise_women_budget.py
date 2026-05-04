# -*- coding: utf-8 -*-
"""One-off: pause men's adset, raise women's daily budget (TARGET ROAS 4:1). Run: railway run -- python scripts/meta_pause_men_raise_women_budget.py"""
from __future__ import annotations

import json
import os
import sys

import requests

BASE = "https://graph.facebook.com/v22.0"
MEN_ADSET = "120245228295720305"
WOMEN_ADSET = "120245108705080305"


def main() -> int:
    token = (os.environ.get("META_ACCESS_TOKEN") or "").strip()
    if not token:
        print(json.dumps({"error": "META_ACCESS_TOKEN missing"}))
        return 1

    # Meta Marketing API uses POST for ad set updates (not PATCH).
    r1 = requests.post(
        f"{BASE}/{MEN_ADSET}",
        params={"status": "PAUSED", "access_token": token},
        timeout=60,
    )
    if r1.status_code not in (200, 201):
        print(json.dumps({"step": "pause_men", "http": r1.status_code, "body": r1.text[:2000]}))
        return 1

    r2 = requests.post(
        f"{BASE}/{WOMEN_ADSET}",
        params={"daily_budget": "35000", "access_token": token},
        timeout=60,
    )
    if r2.status_code not in (200, 201):
        print(json.dumps({"step": "women_budget", "http": r2.status_code, "body": r2.text[:2000]}))
        return 1

    g1 = requests.get(
        f"{BASE}/{MEN_ADSET}",
        params={"fields": "id,status,effective_status,daily_budget", "access_token": token},
        timeout=60,
    )
    g2 = requests.get(
        f"{BASE}/{WOMEN_ADSET}",
        params={"fields": "id,status,effective_status,daily_budget", "access_token": token},
        timeout=60,
    )
    out = {
        "ok": True,
        "men": g1.json() if g1.ok else {"error": g1.text[:500]},
        "women": g2.json() if g2.ok else {"error": g2.text[:500]},
    }
    print(json.dumps(out, indent=2))
    m = out.get("men") or {}
    w = out.get("women") or {}
    ok_pause = str(m.get("effective_status") or m.get("status") or "").upper() in (
        "PAUSED",
        "CAMPAIGN_PAUSED",
    ) or str(m.get("status") or "").upper() == "PAUSED"
    ok_budget = str(w.get("daily_budget") or "") == "35000"
    if not ok_pause:
        print("WARNING: men adset effective_status not clearly PAUSED", file=sys.stderr)
    if not ok_budget:
        print("WARNING: women daily_budget not 35000 (minor units)", file=sys.stderr)
    return 0 if ok_pause and ok_budget else 1


if __name__ == "__main__":
    sys.exit(main())
