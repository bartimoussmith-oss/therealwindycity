# casper-record-mirror

Archive of publicly accessible Casper, Wyoming municipal documents from casperwy.gov, with a sitemap-driven collection workflow and provenance manifests.

This is a **public-records mirror**, not an official City of Casper site. Every
file here was published on [casperwy.gov](https://www.casperwy.gov) for the public,
and is archived with its source URL, download time and SHA-256 hash so a reader
can verify provenance. Not affiliated with the City of Casper.

## What is in this repo

- `documents/` — every document found on the site, path-preserved, hashed.
- `manifest.json` — machine-readable provenance for each archived file.
- `MANIFEST.md` — human-readable coverage summary generated on each run.
- `collect.py` — the polite crawler (robots.txt-aware, custom UA, ≥3 s between
  hits, documents only). Re-run with `workflow_dispatch`.

## Politeness contract

This is a municipal site. The crawler:

- reads and honors `robots.txt` before touching anything;
- identifies itself with a custom `User-Agent`;
- waits at least 3 seconds between requests to `casperwy.gov` (and honors any
  `crawl-delay` the site declares);
- collects public documents only — no media, no images, no HTML pages;
- is resumable and idempotent (documents already in `manifest.json` are skipped).

## Coverage

Run `MANIFEST.md` to see the current count and which buckets are fully
archived. Documents that fail or exceed 50 MiB are recorded as failed/oversized
with the reason; nothing is silently dropped.

## How it runs

The workflow in `.github/workflows/collect.yml` is manual-only
(`workflow_dispatch`). It:

1. fetches `robots.txt` and the sitemap,
2. enumerates every document URL anywhere on the site plus the links on the
   city council documents page,
3. downloads them politely, writing files and manifest entries,
4. commits the changes back to `main`.

Re-dispatch it to pick up new publications.

## Source

- **Site:** https://www.casperwy.gov
- **Sitemap:** https://www.casperwy.gov/sitemap.xml
- **Documents page:** https://www.casperwy.gov/government/city_council/documents.php

## License

Content is a mirror of public records published by the City of Casper, WY.
No claim of endorsement by the City. Use freely for inspection and accountability;
re-publish specific documents from their original source for citation.
