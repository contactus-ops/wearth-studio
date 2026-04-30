# WEARTH Studio Architecture Map

Purpose: quick wiring reference for n8n without reading `app.py`.

## Runtime + External Systems

- App runtime: Flask (`app.py`) on Railway
- Content generation: Anthropic API
- Image/video processing + storage: FAL.ai
- Commerce publishing: Shopify (via `seo_engine.py`)
- Ads: Meta Graph API
- Asset source: Google Drive API

---

## Environment Variables

### Core AI / Media
- `ANTHROPIC_API_KEY`
- `FAL_API_KEY`
- `GOOGLE_DRIVE_API_KEY`

### Meta Ads
- `META_ACCESS_TOKEN`
- `META_AD_ACCOUNT_ID`
- `META_APP_ID`
- `META_PAGE_ID`
- `META_PIXEL_ID`

### SEO / Shopify Engine
- `SHOPIFY_TOKEN`
- `UNSPLASH_ACCESS_KEY` (fallback imagery for SEO blog posts)

---

## Endpoints (Method, Path, Inputs, Response, Env, Status)

## Health + SEO Engine

- `GET /health`
  - **Inputs:** none
  - **Response:** `{ "status": "ok", "engine": "infinite" }`
  - **Env:** none
  - **Status:** working

- `POST /generate-article`
  - **Inputs:** optional `dry_run` (bool/string), optional `index`
  - **Response:** `{ "status": "started", "job_id": "...", "message": "Check /seo-job/<job_id> for result" }`
  - **Env:** `ANTHROPIC_API_KEY` (+ Shopify vars required downstream in `seo_engine.py`)
  - **Status:** working (async pattern)

- `GET /seo-job/<job_id>`
  - **Inputs:** path `job_id`
  - **Response:** running/complete/error payload from in-memory job map
  - **Env:** none
  - **Status:** working

- `GET /seo-status`
  - **Inputs:** none
  - **Response:** `{ "published": <count>, "engine": "infinite", "next_up": "..." }`
  - **Env:** Shopify credentials used via `seo_engine.py`
  - **Status:** working

## Frontend Static / PWA

- `GET /`
  - **Inputs:** none
  - **Response:** `index.html`
  - **Env:** none
  - **Status:** working

- `GET /manifest.json`
  - **Inputs:** none
  - **Response:** `manifest.json`
  - **Env:** none
  - **Status:** working

- `GET /sw.js`
  - **Inputs:** none
  - **Response:** service worker file
  - **Env:** none
  - **Status:** working

- `GET /<path:path>`
  - **Inputs:** static file path
  - **Response:** file or 404
  - **Env:** none
  - **Status:** working

## Instagram Content + Media

- `GET /api/garments`
  - **Inputs:** none
  - **Response:** garment list payload
  - **Env:** none
  - **Status:** working

- `POST /api/generate`
  - **Inputs:** `mood`, `image_url`, optional `skip_composite`, optional `logo_url`
  - **Response:** `{ "image_url", "headline", "tagline", "captions" }`
  - **Env:** `ANTHROPIC_API_KEY`, `FAL_API_KEY`
  - **Status:** working

- `POST /api/rephrase`
  - **Inputs:** `draft`
  - **Response:** `{ "rephrased": "..." }`
  - **Env:** `ANTHROPIC_API_KEY`
  - **Status:** working

- `POST /api/upload-image`
  - **Inputs:** `image_b64`, optional `content_type`
  - **Response:** `{ "url": "..." }`
  - **Env:** `FAL_API_KEY`
  - **Status:** working

## Kling / FAL Diagnostics + Video Generation

- `GET /api/tryon-test`
  - **Inputs:** none
  - **Response:** status/body preview test payload
  - **Env:** `FAL_API_KEY`
  - **Status:** working (diagnostic)

