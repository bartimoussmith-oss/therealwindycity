#!/usr/bin/env python3
"""build_ai_record.py - generate ai-record/, the AI-readable mirror of the
Cheyenne public-meetings record.

Every meeting gets one Markdown page. Every archived document gets a
plain-text Markdown file with page markers, a quality label, and links back
to the original file. Transcripts and Records of Proceedings are copied in
next to the meeting they belong to. Indexes (year, body, keyword, statute,
ordinance) and llms.txt tie it together.

Inputs (all local; see tools/README-ai-record.md):
  --meetings   meetings.json from TheReelWindyCity (node scripts/build-data.mjs)
  --text       directory of <blob-sha>.json extraction records (extract step)
  --ocr        optional directory of <blob-sha>.json OCR records {page_index: text}
  --transcripts  checkout of therealwindycity/The-Real-Windy-City-
  --minutes    pipeline/corpus (Records of Proceedings text, 2008-2026)
  --trees      directory holding tree_<repo>.json (git tree snapshots)
  --drive-db   optional WindyCityMeetings caption-transcript database
               (drive-import/master_meetings_database.json.gz; see tools/ai_record_drive.py)

Output is deterministic: same inputs, same bytes.
"""
import argparse, collections, html, json, os, re, shutil, sys, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ai_record_drive
from datetime import date

SITE = "https://bartimoussmith-oss.github.io/therealwindycity/"
REPO_BLOB = "https://github.com/bartimoussmith-oss/therealwindycity/blob/main/ai-record/"
ORG = "therealwindycity"
PART_CHARS = 150_000          # split long documents so web fetchers don't truncate
INLINE_MINUTES = 70_000

BODY_LABELS = {
    "city-council": "City Council", "finance-committee": "Finance Committee",
    "public-services-committee": "Public Services Committee", "work-sessions": "Work Session / Committee of the Whole",
    "board-of-adjustment": "Board of Adjustment", "historic-preservation-board": "Historic Preservation Board",
    "planning-commission": "Planning Commission", "urban-renewal-authority": "Urban Renewal Authority",
    "board-of-county-commissioners": "Laramie County Board of County Commissioners",
    "work-session": "Work Session / Committee of the Whole",
}
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]

# Watch terms for the keyword index. Patterns are case-insensitive.
KEYWORDS = [
    ("Annexation", r"\bannex(?:ation|ed|ing)?\b"),
    ("Data center", r"\bdata[- ]?cent(?:er|re)s?\b"),
    ("Microsoft", r"\bmicrosoft\b"),
    ("Project Jade", r"\bproject jade\b"),
    ("Project Latigo", r"\bproject latigo\b"),
    ("Cox Ranch", r"\bcox ranch\b"),
    ("Roundtop Road / Happy Jack Road", r"\b(?:round ?top road|happy jack road)\b"),
    ("Chapter 1.28 / administrative inspection warrants", r"\b(?:chapter 1\.28|inspection warrants?)\b"),
    ("Referendum", r"\breferend(?:um|a)\b"),
    ("Sixth-penny sales tax", r"\b(?:6th|sixth)[- ]penny\b"),
    ("Fifth-penny sales tax", r"\b(?:5th|fifth)[- ]penny\b"),
    ("Sole source", r"\bsole[- ]source\b"),
    ("Roundabout", r"\broundabouts?\b"),
    ("Ardurra", r"\bardurra\b"),
    ("Musco", r"\bmusco\b"),
    ("Board of Public Utilities (BOPU)", r"\b(?:bopu|board of public utilities)\b"),
    ("Water rights / water use", r"\bwater (?:rights?|usage|use)\b"),
    ("Moratorium", r"\bmoratori(?:um|a)\b"),
    ("Executive session", r"\bexecutive session\b"),
    ("Downtown Development Authority (DDA)", r"\b(?:downtown development authority|DDA)\b"),
    ("Unified Development Code (UDC)", r"\b(?:unified development code|UDC)\b"),
    ("Public comment", r"\bpublic comments?\b"),
    ("First Amendment", r"\bfirst amendment\b"),
    ("Wyoming Public Records Act", r"\bpublic records act\b"),
    ("Wyoming Public Meetings Act", r"\bpublic meetings? act\b"),
    ("Zoning / rezoning", r"\b(?:re)?zon(?:ing|ed)\b"),
    ("Tax increment / urban renewal", r"\b(?:tax increment|urban renewal)\b"),
    ("Charles Miller (public commenter)", r"\bcharles miller\b"),
]
KW_RE = [(k, re.compile(p, re.I)) for k, p in KEYWORDS]
STATUTE_RE = re.compile(r"\b(?:W\.?\s?S\.?|Wyo(?:ming)?\.?\s+Stat(?:ute)?s?\.?(?:\s+Ann\.)?|Wyoming\s+statute\s+(?:section\s+)?|§+)\s*(\d{1,2})[-‐–](\d{1,2})[-‐–](\d{3,4})", re.I)
ORD_RE = re.compile(r"\(#\s?(\d{4})\)")


def iso_label(d):
    y, m, dd = map(int, d.split("-"))
    wd = WEEKDAYS[date(y, m, dd).weekday()]
    return f"{wd}, {MONTHS[m-1]} {dd}, {y}"


def gh_blob(repo, path):
    return f"https://github.com/{ORG}/{repo}/blob/main/" + urllib.parse.quote(path)


def gh_raw(repo, path):
    return f"https://raw.githubusercontent.com/{ORG}/{repo}/main/" + urllib.parse.quote(path)


def slugify(s, n=70):
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()
    return (s[:n].rstrip("-") or "document")


def doc_title(path):
    name = path.split("/")[-1]
    name = re.sub(r"\.(pdf|bin)$", "", name, flags=re.I)
    name = re.sub(r"^\d{9,10}[A-Z][a-z]{2}\s+\d{1,2},\s*\d{4}\s*-\s*", "", name)
    parts = [p.strip() for p in name.split(" - ")]
    # "Meeting - X - X" -> "X"
    if len(parts) >= 3 and parts[-1] == parts[-2]:
        parts = parts[:-1]
    if len(parts) >= 2 and re.search(r"meeting|council|committee|session|board", parts[0], re.I):
        parts = parts[1:]
    t = " - ".join(parts).replace("_", " ").strip()
    t = re.sub(r"\s+", " ", t)
    return t or name


