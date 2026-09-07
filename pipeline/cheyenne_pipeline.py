#!/usr/bin/env python3
"""
cheyenne_pipeline.py — Cheyenne municipal records & video pipeline
==================================================================
One tool to:
  1. INDEX   every meeting in the city's Granicus archive (agendas, minutes,
             direct MP4s) plus the city's own Minutes-and-Agendas page.
  2. FETCH   every supporting document (agenda, minutes, staff reports,
             MetaViewer attachments, DocumentViewer PDFs, COTW files).
  3. VIDEO   download any meeting's full video (direct MP4 when available,
             yt-dlp fallback for anything else, e.g. YouTube/Facebook).
  4. CLIP    cut exact segments from any downloaded meeting by timestamp
             (use your "Sync to video time" indexes directly).
  5. PROJECT stitch meeting clips + your commentary into one rendered video:
             interleaved commentary segments, voice-over with optional
             auto-ducking over meeting audio, and title cards.

Sources handled (verified against the live archive):
  - https://cheyenne.granicus.com/ViewPublisher.php?view_id=5  (agenda/minutes view)
  - https://cheyenne.granicus.com/ViewPublisher.php?view_id=2  (direct MP4 archive)
  - AgendaViewer.php / GeneratedAgendaViewer.php  (agendas + links to supporting docs)
  - MinutesViewer.php?clip_id=N&doc_id=UUID         (minutes pages -> PDFs)
  - MetaViewer.php?meta_id=N                        (staff reports / packet docs)
  - DocumentViewer.php?file=cheyenne_<hash>.pdf     (direct PDF bytes)
  - cheyennecity.org Minutes-and-Agendas page       (DocumentViewer + event links)
  - cheyennecity.org COTW pattern: .../wscow-YYYY/cow-MM-DD-YY-{agenda,minutes}.pdf

Dependencies:  python3 -m pip install requests yt-dlp   +   ffmpeg on PATH
Workspace:     everything lands under ./pipeline/ (videos/, docs/, clips/, renders/)
Public records source; be polite -- the tool rate-limits itself by default.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse, parse_qs

try:
    import requests
except ImportError:
    sys.exit("Missing dependency: pip install requests")

BASE = "https://cheyenne.granicus.com/"
VIEW5 = f"{BASE}ViewPublisher.php?view_id=5"   # agendas + minutes listings
VIEW2 = f"{BASE}ViewPublisher.php?view_id=2"   # direct-MP4 archive listing
CITY_MINUTES_PAGE = "https://www.cheyennecity.org/Your-Government/City-Council/Minutes-and-Agendas"
CITY_COTW_PATTERN = ("https://www.cheyennecity.org/files/sharedassets/public/v/1/"
                     "your-government/city-council/wscow-{yy}/cow-{mm}-{dd}-{yy}-{kind}.pdf")

ROOT = Path(__file__).resolve().parent
MEETINGS_JSON = ROOT / "meetings.json"
VIDEOS = ROOT / "videos"
DOCS = ROOT / "docs"
CLIPS = ROOT / "clips"
RENDERS = ROOT / "renders"
COMMENT = ROOT / "commentary"

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 CheyenneRecordsPipeline/1.0"}
SESSION = requests.Session()
SESSION.headers.update(UA)
NICE_DELAY = 0.4  # seconds between doc fetches — be polite to public servers


# ----------------------------------------------------------------------------
# small utilities
# ----------------------------------------------------------------------------

def http_get(url: str, **kw) -> requests.Response:
    kw.setdefault("headers", UA)
    kw.setdefault("timeout", 60)
    r = SESSION.get(url, **kw)
    r.raise_for_status()
    return r


def warm_session(player_url: str = "") -> None:
    """Granicus stream hosts reject cold requests; establish cookies + referer."""
    if not SESSION.cookies:
        try:
            SESSION.get(VIEW5, timeout=30)
        except Exception:
            pass
    if player_url:
        try:
            SESSION.get(player_url, timeout=30)
        except Exception:
            pass


def stream_url_for(mp4_url: str) -> str:
    """archive-video.granicus.com direct file -> Wowza HLS playlist.
    https://archive-video.../cheyenne/cheyenne_X.mp4
        -> https://archive-stream.granicus.com/OnDemand/_definst_/mp4:archive/cheyenne/cheyenne_X.mp4/playlist.m3u8
    """
    m = re.search(r"cheyenne/([A-Za-z0-9_-]+\.mp4)$", mp4_url)
    if not m:
        return mp4_url
    return ("https://archive-stream.granicus.com/OnDemand/_definst_/"
            f"mp4:archive/cheyenne/{m.group(1)}/playlist.m3u8")


def ffmpeg_headers(player_url: str) -> list[str]:
    cookies = "; ".join(f"{c.name}={c.value}" for c in SESSION.cookies)
    hdr = f"Referer: {player_url}\r\nUser-Agent: {UA['User-Agent']}\r\n"
    if cookies:
        hdr += f"Cookie: {cookies}\r\n"
    return ["-headers", hdr]


def to_seconds(ts: str) -> float:
    """'01:23:45' | '23:45' | '45' | '90.5' -> seconds."""
    ts = str(ts).strip()
    if re.fullmatch(r"[\d.]+", ts):
        return float(ts)
    parts = [float(p) for p in ts.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    h, m, s = parts
    return h * 3600 + m * 60 + s


def fmt_ts(sec: float) -> str:
    sec = max(0, int(round(sec)))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def need_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        sys.exit("ffmpeg not found on PATH. Install it first (apt install ffmpeg / brew install ffmpeg).")


# ----------------------------------------------------------------------------
# 1. INDEX — build meetings.json from Granicus views 2 & 5 + city page
# ----------------------------------------------------------------------------

ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
LINK_RE = re.compile(r"<a[^>]+href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", re.S | re.I)
TAG_RE = re.compile(r"<[^>]+>")
DATE_RE = re.compile(r"([A-Z][a-z]{2})\s+(\d{1,2}),\s*(\d{4})")
MONTHS = {m: i + 1 for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])}


def _clean(text: str) -> str:
    return TAG_RE.sub("", text).replace("&nbsp;", " ").replace("&amp;", "&").strip()


def _qs(url: str, key: str) -> Optional[str]:
    q = parse_qs(urlparse(url).query)
    vals = q.get(key)
    return vals[0] if vals else None


def parse_listing(html: str) -> dict[int, dict]:
    """Parse a ViewPublisher table into {clip_id: meeting_fields}."""
    meetings: dict[int, dict] = {}
    for row in ROW_RE.findall(html):
        links = LINK_RE.findall(row)
        if not links:
            continue
        row_txt = _clean(row)
        clip_id = None
        fields: dict = {}
        for href, label in links:
            href = href.replace("&amp;", "&")
            label_l = _clean(label).lower()
            cid = _qs(href, "clip_id")
            if "AgendaViewer" in href or "GeneratedAgendaViewer" in href:
                clip_id = int(cid) if cid and cid.isdigit() else clip_id
                fields["agenda_url"] = urljoin(BASE, href)
                fields["event_id"] = _qs(href, "event_id")
            elif "MinutesViewer" in href:
                clip_id = int(cid) if cid and cid.isdigit() else clip_id
                fields["minutes_url"] = urljoin(BASE, href)
                if _qs(href, "doc_id"):
                    fields["minutes_doc_id"] = _qs(href, "doc_id")
            elif "DocumentViewer" in href and ".pdf" in href.lower():
                fields.setdefault("city_minutes_pdf", urljoin(BASE, href))
            elif href.lower().endswith(".mp4") or "archive-video" in href:
                if cid and cid.isdigit():
                    clip_id = int(cid)
                fields["mp4_url"] = href.replace("http://", "https://")
        if clip_id is None:
            continue
        m = DATE_RE.search(row_txt)
        if m:
            try:
                fields["date"] = f"{int(m.group(3)):04d}-{MONTHS[m.group(1)]:02d}-{int(m.group(2)):02d}"
            except KeyError:
                pass
        name = _clean(row_txt)
        # keep a short readable name: text before the date match, no wrapped lines
        if m and m.start() > 0:
            name = name[: m.start()].strip(" -\t")
        name = name.split("\n")[0].strip()
        name = re.sub(r"\s*\d{9,10}\s*$", "", name)  # trailing unix timestamps
        fields["name"] = name[:120] or f"clip {clip_id}"
        fields.setdefault("date", "")
        meetings.setdefault(clip_id, {}).update(fields)
    return meetings


def crawl_city_page(index: dict[int, dict]) -> None:
    """Harvest the city's Minutes-and-Agendas page for extra links + COTW rows."""
    try:
        html = http_get(CITY_MINUTES_PAGE).text
    except Exception as e:  # city site is sometimes slow; index still works
        print(f"    [!] city page unavailable: {e}")
        return
    # date rows like "01/14/26" followed by links
    for href, _label in LINK_RE.findall(html):
        href = href.replace("&amp;", "&")
        if "DocumentViewer" in href and ".pdf" in href.lower():
            continue  # hashed files can't be mapped to clip rows here; harvested per-meeting later
        cid = _qs(href, "clip_id")
        if cid and cid.isdigit():
            key = int(cid)
            entry = index.setdefault(key, {})
            if "AgendaViewer" in href or "GeneratedAgendaViewer" in href:
                entry["agenda_url"] = urljoin(BASE, href)
                entry["event_id"] = _qs(href, "event_id")
            elif "MinutesViewer" in href:
                entry["minutes_url"] = urljoin(BASE, href)
            elif "/player/" in href:
                entry["player_url"] = href
    # Committee of the Whole rows: "01/14/26 Agenda(PDF...) Minutes(PDF...) Video"
    for mm, dd, yy, yy2 in re.findall(
            r"(\d{2})/(\d{2})/(\d{2})\b", html[:400000]):
        pass  # COTW PDFs are resolved by name in `docs --cotw` instead


