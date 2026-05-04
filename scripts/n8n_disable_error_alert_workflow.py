# -*- coding: utf-8 -*-
"""Disable WEARTH n8n Error Alert workflow (TARGET ROAS 4:1).

n8n Cloud: PATCH/PUT on /api/v1/workflows/:id may be blocked or treat `active` as read-only.
Use POST /api/v1/workflows/:id/deactivate instead.
"""
from __future__ import annotations

import os
import sys

import requests

WORKFLOW_ID = "Ez9l9stZJkLfsviy"
HOST = "https://wearthactive.app.n8n.cloud"


def main() -> int:
    key = (os.environ.get("N8N_API_KEY") or "").strip()
    if not key:
        print("N8N_API_KEY missing", file=sys.stderr)
        return 1
    url = f"{HOST}/api/v1/workflows/{WORKFLOW_ID}/deactivate"
    r = requests.post(
        url,
        headers={"X-N8N-API-KEY": key},
        timeout=30,
    )
    print(r.status_code, r.text[:400])
    return 0 if r.status_code in (200, 201) else 1


if __name__ == "__main__":
    raise SystemExit(main())
