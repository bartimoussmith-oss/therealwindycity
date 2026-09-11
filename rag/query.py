#!/usr/bin/env python3
"""query.py — ask the vector DB, get answers with citations.

Hybrid retrieval: Chroma vector similarity + per-chunk keyword match, fused
with Reciprocal Rank Fusion (matches the repo's FTS-first philosophy while
adding semantic recall). Pure stdlib besides chromadb.

Usage (repo root):
  python rag/query.py "Which members were present March 9 2026?"
  python rag/query.py "annexation" --k 8 --persist rag/vectordb_sample
  python rag/query.py "liquor license" --where '{"clip_id": "1124"}'
  python rag/query.py "water rates" --type minutes --type transcript_clean
  python rag/query.py "postponement" --vector-only   # skip keyword side
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STOP = {"who", "what", "when", "where", "why", "how", "the", "and", "for",
        "was", "were", "with", "from", "that", "this", "are", "did", "does",
        "about", "which"}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", s)).strip()


def load_chunks(persist: Path) -> list[dict]:
    fp = persist / "chunks.jsonl"
    if not fp.exists():
        return []
    return [json.loads(line) for line in fp.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def match_where(meta: dict, where: dict | None) -> bool:
    if not where:
        return True
    for k, v in where.items():
        if k == "$and":
            if not all(match_where(meta, c) for c in v):
                return False
        elif isinstance(v, dict) and "$in" in v:
            if meta.get(k) not in v["$in"]:
                return False
        elif meta.get(k) != v:
            return False
    return True


def _stem(t):
    """Crude recall stem: voted/voting/votes -> vot, members -> member."""
    for suf in ("ing", "ed", "s"):
        if t.endswith(suf) and len(t) - len(suf) >= 3:
            return t[: -len(suf)]
    return t


def keyword_ranks(chunks: list[dict], query: str, where: dict | None
                ) -> tuple[dict[str, int], dict[str, int]]:
    """Return (ranks, matched_term_counts)."""
    terms = [t for t in norm(query).split() if len(t) >= 3 and t not in STOP]
    pats = {t: (re.compile(r"\b" + re.escape(t) + r"\b") if len(t) <= 4 else None)
            for t in terms}
    alts = {t: ([t] + ([_stem(t)] if _stem(t) != t else [])) for t in terms}
    scored = []
    for c in chunks:
        if not match_where(c["metadata"], where):
            continue
        text = norm(c["text"])
        matched = []
        for t in terms:
            hit = None
            if pats[t] is not None:
                m = pats[t].search(text)
                hit = m.start() if m else None
            else:
                for alt in alts[t]:  # original + stem; count the term once
                    k = text.find(alt)
                    if k != -1 and (hit is None or k < hit):
                        hit = k
            if hit is not None:
                matched.append((t, hit))
        if matched:
            scored.append((len(matched), -min(p for _, p in matched), c["id"]))
    scored.sort(key=lambda t: t[2])  # stable tiebreak: earlier chunk id first
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    ranks = {cid: rank + 1 for rank, (_, _, cid) in enumerate(scored)}
    counts = {cid: n for n, _, cid in scored}
    return ranks, counts


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("--persist", default="rag/vectordb_sample")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--where", default="", help='metadata filter JSON, e.g. {"clip_id":"1093"}')
    ap.add_argument("--type", dest="types", action="append", default=[],
                    help="filter source_type (repeatable)")
    ap.add_argument("--vector-only", action="store_true")
    ap.add_argument("--keyword-only", action="store_true")
    args = ap.parse_args()

    import chromadb

    persist = Path(args.persist)
    if not persist.is_absolute():
        persist = ROOT / persist
    client = chromadb.PersistentClient(path=str(persist))
    col = client.get_collection("cheyenne_meetings")

    where = json.loads(args.where) if args.where else None
    if args.types:
        tcond: dict = ({"source_type": {"$in": args.types}} if len(args.types) > 1
                       else {"source_type": args.types[0]})
        where = {"$and": [where, tcond]} if where else tcond

    n_fetch = max(args.k * 10, 50)
    vec_ranks: dict[str, int] = {}
    store: dict[str, tuple[str, dict, float]] = {}
    if not args.keyword_only:
        res = col.query(query_texts=[args.question], n_results=n_fetch, where=where)
        for rank, (cid, doc, meta, dist) in enumerate(zip(
                res.get("ids", [[]])[0], res.get("documents", [[]])[0],
                res.get("metadatas", [[]])[0], res.get("distances", [[]])[0]), 1):
            vec_ranks[cid] = rank
            store[cid] = (doc, meta or {}, dist)

    kw_ranks: dict[str, int] = {}
    kw_counts: dict[str, int] = {}
    if not args.vector_only:
        chunks = load_chunks(persist)
        kw_ranks, kw_counts = keyword_ranks(chunks, args.question, where)
        by_id = {c["id"]: c for c in chunks}
        for cid in kw_ranks:
            if cid not in store and cid in by_id:
                c = by_id[cid]
                store[cid] = (c["text"], c["metadata"], float("nan"))

    rrf: dict[str, float] = {}
    for cid in set(vec_ranks) | set(kw_ranks):
        score = 0.0
        if cid in vec_ranks:
            score += 1.0 / (60 + vec_ranks[cid])
        if cid in kw_ranks:
            score += 1.0 / (60 + kw_ranks[cid])
        rrf[cid] = score

    top = sorted(rrf, key=rrf.get, reverse=True)  # type: ignore[arg-type]
    # keyword-star promotion: a chunk matching 4+ query terms verbatim must
    # never be buried by fusion math — pin kw#1 at #1, kw#2 at #3.
    by_kw = sorted(kw_ranks, key=kw_ranks.get)
    stars = [cid for cid in by_kw[:2] if kw_counts.get(cid, 0) >= 4]
    for pos, cid in zip((0, 2), stars):
        if cid in top:
            top.remove(cid)
        top.insert(min(pos, len(top)), cid)
    top = top[:args.k]
    mode = ("vector-only" if args.vector_only else
            "keyword-only" if args.keyword_only else "hybrid RRF")
    print(f"collection: cheyenne_meetings @ {persist} ({col.count()} chunks, {mode})\n")
    for i, cid in enumerate(top, 1):
        doc, meta, dist = store[cid]
        tline = ""
        if meta.get("t_start") or meta.get("t_end"):
            tline = f" @{meta.get('t_start')}s-{meta.get('t_end')}s"
        dstr = f"{dist:.3f}" if dist == dist else "n/a"
        print(f"[{i}] clip={meta.get('clip_id')} date={meta.get('date')} "
              f"src={meta.get('source_type')}{tline} "
              f"(vec_rank={vec_ranks.get(cid, '-')} kw_rank={kw_ranks.get(cid, '-')} dist={dstr})")
        print(f"    file={meta.get('source_file')} item={meta.get('item_ref')} page={meta.get('page')}")
        if meta.get("source_url"):
            print(f"    url={meta.get('source_url')}")
        print(f"    {doc[:420].strip()}")
        print()


if __name__ == "__main__":
    main()
