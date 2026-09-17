#!/usr/bin/env python3
"""OCR pass for scanned attachments (docs with <20 extractable words).
RapidOCR (ONNX, CPU) over pypdfium2 renders. Writes pages back into civic.db so FTS/extract/rag see them.
Usage: python3 ocr.py [--min-words 20] [--dpi 150] [--limit N]
"""
import argparse, os, sqlite3, sys, time
from pathlib import Path
import numpy as np
import pypdfium2 as pdfium
from rapidocr_onnxruntime import RapidOCR
import civicwatch as cw, resource
# (no RLIMIT_AS: onnxruntime reserves large virtual space; render cap below bounds real RSS)

def ocr_pdf(path, engine, dpi=150, max_pages=60):
    pdf = pdfium.PdfDocument(str(path)); out = []
    for i in range(min(len(pdf), max_pages)):
        pg = pdf[i]; w, h = pg.get_size()
        sc = min(dpi / 72, (2500 * 72 / max(w, h)) / 72)  # cap longest side ~2500px: bounded RAM regardless of page size
        img = pg.render(scale=sc).to_pil().convert("RGB")
        res, _ = engine(np.array(img))
        lines = [r[1] for r in (res or [])]
        out.append((i + 1, "\n".join(lines)))
    return out

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--min-words", type=int, default=20); ap.add_argument("--dpi", type=int, default=150)
    ap.add_argument("--limit", type=int, default=0); a = ap.parse_args()
    c = cw.db()
    cuda = os.environ.get("OCR_CUDA") == "1"   # Colab/GPU: OCR_CUDA=1 (needs onnxruntime-gpu). Output text is the same either way.
    eng = RapidOCR(det_use_cuda=cuda, rec_use_cuda=cuda, cls_use_cuda=cuda) if cuda else RapidOCR()
    rows = c.execute("SELECT id,path FROM docs WHERE (words IS NULL OR words<?) AND COALESCE(ocr,0)=0 ORDER BY id", (a.min_words,)).fetchall()
    if a.limit: rows = rows[:a.limit]
    print(f"{len(rows)} scanned docs to OCR", flush=True)
    for n, (did, path) in enumerate(rows, 1):
        p = Path(path)
        if not p.exists():
            try: cw.save(c.execute("SELECT url FROM docs WHERE id=?", (did,)).fetchone()[0], p)
            except Exception as e: print(f"  doc{did}: fetch fail {e}"); continue
        t = time.time(); c.execute("UPDATE docs SET ocr=-1 WHERE id=?", (did,)); c.commit()  # -1 = attempted; survives a crash
        try: pages = ocr_pdf(p, eng, a.dpi)
        except Exception as e: print(f"  doc{did}: OCR fail {e}"); continue
        words = sum(len(x.split()) for _, x in pages)
        c.execute("DELETE FROM pages WHERE doc_id=?", (did,))
        for pg, txt in pages: c.execute("INSERT INTO pages(doc_id,page,text) VALUES(?,?,?)", (did, pg, txt))
        c.execute("UPDATE docs SET pages=?,words=?,ocr=1 WHERE id=?", (len(pages), words, did))
        (cw.TXT / f"{did}.txt").write_text("\n\f".join(x for _, x in pages)); c.commit()
        print(f"  [{n}/{len(rows)}] doc{did}: {len(pages)}p {words}w {time.time()-t:.0f}s", flush=True)
    c.execute("INSERT INTO pages_fts(pages_fts) VALUES('rebuild')"); c.commit(); print("done")

if __name__ == "__main__":
    c = cw.db()
    try: c.execute("ALTER TABLE docs ADD COLUMN ocr INTEGER DEFAULT 0"); c.commit()
    except Exception: pass
    main()
