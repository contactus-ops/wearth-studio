"""
Unpause WEARTH parent campaign and print ad set statuses (Graph API).
Uses META_ACCESS_TOKEN from the environment (same as Railway).

Usage (PowerShell):
  $env:META_ACCESS_TOKEN = "..."; python scripts/meta_unpause_campaign.py
"""
from __future__ import annotations

import os
import sys

import requests

GRAPH = "https://graph.facebook.com/v22.0"
CAMPAIGN_ID = "120245108704880305"
ADSET_IDS = ("120245108705080305", "120245228295720305")


def main() -> int:
    token = (os.environ.get("META_ACCESS_TOKEN") or "").strip()
    if not token:
        print("ERROR: set META_ACCESS_TOKEN in the environment.", file=sys.stderr)
        return 1

    r = requests.post(
        f"{GRAPH}/{CAMPAIGN_ID}",
        data={"status": "ACTIVE", "access_token": token},
        timeout=60,
    )
    print("Campaign POST (status=ACTIVE):", r.status_code)
    try:
        print(r.json())
    except Exception:
        print(r.text[:800])

    for aid in ADSET_IDS:
        s = requests.get(
            f"{GRAPH}/{aid}",
            params={
                "fields": "name,status,effective_status",
                "access_token": token,
            },
            timeout=60,
        )
        print(f"\n--- Ad set {aid} ---")
        print(s.status_code, s.json() if s.ok else s.text[:500])

    return 0 if r.ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
