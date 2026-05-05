"""Print Meta insights spend ladder until non-zero or exhausted (requires META_* env)."""
import json
import os
import sys

import requests

META_V = os.environ.get("META_GRAPH_VERSION", "v22.0").strip() or "v22.0"
TOKEN = (os.environ.get("META_ACCESS_TOKEN") or "").strip()
RAW = (os.environ.get("META_AD_ACCOUNT_ID") or "").strip()
FIELDS = "spend,clicks,impressions,reach,actions,cost_per_action_type"
CAMPAIGN_ID = "120245108704880305"
ADSET_ID = "120245108705080305"


def account_id_path() -> str:
    if not RAW:
        return ""
    if RAW.startswith("act_"):
        return RAW
    return "act_" + RAW.replace("act_", "")


def purchases_from_actions(actions):
    if not isinstance(actions, list):
        return 0
    types = {
        "purchase",
        "offsite_conversion.fb_pixel_purchase",
        "omni_purchase",
    }
    n = 0
    for a in actions:
        if not isinstance(a, dict):
            continue
        if str(a.get("action_type") or "") in types:
            try:
                n += int(float(a.get("value") or 0))
            except (TypeError, ValueError):
                pass
    return n


def print_try(label: str, url: str, params: dict):
    print("\n=== TRY:", label, "===")
    print("GET", url)
    print("params:", json.dumps({k: params[k] for k in params if k != "access_token"}, indent=2))
    try:
        r = requests.get(url, params=params, timeout=45)
        print("HTTP", r.status_code)
        try:
            j = r.json()
        except Exception:
            print("BODY", r.text[:2000])
            return None, {}
        print("BODY", json.dumps(j, indent=2)[:12000])
        data = (j.get("data") or []) if isinstance(j, dict) else []
        row = data[0] if data else {}
        spend_raw = row.get("spend") if isinstance(row, dict) else None
        try:
            spend = float(spend_raw or 0)
        except (TypeError, ValueError):
            spend = 0.0
        clicks = row.get("clicks")
        try:
            clicks_i = int(float(clicks or 0))
        except (TypeError, ValueError):
            clicks_i = 0
        purchases = purchases_from_actions(row.get("actions") if isinstance(row, dict) else None)
        print(
            "PARSED spend=", spend, "clicks=", clicks_i, "purchases=", purchases
        )
        return spend, {
            "spend": spend,
            "clicks": clicks_i,
            "purchases": purchases,
            "row": row,
        }
    except Exception as e:
        print("REQUEST_ERROR", repr(e))
        return None, {}


def main() -> int:
    if not TOKEN:
        print("META_ACCESS_TOKEN missing", file=sys.stderr)
        return 2
    acct = account_id_path()
    if not acct:
        print("META_AD_ACCOUNT_ID missing", file=sys.stderr)
        return 2
    base = f"https://graph.facebook.com/{META_V}"
    tries = [
        (
            "account_maximum",
            f"{base}/{acct}/insights",
            {"date_preset": "maximum", "fields": FIELDS, "access_token": TOKEN},
        ),
        (
            "account_last_90d",
            f"{base}/{acct}/insights",
            {"date_preset": "last_90d", "fields": FIELDS, "access_token": TOKEN},
        ),
        (
            "account_last_year",
            f"{base}/{acct}/insights",
            {"date_preset": "last_year", "fields": FIELDS, "access_token": TOKEN},
        ),
        (
            "campaign_maximum",
            f"{base}/{CAMPAIGN_ID}/insights",
            {"date_preset": "maximum", "fields": FIELDS, "access_token": TOKEN},
        ),
        (
            "adset_maximum",
            f"{base}/{ADSET_ID}/insights",
            {"date_preset": "maximum", "fields": FIELDS, "access_token": TOKEN},
        ),
    ]
    found_label = None
    found_metrics = None
    for label, url, params in tries:
        spend, meta = print_try(label, url, params)
        if spend is not None and spend > 0:
            found_label = label
            found_metrics = meta
            break
    print("\n=== SUMMARY ===")
    print("level_found:", found_label)
    if found_metrics:
        sp = found_metrics["spend"]
        pc = found_metrics["purchases"]
        cl = found_metrics["clicks"]
        cpa = (sp / pc) if pc > 0 else "no purchases recorded"
        print("spend:", sp, "clicks:", cl, "purchases:", pc, "cpa:", cpa)
    return 0


if __name__ == "__main__":
    sys.exit(main())
