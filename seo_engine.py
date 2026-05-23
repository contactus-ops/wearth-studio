"""
WEARTH INFINITE SEO ENGINE
Automatically researches, generates and publishes SEO articles forever.
No fixed article list. Claude picks the best keyword opportunity each time.
Runs via n8n every Monday & Thursday 8am IST.
"""

import os
import sys
import json
import re
import random
import requests
import threading
import time
from datetime import datetime
from flask import jsonify, request
from urllib.parse import quote_plus

from blog_image_engine import (
    optimize_image_from_url,
    shopify_image_attachment_payload,
)

# ─── CONFIG ───────────────────────────────────────────────────────────────────

SHOPIFY_STORE = "wearthactive.myshopify.com"
SHOPIFY_TOKEN = os.environ.get("SHOPIFY_TOKEN", "")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
UNSPLASH_KEY = os.environ.get("UNSPLASH_ACCESS_KEY", "")
GOOGLE_DRIVE_API_KEY = (os.environ.get("GOOGLE_DRIVE_API_KEY") or "").strip()
SEO_IMAGES_FOLDER = (
    (os.environ.get("SEO_IMAGES_FOLDER") or os.environ.get("DRIVE_IMAGES_FOLDER") or "").strip()
)
INSTAGRAM_IMAGES_FOLDER = (os.environ.get("INSTAGRAM_IMAGES_FOLDER") or "").strip()
_seo_results = {}

SHOPIFY_BASE = f"https://{SHOPIFY_STORE}/admin/api/2024-01"
HEADERS_SHOPIFY = {
    "X-Shopify-Access-Token": SHOPIFY_TOKEN,
    "Content-Type": "application/json"
}
HEADERS_CLAUDE = {
    "x-api-key": ANTHROPIC_KEY,
    "anthropic-version": "2023-06-01",
    "content-type": "application/json"
}

# ─── BRAND CONTEXT ────────────────────────────────────────────────────────────

BRAND_CONTEXT = """
BRAND: WEARTH Active (wearthactive.com)
FOUNDER: Shai (Shailaja Gupta), India
TAGLINE: Activewear Without Polyester. Finally.

FABRIC TRUTH:
- Made from plant-based fabric — closed-loop manufacturing, grown not made
- FABRIC LANGUAGE (rotate these, never repeat in same article):
  * "plant-based fabric that breathes"
  * "fabric grown from trees, not made in a lab"
  * "botanical fibre with natural temperature regulation"
  * "fabric that comes from the ground, not petroleum"
  * "natural fibre that moves moisture without chemicals"
  * "tree-derived fabric, closed-loop process"
  * "fabric grown, not manufactured"
  * "plant fibre, not plastic"
- Rotate between: eucalyptus, plant-based fabric, fabric from trees, botanical fibre, tree-derived fabric. Never use TENCEL or lyocell.
- Breathable, temperature-regulating, moisture-wicking naturally
- No microplastics shed in wash
- No chemical treatments on skin during exercise

BRAND POSITIONING:
- Anti-polyester. Anti-synthetic. Pro-plant.
- Quiet luxury. Not LV or Lululemon. More Patagonia — values-driven, substance over logo.
- The WEARTH person reads ingredient labels. Drinks almond milk coffee at home.
  Buys expensive Vit C serum. Chooses quality over quantity, silently.
  Their richness shows in their choices, not their logos.
- Premium product that deserves premium pricing. Content must build that perception.

TARGET READER:
Indian woman AND man, 25-40, metros (Mumbai, Bangalore, Delhi, Pune, Hyderabad).
Reads ingredient labels. Switched to natural products quietly, no announcement.
Moves because it feels good, not for content. Done with synthetic, fast, fake.
When they find WEARTH: "oh. this is it."

PRODUCTS: Flow Tank, Power Crop, Align Bra, Terra Bra, Everyday Joggers,
Maria Skort, Biker Shorts, Leggings, Men's Motion Tee, Edge Tank, Essential Shorts.
Price: ~₹2,000. Sold exclusively at wearthactive.com

VOICE: Calm. Certain. Trusted friend who has done the research.
Short sentences. Uneven rhythm. No exclamation marks. No hype words.
No: sacred, ritual, intentional, conscious, shift, journey, game-changer, amazing.
Declarative. Real. Like texting someone who gets it.

CONTENT ANGLES TO ROTATE (alternate between these for variety):
1. Problem/Education — why polyester/synthetic is harmful, science-backed
2. Aspiration/Lifestyle — who the WEARTH person is, how they live and move
3. Comparison — WEARTH vs alternatives, honest and factual  
4. India-specific — climate, culture, metro life, Indian body types
5. Ingredient/Material deep dive — what plant-based fabric actually is and how it differs from synthetic
6. Seasonal/Timely — monsoon workouts, summer heat, festival fitness
7. Male audience — strong, silent, substance over performance
"""

