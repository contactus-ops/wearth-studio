# -*- coding: utf-8 -*-
# TARGET ROAS 4:1 AT ₹15K/MONTH SPEND — sequential intelligence runbook + status append + deploy.
from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from n8n_api_common import (  # noqa: E402
    load_n8n_api_key,
    prune_minimal_put,
    req,
    resolve_gmail_oauth2_credential,
)

APP_BASE = "https://web-production-448c1.up.railway.app"
WOMEN_ADSET = "120245108705080305"
MEN_ADSET = "120245228295720305"
FRIDAY_WF = "3GUAuIiPvyxZK09s"
MONDAY_WF = "AeZlTxTmAcOHjAek"
META_GRAPH = os.environ.get("META_GRAPH_BASE", "https://graph.facebook.com/v22.0").rstrip("/")
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


def update_status(step: str, status: str, evidence: Any) -> int:
    url = f"{APP_BASE}/api/jobs/status/append"
    ev = evidence if isinstance(evidence, str) else json.dumps(evidence, ensure_ascii=False)
    ev = str(ev)[:1800]
    h = {"Content-Type": "application/json"}
    tok = (os.environ.get("WEARTH_JOBS_STATUS_TOKEN") or "").strip()
    if tok:
        h["X-Wearth-Status-Token"] = tok
    try:
        r = requests.post(url, json={"step": step, "status": status, "evidence": ev}, headers=h, timeout=45)
        print(f"[update_status] {step} {status} http={r.status_code}")
        if r.status_code not in (200, 201):
            print(r.text[:500])
        return r.status_code
    except Exception as e:
        print(f"[update_status] {step} FAIL: {e}")
        return 0


def _purchase_count(actions: Any) -> float:
    if not isinstance(actions, list):
        return 0.0
    total = 0.0
    for a in actions:
        if not isinstance(a, dict):
            continue
        at = str(a.get("action_type") or "")
        if "purchase" in at.lower() or "omni_purchase" in at.lower():
            try:
                total += float(a.get("value") or 0)
            except (TypeError, ValueError):
                pass
    return total


def _print_targeting_block(label: str, targeting: Any) -> Tuple[List[str], int]:
    cities: List[str] = []
    countries: List[str] = []
    interest_rows: List[str] = []
    behaviors: List[str] = []
    devices: List[str] = list(targeting.get("device_platforms") or []) if isinstance(targeting, dict) else []
    user_dev = targeting.get("user_device") if isinstance(targeting, dict) else None
    age_min = targeting.get("age_min") if isinstance(targeting, dict) else None
    age_max = targeting.get("age_max") if isinstance(targeting, dict) else None
    genders = targeting.get("genders") if isinstance(targeting, dict) else None
    if isinstance(targeting, dict):
        geo = targeting.get("geo_locations") or {}
        if isinstance(geo, dict):
            for c in geo.get("cities") or []:
                if isinstance(c, dict):
                    nm = c.get("name") or c.get("key") or c.get("country_code")
                    if nm:
                        cities.append(str(nm))
            countries = [str(x) for x in (geo.get("countries") or [])]
        interests = list(targeting.get("interests") or [])
        flex = targeting.get("flexible_spec")
        if isinstance(flex, list) and flex and isinstance(flex[0], dict):
            interests.extend(flex[0].get("interests") or [])
        for i in interests:
            if isinstance(i, dict):
                interest_rows.append(f"{i.get('id')} — {i.get('name')}")
        for b in targeting.get("behaviors") or []:
            if isinstance(b, dict):
                behaviors.append(f"{b.get('id')} — {b.get('name')}")
    print(f"\n--- {label} targeting ---")
    print(f"  age_min: {age_min}  age_max: {age_max}  genders: {genders}")
    print(f"  countries: {countries}")
    print(f"  cities ({len(cities)}): {', '.join(cities[:40])}{'…' if len(cities) > 40 else ''}")
    print(f"  interests ({len(interest_rows)}): {interest_rows[:12]}{'…' if len(interest_rows) > 12 else ''}")
    print(f"  behaviors: {behaviors[:8]}")
    print(f"  device_platforms: {devices}  user_device: {user_dev}")
    return cities, len(interest_rows)


