"""Print diagnostics about how a page is structured (used to debug extraction)."""
from __future__ import annotations

import re

from bs4 import BeautifulSoup, Tag

from . import scraper


def _path(el: Tag, depth: int = 6) -> str:
    parts = []
    for parent in [el, *el.parents][:depth]:
        if not isinstance(parent, Tag) or parent.name in ("[document]", "html"):
            break
        cls = ".".join((parent.get("class") or [])[:3])
        ident = f"#{parent['id']}" if parent.get("id") else ""
        parts.append(f"{parent.name}{ident}{'.' + cls if cls else ''}")
    return " < ".join(parts)


def inspect(url: str) -> None:
    final_url, html = scraper.fetch_html(url)
    soup = BeautifulSoup(html, "lxml")
    print(f"URL: {final_url}\nHTML size: {len(html)} chars\n")

    print("== date-like metadata ==")
    for m in soup.find_all("meta"):
        key = m.get("property") or m.get("name") or m.get("itemprop") or ""
        if re.search(r"date|time|publish|modified", key, re.I):
            print(f"  meta {key} = {m.get('content')}")
    for t in soup.find_all("time")[:5]:
        print(f"  <time datetime={t.get('datetime')!r}> {t.get_text(strip=True)[:60]!r}  [{_path(t, 3)}]")
    ld = scraper._json_ld(soup)
    for k in ("datePublished", "dateCreated", "dateModified"):
        if k in ld:
            print(f"  json-ld {k} = {ld[k]}")

    print("\n== headings ==")
    for h in soup.find_all(["h1", "h2", "h3", "h4"]):
        text = h.get_text(" ", strip=True)
        if text:
            print(f"  {h.name}: {text[:80]!r}\n      path: {_path(h)}")
    first = soup.find("h2")
    if first:
        print("\n== first h2 outer HTML (and parent) ==")
        print("  " + str(first)[:600])
        print("  parent: " + str(first.parent)[:900])

    post = scraper.parse(html, final_url)
    print("\n== extracted markdown headings ==")
    for line in post.content_markdown.splitlines():
        if line.startswith("#"):
            print("  " + line)
    print(f"\nwords={post.word_count}  published={post.published}")
