"""Regenerate the README sections, per-company indexes and the web viewer data."""
from __future__ import annotations

import json
import os
import re
import subprocess
from collections import defaultdict
from pathlib import Path

from .storage import LIBRARY, ROOT, slugify

README = ROOT / "README.md"
START, END = "<!-- LIBRARY:START -->", "<!-- LIBRARY:END -->"


def _repo_slug() -> str | None:
    if os.environ.get("GITHUB_REPOSITORY"):
        return os.environ["GITHUB_REPOSITORY"]
    try:
        remote = subprocess.run(["git", "-C", str(ROOT), "remote", "get-url", "origin"],
                                capture_output=True, text=True, check=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    m = re.search(r"github\.com[:/]([^/]+/[^/.]+?)(?:\.git)?$", remote)
    if m:
        return m.group(1)
    m = re.search(r"/git/([^/]+/[^/]+?)(?:\.git)?$", remote)  # proxied remotes
    return m.group(1) if m else None


def _esc(text: str) -> str:
    return (text or "").replace("|", "\\|").replace("[", "\\[").replace("]", "\\]")


def _row(b: dict, rel_to: Path) -> str:
    local = os.path.relpath(ROOT / b["path"], rel_to).replace(os.sep, "/")
    stars = "★" * int(b["rating"]) if b.get("rating") else ""
    status = "✅" if b.get("status") == "read" else "📌"
    return (f"| {status} | [{_esc(b['title'])}]({local}) · [↗]({b['url']}) | {_esc(b.get('author') or '')} | "
            f"{_esc(b.get('publication') or '')} | {b.get('published') or '—'} | {b.get('reading_minutes') or '?'}m | {stars} |")


HEADER = "| | Title | Author | Publication | Published | Read | Rating |\n|---|---|---|---|---|---|---|"


def _table(blogs: list[dict], rel_to: Path) -> str:
    return HEADER + "\n" + "\n".join(_row(b, rel_to) for b in blogs)


def _anchor(text: str) -> str:
    a = re.sub(r"[^\w\- ]", "", text.lower()).strip().replace(" ", "-")
    return a


def render_readme(blogs: list[dict]) -> str:
    by_company: dict[str, list] = defaultdict(list)
    by_source: dict[str, list] = defaultdict(list)
    for b in blogs:
        by_company[b["company"]].append(b)
        by_source[b["source"]].append(b)

    read = sum(1 for b in blogs if b.get("status") == "read")
    minutes = sum(b.get("reading_minutes") or 0 for b in blogs if b.get("status") == "read")
    out = [
        f"**{len(blogs)}** posts tracked · **{read}** read · **{len(by_company)}** companies · "
        f"**{len(by_source)}** sources · ~**{minutes // 60}h {minutes % 60}m** of reading",
        "",
    ]
    if not blogs:
        out.append("_Nothing tracked yet. Add your first blog post (see **Adding a blog** below)._")
        return "\n".join(out)

    def order(groups):
        return sorted(groups.items(), key=lambda kv: (kv[0] == "Independent", -len(kv[1]), kv[0].lower()))

    out += ["### 🕒 Recently added", "", _table(blogs[:10], ROOT), ""]

    out += ["### 🏢 By company", ""]
    out.append(" · ".join(f"[{c} ({len(v)})](#{_anchor('company-' + c)})" for c, v in order(by_company)))
    out.append("")
    for company, items in order(by_company):
        idx = f"library/{slugify(company, 40)}/README.md"
        out += [f"<a id=\"{_anchor('company-' + company)}\"></a>",
                f"#### {company} ({len(items)}) — [folder]({idx})", "", _table(items, ROOT), ""]

    out += ["### 📚 By source", ""]
    out.append(" · ".join(f"[{s} ({len(v)})](#{_anchor('source-' + s)})" for s, v in order(by_source)))
    out.append("")
    for source, items in order(by_source):
        out += [f"<a id=\"{_anchor('source-' + source)}\"></a>",
                f"#### {source} ({len(items)})", "", _table(items, ROOT), ""]
    return "\n".join(out)


def render_company_indexes(blogs: list[dict]) -> None:
    by_company: dict[str, list] = defaultdict(list)
    for b in blogs:
        by_company[b["company"]].append(b)
    for company, items in by_company.items():
        folder = LIBRARY / slugify(company, 40)
        folder.mkdir(parents=True, exist_ok=True)
        sources = sorted({b["source"] for b in items})
        text = [f"# {company}", "", f"{len(items)} post(s) · sources: {', '.join(sources)}", "",
                _table(items, folder), "", "[← back to library](../../README.md)", ""]
        (folder / "README.md").write_text("\n".join(text), encoding="utf-8")
    # Remove indexes for companies that no longer have posts.
    if LIBRARY.exists():
        for folder in LIBRARY.iterdir():
            if folder.is_dir() and not any(p.name != "README.md" for p in folder.iterdir()):
                (folder / "README.md").unlink(missing_ok=True)
                folder.rmdir()


def render_all(catalog: dict) -> None:
    blogs = catalog["blogs"]
    render_company_indexes(blogs)
    text = README.read_text(encoding="utf-8") if README.exists() else f"# Blog Library\n\n{START}\n{END}\n"
    if START not in text:
        text += f"\n{START}\n{END}\n"
    pre, rest = text.split(START, 1)
    _, post = rest.split(END, 1)
    README.write_text(f"{pre}{START}\n{render_readme(blogs)}\n{END}{post}", encoding="utf-8")
