"""
WEARTH SEO ENGINE
Generates SEO blog articles and publishes to Shopify blog automatically.
Run manually or via cron/n8n on a schedule.
"""

import os
import json
import requests
from datetime import datetime

# ─── CONFIG ───────────────────────────────────────────────────────────────────

SHOPIFY_STORE = "wearthactive.myshopify.com"
SHOPIFY_TOKEN = os.environ.get("SHOPIFY_TOKEN", "")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")  # set in env or Railway

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

# ─── BRAND CONTEXT (baked in — never changes) ─────────────────────────────────

BRAND_CONTEXT = """
BRAND: WEARTH Active (wearthactive.com)
FOUNDER: Shai (Shailaja Gupta), Mumbai, India
TAGLINE: Activewear Without Polyester. Finally.

FABRIC TRUTH:
- Made from eucalyptus tree fibre — plant-based, closed-loop manufacturing
- Breathable, temperature-regulating, moisture-wicking
- No microplastics shed in wash
- No chemical treatments on skin during exercise
- NEVER say: TENCEL, lyocell (use: eucalyptus fibre, plant-based fabric, from trees)

ANTI-POLYESTER POSITION:
Polyester = petroleum turned into fabric. Traps heat. Holds bacteria and odour.
Sheds microplastics every wash. Chemical treatments sit on skin when pores open during exercise.
WEARTH never uses it.

TARGET READER (THE TRIBE):
Indian woman, 25-40, metros (Mumbai, Bangalore, Delhi, Pune, Hyderabad).
Reads ingredient labels. Switched to natural products quietly. Moves because it feels good.
Done with synthetic, fast, things that look good but feel wrong.

VOICE: Calm. Certain. Like a trusted friend who has done the research.
No exclamation marks. No hype words. Declarative. Real.

PRODUCTS: Flow Tank, Power Crop, Align Bra, Terra Bra, Everyday Joggers,
Maria Skort, Biker Shorts, Leggings, Men's Motion Tee, Edge Tank, Essential Shorts.
Price point: ₹2,000. Sold at wearthactive.com
"""

# ─── SEO KEYWORD CLUSTERS ─────────────────────────────────────────────────────
# 12 articles = 12 weeks of content. Each targets a different keyword cluster.

