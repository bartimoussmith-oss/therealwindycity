"""rag/ — RAG vector database + transcript cleanup for the Cheyenne corpus.

Reads (never modifies): pipeline/corpus/**, pipeline/docs/**, youtube-archive/catalogs.
Writes: pipeline/corpus_clean/**, rag/vectordb*/**, rag/*.json, rag/*.md.

Entry points (run from repo root):
  python rag/build_glossary.py --sample ...   # canonical entities from minutes/docs
  python rag/clean_transcripts.py             # dedup + entity-correct transcripts
  python rag/build_vector_db.py               # chunk + embed into Chroma
  python rag/query.py "question"              # search the vector DB
"""
