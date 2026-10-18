# READ-FIRST.md — read this before touching anything

If you are an agent, assistant, bot, or human starting work in this repo, this
file is your mandatory entry point. It exists because multiple agents have
worked here simultaneously before, and the repo got flattened more than once.
Coordination is not optional here.

## The short version

1. **Read this whole file.** It tells you the repo state and who is doing what.
2. **Claim your work** — add an entry under *Active claims* before you start.
3. **Update your claim's `stage:` line at every major step** you make.
4. **Finish cleanly** — set your status to `done`, summarize the change, and
   move your entry to the *Work log*.
5. **Never modify files inside another active claim's scope.** If your task
   conflicts with one, you wait for it, or you coordinate via notes in their
   claim (see *Etiquette*).

## Hard rules (each of these exists because something broke)

- **Additive only.** Never delete or rewrite content you didn't create. Never
  force-push. Never reset or rewrite history.
- **The entry files are identical twins**: `streamlit_app.py` and
  `Transparency_Index_App.py` must always have identical content — change both
  or neither. Streamlit Cloud boots whichever one the settings point at.
- Never touch without an active claim naming them: the twins,
  `requirements.txt`, `data/`, `.github/`, `engine/`, `README.md`,
  `READ-FIRST.md` (protocol edits: propose in a claim first).
- No committed file over ~50 MB (GitHub's blob limit is 100 MB; the 22 MB
  tape master in `pipeline/renders/` is already the largest thing in here).
- **Credentials never go in files, commits, or this file.** Tokens live in
  Colab Secrets (`GH_PAT`) or GitHub repo secrets. A token pasted into a chat
  is a burned token.
- Pull-rebase before every push. One logical change per commit. Commit under
  the owner identity (`bartimoussmith-oss`); your worker name belongs in your
  claim below, not in git.
- Don't report success you didn't verify against the live repo or API. Two
  different bots have previously announced "deployed" for work that never
  landed. Verify, then say so.

## Etiquette for concurrent work

- A claim is **active** when its status is `proposed`, `active`, or `blocked`
  and its `updated:` stamp is less than **6 hours** old.
- If your scope overlaps an active claim: the earlier `started:` timestamp has
  right of way. You append a note to their claim ("waiting on you — I need X",
  or "I'll take the non-overlapping part"), adjust your scope, and let them
  finish. Politely. That's the whole system.
- A claim untouched for 6+ hours is assumed abandoned: append a dated note
  saying so, then you may proceed with its scope.
- Before every push, pull and re-read this file — someone may have claimed
  while you worked.

### Claim template (copy this into *Active claims*)

```markdown
### claim: short-slug — one-line description of the task
- worker: your-distinct-name
- status: proposed   # proposed | active | blocked | done | abandoned
- stage: what step you are on RIGHT NOW (update me at every major step)
- scope: paths this claim covers
- started: 2026-09-10T09:20Z
- updated: 2026-09-10T09:20Z
- notes: (coordination messages append here as "- 09:20Z name: ...")
```

## Active claims

