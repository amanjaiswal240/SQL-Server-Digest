"""
SQL Server DBA Daily Digest
Fetches articles from curated RSS feeds, summarizes with Gemini API,
and generates a static HTML site.
"""

import feedparser
import requests
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from html import escape
import time

# ── CONFIG ────────────────────────────────────────────────────────────────────

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.0-flash:generateContent?key=" + GEMINI_API_KEY
)

MAX_ARTICLES   = 30   # Max articles to show on site per run
SUMMARY_LIMIT  = 15   # Max articles to AI-summarize per run (free tier friendly)
FETCH_TIMEOUT  = 15   # seconds per feed

# ── TRUSTED SQL SERVER RSS SOURCES ────────────────────────────────────────────

SOURCES = [
    {
        "name": "Brent Ozar Unlimited",
        "url":  "https://www.brentozar.com/feed/",
        "tag":  "Performance"
    },
    {
        "name": "SQL Server Central",
        "url":  "https://www.sqlservercentral.com/feed",
        "tag":  "Community"
    },
    {
        "name": "MSSQLTips",
        "url":  "https://www.mssqltips.com/rss.asp",
        "tag":  "Tips"
    },
    {
        "name": "SQLskills (Paul Randal & Erin Stellato)",
        "url":  "https://www.sqlskills.com/feed/",
        "tag":  "Internals"
    },
    {
        "name": "Microsoft SQL Server Blog",
        "url":  "https://techcommunity.microsoft.com/t5/sql-server-blog/bg-p/SQLServer/rss",
        "tag":  "Official"
    },
    {
        "name": "Simple Talk (Redgate)",
        "url":  "https://www.red-gate.com/simple-talk/feed/",
        "tag":  "Deep Dive"
    },
    {
        "name": "SQL Authority (Pinal Dave)",
        "url":  "https://blog.sqlauthority.com/feed/",
        "tag":  "Tips"
    },
    {
        "name": "Aaron Bertrand",
        "url":  "https://sqlblog.org/rss.xml",
        "tag":  "Performance"
    },
    {
        "name": "Andy Mallon (am2)",
        "url":  "https://am2.co/feed/",
        "tag":  "DBA Life"
    },
    {
        "name": "Kendra Little",
        "url":  "https://littlekendra.com/feed/",
        "tag":  "Query Tuning"
    },
]

# ── KEYWORD RELEVANCE FILTER ───────────────────────────────────────────────────

SQL_KEYWORDS = [
    "sql server", "t-sql", "tsql", "query store", "always on",
    "availability group", "index", "execution plan", "deadlock",
    "tempdb", "in-memory", "columnstore", "intelligent query",
    "azure sql", "managed instance", "backup", "restore", "ha/dr",
    "replication", "database", "dba", "performance", "tuning",
    "wait stats", "transaction", "locking", "blocking", "cumulative update",
    "service pack", "security", "tde", "encryption", "agent",
    "linked server", "ssis", "ssrs", "ssas", "polybase"
]

def is_sql_relevant(title: str, summary: str) -> bool:
    text = (title + " " + summary).lower()
    return any(kw in text for kw in SQL_KEYWORDS)

# ── RSS FETCHING ───────────────────────────────────────────────────────────────

def fetch_articles() -> list[dict]:
    all_articles = []
    for source in SOURCES:
        try:
            print(f"  Fetching: {source['name']} ...")
            feed = feedparser.parse(source["url"], request_headers={
                "User-Agent": "SQLServerDigest/1.0 (+https://github.com)"
            })
            for entry in feed.entries[:5]:  # max 5 per source
                title   = entry.get("title", "").strip()
                link    = entry.get("link", "").strip()
                summary = re.sub(r"<[^>]+>", "", entry.get("summary", ""))[:500]
                pub     = entry.get("published", entry.get("updated", ""))

                if not title or not link:
                    continue
                if not is_sql_relevant(title, summary):
                    continue

                all_articles.append({
                    "title":   title,
                    "link":    link,
                    "summary": summary.strip(),
                    "source":  source["name"],
                    "tag":     source["tag"],
                    "pub":     pub,
                    "ai_summary": None,
                })
        except Exception as e:
            print(f"  ⚠ Error fetching {source['name']}: {e}")
        time.sleep(0.5)  # polite crawling

    # Sort by most recent (approximate — not all feeds have parseable dates)
    all_articles = all_articles[:MAX_ARTICLES]
    print(f"\n✅ Collected {len(all_articles)} relevant articles")
    return all_articles

