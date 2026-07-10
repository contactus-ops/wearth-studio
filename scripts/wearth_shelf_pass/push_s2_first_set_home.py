#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""S2 — Homepage First Set section: move under hero + verbatim copy."""
from __future__ import annotations

import difflib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "wearth_pdp_v2"))
from theme_api import ThemeApi  # noqa: E402

LIVE = "140256739508"
OUT = ROOT / "data" / "wearth_shelf_pass"
BACKUP = OUT / "backup_live"
HERO_ID = "166055755464f3a9f4"
SECTION_ID = "wearth_first_set_home"


def backup_and_diff(key: str, live: str, patched: str, stamp: str) -> Path:
    BACKUP.mkdir(parents=True, exist_ok=True)
    ext = ".css" if key.endswith(".css") else (".json" if key.endswith(".json") else ".liquid")
    backup_path = BACKUP / f"{key.replace('/', '__')}_{stamp}{ext}"
    backup_path.write_text(live, encoding="utf-8")
    diff = "".join(
        difflib.unified_diff(
            live.splitlines(keepends=True),
            patched.splitlines(keepends=True),
            fromfile=f"live/{key}",
            tofile=f"patched/{key}",
        )
    )
    diff_path = OUT / f"diff_S2_{key.replace('/', '__')}_{stamp}.txt"
    diff_path.write_text(diff, encoding="utf-8")
    print(f"=== DIFF {key} ===")
    print(diff[:3500] if diff else "(no textual diff)")
    return backup_path


def patch_liquid(text: str) -> str:
    old = """    <div class="wearth-first-set-block__copy">
      <p class="wearth-first-set-block__kicker">{{ section.settings.kicker }}</p>
      <h2 class="wearth-first-set-block__heading">{{ section.settings.heading }}</h2>
      <p class="wearth-first-set-block__text">{{ section.settings.text }}</p>
      <div class="wearth-first-set-block__offer">
        <strong>{{ section.settings.price_line }}</strong>
        <span>{{ section.settings.guarantee }}</span>
      </div>
      <a class="wearth-first-set-block__btn" href="{{ section.settings.link | default: product.url }}">{{ section.settings.button_label }}</a>
    </div>"""
    new = """    <div class="wearth-first-set-block__copy">
      {%- if section.settings.kicker != blank -%}
        <p class="wearth-first-set-block__kicker">{{ section.settings.kicker }}</p>
      {%- endif -%}
      <h2 class="wearth-first-set-block__heading">{{ section.settings.heading }}</h2>
      <p class="wearth-first-set-block__text">{{ section.settings.text }}</p>
      {%- if section.settings.price_line != blank or section.settings.guarantee != blank -%}
        <div class="wearth-first-set-block__offer">
          {%- if section.settings.price_line != blank -%}<strong>{{ section.settings.price_line }}</strong>{%- endif -%}
          {%- if section.settings.guarantee != blank -%}<span>{{ section.settings.guarantee }}</span>{%- endif -%}
        </div>
      {%- endif -%}
      <a class="wearth-first-set-block__btn" href="{{ section.settings.link | default: product.url }}">{{ section.settings.button_label }}</a>
    </div>"""
    if old not in text:
        raise SystemExit("first-set liquid: copy block anchor missing")
    return text.replace(old, new, 1)


def patch_css(text: str) -> str:
    # Quieter editorial: drop heavy bordered card feel, keep image-left / text-right + mobile stack
    old_inner = """.wearth-first-set-block__inner {
  width: min(100%, 1080px);
  margin: 0 auto;
  display: grid;
  grid-template-columns: minmax(280px, 420px) minmax(0, 1fr);
  gap: clamp(24px, 4vw, 56px);
  align-items: center;
  background: #fffaf2;
  border: 1px solid var(--wfs-line);
}"""
    new_inner = """.wearth-first-set-block__inner {
  width: min(100%, 1120px);
  margin: 0 auto;
  display: grid;
  grid-template-columns: minmax(280px, 1fr) minmax(0, 1fr);
  gap: clamp(28px, 5vw, 64px);
  align-items: center;
  background: transparent;
  border: 0;
}"""
    if old_inner not in text:
        raise SystemExit("first-set css: inner anchor missing")
    text = text.replace(old_inner, new_inner, 1)

    old_btn = """.wearth-first-set-block__btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  margin-top: 22px;
  min-height: 48px;
  padding: 0 28px;
  border: 1px solid var(--wfs-ink);
  background: var(--wfs-ink);
  color: #fffaf2 !important;
  -webkit-text-fill-color: #fffaf2;
  text-decoration: none;
  font-size: 14px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}"""
    new_btn = """.wearth-first-set-block__btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  margin-top: 28px;
  min-height: 48px;
  padding: 0 28px;
  border: 1px solid var(--wfs-ink);
  background: transparent;
  color: var(--wfs-ink) !important;
  -webkit-text-fill-color: var(--wfs-ink);
  text-decoration: none;
  font-size: 12px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}"""
    if old_btn not in text:
        raise SystemExit("first-set css: btn anchor missing")
    return text.replace(old_btn, new_btn, 1)


def patch_index(text: str) -> str:
    data = json.loads(text)
    order = data.get("order") or []
    if SECTION_ID not in order:
        raise SystemExit("index.json: first set section missing from order")
    if HERO_ID not in order:
        raise SystemExit("index.json: hero missing from order")

    order = [x for x in order if x != SECTION_ID]
    hero_idx = order.index(HERO_ID)
    order.insert(hero_idx + 1, SECTION_ID)
    data["order"] = order

    sec = data["sections"].get(SECTION_ID) or {}
    settings = dict(sec.get("settings") or {})
    settings.update(
        {
            "product_handle": "the-first-set",
            "kicker": "",
            "heading": "Most women are not one size.",
            "text": "The First Set is a bra and biker shorts, sized separately. Pick each. One box, ₹4,999.",
            "price_line": "",
            "guarantee": "",
            "button_label": "See The First Set",
            "link": "shopify://products/the-first-set",
        }
    )
    sec["settings"] = settings
    sec["type"] = "wearth-first-set-block"
    data["sections"][SECTION_ID] = sec
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    api = ThemeApi(LIVE)
    report = {"step": "S2", "stamp": stamp, "files": []}

    for key, fn in [
        ("sections/wearth-first-set-block.liquid", patch_liquid),
        ("assets/wearth-first-set-block.css", patch_css),
        ("templates/index.json", patch_index),
    ]:
        live = api.get_asset(key)
        patched = fn(live)
        if patched == live:
            raise SystemExit(f"no change for {key}")
        backup_and_diff(key, live, patched, stamp)
        api.put_asset(key, patched)
        print(f"PUSHED {key} ({len(live)} -> {len(patched)})")
        report["files"].append({"file": key, "bytes_before": len(live), "bytes_after": len(patched)})

    path = OUT / f"report_S2_{stamp}.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
