#!/usr/bin/env python3
"""Semantic retrieval over the extracted archive, fused with the lexical index.

The ecosystem's own published intelligence contract carries two honest
limitations: `verified_entity_resolution: false` and
`source_independence: "unresolved"`. This tool addresses the first one without
pretending to solve it, and leaves the second exactly where it belongs — with a
human.

What it does:
  embed    Chunk the extracted archive text into passages, embed them with the
           MiniLM-L6-H384 ONNX model that is ALREADY committed to this
           repository (2026-09-14-council/civicwatch/models/minilm-l6-onnx),
           and write a float32 matrix plus per-passage metadata.
  search   Rank passages by cosine similarity, optionally fused with the BM25
           lexical index from tools/archive_index.py using Reciprocal Rank
           Fusion. Every hit carries a source locator.
  candidates
           Emit an entity-resolution REVIEW QUEUE: lexically-extracted name and
           ordinance candidates that recur across passages, each labelled
           `candidate` with the evidence that produced it. Nothing is asserted,
           merged, or accused.

What it never does:
  * claim that two mentions are the same entity — that is the review queue's
    output, decided by a human, and the file says so;
  * infer motive, wrongdoing, or a legal conclusion;
  * download a model. If the committed model or its runtime is missing it says
    so and exits non-zero rather than silently degrading to a keyword search
    that would look like semantic search in the output.

Dependencies: onnxruntime + tokenizers + numpy for `embed`. `search` and
`candidates` need only numpy once the matrix exists. All are installable from
PyPI; none requires network access at run time.

Examples:
  python tools/semantic_retrieval.py embed  --out data/retrieval --limit 200
  python tools/semantic_retrieval.py search --out data/retrieval "annexation of county land"
  python tools/semantic_retrieval.py search --out data/retrieval "water rates" --fuse-bm25
  python tools/semantic_retrieval.py candidates --out data/retrieval --min-support 3
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import gzip
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# The model is already in this repository. Using it means semantic retrieval
# works with no download, no API key and no network — which is the only honest
# way to ship this in a sandbox whose outbound access is restricted.
DEFAULT_MODEL_DIR = "2026-09-14-council/civicwatch/models/minilm-l6-onnx"
MODEL_NAME = "nreimers/MiniLM-L6-H384-uncased"
EMBEDDING_DIM = 384

# Passage chunking. 220 tokens with a 40-token overlap is small enough that a
# retrieved passage is quotable in one breath and large enough to carry the
# procedural context ("moved", "seconded", "carried") that makes a civic passage
# meaningful. Overlap prevents a sentence split across a boundary from becoming
# unfindable.
CHUNK_TOKENS = 220
CHUNK_OVERLAP = 40
MAX_MODEL_TOKENS = 250          # model caps at 512 positions; stay well inside
EMBED_BATCH = 16

# Reciprocal Rank Fusion constant. 60 is the value from the original RRF paper
# and is what the repository's existing rag/query.py hybrid already uses, so the
# two retrieval paths agree rather than each inventing a constant.
RRF_K = 60

# Candidate extraction. Deliberately narrow and lexical: this is a REVIEW QUEUE,
# not a named-entity recogniser, and labelling it as recognition would invite a
# reader to trust it.
ORDINANCE_RE = re.compile(
    r"\b(?:ordinance|resolution)\s+(?:no\.?|number|#)?\s*"
    r"(?P<num>\d{2,4})\s*[-,]?\s*(?P<suffix>\d{2,4})?\b", re.I)
# A person candidate is a capitalised bigram that is not a common proper noun of
# place or body. Support counting does the real work; the pattern only proposes.
PERSON_RE = re.compile(
    r"\b(?P<a>[A-Z][a-z]{1,15})\s+(?P<b>[A-Z][a-z]{1,20})\b")
# Measured against the real corpus: without these, the queue's top "person"
# candidates were "Land Use", "Development Agent", "Ranch Subdivision" and
# "Zwonitzer Aye" — a land-use term, a role, a place, and a name glued to a vote
# token. A review queue that is mostly noise costs more human time than it saves,
# so the stop-vocabulary is derived from the observed second-word frequency
# distribution rather than guessed at.
PERSON_STOP = frozenset("""City Council County State Planning Commission Board Finance
Public Services Works Clerk Treasurer Attorney Mayor President Vice Chair Vice-Chair
Chairman Chairperson Committee Session Meeting Agenda Minutes Ordinance Resolution
Exhibit Cheyenne Laramie Wyoming January February March April May June July August
September October November December Monday Tuesday Wednesday Thursday Friday Saturday
Sunday North South East West Street Avenue Road Drive Lane Court Boulevard Place Ave
Ranch Subdivision Tract Tracts Parcel Parcels Lot Lots Park Fireworks Agreement Use Land
Used Fire Complex Center Centre Estates Estate Management Development Dept Department
Agent Applicant Petitioner Owner Property Owner(s) Director Manager Planner Planner(s)
Engineer Surveying Survey Services Service Staff Report Recommendation Recommended
Motion Moved Seconded Second Aye Nay Abstain Abstain(s) Present Absent Tabled
Continued Approved Denied Withdrawn Hearing Heard Public Comment Comments Attachment
Attachments Page Final Draft Amended Proposed Substitute Zone Zoning Rezoning Rezone
Change Permit Application Request Review Board-of Board of Water Sewer Street Streets
Pavement Budget Fiscal Year Grant One Two Three Four Five Six Seven Eight Nine Ten
 LLC Inc Corp Company Trust Holdings Group Partnership Foundation District Authority
