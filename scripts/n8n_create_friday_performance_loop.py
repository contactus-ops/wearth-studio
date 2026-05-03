# -*- coding: utf-8 -*-
# TARGET ROAS 4:1 AT ₹15K/MONTH SPEND — WEARTH Friday Performance Loop → n8n Cloud API.
"""
Creates / updates workflow "WEARTH Friday Performance Loop" on wearthactive.app.n8n.cloud.

Requires (e.g. railway run): N8N_BASE_URL, N8N_API_KEY, and on the n8n instance env vars
mirroring Railway: META_ACCESS_TOKEN, ANTHROPIC_API_KEY, WEARTH_N8N_MAIL_TOKEN (must match web).

Schedule: cron 0 8 * * 5, timezone Asia/Kolkata.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from typing import Any, Dict, List, Optional, Tuple

WORKFLOW_NAME = "WEARTH Friday Performance Loop"
APP_BASE = "https://web-production-448c1.up.railway.app"
META_V = "v19.0"
CAMPAIGN_ID = "120245108704880305"
WOMEN_ADSET = "120245108705080305"
MEN_ADSET = "120245228295720305"


def _nid() -> str:
    return str(uuid.uuid4())


def _req(
    method: str,
    url: str,
    *,
    n8n_key: Optional[str] = None,
    body: Optional[bytes] = None,
    content_type: Optional[str] = None,
) -> Tuple[int, str]:
    headers: Dict[str, str] = {"Accept": "application/json"}
    if n8n_key:
        headers["X-N8N-API-KEY"] = n8n_key
    if content_type:
        headers["Content-Type"] = content_type
    r = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(r, timeout=180) as resp:
            return resp.getcode(), resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")


_ALLOWED_WORKFLOW_SETTINGS_KEYS = frozenset(
    {
        "saveExecutionProgress",
        "saveManualExecutions",
        "saveDataErrorExecution",
        "saveDataSuccessExecution",
        "executionTimeout",
        "errorWorkflow",
        "timezone",
        "executionOrder",
        "callerPolicy",
        "callerIds",
        "timeSavedPerExecution",
        "availableInMCP",
        "sharedWorkflow",
    }
)


def _sanitize_settings(s: Any) -> Dict[str, Any]:
    if not isinstance(s, dict):
        return {}
    return {k: v for k, v in s.items() if k in _ALLOWED_WORKFLOW_SETTINGS_KEYS}


def _prune_minimal_put(wf: Dict[str, Any]) -> Dict[str, Any]:
    o: Dict[str, Any] = {
        "name": wf["name"],
        "nodes": wf["nodes"],
        "connections": wf["connections"],
        "settings": _sanitize_settings(wf.get("settings")),
    }
    if "active" in wf:
        o["active"] = wf["active"]
    return o


def _load_n8n_api_key() -> str:
    key = (os.environ.get("N8N_API_KEY") or "").strip()
    path = (os.environ.get("N8N_API_KEY_FILE") or "").strip()
    if not key and path:
        with open(path, encoding="utf-8") as f:
            key = f.read().strip()
    return key


def _meta_query_params() -> List[Dict[str, str]]:
    return [
        {
            "name": "fields",
            "value": "impressions,clicks,spend,actions,action_values,cpc,cpm,ctr",
        },
        {"name": "date_preset", "value": "last_7d"},
        {"name": "access_token", "value": "={{ $env.META_ACCESS_TOKEN }}"},
    ]


def _http_get_node(
    nid: str,
    name: str,
    url: str,
    pos: List[int],
) -> Dict[str, Any]:
    return {
        "parameters": {
            "method": "GET",
            "url": url,
            "authentication": "none",
            "sendQuery": True,
            "queryParameters": {"parameters": _meta_query_params()},
            "options": {"timeout": 120000},
        },
        "id": nid,
        "name": name,
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": pos,
    }


def _http_get_simple(nid: str, name: str, url: str, pos: List[int]) -> Dict[str, Any]:
    return {
        "parameters": {
            "method": "GET",
            "url": url,
            "authentication": "none",
            "options": {"timeout": 120000},
        },
        "id": nid,
        "name": name,
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": pos,
    }


def build_workflow() -> Dict[str, Any]:
    # Stable ids for connections
    n_sched = _nid()
    n_k1 = _nid()
    n_k2 = _nid()
    n_seo = _nid()
    n_mcamp = _nid()
    n_mmen = _nid()
    n_mw = _nid()
    n_build = _nid()
    n_claude = _nid()
    n_parse = _nid()
    n_prep = _nid()
    n_pause = _nid()
    n_mail = _nid()

    y = 300
    x0 = 100
    dx = 220

    pos = lambda i: [x0 + i * dx, y]

    system_prompt = (
        "You are WEARTH's growth analyst. WEARTH is a premium plant-based activewear brand "
        "targeting urban fitness consumers in Mumbai, Delhi, Bangalore. Target ROAS is 4:1 at "
        "₹15,000/month ad spend. AOV is ₹2,000. Target CPA is ₹800-1,000. Current CPA is "
        "₹2,500-3,700. Women's adset id is 120245108705080305. Men's adset id is 120245228295720305. "
        "Analyze the weekly performance data and return a sharp concise report with exactly three "
        "sections: 1. What's working 2. What's bleeding 3. Three specific action points for next week. "
        "End with a one-line ROAS outlook. No fluff. Be direct."
    )

    build_js = f"""const system = {json.dumps(system_prompt)};
