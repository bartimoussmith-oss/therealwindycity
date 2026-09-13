#!/usr/bin/env python3
"""
THE REAL WINDY CITY — WYOMING STATUTES PULL
Downloads all Wyoming Statutes PDFs from wyoleg.gov (43 files, public domain)
Converts to text, builds section index (e.g. 15-1-402, 16-4-201)

Source verified live 2026-09-12: https://www.wyoleg.gov/stateStatutes/StatutesDownload
Lists: title97 Constitution + title01..title42 + title99

Output: cities/cheyenne/law/wy_statutes/ {pdf/, txt/, statutes.json, sections/}

Run in Colab:
  !pip install -q pdfplumber
  exec(open('tools/wy_statutes_pull.py').read())
"""
import os, re, json, time, pathlib, urllib.request, hashlib
from pathlib import Path

OUT_ROOT = "/content/drive/MyDrive/TheRealWindyCity/cheyenne/law/wy_statutes"
if not os.path.isdir("/content/drive"):
    OUT_ROOT = str(Path(__file__).resolve().parent.parent / "cities/cheyenne/law/wy_statutes")

BASE = "https://wyoleg.gov/statutes/compress"
TITLES = ["title97"] + [f"title{i:02d}" for i in range(1,43)] + ["title99"] + ["title34.1"]
# title34.1 = UCC
DELAY = 0.8
UA = "TheRealWindyCity/1.0 (+civic-archive)"

SECTION_RE = re.compile(r"\b(\d{1,2}-\d{1,2}-\d{1,4}(?:\([a-z0-9]+\))?)\b")

def http_get_bytes(url):
    time.sleep(DELAY)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()

def pdf_to_text(data):
    try:
        import pdfplumber, io
        text = []
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for p in pdf.pages:
                text.append(p.extract_text() or "")
        return "\n".join(text)
    except Exception as e:
        print(f"  pdfplumber failed {e}, trying pypdf")
        try:
            import io
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(data))
            return "\n".join((page.extract_text() or "") for page in reader.pages)
        except Exception as e2:
            return f"[extract failed {e2}]"

def main():
    out_root = Path(OUT_ROOT)
    if str(out_root).startswith("/content/drive") and not os.path.isdir("/content/drive/MyDrive"):
        try:
            from google.colab import drive
            drive.mount("/content/drive")
        except Exception:
            out_root = Path(__file__).resolve().parent.parent / "cities/cheyenne/law/wy_statutes"
    (out_root / "pdf").mkdir(parents=True, exist_ok=True)
    (out_root / "txt").mkdir(parents=True, exist_ok=True)
    (out_root / "sections").mkdir(parents=True, exist_ok=True)

    index = {"source": "wyoleg.gov", "titles": {}, "sections": {}}
    print(f"OUT_ROOT={out_root}  {len(TITLES)} titles")

    for title in TITLES:
        url = f"{BASE}/{title}.pdf"
        pdf_path = out_root / "pdf" / f"{title}.pdf"
        txt_path = out_root / "txt" / f"{title}.txt"
        try:
            if not pdf_path.exists() or pdf_path.stat().st_size < 1024:
                print(f"Downloading {url} ...")
                data = http_get_bytes(url)
                pdf_path.write_bytes(data)
                print(f"  {len(data)//1024}KB -> {pdf_path}")
            else:
                data = pdf_path.read_bytes()
                print(f"Exists {pdf_path} {len(data)//1024}KB")
            # text
            if not txt_path.exists() or txt_path.stat().st_size < 100:
                text = pdf_to_text(data)
                txt_path.write_text(text, encoding="utf-8")
                print(f"  text {len(text)} chars")
            else:
                text = txt_path.read_text(encoding="utf-8", errors="replace")
            # sections
            secs = sorted(set(SECTION_RE.findall(text)))
            index["titles"][title] = {"file": f"pdf/{title}.pdf", "txt": f"txt/{title}.txt", "sections": secs[:2000], "count": len(secs)}
            # write per-section snippet (first occurrence)
            for sec in secs[:5000]:  # cap
                # find snippet
                m = re.search(re.escape(sec), text)
                if m:
                    start = max(0, m.start()-500)
                    end = min(len(text), m.end()+2000)
                    snippet = text[start:end]
                    # save
                    safe_sec = re.sub(r"[^A-Za-z0-9._-]+","_", sec)
                    (out_root / "sections" / f"{safe_sec}.txt").write_text(snippet, encoding="utf-8")
                    index["sections"][sec] = {"title": title, "snippet_file": f"sections/{safe_sec}.txt"}
        except Exception as e:
            print(f"!! {title} {e}")
            index["titles"][title] = {"error": str(e)}

    (out_root / "statutes.json").write_text(json.dumps(index, indent=1), encoding="utf-8")
    print(f"\nDone: {len(index['titles'])} titles, {len(index['sections'])} sections indexed -> {out_root/'statutes.json'}")

if __name__ == "__main__":
    main()
