# 🗄️ SQL Server DBA Digest

> Daily curated SQL Server news, features & enhancements — fetched from 10 trusted sources,
> summarized by Gemini AI, deployed as a public static site on Netlify.
> Runs automatically every day. Your laptop can be OFF.

---

## 📁 Project Structure

```
sqlserver-digest/
├── .github/
│   └── workflows/
│       └── daily_digest.yml     ← GitHub Actions scheduler
├── scripts/
│   └── fetch_and_build.py       ← Main Python script
├── site/
│   ├── index.html               ← Generated public website
│   └── articles_history.json   ← Article archive (auto-updated)
├── requirements.txt             ← Python dependencies
├── netlify.toml                 ← Netlify config
└── README.md
```

---

## 🚀 ONE-TIME SETUP (Do This Once — Takes ~15 Minutes)

### STEP 1 — Get a Free Gemini API Key

1. Go to → https://aistudio.google.com
2. Sign in with your Google account
3. Click **"Get API Key"** → **"Create API Key"**
4. Copy the key — looks like: `AIzaSyXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX`
5. Keep it safe — you'll need it in Step 3

> ✅ No credit card required. Free tier = 1,500 requests/day (way more than needed).

---

### STEP 2 — Push This Project to GitHub

1. Go to → https://github.com/new
2. Create a new **public** repository (name it: `sqlserver-dba-digest`)
3. On your local machine (or GitHub web UI), upload all these files:
   ```
   .github/workflows/daily_digest.yml
   scripts/fetch_and_build.py
   site/index.html
   site/articles_history.json
   requirements.txt
   netlify.toml
   .gitignore
   README.md
   ```

**Using Git CLI:**
```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/sqlserver-dba-digest.git
git push -u origin main
```

---

### STEP 3 — Add Gemini API Key as GitHub Secret

1. Go to your GitHub repo page
2. Click **Settings** → **Secrets and variables** → **Actions**
3. Click **"New repository secret"**
4. Name:  `GEMINI_API_KEY`
5. Value: paste your Gemini API key from Step 1
6. Click **"Add secret"**

> 🔒 This keeps your API key secure — it's never visible in code or logs.

---

### STEP 4 — Connect to Netlify (Free Hosting)

1. Go to → https://netlify.com → Sign up free (use GitHub login)
2. Click **"Add new site"** → **"Import an existing project"**
3. Choose **GitHub** → Select your `sqlserver-dba-digest` repo
4. Netlify settings (should auto-detect from `netlify.toml`):
   - **Build command:** (leave empty)
   - **Publish directory:** `site`
5. Click **"Deploy site"**
6. Netlify gives you a URL like: `https://dazzling-xyz-123.netlify.app`

> 💡 Optional: Go to Site Settings → Domain → set a custom name like
> `sqlserver-digest.netlify.app`

---

### STEP 5 — Tell Netlify to Deploy When GitHub Pushes

This happens automatically! Netlify watches your GitHub repo.
Every time GitHub Actions pushes the updated `site/index.html`,
Netlify detects the push and re-deploys within seconds.

---

### STEP 6 — Run Your First Build Manually

Don't want to wait until tomorrow? Trigger it now:

1. Go to your GitHub repo
2. Click **Actions** tab
3. Click **"SQL Server DBA Digest — Daily Build"**
4. Click **"Run workflow"** → **"Run workflow"** (green button)
5. Watch it run — takes ~2-3 minutes
6. Visit your Netlify URL — your site is live! 🎉

---

## ⏰ When Does It Run?

The workflow is scheduled for **6:00 AM IST every day** (00:30 UTC).

To change the time, edit `.github/workflows/daily_digest.yml`:
```yaml
- cron: '30 0 * * *'   # 6:00 AM IST
```

**Cron reference (UTC times):**
| Desired Time (IST) | Cron (UTC)        |
|--------------------|-------------------|
| 5:30 AM IST        | `0 0 * * *`       |
| 6:00 AM IST        | `30 0 * * *`      |
| 7:00 AM IST        | `30 1 * * *`      |
| 8:00 AM IST        | `30 2 * * *`      |

> IST = UTC + 5:30

---

## 🤖 How AI Summarization Works

- The script fetches articles from 10 RSS feeds
- Filters for SQL Server relevance using keyword matching
- For the top 15 articles, calls **Gemini Flash API** with a DBA-focused prompt
- Each article gets 3 bullet points: *what changed · why it matters · action needed*
- If no API key is set, the site still works — just without AI bullets

---

## 📰 Curated Sources

| Source | Focus |
|--------|-------|
| Brent Ozar Unlimited | Performance Tuning |
| SQL Server Central | Community |
| MSSQLTips | Tips & How-Tos |
| SQLskills (Paul Randal & Erin Stellato) | Internals |
| Microsoft SQL Server Blog | Official Announcements |
| Simple Talk (Redgate) | Deep Dives |
| SQL Authority (Pinal Dave) | Tips |
| Aaron Bertrand | Performance |
| Andy Mallon | DBA Life |
| Kendra Little | Query Tuning |

To add/remove sources, edit the `SOURCES` list in `scripts/fetch_and_build.py`.

---

## 💰 Cost Summary

| Component | Cost |
|-----------|------|
| GitHub Actions | Free (2,000 min/month) |
| Gemini Flash API | Free (1,500 req/day) |
| Netlify Hosting | Free |
| **Total** | **₹0 / month** |

---

## 🔧 Customization

**Change schedule time:** Edit `cron` in `daily_digest.yml`

**Add more sources:** Add entries to `SOURCES` in `fetch_and_build.py`

**Change keyword filter:** Edit `SQL_KEYWORDS` list

**Switch to Claude API:** Replace `summarize_article()` function:
```python
# Replace Gemini call with:
import anthropic
client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
msg = client.messages.create(
    model="claude-haiku-4-5-20251001",
    max_tokens=200,
    messages=[{"role": "user", "content": prompt}]
)
return msg.content[0].text
```

---

## ❓ Troubleshooting

**Build fails in GitHub Actions:**
- Check the Actions tab for error logs
- Make sure `GEMINI_API_KEY` secret is set correctly
- Test locally: `GEMINI_API_KEY=your_key python scripts/fetch_and_build.py`

**No articles showing:**
- Some feeds may be temporarily down — normal, script handles it
- Check if keyword filter is too strict (edit `SQL_KEYWORDS`)

**Netlify not updating:**
- Check Netlify dashboard → Deploys — should show a new deploy after each GitHub push
- Make sure Netlify is connected to your GitHub repo

---

*Built with ❤️ for SQL Server DBAs everywhere.*
