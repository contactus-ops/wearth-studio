# -*- coding: utf-8 -*-
"""Phase 1 — duplicate live theme 140232392884 as Live-JS-Patch."""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "wearth_js_patch"
sys.path.insert(0, str(ROOT / "scripts"))

from wearth_sat_fixes.client import HEADERS, TOKEN  # noqa: E402

LIVE_THEME_ID = "140232392884"
NEW_THEME_NAME = "Live-JS-Patch"
BASE = "https://wearthactive.myshopify.com/admin/api/2024-01"
GROUP_KEYS = (
    "sections/header-group.json",
    "sections/footer-group.json",
)
TIMEOUT = 300


def get_themes() -> list[dict]:
    req = urllib.request.Request(f"{BASE}/themes.json", headers=HEADERS)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode()).get("themes") or []


def create_theme() -> str:
    for t in get_themes():
        if t.get("name") == NEW_THEME_NAME and t.get("role") != "main":
            return str(t["id"])
    body = json.dumps({"theme": {"name": NEW_THEME_NAME, "role": "unpublished"}}).encode()
    req = urllib.request.Request(f"{BASE}/themes.json", data=body, method="POST", headers=HEADERS)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return str(json.loads(r.read().decode())["theme"]["id"])


def list_keys(theme_id: str) -> set[str]:
    req = urllib.request.Request(f"{BASE}/themes/{theme_id}/assets.json", headers=HEADERS)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return {a["key"] for a in json.loads(r.read().decode()).get("assets") or [] if a.get("key")}


def get_asset(theme_id: str, key: str) -> str | None:
    q = urllib.parse.urlencode({"asset[key]": key})
    req = urllib.request.Request(f"{BASE}/themes/{theme_id}/assets.json?{q}", headers=HEADERS)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        asset = json.loads(r.read().decode()).get("asset") or {}
        return asset.get("value")


def put_asset(theme_id: str, key: str, value: str) -> None:
    body = json.dumps({"asset": {"key": key, "value": value}}).encode()
    req = urllib.request.Request(f"{BASE}/themes/{theme_id}/assets.json", data=body, method="PUT", headers=HEADERS)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        if r.status not in (200, 201):
            raise RuntimeError(f"PUT {key} HTTP {r.status}")


def clone_assets(src: str, dest: str) -> list[str]:
    src_keys = sorted(list_keys(src))
    dest_keys = list_keys(dest)
    failed = []
    for i, key in enumerate(src_keys, 1):
        if key in dest_keys:
            continue
        try:
            val = get_asset(src, key)
            if val is None:
                failed.append(key)
                continue
            put_asset(dest, key, val)
        except urllib.error.HTTPError as e:
            failed.append(key)
            print(f"  SKIP {key}: {e.code}")
        if i % 25 == 0:
            print(f"  {i}/{len(src_keys)}")
        time.sleep(0.15)
    return failed


def ensure_groups(src: str, dest: str) -> dict[str, bool]:
    out = {}
    dest_keys = list_keys(dest)
    for key in GROUP_KEYS:
        present = key in dest_keys
        if not present:
            try:
                put_asset(dest, key, get_asset(src, key))
                present = True
            except Exception as e:
                print(f"  WARN copy {key}: {e}")
        out[key] = present
    return out


def main() -> None:
    if not TOKEN:
        raise SystemExit("SHOPIFY_TOKEN missing")
    dest_id = create_theme()
    print(f"Duplicate theme ID: {dest_id}")
    failed = clone_assets(LIVE_THEME_ID, dest_id)
    groups = ensure_groups(LIVE_THEME_ID, dest_id)
    state = {
        "live_theme_id": LIVE_THEME_ID,
        "work_theme_id": dest_id,
        "work_theme_name": NEW_THEME_NAME,
        "failed_assets": failed,
        "header_footer_groups": groups,
        "preview": f"https://wearthactive.myshopify.com/?preview_theme_id={dest_id}",
    }
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")
    print("\nPHASE 1 COMPLETE")
    print(json.dumps(state, indent=2))


if __name__ == "__main__":
    main()