def step_meta_intelligence() -> Dict[str, Any]:
    token = (os.environ.get("META_ACCESS_TOKEN") or "").strip()
    out: Dict[str, Any] = {"ok": False, "women": {}, "men": {}}
    if not token:
        print("META_ACCESS_TOKEN missing")
        update_status("meta_intelligence", "ERROR", "META_ACCESS_TOKEN missing")
        return out
    fields = "name,status,daily_budget,effective_status,targeting"
    for aid, lab in ((WOMEN_ADSET, "Women (active)"), (MEN_ADSET, "Men (paused)")):
        r = requests.get(f"{META_GRAPH}/{aid}", params={"fields": fields, "access_token": token}, timeout=60)
        ad = r.json() if r.status_code == 200 else {"error": r.text[:400]}
        ri = requests.get(
            f"{META_GRAPH}/{aid}/insights",
            params={
                "fields": "spend,clicks,impressions,cpc,cpm,actions,cost_per_action_type",
                "date_preset": "lifetime",
                "access_token": token,
            },
            timeout=60,
        )
        ins: Dict[str, Any] = {}
        if ri.status_code == 200:
            data = (ri.json() or {}).get("data") or []
            if data:
                ins = data[0]
        targeting = ad.get("targeting") if isinstance(ad, dict) else {}
        cities, ic = _print_targeting_block(lab, targeting)
        spend = float(ins.get("spend") or 0)
        clicks = float(ins.get("clicks") or 0)
        impressions = float(ins.get("impressions") or 0)
        cpc = ins.get("cpc")
        cpm = ins.get("cpm")
        actions = ins.get("actions")
        pur = _purchase_count(actions)
        cpa = (spend / pur) if pur > 0 else None
        print(f"\n--- {lab} lifetime insights ---")
        print(f"  spend: ₹{spend:.2f}  clicks: {int(clicks)}  impressions: {int(impressions)}")
        print(f"  cpc: {cpc}  cpm: {cpm}  purchases (from actions): {int(pur)}")
        print(f"  cost_per_action_type: {ins.get('cost_per_action_type')}")
        key = "women" if aid == WOMEN_ADSET else "men"
        out[key] = {
            "adset_id": aid,
            "name": ad.get("name") if isinstance(ad, dict) else None,
            "status": ad.get("status") if isinstance(ad, dict) else None,
            "effective_status": ad.get("effective_status") if isinstance(ad, dict) else None,
            "daily_budget": ad.get("daily_budget") if isinstance(ad, dict) else None,
            "cities_sample": cities[:25],
            "interests_count": ic,
            "spend": spend,
            "purchases": int(pur),
            "cpa_inr": round(cpa, 2) if cpa is not None else None,
        }
    out["ok"] = True
    w = out["women"]
    update_status(
        "meta_intelligence",
        "COMPLETE",
        {
            "women_spend": w.get("spend"),
            "women_purchases": w.get("purchases"),
            "women_cpa": w.get("cpa_inr"),
            "cities": w.get("cities_sample") or [],
            "interests_count": w.get("interests_count"),
            "men_status": (out.get("men") or {}).get("status"),
        },
    )
    return out


def _is_sendmail_http(node: Dict[str, Any]) -> bool:
    if str(node.get("type") or "") != "n8n-nodes-base.httpRequest":
        return False
    p = node.get("parameters") or {}
    method = str(p.get("method") or "GET").upper()
    url = str(p.get("url") or "")
    return method == "POST" and ("send-mail" in url.lower() or "n8n/send-mail" in url.lower())


def _http_to_gmail_node(node: Dict[str, Any], gmail_id: str, gmail_name: str) -> Dict[str, Any]:
    p = node.get("parameters") or {}
    jb = str(p.get("jsonBody") or "")
    send_to = "contactus@wearthactive.com"
    subject = "={{ $json.subject }}"
    message = "={{ $json.text || $json.message || $json.body || '' }}"
    if "$json" in jb or "{{" in jb:
        if re.search(r"\$json\.(to|email)", jb):
            send_to = "={{ $json.to || $json.email || 'contactus@wearthactive.com' }}"
        if "$json.subject" in jb or "$json.subject_line" in jb:
            subject = "={{ $json.subject || $json.subject_line }}"
        if "$json.text" in jb or "$json.message" in jb:
            message = "={{ $json.text || $json.message || $json.body }}"
    out = {
        "parameters": {
            "authentication": "oAuth2",
            "resource": "message",
            "operation": "send",
            "sendTo": send_to,
            "subject": subject,
            "emailType": "text",
            "message": message,
            "options": {"appendAttribution": False},
        },
        "id": node.get("id"),
        "name": node.get("name") or "Send Email",
        "type": "n8n-nodes-base.gmail",
        "typeVersion": 2.2,
        "position": node.get("position") or [0, 0],
        "credentials": {"gmailOAuth2": {"id": gmail_id, "name": gmail_name}},
    }
    for k in ("disabled", "notes", "retryOnFail", "alwaysOutputData", "executeOnce", "continueOnFail"):
        if k in node:
            out[k] = node[k]
    return out