def cmd_index(args) -> None:
    print("[*] Fetching Granicus view 5 (agendas/minutes) ...")
    v5 = parse_listing(http_get(VIEW5).text)
    print(f"    {len(v5)} meetings with agenda/minutes links")
    print("[*] Fetching Granicus view 2 (direct MP4 archive) ...")
    v2 = parse_listing(http_get(VIEW2).text)
    print(f"    {len(v2)} meetings with direct MP4s")
    index: dict[int, dict] = {}
    for source in (v5, v2):
        for cid, fields in source.items():
            index.setdefault(cid, {"clip_id": cid}).update(fields)
    print("[*] Supplementing from cheyennecity.org Minutes-and-Agendas page ...")
    crawl_city_page(index)
    # tag COTW-era meetings so `docs` knows to try the city PDF pattern
    data = {"generated": datetime.now().isoformat(timespec="seconds"),
            "meetings": {str(k): v for k, v in sorted(index.items(), reverse=True)}}
    MEETINGS_JSON.write_text(json.dumps(data, indent=1))
    total = len(index)
    with_mp4 = sum(1 for v in index.values() if v.get("mp4_url"))
    with_agenda = sum(1 for v in index.values() if v.get("agenda_url"))
    with_minutes = sum(1 for v in index.values() if v.get("minutes_url") or v.get("city_minutes_pdf"))
    print(f"[+] Indexed {total} meetings -> {MEETINGS_JSON}")
    print(f"    {with_mp4} direct MP4s | {with_agenda} agendas | {with_minutes} minutes")


def load_index() -> dict[int, dict]:
    if not MEETINGS_JSON.exists():
        sys.exit("No meetings.json yet — run: cheyenne_pipeline.py index")
    raw = json.loads(MEETINGS_JSON.read_text())["meetings"]
    return {int(k): v for k, v in raw.items()}


def resolve(clip: str) -> tuple[int, dict]:
    idx = load_index()
    if clip.isdigit() and int(clip) in idx:
        return int(clip), idx[int(clip)]
    hits = [c for c, v in idx.items() if clip.lower() in (v.get("name", "") + " " + v.get("date", "")).lower()]
    if len(hits) == 1:
        return hits[0], idx[hits[0]]
    if not hits:
        sys.exit(f"No meeting matching {clip!r}. Try a clip_id from: cheyenne_pipeline.py list")
    sys.exit(f"Ambiguous {clip!r}: " + ", ".join(f"{c} ({idx[c].get('date')})" for c in hits[:8]))


def cmd_list(args) -> None:
    idx = load_index()
    rows = sorted(idx.items(), key=lambda kv: (kv[1].get("date") or "", kv[0]), reverse=True)
    if args.search:
        rows = [(c, v) for c, v in rows if args.search.lower() in
                (v.get("name", "") + " " + v.get("date", "")).lower()]
    print(f"{'clip':>5}  {'date':<10}  {'mp4':<3} {'ag':<3} {'min':<3}  name")
    for c, v in rows[: args.limit]:
        print(f"{c:>5}  {v.get('date', '?'):<10}  "
              f"{'Y' if v.get('mp4_url') else '-':<3} "
              f"{'Y' if v.get('agenda_url') else '-':<3} "
              f"{'Y' if (v.get('minutes_url') or v.get('city_minutes_pdf')) else '-':<3}  "
              f"{v.get('name', '')[:70]}")


# ----------------------------------------------------------------------------
# 2. DOCS — agendas, minutes, every supporting document
# ----------------------------------------------------------------------------

PDF_HARVEST_RE = re.compile(
    r"(DocumentViewer\.php\?file=[^\"'&\s]+\.pdf|https?://[^\"'\s]+\.pdf)", re.I)


def harvest_pdfs(page_url: str, seen: set[str]) -> list[str]:
    """All PDF links reachable on one page (DocumentViewer + direct .pdf)."""
    try:
        html = http_get(page_url).text
    except Exception as e:
        print(f"    [!] {page_url}: {e}")
        return []
    found = []
    for raw in PDF_HARVEST_RE.findall(html):
        url = raw.replace("&amp;", "&")
        if url.startswith("DocumentViewer"):
            url = BASE + url
        url = urljoin(page_url, url)
        if url.lower().endswith(".pdf") and url not in seen:
            seen.add(url)
            found.append(url)
    return found


def safe_name(url: str, i: int) -> str:
    name = Path(urlparse(url).path).name or f"doc_{i}"
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name)[:100]
    return f"{i:02d}_{name}" if not name[:2].isdigit() else name


def download_pdf(url: str, dest_dir: Path) -> Optional[Path]:
    r = http_get(url, stream=True)
    ctype = r.headers.get("content-type", "")
    if "text/html" in ctype:
        return None  # link rendered an error page, not a document
    dest_dir.mkdir(parents=True, exist_ok=True)
    name = Path(urlparse(url).path).name
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name or "doc.pdf")
    out = dest_dir / name
    if out.exists() and out.stat().st_size > 0:
        return out
    with open(out, "wb") as f:
        for chunk in r.iter_content(65536):
            f.write(chunk)
    return out


def fetch_meeting_docs(cid: int, m: dict, max_docs: int) -> None:
    """Pull everything a meeting has: agenda page, minutes page, every supporting
    document (MetaViewer pages carry the packet content inline), plus any real
    PDFs (DocumentViewer / city-site files). HTML pages are saved as artifacts —
    Granicus renders agendas/minutes/packets as HTML, not PDF."""
    dest = DOCS / str(cid)
    dest.mkdir(parents=True, exist_ok=True)
    stamp = m.get("date") or str(cid)
    count = 0
    meta_pages: list[str] = []

    def save_html(kind: str, url: str) -> None:
        nonlocal count
        try:
            r = http_get(url)
        except Exception as e:
            print(f"    [!] {kind}: {e}")
            return
        out = dest / f"{stamp}_{kind}.html"
        out.write_bytes(r.content)
        count += 1
        print(f"    [+] {kind}.html ({len(r.content)//1024} KB) <- {url[:80]}")

    # direct PDFs we already know about
    pdf_queue = [m["city_minutes_pdf"]] if m.get("city_minutes_pdf") else []
    if m.get("date") and not m.get("agenda_url"):  # COTW guessable city PDFs
        yy, mm, dd = m["date"][2:4], m["date"][5:7], m["date"][8:10]
        for kind in ("agenda", "minutes"):
            pdf_queue.append(CITY_COTW_PATTERN.format(yy=yy, mm=mm, dd=dd, yy2=yy, kind=kind))

    # agenda page = the agenda + the MetaViewer links for every supporting doc
    if m.get("agenda_url"):
        save_html("agenda", m["agenda_url"])
        try:
            html = http_get(m["agenda_url"]).text
            for href, _ in LINK_RE.findall(html):
                href = href.replace("&amp;", "&")
                if "MetaViewer" in href:
                    meta_pages.append(urljoin(BASE, href))
                if ".pdf" in href.lower() or "DocumentViewer" in href:
                    pdf_queue.append(urljoin(BASE, href))
        except Exception as e:
            print(f"    [!] agenda scan: {e}")

    # minutes page = full minutes rendered inline
    if m.get("minutes_url"):
        save_html("minutes", m["minutes_url"])

    # supporting documents: one MetaViewer page each
    for i, mp in enumerate(dict.fromkeys(meta_pages)):
        if max_docs and count >= max_docs:
            break
        time.sleep(NICE_DELAY)
        save_html(f"meta_{i+1:02d}", mp)
        try:  # some metas also expose real file attachments
            for pdf in harvest_pdfs(mp, set()):
                pdf_queue.append(pdf)
        except Exception:
            pass

    # any real PDFs found anywhere above
    for url in dict.fromkeys(pdf_queue):
        if max_docs and count >= max_docs:
            break
        time.sleep(NICE_DELAY)
        got = download_pdf(url, dest)
        if got:
            count += 1
            print(f"    [+] pdf: {got.name} ({got.stat().st_size//1024} KB)")
    print(f"[+] Meeting {cid}: {count} documents in {dest}")


