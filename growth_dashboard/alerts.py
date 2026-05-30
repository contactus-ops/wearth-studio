# -*- coding: utf-8 -*-
"""Gmail alerts for pipeline failures."""
from __future__ import annotations

import os
import smtplib
from email.mime.text import MIMEText


def send_gmail_alert(subject: str, body: str, *, to: str | None = None) -> bool:
    user = (os.environ.get("GMAIL_USER") or os.environ.get("WEARTH_ALERT_EMAIL_FROM") or "").strip()
    pwd = (os.environ.get("GMAIL_APP_PASSWORD") or "").strip()
    recipient = (to or os.environ.get("WEARTH_ALERT_EMAIL_TO") or "abhi@wearthactive.com").strip()
    if not user or not pwd:
        return False
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = recipient
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as smtp:
        smtp.login(user, pwd)
        smtp.sendmail(user, [recipient], msg.as_string())
    return True


def meta_token_expired_alert(detail: str) -> bool:
    return send_gmail_alert(
        "WEARTH: Meta Insights token expired — Growth Dashboard",
        f"Meta API rejected the insights token (META_INSIGHTS_TOKEN).\n\n"
        f"Refresh the system user token in Meta Business Manager (ads_read scope) "
        f"and update Railway env META_INSIGHTS_TOKEN.\n\n"
        f"Reminder: long-lived token refresh due ~July 27.\n\n"
        f"Error:\n{detail[:2000]}",
        to="abhi@wearthactive.com",
    )
