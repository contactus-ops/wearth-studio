#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""S3 — Sticky mobile Add to Bag bar on PDPs (un-kill + scroll reveal + form submit)."""
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


def backup_and_diff(key: str, live: str, patched: str, stamp: str) -> None:
    BACKUP.mkdir(parents=True, exist_ok=True)
    ext = ".css" if key.endswith(".css") else ".liquid"
    (BACKUP / f"{key.replace('/', '__')}_{stamp}{ext}").write_text(live, encoding="utf-8")
    diff = "".join(
        difflib.unified_diff(
            live.splitlines(keepends=True),
            patched.splitlines(keepends=True),
            fromfile=f"live/{key}",
            tofile=f"patched/{key}",
        )
    )
    (OUT / f"diff_S3_{key.replace('/', '__')}_{stamp}.txt").write_text(diff, encoding="utf-8")
    print(f"=== DIFF {key} ===")
    try:
        print(diff[:4500])
    except UnicodeEncodeError:
        print(diff[:4500].encode("ascii", "replace").decode("ascii"))


def patch_foundation_css(text: str) -> str:
    # Remove wearth-sticky-checkout from the global kill list (keep other sticky killers)
    old_kill = """.stickyCart,
.stickyCart-active,
.sticky-cart,
.sticky-add-to-cart,
.sticky-product-bar,
#sticky-cart,
#sticky-add-to-cart,
[data-sticky-cart],
[data-sticky-add-to-cart],
.product-sticky-cart,
.product-sticky-bar,
.wearth-sticky-checkout,
.SCC,
.scc-sticky-cart {
  display: none !important;
  visibility: hidden !important;
  pointer-events: none !important;
}"""
    new_kill = """.stickyCart,
.stickyCart-active,
.sticky-cart,
.sticky-add-to-cart,
.sticky-product-bar,
#sticky-cart,
#sticky-add-to-cart,
[data-sticky-cart],
[data-sticky-add-to-cart],
.product-sticky-cart,
.product-sticky-bar,
.SCC,
.scc-sticky-cart {
  display: none !important;
  visibility: hidden !important;
  pointer-events: none !important;
}"""
    if old_kill not in text:
        raise SystemExit("foundation css: sticky kill block anchor missing")
    text = text.replace(old_kill, new_kill, 1)

    # Replace duplicated V2/V3 sticky rules with one scroll-gated rule
    old_v2 = """/* WEARTH STICKY CHECKOUT V2 */
.wearth-sticky-checkout{display:none;}
@media screen and (max-width:749px){
  .template-product .wearth-sticky-checkout{position:fixed;left:8px;right:8px;bottom:8px;z-index:2140;display:flex;align-items:center;justify-content:space-between;gap:10px;padding:8px 10px;border:1px solid rgba(215,176,106,.5);border-radius:14px;background:rgba(26,22,18,.80);backdrop-filter:blur(6px);box-shadow:0 10px 28px rgba(0,0,0,.22);} 
  .wearth-sticky-checkout__meta{display:flex;flex-direction:column;min-width:0;}
  .wearth-sticky-checkout__title{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:#efe5d8;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:42vw;}
  .wearth-sticky-checkout__price{font-size:12px;letter-spacing:.06em;color:#f4e8d8;font-weight:600;}
  .wearth-sticky-checkout__btn{border:1px solid rgba(215,176,106,.84);border-radius:999px;background:linear-gradient(125deg,rgba(33,28,24,.40),rgba(23,26,24,.27));color:#f4ebdc;-webkit-text-fill-color:#f4ebdc;font-size:10px;letter-spacing:.12em;text-transform:uppercase;font-weight:600;padding:.62rem .78rem;min-height:38px;}
}


/* WEARTH STICKY CHECKOUT V3 */
.wearth-sticky-checkout{display:none;}
@media screen and (max-width:749px){
  .template-product .wearth-sticky-checkout{position:fixed;left:8px;right:8px;bottom:8px;z-index:2140;display:flex;align-items:center;justify-content:space-between;gap:10px;padding:8px 10px;border:1px solid rgba(215,176,106,.5);border-radius:14px;background:rgba(26,22,18,.80);backdrop-filter:blur(6px);box-shadow:0 10px 28px rgba(0,0,0,.22);} 
  .wearth-sticky-checkout__meta{display:flex;flex-direction:column;min-width:0;}
  .wearth-sticky-checkout__title{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:#efe5d8;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:42vw;}
  .wearth-sticky-checkout__price{font-size:12px;letter-spacing:.06em;color:#f4e8d8;font-weight:600;}
  .wearth-sticky-checkout__btn{border:1px solid rgba(215,176,106,.84);border-radius:999px;background:linear-gradient(125deg,rgba(33,28,24,.40),rgba(23,26,24,.27));color:#f4ebdc;-webkit-text-fill-color:#f4ebdc;font-size:10px;letter-spacing:.12em;text-transform:uppercase;font-weight:600;padding:.62rem .78rem;min-height:38px;}
}"""
    new_sticky = """/* WEARTH STICKY ADD-TO-BAG — mobile only, scroll-gated */
.wearth-sticky-checkout{display:none !important;}
@media screen and (max-width:749px){
  .template-product .wearth-sticky-checkout.is-visible{
    position:fixed;
    left:8px;
    right:8px;
    bottom:8px;
    z-index:3200;
    display:flex !important;
    align-items:center;
    justify-content:space-between;
    gap:10px;
    padding:8px 10px;
    border:1px solid rgba(215,176,106,.5);
    border-radius:14px;
    background:rgba(26,22,18,.92);
    backdrop-filter:blur(6px);
    box-shadow:0 10px 28px rgba(0,0,0,.22);
    visibility:visible !important;
    pointer-events:auto !important;
  }
  .wearth-sticky-checkout__meta{display:flex;flex-direction:column;min-width:0;}
  .wearth-sticky-checkout__title{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:#efe5d8;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:42vw;}
  .wearth-sticky-checkout__price{font-size:12px;letter-spacing:.06em;color:#f4e8d8;font-weight:600;}
  .wearth-sticky-checkout__btn{border:1px solid rgba(215,176,106,.84);border-radius:999px;background:linear-gradient(125deg,rgba(33,28,24,.40),rgba(23,26,24,.27));color:#f4ebdc;-webkit-text-fill-color:#f4ebdc;font-size:10px;letter-spacing:.12em;text-transform:uppercase;font-weight:600;padding:.62rem .78rem;min-height:38px;cursor:pointer;}
}"""
    if old_v2 not in text:
        raise SystemExit("foundation css: sticky V2/V3 block missing")
    return text.replace(old_v2, new_sticky, 1)


