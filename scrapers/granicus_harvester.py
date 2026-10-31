#!/usr/bin/env python3
import os, re, sqlite3, hashlib, argparse, urllib.parse
from datetime import datetime, timezone
import requests
from bs4 import BeautifulSoup
from urllib.robotparser import RobotFileParser

DB_PATH = os.environ.get("PROMETHEAN_DB", "database/promethean_evidence.db")
HEADERS = {"User-Agent": "Promethean_CivicWatch_Auditor/3.0"}
AGENDA_LINK_RE = re.compile(r'((?:https?:)?//[^"\'\s<>]+/(?:GeneratedAgendaViewer|AgendaViewer|MinutesViewer)\.php\?[^"\'\s<>]+)', re.I)

def audit_robots_txt(target_url):
    parsed = urllib.parse.urlparse(target_url)
    rp = RobotFileParser()
    try:
        rp.set_url(f"{parsed.scheme}://{parsed.netloc}/robots.txt")
        rp.read()
        return rp.can_fetch(HEADERS["User-Agent"], target_url)
    except Exception:
        return True

def harvest_and_ingest(target_url, prefix, historical):
    session = requests.Session()
    session.headers.update(HEADERS)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    robots_allowed = audit_robots_txt(target_url)
    advisory_flag = 0 if robots_allowed else 1
    resp = session.get(target_url, timeout=30)
    
    # Extraction logic simplified for deep historical crawl
    endpoints = {target_url: "Root_Crawl"}
    for match in AGENDA_LINK_RE.findall(resp.text):
        full_url = urllib.parse.urljoin(target_url, match.strip("'\" "))
        endpoints[full_url] = "Discovered_Agenda"

    out_dir = f"artifacts/{prefix}_raw"
    os.makedirs(out_dir, exist_ok=True)
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    for url, title in endpoints.items():
        try:
            r = session.get(url, timeout=25)
            # Find all PDF endpoints within the agenda
            for pdf_match in re.findall(r'href=["\']([^"\']+(?:meta_id=|ViewAttachment|\.pdf)[^"\']*)["\']', r.text, re.I):
                pdf_url = urllib.parse.urljoin(url, pdf_match)
                pr = session.get(pdf_url, timeout=20)
                if pr.content[:4] == b"%PDF":
                    # Full SHA-512 hashing for silent edit detection
                    fhash = hashlib.sha512(pr.content).hexdigest()
                    
                    # Cross-reference existing records to detect tampering
                    cur.execute("SELECT item_id, attachment_sha256 FROM governance_items WHERE source_url = ?", (pdf_url,))
                    existing = cur.fetchone()
                    
                    fname = f"{out_dir}/{fhash[:12]}.pdf"
                    
                    if existing:
                        item_id, old_hash = existing
                        if old_hash != fhash:
                            print(f"[!] SILENT EDIT DETECTED: {pdf_url}")
                            cur.execute("INSERT INTO document_tamper_log (item_id, source_url, original_hash, new_hash) VALUES (?, ?, ?, ?)", (item_id, pdf_url, old_hash, fhash))
                            with open(f"{out_dir}/TAMPERED_{fhash[:12]}.pdf", "wb") as f: f.write(pr.content)
                    else:
                        with open(fname, "wb") as f: f.write(pr.content)
                        cur.execute(
                            "INSERT INTO governance_items (meeting_date, committee_or_body, title, attachment_sha256, local_pdf_path, source_url, robots_advisory_ignored) VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (today_str, "Cheyenne Archives", "Extracted PDF", fhash, fname, pdf_url, advisory_flag)
                        )
                    conn.commit()
        except Exception:
            continue
    conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--prefix", default="Cheyenne_Historical")
    parser.add_argument("--historical", action="store_true")
    args = parser.parse_args()
    harvest_and_ingest(args.url, args.prefix, args.historical)