# ── GEMINI SUMMARIZATION ───────────────────────────────────────────────────────

def summarize_article(title: str, raw_summary: str) -> str:
    """Call Gemini Flash to generate a 3-bullet DBA-focused summary."""
    if not GEMINI_API_KEY:
        return ""

    prompt = f"""You are an expert SQL Server DBA. Summarize this article for a busy DBA.

Article Title: {title}
Article Excerpt: {raw_summary}

Respond with ONLY 3 concise bullet points (each max 20 words).
Focus on: what changed, why it matters to a DBA, and any action needed.
Do NOT include any preamble, headers, or extra text. Just the 3 bullets starting with •"""

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 200, "temperature": 0.3}
    }

    try:
        resp = requests.post(GEMINI_URL, json=payload, timeout=20)
        data = resp.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        return text
    except Exception as e:
        print(f"    ⚠ Gemini error: {e}")
        return ""

def add_ai_summaries(articles: list[dict]) -> list[dict]:
    if not GEMINI_API_KEY:
        print("⚠ No GEMINI_API_KEY set — skipping AI summaries")
        return articles

    print(f"\n🤖 Generating AI summaries for top {SUMMARY_LIMIT} articles...")
    for i, article in enumerate(articles[:SUMMARY_LIMIT]):
        print(f"  [{i+1}/{SUMMARY_LIMIT}] {article['title'][:60]}...")
        article["ai_summary"] = summarize_article(
            article["title"], article["summary"]
        )
        time.sleep(1)  # rate limit friendly
    return articles

# ── LOAD / SAVE HISTORY ────────────────────────────────────────────────────────

HISTORY_FILE = Path("site/articles_history.json")

def load_history() -> list[dict]:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text())
        except Exception:
            return []
    return []

def save_history(articles: list[dict]):
    existing = load_history()
    existing_links = {a["link"] for a in existing}
    new_articles = [a for a in articles if a["link"] not in existing_links]
    combined = new_articles + existing
    combined = combined[:200]  # keep last 200 articles
    HISTORY_FILE.write_text(json.dumps(combined, indent=2, ensure_ascii=False))
    print(f"💾 History: {len(new_articles)} new articles saved ({len(combined)} total)")

# ── HTML GENERATION ────────────────────────────────────────────────────────────

TAG_COLORS = {
    "Performance":   "#e74c3c",
    "Official":      "#2980b9",
    "Community":     "#27ae60",
    "Tips":          "#f39c12",
    "Internals":     "#8e44ad",
    "Deep Dive":     "#16a085",
    "DBA Life":      "#d35400",
    "Query Tuning":  "#c0392b",
}

def tag_color(tag: str) -> str:
    return TAG_COLORS.get(tag, "#555")

