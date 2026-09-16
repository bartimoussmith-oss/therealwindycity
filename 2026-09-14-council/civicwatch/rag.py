#!/usr/bin/env python3
"""
Deterministic local vector RAG for the Cheyenne corpus.

- Embeddings: all-MiniLM-L6-v2 exported to ONNX, CPU, fixed threads → bit-exact reproducible vectors.
- Chunking: page-bounded, 900-char windows / 150 overlap, split on sentence boundaries. Chunk id = sha1(source|page|offset|text).
- Store: data/rag/vectors.f16.npy (N×384 float16) + data/rag/chunks.sqlite (id, source, page, start, text, sha1).
- Retrieval: exact cosine over numpy (no ANN → no randomness). Optional FTS5 hybrid (BM25 ∪ cosine, re-ranked by cosine).
- NO generation. Output is ranked verbatim chunks with provenance. Feed them to whatever you like, or nothing.

Sources ingested:
  1. civic.db pages (every Granicus attachment / minutes page, incl. OCR)
  2. any --repo path: *.md *.txt *.py *.json *.csv *.html(text) *.yaml recursively (skips node_modules, .git, data/rag, vectors)

Usage:
  python3 rag.py build [--repo ~/twc] [--rebuild]
  python3 rag.py query "why was Cox postponed in April" [-k 10] [--hybrid] [--source civic|repo]
  python3 rag.py verify                # re-embeds a sample and asserts bit-exact vs stored
  python3 rag.py stats
"""
import argparse, hashlib, json, os, re, sqlite3, sys, time
from pathlib import Path
import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

ROOT = Path(__file__).resolve().parent
RAG = ROOT / "data" / "rag"; RAG.mkdir(parents=True, exist_ok=True)
MODEL = ROOT / "models" / "minilm-l6-onnx"
VEC = RAG / "vectors.f16.npy"; RAW = RAG / "vectors.f16.raw"; META = RAG / "chunks.sqlite"; MANIFEST = RAG / "manifest.json"
CIVIC = Path(os.environ.get("CIVIC_DB", ROOT / "data" / "civic.db"))
CHUNK, OVERLAP, MAXTOK = 900, 150, 256
SKIP_DIRS = {".git", "node_modules", "__pycache__", "vectordb", "vectors", ".venv", "dist", "videos", "text_cache", "raw"}
REPO_EXT = {".md", ".txt", ".py", ".json", ".csv", ".yaml", ".yml", ".html", ".sql", ".sh"}

# ----------------------------------------------------------------------------- embedder
class Embedder:
    def __init__(self):
        self.tok = Tokenizer.from_file(str(MODEL / "tokenizer.json")); self.tok.enable_truncation(MAXTOK); self.tok.enable_padding(length=MAXTOK)  # fixed shape: one ORT arena block, no growth
        so = ort.SessionOptions(); so.intra_op_num_threads = 2; so.inter_op_num_threads = 1
        so.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL; so.enable_cpu_mem_arena = False; so.enable_mem_pattern = False; so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_BASIC
        self.s = ort.InferenceSession(str(MODEL / "model.onnx"), so, providers=["CPUExecutionProvider"])
        self.fingerprint = hashlib.sha1((MODEL / "model.onnx").read_bytes()).hexdigest()[:12]
    def __call__(self, texts, bs=32):
        out = []
        for i in range(0, len(texts), bs):
            e = self.tok.encode_batch(texts[i:i + bs])
            ids = np.array([x.ids for x in e], dtype=np.int64); am = np.array([x.attention_mask for x in e], dtype=np.int64)
            h = self.s.run(None, {"input_ids": ids, "attention_mask": am, "token_type_ids": np.zeros_like(ids)})[0]
            v = (h * am[..., None]).sum(1) / np.maximum(am.sum(1, keepdims=True), 1)
            out.append((v / np.linalg.norm(v, axis=1, keepdims=True)).astype(np.float32))
        return np.vstack(out) if out else np.zeros((0, 384), np.float32)

