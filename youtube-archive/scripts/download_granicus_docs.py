#!/usr/bin/env python3
"""
download_granicus_docs.py — Download EVERY agenda, supporting document, and set
of minutes from the City of Cheyenne Granicus archive.

What gets grabbed per meeting (clip):
  1. agenda.html        — the full AgendaViewer agenda (agendas exist only as HTML)
  2. item_XX_metaNNNNN_*.pdf — each agenda item's "Supporting Document" PDF
     (recent era; older meetings have none — the MetaViewer snippet HTML is
     saved instead so the record is still complete)
  3. minutes.pdf        — MinutesViewer PDF, tried for EVERY clip (the archive
     table under-reports minutes links, so we don't trust it)

Unlike the meeting VIDEOS (CloudFront-blocked on datacenter IPs), these
documents come from the main Granicus web host and download fine from ANY
network, including cloud servers.

Layout:
  documents/clip1126_2026-08-24/agenda.html
  documents/clip1126_2026-08-24/item_05_meta149999_minutes-from-regular-meeting....pdf
  documents/clip1126_2026-08-24/minutes.pdf
  documents_manifest.csv   (one row per document + status)

Usage:
  pip install -r requirements.txt
  python scripts/download_granicus_docs.py --only 1126 31        # test: 1 new + 1 old
  python scripts/download_granicus_docs.py                       # everything
  python scripts/download_granicus_docs.py --from-date 2020-01-01
  python scripts/download_granicus_docs.py --no-supporting        # agendas + minutes only

Storage: agendas/minutes are ~50-200 KB each; supporting docs ~0.1-5 MB each.
The full set should land in the low tens of GB at most.
"""
import argparse, csv, os, re, time
import requests

BASE = "https://cheyenne.granicus.com"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) CheyenneArchiveResearch/1.0"}

SKIP_MINUTES_HTML_MARKERS = ("not found", "no minutes", "unavailable")


def slug(text: str, maxlen: int = 70) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-")
    return text[:maxlen].rstrip("-") or "item"


def clean(text: str) -> str:
    from html import unescape
    text = unescape(re.sub(r"<[^>]+>", " ", text or ""))
    return re.sub(r"\s+", " ", text).strip()


def parse_agenda(html: str):
    """Return [(meta_id, item_no, item_title)] in agenda order.

    Agenda items are <td width=40>N.</td><td>TITLE...ACTION:...</td> tables;
    each 'Supporting Document' link (name="document<METAID>") belongs to the
    most recent preceding item.
    """
    events = []  # (pos, kind, payload)
    for m in re.finditer(r"<td width=40>\s*([^<]*?)</td>\s*<td>(.*?)</td>", html, re.S | re.I):
        no = clean(m.group(1)).rstrip(".")
        title_full = clean(m.group(2))
        title = re.split(r"\bACTION\s*:", title_full, maxsplit=1)[0].strip(" ;\t")
        events.append((m.start(), "item", (no, title[:300])))
    for m in re.finditer(r'name="document(\d+)"', html):
        events.append((m.start(), "doc", m.group(1)))
    events.sort()
    out, current = [], ("", "")
    for _, kind, payload in events:
        if kind == "item":
            current = payload
        else:
            out.append((payload, current[0], current[1]))
    # de-dupe (same meta linked twice in odd pages) preserving order
    seen, deduped = set(), []
    for meta, no, title in out:
        if meta not in seen:
            seen.add(meta)
            deduped.append((meta, no, title))
    return deduped


def pdf_page_count(path: str):
    try:
        from pypdf import PdfReader
        return len(PdfReader(path).pages)
    except Exception:
        return ""


def fetch(session: requests.Session, url: str):
    r = session.get(url, timeout=60)
    r.raise_for_status()
    return r