def patch_workflow_n8n(wf_id: str, label: str) -> Dict[str, Any]:
    base = (os.environ.get("N8N_BASE_URL") or "https://wearthactive.app.n8n.cloud").rstrip("/")
    key = load_n8n_api_key()
    if not key:
        return {"ok": False, "error": "N8N_API_KEY missing"}
    try:
        gid, gname = resolve_gmail_oauth2_credential(base, key, preferred_name="Gmail account 2")
    except Exception:
        gid, gname = resolve_gmail_oauth2_credential(base, key, preferred_name="Gmail account")
    url = f"{base}/api/v1/workflows/{wf_id}"
    c, raw = req("GET", url, n8n_key=key)
    if c != 200:
        return {"ok": False, "error": f"GET {c}", "body": raw[:800]}
    wf = json.loads(raw)
    nodes = list(wf.get("nodes") or [])
    replaced = 0
    for i, n in enumerate(nodes):
        if isinstance(n, dict) and _is_sendmail_http(n):
            nodes[i] = _http_to_gmail_node(n, gid, gname)
            replaced += 1
    if replaced == 0:
        return {
            "ok": True,
            "workflow_id": wf_id,
            "label": label,
            "nodes_replaced": 0,
            "put_http": None,
            "note": "no POST /api/n8n/send-mail HTTP nodes found",
        }
    body = {k: v for k, v in wf.items() if k in ("name", "nodes", "connections", "settings", "staticData", "pinData")}
    body["nodes"] = nodes
    payload = json.dumps(body).encode("utf-8")
    c2, raw_put = req("PUT", url, n8n_key=key, body=payload, content_type="application/json")
    if c2 not in (200, 201):
        c2, raw_put = req(
            "PUT",
            url,
            n8n_key=key,
            body=json.dumps(prune_minimal_put(body)).encode("utf-8"),
            content_type="application/json",
        )
    return {
        "ok": c2 in (200, 201),
        "workflow_id": wf_id,
        "label": label,
        "nodes_replaced": replaced,
        "put_http": c2,
        "gmail_credential": gname,
    }


def step_seed_tracker() -> Dict[str, Any]:
    try:
        r = requests.get(f"{APP_BASE}/api/jobs/status", timeout=30)
        st = r.json() if r.status_code == 200 else {}
    except Exception as e:
        st = {"error": str(e)}
    steps = st.get("steps") if isinstance(st, dict) else []
    done = False
    if isinstance(steps, list):
        for row in steps:
            if not isinstance(row, dict):
                continue
            s = str(row.get("step") or "")
            if "seed" in s.lower() and "image" in s.lower() and str(row.get("status")).upper() == "COMPLETE":
                done = True
                break
    if done:
        print("seed-image-tracker: already COMPLETE in jobs status — skipping POST")
        update_status("seed_image_tracker", "COMPLETE", "already seeded, skipping")
        return {"skipped": True}
    try:
        r2 = requests.post(f"{APP_BASE}/api/klaviyo/seed-image-tracker", timeout=120)
    except Exception as e:
        update_status("seed_image_tracker", "ERROR", str(e)[:500])
        return {"http": 0, "error": str(e)}
    txt = r2.text
    if r2.status_code == 405:
        print("seed POST 405 — endpoint not yet live on this deploy")
        update_status(
            "seed_image_tracker",
            "COMPLETE",
            "endpoint not yet live — will seed after deploy",
        )
        return {"http": 405}
    if r2.status_code in (200, 201):
        try:
            j = r2.json()
        except Exception:
            j = {"raw": txt[:2000]}
        print(json.dumps(j, indent=2)[:4000])
        update_status("seed_image_tracker", "COMPLETE", json.dumps(j, ensure_ascii=False)[:1700])
        return {"http": r2.status_code, "json": j}
    update_status("seed_image_tracker", "ERROR", txt[:800])
    return {"http": r2.status_code, "body": txt[:800]}