# ─── KEYWORD SEED CLUSTERS ────────────────────────────────────────────────────
# Used as inspiration only — Claude will expand and find fresh angles

KEYWORD_SEEDS = [
    "activewear india", "sustainable activewear", "plant based fabric activewear",
    "polyester alternatives", "natural fabric activewear india", "gym wear india",
    "yoga clothes india", "breathable activewear", "natural fabric workout",
    "microplastics clothing", "non toxic activewear", "women activewear india",
    "men activewear india", "morning workout india", "fitness lifestyle india",
    "slow fashion india", "conscious clothing india", "fabric skin health",
    "natural vs synthetic fabric", "workout clothes for indian climate"
]

# ─── SHOPIFY HELPERS ──────────────────────────────────────────────────────────

def get_or_create_blog(blog_title: str = "News") -> str:
    """Get existing blog ID or create one."""
    r = requests.get(f"{SHOPIFY_BASE}/blogs.json", headers=HEADERS_SHOPIFY)
    blogs = r.json().get("blogs", [])
    for blog in blogs:
        if blog["title"] == blog_title:
            return blog["id"]
    r = requests.post(
        f"{SHOPIFY_BASE}/blogs.json",
        headers=HEADERS_SHOPIFY,
        json={"blog": {"title": blog_title}}
    )
    return r.json()["blog"]["id"]

NEWS_BLOG_ID = "84314751156"  # Hardcoded — never changes

def get_existing_articles() -> list:
    """Fetch all published article titles and handles from News blog."""
    try:
        r = requests.get(
            f"{SHOPIFY_BASE}/blogs/{NEWS_BLOG_ID}/articles.json?limit=250&fields=handle,title",
            headers=HEADERS_SHOPIFY
        )
        return r.json().get("articles", [])
    except:
        return []

def prepare_article_hero_image(article: dict) -> dict:
    """Download hero, compress to quality-first JPEG ≤500KB (blog_image_engine)."""
    url = (article.get("image_url") or "").strip()
    if not url:
        return article
    print("Optimizing hero image for blog (<500KB JPEG)...")
    try:
        jpeg_bytes, meta = optimize_image_from_url(url)
        article["image_jpeg_bytes"] = jpeg_bytes
        article["image_optimize_meta"] = meta
        print(
            f"Hero ready: {meta.get('kb')}KB @ Q{meta.get('quality')} "
            f"({meta.get('width_after')}x{meta.get('height_after')})"
        )
    except Exception as exc:
        print(f"Hero optimize fallback (original URL): {exc}")
    return article


def update_article_hero_image(
    blog_id: str, article_id: int, jpeg_bytes: bytes, *, alt: str
) -> dict:
    """PUT article image via base64 attachment (read-only on theme)."""
    payload = {
        "article": {
            "id": article_id,
            "image": shopify_image_attachment_payload(jpeg_bytes, alt),
        }
    }
    r = requests.put(
        f"{SHOPIFY_BASE}/blogs/{blog_id}/articles/{article_id}.json",
        headers=HEADERS_SHOPIFY,
        json=payload,
        timeout=120,
    )
    if r.status_code not in (200, 201):
        raise Exception(f"Shopify article image update: {r.status_code} {r.text[:500]}")
    return r.json().get("article") or {}


