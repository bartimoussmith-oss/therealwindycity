#!/usr/bin/env python3
"""measure_docs.py — Measure exact Granicus docs payload (no bulk downloads).

Fetches all 481 agendas (needed to discover doc links), HEADs every
MetaViewer/MinutsViewer/nested URL for Content-Length, and sums the bytes a
full download_granicus_docs.py run would pull. Writes docs_audit.json.
"""
import csv, json, re, sys, time, urllib.request
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from html import unescape

BASE = "https://cheyenne.granicus.com"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) CheyenneArchiveResearch/1.0"}
ROOT = Path(__file__).resolve().parents[1]  # youtube-archive/


def clean(text):
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", text or ""))).strip()


def parse_agenda(html):
    events = []
    for m in re.finditer(r"<td width=40>\s*([^<]*?)</td>\s*<td>(.*?)</td>", html, re.S | re.I):
        no = clean(m.group(1)).rstrip(".")
        title = re.split(r"\bACTION\s*:", clean(m.group(2)), maxsplit=1)[0].strip(" ;\t")
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
    seen, deduped = set(), []
    for meta, no, title in out:
        if meta not in seen:
            seen.add(meta)
            deduped.append((meta, no, title))
    return deduped


def get(url, timeout=60):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, dict(r.headers), r.read()


def head_size(url, timeout=30):
    """Return (bytes|None, content_type). Never downloads bodies."""
    try:
        req = urllib.request.Request(url, headers=HEADERS, method="HEAD")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            clen = r.headers.get("Content-Length")
            if clen and clen.isdigit():
                return int(clen), r.headers.get("Content-Type", "")
    except Exception:
        pass
    try:  # Range fallback: Content-Range reveals total size
        h = dict(HEADERS, Range="bytes=0-0")
        req = urllib.request.Request(url, headers=h)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            cr = r.headers.get("Content-Range", "")
            m = re.search(r"/(\d+)$", cr)
            if m:
                return int(m.group(1)), r.headers.get("Content-Type", "")
            clen = r.headers.get("Content-Length")
            if clen and clen.isdigit():  # headers-only; body never read
                return int(clen), r.headers.get("Content-Type", "")
    except Exception as e:
        return None, f"ERR {str(e)[:60]}"
    return None, "no-length"


def one(row):
    clip = row["clip_id"]
    res = {"clip": clip, "agenda": 0, "minutes": 0, "docs": [], "errors": []}
    time.sleep(0.2)
    try:
        agenda_url = row["agenda_url"] or f"{BASE}/AgendaViewer.php?view_id=2&clip_id={clip}"
        _, _, body = get(agenda_url)
        res["agenda"] = len(body)
        items = parse_agenda(body.decode("utf-8", "replace"))
    except Exception as e:
        res["errors"].append(f"agenda: {str(e)[:80]}")
        items = []
    for meta, no, title in items:
        time.sleep(0.15)
        url = f"{BASE}/MetaViewer.php?view_id=2&clip_id={clip}&meta_id={meta}"
        size, ctype = head_size(url)
        if size is None:
            res["errors"].append(f"meta{meta}: {ctype}")
            continue
        res["docs"].append({"meta": meta, "bytes": size, "type": ctype[:40]})
        if "pdf" not in ctype.lower():  # chase nested links like the downloader
            try:
                _, _, b2 = get(url)
                nested = re.findall(r'href="([^"]*(?:DocumentViewer\.php[^"]*|\.pdf(?:[^"]*)?))"',
                                    b2.decode("utf-8", "replace"), re.I)
                for href in dict.fromkeys(nested):
                    nurl = href if href.startswith("http") else BASE + href.replace("//cheyenne.granicus.com", "")
                    if nurl.startswith("//"):
                        nurl = "https:" + nurl
                    time.sleep(0.15)
                    nsize, _ = head_size(nurl)
                    if nsize:
                        res["docs"].append({"meta": meta, "bytes": nsize, "nested": True})
            except Exception as e:
                res["errors"].append(f"meta{meta}-nested: {str(e)[:60]}")
    try:
        time.sleep(0.15)
        _, _, mb = get(f"{BASE}/MinutesViewer.php?view_id=2&clip_id={clip}")
        res["minutes"] = len(mb) if mb[:4] == b"%PDF" and len(mb) > 1000 else 0
    except Exception as e:
        res["errors"].append(f"minutes: {str(e)[:60]}")
    return res


def main():
    rows = list(csv.DictReader(open(f"{ROOT}/catalog_granicus.csv", encoding="utf-8")))
    print(f"{len(rows)} clips")
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(one, rows))
    json.dump(results, open(f"{ROOT}/docs_audit.json", "w"))
    agenda = sum(r["agenda"] for r in results)
    minutes = sum(r["minutes"] for r in results)
    docs = sum(d["bytes"] for r in results for d in r["docs"])
    ndocs = sum(len(r["docs"]) for r in results)
    errs = sum(len(r["errors"]) for r in results)
    print(f"done in {time.time()-t0:.0f}s")
    print(f"agendas: {agenda/1e6:.1f} MB | minutes: {minutes/1e6:.1f} MB (+{sum(1 for r in results if r['minutes'])}/481 clips have minutes)")
    print(f"supporting docs: {ndocs} files = {docs/1e9:.2f} GB")
    print(f"TOTAL DOCS: {(agenda+minutes+docs)/1e9:.2f} GB | errors: {errs}")
    for r in results:
        for e in r["errors"][:2]:
            print("  ERR clip", r["clip"], e)
            break


if __name__ == "__main__":
    main()
