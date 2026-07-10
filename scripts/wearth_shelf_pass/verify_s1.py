#!/usr/bin/env python3
"""Verify S1 at 375px viewport."""
from __future__ import annotations

import json
import sys
import urllib.request

from playwright.sync_api import sync_playwright

URLS = [
    ("women", "https://www.wearthactive.com/collections/women"),
    ("home", "https://www.wearthactive.com/"),
]


def main() -> int:
    # CSS sanity
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2] / "scripts" / "wearth_pdp_v2"))
    from theme_api import ThemeApi

    css = ThemeApi("140256739508").get_asset("assets/wearth-editorial-collection.css")
    price_ok = ".wearth-ec-price" in css and ".wearth-ec-fabric" in css and ".wearth-ec-start-badge" in css
    # ensure price block still closed
    idx = css.find(".wearth-ec-price")
    chunk = css[idx : idx + 500]
    print("CSS_CHUNK:\n", chunk)

    results = {"css_ok": price_ok, "pages": []}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 375, "height": 812})
        page.on("pageerror", lambda err: results.setdefault("console_errors", []).append(str(err)))
        page.on("console", lambda msg: results.setdefault("console_msgs", []).append(f"{msg.type}: {msg.text}") if msg.type == "error" else None)

        for name, url in URLS:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(2500)
            data = page.evaluate(
                """() => {
                  const fabric = [...document.querySelectorAll('.wearth-ec-fabric, .wearth-card-comp')]
                    .map(el => el.textContent.trim());
                  const badges = [...document.querySelectorAll('.wearth-ec-start-badge, .wearth-card-start-badge')]
                    .map(el => el.textContent.trim());
                  const prices = [...document.querySelectorAll('.wearth-ec-price, .price-item')]
                    .slice(0, 6)
                    .map(el => el.textContent.replace(/\\s+/g,' ').trim());
                  const compares = [...document.querySelectorAll('.wearth-ec-compare, .price-item--regular')]
                    .map(el => el.textContent.trim());
                  return {
                    fabric_count: fabric.length,
                    fabric_sample: fabric.slice(0, 3),
                    badge_count: badges.length,
                    badges,
                    price_sample: prices,
                    compare_sample: compares.slice(0, 3),
                    has_tencel: document.body.innerText.toLowerCase().includes('tencel'),
                    has_lyocell: document.body.innerText.toLowerCase().includes('lyocell'),
                  };
                }"""
            )
            data["url"] = url
            data["name"] = name
            results["pages"].append(data)
        browser.close()

    out = __import__("pathlib").Path(__file__).resolve().parents[2] / "data" / "wearth_shelf_pass" / "verify_S1.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))
    ok = price_ok and all(p["fabric_count"] > 0 for p in results["pages"])
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