def publish_article(blog_id: str, article: dict) -> dict:
    """Publish article to Shopify blog."""
    article_title = article["title"]
    image_alt = f"{article_title} — plant-based activewear by WEARTH Active India"
    if article.get("image_jpeg_bytes"):
        image_field = shopify_image_attachment_payload(article["image_jpeg_bytes"], image_alt)
    elif article.get("image_url"):
        image_field = {"src": article["image_url"], "alt": image_alt}
    else:
        image_field = {"alt": image_alt}
    payload = {
        "article": {
            "title": article_title,
            "body_html": article["body_html"],
            "summary_html": f"<p>{article['meta_description']}</p>",
            "tags": ", ".join(article.get("tags", [])),
            "published": True,
            "image": image_field,
            "metafields": [
                {
                    "key": "description_tag",
                    "value": article["meta_description"],
                    "type": "single_line_text_field",
                    "namespace": "global"
                }
            ]
        }
    }
    r = requests.post(
        f"{SHOPIFY_BASE}/blogs/{blog_id}/articles.json",
        headers=HEADERS_SHOPIFY,
        json=payload
    )
    if r.status_code not in [200, 201]:
        raise Exception(f"Shopify publish error: {r.status_code} {r.text}")
    return r.json()["article"]

# ─── IMAGE FETCHER ────────────────────────────────────────────────────────────

# Fallback images pool — varied so no repeats
FALLBACK_IMAGES = [
    "https://images.unsplash.com/photo-1571019613454-1cb2f99b2d8b?w=1200",
    "https://images.unsplash.com/photo-1518611012118-696072aa579a?w=1200",
    "https://images.unsplash.com/photo-1506629082955-511b1aa562c8?w=1200",
    "https://images.unsplash.com/photo-1540497077202-7c8a3999166f?w=1200",
    "https://images.unsplash.com/photo-1594737625785-a6cbdabd333c?w=1200",
    "https://images.unsplash.com/photo-1536922246289-88c42f957773?w=1200",
    "https://images.unsplash.com/photo-1574680096145-d05b474e2155?w=1200",
    "https://images.unsplash.com/photo-1554284126-aa88f22d8b74?w=1200",
    "https://images.unsplash.com/photo-1534438327276-14e5300c3a48?w=1200",
    "https://images.unsplash.com/photo-1541534741688-6078c6bfb5c5?w=1200",
    "https://images.unsplash.com/photo-1526506118085-60ce8714f8c5?w=1200",
    "https://images.unsplash.com/photo-1507398941214-572c25f4b1dc?w=1200",
    "https://images.unsplash.com/photo-1549060279-7e168fcee0c2?w=1200",
    "https://images.unsplash.com/photo-1583454110551-21f2fa2afe61?w=1200",
    "https://images.unsplash.com/photo-1544367567-0f2fcb009e0b?w=1200",
    "https://images.unsplash.com/photo-1552196563-55cd4e45efb3?w=1200",
]

def _used_media_tracker():
    _root = os.path.dirname(os.path.abspath(__file__))
    _scripts = os.path.join(_root, "scripts")
    if _scripts not in sys.path:
        sys.path.insert(0, _scripts)
    import importlib

    return importlib.import_module("used_media_tracker")


def _list_seo_drive_folder_images(folder_id: str) -> list:
    """Same Drive v3 list logic as app /api/drive/images (folder images via API key)."""
    if not GOOGLE_DRIVE_API_KEY or not folder_id:
        return []
    try:
        params = {
            "key": GOOGLE_DRIVE_API_KEY,
            "q": f"'{folder_id}' in parents and trashed=false and mimeType contains 'image/'",
            "fields": "files(id,name,mimeType)",
            "pageSize": 100,
        }
        resp = requests.get(
            "https://www.googleapis.com/drive/v3/files", params=params, timeout=20
        )
        if resp.status_code != 200:
            return []
        files = resp.json().get("files", [])
        return [
            {"id": f.get("id", ""), "name": f.get("name", "")}
            for f in files
            if f.get("id")
        ]
    except Exception:
        return []


