import json
from pathlib import Path

import pytest

from tracker import classify, cli, render, scraper, storage

FIXTURE = Path(__file__).parent / "fixtures" / "medium_company_post.html"


@pytest.fixture()
def tmp_repo(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "ROOT", tmp_path)
    monkeypatch.setattr(storage, "DATA_FILE", tmp_path / "data" / "blogs.json")
    monkeypatch.setattr(storage, "LIBRARY", tmp_path / "library")
    monkeypatch.setattr(render, "ROOT", tmp_path)
    monkeypatch.setattr(render, "LIBRARY", tmp_path / "library")
    monkeypatch.setattr(render, "README", tmp_path / "README.md")
    (tmp_path / "README.md").write_text("# Lib\n\n<!-- LIBRARY:START -->\n<!-- LIBRARY:END -->\n\nfooter\n")
    return tmp_path


def test_normalize_url_strips_tracking():
    assert scraper.normalize_url("https://Example.com/post/?utm_source=x&id=2#top") == "https://example.com/post?id=2"


@pytest.mark.parametrize("url,company,source", [
    ("https://netflixtechblog.com/x-123", "Netflix", "Medium"),
    ("https://www.uber.com/en-IN/blog/some-post/", "Uber", "Company Blog"),
    ("https://medium.com/airbnb-engineering/post-1", "Airbnb", "Medium"),
    ("https://medium.com/@someone/my-post-1", "Independent", "Medium"),
    ("https://newsletter.pragmaticengineer.substack.com/p/x", "Independent", "Substack"),
    ("https://engineering.acme-corp.com/post", "Acme Corp", "Company Blog"),
    ("https://jvns.ca/blog/2024/post/", "Jvns", "Company Blog"),
    ("https://danluu.com/post/", "Independent", "Personal / Independent Site"),
    ("https://dev.to/someone/post", "Independent", "Dev.to"),
])
def test_classify(url, company, source):
    html = '<meta property="al:android:package" content="com.medium.reader">' if "netflix" in url else ""
    r = classify.classify(url, html)
    assert (r["company"], r["source"]) == (company, source)


def test_parse_fixture():
    post = scraper.parse(FIXTURE.read_text(), "https://netflixtechblog.com/scaling-event-pipelines-abc123")
    assert post.title == "Scaling Event Pipelines to Trillions of Events"
    assert post.author == "Jane Doe"
    assert post.published == "2025-03-14"
    assert "Kafka" in post.tags
    assert "## The new architecture" in post.content_markdown or "The new architecture" in post.content_markdown
    assert "Consumer lag dropped" in post.content_markdown
    assert "Sign in" not in post.content_markdown
    assert post.word_count > 100


def test_add_update_remove_flow(tmp_repo):
    url = "https://netflixtechblog.com/scaling-event-pipelines-abc123?utm_source=tw"
    html = FIXTURE.read_text()
    catalog = storage.load_catalog()
    res = cli.add_url(catalog, url, html=html, tags=["streaming"], notes="Great read", rating=5)
    assert res["status"] == "added"
    e = res["entry"]
    assert e["company"] == "Netflix" and e["source"] == "Medium"
    assert e["path"].startswith("library/netflix/2025-03-14-scaling-event-pipelines")
    assert "streaming" in e["tags"] and "Kafka" in e["tags"]

    assert cli.add_url(catalog, url, html=html)["status"] == "duplicate"
    storage.save_catalog(catalog)
    render.render_all(catalog)

    article = (tmp_repo / e["path"]).read_text()
    assert article.startswith("---\nid: ")
    assert "## My notes" in article and "Consumer lag dropped" in article
    readme = (tmp_repo / "README.md").read_text()
    assert "By company" in readme and "Netflix (1)" in readme and readme.rstrip().endswith("footer")
    assert (tmp_repo / "library" / "netflix" / "README.md").exists()
    assert json.loads((tmp_repo / "data" / "blogs.json").read_text())["blogs"][0]["id"] == e["id"]

    # refresh keeps personal fields
    res = cli.add_url(catalog, url, html=html, refresh=True)
    assert res["status"] == "updated" and res["entry"]["rating"] == 5 and res["entry"]["notes"] == "Great read"

    storage.save_catalog(catalog)
    assert cli.main(["update", e["id"], "--company", "Netflix Data", "--status", "to-read"]) == 0
    moved = storage.load_catalog()["blogs"][0]
    assert moved["path"].startswith("library/netflix-data/") and (tmp_repo / moved["path"]).exists()
    assert not (tmp_repo / "library" / "netflix").exists()
    assert "Consumer lag dropped" in (tmp_repo / moved["path"]).read_text()

    assert cli.main(["remove", e["id"]]) == 0
    assert storage.load_catalog()["blogs"] == []


def test_issue_form_parsing():
    body = "### Blog URL(s)\n\nhttps://a.com/x\nhttps://b.com/y\n\n### Company\n\n_No response_\n\n### Rating\n\n4 ★★★★\n"
    f = cli.parse_issue_form(body)
    assert cli.URL_RE.findall(f["blog url(s)"]) == ["https://a.com/x", "https://b.com/y"]
    assert f["company"] == "" and f["rating"].startswith("4")


SECTIONED = Path(__file__).parent / "fixtures" / "sectioned_div_post.html"


def test_restores_headings_dropped_by_extractor():
    """Layout that makes trafilatura fall back to its heading-less 'wild text' rescue (seen on databricks.com)."""
    post = scraper.parse(SECTIONED.read_text(), "https://www.acme.com/blog/what-is-widget-ingestion")
    headings = [l for l in post.content_markdown.splitlines() if l.startswith("#")]
    assert headings[-3:] == ["### Ingestion methods", "### Benefits", "### Challenges"]
    md = post.content_markdown
    # each heading sits right before its own section text
    assert md.index("### Benefits") < md.index("Scalability ipsum") < md.index("### Challenges") < md.index("Challenges ipsum")


def test_strips_promos_and_subscribe_boxes():
    md = scraper.parse(SECTIONED.read_text(), "https://www.acme.com/blog/x").content_markdown
    assert "playbook" not in md and "REPORT" not in md
    assert "Subscribe" not in md and "latest posts" not in md
    assert "Quality ipsum" in md  # last real paragraph kept


def test_date_falls_through_unparseable_meta():
    # article:published_time is "Mon, 05/12/2025 - 23:24"; JSON-LD has the ISO date
    assert scraper.parse(SECTIONED.read_text(), "https://www.acme.com/blog/x").published == "2025-05-12"
    assert scraper._iso_date("Mon, 05/12/2025 - 23:24") == "2025-05-12"
    assert scraper._iso_date("2025-05-12T23:24:18+0000") == "2025-05-12"


def test_restore_headings_ignores_unrelated_headings():
    from tracker import cleanup
    html = "<h2>Sidebar</h2><p>Not part of the article at all, just a sidebar blurb.</p><h2>Real</h2><p>This paragraph is in the article body.</p>"
    md = "This paragraph is in the article body."
    assert cleanup.restore_headings(md, html) == "## Real\n\nThis paragraph is in the article body."


def test_restore_headings_skips_link_boxes():
    from tracker import cleanup
    html = ("<h2>Here's more to explore</h2><div><a href='/a'>Some related article title here</a></div>"
            "<p>The real section text starts here.</p>")
    md = "The real section text starts here."
    assert cleanup.restore_headings(md, html) == md
