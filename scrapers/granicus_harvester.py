#!/usr/bin/env python3
import os, re, sqlite3, hashlib, argparse, urllib.parse, io
from datetime import datetime, timezone
import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader
import pdfplumber # Upgraded text extraction
import pytesseract # True OCR for scanned PDFs
from pdf2image import convert_from_bytes

DB_PATH = os.environ.get("PROMETHEAN_DB", "database/promethean_evidence.db")
HEADERS = {"User-Agent": "Promethean_CivicWatch_Auditor/4.1"}

def extract_true_text(pdf_bytes):
    text_content = ""
    try:
        # Try standard extraction first
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            text_content = "\n".join([page.extract_text() or "" for page in pdf.pages])
        
        # If document is a scanned image (no text found), trigger Tesseract OCR
        if len(text_content.strip()) < 50:
            print("[*] Scanned PDF detected. Engaging Optical Character Recognition (OCR)...")
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

    resp = session.get(target_url, timeout=30)
    endpoints = {target_url: "Discovered_Agenda"} # Simplified for brevity

    for url, title in endpoints.items():
        try:
            r = session.get(url, timeout=25)
            for pdf_match in re.findall(r'href=["\']([^"\']+(?:meta_id=|ViewAttachment|\.pdf)[^"\']*)["\']', r.text, re.I):
                pdf_url = urllib.parse.urljoin(url, pdf_match)
                pr = session.get(pdf_url, timeout=20)
                
                if pr.content[:4] == b"%PDF":
                    file_bytes = pr.content
                    sha512_hash = hashlib.sha512(file_bytes).hexdigest()
                    
                    cur.execute("SELECT item_id, attachment_sha256 FROM governance_items WHERE source_url = ?", (pdf_url,))
                    existing = cur.fetchone()
                    
                    if existing:
                        item_id, old_hash = existing
                        # Backwards compatibility: If legacy hash is SHA-256 (64 chars), compare using SHA-256
                        compare_hash = sha512_hash
                        if len(old_hash) == 64:
                            compare_hash = hashlib.sha256(file_bytes).hexdigest()
                        
                        if old_hash != compare_hash:
                            print(f"[!] TAMPER DETECTED: {pdf_url}")
                            cur.execute("INSERT INTO document_tamper_log (item_id, source_url, original_hash, new_hash) VALUES (?, ?, ?, ?)", (item_id, pdf_url, old_hash, sha512_hash))
                        elif len(old_hash) == 64:
                            # Upgrade legacy SHA-256 hash to SHA-512 silently
                            cur.execute("UPDATE governance_items SET attachment_sha256 = ? WHERE item_id = ?", (sha512_hash, item_id))
                    else:
                        extracted_text = extract_true_text(file_bytes)
                        cur.execute("INSERT INTO governance_items (attachment_sha256, source_url) VALUES (?, ?)", (sha512_hash, pdf_url))
                        new_id = cur.lastrowid
                        # Corrected Schema target: body_text
                        cur.execute("INSERT INTO fts_forensic_archive (rowid, body_text) VALUES (?, ?)", (new_id, extracted_text))
                    conn.commit()
        except Exception as e:
            # Replaced silent failure with explicit error logging
            print(f"[!] Pipeline Exception at {url}: {str(e)}")
            continue
    conn.close()

if __name__ == "__main__":
    harvest_and_ingest("https://cheyenne.granicus.com/ViewPublisher.php?view_id=5", "Cheyenne", True)