def _unsplash_track_id_from_src(src: str) -> str:
    """Stable id for dedup: path segment after photo- (matches Shopify-stored Unsplash URLs)."""
    m = re.search(r"photo-([^/?#]+)", src or "", re.I)
    return m.group(1).strip() if m else ""


def _unsplash_track_id_from_photo(photo: dict) -> str:
    urls = photo.get("urls") or {}
    reg = str(urls.get("regular") or urls.get("small") or urls.get("full") or "")
    tid = _unsplash_track_id_from_src(reg)
    if tid:
        return tid
    return str(photo.get("id") or "").strip()


def _unsplash_search_results(unsplash_query: str) -> list:
    """Return Unsplash search `results` list (up to 30) or []."""
    q = (unsplash_query or "").strip() or "calm natural morning light movement"
    if not (UNSPLASH_KEY or "").strip():
        return []
    try:
        page = random.randint(1, 8)
        query_enc = quote_plus(q)
        r = requests.get(
            f"https://api.unsplash.com/search/photos?query={query_enc}"
            f"&orientation=landscape&content_filter=high&page={page}&per_page=30",
            headers={"Authorization": f"Client-ID {UNSPLASH_KEY}"},
            timeout=15,
        )
        if r.status_code == 200:
            return r.json().get("results") or []
    except Exception as e:
        print(f"Unsplash fetch failed: {e}")
    return []


def fetch_seo_image(unsplash_query: str, article_title: str) -> str:
    """
    Drive-first hero image: combined pool from SEO_IMAGES_FOLDER + INSTAGRAM_IMAGES_FOLDER
    (deduped by file id), minus get_used_ids("seo_images"). If empty after filter, reset
    seo_images and pick from full combined pool. Else Unsplash (per_page=30). Marks winner.
    """
    umt = _used_media_tracker()
    title_hint = (article_title or "").strip() or "article"
    print(f"SEO hero image for: {title_hint[:70]}...")

    if GOOGLE_DRIVE_API_KEY and (SEO_IMAGES_FOLDER or INSTAGRAM_IMAGES_FOLDER):
        rows_seo: list = []
        rows_ig: list = []
        try:
            rows_seo = _list_seo_drive_folder_images(SEO_IMAGES_FOLDER) if SEO_IMAGES_FOLDER else []
            rows_ig = (
                _list_seo_drive_folder_images(INSTAGRAM_IMAGES_FOLDER)
                if INSTAGRAM_IMAGES_FOLDER
                else []
            )
            seen: set[str] = set()
            rows: list = []
            for row in rows_seo + rows_ig:
                rid = str(row.get("id") or "").strip()
                if not rid or rid in seen:
                    continue
                seen.add(rid)
                rows.append(row)
            used_ids = umt.get_used_ids("seo_images")
        except Exception:
            rows = []
            used_ids = []
            rows_seo, rows_ig = [], []
        used_set = set(used_ids or [])
        unused_drive = [
            str(row["id"]).strip()
            for row in rows
            if str(row.get("id") or "").strip() not in used_set
        ]
        print(
            json.dumps(
                {
                    "seo_folder_count": len(rows_seo),
                    "instagram_folder_count": len(rows_ig),
                    "combined_after_dedup": len(rows),
                }
            )
        )
        if not unused_drive and rows:
            try:
                umt.reset_category("seo_images")
            except Exception:
                pass
            unused_drive = [str(r["id"]).strip() for r in rows if str(r.get("id") or "").strip()]
        if unused_drive:
            fid = random.choice(unused_drive)
            drive_url = f"https://drive.google.com/uc?export=download&id={fid}"
            try:
                umt.mark_used("seo_images", fid)
            except Exception:
                pass
            print(f"SEO hero: Drive image {fid[:24]}...")
            return drive_url

    results = _unsplash_search_results(unsplash_query)
    if not results:
        url = random.choice(FALLBACK_IMAGES)
        tid = _unsplash_track_id_from_src(url)
        if tid:
            try:
                umt.mark_used("seo_images", tid)
            except Exception:
                pass
        print(f"SEO hero: static fallback {url[:60]}...")
        return url

    try:
        used_ids = umt.get_used_ids("seo_images")
    except Exception:
        used_ids = []
    used_set = set(used_ids or [])

    for photo in results:
        tid = _unsplash_track_id_from_photo(photo)
        if not tid or tid in used_set:
            continue
        url = (photo.get("urls") or {}).get("regular") or ""
        if not url:
            continue
        try:
            umt.mark_used("seo_images", tid)
        except Exception:
            pass
        print(f"SEO hero: Unsplash {url[:60]}...")
        return url

    photo0 = results[0]
    try:
        umt.reset_category("seo_images")
    except Exception:
        pass
    tid0 = _unsplash_track_id_from_photo(photo0)
    url0 = (photo0.get("urls") or {}).get("regular") or random.choice(FALLBACK_IMAGES)
    if tid0:
        try:
            umt.mark_used("seo_images", tid0)
        except Exception:
            pass
    print(f"SEO hero: Unsplash after tracker reset {url0[:60]}...")
    return url0