ARTICLE_BRIEFS = [
    {
        "slug": "why-polyester-is-bad-for-skin-during-exercise",
        "title": "Why Polyester Is Bad for Your Skin During Exercise (And What to Wear Instead)",
        "primary_keyword": "polyester bad for skin exercise",
        "secondary_keywords": ["synthetic activewear problems", "activewear without polyester india", "breathable gym wear"],
        "angle": "Scientific + personal. Explain what polyester actually does to skin during a workout — heat trap, bacteria, microplastics, chemical treatments on open pores. End with the natural alternative. Educational, not preachy.",
        "word_count": 900
    },
    {
        "slug": "eucalyptus-fabric-vs-polyester-activewear",
        "title": "Eucalyptus Fabric vs Polyester: The Truth About What You're Wearing to the Gym",
        "primary_keyword": "eucalyptus fabric vs polyester",
        "secondary_keywords": ["plant based activewear india", "eucalyptus activewear", "natural fabric gym wear india"],
        "angle": "Direct comparison. Properties side by side — breathability, moisture management, smell, microplastics, skin feel. Factual and confident.",
        "word_count": 900
    },
    {
        "slug": "plant-based-activewear-india",
        "title": "Plant-Based Activewear in India: Why It's Time to Make the Switch",
        "primary_keyword": "plant based activewear india",
        "secondary_keywords": ["sustainable activewear india", "natural activewear india", "eco friendly gym wear india"],
        "angle": "India-specific. Why Indian athletes specifically benefit — climate, skin types, washing habits. Position WEARTH as India's answer.",
        "word_count": 900
    },
    {
        "slug": "activewear-without-microplastics",
        "title": "Your Gym Clothes Are Releasing Microplastics. Here's What That Means.",
        "primary_keyword": "activewear without microplastics",
        "secondary_keywords": ["microplastics in activewear", "non toxic gym wear", "sustainable workout clothes india"],
        "angle": "Alarming but calm. What microplastics are, how they shed from synthetic activewear, what they do to the body and environment. The eucalyptus alternative.",
        "word_count": 900
    },
    {
        "slug": "best-breathable-activewear-india",
        "title": "The Best Breathable Activewear for India's Climate (That Isn't Polyester)",
        "primary_keyword": "breathable activewear india",
        "secondary_keywords": ["best gym wear india", "activewear for hot weather india", "moisture wicking activewear india"],
        "angle": "India climate-specific. Heat, humidity, long commutes to gym. Why breathability matters more here than anywhere. Natural fabrics win.",
        "word_count": 900
    },
    {
        "slug": "sustainable-activewear-india-guide",
        "title": "Sustainable Activewear in India: A Complete Guide for 2026",
        "primary_keyword": "sustainable activewear india",
        "secondary_keywords": ["eco friendly activewear india", "slow fashion activewear", "ethical sportswear india"],
        "angle": "Comprehensive guide. What makes activewear sustainable, what to look for, what to avoid, India-specific brands. WEARTH positioned naturally as the answer.",
        "word_count": 1100
    },
    {
        "slug": "how-eucalyptus-fabric-is-made",
        "title": "From Tree to Fabric: How Eucalyptus Activewear Is Made",
        "primary_keyword": "eucalyptus activewear india",
        "secondary_keywords": ["how is eucalyptus fabric made", "lyocell production process", "plant based fabric manufacturing"],
        "angle": "Origin story. Eucalyptus tree → wood pulp → closed-loop process → fabric. Visual, almost poetic. Makes the product feel premium and trustworthy.",
        "word_count": 800
    },
    {
        "slug": "non-polyester-workout-clothes-india",
        "title": "Non-Polyester Workout Clothes in India: Your Options in 2026",
        "primary_keyword": "non polyester workout clothes india",
        "secondary_keywords": ["activewear without polyester india", "cotton vs polyester activewear", "natural fiber gym wear"],
        "angle": "Practical guide. What alternatives to polyester exist for activewear (cotton, bamboo, eucalyptus). Honest pros/cons of each. Why eucalyptus wins for performance.",
        "word_count": 900
    },
    {
        "slug": "morning-workout-routine-activewear",
        "title": "The Morning Workout Ritual: Why What You Wear Actually Matters",
        "primary_keyword": "morning workout activewear india",
        "secondary_keywords": ["best activewear for morning yoga", "activewear for morning run india", "comfortable gym clothes india"],
        "angle": "Lifestyle angle. For the tribe — the 5:30am people. Sacred morning movement. How the wrong fabric breaks the spell. How the right one enhances it. Emotional.",
        "word_count": 800
    },
    {
        "slug": "womens-activewear-india-buying-guide",
        "title": "Women's Activewear in India: What to Look For Before You Buy",
        "primary_keyword": "womens activewear india",
        "secondary_keywords": ["best womens gym wear india", "activewear for indian body types", "women sports wear india"],
        "angle": "Practical buyer's guide for Indian women. Fit for Indian body types, climate considerations, fabric matters, what brands don't tell you. Empowering, not preachy.",
        "word_count": 1000
    },
    {
        "slug": "yoga-clothes-natural-fabric-india",
        "title": "Why Natural Fabric Makes Better Yoga Clothes (And Where to Find Them in India)",
        "primary_keyword": "natural fabric yoga clothes india",
        "secondary_keywords": ["best yoga wear india", "breathable yoga pants india", "sustainable yoga clothes india"],
        "angle": "Yoga-specific. The connection between natural fabric and the yoga practice. Breathability, temperature regulation, feel. Where synthetic breaks the flow.",
        "word_count": 800
    },
    {
        "slug": "wearth-brand-story",
        "title": "Why I Built Wearth: The Story of Making Activewear From Trees",
        "primary_keyword": "wearth activewear india",
        "secondary_keywords": ["indian activewear brand story", "sustainable fashion india founder", "plant based clothing india"],
        "angle": "Shai's voice. First person. Raw and real. The frustration with synthetic fabrics during her morning movement. The search. The discovery. The decision to build.",
        "word_count": 800
    }
]

# ─── ARTICLE GENERATOR ────────────────────────────────────────────────────────

def generate_article(brief: dict) -> dict:
    """Call Claude to generate a full SEO article based on the brief."""
    
    prompt = f"""You are writing a blog article for WEARTH Active (wearthactive.com).

{BRAND_CONTEXT}

ARTICLE BRIEF:
Title: {brief['title']}
Primary keyword: {brief['primary_keyword']}
Secondary keywords: {', '.join(brief['secondary_keywords'])}
Angle: {brief['angle']}
Target word count: {brief['word_count']} words

SEO REQUIREMENTS:
- Include primary keyword naturally in: title (already given), first paragraph, at least 2 subheadings, conclusion
- Include secondary keywords naturally throughout
- Use H2 and H3 subheadings (markdown format: ## and ###)
- First paragraph must hook the reader immediately — no "In today's world" or generic openings
- Include an internal link placeholder at the end: [Shop WEARTH plant-based activewear](https://wearthactive.com)
- Meta description: write one at the end (150-160 chars, includes primary keyword)

VOICE RULES:
- WEARTH voice: calm, certain, trusted friend who has done the research
- No exclamation marks ever
- No hype: amazing, incredible, game-changer, revolutionary
- No TENCEL or lyocell — use: eucalyptus fibre, plant-based fabric, from trees
- Short punchy paragraphs mixed with longer ones — rhythm matters
- Real, specific, factual

OUTPUT FORMAT (raw JSON only, no markdown code blocks):
{{
  "title": "exact title",
  "meta_description": "150-160 char SEO meta description",
  "body_html": "full article in HTML format with proper h2/h3/p tags",
  "tags": ["comma", "separated", "tags", "for", "shopify"],
  "word_count": approximate_number
}}"""

    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers=HEADERS_CLAUDE,
        json={
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 3000,
            "messages": [{"role": "user", "content": prompt}]
        }
    )
    
    if response.status_code != 200:
        raise Exception(f"Claude API error: {response.status_code} {response.text}")
    
    raw = response.json()["content"][0]["text"]
    cleaned = raw.replace("```json", "").replace("```", "").strip()
    return json.loads(cleaned)