def main():
    ap = argparse.ArgumentParser(description="Download all Cheyenne Granicus agendas + supporting docs + minutes.")
    ap.add_argument("--catalog", default="catalog_granicus.csv")
    ap.add_argument("--out", default="documents")
    ap.add_argument("--manifest", default="documents_manifest.csv")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only", nargs="*", default=[])
    ap.add_argument("--from-date", default="")
    ap.add_argument("--to-date", default="")
    ap.add_argument("--delay", type=float, default=0.7, help="seconds between HTTP fetches")
    ap.add_argument("--no-supporting", action="store_true")
    ap.add_argument("--no-minutes", action="store_true")
    ap.add_argument("--oldest-first", action="store_true")
    args = ap.parse_args()

    with open(args.catalog, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if args.only:
        want = set(args.only)
        rows = [r for r in rows if r["clip_id"] in want]
    if args.from_date:
        rows = [r for r in rows if (r["date_iso"] or "") >= args.from_date]
    if args.to_date:
        rows = [r for r in rows if r["date_iso"] and r["date_iso"] <= args.to_date]
    rows.sort(key=lambda r: r["date_iso"] or "", reverse=not args.oldest_first)
    if args.limit:
        rows = rows[:args.limit]

    os.makedirs(args.out, exist_ok=True)
    manifest = []
    session = requests.Session()
    session.headers.update(HEADERS)

    def record(clip, date, dtype, seq, title, meta, url, path, status):
        size = os.path.getsize(path) if path and os.path.exists(path) else 0
        pages = pdf_page_count(path) if path.endswith(".pdf") and os.path.exists(path) else ""
        manifest.append({"clip_id": clip, "date_iso": date, "doc_type": dtype,
                         "item_seq": seq, "item_title": title, "meta_id": meta,
                         "source_url": url, "local_path": path, "bytes": size,
                         "pdf_pages": pages, "status": status})

    for i, row in enumerate(rows, 1):
        clip, date = row["clip_id"], row["date_iso"] or "nodate"
        folder = os.path.join(args.out, f"clip{clip}_{date}")
        os.makedirs(folder, exist_ok=True)
        print(f"\n[{i}/{len(rows)}] clip {clip} | {row['name']} | {row['date_display']}")

        # ---- 1. agenda HTML ----
        agenda_url = row["agenda_url"] or f"{BASE}/AgendaViewer.php?view_id=2&clip_id={clip}"
        agenda_path = os.path.join(folder, "agenda.html")
        agenda_html = ""
        try:
            if os.path.exists(agenda_path) and os.path.getsize(agenda_path) > 0:
                agenda_html = open(agenda_path, encoding="utf-8", errors="replace").read()
                record(clip, date, "agenda", "", row["name"], "", agenda_url, agenda_path, "skipped-exists")
                print("  agenda.html already saved")
            else:
                agenda_html = fetch(session, agenda_url).text
                open(agenda_path, "w", encoding="utf-8").write(agenda_html)
                record(clip, date, "agenda", "", row["name"], "", agenda_url, agenda_path, "ok")
                print(f"  agenda.html saved ({len(agenda_html) // 1024} KB)")
                time.sleep(args.delay)
        except Exception as e:  # noqa: BLE001
            record(clip, date, "agenda", "", row["name"], "", agenda_url, "", f"FAILED: {e}"[:200])
            print(f"  agenda FAILED: {e}")

        # ---- 2. supporting documents ----
        if not args.no_supporting and agenda_html:
            try:
                items = parse_agenda(agenda_html)
            except Exception as e:  # noqa: BLE001
                items = []
                print(f"  agenda parse warning: {e}")
            print(f"  {len(items)} supporting-document link(s) found")
            for seq, (meta, no, title) in enumerate(items, 1):
                doc_url = f"{BASE}/MetaViewer.php?view_id=2&clip_id={clip}&meta_id={meta}"
                label = f"item_{seq:02d}_meta{meta}_{slug((no + ' ' + title) if (no or title) else 'doc')}"
                try:
                    # skip if we already saved either variant
                    existing = [p for p in (os.path.join(folder, label + ".pdf"),
                                            os.path.join(folder, label + ".html"))
                                if os.path.exists(p) and os.path.getsize(p) > 0]
                    if existing:
                        record(clip, date, "supporting_doc", no, title, meta, doc_url, existing[0], "skipped-exists")
                        continue
                    r = fetch(session, doc_url)
                    body = r.content
                    if body[:4] == b"%PDF":
                        path = os.path.join(folder, label + ".pdf")
                        open(path, "wb").write(body)
                        record(clip, date, "supporting_doc", no, title, meta, doc_url, path, "ok")
                    else:
                        # old-era HTML snippet (or wrapper page): save it, then
                        # chase any nested file links inside
                        path = os.path.join(folder, label + ".html")
                        open(path, "wb").write(body)
                        record(clip, date, "supporting_doc_html", no, title, meta, doc_url, path, "ok-html")
                        nested = re.findall(r'href="([^"]*(?:DocumentViewer\.php[^"]*|\.pdf(?:[^"]*)?))"',
                                            body.decode("utf-8", "replace"), re.I)
                        for n, href in enumerate(dict.fromkeys(nested), 1):
                            nurl = href if href.startswith("http") else BASE + href.replace("//cheyenne.granicus.com", "")
                            if nurl.startswith("//"):
                                nurl = "https:" + nurl
                            try:
                                nb = fetch(session, nurl).content
                                ext = ".pdf" if nb[:4] == b"%PDF" else ".bin"
                                npath = os.path.join(folder, f"{label}_att{n}{ext}")
                                open(npath, "wb").write(nb)
                                record(clip, date, "supporting_doc_nested", no, title, meta, nurl, npath, "ok")
                                time.sleep(args.delay)
                            except Exception as e2:  # noqa: BLE001
                                record(clip, date, "supporting_doc_nested", no, title, meta, nurl, "", f"FAILED: {e2}"[:200])
                    time.sleep(args.delay)
                except Exception as e:  # noqa: BLE001
                    record(clip, date, "supporting_doc", no, title, meta, doc_url, "", f"FAILED: {e}"[:200])
                    print(f"    meta {meta} FAILED: {e}")

        # ---- 3. minutes (try every clip) ----
        if not args.no_minutes:
            min_url = f"{BASE}/MinutesViewer.php?view_id=2&clip_id={clip}"
            min_path = os.path.join(folder, "minutes.pdf")
            try:
                if os.path.exists(min_path) and os.path.getsize(min_path) > 1000:
                    record(clip, date, "minutes", "", "", "", min_url, min_path, "skipped-exists")
                    print("  minutes.pdf already saved")
                else:
                    r = fetch(session, min_url)
                    if r.content[:4] == b"%PDF" and len(r.content) > 1000:
                        open(min_path, "wb").write(r.content)
                        record(clip, date, "minutes", "", "", "", min_url, min_path, "ok")
                        print(f"  minutes.pdf saved ({len(r.content) // 1024} KB)")
                    else:
                        record(clip, date, "minutes", "", "", "", min_url, "", "no-minutes")
                        print("  no minutes for this clip")
                    time.sleep(args.delay)
            except Exception as e:  # noqa: BLE001
                record(clip, date, "minutes", "", "", "", min_url, "", f"FAILED: {e}"[:200])
                print(f"  minutes FAILED: {e}")

    with open(args.manifest, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["clip_id", "date_iso", "doc_type", "item_seq",
                                          "item_title", "meta_id", "source_url",
                                          "local_path", "bytes", "pdf_pages", "status"])
        w.writeheader()
        w.writerows(manifest)

    from collections import Counter
    print(f"\nWrote {args.manifest} ({len(manifest)} rows).")
    print("By type/status:",
          dict(Counter((m["doc_type"], m["status"]) for m in manifest)))
    total_mb = sum(m["bytes"] for m in manifest) / 1e6
    print(f"Total bytes referenced: {total_mb:.1f} MB")


if __name__ == "__main__":
    main()
