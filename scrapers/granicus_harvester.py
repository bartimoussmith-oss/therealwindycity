#!/usr/bin/env python3
import os, re, sys, sqlite3, hashlib, argparse, urllib.parse
from datetime import datetime, timezone
import requests
from bs4 import BeautifulSoup

DB_PATH = os.environ.get("PROMETHEAN_DB", "database/promethean_evidence.db")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
}

AGENDA_LINK_RE = re.compile(
    r'((?:https?:)?//[^"\'\s<>]+/(?:GeneratedAgendaViewer|AgendaViewer|MinutesViewer)\.php\?[^"\'\s<>]+|/(?:GeneratedAgendaViewer|AgendaViewer|MinutesViewer)\.php\?[^"\'\s<>]+)',
    re.I
)
ATTACHMENT_RE = re.compile(
    r'((?:https?:)?//[^"\'\s<>]+(?:ViewAttachment\.ashx|meta_id=|attachment_id=|\.pdf)[^"\'\s<>]*|/(?:ViewAttachment\.ashx|AgendaViewer\.php|GeneratedAgendaViewer\.php)[^"\'\s<>]*(?:meta_id=|attachment_id=)[^"\'\s<>]*)',
    re.I
)
META_ID_RE = re.compile(r'meta_id=(\d+)', re.I)
CLIP_ID_RE = re.compile(r'clip_id=(\d+)', re.I)
EVENT_ID_RE = re.compile(r'event_id=(\d+)', re.I)

def init_db(db_path: str):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    schema_file = "database/schema_rhetorical_profiling.sql"
    if os.path.exists(schema_file):
        with open(schema_file, "r", encoding="utf-8") as f:
            conn.executescript(f.read())
    return conn

def normalize_url(base_url: str, raw: str) -> str:
    cleaned = raw.strip("'\" ").replace("&amp;", "&")
    if cleaned.startswith("//"):
        cleaned = "https:" + cleaned
    return urllib.parse.urljoin(base_url, cleaned)

def extract_agenda_viewers(base_url: str, html_text: str, max_agendas: int = 5) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html_text, "html.parser")
    agendas = {}

    for a in soup.find_all(["a", "iframe"]):
        href = a.get("href") or a.get("src") or a.get("onclick") or ""
        label = a.get_text(" ", strip=True) or a.get("title") or "Granicus_Agenda"
        if any(k in href.lower() for k in ["agendaviewer", "minutesviewer", "clip_id=", "event_id="]):
            m = re.search(r"['\"]([^'\"]+)['\"]", href) if "window." in href or "open(" in href else None
            target = m.group(1) if m else href
            full = normalize_url(base_url, target)
            if "viewpublisher.php" not in full.lower():
                agendas[full] = label[:100]

    for match in AGENDA_LINK_RE.findall(html_text):
        full = normalize_url(base_url, match)
        agendas.setdefault(full, "Discovered_Agenda_Viewer")

    parsed = urllib.parse.urlparse(base_url)
    host_root = f"{parsed.scheme}://{parsed.netloc}"
    view_id_match = re.search(r'view_id=(\d+)', base_url, re.I)
    view_id = view_id_match.group(1) if view_id_match else "1"

    for clip_id in CLIP_ID_RE.findall(html_text)[:max_agendas]:
        constructed = f"{host_root}/GeneratedAgendaViewer.php?view_id={view_id}&clip_id={clip_id}"
        agendas.setdefault(constructed, f"Clip_{clip_id}_Agenda")

    for event_id in EVENT_ID_RE.findall(html_text)[:max_agendas]:
        constructed = f"{host_root}/GeneratedAgendaViewer.php?view_id={view_id}&event_id={event_id}"
        agendas.setdefault(constructed, f"Event_{event_id}_Agenda")

    return list(agendas.items())[:max_agendas]

