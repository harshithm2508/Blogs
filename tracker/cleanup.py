"""Post-processing that makes extraction more faithful across sites.

- strip_clutter(): remove ads, promos, subscribe boxes etc. from the HTML before extraction.
- restore_headings(): put back section headings that the extractor dropped.
- trim_tail(): drop "subscribe to our newsletter"-style lines left at the end.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup, Tag

CLUTTER_TOKEN = re.compile(
    r"(^|[-_])(subscribe|subscription|newsletter|promo|promotion|cta|advert|advertisement|ads?|sponsor(ed)?|"
    r"related|recommended|share|sharing|social|cookie|popup|modal|signup|sign-up|banner|callout-card|"
    r"author-bio|comments?|breadcrumbs?|toc|table-of-contents|pagination)([-_]|$)",
    re.I,
)
HEADINGS = ("h1", "h2", "h3", "h4", "h5", "h6")
BLOCKS = ("p", "li", "pre", "blockquote", "td", "figcaption", "dd")
TAIL_JUNK = re.compile(
    r"(subscribe|sign up|newsletter|get the latest posts|follow us|share this|related posts|"
    r"you might also like|read more articles|never miss a)", re.I)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _plain_md(line: str) -> str:
    """Markdown line -> comparable plain text."""
    line = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", line)       # images
    line = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", line)     # links -> text
    line = re.sub(r"^\s*(#+|[-*+]|\d+[.)]|>)\s*", "", line)  # block markers
    line = re.sub(r"[*_`~]", "", line)
    return _norm(line)


def strip_clutter(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    body = soup.body or soup
    total = len(body.get_text(" ", strip=True)) or 1
    for el in body.find_all(True):
        if not isinstance(el, Tag) or el.decomposed or el.name in ("html", "body"):
            continue
        attrs = " ".join((el.get("class") or []) + [el.get("id") or "", el.get("role") or "",
                                                      el.get("data-component") or ""])
        tokens = re.split(r"\s+", attrs)
        if el.name in ("aside", "form", "iframe") or el.get("aria-hidden") == "true" or \
                any(CLUTTER_TOKEN.search(t) for t in tokens if t):
            # Never remove something that holds a big share of the page's text (likely the article).
            if len(el.get_text(" ", strip=True)) < 0.25 * total:
                el.decompose()
    return str(soup)


def restore_headings(markdown: str, html: str) -> str:
    """Insert headings from the HTML before the extracted block that follows them on the page."""
    soup = BeautifulSoup(html, "lxml")
    lines = markdown.splitlines()
    plain = [_plain_md(l) for l in lines]
    present = {p for l, p in zip(lines, plain) if l.lstrip().startswith("#")}

    inserts: list[tuple[int, str]] = []
    last_idx = -1
    for h in soup.find_all(HEADINGS):
        title = re.sub(r"\s+", " ", h.get_text(" ", strip=True)).strip(" #¶🔗")
        key = _norm(title)
        if not key or len(key) > 150 or key in present:
            continue
        # First substantial block after the heading (stop if another heading comes first).
        nxt = None
        for el in h.find_all_next(HEADINGS + BLOCKS + ("a",)):
            if el.name in HEADINGS:
                break
            if h in el.parents:
                continue
            text = _norm(el.get_text(" ", strip=True))
            if el.name == "a":
                if len(text) >= 15:  # heading labels a box of links ("Related", "More to explore"), not prose
                    break
                continue
            if len(text) >= 15:
                nxt = text[:60]
                break
        if not nxt:
            continue
        for i in range(last_idx + 1, len(lines)):
            if plain[i] and (plain[i].startswith(nxt) or (len(plain[i]) >= 15 and nxt.startswith(plain[i][:60]))):
                level = int(h.name[1])
                inserts.append((i, "#" * max(2, min(level, 4)) + " " + title))
                present.add(key)
                last_idx = i
                break
    for i, heading in reversed(inserts):
        lines[i:i] = [heading, ""] if i == 0 or not lines[i - 1].strip() else ["", heading, ""]
    return "\n".join(lines)


def trim_tail(markdown: str) -> str:
    lines = markdown.rstrip().splitlines()
    while lines:
        last = lines[-1].strip()
        if not last or (len(last) < 200 and TAIL_JUNK.search(last)):
            lines.pop()
        else:
            break
    return "\n".join(lines)