const ka = JSON.stringify($('Klaviyo Active Count').first().json);
const kh = JSON.stringify($('Klaviyo Hot Profiles').first().json);
const seo = JSON.stringify($('SEO Status').first().json);
const mc = JSON.stringify($('Meta Campaign Insights').first().json);
const mm = JSON.stringify($('Meta Men Adset Insights').first().json);
const userMsg =
  'Here is this week\\'s data — Klaviyo active profiles: ' +
  ka +
  '. Hot profiles: ' +
  kh +
  '. SEO status: ' +
  seo +
  '. Women\\'s Meta campaign last 7 days: ' +
  mc +
  '. Men\\'s adset last 7 days: ' +
  mm +
  '.';
const anthropic_body = {{
  model: 'claude-sonnet-4-20250514',
  max_tokens: 1500,
  system,
  messages: [{{ role: 'user', content: userMsg }}],
}};
return [{{ json: {{ anthropic_body }} }}];
"""

    parse_js = """const raw = $input.first().json;
const text =
  raw.content && raw.content[0] && raw.content[0].text
    ? raw.content[0].text
    : JSON.stringify(raw);
return [{ json: { report_text: text } }];
"""

    prepare_js = """function roasFromInsight(insightJson) {
  const row = insightJson?.data?.[0];
  if (!row) return null;
  const spend = parseFloat(row.spend || '0');
  const avs = row.action_values || [];
  let pv = 0;
  for (const a of avs) {
    const t = (a.action_type || '').toLowerCase();
    if (t.includes('purchase') || t.includes('omni_purchase')) {
      pv += parseFloat(String(a.value || '0'));
    }
  }
  if (spend <= 0) return pv > 0 ? 999 : null;
  return pv / spend;
}

const women_insights = $('Meta Women Adset Insights').first().json;
const men_insights = $('Meta Men Adset Insights').first().json;
const rw = roasFromInsight(women_insights);
const rm = roasFromInsight(men_insights);

const klaviyo_active_count = $('Klaviyo Active Count').first().json;
const klaviyo_hot_profiles = $('Klaviyo Hot Profiles').first().json;
const seo_status = $('SEO Status').first().json;
const meta_insights = $('Meta Campaign Insights').first().json;

const report_text = $input.first().json.report_text || '';
const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const d = new Date();
const subject =
  'WEARTH weekly performance — ' +
  String(d.getDate()).padStart(2, '0') +
  ' ' +
  months[d.getMonth()] +
  ' ' +
  d.getFullYear();

