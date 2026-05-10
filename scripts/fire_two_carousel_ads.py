import base64
import json
from datetime import datetime

import requests

APP_BASE = "https://web-production-448c1.up.railway.app"
IMAGE_FILE_ID = "1PK3prkjgSQVFQRemEnGW58qgZlyJ9o6N"
VIDEO_FILE_ID = "1Io6Zi5TLT3MIurzUU5xsAlnQkK3EZSDf"


def _drive_download_url(file_id: str) -> str:
    return f"https://drive.google.com/uc?export=download&id={file_id}"


def main() -> int:
    stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    combo_name = f"WEARTH HookLab Women {stamp}"

    health = requests.get(f"{APP_BASE}/health", timeout=20)
    print("health:", health.status_code, health.text[:200])
    if health.status_code != 200:
        print("Aborting: Railway health check failed.")
        return 1

    img_resp = requests.get(_drive_download_url(IMAGE_FILE_ID), timeout=60)
    img_resp.raise_for_status()
    image_b64 = base64.b64encode(img_resp.content).decode("utf-8")
    print("image bytes:", len(img_resp.content), "b64 chars:", len(image_b64))

    payload = {
        "image_b64": image_b64,
        "video_url": _drive_download_url(VIDEO_FILE_ID),
        "combo_name": combo_name,
    }

    # launch-carousel creates two distinct ad sets (two audience tribes).
    publish = requests.post(
        f"{APP_BASE}/api/meta/launch-carousel",
        json=payload,
        timeout=240,
    )
    print("publish status:", publish.status_code)
    try:
        body = publish.json()
    except ValueError:
        print("non-json response:", publish.text[:2000])
        return 1

    print(json.dumps(body, indent=2))

    ok = bool(body.get("ok"))
    ad_sets = body.get("ad_set_ids") or []
    ads = body.get("ad_ids") or []
    errors = body.get("errors") or []

    if ok and len(ad_sets) >= 2 and len(ads) >= 2 and not errors:
        print("SUCCESS: Two carousel ads should now be live.")
        return 0

    print("WARNING: publish returned partial success or errors.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
