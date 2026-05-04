"""
Pause one WEARTH campaign and activate another via Meta Graph API v22.0.

Intended to run with Railway-injected env, e.g.:
  railway run -s web python scripts/railway_meta_two_campaigns.py

Meta Graph uses POST (not PATCH) for object field updates; this script POSTs
status=PAUSED / status=ACTIVE as documented for Campaign nodes.
"""
from __future__ import annotations

import json
import os
import sys

import requests

GRAPH = "https://graph.facebook.com/v22.0"
PAUSE_ID = "120245108729160305"
ACTIVATE_ID = "120245108704880305"


def _post_status(cid: str, status: str, token: str) -> requests.Response:
    return requests.post(
        f"{GRAPH}/{cid}",
        data={"status": status, "access_token": token},
        timeout=90,
    )


def _get_campaign(cid: str, token: str) -> dict:
    r = requests.get(
        f"{GRAPH}/{cid}",
        params={"fields": "name,status,effective_status", "access_token": token},
        timeout=90,
    )
    r.raise_for_status()
    return r.json()


def main() -> int:
    token = (os.environ.get("META_ACCESS_TOKEN") or "").strip()
    if not token:
        print("ERROR: META_ACCESS_TOKEN missing (use `railway run` from a linked project).", file=sys.stderr)
        return 1

    results = []

    # 1) Pause
    print("--- POST status=PAUSED ---", PAUSE_ID, flush=True)
    r1 = _post_status(PAUSE_ID, "PAUSED", token)
    print("HTTP", r1.status_code, r1.text[:500], flush=True)
    if r1.status_code not in (200, 201):
        print("Pause failed.", file=sys.stderr)
        return 2
    results.append(("pause", PAUSE_ID, _get_campaign(PAUSE_ID, token)))

    # 2) Activate
    print("\n--- POST status=ACTIVE ---", ACTIVATE_ID, flush=True)
    r2 = _post_status(ACTIVATE_ID, "ACTIVE", token)
    print("HTTP", r2.status_code, r2.text[:500], flush=True)
    if r2.status_code not in (200, 201):
        print("Activate failed.", file=sys.stderr)
        return 3
    results.append(("activate", ACTIVATE_ID, _get_campaign(ACTIVATE_ID, token)))

    print("\n=== Final verified status (GET) ===", flush=True)
    out = {}
    for _, cid, payload in results:
        out[cid] = {
            "name": payload.get("name"),
            "status": payload.get("status"),
            "effective_status": payload.get("effective_status"),
        }
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