const raw_footer =
  '\\n\\n--- RAW NUMBERS ---\\n' +
  JSON.stringify(
    {
      klaviyo_active_count,
      klaviyo_hot_profiles,
      seo_status,
      meta_insights,
      men_insights,
      women_insights,
      roas_womens_adset_7d: rw,
      roas_mens_adset_7d: rm,
    },
    null,
    2
  );

const email_text = report_text + raw_footer;

return [
  {
    json: {
      subject,
      email_text,
      pause_women: rw != null && rw < 1.5,
      pause_men: rm != null && rm < 1.5,
    },
  },
];
"""

    pause_js = """const prep = $input.first().json;
const token = $env.META_ACCESS_TOKEN;
const self = this;

return await (async () => {
  async function pauseOne(id) {
    const qs = new URLSearchParams({ status: 'PAUSED', access_token: token });
    return await self.helpers.httpRequest({
      method: 'POST',
      url: `https://graph.facebook.com/v19.0/${id}?${qs.toString()}`,
      json: true,
    });
  }

  let pw = null;
  let pm = null;
  try {
    if (prep.pause_women && token) {
      pw = await pauseOne('120245108705080305');
    }
  } catch (e) {
    pw = { error: String(e) };
  }
  try {
    if (prep.pause_men && token) {
      pm = await pauseOne('120245228295720305');
    }
  } catch (e) {
    pm = { error: String(e) };
  }

  const extra =
    pw || pm
      ? '\\n\\n--- Ad set pause ---\\n' + JSON.stringify({ women: pw, men: pm }, null, 2)
      : '';

  return [
    {
      json: {
        to: 'contactus@wearthactive.com',
        subject: prep.subject,
        text: prep.email_text + extra,
      },
    },
  ];
})();
"""

    nodes: List[Dict[str, Any]] = [
        {
            "parameters": {
                "rule": {
                    "interval": [
                        {
                            "field": "cronExpression",
                            "expression": "0 8 * * 5",
                        }
                    ]
                },
                "timezone": "Asia/Kolkata",
            },
            "id": n_sched,
            "name": "Every Friday 8am IST",
            "type": "n8n-nodes-base.scheduleTrigger",
            "typeVersion": 1.2,
            "position": pos(0),
        },
        _http_get_simple(
            n_k1,
            "Klaviyo Active Count",
            f"{APP_BASE}/api/klaviyo/active-count",
            pos(1),
        ),
        _http_get_simple(
            n_k2,
            "Klaviyo Hot Profiles",
            f"{APP_BASE}/api/klaviyo/hot-profiles",
            pos(2),
        ),
        _http_get_simple(n_seo, "SEO Status", f"{APP_BASE}/seo-status", pos(3)),
        _http_get_node(
            n_mcamp,
            "Meta Campaign Insights",
            f"https://graph.facebook.com/{META_V}/{CAMPAIGN_ID}/insights",
            pos(4),
        ),
        _http_get_node(
            n_mmen,
            "Meta Men Adset Insights",
            f"https://graph.facebook.com/{META_V}/{MEN_ADSET}/insights",
            pos(5),
        ),
        _http_get_node(
            n_mw,
            "Meta Women Adset Insights",
            f"https://graph.facebook.com/{META_V}/{WOMEN_ADSET}/insights",
            pos(6),
        ),
        {
            "parameters": {
                "language": "javaScript",
                "jsCode": build_js,
            },
            "id": n_build,
            "name": "Build Anthropic Body",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": pos(7),
        },
        {
            "parameters": {
                "method": "POST",
                "url": "https://api.anthropic.com/v1/messages",
                "authentication": "none",
                "sendHeaders": True,
                "headerParameters": {
                    "parameters": [
                        {"name": "anthropic-version", "value": "2023-06-01"},
                        {"name": "Content-Type", "value": "application/json"},
                        {
                            "name": "x-api-key",
                            "value": "={{ $env.ANTHROPIC_API_KEY }}",
                        },
                    ]
                },
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": "={{ JSON.stringify($json.anthropic_body) }}",
                "options": {"timeout": 180000},
            },
            "id": n_claude,
            "name": "Claude Weekly Report",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": pos(8),
        },
        {
            "parameters": {"language": "javaScript", "jsCode": parse_js},
            "id": n_parse,
            "name": "Parse Claude Response",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": pos(9),
        },
        {
            "parameters": {"language": "javaScript", "jsCode": prepare_js},
            "id": n_prep,
            "name": "Prepare Email And Pause Flags",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": pos(10),
        },
        {
            "parameters": {"language": "javaScript", "jsCode": pause_js},
            "id": n_pause,
            "name": "Apply Pauses And Mail Payload",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": pos(11),
        },
        {
            "parameters": {
                "method": "POST",
                "url": f"{APP_BASE}/api/n8n/send-mail",
                "authentication": "none",
                "sendHeaders": True,
                "headerParameters": {
                    "parameters": [
                        {"name": "Content-Type", "value": "application/json"},
                        {
                            "name": "X-Wearth-N8n-Mail",
                            "value": "={{ $env.WEARTH_N8N_MAIL_TOKEN }}",
                        },
                    ]
                },
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": "={{ JSON.stringify({ to: $json.to, subject: $json.subject, text: $json.text }) }}",
                "options": {"timeout": 120000},
            },
            "id": n_mail,
            "name": "Send Report Email",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": pos(12),
        },
    ]

    connections: Dict[str, Any] = {
        "Every Friday 8am IST": {
            "main": [[{"node": "Klaviyo Active Count", "type": "main", "index": 0}]]
        },
        "Klaviyo Active Count": {
            "main": [[{"node": "Klaviyo Hot Profiles", "type": "main", "index": 0}]]
        },
        "Klaviyo Hot Profiles": {
            "main": [[{"node": "SEO Status", "type": "main", "index": 0}]]
        },
        "SEO Status": {
            "main": [[{"node": "Meta Campaign Insights", "type": "main", "index": 0}]]
        },
        "Meta Campaign Insights": {
            "main": [[{"node": "Meta Men Adset Insights", "type": "main", "index": 0}]]
        },
        "Meta Men Adset Insights": {
            "main": [[{"node": "Meta Women Adset Insights", "type": "main", "index": 0}]]
        },
        "Meta Women Adset Insights": {
            "main": [[{"node": "Build Anthropic Body", "type": "main", "index": 0}]]
        },
        "Build Anthropic Body": {
            "main": [[{"node": "Claude Weekly Report", "type": "main", "index": 0}]]
        },
        "Claude Weekly Report": {
            "main": [[{"node": "Parse Claude Response", "type": "main", "index": 0}]]
        },
        "Parse Claude Response": {
            "main": [[{"node": "Prepare Email And Pause Flags", "type": "main", "index": 0}]]
        },
        "Prepare Email And Pause Flags": {
            "main": [[{"node": "Apply Pauses And Mail Payload", "type": "main", "index": 0}]]
        },
        "Apply Pauses And Mail Payload": {
            "main": [[{"node": "Send Report Email", "type": "main", "index": 0}]]
        },
    }

    return {
        "name": WORKFLOW_NAME,
        "nodes": nodes,
        "connections": connections,
        "settings": _sanitize_settings(
            {
                "executionOrder": "v1",
                "timezone": "Asia/Kolkata",
                "saveDataErrorExecution": "all",
                "saveDataSuccessExecution": "all",
            }
        ),
        "staticData": None,
        "tags": [],
    }


def main() -> None:
    base = (os.environ.get("N8N_BASE_URL") or "https://wearthactive.app.n8n.cloud").rstrip("/")
    n8n_key = _load_n8n_api_key()
    if not n8n_key:
        print(json.dumps({"error": "N8N_API_KEY missing"}))
        sys.exit(1)

    wf = build_workflow()
    list_url = f"{base}/api/v1/workflows"
    code, raw_list = _req("GET", list_url, n8n_key=n8n_key)
    if code != 200:
        print(json.dumps({"step": "list workflows", "http": code, "body": raw_list[:3000]}))
        sys.exit(1)
    existing_id: Optional[str] = None
    try:
        arr = json.loads(raw_list)
        if isinstance(arr, dict) and isinstance(arr.get("data"), list):
            for row in arr["data"]:
                if isinstance(row, dict) and row.get("name") == WORKFLOW_NAME:
                    existing_id = row.get("id")
                    break
        elif isinstance(arr, list):
            for row in arr:
                if isinstance(row, dict) and row.get("name") == WORKFLOW_NAME:
                    existing_id = row.get("id")
                    break
    except Exception:
        pass

    payload = json.dumps(wf).encode("utf-8")
    if existing_id:
        put_url = f"{base}/api/v1/workflows/{existing_id}"
        code, raw_put = _req(
            "PUT",
            put_url,
            n8n_key=n8n_key,
            body=payload,
            content_type="application/json",
        )
        if code != 200:
            code, raw_put = _req(
                "PUT",
                put_url,
                n8n_key=n8n_key,
                body=json.dumps(_prune_minimal_put(wf)).encode("utf-8"),
                content_type="application/json",
            )
        if code != 200:
            print(json.dumps({"step": "PUT workflow", "http": code, "body": raw_put[:8000]}))
            sys.exit(1)
        wf_id = existing_id
    else:
        code, raw_post = _req(
            "POST",
            list_url,
            n8n_key=n8n_key,
            body=payload,
            content_type="application/json",
        )
        if code not in (200, 201):
            code, raw_post = _req(
                "POST",
                list_url,
                n8n_key=n8n_key,
                body=json.dumps(_prune_minimal_put(wf)).encode("utf-8"),
                content_type="application/json",
            )
        if code not in (200, 201):
            print(json.dumps({"step": "POST workflow", "http": code, "body": raw_post[:8000]}))
            sys.exit(1)
        try:
            created = json.loads(raw_post)
            wf_id = created.get("id") or created.get("data", {}).get("id")
        except Exception:
            wf_id = None
        if not wf_id:
            print(json.dumps({"error": "could not read workflow id from POST response", "raw": raw_post[:2000]}))
            sys.exit(1)

    act_url = f"{base}/api/v1/workflows/{wf_id}"
    activated = False
    for activate_try in (
        ("POST", f"{base}/api/v1/workflows/{wf_id}/activate"),
        ("PATCH", act_url),
    ):
        method, aurl = activate_try
        body = None
        content_type = None
        if method == "PATCH":
            body = json.dumps({"active": True}).encode("utf-8")
            content_type = "application/json"
        code_a, raw_a = _req(method, aurl, n8n_key=n8n_key, body=body, content_type=content_type)
        if code_a in (200, 201, 204):
            activated = True
            break

    if not activated:
        code_g, raw_g = _req("GET", act_url, n8n_key=n8n_key)
        if code_g == 200:
            try:
                merged = json.loads(raw_g)
            except Exception:
                merged = {}
            if isinstance(merged, dict):
                merged.pop("active", None)
                merged["name"] = merged.get("name") or WORKFLOW_NAME
                payload_activate = {
                    "name": merged["name"],
                    "nodes": merged.get("nodes") or wf["nodes"],
                    "connections": merged.get("connections") or wf["connections"],
                    "settings": _sanitize_settings(merged.get("settings")),
                }
                code_a2, raw_put = _req(
                    "PUT",
                    act_url,
                    n8n_key=n8n_key,
                    body=json.dumps(payload_activate).encode("utf-8"),
                    content_type="application/json",
                )
                if code_a2 != 200:
                    code_a2, raw_put = _req(
                        "PUT",
                        act_url,
                        n8n_key=n8n_key,
                        body=json.dumps(_prune_minimal_put(payload_activate)).encode("utf-8"),
                        content_type="application/json",
                    )
                activated = code_a2 == 200

    print(
        json.dumps(
            {
                "ok": True,
                "workflow_id": wf_id,
                "workflow_name": WORKFLOW_NAME,
                "active": activated,
                "note": "Set on n8n Cloud the same env vars as Railway: META_ACCESS_TOKEN, ANTHROPIC_API_KEY, WEARTH_N8N_MAIL_TOKEN.",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
