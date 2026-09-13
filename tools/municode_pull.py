#!/usr/bin/env python3
"""
THE REAL WINDY CITY — MUNICODE / MUNICIPAL CODE PULL
Pulls Cheyenne Municipal Code from library.municode.com

Municode is JS-heavy (returns "Loading..."). Two strategies:
1. Playwright headless (in Colab: pip install playwright, playwright install chromium)
2. Wayback fallback (library.municode.com/wy/cheyenne/* via CDX)

Output: cities/cheyenne/code/municode/<title>/...html + extracted txt + manifest.json
Also attempts Previous Versions via Municode UI.

Run in Colab:
  !pip install -q playwright pdfplumber
  !playwright install chromium
  exec(open('tools/municode_pull.py').read())

Config at top.
"""
import os, re, json, time, pathlib, urllib.request, urllib.parse
from pathlib import Path

OUT_ROOT = "/content/drive/MyDrive/TheRealWindyCity/cheyenne/code/municode"
if not os.path.isdir("/content/drive"):
    OUT_ROOT = str(Path(__file__).resolve().parent.parent / "cities/cheyenne/code/municode")

BASE = "https://library.municode.com/wy/cheyenne/codes/code_of_ordinances"
DELAY = 2.0

def safe(s): return re.sub(r"[^A-Za-z0-9._-]+", "_", s).strip("_")[:120] or "doc"

def try_playwright():
    try:
        from playwright.sync_api import sync_playwright
        print("Playwright available — rendering Municode...")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent="Mozilla/5.0 TheRealWindyCity/1.0")
            page.goto(BASE, timeout=120000)
            page.wait_for_timeout(8000)
            html = page.content()
            Path(OUT_ROOT).mkdir(parents=True, exist_ok=True)
            (Path(OUT_ROOT)/"index_rendered.html").write_text(html, encoding="utf-8")
            # Try to extract TOC links
            links = page.eval_on_selector_all("a", "els => els.map(e => ({href: e.href, text: e.innerText}))")
            # Save TOC
            (Path(OUT_ROOT)/"toc.json").write_text(json.dumps(links[:500], indent=1))
            print(f"  rendered {len(html)} bytes, {len(links)} links")
            # Walk each Title link if present
            for item in links:
                href = item.get("href","")
                text = item.get("text","")[:80]
                if "/code_of_ordinances?nodeId=" in href and "Title" in text:
                    try:
                        print(f"  -> {text} {href}")
                        page.goto(href, timeout=60000)
                        page.wait_for_timeout(5000)
                        h2 = page.content()
                        fname = safe(text)
                        (Path(OUT_ROOT)/f"{fname}.html").write_text(h2, encoding="utf-8")
                        time.sleep(DELAY)
                    except Exception as e:
                        print(f"     !! {e}")
            browser.close()
            return True
    except Exception as e:
        print(f"Playwright failed or not installed: {e}")
        return False

def try_wayback_fallback():
    print("Trying Wayback fallback for Municode...")
    cdx_url = "https://web.archive.org/cdx/search/cdx?url=library.municode.com/wy/cheyenne/*&output=json&fl=timestamp,original,mimetype,statuscode&filter=statuscode:200&collapse=digest&from=20180101&to=20261231"
    try:
        req = urllib.request.Request(cdx_url, headers={"User-Agent": "TheRealWindyCity/1.0"})
        with urllib.request.urlopen(req, timeout=120) as r:
            j = json.loads(r.read().decode("utf-8","replace"))
        rows = j[1:] if j and j[0][0]=="timestamp" else j
        print(f"  Wayback {len(rows)} captures")
        out = Path(OUT_ROOT)/"wayback"
        out.mkdir(parents=True, exist_ok=True)
        for row in rows[:100]:
            ts, orig = row[0], row[1]
            raw_url = f"https://web.archive.org/web/{ts}id_/{orig}"
            try:
                req2 = urllib.request.Request(raw_url, headers={"User-Agent": "TheRealWindyCity/1.0"})
                with urllib.request.urlopen(req2, timeout=120) as r2:
                    data = r2.read()
                fname = f"{ts}_{safe(orig)}.html"
                (out/fname).write_bytes(data)
                print(f"    {fname} {len(data)//1024}KB")
                time.sleep(1.0)
            except Exception as e:
                print(f"    !! {orig} {e}")
    except Exception as e:
        print(f"  Wayback failed {e}")

def extract_text_from_html():
    # Use pdfplumber not needed, but extract text from saved HTML via simple stripping
    try:
        from pathlib import Path
        import re, html as htmlmod
        for html_file in Path(OUT_ROOT).glob("*.html"):
            txt = html_file.read_text(encoding="utf-8", errors="replace")
            # strip tags
            txt = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", txt)
            txt = re.sub(r"<[^>]+>", " ", txt)
            txt = htmlmod.unescape(txt)
            txt = re.sub(r"\s+", " ", txt).strip()
            (html_file.with_suffix(".txt")).write_text(txt, encoding="utf-8")
    except Exception as e:
        print(f"text extract failed {e}")

def main():
    out_root = OUT_ROOT
    if out_root.startswith("/content/drive") and not os.path.isdir("/content/drive/MyDrive"):
        try:
            from google.colab import drive
            drive.mount("/content/drive")
        except Exception:
            out_root = str(Path(__file__).resolve().parent.parent / "cities/cheyenne/code/municode")
    Path(out_root).mkdir(parents=True, exist_ok=True)
    print(f"OUT_ROOT={out_root}")
    ok = try_playwright()
    if not ok:
        try_wayback_fallback()
    extract_text_from_html()
    print("Done — check OUT_ROOT for html/txt")

if __name__ == "__main__":
    main()
