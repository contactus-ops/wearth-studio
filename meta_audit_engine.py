# -*- coding: utf-8 -*-
"""Run Meta campaign audit on Railway (Google SA available) → Drive folder."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from flask import jsonify, request

ROOT = Path(__file__).resolve().parent


def _admin_ok() -> bool:
    token = (os.environ.get("ADMIN_TOKEN") or os.environ.get("WEARTH_N8N_MAIL_TOKEN") or "").strip()
    if not token:
        return True
    return (request.headers.get("X-Wearth-Admin") or "").strip() == token


def meta_campaign_full_audit():
    if not _admin_ok():
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    campaign_id = (request.args.get("campaign_id") or "120246893576740305").strip()
    env = os.environ.copy()
    env["META_CAMPAIGN_AUDIT_ID"] = campaign_id
    script = ROOT / "scripts" / "meta_campaign_full_audit.py"
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )
    if proc.returncode != 0:
        return jsonify(
            {
                "ok": False,
                "error": "audit_script_failed",
                "stderr": proc.stderr[-3000:],
                "stdout": proc.stdout[-3000:],
            }
        ), 500
    try:
        result = json.loads(proc.stdout)
    except json.JSONDecodeError:
        result = {"ok": True, "raw_stdout": proc.stdout[-5000:]}
    return jsonify(result)
