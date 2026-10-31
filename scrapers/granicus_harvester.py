#!/usr/bin/env python3
import os, re, sqlite3, hashlib, argparse, urllib.parse, io
from datetime import datetime, timezone
import requests
from bs4 import BeautifulSoup
from urllib.robotparser import RobotFileParser
from pypdf import PdfReader

DB_PATH = os.environ.get("PROMETHEAN_DB", "database/promethean_evidence.db")
HEADERS = {"User-Agent": "Promethean_CivicWatch_Auditor/4.0"}
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

def extract_text_from_pdf(pdf_bytes):
    text_content = ""
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        for page in reader.pages:
            text = page.extract_text()
            if text: text_content += text + "\n"
    except Exception:
        pass
    return text_content.strip()

def harvest_and_ingest(target_url, prefix, historical):
    session = requests.Session()
    session.headers.update(HEADERS)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Ensure FTS5 Virtual Table exists
    cur.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS fts_forensic_archive 
        USING fts5(primary_actor, title_or_claim, fts_forensic_archive)
    """)
    conn.commit()

    robots_allowed = audit_robots_txt(target_url)
    advisory_flag = 0 if robots_allowed else 1
    resp = session.get(target_url, timeout=30)
    
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
            for pdf_match in re.findall(r'href=["\']([^"\']+(?:meta_id=|ViewAttachment|\.pdf)[^"\']*)["\']', r.text, re.I):
                pdf_url = urllib.parse.urljoin(url, pdf_match)
                pr = session.get(pdf_url, timeout=20)
                
                # HTML Interstitial Bypass: If Granicus wraps the PDF in an HTML viewer, recursively extract the true PDF link
                if "text/html" in pr.headers.get("Content-Type", ""):
                    html_bypass = re.search(r'href=["\']([^"\']+\.pdf[^"\']*)["\']', pr.text, re.I)
                    if html_bypass:
                        pdf_url = urllib.parse.urljoin(pdf_url, html_bypass.group(1))
                        pr = session.get(pdf_url, timeout=20)
                
                if pr.content[:4] == b"%PDF":
                    fhash = hashlib.sha512(pr.content).hexdigest()
                    extracted_text = extract_text_from_pdf(pr.content)
                    
                    cur.execute("SELECT item_id, attachment_sha256 FROM governance_items WHERE source_url = ?", (pdf_url,))
                    existing = cur.fetchone()
                    fname = f"{out_dir}/{fhash[:12]}.pdf"
                    
                    if existing:
                        item_id, old_hash = existing
                        if old_hash != fhash:
                            cur.execute("INSERT INTO document_tamper_log (item_id, source_url, original_hash, new_hash) VALUES (?, ?, ?, ?)", (item_id, pdf_url, old_hash, fhash))
                            with open(f"{out_dir}/TAMPERED_{fhash[:12]}.pdf", "wb") as f: f.write(pr.content)
                            # Update FTS5 index with the new altered text
                            cur.execute("UPDATE fts_forensic_archive SET fts_forensic_archive = ? WHERE rowid = ?", (extracted_text, item_id))
                    else:
                        with open(fname, "wb") as f: f.write(pr.content)
                        cur.execute(
                            "INSERT INTO governance_items (meeting_date, committee_or_body, title, attachment_sha256, local_pdf_path, source_url, robots_advisory_ignored) VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (today_str, "Cheyenne Archives", "Extracted Document", fhash, fname, pdf_url, advisory_flag)
                        )
                        new_id = cur.lastrowid
                        cur.execute(
                            "INSERT INTO fts_forensic_archive (rowid, primary_actor, title_or_claim, fts_forensic_archive) VALUES (?, ?, ?, ?)",
                            (new_id, "Cheyenne Archives", "Extracted Document", extracted_text)
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