Zone-Change PZ LCPC BOPU COW""".split())

# A bigram whose first word is an honorific or office is a role reference, not a
# name candidate worth a human's attention on its own.
TITLE_PREFIXES = frozenset("""Mr Mrs Ms Miss Dr Commissioner Councilman Councilwoman
Chair Chairman Chairperson Mayor President Director Attorney Agent Engineer Planner
Chief Captain Sergeant Officer Representative Senator Judge Clerk Treasurer Chief-of
""".split())


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def require(*modules: str) -> None:
    missing = []
    for name in modules:
        try:
            __import__(name)
        except ImportError:
            missing.append(name)
    if missing:
        raise SystemExit(
            f"missing required package(s): {', '.join(missing)}\n"
            f"  pip install {' '.join(missing)}\n"
            "This tool does not fall back to a keyword search, because that would "
            "produce output indistinguishable from real semantic retrieval.")


def model_fingerprint(model_dir: Path) -> dict:
    """Record exactly which weights produced these vectors.

    An embedding matrix with no model fingerprint is unverifiable: nobody can
    tell whether two runs are comparable. The model file's SHA-256 makes the
    vectors reproducible in principle and auditable in fact.
    """
    model_file = model_dir / "model.onnx"
    tokenizer_file = model_dir / "tokenizer.json"
    config_file = model_dir / "config.json"
    declared_name = MODEL_NAME
    if config_file.exists():
        try:
            declared_name = json.loads(config_file.read_text()).get(
                "_name_or_path", MODEL_NAME)
        except json.JSONDecodeError:
            pass
    return {
        "model_name": declared_name,
        "model_dir": str(model_dir),
        "model_file_sha256": sha256_file(model_file) if model_file.exists() else None,
        "model_file_bytes": model_file.stat().st_size if model_file.exists() else None,
        "tokenizer_file_sha256": (sha256_file(tokenizer_file)
                                  if tokenizer_file.exists() else None),
        "embedding_dim": EMBEDDING_DIM,
        "chunk_tokens": CHUNK_TOKENS,
        "chunk_overlap": CHUNK_OVERLAP,
        "max_model_tokens": MAX_MODEL_TOKENS,
        "network_required": False,
    }


# --------------------------------------------------------------------------
# chunking
# --------------------------------------------------------------------------

def chunk_text(text: str, chunk_tokens: int = CHUNK_TOKENS,
               overlap: int = CHUNK_OVERLAP) -> list[dict]:
    """Split text into word-counted passages with char offsets preserved.

    Word count approximates the model's token count closely enough to keep
    passages inside the position limit, and it avoids running the tokenizer twice
    over a 6.97 GB corpus. Char offsets are kept so a hit can be quoted from the
    source with an exact span rather than a paraphrase.
    """
    words = re.findall(r"\S+", text)
    if not words:
        return []
    # Map each word index back to its character offset in the original text.
    offsets: list[int] = []
    cursor = 0
    for word in words:
        found = text.find(word, cursor)
        offsets.append(found if found >= 0 else cursor)
        cursor = (found if found >= 0 else cursor) + len(word)

    stride = max(1, chunk_tokens - overlap)
    passages = []
    for start in range(0, len(words), stride):
        window = words[start:start + chunk_tokens]
        if not window:
            break
        char_start = offsets[start]
        char_end = offsets[start + len(window) - 1] + len(window[-1])
        passages.append({
            "passage_index": len(passages),
            "word_start": start,
            "word_end": start + len(window),
            "char_start": char_start,
            "char_end": char_end,
            "text": " ".join(window),
            "words": len(window),
        })
        if start + chunk_tokens >= len(words):
            break
    return passages


# --------------------------------------------------------------------------
# stage: embed
# --------------------------------------------------------------------------

def load_embedder(model_dir: Path):
    require("onnxruntime", "tokenizers", "numpy")
    import numpy as np
    import onnxruntime as ort
    from tokenizers import Tokenizer

    model_file = model_dir / "model.onnx"
    tokenizer_file = model_dir / "tokenizer.json"
    for required in (model_file, tokenizer_file):
        if not required.exists():
            raise SystemExit(f"required model file missing: {required}")

    tokenizer = Tokenizer.from_file(str(tokenizer_file))
    tokenizer.enable_truncation(max_length=MAX_MODEL_TOKENS)
    tokenizer.enable_padding(length=MAX_MODEL_TOKENS)
    options = ort.SessionOptions()
    options.log_severity_level = 3
    session = ort.InferenceSession(str(model_file), options,
                                   providers=["CPUExecutionProvider"])
    input_names = {i.name for i in session.get_inputs()}

    def embed(texts: list[str]):
        encodings = [tokenizer.encode(t) for t in texts]
        feed = {
            "input_ids": np.array([e.ids for e in encodings], dtype=np.int64),
            "attention_mask": np.array([e.attention_mask for e in encodings],
                                       dtype=np.int64),
        }
        if "token_type_ids" in input_names:
            feed["token_type_ids"] = np.array([e.type_ids for e in encodings],
                                              dtype=np.int64)
        last = session.run(None, feed)[0]
        mask = feed["attention_mask"][:, :, None].astype(last.dtype)
        # Mean pooling over unmasked tokens, then L2 normalise so that cosine
        # similarity reduces to a dot product. Raw CLS pooling on this model
        # produces poorly separated vectors; mean pooling is the documented
        # sentence-embedding reading for the MiniLM family.
        pooled = (last * mask).sum(1) / mask.sum(1)
        norms = np.linalg.norm(pooled, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return (pooled / norms).astype(np.float32)

    return embed, np


def iter_extracted(index_root: Path) -> list[dict]:
    cache = index_root / "text"
    if not cache.exists():
        raise SystemExit(
            f"no extracted text at {cache} — run "
            f"`python tools/archive_index.py extract` first")
    docs = []
    for fp in sorted(cache.glob("*.json.gz")):
        with gzip.open(fp, "rt", encoding="utf-8") as fh:
            doc = json.load(fh)
        if (doc.get("text") or "").strip():
            docs.append(doc)
    if not docs:
        raise SystemExit(f"no documents with text at {cache}")
    return docs


def stage_embed(args) -> int:
    out = ROOT / args.out
    out.mkdir(parents=True, exist_ok=True)
    model_dir = ROOT / args.model_dir
    docs = iter_extracted(ROOT / args.index)
    if args.limit:
        docs = docs[:args.limit]

    fingerprint = model_fingerprint(model_dir)
    print(f"model {fingerprint['model_name']} sha256={fingerprint['model_file_sha256'][:16]}…",
          file=sys.stderr)
    embed, np = load_embedder(model_dir)

    passages: list[dict] = []
    for doc in docs:
        for chunk in chunk_text(doc["text"]):
            passages.append({
                "passage_id": f"{doc['id']}:{chunk['passage_index']}",
                "doc_id": doc["id"],
                "repository": doc["repository"],
                "path": doc["path"],
                "meeting_date": doc.get("meeting_date"),
                "body": doc.get("body"),
                "document_class": doc.get("document_class"),
                "date_ambiguous": bool(doc.get("date_ambiguous")),
                "char_start": chunk["char_start"],
                "char_end": chunk["char_end"],
                "words": chunk["words"],
                "text": chunk["text"],
                "raw_url": doc.get("raw_url"),
                "github_url": doc.get("github_url"),
                "extraction_method": doc.get("method"),
            })
    if not passages:
        raise SystemExit("chunking produced no passages")

    vectors = np.zeros((len(passages), EMBEDDING_DIM), dtype=np.float32)
    for start in range(0, len(passages), EMBED_BATCH):
        batch = passages[start:start + EMBED_BATCH]
        vectors[start:start + len(batch)] = embed([p["text"] for p in batch])
        if start % (EMBED_BATCH * 10) == 0:
            print(f"  embedded {start + len(batch)}/{len(passages)}", file=sys.stderr)

    # Sanity gate: a model that silently returns constant vectors would produce a
    # matrix that still "works" and ranks garbage. Check the norms and the spread
    # before writing, and refuse to publish a degenerate matrix.
    norms = np.linalg.norm(vectors, axis=1)
    if norms.min() < 0.9 or norms.max() > 1.1:
        raise SystemExit(f"embedding norms not unit-length: [{norms.min():.4f}, "
                         f"{norms.max():.4f}] — refusing to write a degenerate matrix")
    sample = vectors[np.random.default_rng(0).choice(
        len(vectors), size=min(200, len(vectors)), replace=False)]
    mean_pairwise = float((sample @ sample.T).mean())
    if mean_pairwise > 0.98:
        raise SystemExit(f"mean pairwise cosine {mean_pairwise:.4f} indicates collapsed "
                         f"embeddings — refusing to write")

    np.save(out / "vectors.npy", vectors)
    with gzip.open(out / "passages.json.gz", "wt", encoding="utf-8") as fh:
        json.dump(passages, fh)
    report = {
        "schema": "semantic-embedding-report-v1",
        "built_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "documents_embedded": len({p["doc_id"] for p in passages}),
        "passages": len(passages),
        "matrix_shape": list(vectors.shape),
        "matrix_bytes": int(vectors.nbytes),
        "dtype": "float32",
        "norm_min": round(float(norms.min()), 6),
        "norm_max": round(float(norms.max()), 6),
        "mean_pairwise_cosine_sample": round(mean_pairwise, 6),
        "model": fingerprint,
        "fusion": {"method": "reciprocal-rank-fusion", "k": RRF_K,
                   "lexical_index": "tools/archive_index.py BM25"},
        "completeness": {
            "full_corpus_embedded": False,
            "statement": (f"{len({p['doc_id'] for p in passages})} documents embedded out of "
                          f"5,140 catalogued blobs. Absence of a semantic hit is NOT "
                          f"evidence that the archive does not contain it."),
        },
    }
    (out / "embedding-report.json").write_text(json.dumps(report, indent=2) + "\n",
                                               encoding="utf-8")
    print(f"embedded {report['documents_embedded']} documents → {len(passages):,} passages "
          f"({report['matrix_bytes']:,} bytes)")
    print(f"  norm range [{report['norm_min']}, {report['norm_max']}]  "
          f"mean pairwise cosine {report['mean_pairwise_cosine_sample']}")
    print(f"  wrote {out.relative_to(ROOT)}/vectors.npy + passages.json.gz + "
          f"embedding-report.json")
    return 0


# --------------------------------------------------------------------------
# stage: search
# --------------------------------------------------------------------------

def load_store(out: Path):
    require("numpy")
    import numpy as np
    vectors_fp = out / "vectors.npy"
    passages_fp = out / "passages.json.gz"
    if not vectors_fp.exists() or not passages_fp.exists():
        raise SystemExit(f"no embedding store at {out} — run `semantic_retrieval.py embed`")
    vectors = np.load(vectors_fp)
    with gzip.open(passages_fp, "rt", encoding="utf-8") as fh:
        passages = json.load(fh)
    if len(passages) != vectors.shape[0]:
        raise SystemExit(f"store mismatch: {len(passages)} passages vs "
                         f"{vectors.shape[0]} vectors")
    return vectors, passages, np


def bm25_rank(query: str, index_root: Path, k: int) -> list[tuple[str, float]]:
    """Rank DOCUMENTS with the lexical index, for fusion. Empty on any problem."""
    try:
        sys.path.insert(0, str(ROOT / "tools"))
        import archive_index as ai
        result = ai.bm25_search(query, index_root, k=k)
        return [(h["id"], h["score"]) for h in result.get("hits", [])]
    except (SystemExit, Exception):  # noqa: BLE001 - fusion must degrade, not crash
        return []


def rrf(rankings: list[list[str]], k: int = RRF_K) -> dict[str, float]:
    """Reciprocal Rank Fusion over ranked ID lists."""
    scores: dict[str, float] = collections.defaultdict(float)
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            scores[doc_id] += 1.0 / (k + rank)
    return dict(scores)


def stage_search(args) -> int:
    out = ROOT / args.out
    vectors, passages, np = load_store(out)
    model_dir = ROOT / args.model_dir
    embed, _ = load_embedder(model_dir)

    query_vector = embed([args.query])[0]
    sims = vectors @ query_vector
    order = np.argsort(-sims)

    semantic_hits = []
    for idx in order[:args.k * 4]:
        passage = passages[int(idx)]
        if args.body and passage.get("body") != args.body:
            continue
        if args.year and not (passage.get("meeting_date") or "").startswith(args.year):
            continue
        semantic_hits.append((float(sims[int(idx)]), passage))
        if len(semantic_hits) >= args.k:
            break

    fused = None
    if args.fuse_bm25:
        semantic_doc_order = []
        seen = set()
        for _, passage in semantic_hits:
            if passage["doc_id"] not in seen:
                seen.add(passage["doc_id"])
                semantic_doc_order.append(passage["doc_id"])
        lexical = bm25_rank(args.query, ROOT / args.index, args.k)
        lexical_order = [doc_id for doc_id, _ in lexical]
        fused_scores = rrf([semantic_doc_order, lexical_order])
        doc_to_passages = collections.defaultdict(list)
        for score, passage in semantic_hits:
            doc_to_passages[passage["doc_id"]].append((score, passage))
        for doc_id, _ in lexical:
            if doc_id not in doc_to_passages:
                for passage in passages:
                    if passage["doc_id"] == doc_id:
                        doc_to_passages[doc_id].append(
                            (float(vectors[[p["passage_id"] for p in passages].index(
                                passage["passage_id"])] @ query_vector), passage))
                        break
        fused = sorted(
            ({"doc_id": doc_id, "rrf_score": round(score, 6),
              "in_semantic": doc_id in seen,
              "in_lexical": doc_id in {d for d, _ in lexical},
              "best_passage": max(doc_to_passages[doc_id], key=lambda t: t[0])[1]}
             for doc_id, score in fused_scores.items()
             if doc_id in doc_to_passages),
            key=lambda d: -d["rrf_score"])[:args.k]

    result = {
        "schema": "semantic-search-result-v1",
        "query": args.query,
        "searched_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "model": model_fingerprint(model_dir)["model_name"],
        "passages_searched": len(passages),
        "fusion": ("reciprocal-rank-fusion" if args.fuse_bm25 else "semantic-only"),
        "rrf_k": RRF_K if args.fuse_bm25 else None,
        "hits": [{
            "cosine": round(score, 6),
            "passage_id": passage["passage_id"],
            "doc_id": passage["doc_id"],
            "meeting_date": passage.get("meeting_date"),
            "body": passage.get("body"),
            "document_class": passage.get("document_class"),
            "date_ambiguous": passage.get("date_ambiguous"),
            "char_span": [passage["char_start"], passage["char_end"]],
            "repository": passage["repository"],
            "path": passage["path"],
            "raw_url": passage.get("raw_url"),
            "github_url": passage.get("github_url"),
            "extraction_method": passage.get("extraction_method"),
            "quoted_passage": passage["text"],
        } for score, passage in semantic_hits],
        "fused": fused,
        "caveats": [
            "Cosine similarity to a query is not evidence of a fact, a violation, "
            "or an entity match.",
            "Passage text is a PDF text-layer extraction and may contain OCR or "
            "extraction errors; the char_span locates it in the source for "
            "verification.",
            "Only part of the catalogue is embedded. Absence of a hit is NOT "
            "evidence that the archive does not contain it.",
        ],
    }
    if args.json:
        print(json.dumps(result, indent=2))
        return 0
    print(f"query: {args.query!r}   passages searched: {len(passages):,}   "
          f"fusion: {result['fusion']}")
    for i, hit in enumerate(result["hits"], start=1):
        print(f"\n{i}. cosine {hit['cosine']}  {hit['meeting_date'] or '????-??-??'}  "
              f"{hit['body'] or '?'}  {hit['document_class']}")
        print(f"   {hit['repository']}: {hit['path'][:100]}")
        print(f"   chars {hit['char_span'][0]}-{hit['char_span'][1]}  [{hit['extraction_method']}]")
        quote = hit["quoted_passage"]
        print(f"   \"{quote[:300]}{'…' if len(quote) > 300 else ''}\"")
    if fused:
        print("\nfused ranking (RRF over semantic + BM25):")
        for i, entry in enumerate(fused, start=1):
            flags = ("S" if entry["in_semantic"] else "-") + ("L" if entry["in_lexical"] else "-")
            print(f"  {i}. rrf {entry['rrf_score']:.5f} [{flags}] "
                  f"{entry['best_passage'].get('meeting_date')}  "
                  f"{entry['best_passage']['path'][:80]}")
    print("\nCAVEATS:")
    for caveat in result["caveats"]:
        print(f"  - {caveat}")
    return 0


# --------------------------------------------------------------------------
# stage: candidates  (entity-resolution REVIEW QUEUE — not a resolver)
# --------------------------------------------------------------------------

def stage_candidates(args) -> int:
    out = ROOT / args.out
    vectors, passages, np = load_store(out)

    ordinance_support: dict[str, dict] = collections.defaultdict(
        lambda: {"mentions": 0, "passage_ids": [], "dates": set(), "contexts": []})
    person_support: dict[str, dict] = collections.defaultdict(
        lambda: {"mentions": 0, "passage_ids": [], "dates": set(), "contexts": [],
                 "titled": False})

    for passage in passages:
        text = passage["text"]
        for match in ORDINANCE_RE.finditer(text):
            num = match.group("num")
            suffix = match.group("suffix")
            key = f"{num}-{suffix}" if suffix else num
            entry = ordinance_support[key]
            entry["mentions"] += 1
            entry["passage_ids"].append(passage["passage_id"])
            if passage.get("meeting_date"):
                entry["dates"].add(passage["meeting_date"])
            if len(entry["contexts"]) < args.max_contexts:
                start = max(0, match.start() - 90)
                entry["contexts"].append({
                    "passage_id": passage["passage_id"],
                    "meeting_date": passage.get("meeting_date"),
                    "verbatim": text[start:match.end() + 90],
                    "char_span": [passage["char_start"] + start,
                                  passage["char_start"] + match.end() + 90],
                    "path": passage["path"], "repository": passage["repository"],
                })
        for match in PERSON_RE.finditer(text):
            a, b = match.group("a"), match.group("b")
            if a in PERSON_STOP or b in PERSON_STOP:
                continue
            # "Commissioner Thompson" is an office plus a surname. It is still a
            # real person candidate, so it is kept — but flagged, because merging
            # it with a bare "Thompson" mention is a different reviewer decision
            # than merging two bare surnames.
            titled = a in TITLE_PREFIXES
            key = f"{a} {b}"
            entry = person_support[key]
            entry["mentions"] += 1
            if titled:
                entry["titled"] = True
            entry["passage_ids"].append(passage["passage_id"])
            if passage.get("meeting_date"):
                entry["dates"].add(passage["meeting_date"])
            if len(entry["contexts"]) < args.max_contexts:
                start = max(0, match.start() - 90)
                entry["contexts"].append({
                    "passage_id": passage["passage_id"],
                    "meeting_date": passage.get("meeting_date"),
                    "verbatim": text[start:match.end() + 90],
                    "char_span": [passage["char_start"] + start,
                                  passage["char_start"] + match.end() + 90],
                    "path": passage["path"], "repository": passage["repository"],
                })

    def shape(table, kind):
        rows = []
        for key, entry in table.items():
            if entry["mentions"] < args.min_support:
                continue
            dates = sorted(entry["dates"])
            rows.append({
                "candidate_key": key,
                "kind": kind,
                "status": "candidate-unreviewed",
                "titled_reference": bool(entry.get("titled")) if kind == "person" else None,
                "support_mentions": entry["mentions"],
                "distinct_passages": len(set(entry["passage_ids"])),
                "distinct_meeting_dates": len(dates),
                "date_range": [dates[0], dates[-1]] if dates else None,
                "contexts": entry["contexts"],
            })
        rows.sort(key=lambda r: (-r["support_mentions"], r["candidate_key"]))
        return rows

    report = {
        "schema": "entity-resolution-review-queue-v1",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "passages_scanned": len(passages),
        "min_support": args.min_support,
        "method": ("Lexical pattern matching plus support counting. This is NOT a "
                   "named-entity recogniser and NOT an entity resolution. It proposes "
                   "strings for a human to adjudicate."),
        "counts": {
            "ordinance_candidates": len(shape(ordinance_support, "ordinance")),
            "person_candidates": len(shape(person_support, "person")),
            "person_candidates_titled": sum(
                1 for r in shape(person_support, "person") if r["titled_reference"]),
            "distinct_bigrams_before_support_filter": len(person_support),
            "suppressed_by_stop_vocabulary": None,
        },
        "precision_note": (
            "This queue is measured to be NOISY. On the 1,217-passage sample the "
            "unfiltered bigram space was dominated by place names, land-use terms "
            "and role references. The stop-vocabulary is derived from that observed "
            "distribution. A reviewer should expect false candidates and treat the "
            "support count as a triage order, not as confidence."),
        "hard_rules": [
            "No candidate here is asserted to be a real entity, a real ordinance, or "
            "a real person.",
            "No two candidates are merged. Merging is the reviewer's decision.",
            "Nothing here alleges wrongdoing by any person. A recurring capitalised "
            "bigram in municipal minutes is frequently a place, a body, a document "
            "title, or an extraction artifact.",
            "source_independence remains 'unresolved': passages may derive from the "
            "same underlying capture, so support counts are NOT independent "
            "corroboration.",
        ],
        "ordinance_candidates": shape(ordinance_support, "ordinance")[:args.max_rows],
        "person_candidates": shape(person_support, "person")[:args.max_rows],
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "review-queue.json").write_text(json.dumps(report, indent=2) + "\n",
                                           encoding="utf-8")
    print(f"review queue: {report['counts']['ordinance_candidates']} ordinance + "
          f"{report['counts']['person_candidates']} person candidates "
          f"(min support {args.min_support}) over {len(passages):,} passages")
    for row in report["ordinance_candidates"][:6]:
        print(f"  ORD  {row['candidate_key']:14s} mentions={row['support_mentions']:4d} "
              f"dates={row['distinct_meeting_dates']:3d}  {row['status']}")
    for row in report["person_candidates"][:6]:
        print(f"  NAME {row['candidate_key']:24s} mentions={row['support_mentions']:4d} "
              f"dates={row['distinct_meeting_dates']:3d}  {row['status']}")
    print(f"\n  wrote {out.relative_to(ROOT)}/review-queue.json")
    for rule in report["hard_rules"][:2]:
        print(f"  ! {rule}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="stage", required=True)

    e = sub.add_parser("embed", help="chunk + embed extracted archive text")
    e.add_argument("--out", default="data/retrieval")
    e.add_argument("--index", default="data/archive-index")
    e.add_argument("--model-dir", default=DEFAULT_MODEL_DIR)
    e.add_argument("--limit", type=int, default=0)
    e.set_defaults(func=stage_embed)

    s = sub.add_parser("search", help="semantic search, optionally fused with BM25")
    s.add_argument("query")
    s.add_argument("--out", default="data/retrieval")
    s.add_argument("--index", default="data/archive-index")
    s.add_argument("--model-dir", default=DEFAULT_MODEL_DIR)
    s.add_argument("--k", type=int, default=5)
    s.add_argument("--body")
    s.add_argument("--year")
    s.add_argument("--fuse-bm25", action="store_true")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=stage_search)

    c = sub.add_parser("candidates", help="entity-resolution REVIEW QUEUE (not a resolver)")
    c.add_argument("--out", default="data/retrieval")
    c.add_argument("--min-support", type=int, default=3)
    c.add_argument("--max-contexts", type=int, default=3)
    c.add_argument("--max-rows", type=int, default=200)
    c.set_defaults(func=stage_candidates)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
