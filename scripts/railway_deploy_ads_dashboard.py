# -*- coding: utf-8 -*-
"""Create/configure Railway service for wearth-ads-dashboard via GraphQL (CLI OAuth token)."""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

GRAPHQL = "https://backboard.railway.com/graphql/v2"
UA = "Railway/4.44.0"

PROJECT_ID = "9d78676d-c257-441d-bf18-cf1a27e1a6a6"
ENV_ID = "fb84587f-3875-4e02-abde-f0bec3be235a"
REPO = "contactus-ops/wearth-studio"
SERVICE_NAME = "wearth-ads-dashboard"
ROOT = "wearth-ads-dashboard"
BUILD_CMD = "npm install && npm run build"
START_CMD = "npx serve -s dist"
VITE_API = "https://web-production-448c1.up.railway.app"


def _token() -> str:
    t = (os.environ.get("RAILWAY_TOKEN") or "").strip()
    if t:
        return t
    p = os.path.join(os.environ.get("USERPROFILE", ""), ".railway", "config.json")
    with open(p, encoding="utf-8") as f:
        return str(json.load(f)["user"]["accessToken"])


def gql(query: str, variables: Optional[Dict[str, Any]] = None, timeout: int = 120) -> Dict[str, Any]:
    body: Dict[str, Any] = {"query": query}
    if variables is not None:
        body["variables"] = variables
    req = urllib.request.Request(
        GRAPHQL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {_token()}",
            "Content-Type": "application/json",
            "User-Agent": UA,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = raw
        return {"http_error": e.code, "body": parsed}


def ensure_service() -> str:
    q = """
query ProjectServices($id: String!) {
  project(id: $id) {
    services {
      edges { node { id name } }
    }
  }
}
"""
    data = gql(q, {"id": PROJECT_ID})
    if data.get("errors"):
        print(json.dumps(data, indent=2))
        sys.exit(1)
    edges = data["data"]["project"]["services"]["edges"]
    for e in edges:
        n = e["node"]
        if n["name"] == SERVICE_NAME:
            return str(n["id"])
    m = """
mutation CreateSvc($input: ServiceCreateInput!) {
  serviceCreate(input: $input) {
    id
    name
  }
}
"""
    cr = gql(
        m,
        {
            "input": {
                "projectId": PROJECT_ID,
                "name": SERVICE_NAME,
                "source": {"repo": REPO},
            }
        },
        timeout=180,
    )
    if cr.get("errors"):
        print(json.dumps(cr, indent=2))
        sys.exit(1)
    return str(cr["data"]["serviceCreate"]["id"])


def patch_instance(service_id: str) -> None:
    m = """
mutation Patch($sid: String!, $eid: String!, $input: ServiceInstanceUpdateInput!) {
  serviceInstanceUpdate(serviceId: $sid, environmentId: $eid, input: $input)
}
"""
    inp: Dict[str, Any] = {
        "rootDirectory": ROOT,
        "buildCommand": BUILD_CMD,
        "startCommand": START_CMD,
    }
    out = gql(m, {"sid": service_id, "eid": ENV_ID, "input": inp})
    if out.get("errors") or out.get("http_error"):
        print(json.dumps(out, indent=2))
        sys.exit(1)


def set_variable(service_id: str) -> None:
    m = """
mutation Upsert($input: VariableUpsertInput!) {
  variableUpsert(input: $input)
}
"""
    out = gql(
        m,
        {
            "input": {
                "projectId": PROJECT_ID,
                "environmentId": ENV_ID,
                "serviceId": service_id,
                "name": "VITE_API_BASE",
                "value": VITE_API,
            }
        },
    )
    if out.get("errors"):
        # Try alternate mutation name from schema
        m2 = """
mutation Bulk($input: [VariableUpsertInput!]!) {
  variablesBulkUpsert(input: $input)
}
"""
        out2 = gql(
            m2,
            {
                "input": [
                    {
                        "projectId": PROJECT_ID,
                        "environmentId": ENV_ID,
                        "serviceId": service_id,
                        "name": "VITE_API_BASE",
                        "value": VITE_API,
                    }
                ]
            },
        )
        if out2.get("errors"):
            print("variableUpsert:", json.dumps(out, indent=2))
            print("variablesBulkUpsert:", json.dumps(out2, indent=2))
            sys.exit(1)


def trigger_deploy(service_id: str) -> str:
    m = """
mutation Deploy($sid: String!, $eid: String!) {
  deploymentRedeploy(serviceId: $sid, environmentId: $eid) {
    id
    status
  }
}
"""
    out = gql(m, {"sid": service_id, "eid": ENV_ID})
    if out.get("errors"):
        m2 = """
mutation SI($sid: String!, $eid: String!) {
  serviceInstanceRedeploy(serviceId: $sid, environmentId: $eid) {
    id
  }
}
"""
        out = gql(m2, {"sid": service_id, "eid": ENV_ID})
    if out.get("errors"):
        print(json.dumps(out, indent=2))
        return ""
    dep = out.get("data", {}).get("deploymentRedeploy") or out.get("data", {}).get(
        "serviceInstanceRedeploy"
    )
    if isinstance(dep, dict):
        return str(dep.get("id") or "")
    return ""


def poll_deploy(service_id: str, timeout_sec: int = 900) -> Dict[str, Any]:
    q = """
query Dep($sid: String!, $eid: String!) {
  project(id: "%s") {
    services {
      edges {
        node {
          id
          name
          serviceInstances {
            edges {
              node {
                environmentId
                latestDeployment {
                  id
                  status
                  createdAt
                }
              }
            }
          }
        }
      }
    }
  }
}
""" % PROJECT_ID
    end = time.time() + timeout_sec
    last: Dict[str, Any] = {}
    while time.time() < end:
        data = gql(q)
        if data.get("errors"):
            return {"errors": data["errors"]}
        edges = data["data"]["project"]["services"]["edges"]
        for e in edges:
            n = e["node"]
            if n["id"] != service_id:
                continue
            inst_edges = n.get("serviceInstances", {}).get("edges") or []
            for ie in inst_edges:
                node = ie["node"]
                if node.get("environmentId") != ENV_ID:
                    continue
                ld = node.get("latestDeployment") or {}
                last = ld
                st = (ld.get("status") or "").upper()
                if st in ("SUCCESS", "FAILED", "CRASHED", "ERROR", "SKIPPED"):
                    return {"latestDeployment": ld, "service": n["name"]}
        time.sleep(8)
    return {"timeout": True, "last": last}


def get_public_domain(service_id: str) -> Optional[str]:
    q = """
query Dom($sid: String!) {
  service(id: $sid) {
    serviceInstances {
      edges {
        node {
          domains {
            serviceDomains {
              domain
            }
          }
        }
      }
    }
  }
}
"""
    data = gql(q, {"sid": service_id})
    if data.get("errors"):
        return None
    edges = data["data"]["service"]["serviceInstances"]["edges"]
    for e in edges:
        doms = e["node"].get("domains") or {}
        for sd in doms.get("serviceDomains") or []:
            d = sd.get("domain")
            if d:
                return f"https://{d}"
    return None


def main() -> None:
    sid = ensure_service()
    print(json.dumps({"step": "service_id", "id": sid}, indent=2))
    patch_instance(sid)
    print(json.dumps({"step": "patched_instance"}, indent=2))
    set_variable(sid)
    print(json.dumps({"step": "variable_set"}, indent=2))
    trigger_deploy(sid)
    print(json.dumps({"step": "deploy_triggered"}, indent=2))
    poll = poll_deploy(sid)
    print(json.dumps({"step": "deploy_poll", "result": poll}, indent=2))
    url = get_public_domain(sid)
    print(json.dumps({"step": "public_url", "url": url}, indent=2))


if __name__ == "__main__":
    main()
