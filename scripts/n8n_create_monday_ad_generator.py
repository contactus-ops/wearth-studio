# -*- coding: utf-8 -*-
# TARGET ROAS 4:1 AT ₹15K/MONTH SPEND — WEARTH Monday Ad Generator → n8n Cloud.
"""
Schedule: Monday 7:00 Asia/Kolkata (cron 0 7 * * 1).

Env on n8n (mirror Railway): ANTHROPIC_API_KEY, WEARTH_N8N_MAIL_TOKEN, and for the publish+poll
Code node the web app needs no extra token for internal poll URLs.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import uuid
from typing import Any, Dict, List

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from n8n_api_common import load_n8n_api_key, sanitize_settings, upsert_workflow

WORKFLOW_NAME = "WEARTH Monday Ad Generator"
APP_BASE = "https://web-production-448c1.up.railway.app"
CAMPAIGN_ID = "120245108704880305"
META_V = "v19.0"


def _nid() -> str:
    return str(uuid.uuid4())


def _meta_q() -> List[Dict[str, str]]:
    return [
        {
            "name": "fields",
            "value": "impressions,clicks,spend,actions,action_values,cpc,cpm,ctr",
        },
        {"name": "date_preset", "value": "last_7d"},
        {"name": "access_token", "value": "={{ $env.META_ACCESS_TOKEN }}"},
    ]


def build_workflow() -> Dict[str, Any]:
    n0, n1, n2, n3, n4, n5, n6, n7, n8, n9, n10 = (_nid() for _ in range(11))
    y, x0, dx = 300, 100, 220
    pos = lambda i: [x0 + i * dx, y]

    system_prompt = (
        "You are WEARTH's ad intelligence engine. TARGET ROAS 4:1 AT ₹15K/MONTH SPEND. "
        "WEARTH is premium plant-based activewear targeting urban fitness consumers in Mumbai, "
        "Delhi, Bangalore. Brand rules: never use TENCEL, lyocell, eco-friendly, sustainable, "
        "journey, conscious, intentional, em dashes, exclamation marks. Fabric language: "
        "plant-based fabric, fabric from trees, botanical fibre. Voice: quiet luxury, short "
        "sentences, uneven rhythm. Target: Bandra-Worli tribe, 25-40, ingredient-aware, done with "
        "polyester. Anchor quote: I literally live in WEARTH now. It's hard to go back — Aisha, "
        "Bandra. Generate an ad plan as JSON only with fields: headline, body, cta, "
        "audience_summary, scheduled_hour (integer 6-22, pick when Mumbai fitness crowd is most "
        "active on this day of week), reasoning (2-3 sentences on why this ad at this time helps "
        "reach ROAS 4), predicted_roas (float). Return JSON only, no markdown, no backticks."
    )

    pick_js = """const list = $('List Drive Videos').first().json;
const used = $('Campaign Used Videos').first().json;
const vids = list.videos || [];
const usedSet = new Set((used.video_ids || []).map(String));
let pick = null;
for (const v of vids) {
  const id = String(v.id || '');
  if (id && !usedSet.has(id)) {
    pick = v;
    break;
  }
}
if (!pick && vids.length) {
  pick = vids[Math.floor(Math.random() * vids.length)];
}
if (!pick) {
  throw new Error('No videos from Drive');
}
return [
  {
    json: {
      video_details: JSON.stringify(pick),
      drive_file_id: pick.id,
      video_label: pick.name || pick.id,
    },
  },
];
"""

    build_anthropic_js = f"""const system = {json.dumps(system_prompt)};
const video_details = $('Pick Unused Video').first().json.video_details;
const meta_insights = JSON.stringify($('Meta Campaign 7d').first().json);
const userMsg =
  'Today is Monday. Selected video: ' +
  video_details +
  '. Last 7 days Meta performance: ' +
  meta_insights +
  '.';
return [
  {{
    json: {{
      anthropic_body: {{
        model: 'claude-sonnet-4-20250514',
        max_tokens: 1000,
        system,
        messages: [{{ role: 'user', content: userMsg }}],
      }},
    }},
  }},
];
"""

    parse_js = """const t = $input.first().json.content[0].text;
