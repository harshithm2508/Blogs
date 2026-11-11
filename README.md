# 📚 Blog Library

A personal tracker for the blog posts I read. Every post is **scraped in full** (text, headings, code,
images, links + metadata), saved as Markdown, and organised **by company** and **by source**.

- **Browse:** open the web viewer (`index.html`, served via GitHub Pages) — search, filter, group by company/source, and read saved copies.
- **Files:** each post lives in `library/<company>/<published-date>-<title>.md`; the catalogue is `data/blogs.json`.

## The library

<!-- LIBRARY:START -->
**0** posts tracked · **0** read · **0** companies · **0** sources · ~**0h 0m** of reading

_Nothing tracked yet. Add your first blog post (see **Adding a blog** below)._
<!-- LIBRARY:END -->

## Adding a blog

| Way | How |
|---|---|
| **Ask Claude** | Send the link(s) in a Claude Code session on this repo — Claude runs the *Add blog* workflow for you. |
| **Issue (works on mobile)** | *Issues → New issue → "Add a blog"*, paste link(s). A bot scrapes them, replies, and closes the issue. |
| **Actions tab** | *Actions → Add blog → Run workflow*, paste link(s). Optional company / source / tags / notes / rating. |
| **Locally** | `pip install -r requirements.txt` then `python -m tracker add <url> [--tags a,b --rating 5 --notes "..."]` |

Scraping runs on GitHub Actions, so it works for any public site. Several URLs can be sent at once.
Already-tracked links are detected (tracking params like `utm_*` are ignored); use *refresh* to re-scrape.

### Other commands

```bash
python -m tracker list [--company Netflix] [--source Medium]
python -m tracker update <id|url> --status to-read --rating 4 --notes "..." --company "X"   # re-files if company changes
python -m tracker remove <id|url>
python -m tracker rebuild          # regenerate README + per-company indexes
python -m tracker add <url> --dry-run   # preview the extraction without saving
```

## How posts are classified

- **Company** – the organisation behind the post (Netflix, Uber, Stripe…), detected from a built-in domain list,
  Medium publication names, and `engineering.` / `/blog` style URLs. Individual writers go under **Independent**.
- **Source** – where it was published: *Company Blog, Medium, Substack, Dev.to, Hashnode, Personal / Independent Site…*
- **Publication** – the specific blog name (e.g. "Netflix TechBlog").

Wrong guess? Override it with `--company` / `--source` (or the form fields), or add the domain to
`tracker/classify.py` → `COMPANY_DOMAINS`.

## Web viewer setup (one time)

*Settings → Pages → Build and deployment → Source: "Deploy from a branch"*, pick the default branch and **/ (root)**.
The viewer is then live at `https://<user>.github.io/<repo>/`. (GitHub Pages on a private repo needs a paid plan;
otherwise the README tables above work everywhere.)

## Layout

```
tracker/            scraper (trafilatura + BeautifulSoup), classifier, storage, CLI
library/<company>/  one Markdown file per post (+ an index README per company)
data/blogs.json     catalogue of all posts (metadata, status, rating, notes)
index.html          web viewer
.github/workflows/  add-blog.yml (scrape + commit), tests.yml
```