def cmd_docs(args) -> None:
    if args.all:
        idx = load_index()
        targets = sorted(idx.items(), reverse=True)
        if args.since:
            targets = [(c, v) for c, v in targets if v.get("date", "") >= args.since]
        print(f"[*] Fetching documents for {len(targets)} meetings"
              + (f" since {args.since}" if args.since else ""))
        for c, v in targets:
            print(f"[*] Meeting {c} — {v.get('date')} {v.get('name', '')[:60]}")
            fetch_meeting_docs(c, v, args.max_docs)
    else:
        cid, m = resolve(args.meeting)
        print(f"[*] Meeting {cid} — {m.get('date')} {m.get('name', '')[:60]}")
        fetch_meeting_docs(cid, m, args.max_docs)


# ----------------------------------------------------------------------------
# 3. VIDEO — full meeting downloads (direct MP4 preferred, yt-dlp fallback)
# ----------------------------------------------------------------------------

def video_path(cid: int, m: dict) -> Path:
    stamp = m.get("date") or "unknown"
    return VIDEOS / f"{cid}_{stamp}.mp4"


def ytdlp_grab(url: str, out_dir: Path, out_name: str = "") -> Path:
    """Original yt-dlp path — works for YouTube/Facebook/anything yt-dlp supports."""
    try:
        import yt_dlp
    except ImportError:
        sys.exit("yt-dlp not installed: pip install yt-dlp")
    out_dir.mkdir(parents=True, exist_ok=True)
    tmpl = str(out_dir / (out_name or "%(id)s"))
    opts = {"format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "outtmpl": f"{tmpl}.%(ext)s", "quiet": False}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        path = ydl.prepare_filename(info)
        if not os.path.exists(path):
            path = os.path.splitext(path)[0] + ".mp4"
        return Path(path)


def stream_download_fallback(hls_url: str, out: Path, seconds: float = 0) -> bool:
    """Last-resort: chrome-impersonated HLS fetch (curl_cffi), segment by segment,
    then local reassembly with ffmpeg. Wins when the CDN blocks script/ffmpeg
    TLS fingerprints. Returns True on success."""
    try:
        from curl_cffi import requests as creq
    except ImportError:
        print("    [!] curl_cffi not installed (pip install curl_cffi) — skipping impersonation path")
        return False
    try:
        r = creq.get(hls_url, impersonate="chrome", timeout=30)
        if r.status_code != 200:
            return False
        text = r.text
        # master playlist? -> pick highest-bandwidth variant
        variants = re.findall(r"^#EXT-X-STREAM-INF:[^\n]*BANDWIDTH=(\d+)[^\n]*\n(\S+)",
                              text, re.M)
        seg_urls: list[str] = []
        if variants:
            best = max(variants, key=lambda v: int(v[0]))[1]
            child = creq.get(urljoin(hls_url, best), impersonate="chrome", timeout=30)
            if child.status_code != 200:
                return False
            text = child.text
            base = urljoin(hls_url, best)
        else:
            base = hls_url
        if "#EXTINF" not in text:
            return False
        seg_urls = [urljoin(base, ln) for ln in text.splitlines()
                    if ln.strip() and not ln.startswith("#")]
        if seconds:  # ~6s segments: keep enough to cover requested seconds
            need = int(seconds / 6) + 2
            seg_urls = seg_urls[:need]
        cache = out.parent / f"{out.stem}.segs"
        cache.mkdir(exist_ok=True)
        local_lines = []
        print(f"    [.] impersonated HLS fetch: {len(seg_urls)} segments")
        for i, u in enumerate(seg_urls):
            seg = cache / f"seg_{i:05d}.ts"
            if not seg.exists() or seg.stat().st_size == 0:
                rr = creq.get(u, impersonate="chrome", timeout=60)
                if rr.status_code != 200:
                    print(f"    [!] segment {i} -> {rr.status_code}; aborting impersonation path")
                    return False
                seg.write_bytes(rr.content)
            local_lines.append(f"file '{seg.resolve().as_posix()}'")
        lst = cache / "list.txt"
        lst.write_text("\n".join(local_lines) + "\n")
        r = run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                 "-c", "copy", str(out)])
        ok = r.returncode == 0 and out.exists() and out.stat().st_size > 10_000
        if ok:
            shutil.rmtree(cache, ignore_errors=True)
        return ok
    except Exception as e:
        print(f"    [!] impersonation path error: {e}")
        return False


def fetch_video(cid: int, m: dict, seconds: float = 0, direct_url: str = "") -> Path:
    need_ffmpeg()
    out = video_path(cid, m)
    if out.exists() and out.stat().st_size > 0 and not seconds:
        print(f"[+] Already have {out}")
        return out
    VIDEOS.mkdir(parents=True, exist_ok=True)
    player = m.get("player_url") or f"{BASE}player/clip/{cid}?view_id=5&redirect=true"
    if not m.get("mp4_url"):
        try:
            html = http_get(player).text
            hit = re.search(r"archive-stream\.granicus\.com[^\"'\\\s]+\.mp4/play", html) \
                or re.search(r"archive-video\.granicus\.com[^\"'\\\s]+\.mp4", html)
            if hit:
                m["mp4_url"] = hit.group(0)
        except Exception:
            pass
    if direct_url:
        warm_session()
        limit = ["-t", str(int(seconds))] if seconds else []
        cmd = ["ffmpeg", "-y", *ffmpeg_headers("https://cheyenne.granicus.com/"),
               "-i", direct_url, *limit, "-c", "copy", str(out)]
        r = run(cmd)
        if r.returncode == 0 and out.exists() and out.stat().st_size > 10_000:
            print(f"[+] Saved {out} ({out.stat().st_size/1e6:.1f} MB)")
            return out
        if stream_download_fallback(direct_url, out, seconds):
            print(f"[+] Saved via impersonated stream: {out}")
            return out
        sys.exit(f"Could not fetch {direct_url} from this network.")
    if m.get("mp4_url"):
        warm_session(player)
        hls = stream_url_for(m["mp4_url"])
        limit = ["-t", str(int(seconds))] if seconds else []
        for label, url in (("hls", hls), ("direct", m["mp4_url"])):
            print(f"[*] Trying {label}: {url[:100]}")
            cmd = (["ffmpeg", "-y", *ffmpeg_headers(player), "-i", url, *limit,
                    "-c", "copy" if not seconds else "libx264"]
                   + ([] if seconds else [])
                   + (["-vf", "scale=640:360", "-preset", "veryfast", "-c:a", "aac"]
                      if seconds else []) + [str(out)])
            r = run(cmd)
            if r.returncode == 0 and out.exists() and out.stat().st_size > 10_000:
                print(f"[+] Saved {out} ({out.stat().st_size/1e6:.1f} MB)")
                return out
            print(f"    [!] {label} failed ({(r.stderr or '')[-160:]})")
        if stream_download_fallback(hls, out, seconds):
            print(f"[+] Saved via impersonated stream: {out}")
            return out
    print("[*] Falling back to yt-dlp ...")
    path = ytdlp_grab(m.get("player_url") or f"{BASE}MediaPlayer.php?view_id=5&clip_id={cid}",
                      VIDEOS, out_name=f"{cid}_{m.get('date') or 'unknown'}")
    return path


def cmd_video(args) -> None:
    if args.url:
        cid = int(args.meeting) if args.meeting and args.meeting.isdigit() else 0
        m = {"date": datetime.now().strftime("%Y-%m-%d"), "name": "manual"}
        VIDEOS.mkdir(parents=True, exist_ok=True)
        got = fetch_video(cid, m, seconds=args.seconds, direct_url=args.url)
        out = VIDEOS / f"{cid or 'manual'}_manual.mp4"
        if got.resolve() != out.resolve():
            got.rename(out)
        print(f"[+] Saved {out}")
        return
    if args.all:
        idx = load_index()
        targets = sorted(idx.items(), reverse=True)
        if args.since:
            targets = [(c, v) for c, v in targets if v.get("date", "") >= args.since]
        for c, v in targets:
            print(f"[*] Meeting {c} — {v.get('date')}")
            fetch_video(c, v, seconds=args.seconds)
    else:
        cid, m = resolve(args.meeting)
        fetch_video(cid, m, seconds=args.seconds)


def cmd_grab(args) -> None:
    """Any URL (YouTube, Facebook city streams, etc.) via yt-dlp — kept from the original script."""
    path = ytdlp_grab(args.url, VIDEOS)
    print(f"[+] Saved {path}")


# ----------------------------------------------------------------------------
# 4. CLIP — cut a segment by timestamp
# ----------------------------------------------------------------------------

