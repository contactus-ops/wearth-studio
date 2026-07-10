#!/usr/bin/env python3
"""Verify S2 homepage First Set block at 375px."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "wearth_pdp_v2"))
from theme_api import ThemeApi


def main() -> int:
    idx = json.loads(ThemeApi("140256739508").get_asset("templates/index.json"))
    order = idx["order"]
    settings = idx["sections"]["wearth_first_set_home"]["settings"]
    structure = {
        "order_first3": order[:3],
        "first_set_index": order.index("wearth_first_set_home"),
        "directly_below_hero": order[0] == "166055755464f3a9f4" and order[1] == "wearth_first_set_home",
        "settings": settings,
    }

    results = {"structure": structure, "live": {}}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 375, "height": 812})
        page.goto("https://www.wearthactive.com/", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2500)
        live = page.evaluate(
            """() => {
              const block = document.querySelector('[data-wearth-first-set-block]');
              if (!block) return {found:false};
              const sections = [...document.querySelectorAll('.shopify-section')];
              const blockSection = block.closest('.shopify-section');
              const idx = sections.indexOf(blockSection);
              const heading = block.querySelector('.wearth-first-set-block__heading')?.textContent.trim();
              const text = block.querySelector('.wearth-first-set-block__text')?.textContent.trim();
              const btn = block.querySelector('.wearth-first-set-block__btn');
              const img = block.querySelector('.wearth-first-set-block__image');
              const media = block.querySelector('.wearth-first-set-block__media');
              const copy = block.querySelector('.wearth-first-set-block__copy');
              const mediaTop = media?.getBoundingClientRect().top ?? null;
              const copyTop = copy?.getBoundingClientRect().top ?? null;
              return {
                found: true,
                section_index: idx,
                heading,
                text,
                button: btn?.textContent.trim(),
                href: btn?.getAttribute('href'),
                has_image: !!img,
                image_above_text: mediaTop != null && copyTop != null && mediaTop < copyTop,
                kicker_visible: !!block.querySelector('.wearth-first-set-block__kicker'),
                offer_visible: !!block.querySelector('.wearth-first-set-block__offer'),
                body_has_tencel: document.body.innerText.toLowerCase().includes('tencel'),
              };
            }"""
        )
        results["live"] = live
        browser.close()

    out = ROOT / "data" / "wearth_shelf_pass" / "verify_S2.json"
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(results, indent=2, ensure_ascii=False))
    ok = (
        structure["directly_below_hero"]
        and live.get("heading") == "Most women are not one size."
        and "bra and biker shorts" in (live.get("text") or "")
        and live.get("button") == "See The First Set"
        and live.get("image_above_text")
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
