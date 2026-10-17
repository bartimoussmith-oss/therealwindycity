#!/usr/bin/env python3
"""ai_record_ocr.py - incremental OCR for image-only pages in the archive PDFs.

Reads extraction records (<sha>.json from ai_record_extract.py), finds pages
with no text layer, OCRs them with RapidOCR (pure pip, no system tesseract),
repairs run-together words with wordninja, and writes ai-record-ocr/<sha>.json
as {"<page_index>": "text", ...}. Work already in the cache is skipped, so each
run continues where the last one stopped.

Priority: short scanned documents first (ordinances, resolutions, maps,
letters), bulk financial listings (payables, vouchers, claims) last.

    python3 tools/ai_record_ocr.py --text /tmp/text --cache ai-record-ocr --minutes 50
"""
import argparse, json, os, re, subprocess, sys, time

BULK = re.compile(r"payable|voucher|claims|p-?card|warrant register|check register|ledger", re.I)


def alnum(t):
    return sum(c.isalnum() for c in t)


def fix_words(t):
    import wordninja
    def split(m):
        w = m.group(0)
        return " ".join(wordninja.split(w)) if len(w) >= 12 else w
    t = re.sub(r"[A-Za-z]{12,}", split, t)
    t = re.sub(r"([a-z])([A-Z][a-z])", r"\1 \2", t)
    t = re.sub(r"([,;:])(?=[A-Za-z])", r"\1 ", t)
    return t


def fetch(repo, sha):
    out = subprocess.run(["gh", "api", "-H", "Accept: application/vnd.github.raw",
                          f"repos/therealwindycity/{repo}/git/blobs/{sha}"], capture_output=True)
    return out.stdout if out.returncode == 0 else b""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", required=True)
    ap.add_argument("--cache", default="ai-record-ocr")
    ap.add_argument("--minutes", type=float, default=50)
    ap.add_argument("--max-pages-per-doc", type=int, default=30)
    ap.add_argument("--dpi", type=int, default=110)
    a = ap.parse_args()
    os.makedirs(a.cache, exist_ok=True)
    work = []
    for f in os.listdir(a.text):
        r = json.load(open(os.path.join(a.text, f)))
        if r.get("kind") != "pdf": continue
        img = [i for i, p in enumerate(r["pages"]) if alnum(p) < 25]
        if not img: continue
        sha = f[:-5]
        done = {}
        cp = os.path.join(a.cache, sha + ".json")
        if os.path.exists(cp):
            done = json.load(open(cp))
        todo = [i for i in img if str(i) not in done][: max(0, a.max_pages_per_doc - len(done))]
        if not todo: continue
        bulk = bool(BULK.search(r["path"]))
        work.append((bulk, len(img), r["path"], r["repo"], sha, todo))
    work.sort()
    total = sum(len(w[5]) for w in work)
    print(f"pending: {len(work)} documents, {total} pages", flush=True)
    if not work: return
    import pymupdf
    from rapidocr_onnxruntime import RapidOCR
    pymupdf.TOOLS.mupdf_display_errors(False)
    eng = RapidOCR()
    deadline = time.time() + a.minutes * 60
    pages_done = 0
    for bulk, nimg, path, repo, sha, todo in work:
        if time.time() > deadline: break
        data = fetch(repo, sha)
        if not data.startswith(b"%PDF"): continue
        try:
            doc = pymupdf.open(stream=data, filetype="pdf")
        except Exception:
            continue
        cp = os.path.join(a.cache, sha + ".json")
        done = json.load(open(cp)) if os.path.exists(cp) else {}
        for i in todo:
            if time.time() > deadline: break
            try:
                res, _ = eng(doc[i].get_pixmap(dpi=a.dpi).tobytes("png"))
                txt = "\n".join(x[1] for x in (res or []))
            except Exception:
                txt = ""
            done[str(i)] = fix_words(txt)
            pages_done += 1
        with open(cp, "w") as fh:
            json.dump(done, fh, ensure_ascii=False, sort_keys=True)
        print(f"  {pages_done}/{total} pages · {path[-70:]}", flush=True)
    print(f"OCR run finished: {pages_done} pages this run", flush=True)


if __name__ == "__main__":
    sys.exit(main())
