#!/usr/bin/env python3
import os, re, sys, sqlite3, hashlib, argparse, urllib.parse
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader, PdfWriter

DB_PATH = os.environ.get("PROMETHEAN_DB", "database/promethean_evidence.db")
HEADERS = {"User-Agent": "Mozilla/5.0"}
GRANICUS_REGEXES = [
    re.compile(r'(https?://[^"\'\s<>]+(?:meta_id=|attachment_id=|ViewAttachment\.ashx|\.pdf)[^"\'\s<>]*)', re.I),
    re.compile(r'(["\']/(?:AgendaViewer|GeneratedAgendaViewer|ViewAttachment)[^"\'\s<>]+["\'])', re.I),
    re.compile(r'meta_id=(\d+)', re.I),
]

def init_db(db_path: str):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    schema_file = "database/schema_rhetorical_profiling.sql"
    if os.path.exists(schema_file):
        with open(schema_file, "r", encoding="utf-8") as f:
            conn.executescript(f.read())
    return conn

def discover_endpoints(base_url, html_text, session):
    soup = BeautifulSoup(html_text, "html.parser")
    found = {}
    for tag in soup.find_all(["a", "area", "embed", "iframe"]):
        candidates = [tag.get("href"), tag.get("src"), tag.get("onclick"), tag.get("data-url")]
        label = tag.get_text(" ", strip=True) or tag.get("title") or "Granicus_Record"
        for raw in filter(None, candidates):
            js_url = re.search(r"['\"](https?://[^'\"]+|/[^'\"]+)['\"]", raw)
            target = js_url.group(1) if js_url else raw
            if any(token in target.lower() for token in ["meta_id", "attachment", ".pdf", "ashx", "document", "agenda"]):
                abs_url = urllib.parse.urljoin(base_url, target.replace("&amp;", "&"))
                found[abs_url] = label[:120]
    return list(found.items())

def harvest_and_ingest(target_url, prefix, committee, meeting_date):
    session = requests.Session()
    session.headers.update(HEADERS)
    conn = init_db(DB_PATH)
    resp = session.get(target_url, timeout=25)
    endpoints = discover_endpoints(target_url, resp.text, session)
    print(f"[*] Identified {len(endpoints)} candidate attachment endpoints.")
