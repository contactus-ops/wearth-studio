# WEARTH Growth Dashboard

Single Google Sheet **WEARTH Growth Dashboard** with six tabs. Data is written by Railway API endpoints triggered by n8n (and manual Cursor commands).

## Railway environment variables

| Variable | Purpose |
|----------|---------|
| `GROWTH_DASHBOARD_SHEET_ID` | Spreadsheet ID (run setup once) |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Service account with Sheets + Drive write |
| `GOOGLE_DRIVE_PARENT_FOLDER_ID` | Drive root for snapshots + creative folders |
| `META_INSIGHTS_TOKEN` | **ads_read** system user token (separate from `META_ACCESS_TOKEN`) |
| `SHOPIFY_TOKEN` | Admin API |
| `KLAVIYO_PRIVATE_KEY` | Campaign reporting |
| `GMAIL_USER` / `GMAIL_APP_PASSWORD` | Token expiry alerts to Abhi |
| `ADMIN_TOKEN` | n8n `X-Wearth-Admin` header |

### Meta system user token (ads_read)

1. Meta Business Manager → Business Settings → System users  
2. Create/select system user → Assign ad account `8979315238856807` with **View performance** (ads_read)  
3. Generate token (60-day long-lived) → store as `META_INSIGHTS_TOKEN` on Railway  
4. Refresh reminder: ~**July 27** (same cycle as existing ad-creation token)

Do **not** reuse `META_ACCESS_TOKEN` for insights if that token lacks `ads_read`.

## Setup

```bash
python scripts/growth_dashboard/setup_growth_sheet.py
# Copy GROWTH_DASHBOARD_SHEET_ID to Railway

python scripts/growth_dashboard/run_e2e_test.py

python scripts/n8n_create_growth_dashboard_workflows.py
```

Share the spreadsheet with the service account email (printed by `/api/growth/verify`).

## API endpoints

| Endpoint | Schedule | Tab |
|----------|----------|-----|
| `POST /api/growth/sync-daily` | Daily 8:00 IST (n8n) | Meta + Shopify append |
| `POST /api/growth/sync-meta-daily` | — | Meta Ads Daily |
| `POST /api/growth/sync-shopify-daily` | — | Shopify Daily |
| `POST /api/growth/sync-klaviyo-weekly` | Mon 8:00 IST | Klaviyo (full replace) |
| `POST /api/growth/sync-creative-registry` | Manual | Creative Registry |
| `POST /api/growth/run-site-audit` | On demand ("run site audit") | Website Snapshots |
| `GET /api/growth/verify` | — | Health check |

Header: `X-Wearth-Admin: <ADMIN_TOKEN>`

## Tab 6 — Clarity (manual)

Each Monday, save Clarity heatmap + scroll-depth PNGs for the five PDPs to Drive folder `Clarity Weekly / YYYY-MM-DD`, then append links to **Clarity Heatmaps Log** (manual or future automation).

## Klaviyo custom trigger

Unrelated to this sheet; see PDP performance notes. Popup form `YegaNJ` should use **30s AND 40% scroll** in Klaviyo UI.