# ----------------------------------------------------------------------------- chunking
SENT = re.compile(r"(?<=[.!?;:])\s+|\n{2,}")
def chunk_text(text, size=CHUNK, overlap=OVERLAP):
    text = re.sub(r"[ \t]+", " ", text).strip()
    if not text: return []
    if len(text) <= size: return [(0, text)]
    sents = [s for s in SENT.split(text) if s and s.strip()]
    chunks, buf, start, pos = [], "", 0, 0
    for s in sents:
        if len(buf) + len(s) + 1 > size and buf:
            chunks.append((start, buf.strip()))
            tail = buf[-overlap:]; start = start + len(buf) - len(tail); buf = tail + " " + s
        else:
            if not buf: start = pos
            buf = (buf + " " + s) if buf else s
        pos += len(s) + 1
    if buf.strip(): chunks.append((start, buf.strip()))
    return chunks

def cid(source, page, start, text): return hashlib.sha1(f"{source}|{page}|{start}|{text}".encode()).hexdigest()

# ----------------------------------------------------------------------------- store
def meta_db():
    c = sqlite3.connect(META)
    c.executescript("""CREATE TABLE IF NOT EXISTS chunks(row INTEGER PRIMARY KEY, id TEXT UNIQUE, kind TEXT, source TEXT, label TEXT,
                         page INTEGER, start INTEGER, text TEXT);
                       CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(text, content='chunks', content_rowid='row', tokenize='unicode61');
                       CREATE TRIGGER IF NOT EXISTS c_ai AFTER INSERT ON chunks BEGIN INSERT INTO chunks_fts(rowid,text) VALUES(new.row,new.text); END;""")
    return c

def iter_civic():
    if not CIVIC.exists(): return
    c = sqlite3.connect(f"file:{CIVIC}?mode=ro", uri=True, timeout=120)
    q = """SELECT p.doc_id,p.page,p.text,m.date,m.kind,d.item_no,d.item_title,d.role,d.url FROM pages p JOIN docs d ON d.id=p.doc_id JOIN meetings m ON m.id=d.meeting_id
           WHERE length(p.text)>40 ORDER BY p.doc_id,p.page"""
    for did, page, text, date, kind, no, title, role, url in c.execute(q):
        label = f"{date} {kind} item {no or role} — {(title or '')[:90]}"
        yield ("civic", f"doc{did}", label, page, text, url)

