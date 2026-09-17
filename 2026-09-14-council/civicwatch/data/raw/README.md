# Raw PDFs live on the `archive/raw-pdfs` branch

All 1,310 packet PDFs (51 meetings, Jan 2025 – Sep 2026, ~2.9 GB) are committed to GitHub on branch
**`archive/raw-pdfs`** — nothing was deleted. They're kept off `main` only so Streamlit Cloud (1 GB clone
limit) can boot the site. `civic.db` + `data/text/` on `main` contain every page's text, so the tools work without them.

Get the PDFs back into this folder:

    git fetch origin archive/raw-pdfs
    git checkout origin/archive/raw-pdfs -- 2026-09-14-council/civicwatch/data/raw

Or a single meeting dir:

    git checkout origin/archive/raw-pdfs -- 2026-09-14-council/civicwatch/data/raw/2026-09-21_1443

New crawls: run `civicwatch.py crawl`, then push `data/raw/` to `archive/raw-pdfs`, not `main`
(`git push origin HEAD:archive/raw-pdfs` from a checkout of that branch, or use `publish.sh`).
