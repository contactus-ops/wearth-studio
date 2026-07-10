#!/usr/bin/env python3
"""Verify S3 sticky Add to Bag at 375px on First Set + Off Duty Short."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
URLS = [
    ("the-first-set", "https://www.wearthactive.com/products/the-first-set"),
    ("the-off-duty-short", "https://www.wearthactive.com/products/the-off-duty-short"),
]


def check(page, name: str, url: str) -> dict:
    page_errors = []
    page.on("pageerror", lambda e: page_errors.append(str(e)))
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(2500)

    base = page.evaluate(
        """() => {
          const bar = document.querySelector('[data-wearth-sticky-bag]');
          const atc = document.querySelector('[data-wearth-pdp-mobile-atc]');
          const btn = bar && bar.querySelector('[data-wearth-sticky-submit]');
          const price = bar && bar.querySelector('[data-wearth-sticky-price]');
          const formId = btn && btn.getAttribute('form');
          const form = formId ? document.getElementById(formId) : null;
          return {
            bar_present: !!bar,
            atc_present: !!atc,
            btn_label: btn ? btn.textContent.trim() : null,
            form_attr: formId,
            form_exists: !!form,
            price_initial: price ? price.textContent.trim() : null,
            visible_before_scroll: bar ? bar.classList.contains('is-visible') : false,
            z_index: bar ? getComputedStyle(bar).zIndex : null,
          };
        }"""
    )

    # Scroll past ATC
    page.evaluate(
        """() => {
          const atc = document.querySelector('[data-wearth-pdp-mobile-atc]');
          if (atc) {
            const y = atc.getBoundingClientRect().top + window.scrollY + atc.offsetHeight + 80;
            window.scrollTo(0, y);
          } else {
            window.scrollTo(0, 1200);
          }
        }"""
    )
    page.wait_for_timeout(800)

    after = page.evaluate(
        """() => {
          const bar = document.querySelector('[data-wearth-sticky-bag]');
          const price = bar && bar.querySelector('[data-wearth-sticky-price]');
          const btn = bar && bar.querySelector('[data-wearth-sticky-submit]');
          const cs = bar ? getComputedStyle(bar) : null;
          return {
            visible_after_scroll: bar ? bar.classList.contains('is-visible') : false,
            aria_hidden: bar ? bar.getAttribute('aria-hidden') : null,
            display: cs ? cs.display : null,
            z_index: cs ? cs.zIndex : null,
            price: price ? price.textContent.trim() : null,
            btn_disabled: btn ? btn.disabled : null,
          };
        }"""
    )

    # Variant change probe for First Set (selects)
    variant_probe = {}
    if name == "the-first-set":
        variant_probe = page.evaluate(
            """() => {
              const selects = [...document.querySelectorAll('variant-selects select, variant-radios select')];
              const priceBefore = document.querySelector('[data-wearth-sticky-price]')?.textContent.trim();
              const form = document.querySelector('form[id^="product-form"]') || document.querySelector('form[action*="/cart/add"]');
              const idBefore = form && form.querySelector('input[name="id"]')?.value;
              if (selects.length >= 2) {
                const s0 = selects[0];
                const s1 = selects[1];
                if (s0.options.length > 1) {
                  s0.selectedIndex = Math.min(1, s0.options.length - 1);
                  s0.dispatchEvent(new Event('change', { bubbles: true }));
                }
                if (s1.options.length > 1) {
                  s1.selectedIndex = Math.min(1, s1.options.length - 1);
                  s1.dispatchEvent(new Event('change', { bubbles: true }));
                }
              }
              // also try radios
              const radios = [...document.querySelectorAll('variant-radios fieldset input[type="radio"]')];
              if (radios.length > 2) {
                const unchecked = radios.find(r => !r.checked);
                if (unchecked) {
                  unchecked.click();
                  unchecked.dispatchEvent(new Event('change', { bubbles: true }));
                }
              }
              return {
                select_count: selects.length,
                price_before: priceBefore,
                id_before: idBefore,
              };
            }"""
        )
        page.wait_for_timeout(500)
        variant_probe["after"] = page.evaluate(
            """() => {
              const form = document.getElementById(document.querySelector('[data-wearth-sticky-submit]')?.getAttribute('form'));
              return {
                price_after: document.querySelector('[data-wearth-sticky-price]')?.textContent.trim(),
                id_after: form && form.querySelector('input[name="id"]')?.value,
              };
            }"""
        )

    return {
        "name": name,
        "url": url,
        "base": base,
        "after_scroll": after,
        "variant_probe": variant_probe,
        "page_errors": page_errors[:10],
        "pass": bool(
            base.get("bar_present")
            and base.get("btn_label") == "Add to Bag"
            and base.get("form_exists")
            and after.get("visible_after_scroll")
            and after.get("display") == "flex"
        ),
    }


def main() -> int:
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 375, "height": 812})
        for name, url in URLS:
            results.append(check(page, name, url))
        browser.close()

    out = {
        "results": results,
        "all_pass": all(r["pass"] for r in results),
    }
    path = ROOT / "data" / "wearth_shelf_pass" / "verify_S3.json"
    path.write_text(json.dumps(out, indent=2, ensure_ascii=True), encoding="utf-8")
    print(json.dumps(out, indent=2, ensure_ascii=True))
    return 0 if out["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
