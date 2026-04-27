"""
WEARTH INFINITE SEO ENGINE
Automatically researches, generates and publishes SEO articles forever.
No fixed article list. Claude picks the best keyword opportunity each time.
Runs via n8n every Monday & Thursday 8am IST.
"""

import os
import json
import requests
from datetime import datetime

# ─── CONFIG ───────────────────────────────────────────────────────────────────

SHOPIFY_STORE = "wearthactive.myshopify.com"
SHOPIFY_TOKEN = os.environ.get("SHOPIFY_TOKEN", "")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
UNSPLASH_KEY = os.environ.get("UNSPLASH_ACCESS_KEY", "")

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
- Made from eucalyptus tree fibre — plant-based, closed-loop manufacturing
- Breathable, temperature-regulating, moisture-wicking naturally
- No microplastics shed in wash
- No chemical treatments on skin during exercise
- NEVER say: TENCEL, lyocell. ALWAYS say: eucalyptus fibre, plant-based fabric, from trees.

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
5. Ingredient/Material deep dive — what eucalyptus fabric actually is
6. Seasonal/Timely — monsoon workouts, summer heat, festival fitness
7. Male audience — strong, silent, substance over performance
"""

# ─── KEYWORD SEED CLUSTERS ────────────────────────────────────────────────────
# Used as inspiration only — Claude will expand and find fresh angles

KEYWORD_SEEDS = [
    "activewear india", "sustainable activewear", "eucalyptus fabric",
    "polyester alternatives", "plant based clothing india", "gym wear india",
    "yoga clothes india", "breathable activewear", "natural fabric workout",
    "microplastics clothing", "non toxic activewear", "women activewear india",
    "men activewear india", "morning workout india", "fitness lifestyle india",
    "slow fashion india", "conscious clothing india", "fabric skin health",
    "eucalyptus vs cotton", "workout clothes for indian climate"
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

def publish_article(blog_id: str, article: dict) -> dict:
    """Publish article to Shopify blog."""
    payload = {
        "article": {
            "title": article["title"],
            "body_html": article["body_html"],
            "summary_html": f"<p>{article['meta_description']}</p>",
            "tags": ", ".join(article.get("tags", [])),
            "published": True,
            "image": {"src": article.get("image_url", "")},
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
]

def fetch_unsplash_image(keyword: str) -> str:
    """Fetch a relevant image from Unsplash with variety."""
    import random as _random
    import time as _time
    try:
        # Try multiple search terms for variety
        search_options = [
            keyword.replace(" ", "+"),
            "eucalyptus+activewear+india",
            "fitness+india+workout",
            "yoga+india+natural",
            "running+india+outdoor",
            "gym+india+woman",
        ]
        search_terms = _random.choice(search_options)
        page = _random.randint(1, 8)
        r = requests.get(
            f"https://api.unsplash.com/search/photos?query={search_terms}&orientation=landscape&page={page}&per_page=15",
            headers={"Authorization": f"Client-ID {UNSPLASH_KEY}"},
            timeout=10
        )
        if r.status_code == 200:
            results = r.json().get("results", [])
            if results:
                photo = _random.choice(results)
                print(f"Unsplash image: {photo['urls']['regular'][:60]}...")
                return photo["urls"]["regular"]
    except Exception as e:
        print(f"Unsplash fetch failed: {e}")
    # Use varied fallback pool - pick based on time to avoid repeats
    idx = int(_time.time()) % len(FALLBACK_IMAGES)
    return FALLBACK_IMAGES[idx]

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

    prompt = f"""You are an SEO strategist for WEARTH Active, an Indian eucalyptus activewear brand.

{BRAND_CONTEXT}

ALREADY PUBLISHED ARTICLES (do NOT repeat these topics):
{json.dumps(existing_titles, indent=2)}

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

    prompt = f"""You are writing a blog article for WEARTH Active (wearthactive.com).

{BRAND_CONTEXT}

ARTICLE BRIEF:
Title: {brief['title']}
Primary Keyword: {brief['primary_keyword']}
Secondary Keywords: {', '.join(brief['secondary_keywords'])}
Content Angle: {brief['angle']}
Target Word Count: {brief.get('word_count', 900)}

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
  "word_count": approximate_number
}}

No markdown fences. Start with {{ and end with }}."""

    raw = call_claude(prompt, max_tokens=4000)
    cleaned = raw.replace("```json", "").replace("```", "").strip()
    return json.loads(cleaned)

# ─── MAIN RUNNER ──────────────────────────────────────────────────────────────


def run_seo_engine(dry_run: bool = False, article_index: int = None) -> dict:
    """
    Main entry point. Called by Flask API.
    1. Fetch existing articles from Shopify
    2. Ask Claude to research best keyword opportunity
    3. Generate full article
    4. Fetch image from Unsplash
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

    # Step 4: Fetch image
    print("Fetching image from Unsplash...")
    # Build gender-aware image search query
    angle = brief.get("content_angle_type", "")
    keyword = brief["primary_keyword"]
    if "male" in angle or "men" in keyword.lower() or "man" in keyword.lower():
        image_query = keyword + " men fitness india"
    elif "female" in angle or "women" in keyword.lower() or "woman" in keyword.lower():
        image_query = keyword + " women fitness india"
    else:
        image_query = keyword + " fitness india"
    article["image_url"] = fetch_unsplash_image(image_query)
    print(f"Image: {article['image_url']}\n")

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


if __name__ == "__main__":
    import sys
    dry = "--dry" in sys.argv
    run_seo_engine(dry_run=dry)
