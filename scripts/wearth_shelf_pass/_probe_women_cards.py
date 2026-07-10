#!/usr/bin/env python3
import re
import urllib.request

req = urllib.request.Request(
    "https://www.wearthactive.com/collections/women",
    headers={"User-Agent": "Mozilla/5.0"},
)
h = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace")
for pat in [
    "card-product",
    "wearth-card",
    "card__heading",
    "price-item",
    "wearth-card-comp",
    "editorial",
    "product-grid",
    "95% Eucalyptus",
]:
    print(pat, h.count(pat))
secs = re.findall(r'id="(shopify-section-[^"]+)"', h)
print("sections", secs[:20])
m = re.search(r"card__heading.{0,300}", h)
print("heading", (m.group(0)[:300] if m else "none"))