# ─── SHOPIFY PUBLISHER ────────────────────────────────────────────────────────

def get_or_create_blog(blog_title: str = "WEARTH Journal") -> str:
    """Get existing blog ID or create one."""
    r = requests.get(f"{SHOPIFY_BASE}/blogs.json", headers=HEADERS_SHOPIFY)
    blogs = r.json().get("blogs", [])
    for blog in blogs:
        if blog["title"] == blog_title:
            return blog["id"]
    # Create new blog
    r = requests.post(
        f"{SHOPIFY_BASE}/blogs.json",
        headers=HEADERS_SHOPIFY,
        json={"blog": {"title": blog_title}}
    )
    return r.json()["blog"]["id"]

def publish_article(blog_id: str, brief: dict, article: dict) -> dict:
    """Publish article to Shopify blog."""
    payload = {
        "article": {
            "title": article["title"],
            "body_html": article["body_html"],
            "summary_html": f"<p>{article['meta_description']}</p>",
            "tags": ", ".join(article.get("tags", [])),
            "published": True,
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

# ─── MAIN RUNNER ──────────────────────────────────────────────────────────────

def run_seo_engine(dry_run: bool = False, article_index: int = None):
    """
    Main function.
    dry_run=True: generate and print but don't publish
    article_index: run specific article (0-11), or None to run next unpublished
    """
    print(f"\n{'='*60}")
    print(f"WEARTH SEO ENGINE — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE PUBLISH'}")
    print(f"{'='*60}\n")

    # Load published log
    log_file = "/home/claude/wearth-seo/published_articles.json"
    try:
        with open(log_file) as f:
            published = json.load(f)
    except FileNotFoundError:
        published = []

    published_slugs = [p["slug"] for p in published]

    # Pick article to generate
    if article_index is not None:
        brief = ARTICLE_BRIEFS[article_index]
    else:
        # Find next unpublished
        brief = None
        for b in ARTICLE_BRIEFS:
            if b["slug"] not in published_slugs:
                brief = b
                break
        if not brief:
            print("All 12 articles published. Cycle complete.")
            return

    print(f"Generating: {brief['title']}")
    print(f"Keyword: {brief['primary_keyword']}\n")

    # Generate article
    article = generate_article(brief)
    print(f"Generated: {article['title']}")
    print(f"Meta: {article['meta_description']}")
    print(f"Words: ~{article.get('word_count', 'unknown')}")

    if dry_run:
        print("\n--- BODY HTML PREVIEW (first 500 chars) ---")
        print(article["body_html"][:500])
        print("\n[DRY RUN — not published]")
        # Save preview
        preview_path = f"/home/claude/wearth-seo/preview_{brief['slug']}.html"
        with open(preview_path, "w") as f:
            f.write(f"<h1>{article['title']}</h1>\n")
            f.write(f"<p><em>Meta: {article['meta_description']}</em></p>\n")
            f.write(article["body_html"])
        print(f"Preview saved: {preview_path}")
        return article

    # Get blog ID
    blog_id = get_or_create_blog("WEARTH Journal")
    print(f"Blog ID: {blog_id}")

    # Publish
    published_article = publish_article(blog_id, brief, article)
    url = f"https://wearthactive.com/blogs/wearth-journal/{published_article.get('handle', brief['slug'])}"
    print(f"\nPublished: {url}")

    # Log it
    published.append({
        "slug": brief["slug"],
        "title": article["title"],
        "published_at": datetime.now().isoformat(),
        "shopify_id": published_article["id"],
        "url": url
    })
    with open(log_file, "w") as f:
        json.dump(published, f, indent=2)

    print(f"\nLog updated. Total published: {len(published)}/12")
    return published_article


if __name__ == "__main__":
    import sys
    dry = "--dry" in sys.argv
    idx = None
    for arg in sys.argv:
        if arg.startswith("--index="):
            idx = int(arg.split("=")[1])
    run_seo_engine(dry_run=dry, article_index=idx)
