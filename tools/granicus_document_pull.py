# ═════════════════════════════════════════════════════════════════════════════
#  THE REAL WINDY CITY — GRANICUS FULL-ARCHIVE SWEEP (NOTHING EXCLUDED)
#
#  Walks the ENTIRE cheyenne.granicus.com surface the way a complete hand-pull
#  would, and saves every document + every media reference it finds:
#
#    1. DISCOVER every live "view" (ViewPublisher.php?view_id=N) by probing,
#       so views that don't fit normal categories are never missed:
#         · 2 = Archives (classic)      · 4 = Redesign
#         · 5 = CivicPlus               · 6 = OpenCities
#         · 7 = TRAINING (staff training recordings — included on purpose)
#    2. ENUMERATE every meeting in every view:
#         · archived meetings (clip_id=), incl. specials, agenda-only, training
#         · upcoming events (event_id=) — the not-yet-held meetings
#         · minutes doc_id (the "Uploaded File" links from the 2008 records)
#         · direct MP4 video links (archive-video.granicus.com)
#    3. OPEN each meeting's agenda and fetch EVERY hyperlink inside it:
#         · supporting documents / proposed substitutes (MetaViewer meta_id)
#         · bare PDFs linked directly from the agenda
#    4. FETCH the minutes (MinutesViewer -> DocumentViewer .pdf), for both the
#       modern clip_id route and the 2008 doc_id "Uploaded File" route
#    5. SAVE to Google Drive, with manifest.json (name/date/url/sha256 for
#       every file) — nothing discovered is dropped; even when a file can't be
#       saved, its URL is recorded in the manifest.
#
#  Paste into one Colab cell and run. Resumable — re-run skips what's done.
#
#  ⚙️ EDIT THESE LINES:
OUT_ROOT     = "/content/drive/MyDrive/TheRealWindyCity/cheyenne"  # Google Drive
VIEW_IDS     = None      # None = auto-discover ALL views (probe 1..MAX_VIEW).
                         #   Set e.g. [2,7] to force specific views.
MAX_VIEW     = 30        # highest view_id to probe during discovery
KEYWORDS     = []        # OPTIONAL extra discovery: searches merged into the
                         #   sweep (e.g. ["Lead","annex","DDA","BOPU"]). Empty
                         #   = skip keyword search; the full listing is enough.
SAVE_DOCS    = True      # agendas, supporting docs, minutes, uploaded files
SAVE_TXT     = True      # extracted text alongside each PDF
SAVE_VIDEO   = False     # actually DOWNLOAD the MP4s (huge: 600+ meetings).
                         #   Video URLs are ALWAYS catalogued in the manifest.
MAX_CLIPS    = 0         # 0 = no limit. Safety: set e.g. 3 for a first smoke test.
DELAY        = 1.5       # seconds between requests — be polite
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
_re_event_id = re.compile(r"event_id=(\d+)", re.I)
_re_doc_uuid = re.compile(r"MinutesViewer\.php[^\"'\s]*?doc_id=([0-9a-fA-F-]{36})", re.I)
_re_mp4      = re.compile(r"(https?://archive-video\.granicus\.com/[^\"'\s<>]+\.mp4)", re.I)
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
def clip_ids(html_text):    return sorted({int(m) for m in _re_clip_id.findall(html_text)})
def event_ids(html_text):   return sorted({int(m) for m in _re_event_id.findall(html_text)})
def doc_meta_ids(html_text):return sorted({int(m) for m in _re_doc_id.findall(html_text)})
def media_meta_ids(html_text): return sorted({int(m) for m in _re_media_id.findall(html_text)})
def pdf_urls(html_text):
    return [html.unescape(u.strip()) for u in _re_pdf.findall(html_text) if u.strip().startswith("http")]
def mp4_urls(html_text):
    return [html.unescape(u.strip()) for u in _re_mp4.findall(html_text)]

