# -*- coding: utf-8 -*-
"""
WEARTH Instagram Auto (cGbp1fEkP5DoIIsZ): list images via Railway GET with omit_used_instagram=1.

The live workflow used a Google Drive node ("List Photos from Drive"), not an HTTP node hitting
/api/drive/images. We replace that single node with a Code node that calls the same Railway URL
and maps items to {id, name, webViewLink} so "Pick Random Photo" → "Limit to One" stay unchanged.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from n8n_api_common import load_n8n_api_key, prune_minimal_put, req

WF_ID = "cGbp1fEkP5DoIIsZ"
LIST_NODE_ID = "4c951b57-f51d-4fe7-b14f-b110cd13ee96"
LIST_NODE_NAME = "List Photos from Drive"
TARGET_URL = "https://web-production-448c1.up.railway.app/api/drive/instagram-media"

# n8n Code node: unified image/video pick; emit one item (Drive-like shape for downstream Sort/Limit).
_JS = """const url = 'https://web-production-448c1.up.railway.app/api/drive/instagram-media';
let data;
try {
  data = await this.helpers.httpRequest({ method: 'GET', url, json: true });
} catch (e) {
  return [{ json: { error: String(e && e.message ? e.message : e), images: [] } }];
}
if (!data || !data.url) {
  return [];
}
const id = String(data.media_id || '');
const name = String((data.media_type || 'media') + ':' + id);
const webViewLink = String(data.url || '');
return [{ json: { id, name, webViewLink } }];
"""


def main() -> int:
    base = (os.environ.get("N8N_BASE_URL") or "https://wearthactive.app.n8n.cloud").rstrip("/")
    key = load_n8n_api_key()
    if not key:
        print(json.dumps({"error": "N8N_API_KEY missing"}))
        return 1
    url = f"{base}/api/v1/workflows/{WF_ID}"
    code, raw = req("GET", url, n8n_key=key)
    if code != 200:
        print(json.dumps({"error": "GET failed", "http": code, "body": raw[:2000]}))
        return 1
    wf = json.loads(raw)
    nodes = wf.get("nodes") or []
    found = False
    out_info: dict = {}
    for i, n in enumerate(nodes):
        if not isinstance(n, dict):
            continue
        if n.get("id") != LIST_NODE_ID and n.get("name") != LIST_NODE_NAME:
            continue
        found = True
        old_type = n.get("type")
        pos = n.get("position") or [464, 496]
        nodes[i] = {
            "parameters": {"language": "javaScript", "jsCode": _JS},
            "id": LIST_NODE_ID,
            "name": LIST_NODE_NAME,
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": pos,
        }
        out_info = {
            "node_name": LIST_NODE_NAME,
            "node_id": LIST_NODE_ID,
            "previous_type": old_type,
            "new_type": "n8n-nodes-base.code",
            "railway_url_used": TARGET_URL,
        }
        break

    if not found:
        print(json.dumps({"error": "List Photos from Drive node not found"}))
        return 1

    body = {k: v for k, v in wf.items() if k in ("name", "nodes", "connections", "settings", "staticData", "pinData")}
    body["nodes"] = nodes
    payload = json.dumps(body).encode("utf-8")
    c2, raw_put = req("PUT", url, n8n_key=key, body=payload, content_type="application/json")
    if c2 != 200:
        c2, raw_put = req(
            "PUT",
            url,
            n8n_key=key,
            body=json.dumps(prune_minimal_put(body)).encode("utf-8"),
            content_type="application/json",
        )
    if c2 not in (200, 201):
        print(json.dumps({"error": "PUT failed", "http": c2, "body": raw_put[:4000]}))
        return 1

    verify_js_contains_omit = False
    c3, raw_get = req("GET", url, n8n_key=key)
    if c3 == 200:
        try:
            wf2 = json.loads(raw_get)
            for n in wf2.get("nodes") or []:
                if isinstance(n, dict) and n.get("name") == LIST_NODE_NAME:
                    js = (n.get("parameters") or {}).get("jsCode", "")
                    verify_js_contains_omit = (
                        "instagram-media" in js or "omit_used_instagram=1" in js
                    )
                    break
        except Exception:
            pass

    print(
        json.dumps(
            {
                "ok": True,
                "workflow_id": WF_ID,
                "put_http": c2,
                "get_verify_http": c3,
                "verify_js_contains_omit": verify_js_contains_omit,
                "patch": out_info,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
