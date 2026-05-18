# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from wearth_sat_fixes.client import HEADERS

BASE = "https://wearthactive.myshopify.com/admin/api/2024-01"
TID = json.loads((ROOT / "data" / "wearth_js_patch" / "state.json").read_text())["work_theme_id"]


def main() -> None:
    with urllib.request.urlopen(
        urllib.request.Request(f"{BASE}/themes/{TID}/assets.json", headers=HEADERS),
        timeout=120,
    ) as r:
        keys = [
            a["key"]
            for a in json.loads(r.read()).get("assets", [])
            if a.get("key", "").endswith(".liquid")
        ]
    hits = []
    for key in keys:
        q = urllib.parse.urlencode({"asset[key]": key})
        body = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(f"{BASE}/themes/{TID}/assets.json?{q}", headers=HEADERS),
                timeout=60,
            ).read()
        ).get("asset", {}).get("value", "")
        for i, line in enumerate(body.splitlines(), 1):
            if "product.title" not in line:
                continue
            if "| json" in line or "| escape" in line:
                continue
            if "<script" in line.lower() or "javascript" in line.lower():
                hits.append((key, i, line.strip()[:140]))
    print("risky product.title in script context:", len(hits))
    for h in hits:
        print(h)


if __name__ == "__main__":
    main()
