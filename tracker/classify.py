"""Work out which *company* a blog post belongs to and which *source* (platform) published it.

- company: the organisation behind the post (Netflix, Uber, Stripe ...) or "Independent".
- source:  the platform / kind of outlet (Company Blog, Medium, Substack, Dev.to ...).
- publication: the human-readable name of the specific blog ("Netflix TechBlog").
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

# Domain (or domain suffix) -> company. Extend freely.
COMPANY_DOMAINS: dict[str, str] = {
    "netflixtechblog.com": "Netflix",
    "netflix.com": "Netflix",
    "uber.com": "Uber",
    "eng.uber.com": "Uber",
    "airbnb.io": "Airbnb",
    "airbnb.tech": "Airbnb",
    "engineering.fb.com": "Meta",
    "ai.meta.com": "Meta",
    "about.fb.com": "Meta",
    "research.google": "Google",
    "blog.google": "Google",
    "developers.googleblog.com": "Google",
    "cloud.google.com": "Google",
    "ai.googleblog.com": "Google",
    "deepmind.google": "Google DeepMind",
    "aws.amazon.com": "Amazon",
    "amazon.science": "Amazon",
    "allthingsdistributed.com": "Amazon",
    "microsoft.com": "Microsoft",
    "devblogs.microsoft.com": "Microsoft",
    "apple.com": "Apple",
    "machinelearning.apple.com": "Apple",
    "blog.cloudflare.com": "Cloudflare",
    "stripe.com": "Stripe",
    "discord.com": "Discord",
    "slack.engineering": "Slack",
    "engineering.atspotify.com": "Spotify",
    "engineering.linkedin.com": "LinkedIn",
    "linkedin.com": "LinkedIn",
    "medium.com/pinterest-engineering": "Pinterest",
    "dropbox.tech": "Dropbox",
    "shopify.engineering": "Shopify",
    "github.blog": "GitHub",
    "gitlab.com": "GitLab",
    "engineering.atlassian.com": "Atlassian",
    "atlassian.com": "Atlassian",
    "blog.twitter.com": "X (Twitter)",
    "blog.x.com": "X (Twitter)",
    "engineering.zalando.com": "Zalando",
    "doordash.engineering": "DoorDash",
    "careersatdoordash.com": "DoorDash",
    "instacart.com": "Instacart",
    "tech.instacart.com": "Instacart",
    "lyft.com": "Lyft",
    "eng.lyft.com": "Lyft",
    "engineering.grab.com": "Grab",
    "engineering.razorpay.com": "Razorpay",
    "blog.swiggy.com": "Swiggy",
    "bytes.swiggy.com": "Swiggy",
    "blog.zomato.com": "Zomato",
    "tech.flipkart.com": "Flipkart",
    "blog.flipkart.tech": "Flipkart",
    "engineering.salesforce.com": "Salesforce",
    "engineering.squarespace.com": "Squarespace",
    "figma.com": "Figma",
    "notion.so": "Notion",
    "notion.com": "Notion",
    "vercel.com": "Vercel",
    "databricks.com": "Databricks",
    "snowflake.com": "Snowflake",
    "confluent.io": "Confluent",
    "mongodb.com": "MongoDB",
    "redis.io": "Redis",
    "elastic.co": "Elastic",
    "hashicorp.com": "HashiCorp",
    "datadoghq.com": "Datadog",
    "openai.com": "OpenAI",
    "anthropic.com": "Anthropic",
    "huggingface.co": "Hugging Face",
    "nvidia.com": "NVIDIA",
    "developer.nvidia.com": "NVIDIA",
    "engineering.monzo.com": "Monzo",
    "monzo.com": "Monzo",
    "booking.com": "Booking.com",
    "blog.booking.com": "Booking.com",
    "engineering.wix.com": "Wix",
    "tech.ebayinc.com": "eBay",
    "engineering.zoom.us": "Zoom",
    "blog.duolingo.com": "Duolingo",
    "canva.dev": "Canva",
    "engineering.canva.com": "Canva",
    "jane-street.com": "Jane Street",
    "blog.janestreet.com": "Jane Street",
    "fly.io": "Fly.io",
    "tailscale.com": "Tailscale",
    "planetscale.com": "PlanetScale",
    "supabase.com": "Supabase",
}

# Medium publications that belong to a company (medium.com/<publication>/...).
MEDIUM_PUBLICATIONS: dict[str, str] = {
    "airbnb-engineering": "Airbnb",
    "pinterest-engineering": "Pinterest",
    "netflix-techblog": "Netflix",
    "paypal-tech": "PayPal",
    "paypal-engineering": "PayPal",
    "walmartglobaltech": "Walmart",
    "expedia-group-tech": "Expedia",
    "lyft-engineering": "Lyft",
    "twitch-engineering": "Twitch",
    "agoda-engineering": "Agoda",
    "zendesk-engineering": "Zendesk",
    "groupon-eng": "Groupon",
    "myntra-engineering": "Myntra",
    "swiggy-bytes": "Swiggy",
    "flipkart-tech-blog": "Flipkart",
    "meesho-tech": "Meesho",
    "cred-club": "CRED",
    "the-atlassian-tech-blog": "Atlassian",
    "adobetech": "Adobe",
    "salesforce-engineering": "Salesforce",
    "tinder": "Tinder",
    "coinbase": "Coinbase",
    "tech-at-instacart": "Instacart",
    "ssense-tech": "SSENSE",
    "data-science-at-microsoft": "Microsoft",
    "google-cloud": "Google",
    "tensorflow": "Google",
}

PLATFORM_DOMAINS: dict[str, str] = {
    "medium.com": "Medium",
    "substack.com": "Substack",
    "dev.to": "Dev.to",
    "hashnode.dev": "Hashnode",
    "hashnode.com": "Hashnode",
    "blogspot.com": "Blogger",
    "wordpress.com": "WordPress",
    "ghost.io": "Ghost",
    "github.io": "GitHub Pages",
    "hackernoon.com": "HackerNoon",
    "towardsdatascience.com": "Medium",
    "betterprogramming.pub": "Medium",
    "levelup.gitconnected.com": "Medium",
    "javascript.plainenglish.io": "Medium",
    "infoq.com": "InfoQ",
    "freecodecamp.org": "freeCodeCamp",
    "dzone.com": "DZone",
    "linkedin.com/pulse": "LinkedIn Articles",
    "notion.site": "Notion",
}

# Platforms whose posts are usually by individuals rather than a company.
COMMUNITY_PLATFORMS = {
    "Medium", "Substack", "Dev.to", "Hashnode", "Blogger", "WordPress", "Ghost",
    "GitHub Pages", "HackerNoon", "freeCodeCamp", "DZone", "LinkedIn Articles", "Notion", "InfoQ",
}


def _host(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _match_domain(url: str, table: dict[str, str]) -> str | None:
    host = _host(url)
    path = urlparse(url).path.lower()
    # Longest key first so "medium.com/pinterest-engineering" beats "medium.com".
    for key in sorted(table, key=len, reverse=True):
        kdomain, _, kpath = key.partition("/")
        if host == kdomain or host.endswith("." + kdomain):
            if not kpath or path.lstrip("/").startswith(kpath):
                return table[key]
    return None


def detect_platform(url: str, html: str) -> str | None:
    """Detect the publishing platform from the URL or tell-tale markup."""
    hit = _match_domain(url, PLATFORM_DOMAINS)
    if hit:
        return hit
    low = html.lower()
    if "com.medium.reader" in low or "cdn-client.medium.com" in low or "miro.medium.com" in low:
        return "Medium"
    if "substackcdn.com" in low or 'content="substack"' in low:
        return "Substack"
    if "cdn.hashnode.com" in low:
        return "Hashnode"
    m = re.search(r'<meta[^>]+name=["\']generator["\'][^>]+content=["\']([^"\']+)', html, re.I)
    if m:
        gen = m.group(1).lower()
        for needle, name in (("ghost", "Ghost"), ("wordpress", "WordPress"), ("blogger", "Blogger"),
                             ("hugo", "Hugo"), ("jekyll", "Jekyll"), ("gatsby", "Gatsby"),
                             ("docusaurus", "Docusaurus"), ("astro", "Astro"), ("next.js", "Next.js")):
            if needle in gen:
                return name
    return None


def _pretty_domain(url: str) -> str:
    host = _host(url)
    parts = host.split(".")
    # drop common blog-ish sub-domains
    while len(parts) > 2 and parts[0] in {"blog", "blogs", "engineering", "eng", "tech", "dev", "developers", "www"}:
        parts = parts[1:]
    core = parts[-2] if len(parts) >= 2 else parts[0]
    return core.replace("-", " ").title()


def classify(url: str, html: str, sitename: str | None = None, author: str | None = None) -> dict:
    """Return {"company", "source", "publication"} for a post."""
    platform = detect_platform(url, html)
    company = _match_domain(url, COMPANY_DOMAINS)

    host = _host(url)
    path_parts = [p for p in urlparse(url).path.split("/") if p]
    if not company and host.endswith("medium.com") and path_parts:
        pub = path_parts[0].lower()
        company = MEDIUM_PUBLICATIONS.get(pub)

    publication = (sitename or "").strip() or None

    if company:
        source = platform if platform in COMMUNITY_PLATFORMS else "Company Blog"
    elif platform in COMMUNITY_PLATFORMS:
        source = platform
        company = "Independent"
        if not publication:
            if host.endswith("substack.com"):
                publication = host.split(".")[0].replace("-", " ").title()
            elif host.endswith("medium.com") and path_parts and not path_parts[0].startswith("@"):
                publication = path_parts[0].replace("-", " ").title()
            elif author:
                publication = author
    else:
        # A standalone site: an unknown company blog or a personal site.
        sub = host.split(".")[0] if host.count(".") >= 2 else ""
        first_path = path_parts[0].lower() if path_parts else ""
        looks_corporate = sub in {"engineering", "eng", "tech", "blog", "blogs", "dev", "developers",
                                  "developer", "techblog", "research", "labs", "ai"} or \
            first_path in {"blog", "blogs", "engineering", "eng", "tech", "tech-blog", "research", "newsroom"}
        if looks_corporate:
            source = "Company Blog"
            company = _pretty_domain(url)
        else:
            source = "Personal / Independent Site"
            company = "Independent"
        if publication is None:
            publication = _pretty_domain(url)

    return {
        "company": company,
        "source": source,
        "publication": publication or _pretty_domain(url),
        "platform": platform,
    }
