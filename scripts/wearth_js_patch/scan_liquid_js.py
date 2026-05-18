# -*- coding: utf-8 -*-
"""Scan duplicate theme for risky Liquid inside <script> blocks."""
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
THEME_ID = json.loads((ROOT / "data" / "wearth_js_patch" / "state.json").read_text())["work_theme_id"]

SCRIPT_BLOCK = re.compile(r"<script[^>]*>([\s\S]*?)</script>", re.I)
LIQUID = re.compile(r"\{\{[^}]+\}\}")


def get_asset(key: str) -> str:
    q = urllib.parse.urlencode({"asset[key]": key})
    with urllib.request.urlopen(
        urllib.request.Request(f"{BASE}/themes/{THEME_ID}/assets.json?{q}", headers=HEADERS),
        timeout=120,
    ) as r:
        return (json.loads(r.read().decode()).get("asset") or {}).get("value") or ""


def list_liquid_keys() -> list[str]:
    with urllib.request.urlopen(
        urllib.request.Request(f"{BASE}/themes/{THEME_ID}/assets.json", headers=HEADERS),
        timeout=120,
    ) as r:
        keys = [a["key"] for a in json.loads(r.read().decode()).get("assets") or [] if a.get("key")]
    return [k for k in keys if k.endswith(".liquid")]


def main() -> None:
    findings = []
    for key in list_liquid_keys():
        body = get_asset(key)
        for m in SCRIPT_BLOCK.finditer(body):
            block = m.group(1)
            if not LIQUID.search(block):
                continue
            for lm in LIQUID.finditer(block):
                tag = lm.group(0)
                if "| json" in tag or "| escape" in tag or "| url_encode" in tag:
                    continue
                if any(
                    x in tag
                    for x in (
                        "asset_url",
                        "shop.",
                        "routes.",
                        "canonical",
                        "content_for_header",
                        "request.",
                        "settings.",
                        "section.",
                        "block.",
                        "form.",
                        "cart.",
                        "money",
                        "image_url",
                        "img_url",
                        "stylesheet",
                        "script_tag",
                    )
                ):
                    continue
                findings.append({"file": key, "liquid": tag[:120]})
    out = ROOT / "data" / "wearth_js_patch" / "liquid_scan.json"
    out.write_text(json.dumps(findings, indent=2), encoding="utf-8")
    print(f"findings: {len(findings)} -> {out}")
    for f in findings[:40]:
        print(f["file"], f["liquid"])


if __name__ == "__main__":
    main()
