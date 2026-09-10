# Civic Transparency Engine — Cheyenne / Laramie County build

> **Agents / collaborators: read [`READ-FIRST.md`](READ-FIRST.md) before
> making any change.** It describes the current repo state and the claim
> protocol that keeps concurrent workers from stepping on each other.

> The console opens on **The Record Speaks** — a looping reel of the
> most contentious moments spoken at the meetings. Under the player,
> a context pane tracks the playing moment: the meeting (date, body,
> full tape), the ordinances being spoken about with their complete
> reading histories across every body, and clickable captions that
> jump the tape to the exact second. Then the adaptive **Start Here**
> wizard drills you into the parts of the record that touch you.

An automated public-records watchdog. It **politely** collects documents from public
government and news endpoints, fingerprints every file cryptographically, detects
silent edits, extracts searchable text, flags watchlist terms with verbatim quotes,
and drafts Wyoming Public Records Act requests and public-comment letters **for a
human to review and send**.

> Built 2026-09-05. Seeded for the Cheyenne data-center saga: annexations,
> Ordinance No. 4687, Chapter 1.28 warrants, moratorium votes, Project Jade,
> Project Latigo, BOPU water events, the referendum, and the Nov 3, 2026 election.

## Design decisions (and why they differ from the whiteboard version)

| "Whiteboard" component | Implemented as | Rationale |
|---|---|---|
| Kafka / RabbitMQ broker | SQLite `jobs` queue (`engine/db.py`) | A civic-scale deployment processes dozens-to-thousands of docs/day. A broker adds an ops burden without adding throughput at this scale. The `jobs` table has the same decoupling semantics; the swap path to a real broker is one function (see `ROADMAP`). |
| Vector database | SQLite **FTS5** full-text index, auto-degrades to `LIKE` | FTS5 gives instant plain-English search over transcripts with zero services. Upgrade path to pgvector is documented in `ROADMAP`. |
| LLM analysis | Provider-agnostic `Summarizer` with a fully-offline extractive fallback | Accountability tooling must work without an API key and must never invent facts. Every generated artifact stores its method tag and every alert carries a **verbatim quote + source URL + fetch timestamp**. Wire a real LLM via `analyze.Summarizer(llm_fn=...)` later. |
| "FOIA requests" | **Wyoming Public Records Act** requests (Wyo. Stat. §§ 16-4-201 through 16-4-205) | FOIA is federal. Wyoming local records use the PRA — citing the wrong statute is exactly the kind of error this engine exists to prevent. Requests are saved as **drafts**; a human sends them. |

## Quickstart

```bash
python3 run.py selftest        # prove the full pipeline offline, zero installs
python3 run.py init            # create ./data/engine.db and load config
python3 run.py crawl           # polite pull of every enabled source
python3 run.py work            # process queued extraction/scan jobs
python3 run.py digest          # write data/out/digest-<today>.md
python3 run.py request pra --help
streamlit run Transparency_Index_App.py   # the console (streamlit_app.py is an identical twin)
```

On Streamlit Community Cloud the console runs from this repo directly, and a
GitHub Action (`civic-cycle`) runs `engine/scheduler.py --once` every six hours
— plus hourly sweeps on Monday/Tuesday meeting nights — committing any ledger
changes back to `main`.

## Seeded sources (config/sources.json)

- **City of Cheyenne — City Council Minutes & Agendas** (CONFIRMED live 2026-09-05 — covers Council, Finance Committee, Public Services Committee, Committee of the Whole, Work Sessions)
- City of Cheyenne news articles page
- Cap City News (WordPress RSS — capcity.news)
- Wyoming Tribune Eagle (TownNews search-RSS pattern — verify on first run)
- Laramie County (disabled; CivicPlus agenda path differs per site — verify before enabling)
- Cheyenne BOPU (verify on first run)

Politeness contract (see LEGAL.md): honors `robots.txt` and `crawl-delay`, custom
identifying User-Agent, ≥3s between hits per host, ≤40 links per page, documents
only (no media), public pages only.

## First live run (2026-09-05) — what it already found

The engine passed its offline selftest (self-modifying fixture caught a
silent contract-dollar edit with a full diff), then did a bounded live crawl:

- **Governance-relevant discovery:** the city's agenda packets/minutes link out
  to `cheyenne.granicus.com`, whose robots.txt disallows automated collection.
  The engine refused every one of those URLs by design — proof the legality
  layer works before it matters. Path to those records: browser download, a
  bulk-access ask to the City Clerk, or a PRA request (the engine drafts one).
- **Current event flagged:** "Council to hold work session on Cox Ranch
  annexation" press release (Aug 25, 2026) — 3 watchlist hits, plus "Cox Ranch
  Annexation Updates" surfaced inside the city's own agendas page body.
- **True-quiet report:** Cap City News' current RSS top items are unrelated to
  data centers — the digest says so instead of manufacturing relevance.
- **Known gaps from the run:** TownNews RSS rate-limited (429) on first
  contact → run ≤1/day; one city-hosted PDF awaits `pip install pdfplumber`;
  language-picker nav links mint two junk rows (harmless, deduped thereafter).

## The integrity rule

Everything this engine emits is traceable: alerts carry verbatim quotes; digests
link source URLs with fetch timestamps; silent-edit reports include unified diffs.
If it isn't quotable, it isn't asserted. That rule is what separates a transparency
tool from a rumor machine.

## Layout

```
run.py               CLI entry point (init / crawl / work / digest / request / selftest)
config/              sources.json + watchlist.json (plain JSON, no deps)
engine/
  db.py              Module 4 — schema, FTS5 index, jobs queue (Module 2 semantics)
  ingest.py          Module 1 — robots-aware polite harvester (urllib stdlib)
  extract.py         text extraction (HTML now; PDF via pdfplumber; OCR hook via pytesseract)
  detect.py          Module 3 — SHA-256 version drift + unified diffs ("silent edit" reports)
  analyze.py         Module 3 — watchlist scanner + extractive summarizer (LLM-pluggable)
  records.py         Module 5 — Wyoming PRA request + public-comment draft generators
  digest.py          Module 5 — daily evidence digest writer
dashboard/app.py     Module 5 — Streamlit dashboard (optional)
```
