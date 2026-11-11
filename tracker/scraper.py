"""Fetch a blog post and extract its full content + metadata."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import requests
import trafilatura
from bs4 import BeautifulSoup

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0 Safari/537.36"
)
TRACKING_PARAMS = re.compile(r"^(utm_|fbclid$|gclid$|mc_|ref$|ref_src$|source$|sk$|si$)", re.I)
WORDS_PER_MINUTE = 230


@dataclass
class Post:
    url: str
    canonical_url: str
    title: str
    author: str | None
    published: str | None  # ISO date (YYYY-MM-DD)
    sitename: str | None
    description: str | None
    image: str | None
    tags: list[str] = field(default_factory=list)
    language: str | None = None
    content_markdown: str = ""
    word_count: int = 0
    reading_minutes: int = 0
    html: str = ""


def normalize_url(url: str) -> str:
    """Strip tracking params, fragments and trailing slashes so duplicates are detected."""
    p = urlparse(url.strip())
    query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not TRACKING_PARAMS.match(k)]
    path = p.path.rstrip("/") or "/"
    host = p.netloc.lower()
    return urlunparse((p.scheme.lower() or "https", host, path, "", urlencode(query), ""))


def fetch_html(url: str, timeout: int = 30) -> tuple[str, str]:
    """Return (final_url, html)."""
    resp = requests.get(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
        timeout=timeout,
        allow_redirects=True,
    )
    resp.raise_for_status()
    if not resp.encoding or resp.encoding.lower() == "iso-8859-1":
        resp.encoding = resp.apparent_encoding
    return resp.url, resp.text


def _meta(soup: BeautifulSoup, *names: str) -> str | None:
    for name in names:
        tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        if tag and tag.get("content"):
            return tag["content"].strip()
    return None


def _json_ld(soup: BeautifulSoup) -> dict:
    """Return the first Article-like JSON-LD object, if any."""
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        items = data if isinstance(data, list) else data.get("@graph", [data]) if isinstance(data, dict) else []
        for item in items:
            if not isinstance(item, dict):
                continue
            kind = item.get("@type")
            kinds = kind if isinstance(kind, list) else [kind]
            if any(k and ("Article" in k or k in {"BlogPosting", "Posting", "Report"}) for k in kinds):
                return item
    return {}


def _ld_author(ld: dict) -> str | None:
    author = ld.get("author")
    if isinstance(author, list):
        names = [a.get("name") if isinstance(a, dict) else str(a) for a in author]
        names = [n for n in names if n]
        return ", ".join(names) or None
    if isinstance(author, dict):
        return author.get("name")
    if isinstance(author, str):
        return author
    return None


def _iso_date(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M%z"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    m = re.match(r"(\d{4}-\d{2}-\d{2})", value)
    return m.group(1) if m else None


def _clean_markdown(md: str) -> str:
    md = re.sub(r"\n{3,}", "\n\n", md)
    return md.strip() + "\n"


def _fallback_markdown(soup: BeautifulSoup) -> str:
    """Very simple extractor used when trafilatura finds nothing."""
    root = soup.find("article") or soup.find("main") or soup.body or soup
    lines: list[str] = []
    for el in root.find_all(["h1", "h2", "h3", "h4", "p", "li", "pre", "blockquote"]):
        text = el.get_text(" ", strip=True)
        if not text:
            continue
        if el.name in {"h1", "h2", "h3", "h4"}:
            lines.append("#" * int(el.name[1]) + " " + text)
        elif el.name == "li":
            lines.append("- " + text)
        elif el.name == "pre":
            lines.append("```\n" + el.get_text() + "\n```")
        elif el.name == "blockquote":
            lines.append("> " + text)
        else:
            lines.append(text)
    return "\n\n".join(lines)


def parse(html: str, url: str) -> Post:
    """Extract a Post from raw HTML."""
    soup = BeautifulSoup(html, "lxml")
    ld = _json_ld(soup)
    meta = trafilatura.extract_metadata(html, default_url=url)

    content = trafilatura.extract(
        html,
        url=url,
        output_format="markdown",
        include_images=True,
        include_links=True,
        include_tables=True,
        include_formatting=True,
        include_comments=False,
        favor_recall=True,
        deduplicate=True,
    ) or ""
    if len(content.split()) < 50:
        fallback = _fallback_markdown(soup)
        if len(fallback.split()) > len(content.split()):
            content = fallback

    canonical = None
    link = soup.find("link", rel="canonical")
    if link and link.get("href", "").startswith("http"):
        canonical = link["href"]
    canonical = canonical or _meta(soup, "og:url") or url

    title = (
        _meta(soup, "og:title", "twitter:title")
        or ld.get("headline")
        or (meta.title if meta else None)
        or (soup.title.get_text(strip=True) if soup.title else None)
        or url
    )
    author = _ld_author(ld) or (meta.author if meta else None) or _meta(soup, "author", "article:author")
    if author and author.startswith("http"):
        author = None
    published = _iso_date(
        _meta(soup, "article:published_time", "og:published_time", "datePublished", "date")
        or ld.get("datePublished")
        or (meta.date if meta else None)
    )
    sitename = _meta(soup, "og:site_name", "application-name") or (meta.sitename if meta else None)
    description = _meta(soup, "og:description", "description", "twitter:description") or (
        meta.description if meta else None
    )
    image = _meta(soup, "og:image", "twitter:image") or (meta.image if meta else None)

    tags: list[str] = []
    for t in soup.find_all("meta", attrs={"property": "article:tag"}):
        if t.get("content"):
            tags.append(t["content"].strip())
    kw = _meta(soup, "keywords", "news_keywords")
    if kw:
        tags.extend(k.strip() for k in kw.split(","))
    ld_kw = ld.get("keywords")
    if isinstance(ld_kw, list):
        tags.extend(str(k) for k in ld_kw)
    elif isinstance(ld_kw, str):
        tags.extend(k.strip() for k in ld_kw.split(","))
    if meta and meta.tags:
        tags.extend(meta.tags)
    seen: set[str] = set()
    clean_tags = []
    for t in tags:
        t = t.strip()
        if t and len(t) < 40 and t.lower() not in seen and not t.lower().startswith(("lite:", "elevated:")):
            seen.add(t.lower())
            clean_tags.append(t)

    content = _clean_markdown(content)
    words = len(re.findall(r"\w+", content))

    return Post(
        url=url,
        canonical_url=canonical,
        title=re.sub(r"\s+", " ", title).strip(),
        author=author,
        published=published,
        sitename=sitename,
        description=description,
        image=image,
        tags=clean_tags[:15],
        language=(meta.language if meta else None) or (soup.html.get("lang") if soup.html else None),
        content_markdown=content,
        word_count=words,
        reading_minutes=max(1, round(words / WORDS_PER_MINUTE)),
        html=html,
    )


def scrape(url: str) -> Post:
    final_url, html = fetch_html(url)
    return parse(html, final_url)