def patch_main_product(text: str) -> str:
    old = """<div class="wearth-sticky-checkout" aria-hidden="true">
  <div class="wearth-sticky-checkout__meta">
    <span class="wearth-sticky-checkout__title">{{ product.title }}</span>
    <span class="wearth-sticky-checkout__price">{{ product.selected_or_first_available_variant.price | money }}</span>
  </div>
  <form method="post" action="/cart/add" class="wearth-sticky-checkout__form" data-wearth-sticky-sync>
    <input type="hidden" name="id" value="{{ product.selected_or_first_available_variant.id }}">
    <input type="hidden" name="quantity" value="1">
    <button type="submit" name="add" class="wearth-sticky-checkout__btn">Add to cart</button>
  </form>
</div>"""
    new = """<div class="wearth-sticky-checkout" data-wearth-sticky-bag aria-hidden="true">
  <div class="wearth-sticky-checkout__meta">
    <span class="wearth-sticky-checkout__title">{{ product.title }}</span>
    <span class="wearth-sticky-checkout__price" data-wearth-sticky-price>{{ product.selected_or_first_available_variant.price | money }}</span>
  </div>
  <button
    type="submit"
    name="add"
    form="{{ product_form_id }}"
    class="wearth-sticky-checkout__btn"
    data-wearth-sticky-submit
    {% if product.selected_or_first_available_variant.available == false %}disabled{% endif %}
  >Add to Bag</button>
</div>
<script type="application/json" data-wearth-sticky-variants>
{{ product.variants | json }}
</script>
{%- comment -%} WEARTH_STICKY_BAG_SCROLL {%- endcomment -%}
<script>
(function () {
  var bar = document.querySelector('[data-wearth-sticky-bag]');
  if (!bar) return;
  var priceEl = bar.querySelector('[data-wearth-sticky-price]');
  var submitBtn = bar.querySelector('[data-wearth-sticky-submit]');
  var formId = {{ product_form_id | json }};
  var sectionKey = {{ section.id | json }};
  var productKey = {{ product.id | json }};
  var variants = [];
  try {
    var raw = document.querySelector('[data-wearth-sticky-variants]');
    variants = raw ? JSON.parse(raw.textContent || '[]') : [];
  } catch (e) { variants = []; }

  function money(cents) {
    try {
      if (window.Shopify && Shopify.formatMoney) {
        return Shopify.formatMoney(cents, {{ shop.money_format | json }});
      }
    } catch (e2) {}
    return '₹' + (Number(cents) / 100).toFixed(0);
  }

  function root() {
    return document.querySelector(
      'variant-radios[data-section="' + sectionKey + '"][data-product="' + productKey + '"],' +
      'variant-selects[data-section="' + sectionKey + '"][data-product="' + productKey + '"]'
    );
  }

  function selectedOptions() {
    var r = root();
    if (!r) return [];
    if (r.tagName.toLowerCase() === 'variant-selects') {
      return Array.from(r.querySelectorAll('select')).map(function (sel) { return sel.value; });
    }
    return Array.from(r.querySelectorAll('fieldset')).map(function (fieldset) {
      var checked = fieldset.querySelector('input:checked');
      return checked ? checked.value : '';
    });
  }

  function syncFromSelection() {
    var options = selectedOptions();
    var match = variants.find(function (variant) {
      return variant.options && variant.options.every(function (opt, idx) {
        return String(opt) === String(options[idx]);
      });
    });
    if (!match) return;
    var form = document.getElementById(formId);
    if (form) {
      var input = form.querySelector('input[name="id"]');
      if (input) {
        input.disabled = false;
        input.value = String(match.id);
      }
    }
    if (priceEl) priceEl.textContent = money(match.price);
    if (submitBtn) submitBtn.disabled = !match.available;
  }

  function setVisible(on) {
    bar.classList.toggle('is-visible', !!on);
    bar.setAttribute('aria-hidden', on ? 'false' : 'true');
  }

  function watchAtc() {
    var atc =
      document.querySelector('[data-wearth-pdp-mobile-atc]') ||
      document.querySelector('.wearth-pdp-desktop-atc-slot') ||
      document.querySelector('#' + formId + ' [data-add-to-cart], #' + formId + ' button[name="add"]');
    if (!atc) {
      setVisible(false);
      return;
    }
    if (!('IntersectionObserver' in window)) {
      setVisible(true);
      return;
    }
    var io = new IntersectionObserver(function (entries) {
      var entry = entries[0];
      if (!entry) return;
      setVisible(!entry.isIntersecting);
    }, { threshold: 0, rootMargin: '0px' });
    io.observe(atc);
  }

  var r = root();
  if (r) r.addEventListener('change', syncFromSelection);
  document.addEventListener('change', function (evt) {
    if (!evt.target) return;
    if (evt.target.closest('variant-radios, variant-selects')) syncFromSelection();
  });
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () {
      syncFromSelection();
      watchAtc();
    });
  } else {
    syncFromSelection();
    watchAtc();
  }
})();
</script>"""
    if old not in text:
        raise SystemExit("main-product: sticky checkout block missing")
    return text.replace(old, new, 1)


def main() -> int:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    api = ThemeApi(LIVE)
    report = {"step": "S3", "stamp": stamp, "files": []}

    for key, fn in [
        ("assets/wearth-l100-foundation.css", patch_foundation_css),
        ("sections/main-product.liquid", patch_main_product),
    ]:
        live = api.get_asset(key)
        patched = fn(live)
        if patched == live:
            raise SystemExit(f"no change for {key}")
        backup_and_diff(key, live, patched, stamp)
        api.put_asset(key, patched)
        print(f"PUSHED {key} ({len(live)} -> {len(patched)})")
        report["files"].append({"file": key, "bytes_before": len(live), "bytes_after": len(patched)})

    path = OUT / f"report_S3_{stamp}.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
