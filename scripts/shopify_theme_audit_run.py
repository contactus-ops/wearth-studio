"""One-off: themes + main theme template assets + shop + jobs status append."""
import json
import os
import urllib.request

HOST = (os.environ.get("SHOPIFY_STORE") or "wearthactive.myshopify.com").strip().lower()
HOST = HOST.replace("https://", "").replace("http://", "").strip("/")
VER = "2024-01"
BASE = f"https://{HOST}/admin/api/{VER}"
RAILWAY = "https://web-production-448c1.up.railway.app/api/jobs/status/append"
TOK = (os.environ.get("SHOPIFY_TOKEN") or "").strip()


def api_get(path: str) -> dict:
    url = BASE + path
    r = urllib.request.Request(
        url,
        headers={
            "X-Shopify-Access-Token": TOK,
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(r, timeout=90) as resp:
        return json.loads(resp.read().decode())


def append_status(theme_name: str, theme_role: str, template_count: int, main_id):
    ev = json.dumps(
        {
            "theme_name": theme_name,
            "theme_role": theme_role,
            "template_count": template_count,
            "main_theme_id": main_id,
        },
        ensure_ascii=False,
    )
    body = json.dumps(
        {"step": "shopify_theme_audit", "status": "COMPLETE", "evidence": ev}
    ).encode()
    rq = urllib.request.Request(
        RAILWAY,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(rq, timeout=20) as resp:
        print(resp.read().decode())


def main():
    if not TOK:
        print("ERROR: SHOPIFY_TOKEN not set in environment")
        raise SystemExit(2)

    print("=== GET /themes.json ===")
    print(f"Host: {HOST}  API: {VER}")
    themes_data = api_get("/themes.json")
    themes = themes_data.get("themes") or []
    print(f"Theme count: {len(themes)}\n")
    for t in themes:
        tid = t.get("id")
        name = t.get("name")
        role = t.get("role")
        created = t.get("created_at")
        print(f"  id={tid}  name={json.dumps(name, ensure_ascii=False)}  role={role}  created_at={created}")

    main = next((x for x in themes if x.get("role") == "main"), None)
    if not main and themes:
        main = themes[0]
    main_id = main.get("id") if main else None
    main_name = (main or {}).get("name") or ""
    main_role = (main or {}).get("role") or ""

    template_keys = []
    if main_id:
        print(f"\n=== GET /themes/{main_id}/assets.json (main theme) ===")
        assets_data = api_get(f"/themes/{main_id}/assets.json")
        assets = assets_data.get("assets") or []
        template_keys = [
            a.get("key")
            for a in assets
            if isinstance(a, dict)
            and str(a.get("key", "")).startswith("templates/")
        ]
        print(f"Total assets in response: {len(assets)}")
        print(f"Template files (templates/*): {len(template_keys)}\n")
        for k in sorted(template_keys):
            print(f"  {k}")

    print("\n=== GET /shop.json ===")
    shop = api_get("/shop.json").get("shop") or {}
    for k in sorted(shop.keys()):
        v = shop[k]
        if isinstance(v, (dict, list)):
            v = json.dumps(v, ensure_ascii=False)[:800]
        print(f"  {k}: {v}")

    tc = len(template_keys)
    print(f"\nSUMMARY  main_theme_id={main_id}  template_count={tc}")
    print("=== update_status(shopify_theme_audit) ===")
    append_status(main_name, main_role or "main", tc, main_id)


if __name__ == "__main__":
    main()
