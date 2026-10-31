#!/usr/bin/env python3
import os, re, sys, sqlite3, hashlib, argparse, urllib.parse
import requests
from bs4 import BeautifulSoup

DB_PATH = os.environ.get("PROMETHEAN_DB", "database/promethean_evidence.db")
HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"}
GRANICUS_PATTERNS = [
    re.compile(r'(https?://[^"\'\s<>]+(?:meta_id=|attachment_id=|ViewAttachment\.ashx|\.pdf)[^"\'\s<>]*)', re.I),
    re.compile(r'(["\']/(?:AgendaViewer|GeneratedAgendaViewer|ViewAttachment)[^"\'\s<>]+["\'])', re.I)
]

def init_db(db_path: str):
    conn = sqlite3.connect(db_path)
    return conn

def discover_endpoints(base_url, html_text):
    soup = BeautifulSoup(html_text, "html.parser")
    found = {}
    for tag in soup.find_all(["a", "iframe", "embed"]):
        raw_link = tag.get("href") or tag.get("src") or tag.get("onclick") or ""
        label = tag.get_text(strip=True) or tag.get("title") or "Attachment"
        target = re.search(r"['\"](https?://[^'\"]+|/[^'\"]+)['\"]", raw_link)
        target = target.group(1) if target else raw_link
        if any(k in target.lower() for k in ["meta_id", "attachment", ".pdf", "ashx"]):
            found[urllib.parse.urljoin(base_url, target.replace("&amp;", "&"))] = label
    return list(found.items())

def harvest_and_ingest(target_url, prefix):
    session = requests.Session()
    session.headers.update(HEADERS)
    resp = session.get(target_url, timeout=25)
    endpoints = discover_endpoints(target_url, resp.text)
    print(f"[*] Identified {len(endpoints)} candidate endpoints.")
    
    os.makedirs(f"artifacts/{prefix}_raw", exist_ok=True)
    for idx, (url, title) in enumerate(endpoints, 1):
        try:
            r = session.get(url, timeout=20, allow_redirects=True)
            if "application/pdf" in r.headers.get("Content-Type", "").lower() or r.content[:4] == b"%PDF":
                fhash = hashlib.sha256(r.content).hexdigest()[:10]
                fname = f"artifacts/{prefix}_raw/{idx:02d}_{fhash}.pdf"
                with open(fname, "wb") as f:
                    f.write(r.content)
                print(f"[+] Downloaded: {fname} ({len(r.content)//1024} KB)")
        except Exception as e:
            print(f"[!] Skipped {url}: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--prefix", default="Cheyenne_Audit")
    args = parser.parse_args()
    harvest_and_ingest(args.url, args.prefix)
