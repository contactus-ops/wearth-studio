"""
One-off: reduce Instagram workflow to 4 nodes (3 schedule triggers + Post to Instagram).
Requires: N8N_API_KEY in env, workflow id cGbp1fEkP5DoIIsZ
"""
import json
import os
import sys
import urllib.error
import urllib.request

WORKFLOW_ID = "cGbp1fEkP5DoIIsZ"
N8N_BASE = (os.environ.get("N8N_BASE_URL") or "https://wearthactive.app.n8n.cloud").rstrip("/")
POST_URL = "https://web-production-448c1.up.railway.app/api/instagram/post"


def main() -> int:
    key = (os.environ.get("N8N_API_KEY") or "").strip()
    if not key:
        print("N8N_API_KEY missing", file=sys.stderr)
        return 2
    h = {
        "X-N8N-API-KEY": key,
        "Content-Type": "application/json",
    }
    get_url = f"{N8N_BASE}/api/v1/workflows/{WORKFLOW_ID}"
    req = urllib.request.Request(get_url, headers=h, method="GET")
    with urllib.request.urlopen(req, timeout=60) as r:
        wf = json.loads(r.read().decode("utf-8"))
    old_nodes = wf.get("nodes") or []
    old_names = [n.get("name") for n in old_nodes if isinstance(n, dict)]
    print("OLD_NODE_NAMES:", json.dumps(old_names, ensure_ascii=False))

    triggers = [
        n
        for n in old_nodes
        if isinstance(n, dict) and n.get("type") == "n8n-nodes-base.scheduleTrigger"
    ]
    if len(triggers) < 3:
        print(
            f"Need 3 schedule triggers; found {len(triggers)}",
            file=sys.stderr,
        )
        return 3
    triggers = triggers[:3]

    y0 = 200
    x_step = 220
    post_id = "ig_post_instagram"
    post_node = {
        "parameters": {
            "method": "POST",
            "url": POST_URL,
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "{}",
            "options": {"timeout": 120000},
        },
        "id": post_id,
        "name": "Post to Instagram",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [len(triggers) * x_step + 200, y0],
    }

    new_nodes = []
    for i, tr in enumerate(triggers):
        tr = dict(tr)
        tr["position"] = [i * x_step, y0]
        new_nodes.append(tr)
    new_nodes.append(post_node)

    connections = {}
    for i, tr in enumerate(triggers):
        tid = tr.get("name")
        if not tid:
            continue
        connections[tid] = {
            "main": [[{"node": "Post to Instagram", "type": "main", "index": 0}]]
        }

    wf["nodes"] = new_nodes
    wf["connections"] = connections
    put_body = json.dumps(wf).encode("utf-8")
    put_req = urllib.request.Request(
        get_url,
        data=put_body,
        headers=h,
        method="PUT",
    )
    try:
        with urllib.request.urlopen(put_req, timeout=120) as pr:
            code = pr.status
            print("PUT status:", code)
    except urllib.error.HTTPError as e:
        print("PUT failed:", e.code, e.read().decode()[:2000], file=sys.stderr)
        return 4

    req2 = urllib.request.Request(get_url, headers=h, method="GET")
    with urllib.request.urlopen(req2, timeout=60) as r2:
        wf2 = json.loads(r2.read().decode("utf-8"))
    nodes2 = wf2.get("nodes") or []
    names2 = [n.get("name") for n in nodes2 if isinstance(n, dict)]
    print("NEW_NODE_COUNT:", len(nodes2))
    print("NEW_NODE_NAMES:", json.dumps(names2, ensure_ascii=False))
    removed = [n for n in old_names if n not in names2]
    print("REMOVED:", json.dumps(removed, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
