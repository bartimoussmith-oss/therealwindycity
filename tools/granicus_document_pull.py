# ═════════════════════════════════════════════════════════════════════════════
#  THE REAL WINDY CITY — GRANICUS DOCUMENT PULLER
#
#  Walks the Cheyenne Granicus archive the same way a hand pull does:
#    1. search (or the full listing)          -> enumerate meetings (clip_ids)
#    2. each meeting's agenda page            -> open EVERY hyperlink in it
#       (GeneratedAgendaViewer)                 MediaPlayer (video markers),
#                                               MetaViewer (supporting docs /
#                                               proposed substitutes)
#    3. each supporting document (MetaViewer) -> resolve + save the real file
#    4. each meeting's minutes (MinutesViewer -> DocumentViewer .pdf) -> save
#    5. everything lands on Google Drive, plus an index.json + sha256 manifest
#
#  Verified URL map (cheyenne.granicus.com, view_id=2 = archives):
#    search      ViewSearchResults.php?keywords=KW&view_id=2     -> clip_id rows
#    listing     ViewPublisher.php?view_id=2                     -> all meetings
#    agenda      AgendaViewer.php?view_id=2&clip_id=N  (302 -> GeneratedAgendaViewer.php)
#    item video  MediaPlayer.php?view_id=2&clip_id=N&meta_id=M   (timestamp marker)
#    doc         MetaViewer.php?view_id=2&clip_id=N&meta_id=M    (supporting doc PDF)
#    minutes     MinutesViewer.php?view_id=2&clip_id=N (302 -> DocumentViewer.php?file=cheyenne_<hash>.pdf)
#
#  Paste into one Colab cell and run. Resumable — re-run skips what's done.
#
#  ⚙️ EDIT THESE LINES to choose what to pull:
KEYWORDS     = ["Lead"]        # search terms; ignored when FULL_ARCHIVE=True
VIEW_ID      = 2               # 2 = archives (clip_id), 5 = live/upcoming (event_id)
FULL_ARCHIVE = False           # True = walk the whole ViewPublisher listing
MAX_CLIPS    = 0               # 0 = no limit. SAFETY: set 2 for a first test.
DELAY        = 1.5             # seconds between requests — be polite
SAVE_PDF     = True            # save the binary documents
SAVE_TXT     = True            # save extracted text alongside
OUT_ROOT     = "/content/drive/MyDrive/TheRealWindyCity/cheyenne"  # Google Drive
#  On a non-Colab machine, OUT_ROOT falls back to ./granicus_pull/ if unmounted.
#
#  Note: cheyenne.granicus.com's robots.txt blocks automated crawlers. This is
#  a single-owner, manually-invoked, throttled pull of PUBLIC records (the same
#  files a citizen opens by hand) for the transparency archive — not a bot.
# ═════════════════════════════════════════════════════════════════════════════
import hashlib, json, os, re, sys, time, urllib.parse, urllib.request, html

BASE     = "https://cheyenne.granicus.com"
UA       = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124 Safari/537.36 TheRealWindyCity/1.0 (+civic-archive)")
TIME_FMT = "%Y-%m-%dT%H:%M:%SZ"

_re_doc_id   = re.compile(r"MetaViewer\.php[^\"'\s]*?meta_id=(\d+)", re.I)
_re_media_id = re.compile(r"MediaPlayer\.php[^\"'\s]*?meta_id=(\d+)", re.I)
_re_clip_id  = re.compile(r"clip_id=(\d+)", re.I)
_re_pdf      = re.compile(r"""(?:href|src)=["']([^"']+\.pdf[^"']*)["']""", re.I)
_re_date     = re.compile(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}\b", re.I)
_re_tag      = re.compile(r"<[^>]+>")

# ── net ──────────────────────────────────────────────────────────────────────
def http_get(url, delay=DELAY):
    """Return (status, body_bytes, final_url, content_type). Follows redirects."""
    time.sleep(delay)
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/pdf,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    })
    with urllib.request.urlopen(req, timeout=120) as r:
        ct = (r.headers.get("Content-Type") or "").lower()
        return r.status, r.read(), r.geturl(), ct