# ─── CLAUDE CALLER ────────────────────────────────────────────────────────────

def call_claude(prompt: str, max_tokens: int = 4000) -> str:
    """Call Claude API and return text response."""
    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers=HEADERS_CLAUDE,
        json={
            "model": "claude-sonnet-4-20250514",
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}]
        }
    )
    if response.status_code != 200:
        raise Exception(f"Claude API error: {response.status_code} {response.text}")
    return response.json()["content"][0]["text"]

# ─── STEP 1: KEYWORD RESEARCHER ───────────────────────────────────────────────

def research_best_keyword(existing_articles: list) -> dict:
    """
    Ask Claude to pick the best keyword opportunity not yet covered.
    Returns a complete article brief.
    """
    existing_titles = [a["title"] for a in existing_articles]
    existing_handles = [a["handle"] for a in existing_articles]

    titles_list = json.dumps(existing_titles, indent=2)
    prompt = f"""You are an SEO strategist for WEARTH Active, an Indian plant-based activewear brand.

{BRAND_CONTEXT}

ALREADY PUBLISHED ARTICLES (do NOT repeat these topics):
{titles_list}

KEYWORD SEED IDEAS (expand beyond these):
{json.dumps(KEYWORD_SEEDS, indent=2)}

YOUR TASK:
Research and identify the BEST keyword opportunity for WEARTH's next blog article.

Consider:
1. Search volume potential in India (monthly searches)
2. Commercial intent — will this reader buy activewear?
3. Competition level — can a new brand rank for this?
4. Brand fit — does this topic serve the WEARTH tribe?
5. Content variety — pick a different angle from what's already published
6. Seasonal relevance — is there a timely angle right now?

Think about long-tail keywords, question-based searches, comparison searches,
India-specific fitness/lifestyle trends, ingredient curiosity searches.

The following article titles already exist — do not pick any topic that is the same as or closely similar to any of these: {titles_list}. Pick a topic that is clearly distinct.

Return ONLY a JSON object with this exact structure:
{{
  "primary_keyword": "the main keyword to target",
  "secondary_keywords": ["keyword2", "keyword3", "keyword4"],
  "title": "The article title (SEO optimized, compelling, under 70 chars)",
  "slug": "url-friendly-slug-with-hyphens",
  "angle": "2-3 sentences describing the content angle, tone, and what makes it unique",
  "word_count": 900,
  "content_angle_type": "one of: problem/education, aspiration/lifestyle, comparison, india-specific, material-deepdive, seasonal, male-audience",
  "why_this_keyword": "one sentence explaining why this is the best opportunity right now"
}}

No markdown. No explanation. Start with {{ and end with }}."""

    raw = call_claude(prompt, max_tokens=1000)
    cleaned = raw.replace("```json", "").replace("```", "").strip()
    return json.loads(cleaned)

# ─── STEP 2: ARTICLE GENERATOR ────────────────────────────────────────────────

