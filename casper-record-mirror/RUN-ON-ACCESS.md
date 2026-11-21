# Run the Casper, WY mirror on the Casper-only repo

**Status: pending** — the session that staged this mirror had read-only access
to the Casper repo (`bartimoussmith-oss/casper-record-mirror`), so the crawler
and the workflow were staged into THIS repo instead of being pushed to it.
When you start a new Arena session and have **write access** to the Casper
repo, follow these steps.

> Do not attempt the crawl from a sandbox that cannot push to the repo. The
> workflow needs to exist on the Casper repo's `main` branch first.

## Prerequisite

Confirm write access to the repo, e.g.:

```bash
gh api /repos/bartimoussmith-oss/casper-record-mirror --jq '.permissions.push'
```

If that returns `true`, Continue. If it returns `false`/`null`, **stop and report** —
the user must grant the sandbox's GitHub integration write access to the repo
(e.g. by re-granting the Arena ↔ GitHub connection or by pushing from their own
credentials). Do not push anything to any other repo in order to work around the
sandbox's permission boundary.

## Pre-check: does the repo exist?

```bash
gh repo view bartimoussmith-oss/casper-record-mirror
```

- **Exists** (it is expected to exist — the owner created it with an auto-init
  README): use it as-is.
- **Missing**: create it public, empty (no auto-init README):
  `gh repo create bartimoussmith-oss/casper-record-mirror --public`

## Steps

1. Clone or reuse the Casper mirror repo:
   `git clone https://github.com/bartimoussmith-oss/casper-record-mirror.git`
2. Copy these files into the Casper repo root (from `casper-record-mirror/` in
   THIS repo):
   - `collect.py`
   - `.github/workflows/collect.yml`
   - `.gitignore`
   - `README.md`
3. **Merge, don't overwrite:** the Casper repo may contain an auto-init
   `README.md` (e.g. the "Initial commit" with a one-line description). Keep
   its first line/title; append the mirror documentation below it.
4. Commit and push to `main`:
   `git add -A && git commit -m "Add politeness-aware Casper WY crawler and workflow" && git push -u origin main`
5. Confirm the workflow file is on `main`:
   `gh api /repos/bartimoussmith-oss/casper-record-mirror/contents/.github/workflows/collect.yml --jq '.sha'`
6. Fire the crawl:
   `gh workflow run collect.yml`  (or take the Actions tab: `Archive Casper WY documents → Run workflow`)
7. Watch the run (may take ~15–40 minutes — roughly a hundred+ documents,
   ≥ 3 s apart):
   `gh run list --repo bartimoussmith-oss/casper-record-mirror --workflow collect.yml --limit 5`
   then
   `gh run watch <run id>`
8. Once the run completes, verify:
   - `documents/` is committed and populated,
   - `manifest.json` lists archived entries with SHA-256,
   - `MANIFEST.md` shows the coverage summary (sitemap entries / documents
     discovered / failed / oversized).
9. Report the outcome (counts, total MiB, failures, oversized files) to the user.
   If the run times out or fails partway, re-dispatch — the crawler is
   idempotent and resumes from `manifest.json`.

## Politeness (do not weaken)

- The crawler reads and honors `robots.txt` (no `Disallow` for the site, but
  keep it; full `crawl-delay` support is wired in).
- It waits ≥ 3 seconds per request (and honors the site's `crawl-delay`).
- It collects public documents only — no media/images, no HTML pages — and it
  uses a custom `User-Agent`.
- Do not add concurrency or lower the delay to finish faster. Use
  `--max-new` or a `workflow_dispatch` re-run instead.
- The workflow is manual-only by design (no schedule).

## Known limits

- Per-file cap: 50 MiB. Files over that are recorded as `oversized` with the
  reason; the manifest never silently drops anything.
- Crawl duration depends on how many documents the site publishes (largest
  sitemap chunk had ~900 entries; document entries are far fewer). Expect
  tens to a few hundred documents, roughly 15–40 minutes in Actions.
- The sitemap is authoritative and re-fetched every run; the headline
  city-council documents page is kept explicit so its documents are archived
  even if the sitemap misses them.