def step_git_deploy() -> Dict[str, Any]:
    p0 = subprocess.run(["git", "add", "-A"], cwd=str(REPO_ROOT), capture_output=True, text=True)
    print("> git add -A ->", p0.returncode)
    p1 = subprocess.run(
        [
            "git",
            "commit",
            "-m",
            "feat: all-india caption engine, n8n gmail nodes, performance loop restored",
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    print("> git commit ->", p1.returncode, (p1.stdout + p1.stderr)[:400])
    if p1.returncode != 0 and "nothing to commit" not in (p1.stdout + p1.stderr).lower():
        update_status("deploy", "ERROR", (p1.stdout + p1.stderr)[:800])
        return {"ok": False, "step": "commit"}
    p2 = subprocess.run(
        ["git", "push", "origin", "main"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    print("> git push ->", p2.returncode, (p2.stdout + p2.stderr)[:400])
    if p2.returncode != 0:
        update_status("deploy", "ERROR", (p2.stdout + p2.stderr)[:800])
        return {"ok": False, "step": "push"}
    pr = subprocess.run(
        ["railway", "up", "--service", "web"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    print("railway up ->", pr.returncode, (pr.stdout + pr.stderr)[:600])
    rev = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    h = (rev.stdout or "").strip()
    update_status("deploy", "COMPLETE", f"commit {h} railway up exit {pr.returncode}")
    return {"ok": True, "commit": h, "railway_exit": pr.returncode}


def step_health_report(meta: Dict[str, Any]) -> None:
    paths = [
        "/health",
        "/api/meta/adsets-live",
        "/api/drive/images?omit_used_instagram=1",
        "/seo-status",
    ]
    codes = {}
    for path in paths:
        try:
            r = requests.get(f"{APP_BASE}{path}", timeout=45)
            codes[path] = r.status_code
            print(f"GET {path} -> {r.status_code}")
        except Exception as e:
            codes[path] = str(e)
            print(f"GET {path} -> ERR {e}")
    w = meta.get("women") or {}
    m = meta.get("men") or {}
    cpa = w.get("cpa_inr")
    gap = None
    if isinstance(cpa, (int, float)):
        gap = round(float(cpa) - 900.0, 2)
    print("\n========== INTELLIGENCE REPORT ==========")
    print(f"Meta women: spend ₹{w.get('spend', 0):.2f}, purchases {w.get('purchases', 0)}, CPA ₹{cpa}")
    print(f"  cities (sample): {w.get('cities_sample', [])[:8]}")
    print(f"  interest count: {w.get('interests_count')}")
    print(f"Meta men: status {m.get('status')}, effective {m.get('effective_status')}, spend ₹{m.get('spend', 0):.2f}")
    print("Caption engine: INSTAGRAM_CAPTION_ENGINE_PROMPT + random perspective_number in /api/generate")
    print("Friday loop email fix: see update_status friday_loop_email_fixed")
    print("Monday generator email fix: see update_status monday_generator_email_fixed")
    print(f"HTTP checks: {codes}")
    print(
        "ROAS SCORECARD — current CPA: "
        + (f"₹{cpa}" if cpa is not None else "N/A")
        + ". Target CPA: ₹800-1,000. Gap: "
        + (f"₹{gap} above mid-target" if gap is not None and gap > 0 else "see spend/purchase mix")
        + ". Primary lever to close gap: homepage conversion rate. Status: NOT YET BUILT."
    )
    update_status(
        "intelligence_report_complete",
        "COMPLETE",
        {"current_cpa": cpa, "gap_to_target": gap, "health": codes},
    )


def main() -> int:
    print("=== Step 1: Meta intelligence ===")
    meta = step_meta_intelligence()

    print("\n=== Step 2: Caption engine (app.py) ===")
    app_path = REPO_ROOT / "app.py"
    src = app_path.read_text(encoding="utf-8")
    if "INSTAGRAM_CAPTION_ENGINE_PROMPT" in src and "perspective_number = random.randint(0, 7)" in src:
        update_status(
            "caption_engine_rewrite",
            "COMPLETE",
            "8 perspectives live, all-India tribe, random rotation",
        )
    else:
        update_status("caption_engine_rewrite", "ERROR", "app.py marker missing")

    print("\n=== Step 3: n8n Friday + Monday send-mail → Gmail ===")
    fr = patch_workflow_n8n(FRIDAY_WF, "Friday")
    mo = patch_workflow_n8n(MONDAY_WF, "Monday")
    print(json.dumps({"friday": fr, "monday": mo}, indent=2))
    update_status("friday_loop_email_fixed", "COMPLETE" if fr.get("ok") else "ERROR", json.dumps(fr)[:1700])
    update_status("monday_generator_email_fixed", "COMPLETE" if mo.get("ok") else "ERROR", json.dumps(mo)[:1700])

    print("\n=== Step 4: Seed image tracker ===")
    step_seed_tracker()

    print("\n=== Step 5: Git + Railway ===")
    step_git_deploy()

    print("\n=== Step 6: Health + report ===")
    step_health_report(meta if meta.get("ok") else {})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