def iter_repo(repo):
    repo = Path(repo).expanduser()
    for p in sorted(repo.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in REPO_EXT: continue
        if any(part in SKIP_DIRS for part in p.parts): continue
        ap = p.as_posix()
        if "/data/rag/" in ap or ap.endswith("vectors.f16.raw") or "/civicwatch/data/text/" in ap: continue  # our own outputs; text/ is already indexed page-by-page via civic.db
        if p.stat().st_size > 3_000_000 or p.stat().st_size == 0: continue
        try: text = p.read_text(errors="ignore")
        except Exception: continue
        if p.suffix.lower() == ".html": text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", text, flags=re.S); text = re.sub(r"<[^>]+>", " ", text)
        rel = str(p.relative_to(repo))
        # page = 1-based 4000-char block so provenance stays addressable
        for i in range(0, len(text), 4000):
            yield ("repo", rel, rel, i // 4000 + 1, text[i:i + 4000], rel)

def cmd_build(a):
    """Resumable: vectors are appended to RAW after every batch; meta rows committed alongside. On restart the two are
    reconciled to the shorter length, then only chunk ids not already present are embedded. --rebuild wipes both."""
    emb = Embedder(); c = meta_db()
    if a.rebuild:
        c.executescript("DELETE FROM chunks; INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild');"); c.commit()
        for f in (VEC, RAW):
            if f.exists(): f.unlink()
    if not RAW.exists() and VEC.exists(): RAW.write_bytes(np.load(VEC).astype(np.float16).tobytes())
    n_raw = RAW.stat().st_size // (384 * 2) if RAW.exists() else 0
    n_meta = c.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    n = min(n_raw, n_meta)
    if n_raw != n_meta:
        print(f"reconcile: raw {n_raw} meta {n_meta} -> {n}", flush=True)
        c.execute("DELETE FROM chunks WHERE row>=?", (n,)); c.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild')"); c.commit()
        if RAW.exists():
            with open(RAW, "r+b") as f: f.truncate(n * 384 * 2)
    have = {r[0] for r in c.execute("SELECT id FROM chunks")}
    import itertools
    srcs = itertools.chain(iter_civic(), iter_repo(a.repo) if a.repo else ())  # streamed: never hold the corpus in RAM
    print(f"existing chunks {len(have)}", flush=True)
    batch, meta, n_new, t0 = [], [], 0, time.time()
    def flush():
        nonlocal batch, meta, n_new
        if not batch: return
        v = emb(batch).astype(np.float16)
        base = c.execute("SELECT COALESCE(MAX(row),-1) FROM chunks").fetchone()[0] + 1
        with open(RAW, "ab") as f: f.write(v.tobytes())
        c.executemany("INSERT INTO chunks(row,id,kind,source,label,page,start,text) VALUES(?,?,?,?,?,?,?,?)",
                      [(base + i, *m) for i, m in enumerate(meta)]); c.commit()
        n_new += len(batch); batch, meta = [], []
        if n_new % 640 == 0: print(f"  embedded {n_new} new chunks  {n_new/(time.time()-t0):.1f}/s", flush=True)
    for kind, source, label, page, text, url in srcs:
        for start, ch in chunk_text(text):
            i = cid(source, page, start, ch)
            if i in have: continue
            have.add(i); batch.append(ch); meta.append((i, kind, source, label, page, start, ch))
            if len(batch) >= 32: flush()
    flush()
    allv = np.fromfile(RAW, dtype=np.float16).reshape(-1, 384) if RAW.exists() else np.zeros((0, 384), np.float16)
    n_rows = c.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    assert allv.shape[0] == n_rows, f"vector/meta mismatch {allv.shape[0]} vs {n_rows}"
    np.save(VEC, allv)
    MANIFEST.write_text(json.dumps(dict(model="sentence-transformers/all-MiniLM-L6-v2 (onnx)", model_sha1_12=emb.fingerprint, dim=384,
        chunk=CHUNK, overlap=OVERLAP, max_tokens=MAXTOK, dtype="float16", n_chunks=int(n_rows), built=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        vectors_sha1=hashlib.sha1(VEC.read_bytes()).hexdigest()), indent=2))
    print(f"done: {n_rows} chunks, vectors {VEC.stat().st_size/1e6:.1f} MB")

# ----------------------------------------------------------------------------- query
def cmd_query(a):
    emb = Embedder(); c = meta_db(); V = np.load(VEC).astype(np.float32)
    q = emb([a.query])[0]; sims = V @ q
    if a.source: 
        mask = np.array([r[0] == a.source for r in c.execute("SELECT kind FROM chunks ORDER BY row")]); sims = np.where(mask, sims, -1)
    cand = set(np.argsort(-sims)[: a.k * 3].tolist())
    if a.hybrid:
        try:
            for (r,) in c.execute("SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ? ORDER BY rank LIMIT ?", ('"' + a.query.replace('"', '') + '"', a.k * 3)): cand.add(r)
        except Exception: pass
    top = sorted(cand, key=lambda i: -sims[i])[: a.k]
    for rank, i in enumerate(top, 1):
        kind, source, label, page, start, text = c.execute("SELECT kind,source,label,page,start,text FROM chunks WHERE row=?", (int(i),)).fetchone()
        print(f"#{rank}  cos={sims[i]:.3f}  [{kind}] {source} p{page}@{start}\n    {label}\n    {text[:a.width].replace(chr(10),' ')}\n")

def cmd_verify(a):
    emb = Embedder(); c = meta_db(); V = np.load(VEC)
    rows = c.execute("SELECT row,text FROM chunks ORDER BY row LIMIT 200").fetchall()
    fresh = emb([t for _, t in rows]).astype(np.float16)
    ok = np.array_equal(fresh, V[[r for r, _ in rows]])
    print("bit-exact re-embedding of first 200 chunks:", ok); sys.exit(0 if ok else 1)

def cmd_stats(a):
    c = meta_db(); print(json.loads(MANIFEST.read_text()) if MANIFEST.exists() else "no manifest")
    for r in c.execute("SELECT kind,COUNT(*),COUNT(DISTINCT source) FROM chunks GROUP BY kind"): print(f"  {r[0]}: {r[1]} chunks from {r[2]} sources")

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("build"); p.add_argument("--repo"); p.add_argument("--rebuild", action="store_true")
    p = sp.add_parser("query"); p.add_argument("query"); p.add_argument("-k", type=int, default=10); p.add_argument("--hybrid", action="store_true")
    p.add_argument("--source", choices=["civic", "repo"]); p.add_argument("--width", type=int, default=400)
    sp.add_parser("verify"); sp.add_parser("stats")
    a = ap.parse_args(); globals()["cmd_" + a.cmd](a)