- `GET /api/fal-upload-test`
  - **Inputs:** none
  - **Response:** FAL upload-init status payload
  - **Env:** `FAL_API_KEY`
  - **Status:** working (diagnostic)

- `GET /api/kling-test`
  - **Inputs:** none
  - **Response:** Kling queue test status payload
  - **Env:** `FAL_API_KEY`
  - **Status:** working (diagnostic)

- `POST /api/kling/submit`
  - **Inputs:** `image_url`, optional `mood`
  - **Response:** `{ "request_id": "..." }`
  - **Env:** `FAL_API_KEY`
  - **Status:** working

- `POST /api/kling/status`
  - **Inputs:** `request_id`
  - **Response:** `{ "status": "..." }` or `{ "status": "COMPLETED", "video_url": "..." }`
  - **Env:** `FAL_API_KEY`
  - **Status:** working

## Asset Libraries

- `GET /api/library`
  - **Inputs:** none
  - **Response:** `{ "photos": [...] }`
  - **Env:** none
  - **Status:** working

- `POST /api/library/add`
  - **Inputs:** `image_b64`, optional `content_type`, optional `name`
  - **Response:** `{ "url": "...", "key": "..." }`
  - **Env:** `FAL_API_KEY`
  - **Status:** working

- `POST /api/library/delete`
  - **Inputs:** `key`
  - **Response:** `{ "ok": true }`
  - **Env:** none
  - **Status:** working

- `GET /api/logos`
  - **Inputs:** none
  - **Response:** `{ "logos": [...] }`
  - **Env:** none
  - **Status:** working

- `POST /api/logos/add`
  - **Inputs:** `image_b64`, optional `content_type`, optional `name`
  - **Response:** `{ "url": "...", "clean_url": "...", "key": "..." }`
  - **Env:** `FAL_API_KEY`
  - **Status:** working

- `POST /api/logos/delete`
  - **Inputs:** `key`
  - **Response:** `{ "ok": true }`
  - **Env:** none
  - **Status:** working

## Meta Advantage+ (Image)

- `POST /api/meta-advantage/generate`
  - **Inputs:** one or more of:
    - `google_drive_links[]`
    - `google_drive_folder_url` or `google_drive_folder_id`
    - `image_urls[]`
    - optional `creative_count`, optional `product_context`
  - **Response:** `{ "ok": true, "platform", "creative_count", "images_count", "variants", "images" }`
  - **Env:** `ANTHROPIC_API_KEY`, optional `GOOGLE_DRIVE_API_KEY` for folder listing
  - **Status:** working

- `POST /api/meta-advantage/publish`
  - **Inputs:** `variant_id`, `headline`, `primary_text`, `image_url`, `cta`, optional `daily_budget` (default 200)
  - **Response (success):** `{ "ok": true, "campaign_id", "adset_id", "ad_id", "status", "preview_url", "image_hash", "warnings" }`
  - **Env:** `META_ACCESS_TOKEN`, `META_AD_ACCOUNT_ID`, `META_APP_ID`, `META_PAGE_ID`, `META_PIXEL_ID`
  - **Status:** broken externally in current environment (Meta API `code=200` access blocked observed)

- `POST /api/meta-advantage/publish-test`
  - **Inputs:** same core fields as image publish
  - **Response:** dry-run validation payload (`ok`, budget conversion, targeting, image metadata, warnings)
  - **Env:** same Meta vars as publish endpoint
  - **Status:** working code path; depends on Meta token/account access for full validation

## Meta Advantage+ (Video)

- `GET /api/drive/videos`
  - **Inputs:** none (fixed Drive folder id)
  - **Response:** `{ "ok": true, "folder_id", "count", "videos": [{ "id", "name", "url", "thumbnail", ...}] }`
  - **Env:** `GOOGLE_DRIVE_API_KEY`
  - **Status:** working

- `POST /api/meta-advantage/generate-video-copy`
  - **Inputs:** one of `video_description`, `video_filename`, `video_name`
  - **Response:** `{ "ok": true, "variants": [...] }`
  - **Env:** `ANTHROPIC_API_KEY`
  - **Status:** working