def generate_article(brief: dict) -> dict:
    """Generate full SEO article based on brief."""

    article_topic = brief["title"]
    unsplash_guidance = (
        'The WEARTH tribe is not a gym person. They are quietly disciplined, ingredient-aware, '
        "self-motivated. They move for themselves not for an audience. The image should feel calm, "
        "natural, unhurried, confident. Think: woman in natural light near a window, person stretching "
        "outdoors in minimal clothing, soft morning movement, earthy tones, solo figure, peaceful focus, "
        "South Asian appearance preferred, natural textures, NOT a gym, NOT weights, NOT group fitness, "
        "NOT neon, NOT performance sport. Return a 4-6 word Unsplash search query that would find this "
        f"kind of image for an article about: {article_topic}."
    )

    prompt = f"""You are writing a blog article for WEARTH Active (wearthactive.com).

{BRAND_CONTEXT}

ARTICLE BRIEF:
Title: {brief['title']}
Primary Keyword: {brief['primary_keyword']}
Secondary Keywords: {', '.join(brief['secondary_keywords'])}
Content Angle: {brief['angle']}
Target Word Count: {brief.get('word_count', 900)}

IMAGE SEARCH (required second output field):
{unsplash_guidance}

WRITING RULES:
- Use the primary keyword naturally in: title, first paragraph, 2-3 subheadings, conclusion
- Use secondary keywords naturally throughout — never forced
- Structure: intro hook → 3-5 H2 sections with H3 subsections → conclusion with CTA
- CTA at end: link to https://wearthactive.com with anchor text relevant to article
- Write for the WEARTH tribe — intelligent, ingredient-aware, done with synthetic
- Calm authority. Not a lecture. Like a trusted friend sharing research.
- No exclamation marks. No: amazing, incredible, game-changer, sacred, ritual, journey
- Short paragraphs. Real sentences. Uneven rhythm.
- Include specific facts, comparisons, and practical insights
- India-specific references where relevant (climate, cities, culture)

Return ONLY a JSON object:
{{
  "title": "exact article title",
  "meta_description": "compelling meta description under 160 chars with primary keyword",
  "body_html": "complete article HTML with proper h2, h3, p tags",
  "tags": ["tag1", "tag2", "tag3", "tag4", "tag5"],
  "word_count": approximate_number,
  "unsplash_query": "4-6 words only, per the image search guidance above"
}}

No markdown fences. Start with {{ and end with }}."""

    raw = call_claude(prompt, max_tokens=4000)
    cleaned = raw.replace("```json", "").replace("```", "").strip()
    data = json.loads(cleaned)
    uq = (data.get("unsplash_query") or "").strip()
    title_for_fallback = (data.get("title") or article_topic or "").strip()
    if not uq:
        data["unsplash_query"] = " ".join(title_for_fallback.split()[:6])
    else:
        data["unsplash_query"] = uq
    return data

# ─── MAIN RUNNER ──────────────────────────────────────────────────────────────


def run_seo_engine(dry_run: bool = False, article_index: int = None) -> dict:
    """
    Main entry point. Called by Flask API.
    1. Fetch existing articles from Shopify
    2. Ask Claude to research best keyword opportunity
    3. Generate full article
    4. Fetch hero image (Drive-first, then Unsplash)
    5. Publish to Shopify
    """
    print(f"\n{'='*60}")
    print(f"WEARTH INFINITE SEO ENGINE — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE PUBLISH'}")
    print(f"{'='*60}\n")

    # Step 1: Get existing articles from Shopify
    print("Fetching existing articles from Shopify...")
    existing_articles = get_existing_articles()
    print(f"Found {len(existing_articles)} existing articles\n")

    # Step 2: Research best keyword
    print("Researching best keyword opportunity...")
    brief = research_best_keyword(existing_articles)
    print(f"Selected keyword: {brief['primary_keyword']}")
    print(f"Title: {brief['title']}")
    print(f"Angle: {brief['content_angle_type']}")
    print(f"Why: {brief['why_this_keyword']}\n")

    # Step 3: Generate article
    print("Generating article...")
    article = generate_article(brief)
    print(f"Generated: {article['title']}")
    print(f"Meta: {article['meta_description']}")
    print(f"Words: ~{article.get('word_count', 'unknown')}\n")

    # Step 4: Hero image (Drive pool first, then Unsplash with 30-result dedup)
    print("Fetching hero image (Drive / Unsplash)...")
    article["image_url"] = fetch_seo_image(
        article.get("unsplash_query") or article["title"],
        article.get("title") or "",
    )
    print(f"Image: {article['image_url']}\n")
    article = prepare_article_hero_image(article)

    if dry_run:
        print("--- BODY HTML PREVIEW (first 500 chars) ---")
        print(article["body_html"][:500])
        print("\n[DRY RUN — not published]")
        preview_path = f"/tmp/preview_{brief['slug']}.html"
        with open(preview_path, "w") as f:
            f.write(f"<h1>{article['title']}</h1>\n")
            f.write(f"<p><em>Keyword: {brief['primary_keyword']}</em></p>\n")
            f.write(f"<p><em>Meta: {article['meta_description']}</em></p>\n")
            f.write(article["body_html"])
        print(f"Preview saved: {preview_path}")
        return article

    # Step 5: Publish
    print("Publishing to Shopify...")
    blog_id = NEWS_BLOG_ID
    published_article = publish_article(blog_id, article)
    url = f"https://wearthactive.com/blogs/news/{published_article.get('handle', brief['slug'])}"
    print(f"\n✅ Published: {url}")
    print(f"Total articles live: {len(existing_articles) + 1}")
    print(f"Running forever. Next post: Monday or Thursday 8am IST.\n")

    return published_article


