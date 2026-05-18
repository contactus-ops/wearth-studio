import json, urllib.parse, urllib.request, sys
sys.path.insert(0, "scripts")
from wearth_sat_fixes.client import HEADERS
T = "140251431092"
BASE = "https://wearthactive.myshopify.com/admin/api/2024-01"
q = urllib.parse.urlencode({"asset[key]": "assets/theme.js"})
js = json.loads(
    urllib.request.urlopen(
        urllib.request.Request(f"{BASE}/themes/{T}/assets.json?{q}", headers=HEADERS), timeout=120
    ).read().decode()
)["asset"]["value"]
print("color", "if (!$card.length) return" in js)
print("back toTopBtn", "if (toTopBtn)" in js)
print("backTop", "if (!backTop) return" in js)