### claim: miller-tapes — auto-playing theater for every Miller intervention
- worker: arena-agent
- status: done
- stage: PR #3 merged (e1bf0ac); branch deleted; theater live on front door
- scope: pages/2_Miller_Tapes.py (now thin wrapper), miller_theater.py (new shared module), pipeline/build_miller_index.py, pipeline/miller_interventions.json, twins (identical front-door chapter add); READ-FIRST.md (this claim + stage updates). Caption tracks (pipeline/miller_captions/, refetchable) stay OUT of git. Explicitly NOT touching: streamlit twins, engine/, data/, pipeline/* (existing), uploads/, requirements.txt, .github/, rag/, youtube-archive/
- started: 2026-09-11T20:45Z
- updated: 2026-09-11T20:45Z
- notes: 616/616 blocks cued (median match 0.97, gold-checked); AppTest + JS syntax verified; PR to main for owner merge, no direct main pushes beyond this claim

### claim: oci-deploy — Oracle Cloud (us-phoenix-1) deployment kit for the whole stack
- worker: arena-agent
- status: active
- stage: reconciled with main after PR #9 (work-log conflict resolved append-only); kit self-verifies 53/53; `tools/colab_import_linked_db.py` added and verified end-to-end (40.1 MB → 12.6 MB, byte-identical across runs); branches out of conflict, waiting on owner merge
- scope: NEW DIR `deploy/oracle/` (README runbook, bootstrap.sh, render_config.sh, update.sh, preflight.sh, selftest.sh, oci-launch.sh, cloud-init.yaml, systemd/*, nginx/*.template, env.example) + NEW `tools/colab_import_linked_db.py` and the `drive-import/README.md` section that documents it + additive README.md "Deploying to your own hardware" section + READ-FIRST.md (this claim + work log). Explicitly NOT touching: the twins (streamlit_app.py / Transparency_Index_App.py), requirements.txt, engine/, data/, .github/, pipeline/, uploads/, Entity_Database/, public/, rag/, youtube-archive/
- started: 2026-10-15T21:55Z
- updated: 2026-10-15T22:05Z
- notes: hosting only — no product logic, no data, no credential in any file. Services bind loopback; nginx is the only public door. The civic cycle on the VM is the GitHub Action's job minus the push (push block shipped commented-out, deploy key required to enable). Verified without a cloud account by rendering every artifact for both the domain and bare-IP configurations and checking them with systemd-analyze + structural assertions; `bash deploy/oracle/selftest.sh` reproduces it. Not verified (no OCI credentials in this sandbox, and none were requested): instance launch, certbot against real DNS, and nginx -t on the VM — `preflight.sh` is the gate for those on the box.

### claim: arrest-records — de-identified arrest-record tier (public records, names sealed)
- worker: arena-agent
- status: active
- stage: TWO tiers live. (1) 65-record tier from the captured weekly report. (2) Owner's MASTER_ARREST_DATABASE.pdf (261 pp) imported: 6,569 records -> 6,492 public, 97 weekly reports, 2021-01-09..2025-09-27, 4,539 unique names sealed. Ingest-time redaction gate added (engine/redact.py + hooks) so future captures never commit a name. Standalone explorer tools/arrest_explorer.py renders the public tier and is AppTest-verified: 6,492 events, 3 charts, 0 exceptions, 'Names published: 0'. Audit proven to FAIL CLOSED by injection tests (full name, surname alone, exact age all caught; prose 'grant' and JSON 'null' do not false-positive). Waiting on owner review; paid-access + password gate NOT built yet.
- scope: NEW `tools/build_arrest_records.py`, `tools/import_master_arrest_db.py`, `tools/arrest_explorer.py`, NEW `engine/redact.py`, NEW DIR `data/arrests/` (records.json/csv, master_records.json/csv, README.md; keyring.jsonl + name_key.json + access_ledger.json are gitignored and never committed), NEW `.github/ISSUE_TEMPLATE/arrest-name-request.md` (the name-release gate), `.gitignore` (seals the keyring/ledger + SQLite WAL sidecars), MINIMAL hooks in `engine/ingest.py::_ingest_one` and `engine/db.py::index_text` (call the redactor, fail closed), READ-FIRST.md (this claim + work log). Explicitly NOT touching: the twins, data/engine.db, data/snapshots/, requirements.txt, pipeline/, public/, .github/workflows/, deploy/oracle/. The engine/ hooks ARE a widening of the original scope, which excluded engine/ — recorded here rather than left implicit.
- started: 2026-10-17T23:40Z
- updated: 2026-10-17T23:55Z
- notes: owner directive — publish arrest records WITHOUT names; names released only on request, for public-safety and non-discriminatory research only. Charges are kept verbatim, never paraphrased; categories are charge groupings only and deliberately encode no protected characteristic or proxy for one (registry-compliance and immigration holds fold into the neutral warrant_court bucket rather than getting a targeting-able label). No demographic field is derived or inferred. Source caveats are carried verbatim into the output because the exclusions (juveniles, sexual-nature charges, anyone bonded out before release) are SYSTEMATIC, so the data must never be read as a complete picture. HONESTY, recorded in data/arrests/README.md §Honesty: the names are already public — capcity.news publishes them, and this repo already holds them TRACKED in data/snapshots/ (64/64) and in data/engine.db's FTS5 text_index (64/64, measured with --report-leaks). This tier governs what THIS PROJECT publishes and surfaces; it is an access-and-use gate, not secrecy. Redacting the source capture at ingest is a real fix but destroys provenance for the verify_vault.py bridge and cannot reach git history — left as an owner decision, deliberately not done here.

### claim: comic-universe — comic-book hero-universe re-theme of the website
- worker: arena-agent
- status: done
- stage: PR #2 merged to main 8fcfd1c (2026-09-11); branch deleted
- scope: streamlit_app.py + Transparency_Index_App.py (IDENTICAL twins — copy, never diverge), pages/1_Screening_Room.py, engine/publish.py (static-ledger theme only), public/index.html (regenerated output); READ-FIRST.md (this claim + stage updates). Copy/CSS/labels ONLY — zero logic, data, or behavior changes. Explicitly NOT touching: engine/ (except publish.py theme), data/, pipeline/, uploads/, Entity_Database/, requirements.txt, .github/, rag/, youtube-archive/, README.md
- started: 2026-09-11T18:35Z
- updated: 2026-09-11T18:45Z
- notes: owner-directed override of twin protection (re-theme authorized by repo owner 2026-09-11); twins stay byte-identical; original hero characters only (no Marvel/DC IP, no named-person villains); PR to main for owner merge, no direct main pushes beyond this claim

### claim: rag-vector-db — RAG vector DB + transcript cleanup + YouTube-archive wing
- worker: arena-agent
- status: done
- stage: PR #1 merged to main 56af0c6 (2026-09-11); branch deleted
- scope: NEW DIRS/FILES ONLY: rag/, youtube-archive/, pipeline/corpus_clean/ (sample outputs); READ-FIRST.md (this claim + stage updates). Explicitly NOT touching: streamlit twins, requirements.txt, data/, .github/, engine/, existing pipeline/*, uploads/, Entity_Database/, README.md
- started: 2026-09-10T11:20Z
- updated: 2026-09-11T18:45Z
- notes: additive-only; videos stay out of git per repo rule (YouTube + Releases); PR to main for owner merge, no direct main pushes beyond this claim

## Current repo state (updated 2026-09-10T11:05Z)

**What this is:** a civic-transparency console for Cheyenne / Laramie County —
an automated public-records watchdog plus a research archive. One Streamlit
app, two faces, sidebar-switched; deploys on push (Streamlit Community Cloud
auto-redeploys from `main`).

- **Site:** https://therealwindycity.streamlit.app — public. (curl sees a 303
  to `share.streamlit.io` first; that's the normal session handshake, not a
  login wall.)
- **App structure:** ledger face opens on the 🔥 contention reel (17-minute autoplay looping compilation of the nine most contentious spoken moments, chapter-sourced to the full meeting tapes, with a three-column context pane: meeting card, ordinance histories (engine/ordinance_index.py -> pipeline/ordinance_history.json, 153 ordinances / 309 mentions), and clickable timestamped captions; rebuild the reel via pipeline/build_reel.py); a 📼 Recordings & captions view driven by pipeline/media_manifest.json (media backfill cell at tools/colab_media_backfill.py: auto-captions to git, full-meeting audio to GitHub Releases), then the 🧭 Start Here wizard (six adaptive stages, per-topic follow-ups, weighted scoring with match bars, profile archetype, next-step chains, fired-rules audit panel), then six sidebar sections (Overview / Live
  operations / The record / Video vault / Intake / Legacy vault — the legacy
  vault rows stay behind leads-not-facts banners until auto-verified against
  the transcript corpus) + Transparency Index face (entity dossiers).
- **Multipage:** `pages/1_Screening_Room.py` — theater for the 8 produced
  montages (`pipeline/renders/`, captioned), separate from the Video Vault
  section in the app.
- **Engine:** `engine/` (pure stdlib), `run.py`, scheduler runs one
  crawl→extract→digest→publish cycle per Action run and commits ledger
  changes back to `main` as `civic-engine-bot`.
- **Actions (both green):** `civic-cycle` every 6 h at :17 UTC (first green
  run 2026-09-10T08:14Z); `meeting-watch` hourly :37 during Tue/Wed 00:00–
  05:59 UTC meeting windows. Manual "Run workflow" available on both.
- **Data:** `data/engine.db` (FTS5), recovered vault db (`cheyenne_watchdog.db`),
  `pipeline/corpus/` = 17 years of minutes + `extra/` transcripts of the three
  verified-tape meetings; `pipeline/cityvideos.json` = 260 indexed city
  YouTube meetings incl. verified-tape timestamps; `uploads/` ≈ 225 files
  (kept out of the app reader on purpose); RSS at `public/feed.xml`.
- **Invariants:** public documents only; robots.txt honored; legacy data is
  leads-not-facts until verified; PRAs are drafted for a human to send; no
  impersonation; verbatim quotes + source URL + fetch timestamp on alerts.
- **Known deferred:** live Granicus captions (no VTT served), check-register
  verification, Turnstile on the tips form, moving `uploads/` to release
  assets.
- **Owner todo:** rotate the GitHub PAT currently circulating in chats.

## Work log (append when you finish; newest last)
- 2026-09-12 21:40Z — arena-agent: **portable-agent runtime shipped** — new top-level `agent/`
  package (+ `AGENT.md`) giving the owner a local, device-portable, multi-agent runtime:
  plan→parallel workers→independent verifier→synthesis, 15 audited tools (shell/files/grep/
  polite web/git/`run.py`/sub-agents), three-tier command policy (deny/confirm/allow) with a
  workspace jail, dry-run and full audit trail, SQLite state in `~/.windycity-agent/` (never
  in the repo), installable PWA console for phone/Chromebook over the LAN, and installers for
  Termux/Windows/Linux/macOS/Chromebook. Providers: Anthropic, any OpenAI-compatible endpoint,
  Ollama, Claude CLI, and a paste-bridge so Arena.ai Agent Mode can drive the local machine
  with no key (Arena publishes no API — documented honestly in `AGENT.md` §1, adapter slot
  ready if one ever ships). Verified offline: 48/48 unit tests, `agent selftest` ALL PASS,
  real tool execution through single/plan/swarm + paste bridge + live SSE console, worktree
  isolation leaves the source tree untouched and creates no branches. Additive only — no
  existing file (twins, engine, data, pipeline, requirements, .github) was modified.

- 2026-09-10 05:04Z — windycity-deploy: v5 mega console + intel_index.json +
  prebuilt artifacts landed via the Colab cell (repo rebuilt after the Sept-7
  flattening).
- 2026-09-10 08:04Z — windycity-deploy: civic-cycle workflow YAML fixed
  (unterminated block scalar; GitHub had been silently rejecting the file).
- 2026-09-10 08:14Z — civic-engine-bot: first green data cycle; engine.db,
  vault verification, and feed.xml refreshed.
- 2026-09-10 08:18Z — windycity-deploy (Screening Room worker): multipage
  theater for the 8 montages + THE_CALLER_TAPE master + tape-meeting
  transcripts into `pipeline/corpus/extra/`.
- 2026-09-10 08:47Z — windycity-deploy (console worker): Video Vault section —
  captioned segments, evidence clips with verified-tape links, 260-meeting
  index.
- 2026-09-10 09:15Z — bartimoussmith-oss: 14-tab strip replaced with sidebar
  sections; README quickstart synced with the real tree.
- 2026-09-10 09:20Z — bartimoussmith-oss: READ-FIRST.md created (this file) +
  pointers added to README and both entry files.
- 2026-09-10 09:55Z — console-worker: Start Here guide shipped — question-driven routing (roles, topics, five booleans) into the existing sections, with because-of copy on every card and search prefills for the minutes archive and canon library.
- 2026-09-10 10:00Z — console-worker: guide v2 shipped — six-stage adaptive wizard with snapshot-backed answers (Streamlit prunes unrendered widget state; caught in harness, fixed with the Next-button snapshot pattern), weighted scoring, profiles, and the fired-rules audit panel.
- 2026-09-10 10:20Z — console-worker: contention reel shipped — CONTENTION_REEL.mp4 (17:25, 25 MB, nine clips, autoplay-mute-loop opener) with chapter links to the source meetings; pipeline/build_reel.py committed so the reel stays rebuildable.
- 2026-09-10 10:45Z — console-worker: context pane shipped under the reel — meeting cards (tape + transcript links), ordinance-history column with per-mention tape jumps, caption lines that link to the exact tape second, and a minute-jumping full-transcript viewer; ordinance index builder committed with its built JSON.
- 2026-09-10 11:05Z — console-worker: media backfill shipped — resumable Colab cell (captions → pipeline/captions/, audio → Releases, optional video) + Recordings & captions view in the Video vault; release-asset upload path live-verified. Video-in-git rejected: 260 meetings ≈ 130 GB vs the 100 MB blob cap.
- 2026-10-15 22:05Z — arena-agent (oci-deploy): Oracle Cloud deployment kit added under `deploy/oracle/` — one-shot bootstrap (Ubuntu 24.04 / Oracle Linux 9, x86 or Ampere ARM): service user + checkout to /opt/windycity, venv, engine init, three systemd units (console 8501, studio 8717, cycle timer :17/6h) and an nginx front door (console at /, static ledger at /ledger/, RSS at /feed.xml, studio on its own port or subdomain) with Let's Encrypt and OCI-specific host-firewall handling; plus preflight verification, fast update, OCI CLI launcher and cloud-init user-data. Selftest: 53 passed · 0 failed.
- 2026-10-16 — access-audit worker: ACCESS-TEST-2026-10-16.md (measured what can actually be read in all 9 repos: 5,122 archive docs / 81% text-extractable, 13% scanned, ~2% dead stubs; site "Ask the record" index covers ~5% of transcript text; claim-by-claim fact-check of prior AI answers; Miller objections table with timestamps + outcomes; fork/copy check) + tools/access_audit.py to reproduce. New files only; no claimed scope touched.
- 2026-10-16 — ai-record-worker: AI-readable mirror shipped (claim ai-record, done). tools/{ai_record_extract,ai_record_ocr,build_ai_record,render_ai_record}.py + tools/ai_record_static/ build a JavaScript-free site of all 1,011 meetings (every archived document as page-marked plain text with quality labels, 2026 transcripts with video-linked timestamps, inlined minutes, year/body/keyword/statute/ordinance indexes, verified topic pages, llms.txt, sitemap, AI-crawler-friendly robots.txt). New workflow .github/workflows/ai-record-pages.yml rebuilds daily and deploys to https://bartimoussmith-oss.github.io/therealwindycity/ from main only; it also OCRs scanned pages incrementally and commits the cache to ai-record-ocr/. Generated output is gitignored (/ai-record/, /_site/). README got one pointer section. Docs: tools/README-ai-record.md.
- 2026-10-17 — ai-record-worker: imported the WindyCityMeetings caption-transcript database from Google Drive (drive-import/master_meetings_database.json.gz, 720 records, sha256 in drive-import/README.md). New tools/ai_record_drive.py normalizes dates, bodies, and duplicates. build_ai_record.py --drive-db attaches 649 unique caption transcripts (6.7M words) to 434 meeting pages, adds 30 video-only meetings, and writes indexes/caption-transcripts. The workflow passes --drive-db. Not imported: the 143 MB _linked variant, which is over the connector's 100 MB cap (see drive-import/README.md).
- 2026-10-17 — arena-agent (arrest-records): de-identified arrest-record tier (claim arrest-records, built + self-audited). tools/build_arrest_records.py parses the captured Laramie County weekly arrest report (8/28/26–9/4/26, capcity.news, published 2026-09-05) into data/arrests/records.{json,csv} — 65 records across 5 date windows, verbatim charges, coarse research categories, opaque sequential record IDs, provenance + sha256, name=null. Names go to data/arrests/name_key.json: gitignored, mode 600, never committed; .github/ISSUE_TEMPLATE/arrest-name-request.md is the owner-reviewed gate (public-safety and non-discriminatory research only). Build fails closed on any name leak (exit 3). Verified by an independent re-parse of the raw HTML — 65 entries / 64 unique names, exact match — plus a sweep of all 5 public artefacts: 0 full names, 0 name tokens; byte-identical across rebuilds. Measured, not assumed: --report-leaks shows the names are ALREADY public in this repo, tracked in data/snapshots/ (64/64) and data/engine.db FTS5 (64/64), so this is an access gate on what the project publishes, not secrecy — documented in data/arrests/README.md §Honesty. Not touched: the twins, engine/, data/engine.db, data/snapshots/, workflows, deploy/oracle/.
- 2026-10-18 — arena-agent (arrest-records): master database imported + ingest-time name gate. Owner supplied MASTER_ARREST_DATABASE.pdf (261 pp, 782 KB, Chromium print-to-PDF of printed JSON): 6,569 {name,charges,source} rows from 97 weekly Cap City News reports, 2021-01-09..2025-09-27. tools/import_master_arrest_db.py cleans and splits it into two tiers — PUBLIC data/arrests/master_records.{json,csv} (6,492 records, names and exact ages withheld, opaque sequential AR-###### ids) and SEALED keyring.jsonl (4,539 names, gitignored, mode 600). The PDF is never copied into the repo. Cleaning measured, not assumed: 76 duplicates dropped, 1 incomplete, 1,421 \uXXXX escapes decoded, 2,454 source URLs repaired (PDF line-wrap spaces), 2,232 ages sealed (34% of rows carried an age — a quasi-identifier), 16 rows repaired where charges bled into the name field, 10 flagged name/charge-uncertain rather than guessed at. NEW engine/redact.py + minimal fail-closed hooks in engine/ingest.py::_ingest_one and engine/db.py::index_text withhold names BEFORE a capture is written or indexed; tested against a scratch DB — 64 live names -> 0 in the committed snapshot, 65 [WITHHELD] placeholders, charges and markup intact, both layers catch raw un-redacted input, non-arrest documents pass through untouched (no over-redaction); all 15 engine modules still import. tools/arrest_explorer.py is a standalone read-only Streamlit explorer of the public tier, AppTest-verified (6,492 events / 97 reports / 11,785 charge entries / 3 charts / 0 exceptions / 'Names published: 0'). The de-identification audit was rewritten twice after it produced false positives on real surnames that are also English words (Duty, Bond, Guardian-Rocka), on authored prose ('access grant'), and on the JSON literal null (Null is a surname here); allowed vocabulary now derives from the RAW source rows plus a zero-record scaffold render, never from the artefact under test (which was self-defeating — an injected name became its own justification). Injection tests then proved it fails closed. Measured with --report-leaks: the names remain public in 3 TRACKED files (data/snapshots/, data/text/9.txt, data/engine.db FTS5, 64/64 each), so this is an access gate on what the project publishes, not secrecy. NOT built: paid access codes, the password-gated full version, and the V-MAX deployment route.
