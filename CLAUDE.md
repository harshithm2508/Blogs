# Blog Library — notes for Claude

This repo tracks blog posts the owner has read. When the user sends one or more blog links
(with or without words like "add this"), add them to the library:

1. **Preferred:** trigger the `add-blog.yml` workflow (`workflow_dispatch`) on the default branch with
   input `urls` = the link(s) separated by newlines. Pass `company`, `source`, `tags`, `notes`,
   `status` (`read`/`to-read`) or `rating` (1–5) only if the user mentioned them. Use `refresh: true`
   to re-scrape an already tracked post. The cloud sandbox usually cannot reach blog sites,
   which is why scraping runs in Actions. After triggering, check the run result and report back the
   title, company and source that were detected (see the run summary or the new commit).
2. If the sandbox *can* reach the site, `python -m tracker add <url> ...` locally then commit + push also works.

Other requests map to CLI commands: `update` (status/rating/notes/tags/company), `remove`, `list`, `rebuild`.
Run `python -m pytest -q` after changing anything in `tracker/`.

Classification rules live in `tracker/classify.py`; add a domain to `COMPANY_DOMAINS` when a company
is misdetected, then `refresh` the affected posts.