def cut_clip(src: Path, start: str, end: str, name: str = "", reencode: bool = True) -> Path:
    need_ffmpeg()
    CLIPS.mkdir(parents=True, exist_ok=True)
    out = CLIPS / (name or f"{src.stem}_{fmt_ts(to_seconds(start)).replace(':', '')}-"
                   f"{fmt_ts(to_seconds(end)).replace(':', '')}.mp4").replace(" ", "_")
    if out.suffix.lower() not in (".mp4", ".mov", ".mkv"):
        out = out.with_suffix(".mp4")
    ss, to = fmt_ts(to_seconds(start)), fmt_ts(to_seconds(end))
    if reencode:  # frame-accurate
        cmd = ["ffmpeg", "-y", "-ss", ss, "-i", str(src), "-to", to,
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
               "-c:a", "aac", "-b:a", "160k", str(out)]
    else:         # fast, keyframe-aligned
        cmd = ["ffmpeg", "-y", "-ss", ss, "-i", str(src), "-to", to,
               "-c", "copy", str(out)]
    r = run(cmd)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg clip failed: {r.stderr[-800:]}")
    print(f"[+] Clip -> {out}")
    return out



# ----------------------------------------------------------------------------
# 4b. STREAM-LOCAL CLIPPING — cut clips WITHOUT downloading full meetings
#     (fetches only the HLS segments covering the requested window)
# ----------------------------------------------------------------------------

def _fetch_text(url: str) -> str:
    try:
        return http_get(url).text
    except Exception:
        from curl_cffi import requests as creq
        r = creq.get(url, impersonate="chrome", timeout=30)
        r.raise_for_status()
        return r.text


def _fetch_bytes(url: str, dest: Path, byte_range: Optional[tuple[int, int]] = None) -> bool:
    if dest.exists() and dest.stat().st_size > 0:
        return True
    headers = {"Range": f"bytes={byte_range[0]}-{byte_range[1]}"} if byte_range else {}
    try:
        r = SESSION.get(url, headers=headers, timeout=60)
        if r.status_code in (200, 206):
            dest.write_bytes(r.content)
            return True
    except Exception:
        pass
    try:
        from curl_cffi import requests as creq
        r = creq.get(url, impersonate="chrome", headers=headers, timeout=60)
        if r.status_code in (200, 206):
            dest.write_bytes(r.content)
            return True
    except Exception:
        return False
    return False


def hls_window(hls_url: str, start_s: float, end_s: float):
    """Parse playlist, pick only the segments covering [start_s, end_s)."""
    text = _fetch_text(hls_url)
    if "#EXT-X-STREAM-INF" in text:  # master playlist -> best variant
        variants = re.findall(r"#EXT-X-STREAM-INF:[^\n]*BANDWIDTH=(\d+)[^\n]*\n(\S+)", text)
        if variants:
            hls_url = urljoin(hls_url, max(variants, key=lambda v: int(v[0]))[1])
            text = _fetch_text(hls_url)
    segs, dur, br, base = [], 0.0, None, 0
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#EXT-X-BYTERANGE:"):
            spec = line.split(":", 1)[1]
            if "@" in spec:
                n, off = spec.split("@")
                br = (int(off), int(off) + int(n) - 1)
                base = int(off) + int(n)
            else:
                n = int(spec)
                br = (base, base + n - 1)
                base += n
        elif line.startswith("#EXTINF:"):
            dur = float(line.split(":", 1)[1].split(",")[0])
        elif line and not line.startswith("#"):
            segs.append((urljoin(hls_url, line), dur or 0.0, br))
            dur, br = 0.0, None
    chosen, first_off, t = [], 0.0, 0.0
    for u, d, b in segs:
        if t + d > start_s and t < end_s:
            if not chosen:
                first_off = t
            chosen.append((u, d, b))
        t += d
    if not chosen:
        raise RuntimeError(f"Window {start_s:.0f}-{end_s:.0f}s outside playlist ({t:.0f}s total)")
    return chosen, first_off, hls_url


