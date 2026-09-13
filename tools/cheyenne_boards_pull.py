#!/usr/bin/env python3
"""
THE REAL WINDY CITY — CHEYENNE BOARDS/COMMISSIONS PULL
Pulls EVERY board/commission listed on cheyennecity.org/Your-Government/Boards-Commissions
26 boards + Finance/PSC/COW/Work Sessions + BOPU + Laramie County

Saves: agenda PDFs, minutes PDFs, supporting docs, raw href inventory
Output: cities/cheyenne/boards/<slug>/ {agendas/, minutes/, docs/, manifest.json}

Run in Colab (sandbox egress blocked):
  !git clone --depth 1 https://github.com/bartimoussmith-oss/therealwindycity.git
  %cd therealwindycity
  exec(open('tools/cheyenne_boards_pull.py').read())

Config at top.
"""
import os, re, json, time, hashlib, urllib.parse, urllib.request, html
from pathlib import Path

OUT_ROOT = "/content/drive/MyDrive/TheRealWindyCity/cheyenne/boards"
# fallback local
if not os.path.isdir("/content/drive"):
    OUT_ROOT = str(Path(__file__).resolve().parent.parent / "cities/cheyenne/boards")

BASE = "https://www.cheyennecity.org"
BOARDS_LIST_URL = f"{BASE}/Your-Government/Boards-Commissions"
DELAY = 1.5
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36 TheRealWindyCity/1.0 (+civic-archive)"
DOC_EXT = (".pdf",".doc",".docx",".xls",".xlsx",".rtf",".txt",".csv")

# 26 boards from live page 2026-09-12 + extras
BOARDS = [
    "Active Transportation Advisory Committee",
    "Affordable Housing Task Force",
    "Board of Adjustment",
    "Building Code Board of Appeals",
    "Cheyenne Housing Authority Board",
    "Cheyenne-Laramie Co. Economic Development JPB",
    "Cheyenne Passenger Rail Commission",
    "City/County Health Board",
    "Community Action of Laramie County",
    "Community Technology Advisory Council",
    "Contractor Licensing Board",
    "Downtown Development Authority",
    "Fire Civil Service Commission",
    "Friends of the Botanic Gardens",
    "Greenway Advisory Committee",
    "Historic Preservation Board",
    "Housing and Community Dev Advisory Council",
    "Innovation and Entrepreneur Advisory Council",
    "International Fire Code Board of Appeals",
    "Mayor's Council for People with Disabilities",
    "Mayor's Youth Council",
    "MPO Citizen's Advisory Committee",
    "Planning Commission",
    "Police Civil Service Commission",
    "Public Transit Advisory Board",
    "Tourism Promotion Joint Powers Board",
    "Urban Renewal Authority",
    # extras that have separate pages but not in list
    "Finance Committee",
    "Public Services Committee",
    "Committee of the Whole",
]

def http_get(url):
    time.sleep(DELAY)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/pdf,*/*;q=0.8"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.status, r.read(), r.geturl(), (r.headers.get("Content-Type") or "").lower()

def safe(s): return re.sub(r"[^A-Za-z0-9._-]+", "_", s).strip("_") or "doc"
def sha256(b): return hashlib.sha256(b).hexdigest()
def hrefs(html_text): return re.findall(r'''href\s*=\s*["']([^"']+)["']''', html_text, re.I)

def discover_board_links():
    try:
        st, body, fin, ct = http_get(BOARDS_LIST_URL)
        txt = body.decode("utf-8","replace")
        links = hrefs(txt)
        board_links = {}
        for h in links:
            if "/Boards-Commissions/" in h or "/Boards" in h:
                full = urllib.parse.urljoin(fin, h)
                # guess slug from link text? use URL
                slug = full.rstrip("/").split("/")[-1]
                if slug and len(slug)>2:
                    board_links[slug] = full
        return board_links
    except Exception as e:
        print(f"discover failed: {e}")
        return {}

def pull_board(name, url, out_root):
    slug = safe(name.lower())
    folder = Path(out_root) / slug
    folder.mkdir(parents=True, exist_ok=True)
    manifest_path = folder / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"board": name, "url": url, "docs": []}
    print(f"\n=== {name} == {url}")
    try:
        st, body, fin, ct = http_get(url)
        txt = body.decode("utf-8","replace")
        (folder / "page.html").write_bytes(body)
        all_hrefs = hrefs(txt)
        pdf_links = [urllib.parse.urljoin(fin, h) for h in all_hrefs if any(h.lower().endswith(ext) for ext in DOC_EXT)]
        print(f"  found {len(pdf_links)} doc links")
        for doc_url in sorted(set(pdf_links))[:200]:  # cap per board for first run
            try:
                st2, b2, f2, ct2 = http_get(doc_url)
                if not b2: continue
                fname = safe(urllib.parse.unquote(f2.split("/")[-1].split("?")[0]) or "doc.pdf")
                if not any(fname.lower().endswith(ext) for ext in DOC_EXT):
                    fname += ".pdf"
                # classify agenda vs minutes
                sub = "docs"
                low = fname.lower()
                if "agenda" in low: sub="agendas"
                elif "minute" in low: sub="minutes"
                out_dir = folder / sub
                out_dir.mkdir(exist_ok=True)
                (out_dir / fname).write_bytes(b2)
                manifest["docs"].append({"url": doc_url, "final_url": f2, "file": f"{slug}/{sub}/{fname}", "sha256": sha256(b2), "size": len(b2)})
                print(f"    saved {sub}/{fname} {len(b2)//1024}KB")
            except Exception as e:
                print(f"    !! {doc_url} {e}")
                manifest["docs"].append({"url": doc_url, "error": str(e)})
        manifest_path.write_text(json.dumps(manifest, indent=1))
    except Exception as e:
        print(f"  !! board {name} failed {e}")

def main():
    out_root = OUT_ROOT
    if out_root.startswith("/content/drive") and not os.path.isdir("/content/drive/MyDrive"):
        try:
            from google.colab import drive
            drive.mount("/content/drive")
        except Exception:
            out_root = str(Path(__file__).resolve().parent.parent / "cities/cheyenne/boards")
    print(f"OUT_ROOT={out_root}")
    discovered = discover_board_links()
    print(f"Discovered {len(discovered)} board links from {BOARDS_LIST_URL}")
    for name in BOARDS:
        # try discovered link if slug matches, else guess URL
        slug_guess = safe(name)
        url = discovered.get(slug_guess) or discovered.get(name.replace(" ","-")) or f"{BASE}/Your-Government/Boards-Commissions/{name.replace(' ','-').replace('/','-')}"
        # also try search via site search? For now use guess + discovered fallback
        # If we have discovered dict, try to find best match by substring
        if url not in discovered.values():
            for k,v in discovered.items():
                if slug_guess.lower()[:6] in k.lower() or name.split()[0].lower() in k.lower():
                    url = v
                    break
        pull_board(name, url, out_root)

if __name__ == "__main__":
    main()
