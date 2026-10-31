#!/usr/bin/env python3
import os, re, sqlite3, hashlib, argparse, urllib.parse, io
from datetime import datetime, timezone
import requests
from bs4 import BeautifulSoup
import pdfplumber
import pytesseract
from pdf2image import convert_from_bytes
from urllib.robotparser import RobotFileParser

DB_PATH = os.environ.get("PROMETHEAN_DB", "database/promethean_evidence.db")
HEADERS = {"User-Agent": "Promethean_CivicWatch_Auditor/4.3"}
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

def extract_true_text(pdf_bytes):
    text_content = ""
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            text_content = "\n".join([page.extract_text() or "" for page in pdf.pages])
        if len(text_content.strip()) < 50:
            print("[*] Scanned PDF detected. Engaging OCR...")
            images = convert_from_bytes(pdf_bytes)
            text_content = "\n".join([pytesseract.image_to_string(img) for img in images])
    except Exception as e:
        print(f"[!] Text extraction error: {e}")
    return text_content.strip()

def harvest_and_ingest(target_url, prefix, historical):
    session = requests.Session()
    session.headers.update(HEADERS)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    robots_allowed = audit_robots_txt(target_url)
    advisory_flag = 0 if robots_allowed else 1
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    try:
        resp = session.get(target_url, timeout=30)
    except Exception as e:
        print(f"[!] Target unreachable {target_url}: {e}")
        return

    endpoints = {target_url: "Root_Crawl"}
    for match in AGENDA_LINK_RE.findall(resp.text):
        full_url = urllib.parse.urljoin(target_url, match.strip("'\" "))
        endpoints[full_url] = "Discovered_Agenda"

    out_dir = f"artifacts/{prefix}_raw"
    os.makedirs(out_dir, exist_ok=True)

    for url, title in endpoints.items():
        try:
            r = session.get(url, timeout=25)
            for pdf_match in re.findall(r'href=["\']([^"\']+(?:meta_id=|ViewAttachment|\.pdf)[^"\']*)["\']', r.text, re.I):
                pdf_url = urllib.parse.urljoin(url, pdf_match)
                pr = session.get(pdf_url, timeout=20)
                
                if "text/html" in pr.headers.get("Content-Type", ""):
                    html_bypass = re.search(r'href=["\']([^"\']+\.pdf[^"\']*)["\']', pr.text, re.I)
                    if html_bypass:
                        pdf_url = urllib.parse.urljoin(pdf_url, html_bypass.group(1))
                        pr = session.get(pdf_url, timeout=20)

                if pr.content[:4] == b"%PDF":
                    file_bytes = pr.content
                    sha512_hash = hashlib.sha512(file_bytes).hexdigest()
                    
                    cur.execute("SELECT item_id, attachment_sha256 FROM governance_items WHERE source_url = ?", (pdf_url,))
                    existing = cur.fetchone()
                    fname = f"{out_dir}/{sha512_hash[:12]}.pdf"
                    
                    if existing:
                        item_id, old_hash = existing
                        compare_hash = sha512_hash if len(old_hash) != 64 else hashlib.sha256(file_bytes).hexdigest()
                        
                        if old_hash != compare_hash:
                            print(f"[!] TAMPER DETECTED: {pdf_url}")
                            cur.execute("INSERT INTO document_tamper_log (item_id, source_url, original_hash, new_hash) VALUES (?, ?, ?, ?)", (item_id, pdf_url, old_hash, sha512_hash))
                            with open(f"{out_dir}/TAMPERED_{sha512_hash[:12]}.pdf", "wb") as f: f.write(file_bytes)
                        elif len(old_hash) == 64:
                            cur.execute("UPDATE governance_items SET attachment_sha256 = ? WHERE item_id = ?", (sha512_hash, item_id))
                    else:
                        extracted_text = extract_true_text(file_bytes)
                        with open(fname, "wb") as f: f.write(file_bytes)
                        # Route body_text directly into the governance table. The schema trigger handles the FTS table.
                        cur.execute(
                            "INSERT INTO governance_items (meeting_date, committee_or_body, title, attachment_sha256, local_pdf_path, source_url, robots_advisory_ignored, body_text) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                            (today_str, "Cheyenne Records", "Extracted Document", sha512_hash, fname, pdf_url, advisory_flag, extracted_text)
                        )
                    conn.commit()
        except Exception as e:
            print(f"[!] Pipeline Exception at {url}: {str(e)}")
            continue
    conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--prefix", default="Cheyenne_Historical")
    parser.add_argument("--historical", action="store_true")
    args = parser.parse_args()
    harvest_and_ingest(args.url, args.prefix, args.historical)
