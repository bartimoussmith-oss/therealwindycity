#!/usr/bin/env python3
"""
THE REAL WINDY CITY — WAYBACK MACHINE CDX PULL
Recovers deleted agendas/minutes via Internet Archive CDX API.

For each host pattern (cheyennecity.org/*, cheyenne.granicus.com/*, library.municode.com/wy/cheyenne/*),
queries CDX, dedupes by digest, downloads raw content with id_ suffix.

Output: wayback/<host>/<timestamp>_<safe_url>.html + manifest.json

Run in Colab:
  exec(open('tools/wayback_pull.py').read())

Config at top.
"""
import os, re, json, time, hashlib, urllib.parse, urllib.request
from pathlib import Path

OUT_ROOT = "/content/drive/MyDrive/TheRealWindyCity/wayback"
if not os.path.isdir("/content/drive"):
    OUT_ROOT = str(Path(__file__).resolve().parent.parent / "wayback")

DELAY = 1.0
UA = "TheRealWindyCity/1.0 (+civic-archive; public records research)"
CDX_BASE = "https://web.archive.org/cdx/search/cdx"

PATTERNS = [
    "cheyennecity.org/*",
    "cheyenne.granicus.com/*",
    "library.municode.com/wy/cheyenne/*",
    "cheyennebopu.org/*",
    "laramiecountywy.gov/*",
]

FROM = "20080101"
TO = "20261231"

def http_get(url, raw=False):
    time.sleep(DELAY)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()

def cdx_query(pattern):
    params = {
        "url": pattern,
        "output": "json",
        "fl": "timestamp,original,mimetype,statuscode,digest",
        "filter": "statuscode:200",
        "collapse": "digest",
        "from": FROM,
        "to": TO,
    }
    qs = urllib.parse.urlencode(params)
    url = f"{CDX_BASE}?{qs}"
    print(f"CDX {pattern} -> {url[:120]}...")
    try:
        data = http_get(url)
        j = json.loads(data.decode("utf-8","replace"))
        # first row is header
        if j and j[0]==["timestamp","original","mimetype","statuscode","digest"]:
            rows = j[1:]
        else:
            rows = j
        print(f"  {len(rows)} captures")
        return rows
    except Exception as e:
        print(f"  !! CDX failed {e}")
        return []

def safe(s): return re.sub(r"[^A-Za-z0-9._-]+", "_", s)[:180].strip("_") or "doc"

def pull_captures(pattern, rows, out_root):
    host = pattern.split("/")[0].replace("*","").replace(":","_")
    folder = Path(out_root) / host
    folder.mkdir(parents=True, exist_ok=True)
    manifest_path = folder / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"pattern": pattern, "captures": []}
    seen_digests = {c.get("digest") for c in manifest["captures"] if c.get("digest")}
    for row in rows:
        if len(row)<5: continue
        ts, orig, mime, status, digest = row
        if digest in seen_digests:
            continue
        # raw URL with id_
        raw_url = f"https://web.archive.org/web/{ts}id_/{orig}"
        try:
            data = http_get(raw_url)
            if not data: continue
            fname = f"{ts}_{safe(orig)}"
            # add extension based on mime
            if "pdf" in mime and not fname.lower().endswith(".pdf"):
                fname += ".pdf"
            elif "html" in mime and not fname.lower().endswith((".html",".htm")):
                fname += ".html"
            (folder / fname).write_bytes(data)
            manifest["captures"].append({"timestamp": ts, "original": orig, "mimetype": mime, "digest": digest, "file": f"{host}/{fname}", "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)})
            seen_digests.add(digest)
            print(f"    {ts} {orig[:80]} {len(data)//1024}KB")
            manifest_path.write_text(json.dumps(manifest, indent=1))
        except Exception as e:
            print(f"    !! {orig} {e}")
            manifest["captures"].append({"timestamp": ts, "original": orig, "error": str(e), "digest": digest})
    manifest_path.write_text(json.dumps(manifest, indent=1))

def main():
    out_root = OUT_ROOT
    if out_root.startswith("/content/drive") and not os.path.isdir("/content/drive/MyDrive"):
        try:
            from google.colab import drive
            drive.mount("/content/drive")
        except Exception:
            out_root = str(Path(__file__).resolve().parent.parent / "wayback")
    print(f"OUT_ROOT={out_root}")
    for pat in PATTERNS:
        rows = cdx_query(pat)
        if rows:
            pull_captures(pat, rows, out_root)

if __name__ == "__main__":
    main()
