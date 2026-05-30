# -*- coding: utf-8 -*-
"""Shopify Daily metrics → Growth Dashboard Tab 2."""
from __future__ import annotations

import json
import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

SHOP = "wearthactive.myshopify.com"
API_VER = "2024-01"


def _token() -> str:
    t = (os.environ.get("SHOPIFY_TOKEN") or "").strip()
    if not t:
        raise RuntimeError("SHOPIFY_TOKEN is not set")
    return t


def _graphql(query: str, variables: dict | None = None) -> dict:
    url = f"https://{SHOP}/admin/api/{API_VER}/graphql.json"
    r = requests.post(
        url,
        headers={"X-Shopify-Access-Token": _token(), "Content-Type": "application/json"},
        json={"query": query, "variables": variables or {}},
        timeout=120,
    )
    data = r.json() if r.text else {}
    if r.status_code != 200 or data.get("errors"):
        raise RuntimeError(json.dumps(data.get("errors") or r.text[:500]))
    return data.get("data") or {}


def _yesterday_range_utc() -> tuple[str, str]:
    """UTC date strings for yesterday (Shopify reporting uses shop timezone often; close enough)."""
    now = datetime.now(timezone.utc)
    end = (now - timedelta(days=1)).replace(hour=23, minute=59, second=59)
    start = end.replace(hour=0, minute=0, second=0)
    return start.date().isoformat(), end.date().isoformat()


def _shopifyql_sessions(day: str) -> dict[str, Any]:
    """Try ShopifyQL sessions table (Shopify Plus / analytics scope)."""
    q = f"""
    FROM sessions
    SHOW sessions, online_store_visitors, bounce_rate, sessions_with_cart_additions,
         sessions_that_reached_checkout, sessions_that_completed_checkout, conversion_rate
    WHERE day = '{day}'
    GROUP BY day
    """
    try:
        data = _graphql(
            """
            query($q: String!) {
              shopifyqlQuery(query: $q) {
                tableData { columns { name } rows }
                parseErrors
              }
            }
            """,
            {"q": q},
        )
    except RuntimeError as e:
        if "shopifyqlQuery" in str(e):
            return {"ok": False, "error": "shopifyql_not_available_on_store"}
        raise
    block = data.get("shopifyqlQuery") or {}
    if block.get("parseErrors"):
        return {"ok": False, "error": block.get("parseErrors")}
    rows = (block.get("tableData") or {}).get("rows") or []
    cols = [c.get("name") for c in (block.get("tableData") or {}).get("columns") or []]
    if not rows:
        return {"ok": False, "error": "no shopifyql rows"}
    row = rows[0]
    if isinstance(row, list):
        return {"ok": True, "data": dict(zip(cols, row))}
    return {"ok": True, "data": row}


def _orders_metrics(day: str) -> dict[str, Any]:
    """Fallback: orders created on day for revenue/AOV/conversion proxies."""
    start = f"{day}T00:00:00+05:30"
    end = f"{day}T23:59:59+05:30"
    q = """
    query($q: String!) {
      orders(first: 250, query: $q, sortKey: CREATED_AT, reverse: true) {
        nodes {
          id
          name
          totalPriceSet { shopMoney { amount } }
          lineItems(first: 20) { nodes { quantity title product { title handle } } }
        }
      }
    }
    """
    query = f"created_at:>={start} created_at:<={end} financial_status:paid"
    data = _graphql(q, {"q": query})
    orders = (data.get("orders") or {}).get("nodes") or []
    revenue = 0.0
    product_counts: Counter = Counter()
    for o in orders:
        try:
            revenue += float((o.get("totalPriceSet") or {}).get("shopMoney", {}).get("amount") or 0)
        except (TypeError, ValueError):
            pass
        for li in (o.get("lineItems") or {}).get("nodes") or []:
            title = (li.get("product") or {}).get("title") or li.get("title") or ""
            product_counts[title] += int(li.get("quantity") or 1)
    n = len(orders)
    aov = round(revenue / n, 2) if n else 0
    top_products = "; ".join(f"{t} ({c})" for t, c in product_counts.most_common(5))
    return {
        "revenue_inr": round(revenue, 2),
        "orders": n,
        "aov_inr": aov,
        "top_products_orders": top_products,
    }


def fetch_daily_report(report_date: str | None = None) -> dict[str, Any]:
    report_date = report_date or _yesterday_range_utc()[0]
    note_parts = []
    sessions = visitors = bounce = conv = atc_rate = checkout_rate = purchase_rate = ""
    top_land = top_exit = top_views = top_atc = ""

    sq = _shopifyql_sessions(report_date)
    if sq.get("ok"):
        d = sq["data"]
        sessions = d.get("sessions", "")
        visitors = d.get("online_store_visitors", d.get("visitors", ""))
        bounce = d.get("bounce_rate", "")
        conv = d.get("conversion_rate", "")
        atc_rate = d.get("sessions_with_cart_additions", "")
        checkout_rate = d.get("sessions_that_reached_checkout", "")
        purchase_rate = d.get("sessions_that_completed_checkout", "")
        note_parts.append("shopifyql:sessions")
    else:
        note_parts.append(f"shopifyql_unavailable:{sq.get('error', '')[:120]}")

    orders = _orders_metrics(report_date)
    if not note_parts or "shopifyql" not in note_parts[0]:
        note_parts.append("orders_api:revenue_aov")
    elif orders["orders"]:
        note_parts.append("orders_api:revenue_aov")

    if not sessions and orders["orders"]:
        purchase_rate = orders["orders"]

    return {
        "date": report_date,
        "sessions": sessions,
        "unique_visitors": visitors,
        "bounce_rate": bounce,
        "top_5_landing_pages": top_land,
        "top_5_exit_pages": top_exit,
        "conversion_rate": conv,
        "atc_rate": atc_rate,
        "checkout_initiation_rate": checkout_rate,
        "purchase_rate": purchase_rate if purchase_rate != "" else orders.get("orders", ""),
        "revenue_inr": orders["revenue_inr"],
        "average_order_value_inr": orders["aov_inr"],
        "top_5_products_by_views": top_views,
        "top_5_products_by_atc": orders.get("top_products_orders", ""),
        "data_source_note": " | ".join(note_parts),
    }


def row_for_sheet(report: dict, synced_at: str) -> list:
    return [
        report.get("date", ""),
        report.get("sessions", ""),
        report.get("unique_visitors", ""),
        report.get("bounce_rate", ""),
        report.get("top_5_landing_pages", ""),
        report.get("top_5_exit_pages", ""),
        report.get("conversion_rate", ""),
        report.get("atc_rate", ""),
        report.get("checkout_initiation_rate", ""),
        report.get("purchase_rate", ""),
        report.get("revenue_inr", ""),
        report.get("average_order_value_inr", ""),
        report.get("top_5_products_by_views", ""),
        report.get("top_5_products_by_atc", ""),
        report.get("data_source_note", ""),
        synced_at,
    ]
