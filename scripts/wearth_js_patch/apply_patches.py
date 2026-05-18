# -*- coding: utf-8 -*-
"""Apply JS error patches to Live-JS-Patch duplicate theme."""
from __future__ import annotations

import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "wearth_js_patch"
sys.path.insert(0, str(ROOT / "scripts"))

from wearth_sat_fixes.client import HEADERS

BASE = "https://wearthactive.myshopify.com/admin/api/2024-01"
THEME_ID = (DATA / "state.json").read_text(encoding="utf-8")
THEME_ID = json.loads(THEME_ID)["work_theme_id"]

COLOR_MOUSEOVER_OLD = """$("body").on( "mouseover", ".color-swatch", function( event ) { 
  $(this).closest('.grid__item').children('.card-wrapper').addClass('Change_variant');
  $('.Change_variant .media img:first').attr("srcset", $(this).attr("data-variant-image")).attr("data-srcset", $(this).attr("data-variant-image"));
  $(this).addClass('active').parent('.ProductItem__ColorSwatchItem').siblings().children('.color-swatch').removeClass('active');
});

$("body").on( "mouseout", ".color-swatch", function( event ) { $(this).closest('.grid__item').children('.card-wrapper').removeClass('Change_variant'); });"""

COLOR_MOUSEOVER_NEW = """$("body").on( "mouseover", ".color-swatch", function( event ) {
  var $card = $(this).closest('.grid__item').children('.card-wrapper');
  if (!$card.length) return;
  var imgUrl = $(this).attr("data-variant-image");
  if (!imgUrl) return;
  $card.addClass('Change_variant');
  $card.find('.media img:first').attr("srcset", imgUrl).attr("data-srcset", imgUrl);
  $(this).addClass('active')
    .parent('.ProductItem__ColorSwatchItem')
    .siblings()
    .children('.color-swatch')
    .removeClass('active');
});

$("body").on( "mouseout", ".color-swatch", function( event ) {
  var $card = $(this).closest('.grid__item').children('.card-wrapper');
  if (!$card.length) return;
  $card.removeClass('Change_variant');
});"""

BACK_TOP_OLD = """let toTopBtn = document.getElementById('back-top__content--desk');

toTopBtn.addEventListener('click', function(e) {
  e.preventDefault();  
 window.scrollTo({top: 0, behavior: "smooth"});
});

//hide/show button on scroll up/down
let scrollPos = 0;

window.addEventListener('scroll', function(){

  // detects new state and compares it with the new one
  if ((document.body.getBoundingClientRect()).top > scrollPos) {
    document.getElementById('back-top').classList.remove('active');
  } else {
    document.getElementById('back-top').classList.add('active');
  }
  // saves the new position for iteration.
  scrollPos = (document.body.getBoundingClientRect()).top;
});"""

BACK_TOP_NEW = """let toTopBtn = document.getElementById('back-top__content--desk');
if (toTopBtn) {
  toTopBtn.addEventListener('click', function(e) {
    e.preventDefault();
    window.scrollTo({top: 0, behavior: "smooth"});
  });
}

//hide/show button on scroll up/down
let scrollPos = 0;

window.addEventListener('scroll', function(){
  var backTop = document.getElementById('back-top');
  if (!backTop) return;
  if ((document.body.getBoundingClientRect()).top > scrollPos) {
    backTop.classList.remove('active');
  } else {
    backTop.classList.add('active');
  }
  scrollPos = (document.body.getBoundingClientRect()).top;
});"""

WOW_OLD = """    <script>
      wow = new WOW({
          boxClass: 'wow',
          animateClass: 'animated',
          offset: 1,
          mobile: false,
          live: true
      })
      wow.init();
    </script>"""

WOW_NEW = """    <script>
      document.addEventListener('DOMContentLoaded', function () {
        if (typeof WOW === 'undefined') return;
        var wow = new WOW({
          boxClass: 'wow',
          animateClass: 'animated',
          offset: 1,
          mobile: false,
          live: true
        });
        wow.init();
      });
    </script>"""

ERROR_REPORT_MARKER = "/* wearth-js-error-beacon */"
ERROR_REPORT_SCRIPT = """
<script>
/* wearth-js-error-beacon */
(function() {
  window.addEventListener('error', function(e) {
    try {
      var data = {
        msg: e.message || 'unknown',
        src: e.filename || '',
        line: e.lineno || 0,
        col: e.colno || 0,
        ua: navigator.userAgent,
        url: window.location.href,
        ref: document.referrer || 'direct',
        ts: new Date().toISOString()
      };
      if (navigator.sendBeacon) {
        navigator.sendBeacon(
          'https://web-production-448c1.up.railway.app/api/js-errors',
          JSON.stringify(data)
        );
      }
    } catch (_) {}
  });
  window.addEventListener('unhandledrejection', function(e) {
    try {
      var data = {
        msg: 'Promise: ' + (e.reason && e.reason.message ? e.reason.message : String(e.reason)),
        ua: navigator.userAgent,
        url: window.location.href,
        ref: document.referrer || 'direct',
        ts: new Date().toISOString()
      };
      if (navigator.sendBeacon) {
        navigator.sendBeacon(
          'https://web-production-448c1.up.railway.app/api/js-errors',
          JSON.stringify(data)
        );
      }
    } catch (_) {}
  });
})();
</script>
"""