def format_article_card(article: dict, index: int) -> str:
    title       = escape(article["title"])
    link        = escape(article["link"])
    source      = escape(article["source"])
    tag         = escape(article["tag"])
    color       = tag_color(article["tag"])
    raw_summary = escape(article["summary"][:200]) + ("…" if len(article["summary"]) > 200 else "")
    pub         = escape(article.get("pub", "")[:16])
    ai          = article.get("ai_summary", "")

    ai_html = ""
    if ai:
        bullets = [b.strip() for b in ai.split("\n") if b.strip().startswith("•")]
        if bullets:
            items = "".join(f"<li>{escape(b[1:].strip())}</li>" for b in bullets)
            ai_html = f"""
        <div class="ai-summary">
          <span class="ai-badge">✦ AI Summary</span>
          <ul>{items}</ul>
        </div>"""

    return f"""
    <article class="card" style="--accent:{color}" data-index="{index}">
      <div class="card-top">
        <span class="tag" style="background:{color}">{tag}</span>
        <span class="source">{source}</span>
        {f'<span class="pub-date">{pub}</span>' if pub else ''}
      </div>
      <h2><a href="{link}" target="_blank" rel="noopener">{title}</a></h2>
      <p class="excerpt">{raw_summary}</p>
      {ai_html}
      <a class="read-link" href="{link}" target="_blank" rel="noopener">
        Read full article →
      </a>
    </article>"""

