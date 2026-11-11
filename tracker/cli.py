"""Command line interface.

    python -m tracker add URL [URL ...] [--company X] [--source Y] [--tags a,b] [--notes "..."]
                              [--status read|to-read] [--rating 1-5] [--refresh] [--dry-run]
    python -m tracker add-from-issue          # reads ISSUE_BODY from the environment (GitHub Actions)
    python -m tracker update ID_OR_URL [--status ...] [--rating ...] [--notes ...] [--tags ...] [--company ...]
    python -m tracker remove ID_OR_URL
    python -m tracker list [--company X] [--source Y]
    python -m tracker rebuild
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

from . import classify, render, scraper, storage

URL_RE = re.compile(r"https?://[^\s<>\"')\]]+")


def _tags(value: str | None) -> list[str]:
    return [t.strip() for t in (value or "").split(",") if t.strip()]


def add_url(catalog: dict, url: str, *, company=None, source=None, tags=None, notes=None,
            status="read", rating=None, refresh=False, dry_run=False, html=None) -> dict:
    norm = scraper.normalize_url(url)
    pid = storage.post_id(norm)
    existing = storage.find(catalog, pid)
    if existing and not refresh:
        print(f"• already tracked: {existing['title']}  ({existing['path']})")
        return {"status": "duplicate", "entry": existing}

    if html is not None:
        post = scraper.parse(html, url)
    else:
        post = scraper.scrape(url)
    cls = classify.classify(post.canonical_url or url, post.html, post.sitename, post.author)

    entry = {
        "id": pid,
        "title": post.title,
        "url": norm,
        "canonical_url": post.canonical_url,
        "author": post.author,
        "published": post.published,
        "company": company or cls["company"],
        "source": source or cls["source"],
        "publication": cls["publication"],
        "platform": cls["platform"],
        "tags": sorted(set(_tags(",".join(tags or [])) + post.tags), key=str.lower) if tags else post.tags,
        "description": post.description,
        "image": post.image,
        "language": post.language,
        "word_count": post.word_count,
        "reading_minutes": post.reading_minutes,
        "status": status,
        "rating": rating,
        "notes": notes,
        "added": existing["added"] if existing else storage.now(),
        "read_on": storage.today() if status == "read" else None,
    }
    if existing:  # keep the user's personal fields on refresh
        entry["status"] = existing.get("status") or status if status == "read" else status
        entry["rating"] = rating or existing.get("rating")
        entry["notes"] = notes or existing.get("notes")
        entry["read_on"] = existing.get("read_on") or entry["read_on"]
        if not company and existing.get("company"):
            entry["company"] = existing["company"]
        if not source and existing.get("source"):
            entry["source"] = existing["source"]

    path = storage.article_path(entry)
    entry["path"] = path.relative_to(storage.ROOT).as_posix()
    print(f"✓ {entry['title']}\n    company={entry['company']}  source={entry['source']}  "
          f"publication={entry['publication']}  words={entry['word_count']}  → {entry['path']}")
    if post.word_count < 100:
        print("    ⚠ very little text was extracted — the page may need JavaScript or be paywalled.")

    if dry_run:
        print("\n----- preview -----\n" + post.content_markdown[:1500])
        return {"status": "dry-run", "entry": entry}

    if existing:
        old = storage.ROOT / existing["path"]
        if old.exists() and old != path:
            old.unlink()
        catalog["blogs"].remove(existing)
    storage.write_article(entry, post.content_markdown)
    catalog["blogs"].append(entry)
    return {"status": "updated" if existing else "added", "entry": entry}


def _resolve(catalog: dict, ref: str) -> dict:
    entry = storage.find(catalog, ref) or storage.find(catalog, storage.post_id(scraper.normalize_url(ref)))
    if not entry:
        sys.exit(f"not found: {ref}")
    return entry


def parse_issue_form(body: str) -> dict:
    """Parse a GitHub issue-form body ("### Label\\n\\nvalue") into a dict."""
    fields = {}
    for m in re.finditer(r"^###\s+(.+?)\s*$\n+(.*?)(?=^###\s|\Z)", body or "", re.M | re.S):
        value = m.group(2).strip()
        fields[m.group(1).strip().lower()] = "" if value == "_No response_" else value
    return fields


def _write_summary(results: list[dict]) -> None:
    lines = []
    for r in results:
        e = r.get("entry") or {}
        if r["status"] == "error":
            lines.append(f"- ❌ {r['url']} — {r['error']}")
        else:
            lines.append(f"- {'✅' if r['status'] in ('added', 'updated') else 'ℹ️'} **{r['status']}**: "
                         f"[{e.get('title')}]({e.get('url')}) → `{e.get('path')}` "
                         f"({e.get('company')} · {e.get('source')} · {e.get('word_count')} words)")
    text = "\n".join(lines) + "\n"
    out = os.environ.get("TRACKER_SUMMARY_FILE")
    if out:
        Path(out).write_text(text, encoding="utf-8")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as fh:
            fh.write("## Blog tracker\n\n" + text)


def run_add(urls: list[str], **kw) -> int:
    catalog = storage.load_catalog()
    results, failed = [], 0
    for url in urls:
        try:
            results.append({"url": url, **add_url(catalog, url, **kw)})
        except Exception as exc:  # keep going with the other URLs
            failed += 1
            print(f"✗ {url}: {exc}", file=sys.stderr)
            results.append({"url": url, "status": "error", "error": str(exc)})
    if not kw.get("dry_run"):
        storage.save_catalog(catalog)
        render.render_all(catalog)
    _write_summary(results)
    return 1 if failed and failed == len(urls) else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="tracker", description="Track and archive blog posts you read.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def personal(p, defaults=True):
        p.add_argument("--company")
        p.add_argument("--source")
        p.add_argument("--tags", help="comma separated")
        p.add_argument("--notes")
        p.add_argument("--status", choices=["read", "to-read"], default="read" if defaults else None)
        p.add_argument("--rating", type=int, choices=range(1, 6))

    p_add = sub.add_parser("add", help="scrape and store one or more URLs")
    p_add.add_argument("urls", nargs="+", help="URLs, or text containing URLs")
    personal(p_add)
    p_add.add_argument("--refresh", action="store_true", help="re-scrape if already tracked")
    p_add.add_argument("--dry-run", action="store_true", help="scrape and preview, don't save")
    p_add.add_argument("--html-file", help="parse this saved HTML file instead of fetching (one URL only)")

    sub.add_parser("add-from-issue", help="add URLs found in $ISSUE_BODY (GitHub issue form)")

    p_up = sub.add_parser("update", help="change personal fields of a tracked post")
    p_up.add_argument("ref", help="id or URL")
    personal(p_up, defaults=False)

    p_rm = sub.add_parser("remove", help="delete a tracked post")
    p_rm.add_argument("ref")

    p_ls = sub.add_parser("list")
    p_ls.add_argument("--company")
    p_ls.add_argument("--source")
    p_ls.add_argument("--json", action="store_true")

    sub.add_parser("rebuild", help="regenerate README, indexes and web data")

    p_in = sub.add_parser("inspect", help="print page-structure diagnostics for a URL")
    p_in.add_argument("url")

    args = ap.parse_args(argv)

    if args.cmd == "add":
        urls = [u for chunk in args.urls for u in (URL_RE.findall(chunk) or [chunk])]
        html = Path(args.html_file).read_text(encoding="utf-8") if args.html_file else None
        return run_add(urls, company=args.company, source=args.source, tags=_tags(args.tags), notes=args.notes,
                       status=args.status, rating=args.rating, refresh=args.refresh, dry_run=args.dry_run, html=html)

    if args.cmd == "inspect":
        from .inspect_page import inspect
        inspect(args.url)
        return 0

    if args.cmd == "add-from-issue":
        f = parse_issue_form(os.environ.get("ISSUE_BODY", ""))
        source_text = f.get("blog url(s)") or f.get("blog url") or os.environ.get("ISSUE_BODY", "")
        urls = URL_RE.findall(source_text) or URL_RE.findall(os.environ.get("ISSUE_TITLE", ""))
        if not urls:
            print("no URLs found in the issue", file=sys.stderr)
            return 1
        rating = f.get("rating", "")
        status = "to-read" if "to read" in f.get("status", "").lower() else "read"
        return run_add(urls, company=f.get("company") or None, source=f.get("source") or None,
                       tags=_tags(f.get("tags")), notes=f.get("notes") or None, status=status,
                       rating=int(rating[0]) if rating[:1].isdigit() else None)

    catalog = storage.load_catalog()

    if args.cmd == "update":
        entry = _resolve(catalog, args.ref)
        old_path = storage.ROOT / entry["path"]
        for k in ("company", "source", "notes", "status", "rating"):
            if getattr(args, k) is not None:
                entry[k] = getattr(args, k)
        if args.tags is not None:
            entry["tags"] = _tags(args.tags)
        if args.status == "read" and not entry.get("read_on"):
            entry["read_on"] = storage.today()
        # Re-write the article with new front matter (and folder, if company changed).
        text = old_path.read_text(encoding="utf-8")
        content = text.split("\n---\n", 2)[-1] if text.count("\n---\n") >= 2 else text
        new_path = storage.article_path(entry)
        entry["path"] = new_path.relative_to(storage.ROOT).as_posix()
        storage.write_article(entry, content)
        if old_path != new_path and old_path.exists():
            old_path.unlink()
        print(f"✓ updated {entry['title']}")

    elif args.cmd == "remove":
        entry = _resolve(catalog, args.ref)
        (storage.ROOT / entry["path"]).unlink(missing_ok=True)
        catalog["blogs"].remove(entry)
        print(f"✓ removed {entry['title']}")

    elif args.cmd == "list":
        rows = [b for b in catalog["blogs"]
                if (not args.company or b["company"].lower() == args.company.lower())
                and (not args.source or b["source"].lower() == args.source.lower())]
        if args.json:
            print(json.dumps(rows, indent=2, ensure_ascii=False))
        for b in rows if not args.json else []:
            print(f"{b['id']}  {b.get('published') or 'undated':10}  {b['company'][:18]:18}  "
                  f"{b['source'][:18]:18}  {b['title'][:70]}")
        return 0

    storage.save_catalog(catalog)
    render.render_all(catalog)
    return 0


if __name__ == "__main__":
    sys.exit(main())