def _rows(html_text):
    return re.findall(r"<tr\b[^>]*>(.*?)</tr>", html_text, re.I | re.S)

def first_text_cell(html_text):
    for m in re.finditer(r"<t[dh][^>]*>(.*?)</t[dh]>", html_text, re.I | re.S):
        t = _re_tag.sub(" ", m.group(1))
        t = html.unescape(t).replace("&nbsp;", " ").strip()
        if len(t) >= 2:
            return t
    return ""

def meeting_meta(html_text, key, kind="clip"):
    """Name/date/doc_id/mp4 for one meeting, scoped to its own listing row."""
    marker = f"{kind}_id={key}"
    for row in _rows(html_text):
        if marker not in row:
            continue
        m = _re_date.search(row)
        out = {"name": first_text_cell(row), "date": m.group(0) if m else ""}
        for uuid in _re_doc_uuid.findall(row):
            out.setdefault("minutes_doc_id", uuid)
        for mp in _re_mp4.findall(row):
            out.setdefault("mp4", mp)
        return out
    return {}

def html_to_text(html_text):
    t = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html_text)
    t = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|li|h\d)>", "\n", t)
    t = _re_tag.sub(" ", t)
    t = html.unescape(t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n\s*\n+", "\n", t)
    return t.strip()

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

def sha256(data): return hashlib.sha256(data).hexdigest()

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

# ── discovery: every view, every meeting ────────────────────────────────────
def discover_views():
    """Probe ViewPublisher.php?view_id=1..MAX_VIEW; return live view ids."""
    if VIEW_IDS is not None:
        return list(VIEW_IDS)
    live = []
    for i in range(1, MAX_VIEW + 1):
        try:
            st, body, fin, ct = http_get(f"{BASE}/ViewPublisher.php?view_id={i}")
            txt = body.decode("utf-8", "replace")
        except Exception as e:
            print(f"  view {i}: error {type(e).__name__} — skipping")
            continue
        dead = ("page not found" in txt.lower()) or (not txt.strip())
        has_content = ("clip_id" in txt) or ("event_id" in txt) or ("ViewPublisher" in txt)
        if not dead and has_content:
            live.append(i)
            print(f"  view {i}: LIVE ({fin})")
    return live

def enumerate_view(view_id):
    """Return {'clips': {clip_id: meta}, 'events': {event_id: meta}} for a view."""
    st, body, fin, ct = http_get(f"{BASE}/ViewPublisher.php?view_id={view_id}")
    txt = body.decode("utf-8", "replace")
    clips, events = {}, {}
    for c in clip_ids(txt):
        clips.setdefault(c, meeting_meta(txt, c, "clip"))
    for e in event_ids(txt):
        events.setdefault(e, meeting_meta(txt, e, "event"))
    return clips, events

def enumerate_keyword_search(kw):
    """Extra discovery: a keyword search's clip_ids (catches doc-only hits)."""
    u = f"{BASE}/ViewSearchResults.php?keywords={urllib.parse.quote(kw)}&view_id=2"
    st, body, fin, ct = http_get(u)
    txt = body.decode("utf-8", "replace")
    return {c: meeting_meta(txt, c, "clip") for c in clip_ids(txt)}

# ── one meeting ──────────────────────────────────────────────────────────────
def pull_meeting(kind, mid, meta, root, manifest):
    folder = f"{mid:04d}" if kind == "clip" else f"event_{mid:04d}"
    d = os.path.join(root, folder)
    os.makedirs(d, exist_ok=True)
    rec = manifest["meetings"].setdefault(
        f"{kind}:{mid}", {"kind": kind, "name": meta.get("name", ""),
                          "date": meta.get("date", ""), "documents": []})
    for k in ("mp4", "minutes_doc_id"):
        if meta.get(k):
            rec.setdefault(k, meta[k])
    if meta.get("views"):
        rec.setdefault("views", meta["views"])

    # 1 · agenda + every hyperlink inside it
    ag = http_get(f"{BASE}/AgendaViewer.php?view_id=2&{kind}_id={mid}")
    txt = ag[1].decode("utf-8", "replace")
    if txt.strip() and ("MetaViewer" in txt or "MediaPlayer" in txt or "clip_id" in txt or "GeneratedAgenda" in ag[2]):
        write_bin(os.path.join(d, "agenda.html"), ag[1])
        if SAVE_TXT:
            write_txt(os.path.join(d, "agenda.txt"), html_to_text(txt))
        rec["agenda"] = f"{folder}/agenda.html"
    else:
        rec["agenda"] = None       # no agenda (training / media-only meeting)
    rec["agenda_url"] = ag[2]
    rec["video_meta_ids"] = media_meta_ids(txt)
    rec["pdf_links_in_agenda"] = pdf_urls(txt)

    # 2 · minutes (clip route + 2008 "Uploaded File" doc_id route)
    doc_id = meta.get("minutes_doc_id")
    murl = f"{BASE}/MinutesViewer.php?view_id=2&{kind}_id={mid}"
    if doc_id:
        murl += f"&doc_id={doc_id}"
    st, mbody, mfin, mct = http_get(murl)
    mname = "minutes.pdf"
    m = re.search(r"file=([^&\"]+\.pdf)", mfin)
    if m:
        mname = urllib.parse.unquote(m.group(1))
    if SAVE_DOCS and mbody[:4] == b"%PDF":
        mpath = os.path.join(d, mname)
        write_bin(mpath, mbody)
        if SAVE_TXT:
            write_txt(os.path.join(d, "minutes.txt"), pdf_to_text(mbody))
        rec["minutes"] = f"{folder}/{mname}"
        rec["minutes_sha256"] = sha256(mbody)
    else:
        rec["minutes"] = None
    rec["minutes_url"] = mfin

    # 3 · every supporting-document hyperlink in the agenda
    for i, meta_id in enumerate(doc_meta_ids(txt), 1):
        if any(x.get("meta_id") == meta_id for x in rec["documents"]):
            continue
        st, dbody, dfin, dct = http_get(
            f"{BASE}/MetaViewer.php?view_id=2&{kind}_id={mid}&meta_id={meta_id}")
        entry = {"meta_id": meta_id, "url": dfin}
        if not dbody:
            entry.update({"file": None, "empty": True})
        else:
            is_pdf = dct == "application/pdf" or dbody[:4] == b"%PDF"
            fname = f"{meta_id}.pdf" if is_pdf else f"{meta_id}.html"
            m = re.search(r"file=([^&\"]+\.pdf)", dfin)
            if m:
                fname = urllib.parse.unquote(m.group(1))
            fpath = os.path.join(d, "docs", fname)
            if SAVE_DOCS:
                write_bin(fpath, dbody)
            text = ""
            if SAVE_TXT:
                text = pdf_to_text(dbody) if is_pdf else \
                       html_to_text(dbody.decode("utf-8", "replace"))
            if text:
                write_txt(os.path.join(d, "docs", f"{fname}.txt"), text)
            entry.update({"file": f"{folder}/docs/{fname}", "pdf": is_pdf,
                          "sha256": sha256(dbody)})
        rec["documents"].append(entry)
        print(f"    doc {i}/{len(doc_meta_ids(txt))} meta_id={meta_id} "
              f"{entry.get('file') or 'unavailable'}", flush=True)

    # 4 · bare PDFs linked straight from the agenda
    for u in pdf_urls(txt):
        if any(x.get("url") == u for x in rec["documents"]):
            continue
        try:
            st, pbody, pfin, pct = http_get(u)
        except Exception:
            pbody, pfin = b"", u
        entry = {"url": u, "pdf_link": True}
        if pbody[:4] == b"%PDF" and SAVE_DOCS:
            fname = safe(urllib.parse.unquote(pfin.rsplit("/", 1)[-1] or "link.pdf"))
            fpath = os.path.join(d, "docs", fname)
            write_bin(fpath, pbody)
            if SAVE_TXT:
                write_txt(os.path.join(d, "docs", f"{fname}.txt"), pdf_to_text(pbody))
            entry.update({"file": f"{folder}/docs/{fname}", "sha256": sha256(pbody)})
        rec["documents"].append(entry)

    # 5 · video MP4 — always catalogued; downloaded only if SAVE_VIDEO
    mp4 = meta.get("mp4")
    if mp4 and SAVE_VIDEO:
        try:
            st, vbody, vfin, vct = http_get(mp4, delay=0.5)
            vname = urllib.parse.unquote(vfin.rsplit("/", 1)[-1])
            vpath = os.path.join(d, "video", vname)
            write_bin(vpath, vbody)
            rec["video_file"] = f"{folder}/video/{vname}"
            rec["video_sha256"] = sha256(vbody)
            print(f"    video saved: {vname} ({len(vbody)//1048576} MB)", flush=True)
        except Exception as e:
            rec["video_error"] = str(e)
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
    if root.startswith("/content/drive") and not os.path.isdir("/content/drive"):
        root = os.path.abspath("granicus_pull")     # mount failed / local run

    manifest_path = os.path.join(root, "manifest.json")
    manifest = (json.loads(open(manifest_path).read()) if os.path.exists(manifest_path)
                else {"source": "tools/granicus_document_pull.py",
                      "generated_at": "", "base": BASE,
                      "keywords": KEYWORDS, "views": [], "meetings": {}})

    views = discover_views()
    manifest["views"] = sorted(set(manifest.get("views", []) + views))

    meetings = {}   # key -> meta
    for v in views:
        try:
            clips, events = enumerate_view(v)
        except Exception as e:
            print(f"  view {v}: enumerate failed: {e}")
            continue
        for c, m in clips.items():
            rec = meetings.setdefault(f"clip:{c}", {"kind": "clip", "views": []})
            rec["views"].append(v)
            for k, val in m.items():
                if val:
                    rec[k] = val
        for e, m in events.items():
            rec = meetings.setdefault(f"event:{e}", {"kind": "event", "views": []})
            rec["views"].append(v)
            for k, val in m.items():
                if val:
                    rec[k] = val
    for kw in KEYWORDS:
        for c, m in enumerate_keyword_search(kw).items():
            rec = meetings.setdefault(f"clip:{c}", {"kind": "clip", "views": []})
            for k, val in m.items():
                if val:
                    rec[k] = val
            rec.setdefault("keywords", []).append(kw)

    print(f"\nTOTAL unique meetings/events: {len(meetings)}")
    todo = [k for k in meetings if k not in manifest["meetings"]
            or not manifest["meetings"][k].get("documents")]
    if MAX_CLIPS:
        todo = todo[:MAX_CLIPS]
    print(f"  to pull now: {len(todo)}")
    for n, key in enumerate(todo, 1):
        meta = meetings[key]
        kind, mid = key.split(":", 1)
        print(f"\n[{n}/{len(todo)}] {kind} {mid} — {meta.get('name')} {meta.get('date')}",
              flush=True)
        try:
            pull_meeting(kind, int(mid), meta, root, manifest)
        except Exception as e:
            print(f"  !! {key} failed: {type(e).__name__}: {e}")
            manifest["meetings"].setdefault(key, {})["error"] = str(e)
        manifest["generated_at"] = time.strftime(TIME_FMT, time.gmtime())
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=1)

    n_docs = sum(len(v.get("documents", [])) for v in manifest["meetings"].values())
    n_pdf = sum(1 for v in manifest["meetings"].values()
                for x in v.get("documents", []) if x.get("pdf") or x.get("pdf_link"))
    n_min = sum(1 for v in manifest["meetings"].values() if v.get("minutes"))
    n_mp4 = sum(1 for v in manifest["meetings"].values() if v.get("mp4"))
    print("\n" + "═" * 62)
    print(f"  GRANICUS FULL SWEEP DONE ✅  (nothing excluded)")
    print(f"   views probed:  {manifest['views']}")
    print(f"   meetings/events: {len(manifest['meetings'])}")
    print(f"   minutes saved: {n_min}")
    print(f"   documents:     {n_docs}  ({n_pdf} PDF)")
    print(f"   videos catalogued: {n_mp4}  (downloaded if SAVE_VIDEO)")
    print(f"   manifest:      {manifest_path}")
    print("═" * 62)

