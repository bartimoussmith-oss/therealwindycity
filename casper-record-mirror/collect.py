#!/usr/bin/env python3
"""Polite archiver for the City of Casper, WY official website.

What it does, end to end:
  1. Fetches robots.txt and parses it (honors Disallow and crawl-delay).
  2. Fetches the sitemap and walks it.
  3. Collects every document URL (PDF/DOC/DOCX/RTF/XLS/XLSX/PPT/PPTX/ODT/TXT/CSV)
     anywhere on the site, plus the documents listed on the city-council
     documents page (kept explicit as a headline target).
  4. Downloads each document with polite pacing, writes it under documents/
     preserving the original path structure, hashes it (SHA-256) and records
     full provenance in manifest.json.
  5. Writes MANIFEST.md with a human-readable coverage summary.

Idempotent: documents already recorded in manifest.json are skipped, so a
re-run can pick up only what is new.

Politeness contract:
  * identifies itself with a custom User-Agent;
  * waits at least --delay seconds between requests per host, and at least the
    site's own crawl-delay when it declares one;
  * documents only -- no media, no HTML pages;
  * honors robots.txt;
  * all documents are public, published by a town government for the public.

Nothing is sent anywhere and no credentials are stored. The manifest is the
only source of record for what is archived and where it comes from.

Usage:
  python3 collect.py                 # full run (sitemap + headline page)
  python3 collect.py --dry-run       # list URLs without downloading anything
  python3 collect.py --headline-only # only the city-council documents page
  python3 collect.py --delay 3.0     # polite pacing (seconds between hits)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.robotparser import RobotFileParser

SITE = "https://www.casperwy.gov"
SITEMAP_URL = SITE + "/sitemap.xml"
HEADLINE_PAGE = SITE + "/government/city_council/documents.php"
USER_AGENT = "casper-record-mirror/1.0 (+https://github.com/bartimoussmith-oss/casper-record-mirror)"
DEFAULT_DELAY = 3.0
MAX_BYTES = 50 * 1024 * 1024  # 50 MiB per document; bigger files are recorded, not downloaded
DOC_EXTS = (".pdf", ".doc", ".docx", ".rtf", ".xls", ".xlsx",
            ".ppt", ".pptx", ".odt", ".txt", ".csv")
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".ico", ".tif", ".tiff", ".svg")
LINK_RE = re.compile(r"""href=["']([^"']+)["']""", re.I)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def is_document_url(url: str) -> bool:
    if not url:
        return False
    if not re.match(r"^https?://", url, re.I):
        return False
    parsed = urllib.parse.urlparse(url)
    if not parsed.netloc.lower().endswith("casperwy.gov"):
        return False
    path = urllib.parse.unquote(parsed.path.lower())
    if path.endswith(IMAGE_EXTS):
        return False
    return path.endswith(DOC_EXTS)


def normalize_key(url: str) -> str:
    """Strip cache-buster query params and fragments for deduping."""
    parsed = urllib.parse.urlparse(url)
    return f"{urllib.parse.unquote(parsed.netloc).lower()}{urllib.parse.unquote(parsed.path).lower()}"


def bucket_for(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    path = urllib.parse.unquote(parsed.path).lstrip("/")
    parts = [p for p in path.split("/") if p]
    if parts and parts[0].lower() == "documents":
        parts = parts[1:]
    return parts[0] if parts else "misc"


def safe_filename(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip()


def local_path(url: str, buckets_used: dict) -> str:
    """Map a document URL to a path under documents/, preserving nesting.

    e.g. .../Documents/Government/City Council/Gaming Location Survey.pdf
         -> documents/Government/City Council/Gaming Location Survey.pdf
    """
    parsed = urllib.parse.urlparse(url)
    rel = urllib.parse.unquote(parsed.path).lstrip("/")
    parts = [p for p in rel.split("/") if p]
    if parts and parts[0].lower() == "documents":
        parts = parts[1:]
    if not parts:
        return "documents/misc/document.pdf"
    folders = [safe_filename(p) or "folder" for p in parts[:-1]]
    basename = safe_filename(parts[-1]) or "document"
    folder = "/".join(["documents"] + folders)
    target = f"{folder}/{basename}"
    n = 2
    while target in buckets_used:
        stem = Path(basename).stem
        suffix = Path(basename).suffix
        target = f"{folder}/{stem}-{n}{suffix}"
        n += 1
    buckets_used[target] = url
    return target


def request(url: str, delay: float, timeout: int = 60):
    time.sleep(delay)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
        return resp.status, resp.headers, body


def fetch_text(url: str, delay: float, timeout: int = 60):
    status, headers, body = request(url, delay, timeout)
    return body.decode("utf-8", "replace"), headers.get("Content-Type", ""), status


def load_manifest(path: Path) -> dict:
    if path.exists():
        try:
            with open(path) as fh:
                data = json.load(fh)
                if isinstance(data, dict) and "documents" in data:
                    return data
        except Exception as exc:
            print(f"[!] Could not read existing manifest ({exc}); starting fresh.")
    return {
        "source": {
            "site": SITE,
            "sitemap_url": SITEMAP_URL,
            "documents_page_url": HEADLINE_PAGE,
        },
        "generated_at": None,
        "site_map": {"locs_total": 0, "documents_found": 0},
        "summary": {},
        "documents": [],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--delay", type=float, default=DEFAULT_DELAY,
                    help="seconds to wait between requests (default 3.0)")
    ap.add_argument("--max-bytes", type=int, default=MAX_BYTES,
                    help="per-document size cap (default 50 MiB)")
    ap.add_argument("--max-new", type=int, default=0,
                    help="stop after this many NEW documents (0 = no cap)")
    ap.add_argument("--output-dir", default="documents")
    ap.add_argument("--manifest", default="manifest.json")
    ap.add_argument("--headline-only", action="store_true",
                    help="only collect documents linked from the city-council documents page")
    ap.add_argument("--no-sitemap", action="store_true",
                    help="skip the sitemap and only use the documents page")
    ap.add_argument("--dry-run", action="store_true",
                    help="list discovered URLs without downloading anything")
    args = ap.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = Path(args.manifest)
    manifest = load_manifest(manifest_path)
    documents = manifest.get("documents", [])
    known = {normalize_key(d.get("url", "")): d for d in documents}

    # ---- robots.txt ------------------------------------------------------
    rp = RobotFileParser()
    robots_skip = False
    crawl_delay = 0.0
    try:
        robots_text, _, _ = fetch_text(SITE + "/robots.txt", args.delay, timeout=20)
        rp.parse(robots_text.splitlines())
        crawl_delay = rp.crawl_delay(USER_AGENT) or rp.crawl_delay("*") or 0.0
    except Exception as exc:
        print(f"[!] robots.txt could not be fetched ({exc}); continuing without robots filtering")
        robots_skip = True
    # crawl-delay is a law, not a suggestion: use the larger of our delay or the site's.
    delay = max(args.delay, crawl_delay)

    def robots_allowed(url: str) -> bool:
        if robots_skip:
            return True
        parsed = urllib.parse.urlparse(url)
        if not parsed.netloc.lower().endswith("casperwy.gov"):
            return False
        return rp.can_fetch(USER_AGENT, url)

    # ---- discover documents ----------------------------------------------
    discovered = {}

    def add_url(raw_url: str, source: str):
        if not raw_url:
            return
        url = urllib.parse.urljoin(HEADLINE_PAGE, raw_url.strip("\"'<>\t\n"))
        url = url.replace("&amp;", "&")
        if is_document_url(url):
            key = normalize_key(url)
            discovered[key] = {"url": url, "source": source}

    if not args.no_sitemap and not args.headline_only:
        print("[*] Fetching sitemap...")
        try:
            sitemap_text, _, _ = fetch_text(SITEMAP_URL, delay, timeout=60)
            root = ET.fromstring(sitemap_text)
            locs = [loc.text.strip() for loc in root.iter()
                    if loc.tag.lower().endswith("loc") and loc.text]
            manifest["site_map"]["locs_total"] = len(locs)
            for loc in locs:
                add_url(loc, "sitemap.xml")
            print(f"[*] Sitemap listed {len(locs)} URLs; {len(discovered)} documents found so far")
        except Exception as exc:
            print(f"[!] Sitemap fetch failed ({exc}); continuing with headline page only")

    print("[*] Fetching headline documents page...")
    try:
        page_text, _, _ = fetch_text(HEADLINE_PAGE, delay, timeout=30)
        for m in LINK_RE.findall(page_text):
            add_url(m, "documents.php")
        print(f"[*] Headline page documents discovered; {len(discovered)} unique documents total")
    except Exception as exc:
        print(f"[!] Headline page fetch failed ({exc})")

    manifest["site_map"]["documents_found"] = len(discovered)

    if args.dry_run:
        for key, entry in sorted(discovered.items()):
            suffix = " [already archived]" if key in known else ""
            print(f"[dry-run] {entry['url']}{suffix}")
        return 0

    # ---- download ---------------------------------------------------------
    new_count = 0
    skipped_count = 0
    buckets_used: dict[str, str] = {}

    def upsert(rec: dict):
        key = normalize_key(rec.get("url", ""))
        docs = [d for d in documents if normalize_key(d.get("url", "")) != key]
        docs.append(rec)
        return docs

    for key, entry in sorted(discovered.items()):
        url = entry["url"]
        existing = known.get(key)
        if existing and existing.get("status") == "archived" \
                and existing.get("local_path") and Path(existing["local_path"]).exists():
            skipped_count += 1
            continue
        if args.max_new and new_count >= args.max_new:
            break
        if not robots_allowed(url):
            print(f"[robots] Disallowed — skipping {url}")
            documents = upsert({"url": url, "status": "robots_refused",
                                "fetched_at": now_iso(),
                                "error": "disallowed by robots.txt",
                                "source": entry["source"]})
            continue
        print(f"[*] Downloading {url}")
        try:
            status, headers, body = request(url, delay, timeout=90)
            content_len = len(body)
            if content_len > args.max_bytes:
                raise RuntimeError(f"file too large ({content_len} > {args.max_bytes} bytes)")
            local = local_path(url, buckets_used)
            target = Path(local)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)
            documents = upsert({
                "url": url,
                "local_path": local,
                "bytes": content_len,
                "sha256": hashlib.sha256(body).hexdigest(),
                "content_type": headers.get("Content-Type", ""),
                "status": "archived",
                "fetched_at": now_iso(),
                "source": entry["source"],
            })
            new_count += 1
        except Exception as exc:
            status_hint = "oversized" if "too large" in str(exc) else "failed"
            documents = upsert({"url": url, "status": status_hint,
                                "fetched_at": now_iso(),
                                "error": str(exc),
                                "source": entry["source"]})

    documents = sorted(documents, key=lambda d: normalize_key(d.get("url", "")))
    manifest["documents"] = documents
    manifest["generated_at"] = now_iso()
    manifest["summary"] = {}
    for doc in documents:
        st = doc.get("status", "unknown")
        manifest["summary"][st] = manifest["summary"].get(st, 0) + 1

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(manifest_path, "w") as fh:
        json.dump(manifest, fh, indent=2)

    # ---- MANIFEST.md -----------------------------------------------------
    lines = [
        "# Casper, WY — archived documents",
        "",
        f"Generated from [casperwy.gov]({SITE}) via the sitemap and the "
        f"[city council documents page]({HEADLINE_PAGE}).",
        "",
        f"- **Sitemap entries:** {manifest['site_map']['locs_total']}",
        f"- **Documents discovered:** {manifest['site_map']['documents_found']}",
        f"- **Archive run:** {now_iso()}",
        "",
        "## Summary",
        "",
        "| Status | Count |",
        "| --- | --- |",
    ]
    for status, count in sorted(manifest["summary"].items()):
        lines.append(f"| {status} | {count} |")
    lines += ["", "## Not archived", ""]
    failures = [d for d in documents if d.get("status") != "archived"]
    if failures:
        for d in failures:
            lines.append(f"- **{d.get('status')}** — {d.get('url')}")
            if d.get("error"):
                lines.append(f"  - error: {d['error']}")
    else:
        lines.append("None — every discovered document archived.")
    lines += [
        "",
        "## Documents",
        "",
        "Full provenance (source URL, local path, SHA-256, size, fetch time,",
        "content type) is in [`manifest.json`](manifest.json).",
        "",
    ]
    by_bucket: dict[str, list] = {}
    for d in documents:
        if d.get("status") != "archived":
            continue
        rel = (d.get("local_path") or "").strip()
        if not rel:
            continue
        bucket = rel.split("/")[1] if len(rel.split("/")) > 2 else "misc"
        by_bucket.setdefault(bucket, []).append(d)
    for bucket, docs in sorted(by_bucket.items()):
        bucket_bytes = sum(d.get("bytes", 0) for d in docs)
        lines.append(f"### {bucket} — {len(docs)} documents ({bucket_bytes/1024/1024:.1f} MiB)")
        lines.append("")
        for d in sorted(docs, key=lambda x: x.get("local_path", "")):
            lines.append(f"- `{d.get('local_path')}` — {d.get('bytes', 0)/1024:.1f} KiB")
        lines.append("")
    with open("MANIFEST.md", "w") as fh:
        fh.write("\n".join(lines))

    print(f"[done] new={new_count} skipped={skipped_count} total={len(documents)}")
    print(f"[done] summary: {json.dumps(manifest['summary'], sort_keys=True)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
