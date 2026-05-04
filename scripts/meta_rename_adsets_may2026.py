# -*- coding: utf-8 -*-
"""Rename WEARTH Plastic Feel ad sets on Meta (Graph v22.0). TARGET ROAS 4:1."""
from __future__ import annotations

import json
import os
import sys

import requests

GRAPH = "https://graph.facebook.com/v22.0"
TOKEN = (os.environ.get("META_ACCESS_TOKEN") or "").strip()

RENAME = (
    ("120245108705080305", "WEARTH — Plastic Feel — Women — May 2026"),
    ("120245228295720305", "WEARTH — Plastic Feel — Men — May 2026"),
)


def main() -> int:
    if not TOKEN:
        print("META_ACCESS_TOKEN missing", file=sys.stderr)
        return 1
    out = []
    for adset_id, name in RENAME:
        r = requests.post(
            f"{GRAPH}/{adset_id}",
            params={"access_token": TOKEN},
            data={"name": name},
            timeout=60,
        )
        try:
            j = r.json()
        except Exception:
            j = {"raw": r.text[:500]}
        ok = r.status_code == 200 and not j.get("error")
        out.append({"adset_id": adset_id, "http": r.status_code, "body": j, "ok": ok})
        if not ok:
            print(json.dumps(out, indent=2))
            return 1
        g = requests.get(
            f"{GRAPH}/{adset_id}",
            params={"fields": "name", "access_token": TOKEN},
            timeout=30,
        )
        out[-1]["verified_name"] = (g.json() or {}).get("name")
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