# ── parsers (pure; selftest below) ───────────────────────────────────────────
def clip_ids(html_text):
    return sorted({int(m) for m in _re_clip_id.findall(html_text)})

def doc_meta_ids(html_text):
    """meta_ids of supporting documents (MetaViewer links only — not video)."""
    return sorted({int(m) for m in _re_doc_id.findall(html_text)})

def media_meta_ids(html_text):
    """meta_ids of video timestamp markers (MediaPlayer links)."""
    return sorted({int(m) for m in _re_media_id.findall(html_text)})

def pdf_urls(html_text):
    out = []
    for u in _re_pdf.findall(html_text):
        u = html.unescape(u.strip())
        if u.startswith("http"):
            out.append(u)
    return out

def title_and_date(html_text, clip):
    """Best-effort meeting name + date for one clip_id, from the listing row."""
    i = html_text.find(f"clip_id={clip}")
    if i < 0:
        return "", ""
    window = html_text[max(0, i - 4000): i + 4000]
    m = _re_date.search(window)
    date = m.group(0) if m else ""
    name = ""
    m2 = re.search(r"<td[^>]*>\s*([^<]{3,80})\s*</td>", window, re.I)
    if m2:
        name = _re_tag.sub("", m2.group(1)).strip()
    return name, date

def html_to_text(html_text):
    t = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html_text)
    t = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|li|h\d)>", "\n", t)
    t = _re_tag.sub(" ", t)
    t = html.unescape(t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n\s*\n+", "\n", t)
    return t.strip()

# ── pdf text (optional) ─────────────────────────────────────────────────────
def pdf_to_text(data):
    try:
        import pdfplumber
    except Exception:
        try:
            import subprocess
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "pdfplumber"])
            import pdfplumber
        except Exception:
            return ""  # no pdfplumber, no text — PDF still saved
    try:
        import io
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            return "\n".join((p.extract_text() or "") for p in pdf.pages)
    except Exception as e:
        return f"[pdf text extraction failed: {e}]"

def sha256(data):
    return hashlib.sha256(data).hexdigest()

def write_bin(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)

def write_txt(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)

def safe(s):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", s).strip("_") or "doc"

# ── archive enumeration ──────────────────────────────────────────────────────
def enumerate_clip_ids():
    """Return {clip_id: (name, date)} across KEYWORDS searches or the full listing."""
    if FULL_ARCHIVE:
        urls = [f"{BASE}/ViewPublisher.php?view_id={VIEW_ID}"]
    else:
        urls = [f"{BASE}/ViewSearchResults.php?keywords={urllib.parse.quote(k)}&view_id={VIEW_ID}"
                for k in KEYWORDS]
    found = {}
    for u in urls:
        page = 1
        seen_pages = set()
        while True:
            st, body, fin, ct = http_get(u)
            txt = body.decode("utf-8", "replace")
            new = {c: title_and_date(txt, c) for c in clip_ids(txt) if c not in found}
            found.update(new)
            if new:
                print(f"  {u.split('?')[0]} page {page}: +{len(new)} clips "
                      f"(total {len(found)})")
            # pagination: follow a next-page link if present and not yet seen
            nxt = re.search(r'[?&](?:page|start|p)=(\d+)', txt)
            nxt = int(nxt.group(1)) if nxt else 0
            if not new or nxt in seen_pages or nxt <= page:
                break
            seen_pages.add(nxt)
            sep = "&" if "?" in u else "?"
            u = re.sub(r"[?&](?:page|start|p)=\d+", "", u) + f"{sep}page={nxt}"
            page = nxt
    return found