# Liquid patterns: {{ x }} inside script without | json
LIQUID_SCRIPT_PATTERNS = [
    (
        re.compile(
            r"(<script[^>]*>[\s\S]*?)(['\"])\{\{\s*product\.title\s*\}\}\2",
            re.I,
        ),
        r"\1{{ product.title | json }}",
    ),
    (
        re.compile(
            r"(<script[^>]*>[\s\S]*?)(['\"])\{\{\s*product\.title\s*\|\s*escape\s*\}\}\2",
            re.I,
        ),
        r"\1{{ product.title | json }}",
    ),
]


def get_asset(key: str) -> str:
    q = urllib.parse.urlencode({"asset[key]": key})
    with urllib.request.urlopen(
        urllib.request.Request(f"{BASE}/themes/{THEME_ID}/assets.json?{q}", headers=HEADERS),
        timeout=120,
    ) as r:
        return (json.loads(r.read().decode()).get("asset") or {}).get("value") or ""


def put_asset(key: str, value: str) -> None:
    body = json.dumps({"asset": {"key": key, "value": value}}).encode()
    req = urllib.request.Request(f"{BASE}/themes/{THEME_ID}/assets.json", data=body, method="PUT", headers=HEADERS)
    with urllib.request.urlopen(req, timeout=120) as r:
        if r.status not in (200, 201):
            raise RuntimeError(f"PUT {key} failed")


def list_liquid_keys() -> list[str]:
    with urllib.request.urlopen(
        urllib.request.Request(f"{BASE}/themes/{THEME_ID}/assets.json", headers=HEADERS),
        timeout=120,
    ) as r:
        keys = [a["key"] for a in json.loads(r.read().decode()).get("assets") or [] if a.get("key")]
    return [k for k in keys if k.endswith(".liquid")]


def patch_liquid_scripts() -> list[str]:
    changed = []
    risky = re.compile(
        r"<script[\s\S]*?</script>",
        re.I,
    )
    for key in list_liquid_keys():
        body = get_asset(key)
        orig = body
        # product.title in quotes inside script blocks
        if "product.title" in body and "<script" in body.lower():

            def fix_script_block(m: re.Match) -> str:
                block = m.group(0)
                if "product.title" not in block:
                    return block
                block = re.sub(
                    r"['\"]\{\{\s*product\.title\s*(\|\s*escape)?\s*\}\}['\"]",
                    "{{ product.title | json }}",
                    block,
                )
                block = re.sub(
                    r"=\s*['\"]\{\{\s*product\.title",
                    "= {{ product.title | json }}",
                    block,
                )
                return block

            body = risky.sub(fix_script_block, body)
        # variant json in onclick handlers
        body = re.sub(
            r"var product\s*=\s*\{\{\s*product\s*\|\s*json\s*\}\};?",
            "{{ product | json }};",
            body,
        )
        if body != orig:
            put_asset(key, body)
            changed.append(key)
    return changed


def main() -> None:
    report = {"theme_id": THEME_ID, "patches": {}}

    layout = get_asset("layout/theme.liquid")
    if WOW_OLD in layout:
        layout = layout.replace(WOW_OLD, WOW_NEW, 1)
        report["patches"]["wow"] = "option_a_guard_and_domcontentloaded"
    else:
        report["patches"]["wow"] = "pattern_not_found_manual_review"
    if ERROR_REPORT_MARKER not in layout:
        layout = layout.replace("</head>", ERROR_REPORT_SCRIPT + "\n</head>", 1)
        report["patches"]["error_beacon"] = True
    put_asset("layout/theme.liquid", layout)

    theme_js_key = "assets/theme.js.liquid"
    theme_js = get_asset(theme_js_key)
    if COLOR_MOUSEOVER_OLD in theme_js:
        theme_js = theme_js.replace(COLOR_MOUSEOVER_OLD, COLOR_MOUSEOVER_NEW, 1)
        report["patches"]["color_swatch"] = True
    if BACK_TOP_OLD in theme_js:
        theme_js = theme_js.replace(BACK_TOP_OLD, BACK_TOP_NEW, 1)
        report["patches"]["back_top"] = True
    put_asset(theme_js_key, theme_js)
    report["patches"]["theme_js_source"] = theme_js_key

    liquid_changed = patch_liquid_scripts()
    report["liquid_files"] = liquid_changed

    (DATA / "patch_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