def extract_attachments_from_page(page_url: str, html_text: str, session: requests.Session) -> dict[str, str]:
    found = {}
    soup = BeautifulSoup(html_text, "html.parser")

    for iframe in soup.find_all("iframe"):
        src = iframe.get("src")
        if src:
            inner_url = normalize_url(page_url, src)
            try:
                ir = session.get(inner_url, timeout=15)
                if ir.ok:
                    html_text += "\n" + ir.text
                    soup = BeautifulSoup(html_text, "html.parser")
            except Exception:
                pass

    for tag in soup.find_all(["a", "area", "embed"]):
        raw = tag.get("href") or tag.get("src") or tag.get("onclick") or tag.get("data-url") or ""
        label = tag.get_text(" ", strip=True) or tag.get("title") or "Agenda_Attachment"
        if any(k in raw.lower() for k in ["meta_id=", "attachment", "viewattachment", ".pdf"]):
            m = re.search(r"['\"]([^'\"]+)['\"]", raw) if "(" in raw else None
            target = m.group(1) if m else raw
            full = normalize_url(page_url, target)
            found[full] = label[:120]

    for match in ATTACHMENT_RE.findall(html_text):
        full = normalize_url(page_url, match)
        found.setdefault(full, "Regex_Attachment")

    parsed = urllib.parse.urlparse(page_url)
    host_root = f"{parsed.scheme}://{parsed.netloc}"
    for meta_id in META_ID_RE.findall(html_text):
        ashx_url = f"{host_root}/ViewAttachment.ashx?meta_id={meta_id}"
        found.setdefault(ashx_url, f"MetaID_{meta_id}_Attachment")

    return found

def harvest_and_ingest(target_url: str, prefix: str, max_agendas: int = 4, max_files: int = 25):
    session = requests.Session()
    session.headers.update(HEADERS)
    conn = init_db(DB_PATH)

    print(f"[*] Stage 1: Auditing Granicus Portal -> {target_url}")
    resp = session.get(target_url, timeout=25)
    resp.raise_for_status()

    candidate_files = extract_attachments_from_page(target_url, resp.text, session)

    if "viewpublisher.php" in target_url.lower() or len(candidate_files) == 0:
        agendas = extract_agenda_viewers(target_url, resp.text, max_agendas=max_agendas)
        print(f"[*] Stage 2: Discovered {len(agendas)} meeting agenda viewers from Publisher index.")
        for ag_url, ag_title in agendas:
            print(f"    -> Crawling Agenda: {ag_title} ({ag_url})")
            try:
                ar = session.get(ag_url, timeout=20)
                if ar.ok:
                    sub_files = extract_attachments_from_page(ag_url, ar.text, session)
                    print(f"       [+] Found {len(sub_files)} attachment endpoints inside {ag_title}")
                    for k, v in sub_files.items():
                        candidate_files.setdefault(k, f"{ag_title}_{v}")
            except Exception as e:
                print(f"       [!] Agenda fetch error: {e}")

    endpoints = list(candidate_files.items())[:max_files]
    print(f"[*] Stage 3: Identified {len( candidate_files )} total attachment endpoints (processing top {len(endpoints)}).")

    out_dir = f"artifacts/{prefix}_raw"
    os.makedirs(out_dir, exist_ok=True)
    saved_count = 0
    seen_hashes = set()
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    for idx, (url, title) in enumerate(endpoints, 1):
        try:
            r = session.get(url, timeout=20, allow_redirects=True)
            ctype = r.headers.get("Content-Type", "").lower()
            is_pdf = "application/pdf" in ctype or r.content[:4] == b"%PDF"
            is_html_agenda = "text/html" in ctype and len(r.content) > 1500 and ("agenda" in title.lower() or "meta_id" in url.lower())

            if is_pdf or is_html_agenda:
                fhash = hashlib.sha256(r.content).hexdigest()
                if fhash in seen_hashes:
                    continue
                seen_hashes.add(fhash)

                ext = "pdf" if is_pdf else "html"
                safe_title = re.sub(r"[^a-zA-Z0-9_-]", "_", title)[:45].strip("_") or f"record_{idx}"
                fname = f"{out_dir}/{idx:02d}_{safe_title}_{fhash[:10]}.{ext}"
                with open(fname, "wb") as f:
                    f.write(r.content)

                extracted_text = ""
                if not is_pdf:
                    extracted_text = BeautifulSoup(r.text, "html.parser").get_text(" ", strip=True)[:20000]

                conn.execute(
                    """
                    INSERT OR IGNORE INTO governance_items
                    (meeting_date, committee_or_body, title, attachment_sha256, local_pdf_path, source_url, extracted_text)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (today_str, "Cheyenne Governing Body", title, fhash, fname, url, extracted_text)
                )
                conn.commit()
                saved_count += 1
                print(f"[+] Indexed #{saved_count} ({ext.upper()} - {len(r.content)//1024} KB): {fname}")
        except Exception as e:
            print(f"[!] Skipped {url}: {e}")

    conn.close()
    print(f"[+] Harvest complete: {saved_count} municipal records stored in {out_dir} and indexed into {DB_PATH}.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--prefix", default="Cheyenne_Audit")
    args = parser.parse_args()
    harvest_and_ingest(args.url, args.prefix)