def generate_article_endpoint():
    """
    Legacy async endpoint used by the n8n SEO workflow.
    POST /generate-article returns a job id; n8n polls /seo-job/<job_id>.
    """
    data = request.get_json(force=True, silent=True) or {}
    dry_run_raw = data.get("dry_run", False)
    dry_run = str(dry_run_raw).lower() == "true" if isinstance(dry_run_raw, str) else bool(dry_run_raw)

    if not ANTHROPIC_KEY:
        return jsonify({"status": "error", "error": "ANTHROPIC_API_KEY not set"}), 500
    if not SHOPIFY_TOKEN:
        return jsonify({"status": "error", "error": "SHOPIFY_TOKEN not set"}), 500

    job_id = str(int(time.time()))
    _seo_results[job_id] = {
        "status": "running",
        "started_at": datetime.utcnow().isoformat() + "Z",
        "dry_run": dry_run,
    }

    def run():
        try:
            article = run_seo_engine(dry_run=dry_run, article_index=data.get("index"))
            handle = article.get("handle", "") if isinstance(article, dict) else ""
            opt = article.get("image_optimize_meta") if isinstance(article, dict) else {}
            _seo_results[job_id] = {
                "status": "complete",
                "completed_at": datetime.utcnow().isoformat() + "Z",
                "article": article if isinstance(article, dict) else {},
                "title": article.get("title", "") if isinstance(article, dict) else "",
                "handle": handle,
                "url": f"https://wearthactive.com/blogs/news/{handle}" if handle else "",
                "image": ((article.get("image") or {}).get("src") if isinstance(article, dict) else "") or "",
                "hero_image_kb": opt.get("kb") if isinstance(opt, dict) else None,
                "summary": article.get("summary_html", "") if isinstance(article, dict) else "",
            }
        except Exception as exc:
            _seo_results[job_id] = {
                "status": "error",
                "completed_at": datetime.utcnow().isoformat() + "Z",
                "error": str(exc),
            }

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return jsonify({"status": "started", "job_id": job_id, "message": f"Check /seo-job/{job_id} for result"})


def seo_job_status(job_id):
    return jsonify(_seo_results.get(str(job_id), {"status": "not_found"}))


def seo_status():
    try:
        published = get_existing_articles()
    except Exception as exc:
        return jsonify({"status": "error", "error": str(exc)}), 500
    return jsonify(
        {
            "status": "ok",
            "published": len(published),
            "engine": "infinite",
            "running_jobs": sum(1 for row in _seo_results.values() if row.get("status") == "running"),
            "next_up": "Claude researches and picks automatically",
        }
    )


if __name__ == "__main__":
    import sys
    dry = "--dry" in sys.argv
    run_seo_engine(dry_run=dry)