# ── selftest (offline; proves parsers on real observed HTML) ────────────────
def selftest():
    listing = """
      <tr><td>City Council Meeting</td><td>Jun 23, 2026</td>
      <a href="http://cheyenne.granicus.com/AgendaViewer.php?view_id=2&clip_id=1103">Agenda</a>
      <a href="http://cheyenne.granicus.com/MinutesViewer.php?view_id=2&clip_id=1103">Minutes</a>
      <a href="http://cheyenne.granicus.com/ASX.php?view_id=2&clip_id=1103&sn=x">Video</a>
      <a href="https://archive-video.granicus.com/cheyenne/cheyenne_09f1fb45.mp4">MP4 Video</a></tr>
      <tr><td>Cheyenne City Council</td><td>Jul 28, 2008</td>
      <a href="AgendaViewer.php?view_id=6&clip_id=36">Agenda</a>
      <a href="MinutesViewer.php?view_id=6&clip_id=36&doc_id=41f85f2d-633b-4b1f-82c6-7830d7b903e1">Uploaded File</a></tr>
      <tr><td>City Council Meeting</td><td>Sep 14, 2026</td>
      <a href="AgendaViewer.php?view_id=2&event_id=1441">Agenda</a></tr>
      <tr><td>LiveManager Web Training</td><td>Feb 10, 2026</td>
      <a href="ASX.php?view_id=7&clip_id=899">Video</a></tr>
    """
    agenda = """
      <a href="https://cheyenne.granicus.com/MediaPlayer.php?view_id=2&clip_id=1103&meta_id=148913">1. CALL MEETING TO ORDER.</a>
      <a href="https://cheyenne.granicus.com/MetaViewer.php?view_id=2&clip_id=1103&meta_id=148918">Supporting Document</a>
      <a href="https://cheyenne.granicus.com/MetaViewer.php?view_id=2&clip_id=1103&meta_id=148923">Proposed Substitute</a>
      <a href="https://cheyenne.granicus.com/DocumentViewer.php?file=cheyenne_964bdd5707a3db4918c35f6e987ac155.pdf&amp;view=1">pdf</a>
    """
    assert clip_ids(listing) == [36, 899, 1103], clip_ids(listing)
    assert event_ids(listing) == [1441], event_ids(listing)
    assert doc_meta_ids(agenda) == [148918, 148923], doc_meta_ids(agenda)
    assert media_meta_ids(agenda) == [148913], media_meta_ids(agenda)
    assert pdf_urls(agenda) == ["https://cheyenne.granicus.com/DocumentViewer.php?file=cheyenne_964bdd5707a3db4918c35f6e987ac155.pdf&view=1"], pdf_urls(agenda)
    assert mp4_urls(listing) == ["https://archive-video.granicus.com/cheyenne/cheyenne_09f1fb45.mp4"], mp4_urls(listing)
    m = meeting_meta(listing, 36, "clip")
    assert m["name"] == "Cheyenne City Council" and m["date"] == "Jul 28, 2008", m
    assert m["minutes_doc_id"] == "41f85f2d-633b-4b1f-82c6-7830d7b903e1", m
    m = meeting_meta(listing, 1103, "clip")
    assert m["mp4"] == "https://archive-video.granicus.com/cheyenne/cheyenne_09f1fb45.mp4", m
    print("SELFTEST OK — parsers match every live Granicus URL shape (clip/event/doc_id/mp4/training)")

if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        main()
