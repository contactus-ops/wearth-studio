# -*- coding: utf-8 -*-
"""Playwright console QA on Live-JS-Patch preview theme."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "wearth_js_patch" / "qa"
DATA.mkdir(parents=True, exist_ok=True)

PREVIEW = "https://wearthactive.myshopify.com"
THEME_ID = json.loads((ROOT / "data" / "wearth_js_patch" / "state.json").read_text())[
    "work_theme_id"
]
PW = f"?preview_theme_id={THEME_ID}"

PAGES = [
    ("01-home", "/"),
    ("02-women", "/collections/women"),
    ("03-men", "/collections/men"),
    ("04-pdp-align", "/products/align-sports-bra"),
    ("05-pdp-apostrophe", None),  # resolved at runtime
    ("06-cart-drawer", "/products/align-sports-bra"),
]


def preview_url(path: str) -> str:
    sep = "&" if "?" in path else "?"
    return f"{PREVIEW}{path}{sep}preview_theme_id={THEME_ID}"


def main() -> None:
    from playwright.sync_api import sync_playwright

    report = {"theme_id": THEME_ID, "pages": [], "all_clean": True}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        desktop = browser.new_context(viewport={"width": 1280, "height": 800})
        mobile = browser.new_context(
            viewport={"width": 390, "height": 844},
            user_agent=(
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
            ),
        )

        apostrophe_url = None
        page = desktop.new_page()
        page.goto(preview_url("/collections/women"), wait_until="networkidle", timeout=90000)
        links = page.eval_on_selector_all(
            "a[href*='/products/']",
            "els => els.map(e => e.href).filter(Boolean)",
        )
        for href in links:
            card = page.locator(f"a[href='{href}']").first
            try:
                title = card.inner_text(timeout=2000)
            except Exception:
                continue
            if "'" in title or "\u2019" in title:
                apostrophe_url = href.split("?")[0]
                break
        page.close()

        if not apostrophe_url:
            apostrophe_url = preview_url("/collections/all")

        for name, path in PAGES:
            if name == "05-pdp-apostrophe":
                url = (
                    apostrophe_url + PW.replace("?", "&")
                    if "?" in apostrophe_url
                    else apostrophe_url + PW
                )
            elif name == "06-cart-drawer":
                url = preview_url(path)
            else:
                url = preview_url(path or "/")

            for ctx_name, ctx in [("desktop", desktop), ("mobile", mobile)]:
                page = ctx.new_page()
                errors: list[str] = []

                def on_console(msg):
                    if msg.type in ("error", "warning"):
                        errors.append(f"[{msg.type}] {msg.text}")

                def on_pageerror(exc):
                    errors.append(f"[pageerror] {exc}")

                page.on("console", on_console)
                page.on("pageerror", on_pageerror)
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=90000)
                    page.wait_for_timeout(2500)
                    if name == "06-cart-drawer":
                        btn = page.locator(
                            "button[name='add'], [data-add-to-cart], .product-form__submit"
                        ).first
                        if btn.count():
                            btn.click(timeout=10000)
                            page.wait_for_timeout(2000)
                except Exception as e:
                    errors.append(f"[navigation] {e}")

                shot = DATA / f"{name}-{ctx_name}.png"
                page.screenshot(path=str(shot), full_page=False)
                page.close()

                clean = len(errors) == 0
                if not clean:
                    report["all_clean"] = False
                report["pages"].append(
                    {
                        "name": name,
                        "context": ctx_name,
                        "url": url,
                        "clean": clean,
                        "errors": errors,
                        "screenshot": str(shot.relative_to(ROOT)),
                    }
                )

        browser.close()

    (DATA / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