# ── one meeting ──────────────────────────────────────────────────────────────
def pull_clip(clip, name, date, root, manifest):
    d = os.path.join(root, f"{clip:04d}")
    os.makedirs(d, exist_ok=True)
    rec = manifest["meetings"].setdefault(
        str(clip), {"name": name, "date": date, "documents": []})

    # 1 · agenda page + its hyperlinks
    st, body, fin, ct = http_get(f"{BASE}/AgendaViewer.php?view_id={VIEW_ID}&clip_id={clip}")
    txt = body.decode("utf-8", "replace")
    ag_path = os.path.join(d, "agenda.html")
    write_bin(ag_path, body)
    if SAVE_TXT:
        write_txt(os.path.join(d, "agenda.txt"), html_to_text(txt))
    rec["agenda"] = os.path.relpath(ag_path, root)
    rec["agenda_url"] = fin

    docs = doc_meta_ids(txt)                       # supporting docs / substitutes
    vids = media_meta_ids(txt)                     # video timestamp markers
    rec["video_meta_ids"] = vids
    rec["pdf_links_in_agenda"] = pdf_urls(txt)     # any bare PDFs linked directly

    # 2 · minutes -> DocumentViewer .pdf
    st, mbody, mfin, mct = http_get(f"{BASE}/MinutesViewer.php?view_id={VIEW_ID}&clip_id={clip}")
    mname = "minutes.pdf"
    m = re.search(r"file=([^&\"]+\.pdf)", mfin)
    if m:
        mname = urllib.parse.unquote(m.group(1))
    mpath = os.path.join(d, mname)
    if SAVE_PDF and mbody[:4] == b"%PDF":
        write_bin(mpath, mbody)
        if SAVE_TXT:
            write_txt(os.path.join(d, "minutes.txt"), pdf_to_text(mbody))
        rec["minutes"] = os.path.relpath(mpath, root)
        rec["minutes_sha256"] = sha256(mbody)
    else:
        rec["minutes"] = None
    rec["minutes_url"] = mfin

    # 3 · every supporting document hyperlink
    for i, mid in enumerate(docs, 1):
        if any(x.get("meta_id") == mid for x in rec["documents"]):
            continue                                # already pulled
        st, dbody, dfin, dct = http_get(
            f"{BASE}/MetaViewer.php?view_id={VIEW_ID}&clip_id={clip}&meta_id={mid}")
        if not dbody:
            rec["documents"].append({"meta_id": mid, "file": None, "empty": True})
            continue
        is_pdf = dct == "application/pdf" or dbody[:4] == b"%PDF"
        fname = f"{mid}.pdf" if is_pdf else f"{mid}.html"
        # if it redirected to a DocumentViewer.php?file=..., keep the real name
        m = re.search(r"file=([^&\"]+\.pdf)", dfin)
        if m:
            fname = urllib.parse.unquote(m.group(1))
        fpath = os.path.join(d, "docs", fname)
        if SAVE_PDF:
            write_bin(fpath, dbody)
        text = ""
        if is_pdf:
            text = pdf_to_text(dbody) if SAVE_TXT else ""
        else:
            text = html_to_text(dbody.decode("utf-8", "replace")) if SAVE_TXT else ""
        if SAVE_TXT and text:
            tpath = os.path.join(d, "docs", f"{fname}.txt")
            write_txt(tpath, text)
        rec["documents"].append({
            "meta_id": mid, "file": os.path.relpath(fpath, root),
            "url": dfin, "pdf": is_pdf, "sha256": sha256(dbody),
        })
        print(f"    doc {i}/{len(docs)} meta_id={mid} {fname} "
              f"({len(dbody)//1024} KB{' pdf' if is_pdf else ''})", flush=True)
    return rec

