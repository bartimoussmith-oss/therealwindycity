# Record Atlas — initial repository integration

Run from the repository root with the existing Streamlit environment:

    streamlit run pages/25_Record_Atlas.py

Tests:

    python -m unittest tools.test_record_atlas

This first integration reads local public-archive text from pipeline/corpus, pipeline/corpus_clean, pipeline/corpus_yt, and ai-record-ocr. Only TXT, MD, VTT and SRT files up to 3 MB are eligible. Exact text duplicates are reported and excluded. Missing folders are harmless. No network requests, repository writes, database writes, or new dependencies are introduced by the indexer.

Search a record, select an extracted ordinance/resolution/parcel identifier, and explore matching historical records. The graph uses a selected shared identifier; it does not infer substantive legal or interpersonal relationships. Evidence snippets and text hashes remain attached to source documents. Source links use the checkout revision when Git is available; the main fallback is not immutable. Dates are filename-derived. The preview is capped, but source downloads are complete.

This is NOT yet comprehensive ingestion. PDFs, SQLite, JSON, compressed transcripts, private repositories, Git history, agenda-item segmentation, alias resolution, and semantic links need separate adapters and tests. PII-path exclusions are a precaution, not a general redaction system. Source folders must remain appropriate for public display. The graph has a display limit, while evidence downloads include all matches for the selected identifier.

The files are additive. Existing Streamlit entrypoints, requirements, workflows, engine and data files are unchanged. Automatic sidebar registration must be verified against the actual deployed navigation; this page can be run directly even if custom navigation omits it. No deployment or live browser verification has been performed.

Validation before commit approval: four indexer tests passed on synthetic temporary fixtures, page Python compilation passed, and rendered graph JavaScript passed Node syntax checking. Tests did not exercise the full repository corpus or Streamlit runtime.