def build_html(articles: list[dict], history: list[dict]) -> str:
    now        = datetime.now(timezone.utc).strftime("%B %d, %Y — %H:%M UTC")
    total_hist = len(history)
    cards      = "\n".join(format_article_card(a, i) for i, a in enumerate(articles))
    sources_list = ", ".join(s["name"] for s in SOURCES)

    # Stats
    tags       = {}
    for a in articles:
        tags[a["tag"]] = tags.get(a["tag"], 0) + 1
    tag_pills  = "".join(
        f'<button class="filter-btn" data-tag="{escape(t)}" style="--c:{tag_color(t)}">'
        f'{escape(t)} <span>{c}</span></button>'
        for t, c in sorted(tags.items(), key=lambda x: -x[1])
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>SQL Server DBA Digest</title>
  <meta name="description" content="Daily curated SQL Server news, features and enhancements for DBAs — summarized by AI."/>
  <link rel="preconnect" href="https://fonts.googleapis.com"/>
  <link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;700;800&family=JetBrains+Mono:wght@400;500&family=Lora:ital,wght@0,400;0,600;1,400&display=swap" rel="stylesheet"/>
  <style>
    :root {{
      --bg:       #0d1117;
      --surface:  #161b22;
      --surface2: #21262d;
      --border:   #30363d;
      --text:     #e6edf3;
      --muted:    #8b949e;
      --accent:   #f78166;
      --gold:     #d4a820;
      --green:    #3fb950;
      --font-head: 'Syne', sans-serif;
      --font-body: 'Lora', serif;
      --font-mono: 'JetBrains Mono', monospace;
    }}

    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

    body {{
      background: var(--bg);
      color: var(--text);
      font-family: var(--font-body);
      font-size: 1rem;
      line-height: 1.7;
      min-height: 100vh;
    }}

    /* ── HERO ── */
    .hero {{
      position: relative;
      overflow: hidden;
      padding: 4rem 2rem 3rem;
      border-bottom: 1px solid var(--border);
      background:
        radial-gradient(ellipse 80% 60% at 50% -10%, rgba(247,129,102,0.12) 0%, transparent 70%),
        var(--bg);
    }}
    .hero::before {{
      content: '';
      position: absolute;
      inset: 0;
      background-image:
        repeating-linear-gradient(0deg, transparent, transparent 39px, rgba(48,54,61,0.35) 40px),
        repeating-linear-gradient(90deg, transparent, transparent 39px, rgba(48,54,61,0.35) 40px);
      pointer-events: none;
    }}

    .hero-inner {{
      max-width: 900px;
      margin: 0 auto;
      position: relative;
    }}
    .hero-eyebrow {{
      font-family: var(--font-mono);
      font-size: 0.72rem;
      letter-spacing: 0.18em;
      color: var(--accent);
      text-transform: uppercase;
      margin-bottom: 1rem;
    }}
    .hero h1 {{
      font-family: var(--font-head);
      font-size: clamp(2.4rem, 6vw, 4rem);
      font-weight: 800;
      line-height: 1.05;
      letter-spacing: -0.02em;
    }}
    .hero h1 span {{ color: var(--accent); }}
    .hero-sub {{
      margin-top: 1rem;
      color: var(--muted);
      font-size: 1.05rem;
      max-width: 520px;
    }}
    .hero-meta {{
      margin-top: 2rem;
      display: flex;
      flex-wrap: wrap;
      gap: 1.5rem;
      align-items: center;
    }}
    .stat {{
      display: flex;
      flex-direction: column;
      gap: 0.1rem;
    }}
    .stat-num {{
      font-family: var(--font-head);
      font-size: 1.8rem;
      font-weight: 800;
      color: var(--text);
      line-height: 1;
    }}
    .stat-label {{
      font-family: var(--font-mono);
      font-size: 0.68rem;
      color: var(--muted);
      letter-spacing: 0.1em;
      text-transform: uppercase;
    }}
    .divider-v {{
      width: 1px;
      height: 40px;
      background: var(--border);
    }}
    .updated {{
      font-family: var(--font-mono);
      font-size: 0.72rem;
      color: var(--muted);
      margin-left: auto;
    }}
    .updated span {{ color: var(--green); }}

    /* ── TOOLBAR ── */
    .toolbar {{
      max-width: 900px;
      margin: 0 auto;
      padding: 1.5rem 2rem;
      display: flex;
      flex-wrap: wrap;
      gap: 0.6rem;
      align-items: center;
      border-bottom: 1px solid var(--border);
    }}
    .toolbar-label {{
      font-family: var(--font-mono);
      font-size: 0.7rem;
      color: var(--muted);
      letter-spacing: 0.12em;
      text-transform: uppercase;
      margin-right: 0.4rem;
    }}
    .filter-btn {{
      font-family: var(--font-mono);
      font-size: 0.72rem;
      padding: 0.3rem 0.75rem;
      border-radius: 2rem;
      border: 1px solid var(--c, #555);
      background: transparent;
      color: var(--c, #aaa);
      cursor: pointer;
      transition: background 0.15s, color 0.15s;
      display: flex; gap: 0.4rem; align-items: center;
    }}
    .filter-btn span {{
      background: var(--c, #555);
      color: #000;
      border-radius: 1rem;
      padding: 0 0.4rem;
      font-size: 0.65rem;
      font-weight: 700;
    }}
    .filter-btn:hover,
    .filter-btn.active {{
      background: var(--c, #555);
      color: #fff;
    }}
    .filter-btn.active span {{ background: rgba(0,0,0,0.3); color: #fff; }}

    /* ── SEARCH ── */
    .search-wrap {{
      max-width: 900px;
      margin: 0 auto;
      padding: 0 2rem 1.5rem;
    }}
    .search-input {{
      width: 100%;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 0.75rem 1.1rem 0.75rem 2.8rem;
      color: var(--text);
      font-family: var(--font-mono);
      font-size: 0.85rem;
      outline: none;
      transition: border-color 0.15s;
      background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' fill='%238b949e' viewBox='0 0 16 16'%3E%3Cpath d='M11.742 10.344a6.5 6.5 0 1 0-1.397 1.398h-.001c.03.04.062.078.098.115l3.85 3.85a1 1 0 0 0 1.415-1.414l-3.85-3.85a1.007 1.007 0 0 0-.115-.099zm-5.242 1.656a5.5 5.5 0 1 1 0-11 5.5 5.5 0 0 1 0 11z'/%3E%3C/svg%3E");
      background-repeat: no-repeat;
      background-position: 0.9rem center;
    }}
    .search-input:focus {{ border-color: var(--accent); }}
    .search-input::placeholder {{ color: var(--muted); }}

    /* ── CARDS ── */
    .feed {{
      max-width: 900px;
      margin: 0 auto;
      padding: 0 2rem 4rem;
      display: flex;
      flex-direction: column;
      gap: 1.25rem;
    }}

    .card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-left: 3px solid var(--accent);
      border-radius: 10px;
      padding: 1.5rem 1.75rem;
      transition: border-color 0.2s, transform 0.15s, box-shadow 0.2s;
      animation: fadeUp 0.4s ease both;
      animation-delay: calc(var(--index, 0) * 0.04s);
    }}
    @keyframes fadeUp {{
      from {{ opacity: 0; transform: translateY(12px); }}
      to   {{ opacity: 1; transform: translateY(0); }}
    }}
    .card:hover {{
      border-color: var(--accent);
      box-shadow: 0 4px 24px rgba(0,0,0,0.4);
      transform: translateY(-2px);
    }}
    .card-top {{
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
      align-items: center;
      margin-bottom: 0.75rem;
    }}
    .tag {{
      font-family: var(--font-mono);
      font-size: 0.65rem;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      color: #fff;
      padding: 0.2rem 0.65rem;
      border-radius: 2rem;
      font-weight: 500;
    }}
    .source {{
      font-family: var(--font-mono);
      font-size: 0.72rem;
      color: var(--muted);
    }}
    .pub-date {{
      font-family: var(--font-mono);
      font-size: 0.68rem;
      color: var(--muted);
      margin-left: auto;
    }}

    .card h2 {{
      font-family: var(--font-head);
      font-size: 1.15rem;
      font-weight: 700;
      line-height: 1.3;
      margin-bottom: 0.6rem;
    }}
    .card h2 a {{
      color: var(--text);
      text-decoration: none;
      transition: color 0.15s;
    }}
    .card h2 a:hover {{ color: var(--accent); }}

    .excerpt {{
      color: var(--muted);
      font-size: 0.9rem;
      line-height: 1.6;
      margin-bottom: 0.85rem;
    }}

    /* ── AI SUMMARY ── */
    .ai-summary {{
      background: var(--surface2);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 1rem 1.2rem;
      margin-bottom: 1rem;
    }}
    .ai-badge {{
      font-family: var(--font-mono);
      font-size: 0.65rem;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      color: var(--gold);
      display: block;
      margin-bottom: 0.6rem;
    }}
    .ai-summary ul {{
      list-style: none;
      padding: 0;
      display: flex;
      flex-direction: column;
      gap: 0.35rem;
    }}
    .ai-summary li {{
      font-size: 0.88rem;
      color: var(--text);
      padding-left: 1.2rem;
      position: relative;
      line-height: 1.5;
    }}
    .ai-summary li::before {{
      content: '›';
      position: absolute;
      left: 0;
      color: var(--gold);
      font-weight: 700;
    }}

    .read-link {{
      font-family: var(--font-mono);
      font-size: 0.78rem;
      color: var(--accent);
      text-decoration: none;
      letter-spacing: 0.03em;
      transition: opacity 0.15s;
    }}
    .read-link:hover {{ opacity: 0.7; }}

    /* ── EMPTY STATE ── */
    .no-results {{
      text-align: center;
      padding: 4rem 2rem;
      color: var(--muted);
      font-family: var(--font-mono);
      font-size: 0.85rem;
      display: none;
    }}

    /* ── FOOTER ── */
    footer {{
      border-top: 1px solid var(--border);
      padding: 2rem;
      text-align: center;
      font-family: var(--font-mono);
      font-size: 0.72rem;
      color: var(--muted);
      line-height: 2;
    }}
    footer a {{ color: var(--muted); }}

    /* ── RESPONSIVE ── */
    @media (max-width: 600px) {{
      .hero {{ padding: 2.5rem 1.25rem 2rem; }}
      .toolbar, .search-wrap, .feed {{ padding-left: 1.25rem; padding-right: 1.25rem; }}
      .hero-meta {{ gap: 1rem; }}
      .updated {{ margin-left: 0; }}
    }}
  </style>
</head>
<body>

<!-- HERO -->
<header class="hero">
  <div class="hero-inner">
    <p class="hero-eyebrow">// Daily Intelligence Feed</p>
    <h1>SQL Server<br/><span>DBA Digest</span></h1>
    <p class="hero-sub">
      Curated news, features &amp; enhancements from the top SQL Server experts —
      summarized by AI, delivered daily.
    </p>
    <div class="hero-meta">
      <div class="stat">
        <span class="stat-num" id="js-count">{len(articles)}</span>
        <span class="stat-label">Articles Today</span>
      </div>
      <div class="divider-v"></div>
      <div class="stat">
        <span class="stat-num">{total_hist}</span>
        <span class="stat-label">In Archive</span>
      </div>
      <div class="divider-v"></div>
      <div class="stat">
        <span class="stat-num">{len(SOURCES)}</span>
        <span class="stat-label">Trusted Sources</span>
      </div>
      <p class="updated">Updated <span>{now}</span></p>
    </div>
  </div>
</header>

<!-- FILTER TOOLBAR -->
<div class="toolbar">
  <span class="toolbar-label">Filter:</span>
  <button class="filter-btn active" data-tag="all" style="--c:#8b949e">
    All <span>{len(articles)}</span>
  </button>
  {tag_pills}
</div>

<!-- SEARCH -->
<div class="search-wrap">
  <input
    class="search-input"
    type="search"
    id="js-search"
    placeholder="Search articles, topics, sources…"
    autocomplete="off"
  />
</div>

<!-- ARTICLES -->
<main class="feed" id="js-feed">
{cards}
  <p class="no-results" id="js-empty">No articles match your search.</p>
</main>

<!-- FOOTER -->
<footer>
  <p>Sources: {sources_list}</p>
  <p style="margin-top:0.5rem">
    Built with Python · GitHub Actions · Gemini AI · Netlify &nbsp;|&nbsp;
    <a href="articles_history.json">Raw JSON</a>
  </p>
</footer>

<script>
  // ── Filter by tag ──
  const filterBtns = document.querySelectorAll('.filter-btn');
  const cards      = document.querySelectorAll('.card');
  const feed       = document.getElementById('js-feed');
  const countEl    = document.getElementById('js-count');
  const emptyEl    = document.getElementById('js-empty');
  const searchEl   = document.getElementById('js-search');

  let activeTag  = 'all';
  let searchTerm = '';

  function applyFilters() {{
    let visible = 0;
    cards.forEach(card => {{
      const tag    = card.querySelector('.tag')?.textContent.trim() || '';
      const text   = card.textContent.toLowerCase();
      const tagOk  = activeTag === 'all' || tag === activeTag;
      const srchOk = !searchTerm || text.includes(searchTerm);
      const show   = tagOk && srchOk;
      card.style.display = show ? '' : 'none';
      if (show) visible++;
    }});
    countEl.textContent = visible;
    emptyEl.style.display = visible === 0 ? 'block' : 'none';
  }}

  filterBtns.forEach(btn => {{
    btn.addEventListener('click', () => {{
      filterBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      activeTag = btn.dataset.tag;
      applyFilters();
    }});
  }});

  searchEl.addEventListener('input', e => {{
    searchTerm = e.target.value.toLowerCase().trim();
    applyFilters();
  }});

  // ── Stagger animation ──
  cards.forEach((card, i) => card.style.setProperty('--index', i));
</script>

</body>
</html>"""

# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 55)
    print("  SQL Server DBA Digest — Build Script")
    print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 55)

    print("\n📡 Fetching RSS feeds...")
    articles = fetch_articles()

    if not articles:
        print("⚠ No articles found — check feed URLs or network.")
        return

    articles = add_ai_summaries(articles)

    history = load_history()
    save_history(articles)
    # Reload history after save so count is accurate
    history = load_history()

    print("\n🏗  Building HTML...")
    html = build_html(articles, history)

    out = Path("site/index.html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"✅ Site written → {out}  ({len(html):,} bytes)")
    print("\n🎉 Done! Deploy the /site folder to Netlify.\n")

if __name__ == "__main__":
    main()