- `POST /api/meta-advantage/publish-video`
  - **Inputs:** `variant_id`, `video_url`, `headline`, `primary_text`, `cta`, optional `daily_budget` (default 200)
  - **Response (success):** `{ "ok": true, "campaign_id", "adset_id", "ad_id", "video_id", "status", "warnings" }`
  - **Env:** `META_ACCESS_TOKEN`, `META_AD_ACCOUNT_ID`, `META_APP_ID`, `META_PAGE_ID`, `META_PIXEL_ID`
  - **Status:** broken externally in current environment (Meta API `code=200` access blocked observed)

---

## n8n Workflow Triggers + Call Order

## 1) SEO Automation (Mon/Thu 8am IST)

- Trigger: `Cron` (Mon, Thu, 08:00 IST)
- Call: `POST /generate-article` with optional `{ "dry_run": false }`
- Save `job_id`
- Loop/poll: `GET /seo-job/<job_id>` every 20-30s
- Branch:
  - `status=complete` -> log title/url and notify
  - `status=error` -> alert + stop

## 2) Instagram Automation

- Trigger: schedule or manual webhook
- (Optional) upload source media: `POST /api/upload-image`
- Generate copy+visual output: `POST /api/generate`
- (Optional) rewrite draft captions: `POST /api/rephrase`
- (Optional) animate: `POST /api/kling/submit` -> poll `POST /api/kling/status`
- Publish to IG via your separate channel integration

## 3) Meta Image Ad Automation

- Trigger: schedule/manual/new asset event
- Generate variants: `POST /api/meta-advantage/generate`
- Pick winning variant in n8n logic
- (Recommended precheck) `POST /api/meta-advantage/publish-test`
- Publish: `POST /api/meta-advantage/publish`
- Store IDs (`campaign_id`, `adset_id`, `ad_id`) for tracking

## 4) Meta Video Ad Automation

- Trigger: schedule/manual/new video event
- List videos: `GET /api/drive/videos`
- Generate copy: `POST /api/meta-advantage/generate-video-copy`
- Pick variant + video
- Publish: `POST /api/meta-advantage/publish-video`
- Store IDs (`campaign_id`, `adset_id`, `ad_id`, `video_id`)

---

## Current Endpoint Status Summary

- **Working:** health, seo job orchestration, Instagram generate/rephrase/upload, Kling submit/status, library/logo CRUD, meta copy generation, drive video listing.
- **Externally blocked right now:** meta publish endpoints (`/api/meta-advantage/publish`, `/api/meta-advantage/publish-video`) due current Meta API access restrictions in deployed credentials.
- **Pending verification after credential update:** meta publish-test + live publish flows end-to-end.

---

## Known Issues + Workarounds

- **Meta Graph API `code=200` API access blocked**
  - **Symptom:** publish endpoints fail before ad object creation.
  - **Workaround:** fix Meta app/token/ad-account permissions first (app live mode, ads permissions, ad account access, system user mapping).

- **Google Drive large video file confirmation pages**
  - **Symptom:** HTML response instead of raw video bytes.
  - **Workaround implemented:** downloader now parses `confirm`/`uuid` tokens and retries with confirmed URL.

- **Large video uploads can fail/be slow**
  - **Workaround implemented:** auto-compress >30MB to H.264 720p via ffmpeg before Meta upload.

- **Ad set targeting automation inconsistency**
  - Current code sends `targeting.targeting_automation.advantage_audience = 1` but adset-level `targeting_automation` payload still serializes `advantage_audience = 0` in publish routes.
  - If Meta validation becomes strict again, align both to the same value.

- **In-memory SEO job tracking**
  - `_seo_results` is process-memory only; restarts lose job state.
  - Workaround: in n8n, keep your own execution log and retry strategy.