def stream_clip(hls_url: str, start: str, end: str, name: str = "",
                cid: int = 0, normalize: bool = False) -> Path:
    """Download ONLY the segments covering start->end, assemble, exact-trim.
    A 3-minute turn costs ~30 small segment fetches instead of a multi-GB file."""
    need_ffmpeg()
    CLIPS.mkdir(parents=True, exist_ok=True)
    start_s, end_s = to_seconds(start), to_seconds(end)
    chosen, first_off, media_url = hls_window(hls_url, start_s, end_s)
    cache = VIDEOS / ".segcache" / (str(cid) if cid else "manual")
    cache.mkdir(parents=True, exist_ok=True)
    local, total_bytes = [], 0
    print(f"    [.] window {fmt_ts(start_s)}-{fmt_ts(end_s)}: {len(chosen)} segments to fetch")
    for i, (u, d, b) in enumerate(chosen):
        tag = re.sub(r"[^A-Za-z0-9._-]", "_",
                     f"{Path(urlparse(u).path).stem}_{i:04d}" + (f"_{b[0]}" if b else ""))[:80]
        seg = cache / f"{tag}.ts"
        if not _fetch_bytes(u, seg, b):
            raise RuntimeError(f"segment fetch failed: {u[:90]}")
        local.append(seg)
        total_bytes += seg.stat().st_size
    key = abs(hash((hls_url, int(start_s * 1000), int(end_s * 1000)))) % 999999
    lst = cache / f"job_{key}.txt"
    lst.write_text("".join(f"file '{p.resolve().as_posix()}\n" for p in local).replace("\n", "\n"))
    raw = cache / f"raw_{key}.mp4"
    r = run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(raw)])
    if r.returncode != 0:
        raise RuntimeError(f"segment concat failed: {r.stderr[-400:]}")
    out = CLIPS / (name or f"stream_{cid}_{fmt_ts(start_s).replace(':', '')}-"
                   f"{fmt_ts(end_s).replace(':', '')}.mp4")
    if out.suffix.lower() != ".mp4":
        out = out.with_suffix(".mp4")
    trim_from = max(0.0, start_s - first_off)
    dur = end_s - start_s
    vf = ("scale=1280:720:force_original_aspect_ratio=decrease,"
          "pad=1280:720:(ow-iw)/2:(oh-ih)/2,fps=30,format=yuv420p")
    cmd = (["ffmpeg", "-y", "-ss", f"{trim_from:.3f}", "-i", str(raw), "-t", f"{dur:.3f}",
            "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "160k", str(out)]
           if normalize else
           ["ffmpeg", "-y", "-ss", f"{trim_from:.3f}", "-i", str(raw), "-t", f"{dur:.3f}",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-c:a", "aac", "-b:a", "160k", str(out)])
    r = run(cmd)
    raw.unlink(missing_ok=True)
    if r.returncode != 0:
        raise RuntimeError(f"trim failed: {r.stderr[-400:]}")
    print(f"[+] Clip -> {out} ({out.stat().st_size/1e6:.1f} MB; fetched "
          f"{total_bytes/1e6:.1f} MB across {len(local)} segments — no full download)")
    return out


def meeting_hls(cid: int, m: dict) -> str:
    if not m.get("mp4_url"):
        player = m.get("player_url") or f"{BASE}player/clip/{cid}?view_id=5&redirect=true"
        html = _fetch_text(player)
        hit = (re.search(r"archive-stream\.granicus\.com[^\"'\\s]+\.mp4/play", html)
               or re.search(r"archive-video\.granicus\.com[^\"'\\s]+\.mp4", html))
        if hit:
            m["mp4_url"] = hit.group(0)
    if not m.get("mp4_url"):
        sys.exit(f"No stream found for meeting {cid}")
    return stream_url_for(m["mp4_url"])


def smart_clip(meeting: str, start: str, end: str, name: str = "",
               normalize: bool = False) -> Path:
    """Cut start->end: local file if present, otherwise windowed stream fetch."""
    if Path(meeting).exists():
        return cut_clip(Path(meeting), start, end, name=name, reencode=True)
    cid, m = resolve(meeting)
    src = video_path(cid, m)
    if src.exists():
        return cut_clip(src, start, end, name=name, reencode=True)
    return stream_clip(meeting_hls(cid, m), start, end, name=name, cid=cid, normalize=normalize)


def cmd_segments(args) -> None:
    """Batch-create clips from a JSON spec — on the fly, no full downloads."""
    plan = json.loads(Path(args.plan).read_text())
    items = plan if isinstance(plan, list) else (plan.get("segments") or plan.get("turns") or plan)
    made, skipped = [], 0
    for i, seg in enumerate(items):
        name = seg.get("name") or f"seg_{i+1:02d}"
        out = CLIPS / (name if name.endswith(".mp4") else name + ".mp4")
        if out.exists() and not args.force:
            print(f"[=] exists, skipping: {out.name}")
            skipped += 1
            continue
        label = seg.get("meeting") or seg.get("url") or "?"
        print(f"[*] {i+1}/{len(items)}: {name} <- {label} {seg.get('start')}-{seg.get('end')}")
        if seg.get("url"):
            stream_clip(seg["url"], seg["start"], seg["end"], name=name,
                        normalize=seg.get("normalize", False))
        else:
            smart_clip(str(seg["meeting"]), seg["start"], seg["end"],
                       name=name, normalize=seg.get("normalize", False))
        made.append(out)
    print(f"[+] {len(made)} clips created, {skipped} skipped -> {CLIPS}")



# ----------------------------------------------------------------------------
# 6. TRANSCRIPT CORPUS, NOTEBOOKLM BRIDGE & SOCIAL ANSWER REELS
# ----------------------------------------------------------------------------

CORPUS = ROOT / "corpus"
NB_DIR = ROOT / "notebooklm"
SCRIPT_STYLE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.S | re.I)


def html_to_text(html: str) -> str:
    html = SCRIPT_STYLE.sub(" ", html)
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    html = re.sub(r"</(p|div|tr|h\d|li)>", "\n", html, flags=re.I)
    text = TAG_RE.sub(" ", html)
    text = (text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&quot;", '"')
                .replace("&#39;", "'").replace("&lt;", "<").replace("&gt;", ">"))
    return re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]{2,}", " ", text)).strip()



def minutes_to_text(raw: bytes) -> str:
    """MinutesViewer serves PDF (or HTML) - handle both."""
    if raw[:5] == b"%PDF-":
        try:
            from pypdf import PdfReader
        except ImportError:
            sys.exit("pip install pypdf  (needed to read Granicus minutes PDFs)")
        import io as _io
        pages = PdfReader(_io.BytesIO(raw)).pages
        return "\n".join((p.extract_text() or "") for p in pages)
    return html_to_text(raw.decode("utf-8", errors="ignore"))


def cmd_corpus(args) -> None:
    """Minutes -> one clean text file per meeting (corpus/) + NotebookLM upload bundle."""
    idx = load_index()
    targets = sorted(((c, v) for c, v in idx.items() if v.get("minutes_url")), reverse=True)
    if args.since:
        targets = [(c, v) for c, v in targets if v.get("date", "") >= args.since]
    CORPUS.mkdir(exist_ok=True)
    (CORPUS / "extra").mkdir(exist_ok=True)
    made = 0
    print(f"[*] Building minutes corpus for {len(targets)} meetings ...")
    for c, v in targets:
        out = CORPUS / f"{c}_{v.get('date') or 'unknown'}.txt"
        if out.exists() and not args.force:
            made += 1
            continue
        cached = list((DOCS / str(c)).glob("*minutes*.html"))
        try:
            if cached:
                raw = cached[0].read_bytes()
            else:
                raw = http_get(v["minutes_url"]).content
                time.sleep(NICE_DELAY)
            text = minutes_to_text(raw)
            header = (f"MEETING: {v.get('name', 'City Council')} | DATE: {v.get('date', '?')} | "
                      f"CLIP_ID: {c} | SOURCE: cheyenne.granicus.com MinutesViewer clip {c}\n\n")
            out.write_text(header + text)
            made += 1
            print(f"    [+] {out.name} ({len(text)//1024} KB)")
        except Exception as e:
            print(f"    [!] {c}: {e}")
    NB_DIR.mkdir(exist_ok=True)
    years: dict[str, list[Path]] = {}
    for f in sorted(CORPUS.glob("*.txt")) + sorted((CORPUS / "extra").glob("*.txt")):
        y = f.stem.split("_")[-1][:4]
        years.setdefault(y if y.isdigit() else "extra", []).append(f)
    for y, fs in sorted(years.items()):
        bundle = NB_DIR / f"cheyenne_minutes_{y}.md"
        with open(bundle, "w") as bf:
            for f in fs:
                bf.write(f.read_text(errors="ignore") + "\n\n---\n\n")
        print(f"[+] NotebookLM source file: {bundle.name} ({len(fs)} meetings)")
    print(f"[+] Corpus: {made} meeting transcripts in {CORPUS}; bundle in {NB_DIR}")
    print("    Next: `search <terms>` locally, or upload notebooklm/*.md to a NotebookLM notebook.")


def corpus_search(query: str, limit: int = 10):
    terms = [t.lower() for t in query.split() if t]
    hits = []
    for f in sorted(CORPUS.glob("*.txt")) + sorted((CORPUS / "extra").glob("*.txt")):
        text = f.read_text(errors="ignore")
        low = text.lower()
        if not all(t in low for t in terms):
            continue
        score = low.count(" ".join(terms)) * 10 + sum(low.count(t) for t in terms)
        snippet = ""
        for mm in re.finditer(re.escape(terms[0]), low):
            cand = text[max(0, mm.start() - 160):mm.start() + 260].replace("\n", " ")
            if all(t in cand.lower() for t in terms):
                snippet = cand
                break
        hits.append({"score": score, "file": f.name, "snippet": snippet or text[:220]})
    hits.sort(key=lambda h: -h["score"])
    return hits[:limit]


def cmd_search(args) -> None:
    if not CORPUS.exists():
        sys.exit("no corpus yet - run: cheyenne_pipeline.py corpus")
    hits = corpus_search(args.query, args.limit)
    if not hits:
        print("no hits - try fewer terms, or rebuild the corpus")
        return
    for h in hits:
        print(f"\n=== {h['file']} (score {h['score']}) ===")
        print("   ...", h["snippet"][:400], "...")
    print(f"\n[+] {len(hits)} files match")


NB_PROMPT = """NOTEBOOKLM PROMPT PACK - Cheyenne meeting-minutes notebook
=========================================================
Upload the files in pipeline/notebooklm/ (cheyenne_minutes_YYYY.md, one per year,
plus any of your own verbatim transcripts) as sources in ONE NotebookLM notebook.
Then paste the following, with your question at the top:

---
MY QUESTION: <<paste your question here>>

Answer using ONLY the uploaded meeting sources. Find the strongest on-the-record
moments, then reply with STRICT JSON only - no markdown fences, no commentary:

{
 "hook": "<= 8 words: the on-screen opener for a short video",
 "narration": "<= 80 words: neutral answer script, citing meeting dates",
 "segments": [
  {"clip_id": <CLIP_ID number from the source header>,
   "date": "YYYY-MM-DD",
   "quote": "<= 35-word VERBATIM quote from that meeting's minutes",
   "source_label": "Cheyenne City Council - Mon DD, YYYY",
   "start": null, "end": null}
 ]
}

Rules: 3-6 segments, strongest first. Every quote must appear verbatim in the
sources - do not invent meetings, dates, quotes, or clip_ids. If a source file
contains video timestamps (e.g. your sync-to-video transcripts), put them in
start/end as "HH:MM:SS"; otherwise null.
---

Save the JSON reply as answer.json, fill any null start/end (from your sync
transcripts or by scrubbing the player at cheyenne.granicus.com), then run:
    python3 cheyenne_pipeline.py answer answer.json
which renders a vertical 1080x1920 captioned social reel automatically.
"""


def cmd_nbprompt(args) -> None:
    NB_DIR.mkdir(exist_ok=True)
    (NB_DIR / "PROMPT.txt").write_text(NB_PROMPT)
    print(NB_PROMPT)


VF_BLUR = ("split=2[bgS][fgS];[bgS]scale=1080:1920:force_original_aspect_ratio=increase,"
           "crop=1080:1920,boxblur=24:5[bg];[fgS]scale=1080:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2")


def _vtext_files(work: Path, tag: str, caption: str, source_label: str):
    cap = work / f"cap_{tag}.txt"
    cap.write_text(wrap_text(caption, width=26))
    srcf = work / f"src_{tag}.txt"
    srcf.write_text(source_label)
    return cap, srcf


def vertical_segment(src: Path, caption: str, source_label: str, work: Path, tag: str) -> Path:
    need_ffmpeg()
    font = find_font()
    cap, srcf = _vtext_files(work, tag, caption, source_label)
    dt_cap = (f"drawtext=fontfile={font}:textfile={cap}:fontcolor=white:fontsize=56:"
              "box=1:boxcolor=black@0.55:boxborderw=20:x=(w-text_w)/2:y=h*0.66:line_spacing=12")
    dt_src = (f"drawtext=fontfile={font}:textfile={srcf}:fontcolor=white@0.85:fontsize=34:"
              "x=(w-text_w)/2:y=h*0.92")
    out = work / f"v_{tag}.mp4"
    vf = f"{VF_BLUR},{dt_cap},{dt_src},fps=30,format=yuv420p[vout]"
    r = run(["ffmpeg", "-y", "-i", str(src), "-filter_complex", vf,
             "-map", "[vout]", "-map", "0:a?",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
             "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "128k", str(out)])
    if r.returncode != 0:
        raise RuntimeError(f"vertical segment failed: {r.stderr[-400:]}")
    return out


def vertical_card(title: str, sub: str, duration: float, work: Path, tag: str) -> Path:
    need_ffmpeg()
    font = find_font()
    tf = work / f"card_{tag}.txt"
    tf.write_text(wrap_text(title, width=22))
    sf = work / f"cardsub_{tag}.txt"
    sf.write_text(sub)
    vf = (f"color=black:size=1080x1920:rate=30,format=yuv420p,"
          f"drawtext=fontfile={font}:textfile={tf}:fontcolor=white:fontsize=88:"
          f"x=(w-text_w)/2:y=h*0.42:line_spacing=22,"
          f"drawtext=fontfile={font}:textfile={sf}:fontcolor=white@0.8:fontsize=40:"
          f"x=(w-text_w)/2:y=h*0.78")
    out = work / f"card_{tag}.mp4"
    r = run(["ffmpeg", "-y", "-f", "lavfi", "-i", vf,
             "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
             "-t", str(duration),
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
             "-c:a", "aac", "-ar", "48000", "-ac", "2", str(out)])
    if r.returncode != 0:
        raise RuntimeError(f"vertical card failed: {r.stderr[-400:]}")
    return out


def cmd_answer(args) -> None:
    """NotebookLM JSON / ask spec / hand-written spec -> vertical social reel.
    Give it a DIRECTORY to render every spec inside (batch mode)."""
    p = Path(args.plan)
    if p.is_dir():
        for f in sorted(p.glob("*.json")):
            try:
                cmd_answer(type("A", (), {"plan": str(f)})())
            except Exception as e:
                print(f"[!] {f.name}: {e}")
        return
    raw = p.read_text().strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\n|\n```$", "", raw)
    spec = json.loads(raw)
    segs = spec.get("segments") or []
    hook = spec.get("hook") or spec.get("question") or "The city's own words"
    cta = spec.get("cta") or "Full meetings: cheyenne.granicus.com"
    max_len = float(spec.get("max_len") or 45)
    RENDERS.mkdir(parents=True, exist_ok=True)
    work = RENDERS / f"answer_{int(time.time())}"
    work.mkdir(parents=True, exist_ok=True)
    parts: list[Path] = []
    srt: list[tuple] = []
    todo: list[dict] = []
    print(f"[*] Answer reel: {hook!r} - {len(segs)} segments")
    parts.append(vertical_card(hook, spec.get("question", ""), 2.6, work, "hook"))
    n = 0
    for i, seg in enumerate(segs):
        if not (seg.get("start") and seg.get("end")):
            todo.append(seg)
            continue
        start_s, end_s = to_seconds(seg["start"]), to_seconds(seg["end"])
        if end_s - start_s > max_len:
            end_s = start_s + max_len
        if seg.get("file"):
            src = cut_clip(Path(seg["file"]), fmt_ts(start_s), fmt_ts(end_s),
                           name=f"_a{i}", reencode=False)
        elif seg.get("url"):
            src = stream_clip(seg["url"], fmt_ts(start_s), fmt_ts(end_s),
                              name=f"_a{i}")
        else:
            src = smart_clip(str(seg["meeting"]), fmt_ts(start_s), fmt_ts(end_s),
                             name=f"_a{i}")
        n += 1
        label = seg.get("source_label") or f"Cheyenne City Council - {seg.get('date', '')}"
        parts.append(vertical_segment(src, seg.get("quote") or seg.get("caption") or "",
                                      label, work, f"{i:02d}"))
        srt.append((end_s - start_s, seg.get("quote") or label))
        print(f"    [{n}] {label}  {seg['start']}-{fmt_ts(end_s)}")
    parts.append(vertical_card(cta, "@you - source: city records", 2.6, work, "cta"))
    if not n:
        print("[!] no timestamped segments - see edit sheet; nothing to stitch")
    else:
        lst = work / "list.txt"
        lst.write_text("".join(f"file '{p.resolve().as_posix()}'\n" for p in parts))
        out = RENDERS / (spec.get("output") or re.sub(r"[^A-Za-z0-9_-]", "_", hook)[:40] + ".mp4")
        r = run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                 "-c", "copy", str(out)])
        if r.returncode != 0:
            r = run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                     "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
                     "-c:a", "aac", "-ar", "48000", "-ac", "2", str(out)])
            if r.returncode != 0:
                raise RuntimeError(f"answer concat failed: {r.stderr[-400:]}")
        srt_path = out.with_suffix(".srt")
        t0, blocks = 2.6, []
        for j, (dur, text) in enumerate([(2.6, hook)] + srt + [(2.6, cta)], 1):
            def _f(t):
                h, rem = divmod(int(t), 3600)
                m, s2 = divmod(rem, 60)
                return f"{h:02d}:{m:02d}:{s2:02d},000"
            blocks.append(f"{j}\n{_f(t0)} --> {_f(t0 + dur)}\n{text}\n")
            t0 += dur
        srt_path.write_text("\n".join(blocks))
        post = work_with_post(spec, segs, todo)
        print(f"[+] SOCIAL REEL -> {out} ({out.stat().st_size/1e6:.1f} MB, 1080x1920, SRT: {srt_path.name})")
        print(post)


def work_with_post(spec, segs, todo) -> str:
    lines = [f"POST CAPTION (draft):", spec.get("question", ""), "",
             f"{spec.get('hook','')}", ""]
    for s in segs:
        lines.append(f"- {s.get('source_label','')} ({s.get('date','')}): \"{s.get('quote','')}\"")
    lines += ["", "#Cheyenne #Wyoming #CityCouncil #LocalGovernment #OpenRecords"]
    if todo:
        lines += ["", "EDIT SHEET - fill these timestamps then re-run:",
                  *(f"  - clip {s.get('clip_id', s.get('meeting', '?'))} ({s.get('date','')}): "
                    f"\"{s.get('quote','')[:70]}\" needs start/end" for s in todo)]
    txt = "\n".join(lines)
    (RENDERS / "POST.txt").write_text(txt)
    return txt



# ----------------------------------------------------------------------------
# 7. ASK ENGINE (local answer generation), VERIFY, AUTOPILOT, BATCH REELS
# ----------------------------------------------------------------------------

ASKS = ROOT / "asks"
STOPWORDS = set(("what who when where why how has have had did does do the a an of to in on for "
"and or but is are was were be been being it its this that these those they them their there here "
"about into over under after before during through between with without from by at as not no yes "
"you your we our i me my he she his her will would could should can may might must shall "
"said says say told get got go went make made take took").split())


def _terms(q: str) -> list[str]:
    return [w.lower() for w in re.findall(r"[a-zA-Z']{4,}", q) if w.lower() not in STOPWORDS]


def _sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text)
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z\"'])", text) if s.strip()]


def _meet_from_file(f: Path):
    head = f.read_text(errors="ignore")[:300]
    m = re.search(r"CLIP_ID:\s*(\d+)", head)
    d = re.search(r"DATE:\s*([\d-]+)", head)
    return (int(m.group(1)) if m else f.stem.split("_")[0],
            d.group(1) if d else (f.stem.split("_")[-1] if len(f.stem.split("_")) > 1 else ""))


def _find_timestamp(quote: str, clip_id: int):
    """If a sync-to-video transcript exists in corpus/extra for this meeting,
    find a line whose text overlaps the quote and return its timestamp."""
    for f in (CORPUS / "extra").glob(f"{clip_id}*.txt"):
        for line in f.read_text(errors="ignore").splitlines():
            m = re.match(r"\s*(?:(\d{1,2}):)?(\d{1,2}):(\d{2})\s*[-\u2013\u2014|]?\s*(.+)", line)
            if not m:
                continue
            h, mi, s, rest = m.groups()
            words = re.findall(r"[a-z']{4,}", rest.lower())
            qwords = re.findall(r"[a-z']{4,}", quote.lower())
            if words and qwords and len(set(words) & set(qwords)) >= max(3, min(6, len(qwords) // 2)):
                start = f"{int(h or 0):02d}:{int(mi):02d}:{s}"
                dur = min(40, max(8, round(len(rest.split()) / 2.6)))
                sh, sm, ss = int(h or 0), int(mi), int(s)
                tot = sh * 3600 + sm * 60 + int(ss) + dur
                end = f"{tot // 3600:02d}:{tot % 3600 // 60:02d}:{tot % 60:02d}"
                return start, end
    return None, None


def ask_engine(question: str, max_segments: int = 5) -> dict:
    terms = _terms(question) or question.lower().split()
    files = sorted(CORPUS.glob("*.txt")) + sorted((CORPUS / "extra").glob("*.txt"))
    if not files:
        sys.exit("no corpus - run: cheyenne_pipeline.py corpus")
    scored = []
    for f in files:
        text = f.read_text(errors="ignore")
        low = text.lower()
        score = sum(low.count(t) for t in terms) + 8 * low.count(" ".join(terms[:2]))
        if score:
            scored.append((score, f, text))
    scored.sort(key=lambda x: -x[0])
    candidates = []
    for score, f, text in scored[:12]:
        cid, date = _meet_from_file(f)
        for sent in _sentences(text):
            sl = sent.lower()
            hits = sum(1 for t in terms if t in sl)
            if hits >= min(2, len(terms)) and 40 <= len(sent) <= 340:
                candidates.append((hits * 10 + score // 50, cid, date, sent))
    candidates.sort(key=lambda c: -c[0])
    picked, used_files = [], {}
    for sc, cid, date, sent in candidates:
        if used_files.get(cid, 0) >= 2 or len(picked) >= max_segments:
            continue
        used_files[cid] = used_files.get(cid, 0) + 1
        s, e = _find_timestamp(sent, cid)
        picked.append({"clip_id": cid, "date": date, "quote": sent,
                       "source_label": f"Cheyenne City Council - {date}",
                       "start": s, "end": e})
    hook = " ".join(question.split()[:8])
    return {"question": question, "hook": hook,
            "narration": "Across " + str(len({p['date'] for p in picked})) +
                         " meetings on the record: " +
                         " ".join(p["quote"][:90].rsplit(" ", 1)[0] + " ..." for p in picked[:2]),
            "segments": picked, "cta": "Full meetings: cheyenne.granicus.com"}


def cmd_ask(args) -> None:
    ASKS.mkdir(exist_ok=True)
    questions = []
    if args.batch:
        questions = [q.strip() for q in Path(args.batch).read_text().splitlines() if q.strip()]
    else:
        questions = [args.question]
    made = []
    for q in questions:
        spec = ask_engine(q, args.max)
        n = len(list(ASKS.glob("ask_*.json"))) + 1
        out = ASKS / f"ask_{n:03d}.json"
        out.write_text(json.dumps(spec, indent=1))
        ready = sum(1 for s in spec["segments"] if s["start"])
        print(f"[+] {out.name}: '{q}' -> {len(spec['segments'])} segments "
              f"({ready} timestamped{', render-ready' if ready else ''})")
        made.append(out)
        if args.auto and ready:
            cmd_answer(type("A", (), {"plan": str(out)})())
    print(f"[+] {len(made)} ask specs in {ASKS}  (edit timestamps, then: answer {ASKS}/ask_001.json)")


def cmd_verify(args) -> None:
    """Verbatim check of a quote against every meeting transcript."""
    quote = re.sub(r"\s+", " ", args.quote.strip().lower())
    files = sorted(CORPUS.glob("*.txt")) + sorted((CORPUS / "extra").glob("*.txt"))
    if len(quote) < 15:
        sys.exit("quote too short to verify")
    head, tail = quote[:60], quote[-60:]
    found = []
    for f in files:
        text = re.sub(r"\s+", " ", f.read_text(errors="ignore").lower())
        where = "EXACT" if quote in text else (
            "PARTIAL" if (head in text or tail in text) else None)
        if where:
            i = text.find(head if head in text else tail)
            found.append((where, f.name, text[max(0, i - 80):i + len(quote) + 80]))
    if not found:
        print("NOT FOUND in any meeting transcript - do not publish without the tape.")
        return
    for where, name, ctx in found[:6]:
        print(f"[{where}] {name}\n    ...{ctx}...")


def cmd_autopass(args) -> None:
    """One research pass: refresh index, pull docs+corpus for anything new."""
    old = set(load_index()) if MEETINGS_JSON.exists() else set()
    cmd_index(type("A", (), {})())
    new = sorted(set(load_index()) - old)
    print(f"[*] {len(new)} new meetings" + (f": {new}" if new else ""))
    for c in new:
        m = load_index()[c]
        if m.get("minutes_url"):
            try:
                raw = http_get(m["minutes_url"]).content
                (CORPUS / f"{c}_{m.get('date') or 'unknown'}.txt").write_text(
                    f"MEETING: {m.get('name','City Council')} | DATE: {m.get('date','?')} | "
                    f"CLIP_ID: {c} | SOURCE: cheyenne.granicus.com MinutesViewer clip {c}\n\n"
                    + minutes_to_text(raw))
                print(f"    [+] corpus: {c} {m.get('date')}")
            except Exception as e:
                print(f"    [!] minutes {c}: {e}")
        try:
            fetch_meeting_docs(c, m, 0)
        except Exception as e:
            print(f"    [!] docs {c}: {e}")
    if new:
        cmd_corpus(type("A", (), {"since": "", "force": False})())
    print("[+] autopass complete")


def parse_turns(text: str, meeting=None) -> list[dict]:
    """Paste a sync-to-video transcript; every timestamped line becomes a clip spec."""
    rows = []
    for line in text.splitlines():
        m = re.match(r"\s*(?:(\d{1,2}):)?(\d{1,2}):(\d{2})\s*[-\u2013\u2014|]?\s*(.+)", line)
        if m:
            h, mi, s, rest = m.groups()
            rows.append({"start": f"{int(h or 0):02d}:{int(mi):02d}:{s}",
                         "end": None, "label": rest.strip()[:60]})
    for i, r in enumerate(rows):
        tot = (lambda hms: int(hms[0]) * 3600 + int(hms[1]) * 60 + int(hms[2]))(r["start"].split(":"))
        nxt = rows[i + 1]["start"] if i + 1 < len(rows) else None
        end = (lambda hms: int(hms[0]) * 3600 + int(hms[1]) * 60 + int(hms[2]))(nxt.split(":")) \
            if nxt else tot + 180
        end = min(end, tot + 600)
        r["end"] = f"{end // 3600:02d}:{end % 3600 // 60:02d}:{end % 60:02d}"
        r["name"] = re.sub(r"[^A-Za-z0-9_-]", "_", r["label"])[:40] or f"turn_{i+1:02d}"
        if meeting:
            r["meeting"] = meeting
    return rows


def cmd_captions(args) -> None:
    """Grab the WebVTT track (empty on this Granicus instance so far, but cheap)."""
    cid = int(args.meeting) if args.meeting.isdigit() else resolve(args.meeting)[0]
    url = f"{BASE}videos/{cid}/captions.vtt"
    r = http_get(url)
    DOCS.mkdir(parents=True, exist_ok=True)
    out = DOCS / f"{cid}_captions.vtt"
    out.write_bytes(r.content)
    status = "EMPTY (not populated)" if len(r.content) <= 12 else f"{len(r.content)//1024} KB"
    print(f"[+] {out} — {status}")


def cmd_clip(args) -> None:
    smart_clip(args.meeting, args.start, args.end, name=args.name)


# ----------------------------------------------------------------------------
# 5. PROJECT — stitch meeting clips + commentary into one video
# ----------------------------------------------------------------------------

NORMAL = ["-vf", "scale=1280:720:force_original_aspect_ratio=decrease,"
          "pad=1280:720:(ow-iw)/2:(oh-ih)/2,fps=30,format=yuv420p",
          "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
          "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "160k"]

FONT_CANDIDATES = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                   "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
                   "/System/Library/Fonts/Helvetica.ttc",
                   "C:/Windows/Fonts/arial.ttf"]


def find_font() -> Optional[str]:
    return next((f for f in FONT_CANDIDATES if Path(f).exists()), None)


def wrap_text(text: str, width: int = 34) -> str:
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return "\n".join(lines[:6])


def make_title_card(text: str, duration: float, workdir: Path) -> Path:
    need_ffmpeg()
    font = find_font()
    out = workdir / f"title_{abs(hash(text)) % 99999}.mp4"
    vf = "color=black:size=1280x720:rate=30,format=yuv420p"
    if font:
        tf = workdir / f"title_{abs(hash(text)) % 99999}.txt"
        tf.write_text(wrap_text(text))
        vf = (f"color=black:size=1280x720:rate=30,format=yuv420p,"
              f"drawtext=fontfile={font}:textfile={tf}:fontcolor=white:fontsize=44:"
              f"x=(w-text_w)/2:y=(h-text_h)/2:line_spacing=14")
    cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", vf,
           "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
           "-t", str(duration), *NORMAL[0:8], str(out)]
    r = run(cmd)
    if r.returncode != 0:
        raise RuntimeError(f"title card failed: {r.stderr[-500:]}")
    return out


def normalize_clip(src: Path, start: Optional[str], end: Optional[str],
                   overlay_audio: Optional[str], duck: bool, workdir: Path, tag: str) -> Path:
    """One timeline item -> a normalized 1280x720/30fps/aac mp4 in workdir."""
    need_ffmpeg()
    out = workdir / f"seg_{tag}.mp4"
    seek = ["-ss", fmt_ts(to_seconds(start))] if start else []
    trim = ["-to", fmt_ts(to_seconds(end))] if end else []
    inputs = [*seek, "-i", str(src), *trim]

    if overlay_audio:
        filters = "[1:a]volume=1.6,asplit=2[sc][vo]"
        if duck:
            filters += (";[0:a][sc]sidechaincompress=threshold=0.03:ratio=12:"
                        "attack=20:release=400[bg];"
                        "[bg][vo]amix=inputs=2:duration=first:normalize=0[aout]")
            amap = "[aout]"
        else:
            filters += ";[0:a][vo]amix=inputs=2:duration=first:normalize=0[aout]"
            amap = "[aout]"
        cmd = ["ffmpeg", "-y", *inputs, "-i", overlay_audio,
               "-filter_complex", filters, "-map", "0:v", "-map", amap,
               *NORMAL, str(out)]
    else:
        cmd = ["ffmpeg", "-y", *inputs, *NORMAL, str(out)]
    r = run(cmd)
    if r.returncode != 0:
        raise RuntimeError(f"normalize {src.name} failed: {r.stderr[-800:]}")
    return out


def cmd_project(args) -> None:
    plan = json.loads(Path(args.plan).read_text())
    segments = plan.get("segments") or plan
    RENDERS.mkdir(parents=True, exist_ok=True)
    work = RENDERS / f"work_{int(time.time())}"
    work.mkdir(parents=True, exist_ok=True)
    parts: list[Path] = []

    print(f"[*] Building {len(segments)} segments ...")
    for i, seg in enumerate(segments):
        kind = seg.get("type", "clip")
        if kind == "title":
            card = make_title_card(seg["text"], seg.get("duration", 4), work)
            parts.append(card)
            print(f"    [{i+1}/{len(segments)}] title card: {seg['text'][:40]}")
        elif kind == "file":
            p = normalize_clip(Path(seg["path"]), None, None,
                               seg.get("overlay_audio"), seg.get("duck", True), work, f"{i:02d}f")
            parts.append(p)
            print(f"    [{i+1}/{len(segments)}] commentary/file: {Path(seg['path']).name}")
        elif kind == "clip":
            seg_name = seg.get("name") or f"seg_{i:02d}_{seg.get('meeting')}"
            p = smart_clip(str(seg.get("meeting")), seg.get("start"), seg.get("end"),
                           name=seg_name, normalize=True)
            if not p.exists():
                sys.exit(f"clip failed: {seg}")
            parts.append(p)
            label = f"meeting {cid} {seg.get('start','')}-{seg.get('end','')}"
            print(f"    [{i+1}/{len(segments)}] clip: {label}")
        else:
            sys.exit(f"Unknown segment type {kind!r} (use clip|file|title)")

    if len(parts) == 1:
        final = RENDERS / plan.get("output", "render.mp4")
        shutil.copy(parts[0], final)
        print(f"[+] Single segment; saved {final}")
        return

    concat_file = work / "list.txt"
    concat_file.write_text("".join(f"file '{p.resolve().as_posix()}'\n" for p in parts))
    final = RENDERS / plan.get("output", "render.mp4")
    r = run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
             "-c", "copy", str(final)])
    if r.returncode != 0:
        # codec mismatch safety net: full re-encode of the concat
        print("    [.] stream copy failed; re-encoding concat ...")
        r = run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
                 *NORMAL, str(final)])
        if r.returncode != 0:
            raise RuntimeError(f"stitch failed: {r.stderr[-800:]}")
    print(f"[+] Rendered {final} ({final.stat().st_size/1e6:.1f} MB)")
    if not args.keep_work:
        shutil.rmtree(work, ignore_errors=True)


def cmd_example(args) -> None:
    example = {
        "output": "mlk_reel.mp4",
        "segments": [
            {"type": "title", "text": "MLK Park, by the numbers", "duration": 4},
            {"type": "clip", "meeting": 1071, "start": "00:04:10", "end": "00:06:30"},
            {"type": "file", "path": "commentary/my_response.mp4"},
            {"type": "clip", "meeting": 1103, "start": "01:22:00", "end": "01:25:00",
             "overlay_audio": "commentary/voiceover_mix.mp3", "duck": True},
            {"type": "title", "text": "19,795 bookings. 16 park arrests.", "duration": 4}
        ]
    }
    Path(args.path).write_text(json.dumps(example, indent=2))
    print(f"[+] Example project written to {args.path}")
    print("    Edit it, then: cheyenne_pipeline.py project " + args.path)


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Cheyenne municipal records & video pipeline")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("index", help="build/refresh meetings.json from the city archive")
    sp.set_defaults(fn=cmd_index)

    sp = sub.add_parser("list", help="list indexed meetings")
    sp.add_argument("--search", default="")
    sp.add_argument("--limit", type=int, default=40)
    sp.set_defaults(fn=cmd_list)

    sp = sub.add_parser("docs", help="download agenda/minutes/supporting docs")
    sp.add_argument("meeting", nargs="?", help="clip_id or search text (e.g. 1091 or 'Apr 13')")
    sp.add_argument("--all", action="store_true", help="every indexed meeting")
    sp.add_argument("--since", default="", help="with --all: YYYY-MM-DD floor")
    sp.add_argument("--max-docs", type=int, default=0, help="0 = no limit")
    sp.set_defaults(fn=cmd_docs)

    sp = sub.add_parser("video", help="download meeting video(s)")
    sp.add_argument("meeting", nargs="?")
    sp.add_argument("--all", action="store_true")
    sp.add_argument("--since", default="")
    sp.add_argument("--seconds", type=float, default=0,
                    help="partial fetch (testing / quick access), 0 = full")
    sp.add_argument("--url", default="",
                    help="explicit stream URL (m3u8/mp4 copied from a browser network tab)")
    sp.set_defaults(fn=cmd_video)

    sp = sub.add_parser("captions", help="fetch the WebVTT caption track for a meeting")
    sp.add_argument("meeting")
    sp.set_defaults(fn=cmd_captions)

    sp = sub.add_parser("grab", help="download any URL via yt-dlp (YouTube/Facebook)")
    sp.add_argument("url")
    sp.set_defaults(fn=cmd_grab)

    sp = sub.add_parser("clip", help="cut a timestamped segment from a meeting video")
    sp.add_argument("meeting")
    sp.add_argument("--start", required=True, help="HH:MM:SS or MM:SS")
    sp.add_argument("--end", required=True)
    sp.add_argument("--name", default="")
    sp.add_argument("--fast", action="store_true", help="keyframe-aligned copy, no re-encode")
    sp.set_defaults(fn=cmd_clip)

    sp = sub.add_parser("segments", help="batch-create clips from a JSON spec (stream-local, no full downloads)")
    sp.add_argument("plan", help="JSON: [{meeting|url, start, end, name}, ...]")
    sp.add_argument("--force", action="store_true", help="re-create existing clips")
    sp.set_defaults(fn=cmd_segments)

    sp = sub.add_parser("corpus", help="build searchable minutes corpus + NotebookLM bundle")
    sp.add_argument("--since", default="")
    sp.add_argument("--force", action="store_true")
    sp.set_defaults(fn=cmd_corpus)

    sp = sub.add_parser("search", help="search the minutes corpus")
    sp.add_argument("query")
    sp.add_argument("--limit", type=int, default=10)
    sp.set_defaults(fn=cmd_search)

    sp = sub.add_parser("nbprompt", help="print/write the NotebookLM prompt pack")
    sp.set_defaults(fn=cmd_nbprompt)

    sp = sub.add_parser("answer", help="NotebookLM JSON -> vertical social answer reel")
    sp.add_argument("plan", help="answer.json (NotebookLM reply or hand-written)")
    sp.set_defaults(fn=cmd_answer)

    sp = sub.add_parser("ask", help="question -> render-ready answer spec (local quote engine)")
    sp.add_argument("question", nargs="?")
    sp.add_argument("--batch", default="", help="file with one question per line")
    sp.add_argument("--max", type=int, default=5)
    sp.add_argument("--auto", action="store_true", help="render reels immediately when timestamps exist")
    sp.set_defaults(fn=cmd_ask)

    sp = sub.add_parser("verify", help="verbatim-check a quote against every transcript")
    sp.add_argument("quote")
    sp.set_defaults(fn=cmd_verify)

    sp = sub.add_parser("autopass", help="refresh index + auto-pull docs/minutes for new meetings")
    sp.set_defaults(fn=cmd_autopass)

    sp = sub.add_parser("project", help="stitch clips + commentary per a project JSON")
    sp.add_argument("plan")
    sp.add_argument("--keep-work", action="store_true", help="keep normalized intermediates")
    sp.set_defaults(fn=cmd_project)

    sp = sub.add_parser("example", help="write an example project JSON")
    sp.add_argument("--path", default="project_example.json")
    sp.set_defaults(fn=cmd_example)

    args = ap.parse_args()
    for d in (VIDEOS, DOCS, CLIPS, RENDERS):
        d.mkdir(exist_ok=True)
    args.fn(args)


if __name__ == "__main__":
    main()