def doc_kind(path):
    p = path.lower()
    n = p.split("/")[-1]
    if "minutes" in n or "record of proceedings" in n: return "Minutes"
    if "agenda" in n and "packet" not in n: return "Agenda"
    if "_packet" in n or "packet-" in n: return "Agenda packet item"
    if "backup_doc" in n: return "Backup document"
    if "substitut" in n: return "Proposed substitute"
    if "supporting" in p: return "Supporting document"
    return "Document"


def clean_text(t):
    t = t.replace("\r", "").replace("\x00", "").replace("\u00a0", " ")
    t = re.sub(r"[ \t]+\n", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def alnum(t):
    return sum(c.isalnum() for c in t)


def is_stub_html(txt):
    return alnum(txt) < 250 or ("Juneteenth" in txt and "opens in new tab" in txt)


def fence(t):
    t = t.replace("```", "\u02bc\u02bc\u02bc")
    return "```text\n" + t + "\n```"


def md_inline(s):
    s = s.replace("\\", "\\\\").replace("<", "&lt;")
    return re.sub(r"([*_\[\]`#|])", r"\\\1", s)


def md_escape_cell(s):
    return md_inline(s).replace("\n", " ")


class Builder:
    def __init__(self, a):
        self.a = a
        self.out = a.out
        mj = json.load(open(a.meetings))
        self.meetings = [m for m in mj["meetings"]]
        self.sizes = {}
        for f in os.listdir(a.trees):
            if f.startswith("tree_cheyenne-archives") and f.endswith(".json"):
                repo = f[5:-5]
                for x in json.load(open(os.path.join(a.trees, f)))["tree"]:
                    if x["type"] == "blob":
                        self.sizes[(repo, x["path"])] = (x["sha"], x.get("size", 0))
        self.kw_hits = collections.defaultdict(list)       # kw -> [(meeting, count, link)]
        self.statutes = collections.defaultdict(lambda: collections.Counter())
        self.ordinances = collections.defaultdict(set)
        self.files = []
        self.quality = collections.Counter()
        self.pages_total = 0
        self.chars_total = 0
        self.rendered = {}
        self.tparts = {}

    # ------------------------------------------------------------- utils
    def write(self, rel, text):
        path = os.path.join(self.out, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text.rstrip() + "\n")
        self.files.append(rel)

    @staticmethod
    def rel(from_rel, to_rel):
        return os.path.relpath(to_rel, os.path.dirname(from_rel)).replace(os.sep, "/")

    def year_of(self, m):
        return m["date"][:4]

    def mpath(self, m):
        return f"meetings/{self.year_of(m)}/{m['id']}.md"

    def dpath(self, m, slug):
        return f"documents/{self.year_of(m)}/{m['id']}/{slug}.md"

    # --------------------------------------------------- per-document text
    def load_doc(self, repo, path):
        sha, size = self.sizes.get((repo, path), (None, 0))
        rec = None
        if sha:
            fp = os.path.join(self.a.text, sha + ".json")
            if os.path.exists(fp):
                rec = json.load(open(fp))
        ocr = {}
        if sha and self.a.ocr:
            op = os.path.join(self.a.ocr, sha + ".json")
            if os.path.exists(op):
                ocr = {int(k): v for k, v in json.load(open(op)).items()}
        return sha, size, rec, ocr

    def render_doc(self, m, d, slug, used_text_sink):
        repo, path = d["repo"], d["path"]
        sha, size, rec, ocr = self.load_doc(repo, path)
        title = doc_title(path)
        kind = doc_kind(path)
        meeting_label = f"{BODY_LABELS.get(m['body'], m['body'])} — {iso_label(m['date'])}"
        pages_md, status, n_pages, image_pages, ocr_pages = [], "", 0, [], []
        if rec is None:
            status = "not extracted (file missing from snapshot)"
        elif rec["kind"] == "pdf":
            pages = rec["pages"]; n_pages = len(pages)
            for i, p in enumerate(pages):
                t = clean_text(p)
                if alnum(t) < 25:
                    if i in ocr and alnum(ocr[i]) >= 25:
                        ocr_pages.append(i + 1)
                        pages_md.append(f"### Page {i+1} of {n_pages} (scanned page: machine OCR, may contain errors)\n\n{fence(clean_text(ocr[i]))}")
                    else:
                        image_pages.append(i + 1)
                        pages_md.append(f"### Page {i+1} of {n_pages} (scanned page: no text layer yet; see the original PDF)")
                else:
                    pages_md.append(f"### Page {i+1} of {n_pages}\n\n{fence(t)}")
            if n_pages == 0:
                status = "PDF has no pages"
            elif not image_pages and not ocr_pages:
                status = "full text"
            elif len(image_pages) == n_pages:
                status = "image-only scan: no text layer (OCR pending)"
            elif ocr_pages and not image_pages:
                status = f"full text ({len(ocr_pages)} of {n_pages} pages via machine OCR)"
            else:
                status = f"partial text ({len(image_pages)} of {n_pages} pages image-only" + (f", {len(ocr_pages)} via OCR" if ocr_pages else "") + ")"
        elif rec["kind"] == "html":
            t = clean_text(rec["pages"][0] if rec["pages"] else "")
            if is_stub_html(t):
                status = "capture failed: the file is a web error page or the wrong page, not the document"
                pages_md.append(fence(t[:1500]) if t else "(empty)")
            else:
                status = "agenda saved as an HTML web page (named .pdf); text recovered"
                pages_md.append(fence(t))
            n_pages = 1
        elif rec["kind"] == "empty":
            status = "empty file (capture failed)"
        else:
            t = clean_text(rec["pages"][0] if rec["pages"] else "")
            status = "unrecognized file format" + ("" if alnum(t) < 250 else "; text shown as found")
            if alnum(t) >= 250: pages_md.append(fence(t))
        self.quality[status.split(":")[0].split("(")[0].strip()] += 1
        self.pages_total += n_pages
        body = "\n\n".join(pages_md)
        self.chars_total += len(body)
        used_text_sink.append(body)

        header = [
            f"# {md_inline(title)}",
            "",
            f"*{kind} from the {meeting_label} meeting, City of Cheyenne, Wyoming. Plain-text copy for reading and search. The original file is the authoritative version.*",
            "",
            f"- **Meeting:** [{meeting_label}]({self.rel(self.dpath(m, slug), self.mpath(m))})",
            f"- **Document type:** {kind}",
            f"- **Text status:** {status}",
            f"- **Pages:** {n_pages}" + (f" (image-only pages: {', '.join(map(str, image_pages[:40]))}{' …' if len(image_pages) > 40 else ''})" if image_pages else ""),
            f"- **Original file:** [{path}]({gh_blob(repo, path)}) in `{ORG}/{repo}` ([direct download]({gh_raw(repo, path)}))",
            f"- **File size:** {size:,} bytes" + (f" · git blob `{sha[:12]}`" if sha else ""),
            "- **Extraction:** PyMuPDF text layer" + ("; RapidOCR for image-only pages" if ocr_pages else "") + ". Wording is unchanged; line breaks and table layout may differ from the PDF.",
            "",
        ]
        parts = []
        if len(body) > PART_CHARS:
            cur = []
            for block in pages_md:
                if cur and sum(len(x) for x in cur) + len(block) > PART_CHARS:
                    parts.append("\n\n".join(cur)); cur = []
                cur.append(block)
            if cur: parts.append("\n\n".join(cur))
        if len(parts) > 1:
            listing = [f"This document is long, so it is split into {len(parts)} parts:"]
            for i in range(len(parts)):
                listing.append(f"- [Part {i+1}]({slug}.part{i+1}.md)")
            self.write(self.dpath(m, slug), "\n".join(header + listing))
            for i, c in enumerate(parts):
                nav = f"[← document overview]({slug}.md)"
                if i > 0: nav += f" · [← part {i}]({slug}.part{i}.md)"
                if i < len(parts) - 1: nav += f" · [part {i+2} →]({slug}.part{i+2}.md)"
                self.write(f"documents/{self.year_of(m)}/{m['id']}/{slug}.part{i+1}.md",
                           f"# {title}, part {i+1} of {len(parts)}\n\n*{meeting_label}. Original: [{path.split('/')[-1]}]({gh_blob(repo, path)})*\n\n{nav}\n\n---\n\n{c}\n\n---\n\n{nav}")
        else:
            self.write(self.dpath(m, slug), "\n".join(header + ["---", "", body or "*(No extractable text. Open the original file.)*"]))
        excerpt = re.sub(r"### Page \d+ of \d+[^\n]*|```(?:text)?", " ", body)
        excerpt = md_inline(re.sub(r"\s+", " ", excerpt).strip()[:220])
        return {"title": title, "kind": kind, "status": status, "pages": n_pages, "slug": slug,
                "excerpt": excerpt, "url": gh_blob(repo, path), "path": self.dpath(m, slug), "meeting": m["id"]}

    # ------------------------------------------------------- transcripts
    def transcripts_for(self, m):
        prim = m.get("transcript")
        out = [prim] if prim else []
        for t in m.get("transcripts", []) or []:
            if prim and t["path"] == prim["path"]: continue
            if prim and t["path"].replace(".clean.md", ".md") == prim["path"].replace(".clean.md", ".md"): continue
            out.append(t)
        return out

    def render_transcript(self, m, used_text_sink, t=None, name="transcript", label=None, rel_base=None):
        t = t or m.get("transcript")
        if not t: return None
        fp = os.path.join(self.a.transcripts, t["path"])
        if not os.path.exists(fp): return None
        raw = open(fp, encoding="utf-8").read()
        yt = re.search(r"YouTube ID:\*\*\s*`([A-Za-z0-9_-]{6,})`", raw)
        ytid = yt.group(1) if yt else None
        body = raw.split("\n---\n", 1)[1] if "\n---\n" in raw else raw
        body = body.replace("<", "&lt;").replace("*", "\\*").replace("_", "\\_")
        # add YouTube jump links to timestamps
        if ytid:
            def link(mm):
                h, mi, s = map(int, mm.group(1).split(":"))
                return f"[[{mm.group(1)}]](https://www.youtube.com/watch?v={ytid}&t={h*3600+mi*60+s}s)"
            body_linked = re.sub(r"^\[(\d{2}:\d{2}:\d{2})\]", link, body, flags=re.M)
        else:
            body_linked = body
        used_text_sink.append(body)
        label = label or f"{BODY_LABELS.get(m['body'], m['body'])} — {iso_label(m['date'])}"
        rel_base = rel_base or f"documents/{self.year_of(m)}/{m['id']}/{name}"
        meeting_line = f"- **Meeting:** [{label}]({self.rel(rel_base + '.md', self.mpath(m))})" if m else f"- **Meeting:** {label}"
        head = [
            f"# Transcript: {label}",
            "",
            f"*Verbatim auto-caption transcript of the {label} meeting, Cheyenne, Wyoming. Each timestamp links to that moment in the official video.*",
            "",
            meeting_line,
            f"- **Official video:** https://www.youtube.com/watch?v={ytid}" if ytid else "- **Official video:** (not linked)",
            f"- **Source file:** [{t['path']}]({gh_blob(t['repo'], t['path'])})",
            "- **Accuracy:** auto-generated captions. Names and numbers are often misheard (examples: Segrave → \"Crave\", Esquibel → \"Escoel\", W.S. 16-4-403 → \"16443\", Ardurra → \"Adura\"). Check quotes against the video before relying on them.",
            "",
        ]
        chunks, cur = [], ""
        for para in body_linked.split("\n\n"):
            if len(cur) + len(para) > PART_CHARS and cur:
                chunks.append(cur); cur = para
            else:
                cur = cur + "\n\n" + para if cur else para
        if cur: chunks.append(cur)
        def secs(c):
            f = re.search(r"\[\[?(\d{2}):(\d{2}):(\d{2})\]", c)
            return int(f.group(1)) * 3600 + int(f.group(2)) * 60 + int(f.group(3)) if f else 0
        self.tparts[rel_base] = [(secs(c), f"{rel_base}.part{i+1}.md" if len(chunks) > 1 else rel_base + ".md") for i, c in enumerate(chunks)]
        if len(chunks) <= 1:
            self.write(rel_base + ".md", "\n".join(head + ["---", "", body_linked]))
        else:
            listing = [f"The transcript is long, so it is split into {len(chunks)} parts:"]
            for i, c in enumerate(chunks):
                first = re.search(r"\[\[(\d{2}:\d{2}:\d{2})\]\]|\[(\d{2}:\d{2}:\d{2})\]", c)
                st = (first.group(1) or first.group(2)) if first else ""
                listing.append(f"- [Part {i+1}]({os.path.basename(rel_base)}.part{i+1}.md)" + (f" — from {st}" if st else ""))
            self.write(rel_base + ".md", "\n".join(head + listing))
            for i, c in enumerate(chunks):
                bn = os.path.basename(rel_base)
                nav = f"[← transcript overview]({bn}.md)"
                if i > 0: nav += f" · [← part {i}]({bn}.part{i}.md)"
                if i < len(chunks) - 1: nav += f" · [part {i+2} →]({bn}.part{i+2}.md)"
                self.write(f"{rel_base}.part{i+1}.md", f"# Transcript: {label}, part {i+1} of {len(chunks)}\n\n{nav}\n\n---\n\n{c}\n\n---\n\n{nav}")
        return {"ytid": ytid, "path": rel_base + ".md", "words": len(body.split()), "source": t["path"]}

    # ------------------------------------------------- caption database
    DRIVE_SRC = "WindyCityMeetings/processed_database/master_meetings_database.json (Google Drive), committed as drive-import/master_meetings_database.json.gz"

    def render_caption(self, rec, rel_base, label, m=None, note=None):
        paras = [ai_record_drive.md_safe(p) for p in ai_record_drive.paragraphs(rec["text"])]
        dsrc = {"database": "from the database", "title": "read from the video title"}.get(rec["date_source"], "")
        head = [
            f"# Caption transcript: {label}",
            "",
            f"*Machine caption transcript of {md_inline(rec['title'])}, a City of Cheyenne, Wyoming public session, from the WindyCityMeetings database. "
            "The wording is the automatic captions, unchanged. There are no timestamps or punctuation, so it is wrapped into paragraphs for reading.*",
            "",
        ]
        if m is not None:
            head.append(f"- **Meeting:** [{BODY_LABELS.get(m['body'], m['body'])} — {iso_label(m['date'])}]({self.rel(rel_base + '.md', self.mpath(m))})")
        head += [
            f"- **Video title:** {md_inline(rec['title'])}",
            f"- **Date:** {rec['date'] + ' (' + dsrc + ')' if rec['date'] else 'not given in the database or the title'}",
            f"- **Database category:** {md_inline(rec['category'] or '')}" + (f" ({note})" if note else ""),
            f"- **Length:** {rec['words']:,} words",
            f"- **Database record:** `{rec['id']}` (source file `{rec['filename']}`)",
            f"- **Source:** {self.DRIVE_SRC}",
            "- **Accuracy:** automatic captions. Names and numbers are often misheard, and speakers are not identified. Check quotes against the official video or minutes before relying on them.",
            "",
        ]
        if rec.get("dup_of"):
            head += [f"*This record has the same text as database record `{rec['dup_of']}`.*", ""]
        chunks, cur = [], []
        size = 0
        for pgh in paras:
            if size + len(pgh) > PART_CHARS and cur:
                chunks.append(cur); cur, size = [], 0
            cur.append(pgh); size += len(pgh) + 2
        if cur: chunks.append(cur)
        bn = os.path.basename(rel_base)
        if len(chunks) <= 1:
            self.write(rel_base + ".md", "\n".join(head + ["---", ""]) + "\n" + "\n\n".join(chunks[0] if chunks else ["(no text)"]))
        else:
            listing = [f"The transcript is long, so it is split into {len(chunks)} parts:"] + \
                      [f"- [Part {i+1}]({bn}.part{i+1}.md)" for i in range(len(chunks))]
            self.write(rel_base + ".md", "\n".join(head + listing))
            for i, c in enumerate(chunks):
                nav = f"[← transcript overview]({bn}.md)"
                if i > 0: nav += f" · [← part {i}]({bn}.part{i}.md)"
                if i < len(chunks) - 1: nav += f" · [part {i+2} →]({bn}.part{i+2}.md)"
                self.write(f"{rel_base}.part{i+1}.md", f"# Caption transcript: {label}, part {i+1} of {len(chunks)}\n\n{nav}\n\n---\n\n" + "\n\n".join(c) + f"\n\n---\n\n{nav}")
        return {"path": rel_base + ".md", "words": rec["words"], "title": rec["title"], "id": rec["id"], "note": note}

    def attach_drive(self, by_key):
        """Attach caption records to meetings; create meetings for dated records of a known body."""
        self.drive = ai_record_drive.load(self.a.drive_db) if getattr(self.a, "drive_db", None) else []
        self.drive_loose = []
        by_date = collections.defaultdict(list)
        for m in self.meetings:
            by_date[m["date"]].append(m)
        for r in self.drive:
            m, note = None, None
            if r["date"] and r["body"]:
                m = by_key.get((r["body"], r["date"]))
                same_day = by_date.get(r["date"], [])
                if (m is None and len(same_day) == 1 and r["body"] in ("city-council", "work-sessions")
                        and same_day[0]["body"] in ("city-council", "work-sessions")):
                    m = by_date[r["date"]][0]
                    note = f"attached to the only meeting on this date; the database labels it {r['category']}"
                if m is None:
                    m = {"id": f"{r['body']}-{r['date']}", "body": r["body"], "date": r["date"], "docs": [], "official": {},
                         "notes": ["known only from a recorded video in the caption-transcript database; no archived documents. The date comes from the database or the video title and is not confirmed by an agenda (it may be the upload date)"]}
                    self.meetings.append(m); by_key[(r["body"], r["date"])] = m; by_date[r["date"]].append(m)
            if m is not None:
                m.setdefault("_cap_recs", []).append((r, note))
            else:
                self.drive_loose.append(r)

    # ----------------------------------------------------------- minutes
    def minutes_by_date(self):
        out = collections.defaultdict(list)
        for f in sorted(os.listdir(self.a.minutes)):
            mm = re.match(r"(\d+)_(\d{4}-\d{2}-\d{2})\.txt$", f)
            if mm:
                out[mm.group(2)].append((mm.group(1), os.path.join(self.a.minutes, f)))
        return out

    # -------------------------------------------------------------- main
    def build(self):
        if os.path.exists(self.out):
            shutil.rmtree(self.out)
        os.makedirs(self.out)
        minutes = self.minutes_by_date()
        # attach minutes to city-council meetings (create a meeting entry if missing)
        by_key = {(m["body"], m["date"]): m for m in self.meetings}
        for d, lst in minutes.items():
            if ("city-council", d) not in by_key:
                m = {"id": f"city-council-{d}", "body": "city-council", "date": d, "docs": [], "official": {}}
                self.meetings.append(m); by_key[("city-council", d)] = m
            by_key[("city-council", d)]["_minutes"] = lst
        self.attach_drive(by_key)
        self.meetings.sort(key=lambda m: (m["date"], m["body"], m["id"]))
        seq = collections.defaultdict(list)
        for m in self.meetings:
            seq[m["body"]].append(m)

        summaries = []
        for m in self.meetings:
            texts = []
            docs_info = []
            used = set()
            # minutes first
            mins = []
            for clip, fp in m.get("_minutes", []):
                raw = open(fp, encoding="utf-8", errors="ignore").read()
                body = raw.split("\n", 2)[2] if raw.startswith("MEETING:") else raw
                body = clean_text(body)
                texts.append(body)
                mins.append((clip, body))
            seen_here = set()
            for d in sorted(m["docs"], key=lambda d: (doc_kind(d["path"]) != "Agenda", doc_kind(d["path"]) != "Minutes", d["path"])):
                sha = self.sizes.get((d["repo"], d["path"]), (None, 0))[0]
                if sha and sha in seen_here:
                    continue                      # identical file archived twice for this meeting
                if sha and sha in self.rendered:
                    prev = dict(self.rendered[sha]); prev["dup_of"] = prev["meeting"]
                    docs_info.append(prev); seen_here.add(sha)
                    continue
                base = slugify(doc_title(d["path"]))
                slug, k = base, 2
                while slug in used:
                    slug = f"{base}-{k}"; k += 1
                used.add(slug)
                info = self.render_doc(m, d, slug, texts)
                docs_info.append(info)
                if sha:
                    self.rendered[sha] = info; seen_here.add(sha)
            trs = []
            for k, t in enumerate(self.transcripts_for(m)):
                r = self.render_transcript(m, texts, t=t, name="transcript" if k == 0 else f"transcript-{k+1}")
                if r: trs.append(r)
            tr = trs[0] if trs else None
            m["_trs"] = trs
            caps = []
            for k, (r, note) in enumerate(m.get("_cap_recs", [])):
                if r.get("dup_of") and any(c["id"] == r["dup_of"] for c in caps):
                    continue                        # identical text already shown for this meeting
                name = "captions" if k == 0 else f"captions-{k+1}"
                caps.append(self.render_caption(r, f"documents/{self.year_of(m)}/{m['id']}/{name}",
                                                f"{BODY_LABELS.get(m['body'], m['body'])} — {iso_label(m['date'])}", m, note))
                texts.append(r["text"])
            m["_caps"] = caps
            alltext = "\n".join(texts)
            kws = []
            for k, rx in KW_RE:
                n = len(rx.findall(alltext))
                if n:
                    kws.append((k, n)); self.kw_hits[k].append((m, n))
            for mm in STATUTE_RE.finditer(alltext):
                self.statutes[f"{int(mm.group(1))}-{int(mm.group(2))}-{mm.group(3)}"][m["id"]] += 1
            for mm in ORD_RE.finditer("\n".join(b for _, b in mins)):
                self.ordinances[mm.group(1)].add(m["id"])
            m["_kws"] = kws
            self.write_meeting(m, docs_info, tr, mins, seq[m["body"]])
            summaries.append((m, len(docs_info), bool(tr or caps), bool(mins), sum(1 for x in docs_info if x["status"].startswith(("full text", "agenda saved")))))
        self.m_by_id = {m["id"]: m for m in self.meetings}
        bound = {t["path"] for m in self.meetings for t in ([m.get("transcript")] if m.get("transcript") else []) + (m.get("transcripts") or [])}
        self.undated = []
        troot = os.path.join(self.a.transcripts, "cheyenne-2026-transcripts")
        for root, _, fs in os.walk(troot):
            for f in sorted(fs):
                rp = os.path.relpath(os.path.join(root, f), self.a.transcripts).replace(os.sep, "/")
                if not f.endswith(".md") or f == "README.md" or rp in bound or "/raw/" in rp: continue
                title = open(os.path.join(root, f), encoding="utf-8").readline().lstrip("# ").strip()
                r = self.render_transcript(None, [], t={"repo": "The-Real-Windy-City-", "path": rp}, label=title + " (date not published)",
                                           rel_base=f"documents/2026/undated/{slugify(f[:-3])}")
                if r: self.undated.append((title, r))
        self.loose_pages = []
        for r in self.drive_loose:
            y = r["date"][:4] if r["date"] else "undated"
            slug = slugify(r["title"]) or r["id"]
            rel_base = f"transcripts/{y}/{slug}-{r['id'].replace('_', '-')}"
            info = self.render_caption(r, rel_base, md_inline(r["title"]) + (f" ({r['date']})" if r["date"] else ""))
            self.loose_pages.append((r, info))
        self.write_indexes(summaries)

    def write_meeting(self, m, docs, tr, mins, seq):
        rel = self.mpath(m)
        label = BODY_LABELS.get(m["body"], m["body"])
        dl = iso_label(m["date"])
        lines = [f"# {label} — {dl}", "",
                 f"*Public meeting of the {label}, Cheyenne, Wyoming, held {dl}. This page links every archived document for the meeting as plain text, any transcripts of the meeting video, and the official Record of Proceedings where available.*", "",
                 f"- **Meeting ID:** `{m['id']}`",
                 f"- **Body:** {label}",
                 f"- **Date:** {m['date']}"]
        notes = [n for n in m.get("notes", []) if n]
        if notes: lines.append(f"- **Notes:** {'; '.join(notes)}")
        if m.get("upcoming"): lines.append("- **Status:** upcoming at the time of the snapshot")
        caps = m.get("_caps", [])
        lines.append(f"- **Archived documents:** {len(docs)}" + (f" · **Transcript:** yes ({tr['words']:,} words)" if tr else "")
                     + (f" · **Caption transcript:** yes ({sum(c['words'] for c in caps):,} words)" if caps else "")
                     + (" · **Official minutes text:** yes" if mins else ""))
        i = seq.index(m)
        yr = m["date"][:4]; yrel = f"years/{yr}.md"; brel = f"bodies/{m['body']}.md"
        nav = [f"[Year {yr}]({self.rel(rel, yrel)})",
               f"[All {label} meetings]({self.rel(rel, brel)})",
               f"[Home]({self.rel(rel, 'README.md')})"]
        if i > 0: nav.insert(0, f"[← previous {label}]({self.rel(rel, self.mpath(seq[i-1]))})")
        if i < len(seq) - 1: nav.append(f"[next {label} →]({self.rel(rel, self.mpath(seq[i+1]))})")
        lines += ["", " · ".join(nav), ""]
        off = m.get("official") or {}
        if off:
            lines += ["## Official sources (City of Cheyenne)", ""]
            for k in ("agenda", "minutes", "video", "granicus"):
                if off.get(k): lines.append(f"- **{k.capitalize()}:** {off[k]}")
            lines.append("")
        if m.get("_kws"):
            lines += ["## Topics mentioned (keyword counts across all text for this meeting)", "",
                      ", ".join(f"{k} ({n})" for k, n in m["_kws"]), "",
                      f"*Counts are keyword matches to help you find things, not findings. See the [keyword index]({self.rel(rel, 'indexes/keywords.md')}).*", ""]
        if tr or caps:
            lines += ["## Transcript", ""]
            for k, t in enumerate(m.get("_trs", []) if tr else []):
                lab = "Full transcript with timestamps" if k == 0 else f"Additional transcript ({t['source'].split('/')[-1]})"
                lines.append(f"- [{lab}]({self.rel(rel, t['path'])})" + (f" · [official video](https://www.youtube.com/watch?v={t['ytid']})" if t["ytid"] else ""))
            for c in caps:
                lines.append(f"- [Caption transcript: {md_inline(c['title'])}]({self.rel(rel, c['path'])}) ({c['words']:,} words, WindyCityMeetings database record `{c['id']}`)"
                             + (f" — {c['note']}" if c.get("note") else ""))
            lines.append("")
        if docs:
            lines += ["## Archived documents", "",
                      "| # | Document | Type | Pages | Text status |", "|---|---|---|---|---|"]
            for n, d in enumerate(docs, 1):
                dup = f" (same file as in {d['dup_of']})" if d.get("dup_of") and d["dup_of"] != m["id"] else ""
                lines.append(f"| {n} | [{md_escape_cell(d['title'])}]({self.rel(rel, d['path'])}){dup} | {d['kind']} | {d['pages']} | {md_escape_cell(d['status'])} |")
            lines.append("")
            lines += ["### Document previews", ""]
            for n, d in enumerate(docs, 1):
                if d["excerpt"]:
                    lines.append(f"{n}. **{md_inline(d['title'])}**: {d['excerpt']}…")
            lines.append("")
        for clip, body in mins:
            lines += [f"## Record of Proceedings (official minutes text, Granicus clip {clip})", ""]
            if len(body) <= INLINE_MINUTES:
                lines += [fence(body), ""]
            else:
                mrel = f"documents/{self.year_of(m)}/{m['id']}/record-of-proceedings-{clip}.md"
                self.write(mrel, f"# Record of Proceedings: {label}, {dl}\n\n[← meeting]({self.rel(mrel, rel)})\n\n{fence(body)}")
                lines += [f"[Full Record of Proceedings text]({self.rel(rel, mrel)}) ({len(body):,} characters)", ""]
        lines += ["---", "", f"*Part of the [Cheyenne public meetings AI-readable record]({self.rel(rel, 'README.md')}). Cite the official source or the original archive file when you can.*"]
        self.write(rel, "\n".join(lines))

    # ----------------------------------------------------------- indexes
    def meeting_row(self, from_rel, m, ndocs, has_tr, has_min, n_text):
        return (f"| {m['date']} | [{BODY_LABELS.get(m['body'], m['body'])}]({self.rel(from_rel, self.mpath(m))}) | {ndocs} | "
                f"{n_text} | {'yes' if has_tr else ''} | {'yes' if has_min else ''} |")

    def write_indexes(self, summaries):
        years = collections.defaultdict(list); bodies = collections.defaultdict(list)
        for s in summaries:
            years[s[0]["date"][:4]].append(s); bodies[s[0]["body"]].append(s)
        hdr = ["| Date | Meeting | Documents | Docs with text | Transcript | Minutes text |", "|---|---|---|---|---|---|"]
        for y, lst in sorted(years.items()):
            rel = f"years/{y}.md"
            ys = sorted(years)
            i = ys.index(y)
            nav = ([f"[← {ys[i-1]}]({ys[i-1]}.md)"] if i else []) + ["[Home](../README.md)"] + ([f"[{ys[i+1]} →]({ys[i+1]}.md)"] if i < len(ys)-1 else [])
            extra = []
            if y == "2026" and getattr(self, "undated", None):
                extra = ["", "## Transcripts with no published date", ""] + [f"- [{t}]({self.rel(rel, r['path'])})" for t, r in self.undated]
            loose = [(r, i) for r, i in getattr(self, "loose_pages", []) if r["date"] and r["date"][:4] == y]
            if loose:
                extra += ["", "## Other recorded sessions this year (caption transcripts)", ""] + \
                         [f"- {r['date']}: [{md_inline(r['title'])}]({self.rel(rel, i['path'])}) ({r['words']:,} words)" for r, i in sorted(loose, key=lambda x: x[0]["date"])]
            self.write(rel, "\n".join([f"# Cheyenne public meetings in {y}", "",
                                       f"*{len(lst)} meetings. Every row links to a page with all of that meeting's documents as plain text.*", "",
                                       " · ".join(nav), ""] + hdr + [self.meeting_row(rel, *s) for s in lst] + extra))
        for b, lst in sorted(bodies.items()):
            rel = f"bodies/{b}.md"
            self.write(rel, "\n".join([f"# {BODY_LABELS.get(b, b)}: all meetings", "",
                                       f"*{len(lst)} meetings, {lst[0][0]['date']} to {lst[-1][0]['date']}.* [Home](../README.md)", ""]
                                      + hdr + [self.meeting_row(rel, *s) for s in lst]))
        # keyword index
        rel = "indexes/keywords.md"
        out = ["# Keyword index", "",
               "*For each watch term: every meeting whose text (documents, transcript, minutes) mentions it, with the match count. Counts help you find passages; they are not findings. Auto-captions mishear names, so a missing hit does not prove a term was never said.*", "",
               "[Home](../README.md)", ""]
        out += ["## Terms", ""] + [f"- [{k}](#{slugify(k)}) ({len(self.kw_hits.get(k, []))} meetings)" for k, _ in KEYWORDS] + [""]
        for k, _ in KEYWORDS:
            hits = self.kw_hits.get(k, [])
            out += [f"## {k}", "", f"{len(hits)} meetings.", ""]
            if hits:
                out += ["| Date | Meeting | Mentions |", "|---|---|---|"]
                for m, n in hits:
                    out.append(f"| {m['date']} | [{BODY_LABELS.get(m['body'], m['body'])}]({self.rel(rel, self.mpath(m))}) | {n} |")
                out.append("")
        self.write(rel, "\n".join(out))
        # statute index
        rel = "indexes/statutes.md"
        out = ["# Wyoming statute citations", "",
               "*Every `W.S. xx-x-xxx` style citation found in the archived text, with the meetings where it appears. Pattern-matched from OCR, PDF text, and captions, so check each one in context. Statute text: https://wyoleg.gov/statutes/compress/title{N}.pdf*", "",
               "[Home](../README.md)", "", "| Statute | Meetings | Where |", "|---|---|---|"]
        def skey(s): return tuple(int(x) for x in s.split("-"))
        for s in sorted(self.statutes, key=skey):
            ms = sorted(self.statutes[s], key=lambda i: self.m_by_id[i]["date"])
            links = ", ".join(f"[{self.m_by_id[i]['date']} {BODY_LABELS.get(self.m_by_id[i]['body'], '')}]({self.rel(rel, self.mpath(self.m_by_id[i]))})" for i in ms[:25])
            if len(ms) > 25: links += f", … (+{len(ms)-25})"
            out.append(f"| W.S. {s} | {len(ms)} | {links} |")
        self.write(rel, "\n".join(out))
        # ordinance index
        rel = "indexes/ordinances.md"
        out = ["# Ordinance numbers in the Records of Proceedings", "",
               "*Ordinance numbers are assigned at final passage. The Record of Proceedings prints them as `(#NNNN)` right after the item. Each row links to the meeting where that number appears.*", "",
               "[Home](../README.md)", "", "| Ordinance # | Meeting(s) |", "|---|---|"]
        for o in sorted(self.ordinances, key=int):
            ms = sorted(self.ordinances[o], key=lambda i: self.m_by_id[i]["date"])
            out.append(f"| {o} | " + ", ".join(f"[{self.m_by_id[i]['date']}]({self.rel(rel, self.mpath(self.m_by_id[i]))})" for i in ms) + " |")
        self.write(rel, "\n".join(out))
        # caption-transcript index
        rel = "indexes/caption-transcripts.md"
        rows = []
        for m, *_ in summaries:
            for c in m.get("_caps", []):
                rows.append((m["date"], BODY_LABELS.get(m["body"], m["body"]), c["title"], c["words"], c["path"], c["id"]))
        for r, i in getattr(self, "loose_pages", []):
            rows.append((r["date"] or "", BODY_LABELS.get(r["body"], "") if r["body"] else "", r["title"], r["words"], i["path"], r["id"]))
        dated = sorted([x for x in rows if x[0]], key=lambda x: (x[0], x[2]))
        undated = sorted([x for x in rows if not x[0]], key=lambda x: x[2])
        n_dup = sum(1 for r in self.drive if r.get("dup_of"))
        out = ["# Caption transcripts (WindyCityMeetings database)", "",
               f"*{len(rows):,} machine caption transcripts of City of Cheyenne meeting videos, about {sum(x[3] for x in rows):,} words in total. "
               "Each one is listed here and also linked from its meeting page when the meeting is known. "
               "These are automatic captions with no punctuation, timestamps, or speaker names, so check quotes against the official video or minutes.*", "",
               f"- **Source:** {self.DRIVE_SRC}",
               f"- **Records in the database:** {len(self.drive):,} ({n_dup} have the same text as another record; duplicates for the same meeting are shown once)",
               f"- **Dates:** {sum(1 for r in self.drive if r['date_source'] == 'database'):,} from the database, {sum(1 for r in self.drive if r['date_source'] == 'title'):,} read from the video title, {sum(1 for r in self.drive if not r['date']):,} unknown",
               "", "[Home](../README.md) · [Keyword index](keywords.md)", "",
               f"## Dated ({len(dated):,})", "", "| Date | Body | Video title | Words | Record |", "|---|---|---|---|---|"]
        out += [f"| {d} | {b} | [{md_escape_cell(t)}]({self.rel(rel, pth)}) | {w:,} | `{rid}` |" for d, b, t, w, pth, rid in dated]
        out += ["", f"## Date not given ({len(undated):,})", "",
                "*Many of these are numbered City Council uploads (\"City Council Meeting 23\"). The database has no date for them, and the title doesn't give one either.*", "",
                "| Body (from title) | Video title | Words | Record |", "|---|---|---|---|"]
        out += [f"| {b} | [{md_escape_cell(t)}]({self.rel(rel, pth)}) | {w:,} | `{rid}` |" for d, b, t, w, pth, rid in undated]
        self.write(rel, "\n".join(out))
        self.caption_rows = rows
        # catalog json
        cat = []
        for m, ndocs, has_tr, has_min, ntext in summaries:
            cat.append({"id": m["id"], "date": m["date"], "body": m["body"], "bodyLabel": BODY_LABELS.get(m["body"], m["body"]),
                        "page": SITE + self.mpath(m).replace(".md", ".html"), "markdown": REPO_BLOB + self.mpath(m),
                        "documents": ndocs, "documentsWithText": ntext, "transcript": has_tr, "minutesText": has_min,
                        "captionTranscripts": [SITE + c["path"].replace(".md", ".html") for c in m.get("_caps", [])],
                        "official": m.get("official") or {}, "keywords": dict(m.get("_kws", []))})
        self.write("indexes/meetings.json", json.dumps({"generated": "from the archive snapshot", "count": len(cat), "meetings": cat}, indent=1))
        self.stats = {"meetings": len(summaries), "documents": sum(s[1] for s in summaries),
                      "transcripts": sum(1 for s in summaries if s[2]), "minutes": sum(1 for s in summaries if s[3]),
                      "years": f"{min(years)}–{max(years)}", "pages": self.pages_total, "chars": self.chars_total,
                      "caption_transcripts": len(self.caption_rows),
                      "caption_words": sum(x[3] for x in self.caption_rows),
                      "caption_meetings": sum(1 for s in summaries if s[0].get("_caps")),
                      "quality": dict(self.quality)}
        json.dump(self.stats, open(os.path.join(self.out, "indexes", "stats.json"), "w"), indent=1)
        self.files.append("indexes/stats.json")
        from ai_record_status import snapshot_status, status_panel
        status = snapshot_status(cat, self.stats)
        self.write("indexes/status.json", json.dumps(status, indent=2))
        # curated pages: copy from tools/ai_record_static, expanding {{yt:meeting-id@HH:MM:SS}} and {{m:meeting-id}}
        static = self.a.static
        for root, _, fs in os.walk(static):
            for f in fs:
                src = os.path.join(root, f)
                relp = os.path.relpath(src, static).replace(os.sep, "/")
                txt = open(src, encoding="utf-8").read()
                txt = self.expand(relp, txt)
                if relp == "README.md":
                    heading, separator, rest = txt.partition("\n\n")
                    txt = heading + "\n\n" + status_panel(status) + rest
                self.write(relp, txt)

    def expand(self, relp, txt):
        def yt(mm):
            mid, ts = mm.group(1), mm.group(2)
            m = self.m_by_id.get(mid)
            if not m: return f"{mid} [{ts}]"
            tpath = f"documents/{self.year_of(m)}/{m['id']}/transcript.md"
            ytid = None
            t = m.get("transcript")
            if t:
                raw = open(os.path.join(self.a.transcripts, t["path"]), encoding="utf-8").read()
                g = re.search(r"YouTube ID:\*\*\s*`([A-Za-z0-9_-]{6,})`", raw)
                ytid = g.group(1) if g else None
            h, mi, s = map(int, ts.split(":"))
            sec = h * 3600 + mi * 60 + s
            for start, part in self.tparts.get(tpath[:-3], []):
                if start <= sec: tpath = part
            v = f" ([video](https://www.youtube.com/watch?v={ytid}&t={sec}s))" if ytid else ""
            return f"[{ts}]({self.rel(relp, tpath)}){v}"
        def ml(mm):
            m = self.m_by_id.get(mm.group(1))
            if not m: return mm.group(1)
            return f"[{BODY_LABELS.get(m['body'], m['body'])}, {m['date']}]({self.rel(relp, self.mpath(m))})"
        txt = re.sub(r"\{\{yt:([a-z0-9-]+)@(\d{2}:\d{2}:\d{2})\}\}", yt, txt)
        txt = re.sub(r"\{\{m:([a-z0-9-]+)\}\}", ml, txt)
        for k, v in self.stats.items():
            if not isinstance(v, dict):
                txt = txt.replace("{{stat:%s}}" % k, f"{v:,}" if isinstance(v, int) else str(v))
        return txt


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--meetings", required=True)
    ap.add_argument("--text", required=True)
    ap.add_argument("--ocr")
    ap.add_argument("--transcripts", required=True)
    ap.add_argument("--minutes", default="pipeline/corpus")
    ap.add_argument("--trees", required=True)
    ap.add_argument("--static", default="tools/ai_record_static")
    ap.add_argument("--out", default="ai-record")
    ap.add_argument("--drive-db", help="caption-transcript database JSON(.gz) from Google Drive")
    a = ap.parse_args()
    b = Builder(a)
    b.build()
    print(json.dumps(b.stats, indent=1))
    print("files written:", len(b.files))


if __name__ == "__main__":
    main()
