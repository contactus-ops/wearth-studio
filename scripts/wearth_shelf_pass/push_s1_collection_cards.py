#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""S1 — Collection product cards: fabric under price + First Set badge + compare-at on card-product."""
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


def push_one(api: ThemeApi, key: str, apply_fn, stamp: str) -> dict:
    live = api.get_asset(key)
    backup_path = BACKUP / f"{key.replace('/', '__')}_{stamp}.liquid"
    if key.endswith(".css"):
        backup_path = BACKUP / f"{key.replace('/', '__')}_{stamp}.css"
    BACKUP.mkdir(parents=True, exist_ok=True)
    backup_path.write_text(live, encoding="utf-8")

    patched = apply_fn(live)
    if patched == live:
        raise SystemExit(f"no change produced for {key}")

    diff = "".join(
        difflib.unified_diff(
            live.splitlines(keepends=True),
            patched.splitlines(keepends=True),
            fromfile=f"live/{key}",
            tofile=f"patched/{key}",
        )
    )
    diff_path = OUT / f"diff_S1_{key.replace('/', '__')}_{stamp}.txt"
    diff_path.write_text(diff, encoding="utf-8")
    print(f"=== DIFF {key} ===")
    print(diff[:4000])
    api.put_asset(key, patched)
    print(f"PUSHED {key} ({len(live)} -> {len(patched)})")
    return {
        "file": key,
        "bytes_before": len(live),
        "bytes_after": len(patched),
        "backup": str(backup_path),
        "diff": str(diff_path),
    }


def patch_editorial(text: str) -> str:
    old_title = """            <h2 class="wearth-ec-title">
              <a href="{{ product.url }}">{{ product.title }}</a>
            </h2>"""
    new_title = """            <h2 class="wearth-ec-title">
              <a href="{{ product.url }}">{{ product.title }}</a>
            </h2>
            {%- if product.handle == 'the-first-set' -%}
              <span class="wearth-ec-start-badge">the place to start</span>
            {%- endif -%}"""
    if old_title not in text:
        raise SystemExit("editorial: title anchor missing")
    if "wearth-ec-start-badge" in text:
        raise SystemExit("editorial: badge already present")
    text = text.replace(old_title, new_title, 1)

    old_price = """            <div class="wearth-ec-price">
              {%- if product.compare_at_price > product.price -%}
                <s class="wearth-ec-compare">{{ product.compare_at_price | money }}</s>
              {%- endif -%}
              <span>{{ product.price | money }}</span>
            </div>
            <a class="wearth-ec-cta" href="{{ product.url }}">Explore the piece</a>"""
    new_price = """            <div class="wearth-ec-price">
              {%- if product.compare_at_price > product.price -%}
                <s class="wearth-ec-compare">{{ product.compare_at_price | money }}</s>
              {%- endif -%}
              <span>{{ product.price | money }}</span>
            </div>
            <p class="wearth-ec-fabric">eucalyptus fibre, no polyester</p>
            <a class="wearth-ec-cta" href="{{ product.url }}">Explore the piece</a>"""
    if old_price not in text:
        raise SystemExit("editorial: price+cta anchor missing")
    if "wearth-ec-fabric" in text:
        raise SystemExit("editorial: fabric already present")
    return text.replace(old_price, new_price, 1)


def patch_editorial_css(text: str) -> str:
    if ".wearth-ec-fabric" in text:
        raise SystemExit("editorial css: fabric rule already present")
    block = """
.wearth-ec-fabric {
  margin: 4px 0 0;
  font-size: 11px;
  letter-spacing: 0.04em;
  color: #8a7f72;
  font-weight: 400;
  line-height: 1.35;
}

.wearth-ec-start-badge {
  display: block;
  margin: 4px 0 0;
  font-size: 10px;
  letter-spacing: 0.12em;
  text-transform: lowercase;
  color: #6b5d4f;
  font-weight: 400;
}
"""
    anchor = ".wearth-ec-compare {"
    if anchor not in text:
        raise SystemExit("editorial css: compare anchor missing")
    return text.replace(anchor, block + "\n" + anchor, 1)


def patch_card_product(text: str) -> str:
    old = """        <h3 class="card__heading">
          <a href="{{ wearth_default_url }}" class="full-unstyled-link wearth-phase1-pdp-link" data-wearth-phase1-link>{{ card_product.title }}</a>
        </h3>
        {%- if wearth_card_hook != blank -%}
          <span class="wearth-card-hook" style="display:block;font-size:11px;letter-spacing:.08em;color:#6b5d4f;margin:2px 0 4px;font-weight:500;">{{ wearth_card_hook }}</span>
        {%- endif -%}
        {%- assign wearth_comp_line = '95% Eucalyptus · 0% Polyester' -%}
        <span class="wearth-card-comp" style="display:block;font-size:10px;letter-spacing:.09em;color:#c4a15f;font-weight:500;text-transform:uppercase;margin:0 0 4px;">{{ wearth_comp_line }}</span>
        <div class="card-information">
          <a href="{{ wearth_default_url }}" class="wearth-card-price-link wearth-phase1-pdp-link" data-wearth-phase1-link><span class="price-item">{{ card_product.price | money }}</span></a>
        </div>"""
    new = """        <h3 class="card__heading">
          <a href="{{ wearth_default_url }}" class="full-unstyled-link wearth-phase1-pdp-link" data-wearth-phase1-link>{{ card_product.title }}</a>
        </h3>
        {%- if card_product.handle == 'the-first-set' -%}
          <span class="wearth-card-start-badge" style="display:block;font-size:10px;letter-spacing:.12em;text-transform:lowercase;color:#6b5d4f;font-weight:400;margin:2px 0 0;">the place to start</span>
        {%- endif -%}
        {%- if wearth_card_hook != blank -%}
          <span class="wearth-card-hook" style="display:block;font-size:11px;letter-spacing:.08em;color:#6b5d4f;margin:2px 0 4px;font-weight:500;">{{ wearth_card_hook }}</span>
        {%- endif -%}
        <div class="card-information">
          <a href="{{ wearth_default_url }}" class="wearth-card-price-link wearth-phase1-pdp-link" data-wearth-phase1-link>
            {%- if card_product.compare_at_price > card_product.price -%}
              <s class="price-item price-item--regular" style="opacity:.55;margin-right:.4rem;font-weight:400;">{{ card_product.compare_at_price | money }}</s>
            {%- endif -%}
            <span class="price-item">{{ card_product.price | money }}</span>
          </a>
        </div>
        <span class="wearth-card-comp" style="display:block;font-size:11px;letter-spacing:.04em;color:#8a7f72;font-weight:400;text-transform:none;margin:4px 0 0;">eucalyptus fibre, no polyester</span>"""
    if old not in text:
        raise SystemExit("card-product: content anchor missing")
    return text.replace(old, new, 1)


def main() -> int:
    if LIVE != "140256739508":
        raise SystemExit("refusing: not live theme")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    api = ThemeApi(LIVE)
    reports = []
    reports.append(push_one(api, "sections/wearth-editorial-collection.liquid", patch_editorial, stamp))
    reports.append(push_one(api, "assets/wearth-editorial-collection.css", patch_editorial_css, stamp))
    reports.append(push_one(api, "snippets/card-product.liquid", patch_card_product, stamp))
    report = {
        "step": "S1",
        "stamp": stamp,
        "already_present": [
            "editorial price under title",
            "editorial compare-at when higher",
        ],
        "files": reports,
    }
    path = OUT / f"report_S1_{stamp}.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
