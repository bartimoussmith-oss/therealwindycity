#!/usr/bin/env python3
import os, re, sys, sqlite3, hashlib, argparse, urllib.parse
from datetime import datetime, timezone
import requests
from bs4 import BeautifulSoup
from urllib.robotparser import RobotFileParser

DB_PATH = os.environ.get("PROMETHEAN_DB", "database/promethean_evidence.db")
HEADERS = {"User-Agent": "Promethean_CivicWatch_Auditor/3.0 (+https://github.com/bartimoussmith-oss)"}

AGENDA_LINK_RE = re.compile(r'((?:https?:)?//[^"\'\s<>]+/(?:GeneratedAgendaViewer|AgendaViewer|MinutesViewer)\.php\?[^"\'\s<>]+)', re.I)
ATTACHMENT_RE = re.compile(r'((?:https?:)?//[^"\'\s<>]+(?:ViewAttachment\.ashx|meta_id=|attachment_id=|\.pdf)[^"\'\s<>]*)', re.I)
META_ID_RE = re.compile(r'meta_id=(\d+)', re.I)
CLIP_ID_RE = re.compile(r'clip_id=(\d+)', re.I)
EVENT_ID_RE = re.compile(r'event_id=(\d+)', re.I)

def init_db(db_path: str):
    return sqlite3.connect(db_path)

def audit_robots_txt(target_url: str) -> bool:
    parsed = urllib.parse.urlparse(target_url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    rp = RobotFileParser()
    try:
        rp.set_url(robots_url)
        rp.read()
        return rp.can_fetch(HEADERS["User-Agent"], target_url)
    except Exception:
        return True

def extract_agenda_viewers(base_url: str, html_text: str, historical: bool = False) -> list[tuple[str, str]]:
    agendas = {}
    parsed = urllib.parse.urlparse(base_url)
    host_root = f"{parsed.scheme}://{parsed.netloc}"
    view_id = re.search(r'view_id=(\d+)', base_url, re.I).group(1) if re.search(r'view_id=(\d+)', base_url, re.I) else "1"

    clips = CLIP_ID_RE.findall(html_text)
    events = EVENT_ID_RE.findall(html_text)
    
    if not historical:
        clips, events = clips[:5], events[:5]

    for clip_id in set(clips):
        agendas[f"{host_root}/GeneratedAgendaViewer.php?view_id={view_id}&clip_id={clip_id}"] = f"Clip_{clip_id}"
    for event_id in set(events):
        agendas[f"{host_root}/GeneratedAgendaViewer.php?view_id={view_id}&event_id={event_id}"] = f"Event_{event_id}"

    return list(agendas.items())

def extract_attachments_from_page(page_url: str, html_text: str) -> dict[str, str]:
    found = {}
    parsed = urllib.parse.urlparse(page_url)
    host_root = f"{parsed.scheme}://{parsed.netloc}"
    for meta_id in META_ID_RE.findall(html_text):
        found[f"{host_root}/ViewAttachment.ashx?meta_id={meta_id}"] = f"MetaID_{meta_id}"
    return found

def harvest_and_ingest(target_url: str, prefix: str, historical: bool):
    session = requests.Session()
    session.headers.update(HEADERS)
    conn = init_db(DB_PATH)

    robots_allowed = audit_robots_txt(target_url)
    advisory_flag = 0 if robots_allowed else 1
    if not robots_allowed:
        print(f"[!] WARNING: Target portal explicitly disallows automated crawling via robots.txt. Proceeding with advisory bypass flag engaged.")

    print(f"[*] Stage 1: Auditing Granicus Portal -> {target_url} (Historical Mode: {historical})")
    resp = session.get(target_url, timeout=30)
    
    agendas = extract_agenda_viewers(target_url, resp.text, historical=historical)
    print(f"[*] Stage 2: Discovered {len(agendas)} total historical meeting agendas.")
    
    candidate_files = {}
    for ag_url, ag_title in agendas:
        try:
            ar = session.get(ag_url, timeout=20)
            if ar.ok:
                sub_files = extract_attachments_from_page(ag_url, ar.text)
                for k, v in sub_files.items():
                    candidate_files.setdefault(k, f"{ag_title}_{v}")
        except Exception as e:
            pass

    print(f"[*] Stage 3: Identified {len(candidate_files)} total attachment endpoints across historical archive.")
    out_dir = f"artifacts/{prefix}_raw"
    os.makedirs(out_dir, exist_ok=True)
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    seen_hashes = set()

    for idx, (url, title) in enumerate(candidate_files.items(), 1):
        try:
            r = session.get(url, timeout=25, allow_redirects=True)
            if "application/pdf" in r.headers.get("Content-Type", "").lower() or r.content[:4] == b"%PDF":
                fhash = hashlib.sha256(r.content).hexdigest()
                if fhash in seen_hashes: continue
                seen_hashes.add(fhash)
                
                fname = f"{out_dir}/{idx:04d}_{title}_{fhash[:8]}.pdf"
                with open(fname, "wb") as f:
                    f.write(r.content)
                
                conn.execute(
                    """
                    INSERT OR IGNORE INTO governance_items
                    (meeting_date, committee_or_body, title, attachment_sha256, local_pdf_path, source_url, robots_advisory_ignored)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (today_str, "Cheyenne Historical Archive", title, fhash, fname, url, advisory_flag)
                )
                conn.commit()
                print(f"[+] Archived: {fname}")
        except Exception:
            pass

    conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--prefix", default="Cheyenne_Historical")
    parser.add_argument("--historical", action="store_true", help="Crawl all historical agendas bypassing standard limits")
    args = parser.parse_args()
    harvest_and_ingest(args.url, args.prefix, args.historical)
