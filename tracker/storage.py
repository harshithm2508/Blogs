"""Persist posts as Markdown files + a JSON catalogue."""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "data" / "blogs.json"
LIBRARY = ROOT / "library"


def slugify(text: str, max_len: int = 70) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return (text[:max_len].rstrip("-")) or "untitled"


def post_id(normalized_url: str) -> str:
    return hashlib.sha1(normalized_url.encode()).hexdigest()[:12]


def load_catalog() -> dict:
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    return {"version": 1, "blogs": []}


def save_catalog(catalog: dict) -> None:
    from .render import _repo_slug  # local import to avoid a cycle
    catalog["repo"] = _repo_slug() or catalog.get("repo")
    catalog["blogs"].sort(key=lambda b: (b.get("added") or "", b.get("published") or ""), reverse=True)
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def find(catalog: dict, pid: str) -> dict | None:
    return next((b for b in catalog["blogs"] if b["id"] == pid), None)


def article_path(entry: dict) -> Path:
    prefix = entry.get("published") or "undated"
    return LIBRARY / slugify(entry["company"], 40) / f"{prefix}-{slugify(entry['title'])}.md"


def write_article(entry: dict, content_markdown: str) -> Path:
    path = article_path(entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    front = {k: entry.get(k) for k in (
        "id", "title", "url", "canonical_url", "author", "published", "company", "source",
        "publication", "platform", "tags", "status", "rating", "added", "read_on",
        "word_count", "reading_minutes", "image", "description", "notes",
    ) if entry.get(k) not in (None, "", [])}
    header = yaml.safe_dump(front, sort_keys=False, allow_unicode=True, width=1000).strip()
    meta_line = " · ".join(x for x in (
        entry.get("author"),
        entry.get("publication"),
        entry.get("published"),
        f"{entry.get('reading_minutes')} min read" if entry.get("reading_minutes") else None,
    ) if x)
    body = [
        "---", header, "---", "",
        f"# {entry['title']}", "",
        f"> {meta_line}  ", f"> Original: <{entry['url']}>", "",
    ]
    if entry.get("notes"):
        body += ["## My notes", "", entry["notes"], ""]
    content = content_markdown.strip()
    first, _, rest = content.partition("\n")
    if first.lstrip("# ").strip().lower() == entry["title"].strip().lower():
        content = rest.strip()  # avoid repeating the title heading
    body += ["---", "", content, ""]
    path.write_text("\n".join(body), encoding="utf-8")
    return path


def today() -> str:
    return date.today().isoformat()


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