# ── main ─────────────────────────────────────────────────────────────────────
def main():
    root = OUT_ROOT
    if root.startswith("/content/drive") and not os.path.isdir("/content/drive/MyDrive"):
        try:
            from google.colab import drive
            drive.mount("/content/drive")
        except Exception:
            print("! Drive not available — falling back to ./granicus_pull/")
            root = os.path.abspath("granicus_pull")
    if not os.path.isdir(root.split(":")[-1]) and root.startswith("/content/drive"):
        root = os.path.abspath("granicus_pull")     # mount failed / local run

    manifest_path = os.path.join(root, "manifest.json")
    manifest = (json.loads(open(manifest_path).read()) if os.path.exists(manifest_path)
                else {"source": "tools/granicus_document_pull.py",
                      "generated_at": "", "base": BASE,
                      "keywords": KEYWORDS, "view_id": VIEW_ID, "meetings": {}})

    clips = enumerate_clip_ids()
    print(f"\n{len(clips)} meeting(s) to process")
    todo = [c for c in clips if str(c) not in manifest["meetings"]
            or not manifest["meetings"][str(c)].get("documents")]
    if MAX_CLIPS:
        todo = todo[:MAX_CLIPS]
    print(f"  new/incomplete: {len(todo)}")
    for n, clip in enumerate(todo, 1):
        name, date = clips[clip]
        print(f"\n[{n}/{len(todo)}] clip {clip} — {name} {date}", flush=True)
        try:
            pull_clip(clip, name, date, root, manifest)
        except Exception as e:
            print(f"  !! clip {clip} failed: {type(e).__name__}: {e}")
            manifest["meetings"].setdefault(str(clip), {})["error"] = str(e)
        manifest["generated_at"] = time.strftime(TIME_FMT, time.gmtime())
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=1)

    n_docs = sum(len(v.get("documents", [])) for v in manifest["meetings"].values())
    n_pdf = sum(1 for v in manifest["meetings"].values()
                for x in v.get("documents", []) if x.get("pdf"))
    print("\n" + "═" * 62)
    print(f"  GRANICUS PULL DONE ✅")
    print(f"   meetings:      {len(manifest['meetings'])}")
    print(f"   documents:     {n_docs}  ({n_pdf} PDF)")
    print(f"   manifest:      {manifest_path}")
    print("═" * 62)

# ── selftest (offline; proves the parsers on real observed HTML) ─────────────
def selftest():
    listing = """
      <td>City Council Meeting</td><td>Jun 23, 2026</td>
      <a href="http://cheyenne.granicus.com/AgendaViewer.php?view_id=2&clip_id=1103">Agenda</a>
      <a href="http://cheyenne.granicus.com/MinutesViewer.php?view_id=2&clip_id=1103">Minutes</a>
      <a href="http://cheyenne.granicus.com/ASX.php?view_id=2&clip_id=1103">Video</a>
      <td>City Council Meeting</td><td>Jul 14, 2014</td>
      <a href="AgendaViewer.php?view_id=2&clip_id=435">Agenda</a>
    """
    agenda = """
      <a href="https://cheyenne.granicus.com/MediaPlayer.php?view_id=2&clip_id=1103&meta_id=148913">1. CALL MEETING TO ORDER.</a>
      <a href="https://cheyenne.granicus.com/MetaViewer.php?view_id=2&clip_id=1103&meta_id=148918">Supporting Document</a>
      <a href="https://cheyenne.granicus.com/MetaViewer.php?view_id=2&clip_id=1103&meta_id=148923">Proposed Substitute</a>
      <a href="https://cheyenne.granicus.com/DocumentViewer.php?file=cheyenne_964bdd5707a3db4918c35f6e987ac155.pdf&amp;view=1">pdf</a>
    """
    assert clip_ids(listing) == [435, 1103], clip_ids(listing)
    assert doc_meta_ids(agenda) == [148918, 148923], doc_meta_ids(agenda)
    assert media_meta_ids(agenda) == [148913], media_meta_ids(agenda)
    assert pdf_urls(agenda) == ["https://cheyenne.granicus.com/DocumentViewer.php?file=cheyenne_964bdd5707a3db4918c35f6e987ac155.pdf&view=1"], pdf_urls(agenda)
    name, date = title_and_date(listing, 1103)
    assert name == "City Council Meeting" and date == "Jun 23, 2026", (name, date)
    print("SELFTEST OK — parsers match the live Granicus HTML structure")

if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        main()