let s = t.replace(/```json\\s*/gi, '').replace(/```/g, '').trim();
const plan = JSON.parse(s);
const pick = $('Pick Unused Video').first().json;
return [
  {
    json: {
      plan,
      drive_file_id: pick.drive_file_id,
    },
  },
];
"""

    # Same synchronous pipeline as Flask publish-video-from-drive (async:false): Drive → advideo → _create_meta_video_ad_from_video_id (PAUSED). Avoids publish-video-async Meta access issues.
    publish_js = f"""const base = '{APP_BASE}';
const row = $input.first().json;
const plan = row.plan || {{}};
const drive_file_id = row.drive_file_id;
const self = this;

return await (async () => {{
  const body = {{
    drive_file_id,
    headline: String(plan.headline || ''),
    primary_text: String(plan.body || ''),
    cta: String(plan.cta || 'Shop Now'),
    daily_budget: 200,
    variant_id: 'A',
    async: false,
  }};
  const res = await self.helpers.httpRequest({{
    method: 'POST',
    url: base + '/api/meta-advantage/publish-video-from-drive',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify(body),
    json: true,
    timeout: 900000,
  }});
  if (res && res.ok === false) {{
    throw new Error(res.error || res.message || 'publish-video-from-drive rejected');
  }}
  const pr = res.publish_result || {{}};
  const ad_id = String(pr.ad_id || res.ad_id || '');
  const campaign_id = String(pr.campaign_id || res.campaign_id || '');
  const adset_id = String(pr.adset_id || res.adset_id || '');
  const video_id = String(pr.video_id || res.video_id || '');

  return [
    {{
      json: {{
        plan,
        drive_file_id,
        ad_id,
        campaign_id,
        adset_id,
        video_id,
        creative_url: plan.creative_url || '',
      }},
    }},
  ];
}})();
"""

    pending_body = """={{ JSON.stringify({
  ad_id: $json.ad_id,
  adset_id: $json.adset_id,
  campaign_id: $json.campaign_id,
  video_id: $json.video_id,
  headline: $json.plan.headline,
  body: $json.plan.body,
  cta: $json.plan.cta,
  audience_summary: $json.plan.audience_summary,
  scheduled_hour: $json.plan.scheduled_hour,
  reasoning: $json.plan.reasoning,
  predicted_roas: $json.plan.predicted_roas,
  creative_url: $json.creative_url,
  created_at: new Date().toISOString(),
  status: 'pending'
}) }}"""

    mail_body = """={{ JSON.stringify({
  to: 'contactus@wearthactive.com',
  subject: 'New WEARTH ad ready for approval — ' + $now.setZone('Asia/Kolkata').toFormat('dd MMM yyyy'),
  text:
    'Shai, your weekly ad is ready. Review and approve it at https://wearth-ads.up.railway.app.\\n\\nThe AI recommends this ad because: ' +
    ($('Publish Paused Video Sync Graph').first().json.plan.reasoning || '') +
    '\\n\\nPredicted ROAS: ' +
    String($('Publish Paused Video Sync Graph').first().json.plan.predicted_roas ?? '')
}) }}"""

    nodes: List[Dict[str, Any]] = [
        {
            "parameters": {
                "rule": {
                    "interval": [{"field": "cronExpression", "expression": "0 7 * * 1"}]
                },
                "timezone": "Asia/Kolkata",
            },
            "id": n0,
            "name": "Every Monday 7am IST",
            "type": "n8n-nodes-base.scheduleTrigger",
            "typeVersion": 1.2,
            "position": pos(0),
        },
        {
            "parameters": {
                "method": "GET",
                "url": f"{APP_BASE}/api/drive/videos",
                "authentication": "none",
                "options": {"timeout": 120000},
            },
            "id": n1,
            "name": "List Drive Videos",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": pos(1),
        },
        {
            "parameters": {
                "method": "GET",
                "url": f"{APP_BASE}/api/meta/campaign-used-videos",
                "authentication": "none",
                "sendQuery": True,
                "queryParameters": {
                    "parameters": [
                        {
                            "name": "campaign_id",
                            "value": CAMPAIGN_ID,
                        }
                    ]
                },
                "options": {"timeout": 120000},
            },
            "id": n2,
            "name": "Campaign Used Videos",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": pos(2),
        },
        {
            "parameters": {"language": "javaScript", "jsCode": pick_js},
            "id": n3,
            "name": "Pick Unused Video",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": pos(3),
        },
        {
            "parameters": {
                "method": "GET",
                "url": f"https://graph.facebook.com/{META_V}/{CAMPAIGN_ID}/insights",
                "authentication": "none",
                "sendQuery": True,
                "queryParameters": {"parameters": _meta_q()},
                "options": {"timeout": 120000},
            },
            "id": n4,
            "name": "Meta Campaign 7d",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": pos(4),
        },
        {
            "parameters": {"language": "javaScript", "jsCode": build_anthropic_js},
            "id": n5,
            "name": "Build Claude Request",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": pos(5),
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
                        {"name": "x-api-key", "value": "={{ $env.ANTHROPIC_API_KEY }}"},
                    ]
                },
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": "={{ JSON.stringify($json.anthropic_body) }}",
                "options": {"timeout": 180000},
            },
            "id": n6,
            "name": "Claude Ad Plan",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": pos(6),
        },
        {
            "parameters": {"language": "javaScript", "jsCode": parse_js},
            "id": n7,
            "name": "Parse JSON Plan",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": pos(7),
        },
        {
            "parameters": {"language": "javaScript", "jsCode": publish_js},
            "id": n8,
            "name": "Publish Paused Video Sync Graph",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": pos(8),
        },
        {
            "parameters": {
                "method": "POST",
                "url": f"{APP_BASE}/api/ads/pending",
                "authentication": "none",
                "sendHeaders": True,
                "headerParameters": {
                    "parameters": [{"name": "Content-Type", "value": "application/json"}]
                },
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": pending_body,
                "options": {"timeout": 120000},
            },
            "id": n9,
            "name": "POST Pending Ad",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": pos(9),
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
                "jsonBody": mail_body,
                "options": {"timeout": 120000},
            },
            "id": n10,
            "name": "Email Shai",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": pos(10),
        },
    ]

    # fix duplicate variable - last two nodes need unique ids - used _nid() inline but second call new - ok

    connections = {
        "Every Monday 7am IST": {
            "main": [[{"node": "List Drive Videos", "type": "main", "index": 0}]]
        },
        "List Drive Videos": {
            "main": [[{"node": "Campaign Used Videos", "type": "main", "index": 0}]]
        },
        "Campaign Used Videos": {
            "main": [[{"node": "Pick Unused Video", "type": "main", "index": 0}]]
        },
        "Pick Unused Video": {
            "main": [[{"node": "Meta Campaign 7d", "type": "main", "index": 0}]]
        },
        "Meta Campaign 7d": {
            "main": [[{"node": "Build Claude Request", "type": "main", "index": 0}]]
        },
        "Build Claude Request": {
            "main": [[{"node": "Claude Ad Plan", "type": "main", "index": 0}]]
        },
        "Claude Ad Plan": {
            "main": [[{"node": "Parse JSON Plan", "type": "main", "index": 0}]]
        },
        "Parse JSON Plan": {
            "main": [[{"node": "Publish Paused Video Sync Graph", "type": "main", "index": 0}]]
        },
        "Publish Paused Video Sync Graph": {
            "main": [[{"node": "POST Pending Ad", "type": "main", "index": 0}]]
        },
        "POST Pending Ad": {"main": [[{"node": "Email Shai", "type": "main", "index": 0}]]},
    }

    return {
        "name": WORKFLOW_NAME,
        "nodes": nodes,
        "connections": connections,
        "settings": sanitize_settings(
            {
                "executionOrder": "v1",
                "timezone": "Asia/Kolkata",
                "saveDataErrorExecution": "all",
                "saveDataSuccessExecution": "all",
            }
        ),
    }


def main() -> None:
    base = (os.environ.get("N8N_BASE_URL") or "https://wearthactive.app.n8n.cloud").rstrip("/")
    key = load_n8n_api_key()
    if not key:
        print(json.dumps({"error": "N8N_API_KEY missing"}))
        sys.exit(1)
    wf = build_workflow()
    try:
        wf_id, activated = upsert_workflow(base, key, wf, WORKFLOW_NAME)
    except RuntimeError as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        sys.exit(1)
    print(
        json.dumps(
            {
                "ok": True,
                "workflow_id": wf_id,
                "workflow_name": WORKFLOW_NAME,
                "active": activated,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
