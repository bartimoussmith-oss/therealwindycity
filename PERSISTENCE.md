# Persistence & Access — how this engine lives beyond one session

## What persists where (plain truth)

| Thing | Survives this sandbox session? | Why |
|---|---|---|
| All code, config, data (`civic-engine/`) | **Yes** | Files under `/home/user` persist across sessions |
| The live dashboard URL (preview proxy) | While the sandbox process runs | It's a live process, not a static site |
| Background scheduler process | While the sandbox process runs | Same reason |
| Installed Python packages (pdfplumber/streamlit) | **Maybe not** | Package caches aren't part of the saved snapshot — reinstall is one command: `pip install pdfplumber streamlit` (core engine works without them) |

If the link ever 404s: relaunch with
`python3 -m streamlit run dashboard/app.py --server.address 0.0.0.0 --server.port 8788 --server.headless true --server.enableCORS false --server.enableXsrfProtection false --browser.gatherUsageStats false`
and `python3 -u engine/scheduler.py --hours 6 >> data/scheduler.log 2>&1`.

## For something that truly outlives this environment

The durable state is one folder. Two supported paths — **no Google credentials ever enter this workspace; you keep custody of your accounts:**

**Option A — Your own machine or a $5 VPS (recommended for a watchdog):**
```bash
tar czf civic-engine-export.tar.gz civic-engine    # bundle already made in /home/user
# scp it anywhere, then on that machine, a crontab line:
# 15 */6 * * * cd /path/to/civic-engine && python3 run.py crawl && python3 run.py work && python3 run.py digest --days 1
```
Core crawl/digest needs Python 3.10+ stdlib only; `pip install pdfplumber streamlit` adds PDFs + dashboard.

**Option B — GitHub (free hosting of the *report*, not just the code):**
Push the repo; put `data/out/digest-*.md` under a `docs/` folder and enable GitHub Pages, and every digest becomes a public, permanent URL. Pair with GitHub Actions (cron schedule) for a fully hosted daily run — the daily runner costs $0 on the free tier for this workload.

**Option C — Google Drive / Dropbox:** upload `civic-engine-export.tar.gz` (or the whole folder) from your own browser/client. It's a static snapshot; automation still needs one of the above to *run* somewhere.

## The daily loop (if you do nothing else)

`engine/scheduler.py --hours 6` performs: polite crawl → queue drain (extract +
silent-edit diff) → digest write. Every artifact lands in `data/out/` as
Markdown with source URLs, fetch timestamps, and verbatim quotes — which is the
whole point: evidence you can hand a journalist without explanation.
