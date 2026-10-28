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

### claim: miller-estoppel-white-paper-expansion — source expansion and Wyoming-law analysis for the Miller estoppel-effect white paper
- worker: arena-agent
- status: done
- stage: expanded to about 12,400 words; reconciled all P1–P12 and L1–L6 references; official-record and Wyoming-law analysis added; corpus counts reproduced; `git diff --check` clean
- scope: `MILLER-ESTOPPEL-EFFECT-WHITE-PAPER-2026-10-18.md` + READ-FIRST.md (this claim + work-log entry only). Add/clarify sources and analysis; do not edit meeting transcripts, caption files, data, or app code.
- started: 2026-10-18T21:38Z
- updated: 2026-10-18T21:47Z
- notes: Interpret “expand this” as a substantive, neutral expansion with at least three additional authoritative sources, including the City’s own May 26 agenda/minutes and Wyoming statutes/cases. Preserve caveats; distinguish a documented public objection from statutory remedies and estoppel doctrine. Avoid inferring motive or a Wyoming court outcome. The City-linked video, City Clerk inbox, and any separate Miller email were not independently reviewed.

### claim: estoppel-effect-algorithm — reproducible source-aware chronology and commitment-testing analysis
- worker: arena-agent
- status: active
- stage: PR #11 merged to `main` (merge commit `f4fc508`); Streamlit Community Cloud redeploy is expected from `main`, but the live URL is not externally verifiable from this sandbox
- scope: NEW `tools/estoppel_effect.py` (algorithm + CLI), NEW `tools/test_estoppel_effect.py` (stdlib unit tests), NEW `tools/ESTOPPEL_EFFECT_ALGORITHM.md` (algorithm, limits, runbook), NEW `pages/23_Estoppel_Effect.py` (automatic cached review page), `streamlit_app.py` + `Transparency_Index_App.py` (identical twin home-card links, explicitly authorized by the user's live-site integration request), and READ-FIRST.md (this claim + work-log entry only). Additive only; do not edit transcripts, captions, datasets, existing tools, or generated site data.
- started: 2026-10-18T21:50Z
- updated: 2026-10-18T22:25Z
- notes: The page automatically runs the report when opened, caches the read-only output by input SHA-256, and provides a manual rebuild and JSON/CSV downloads; it is linked from both identical app home entrypoints. AppTest on the page showed 0 exceptions and the expected 926-source/7,678-event/479-lead summary; AppTest on the home entrypoint showed 0 exceptions and the new page link. The full corpus produced 200 cross-meeting chronology candidates, 8 timestamp-sequence candidates, and 271 same-meeting source cross-checks; counts are not verified statements, distinct meetings, or legal findings. Manual spot checks found issue-specific leads and noisy lexical overlaps, so audio/source and proposition review remains mandatory. The intervention index supplied 616 rows -> 291 selected cue records (228 `turn` labels, 63 context; 325 alternatives retained as non-independent metadata); the 720-record meeting master supplied 635 primary text records after 85 exact duplicates were excluded. Speaker attribution is not independently verified, and cross-check records may derive from the same captions. The separate recovery artifacts are absent and were not processed; the earlier all-2026-video review remains incomplete. No source data, existing tools, site data, or transcripts were modified.

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
- notes: hosting only — no product logic, no data, no credential in any file. Services bind loopback; nginx is the only public door. The civic cycle on the VM is the GitHub Action's job minus the push (push block shipped commented-out, deploy key required to enable). Verified without a cloud account by rendering every artifact for both the domain and bare-IP configurations and checking them with systemd-analyze + structural assertions; `bash deploy/oracle/selftest.sh` reproduces it. Not verified (no OCI credentials in this sandbox, and none were requested): instance launch, certbot against real DNS, and nginx -t on the VM — `preflight.sh` is the gate for those on the box. Coordination note (2026-10-18T21:24Z): this claim was last updated 2026-10-15T22:05Z (>6 hours ago), so it is treated as abandoned only for overlapping READ-FIRST edits; existing work is preserved.

### claim: arrest-records — de-identified arrest-record tier (public records, names sealed)
- worker: arena-agent
- status: active
- stage: THREE tiers + a password-gated LIVE page. (1) 65-record tier from the captured weekly report. (2) Owner's MASTER_ARREST_DATABASE.pdf (261 pp) imported: 6,569 records -> 6,492 public, 97 weekly reports, 2021-01-09..2025-09-27, 4,539 unique names sealed. (3) Ingest-time redaction gate (engine/redact.py + hooks) so future captures never commit a name. NEW: the public tier now publishes to the live site behind a password. tools/build_arrest_page.py shapes it (2,996,542 B -> 286,788 B by string interning; 6,492 + 65 rows, both verified field-for-field against source) and tools/arrest_page_seal.mjs seals it with AES-256-GCM under PBKDF2-HMAC-SHA256 / 210,000 iterations -> 382,444 B of base64 ciphertext. Wired into .github/workflows/ai-record-pages.yml between 'Render static site' and the artifact upload, so it lands at <user>.github.io/therealwindycity/arrest/. pages/22_Arrest_Database.py adds the same gate on the Streamlit side, reusing tools/arrest_explorer.py via runpy rather than duplicating it. Both gates proven fail-closed: 5/5 planted names/ages abort the build at exit 3; no password or a <12-char password publishes a notice page and NO data; a wrong password raises OperationError rather than returning garbage. The password lives only in a GitHub Actions secret / Streamlit secret - never in the repo, never logged. TWO OWNER ACTIONS REMAIN before this is live: merge PR #8 (Pages deploys from main only), and add the ARREST_PAGE_PASSWORD secret. FLAGGED, NOT TOUCHED: pages/21_Arrest_Records.py (5759aba, 2026-10-17, 'Colab Composer') publishes two HARDCODED FABRICATED arrest records - ARR-7819 / ARR-7820, with a statute citation and a 'PENDING DETENTION' disposition. It is not data, it is two Python literals presented as an arrest directory, and it sits in the same app as the real 6,492-record dataset. Left in place because this protocol is additive-only and I did not create it; the owner should remove or explicitly label it as fiction.
- scope: NEW `tools/build_arrest_records.py`, `tools/import_master_arrest_db.py`, `tools/arrest_explorer.py`, NEW `engine/redact.py`, NEW DIR `data/arrests/` (records.json/csv, master_records.json/csv, README.md; keyring.jsonl + name_key.json + access_ledger.json are gitignored and never committed), NEW `.github/ISSUE_TEMPLATE/arrest-name-request.md` (the name-release gate), `.gitignore` (seals the keyring/ledger + SQLite WAL sidecars), MINIMAL hooks in `engine/ingest.py::_ingest_one` and `engine/db.py::index_text` (call the redactor, fail closed), READ-FIRST.md (this claim + work log). NEW `tools/build_arrest_page.py` + `tools/arrest_page_seal.mjs` (the sealed live page), NEW `pages/22_Arrest_Database.py` (the Streamlit-side password gate), `tools/arrest_explorer.py` (added an ARREST_EXPLORER_EMBEDDED guard around set_page_config so it can be embedded without a double call), and `.github/workflows/ai-record-pages.yml` (one new build step + three paths-filter entries). Explicitly NOT touching: the twins, data/engine.db, data/snapshots/, requirements.txt, pipeline/, public/, deploy/oracle/, and pages/21_Arrest_Records.py. TWO widenings of the original scope are recorded here rather than left implicit: the engine/ hooks, and now .github/workflows/ + pages/, which the original scope excluded.
- started: 2026-10-17T23:40Z
- updated: 2026-10-18T02:25Z
- notes: owner directive — publish arrest records WITHOUT names; names released only on request, for public-safety and non-discriminatory research only. Charges are kept verbatim, never paraphrased; categories are charge groupings only and deliberately encode no protected characteristic or proxy for one (registry-compliance and immigration holds fold into the neutral warrant_court bucket rather than getting a targeting-able label). No demographic field is derived or inferred. Source caveats are carried verbatim into the output because the exclusions (juveniles, sexual-nature charges, anyone bonded out before release) are SYSTEMATIC, so the data must never be read as a complete picture. HONESTY, recorded in data/arrests/README.md §Honesty: the names are already public — capcity.news publishes them, and this repo already holds them TRACKED in data/snapshots/ (64/64) and in data/engine.db's FTS5 text_index (64/64, measured with --report-leaks). This tier governs what THIS PROJECT publishes and surfaces; it is an access-and-use gate, not secrecy. Redacting the source capture at ingest is a real fix but destroys provenance for the verify_vault.py bridge and cannot reach git history — left as an owner decision, deliberately not done here. Coordination note (2026-10-18T21:24Z): this claim was last updated 2026-10-18T02:25Z (>6 hours ago), so it is treated as abandoned only for overlapping READ-FIRST edits; existing work is preserved.

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

### claim: p2-ecosystem-upgrades — execute the seven P2 structural upgrades from the 2026-10-28 ecosystem memo
- worker: arena-agent
- status: done
- stage: complete — five of seven P2 items executed and verified end-to-end (191 unit tests pass, budget audit and archive catalogue run live against api.github.com); two items recorded as blocked rather than claimed, with reasons
- scope: NEW `tools/repo_partition.py` + test, NEW `tools/intelligence_budget.py` + test, NEW `tools/archive_index.py` + test, NEW `tools/semantic_retrieval.py` + test, NEW `tools/distribution_publish.py` + test, NEW `docs/ARCHITECTURE-TIERS.md`, additive `AGENTS.md` architecture section, NEW `ECOSYSTEM-INVENTORY-AND-UPGRADE-MEMO-2026-10-28.md` (already written), NEW generated artifacts under `data/partition/` + `data/archive-index/` + `data/retrieval/` + `data/distribution/` + `data/intelligence-budget/` (all gitignored as tier-4 derived artifacts), READ-FIRST.md (this claim + work-log entry only). Explicitly NOT touching: the twins (streamlit_app.py / Transparency_Index_App.py), requirements.txt, engine/, .github/, existing pipeline/*, uploads/, Entity_Database/, public/, rag/, deploy/, youtube-archive/, existing tools/*, transcripts, captions, datasets. NO history rewrite, NO force-push, NO deletion of tracked media, NO cross-repository writes.
- started: 2026-10-28T09:40Z
- updated: 2026-10-28T10:35Z
- notes: Owner directive 2026-10-28: "Complete all tasks that you said would take 3 months but do it right now." Measured facts driving this claim: 1,272,712,872 tracked bytes in the working tree (5,597 files), of which 596,009,578 are .mp4 — the repo's own miller-tapes claim states "videos stay out of git per repo rule", so that mass is a standing rule violation, not a design choice. `video/gaveled-down-miller-montage.mp4` and `videos/gaveled-down-miller-montage.mp4` are both tracked at 24,770,554 bytes each (duplicate). All six `therealwindycity/cheyenne-archives-*` repos are FULLY enumerable via the Git trees API with `truncated=false`: 5,140 blobs / 6,970,150,704 bytes total, which is larger than the 4.17 GB the repo `size` field reports. HARD LIMITS recorded up front rather than discovered later: (a) reducing already-tracked mass requires history rewrite or `git rm` + accept-no-shrink, both of which are owner decisions — this claim builds the tooling, manifests and export bundles and does NOT rewrite history; (b) cross-repository writes to civic-newsroom-intelligence-001 and TheReelWindyCity need explicit approval per AGENTS.md, so those two items ship as verified in-repo tooling plus exact commands, not as landed commits elsewhere; (c) OCR/text extraction of the 6.97 GB remote archive is compute- and network-bound and cannot complete in this sandbox — the pipeline ships tested against local PDFs plus a real bounded cross-repo sample, with the full run left as one command; (d) `LEGAL.md` forbids automated outbound communication, so the distribution layer drafts and publishes feeds only and never sends. A committed minilm-l6-onnx model (90,405,214 bytes, with tokenizer.json) is already tracked here, and onnxruntime 1.31.1 + tokenizers 0.23.3 + pypdf 6.21.3 install cleanly, so semantic retrieval is built offline against that model rather than duplicating rag/'s Chroma path.

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
- 2026-10-18 — arena-agent (arrest-records): password-gated arrest database published to the live site (claim arrest-records, built + verified locally, NOT yet live — needs PR #8 merged and the ARREST_PAGE_PASSWORD secret added). GitHub Pages is static hosting with no server, so there is no such thing as a server-side login there; a JavaScript-hidden div would not be protection because the data would still ship to the browser. The gate is therefore real client-side cryptography: NEW tools/build_arrest_page.py reads ONLY the public tier (data/arrests/master_records.json, records.json — sealed files are listed so the refusal is explicit, never opened), shapes it columnar with interned string tables (2,996,542 B -> 286,788 B, a 7.8x reduction: 11,785 charge entries collapse to 2,532 distinct strings, 6,492 rows share 113 source URLs), and NEW tools/arrest_page_seal.mjs seals it with AES-256-GCM under PBKDF2-HMAC-SHA256 / 210,000 iterations / 16-byte salt / 12-byte IV, emitting 382,444 B of base64. The browser opens it with WebCrypto using the identical parameters. Verified: the sealed blob round-trips through WebCrypto (the exact browser API) to both datasets (master 6,492 rows, laramie 65), a wrong password raises OperationError instead of returning garbage, and replicating the viewer's expand() in Node reproduced EVERY field of all 6,557 rows against the source JSON with 0 mismatches — the dictionary-index encoding is not silently corrupting anything. TWO GATES run before a byte is written. The structural gate always runs and needs no keyring: any record with a non-null name, a non-null age, or name_withheld != true aborts the build. Injection tests prove it fails closed — 5/5 planted values (a name, a name+age, an age alone, a cleared withheld flag, a name in the final record) each exit 3 with the offending record ID named, while the unmodified control publishes normally. The keyring audit re-runs the importer's sealed-name audit over the exact bytes about to be published WHEN keyring.jsonl is present; it was absent here (lost in a sandbox rebuild — it is gitignored and was never committed, and is regenerable from the owner-held PDF), so it reported SKIPPED with the reason rather than masquerading as a pass. In CI the keyring never exists, so a CI build physically cannot publish a name it does not have. No password -> a notice page and NO data, exit 0 plus a GitHub ::warning:: annotation so a missing secret cannot break the 3-hour mirror build but also cannot publish an unprotected page; --strict makes it exit 3. A password under 12 characters is refused outright because the blob is publicly downloadable and attackable offline. Two bugs were caught by tests rather than by reading: a mismatched quote in the generated viewer JS (found by extracting the <script> block and running node --check, after an earlier '&& echo OK' had masked the failure), and a relative_to() crash when the builder is pointed outside the repo. NEW pages/22_Arrest_Database.py adds the same gate on the Streamlit side, reading the password from st.secrets (never the repo), comparing with hmac.compare_digest, counting attempts, and then running tools/arrest_explorer.py via runpy so there is ONE copy of the viewer and ONE copy of the data rules; tools/arrest_explorer.py gained an ARREST_EXPLORER_EMBEDDED guard around set_page_config so embedding it does not raise. AppTest-verified: with no secret it fails closed (0 dataframes, 0 metrics, setup instructions shown); a wrong password is rejected with an attempt counter and serves nothing; the right password unlocks and renders 6,492 events / 97 reports / 11,785 charge entries / 'Names published: 0' / 0 exceptions. .github/workflows/ai-record-pages.yml gained one step between 'Render static site' and the artifact upload, plus three paths-filter entries (tools/build_arrest_page.py, tools/arrest_page_seal.mjs, data/arrests/**) so data changes rebuild the page; the deploy job's main-only gate is unchanged, so nothing goes live until PR #8 merges. Names are deliberately NEVER in the encrypted blob: on static hosting one leaked password would publish 4,539 real names permanently with no way to revoke a mirrored file, so a name-bearing tier needs a real server (Streamlit Cloud secrets or the parked Oracle VM), not Pages. HONEST LIMIT: this is an access gate on a de-identified dataset, not secrecy about the arrests, which a news outlet already published. FLAGGED TO OWNER, NOT TOUCHED: pages/21_Arrest_Records.py (5759aba, 2026-10-17, author 'Colab Composer', commit message 'feat: deploy high-contrast arrest records dashboard') publishes two HARDCODED FABRICATED arrest records — ARR-7819 'Interference with Public Safety Radio Systems (18-19.1)' PROCESSED and ARR-7820 'Unlawful Access inside Secured Communications Loop' PENDING DETENTION, dated 2026-10-18/19. They are Python string literals, not data from any source, and they assert specific dates, reference numbers, a statute and a custodial disposition. Left in place because this protocol is additive-only and I did not create it, but it is now on main, it will deploy to the Streamlit app, and it sits beside the real dataset — the repo's own ACCESS-TEST-2026-10-16.md grades exactly this pattern 'Made up'. Recommend the owner delete it or label it unmistakably as fiction. Also merged origin/main (d207a93) into this branch; the twins are still byte-identical.
- 2026-10-18 21:32Z — arena-agent (miller-estoppel-white-paper): added `MILLER-ESTOPPEL-EFFECT-WHITE-PAPER-2026-10-18.md` (about 9,000 words), a neutral, timestamped analysis of Miller’s public “formal constructive notice” and “absolute estoppel effect” claims. Includes May 26 item 28A chronology and the consent-agenda correction; June 8 counsel exchange and related 2026 examples; caption-source/corpus limitations; a reproduced phrase-count method; general federal estoppel, preclusion, immunity, and municipal-liability authorities; evidence-grade matrix and future-research protocol. No transcript, caption, or dataset edits.
- 2026-10-18 21:47Z — arena-agent (miller-estoppel-white-paper-expansion): expanded the paper to about 12,400 words with the official May 26 agenda and City Clerk minutes, a source-hierarchy and agenda-sequence analysis, Wyoming Public Meetings Act/Public Records Act sections (including §§ 16-4-402 through 16-4-408 as cited), and Wyoming Supreme Court estoppel/open-meetings precedent; registered P10–P12 and L1–L6. Reproduced Appendix C counts (83 date-stamped files; 40 “constructive notice” matches across 7 files, 26 “formal constructive notice” across 6, 1 “estoppel” match); all in-text source IDs have appendix entries; `git diff --check` clean. City-linked video audio, any Clerk inbox/email receipt, and any court docket on this specific contract were not reviewed. No transcript, caption, dataset, or app-code edits.

- 2026-10-18 22:10Z — arena-agent (estoppel-effect-algorithm): delivered the additive `tools/estoppel_effect.py` CLI, stdlib tests, and `tools/ESTOPPEL_EFFECT_ALGORITHM.md` runbook. The algorithm extracts eight tactic-oriented phrase signals plus separate diagnostic markers, offsets/excerpts and hashes; deduplicates alignment variants; optionally adds unattributed meeting-level context; and ranks timestamped or date-ordered source comparisons without deciding attribution, contradiction, reliance, causation, or legal effect. Validation: `py_compile` passed, 7/7 unit tests passed, and the default local corpus run processed 616 intervention rows into 291 selected cues (325 alternatives not counted independently) plus 720 master records (635 primary, 85 exact duplicates excluded), yielding 7,678 candidate events and 479 ranked leads (200 cross-meeting, 8 same-meeting sequence, 271 source cross-check). Spot checks found both issue-specific candidates and noisy lexical overlaps; all require human source/proposition review. JSON/CSV smoke outputs were kept under `/tmp`; no input data or existing tools were changed. The separately described recovery artifacts were not present or processed, and the all-2026-video review remains incomplete.

- 2026-10-18 22:23Z — arena-agent (estoppel-effect-algorithm live integration): following the user's explicit request to apply the research aid to the running site, added `pages/23_Estoppel_Effect.py`. Opening the page automatically builds the analysis, caches it by both input-file hashes, exposes filters and human-review excerpts, and offers JSON/CSV downloads plus a manual rebuild. Added a home-page card in both identical Streamlit entrypoints. Installed Streamlit only in `/tmp` for AppTest validation: the new page rendered 926 source records / 7,678 event clusters / 479 comparison leads with 0 exceptions; the home app showed the new link with 0 exceptions. This is not live until the branch is merged into the deployed `main` branch and Streamlit Cloud completes its normal redeploy.

- 2026-10-18 22:25Z — arena-agent (estoppel-effect-algorithm): PR #11 merged to `main` as `f4fc5086066a0891777f501d35844c9914c962fc`, so the Streamlit Community Cloud auto-deploy trigger is in place. The repository documents that the app runs from `main`; the external Streamlit live URL could not be checked from this sandbox, so actual redeploy completion remains unverified.


### claim: archive-freshness — honest status and deployment verification
- worker: arena-freshness
- status: done
- stage: six unit tests passed; synthetic build/render (12 pages) and artifact verifier passed; not deployed
- scope: tools/build_ai_record.py, NEW tools/ai_record_status.py, NEW tools/check_ai_record.py, NEW tools/test_ai_record_status.py, tools/README-ai-record.md, .github/workflows/ai-record-pages.yml, READ-FIRST.md (claim/log only)
- started: 2026-10-21T12:20Z
- updated: 2026-10-21T12:20Z
- notes: Additive status clarification; preserve source records and existing prose. No other app or repository changes.

- result: Added a static freshness/coverage panel and snapshot metadata, local and post-deploy SHA/run verification, and deployment boundaries documentation. No source data, Streamlit twins, or external repositories changed. Full corpus/network publication was not run.


### claim: deployment-agent-handoff — publish cross-repository repair instructions
- worker: arena-freshness
- status: done
- stage: handoff written; publishing with completed freshness safeguards on this session branch
- scope: NEW DEPLOYMENT-REPAIR-HANDOFF.md; READ-FIRST.md (claim/work-log only); commit and publish the completed archive-freshness changes on this session branch
- started: 2026-10-21T13:09Z
- updated: 2026-10-21T13:09Z
- notes: No external repository changes or live deployments in this task.


- result: DEPLOYMENT-REPAIR-HANDOFF.md documents external-repository fixes, diagnosis-only Streamlit work, publication of this repo’s pending changes, acceptance tests, and evidence requirements. No live deployment performed.


### claim: civic-atlas-dais — agenda evidence map and synchronized video crop workspace
- worker: arena-atlas
- status: done
- stage: delivered standalone app; 9 unit/integration tests and JS syntax pass; preview on port 8080; no production deployment
- scope: NEW civic_atlas/; READ-FIRST.md (claim/log only). No existing app, data, or pipeline edits.
- started: 2026-10-25T00:00Z
- updated: 2026-10-25T00:00Z
- notes: Local corpus discovery, lexical evidence links, manual video crops; no identification or emotion inference.


- result: Added `civic_atlas/` with stdlib read-only API/server, agenda-item search, interactive source graph, excerpts and provenance, JSON export, pasted-text agendas, and synchronized manual video crops. Index covers 720 linked meeting entries, 345 Markdown documents, one archived HTML agenda; connections are explicitly lexical leads, not verified relationships. Dais Lens uses a single video clock, local or repository MP4s, manual labels and crops, and browser layout persistence; no identification, emotion inference, live-feed acquisition, or off-camera reconstruction. Nine tests passed, `node --check` and `git diff --check` passed. Browser rendering was not automatically tested. Existing twins, source records, and workflows untouched; no production deployment.


### claim: universal-dais-lens — optional lens for any shared video tab/window
- worker: arena-atlas
- status: done
- stage: implemented; 8 DOM interaction tests + 9 Python tests pass; JS syntax and whitespace checks pass; preview restarted
- scope: civic_atlas/; READ-FIRST.md (claim/log only)
- started: 2026-10-25T06:40Z
- updated: 2026-10-25T06:40Z
- notes: User explicitly requests the lens option for every video. Shared tab/window input avoids cross-origin player pixel restrictions; permission and protected-video limits remain.


- result: Added global opt-in floating lens, separate pop-out window, and user-authorized tab/window capture for cross-site players. Reuses the single video clock and same tile DOM; switches release capture, browser stop clears frames, cancelled picker preserves source, blocked popup falls back. Documented HTTPS/desktop/iframe permissions, DRM/off-camera limits, no automatic injection into external players, and explicit stop-sharing behavior. Real browser sharing was not verified; 8 mocked DOM and 9 Python tests pass. Existing app entrypoints/data unchanged.


### claim: atlas-streamlit-integration — integrate map and optional lens into deployed app entrypoints
- worker: arena-atlas
- status: done
- stage: integrated and tested; preparing PR publication to configured deployed main; external Cloud completion not verified
- scope: civic_atlas/; NEW pages/25_Civic_Atlas.py; twins streamlit_app.py + Transparency_Index_App.py (identical home card and preview video option); rwc_views.py (video launchers only); miller_theater.py (lens launcher + equivalent literal separator for Python 3.11 import compatibility); pages/16b_Screening_Room.py (lens launcher only); READ-FIRST.md (claim/log only)
- started: 2026-10-25T07:00Z
- updated: 2026-10-25T07:00Z
- notes: Explicitly authorized live-app integration; preserve data and existing players. No production deployment claimed without verification.


- result: Added native Streamlit agenda/search/paste page with interactive source graph, full source inspection, and lead exports; identical home-entry cards; opt-in lens beside existing video players (home previews, Origin/Tapes, media fallback, Miller playlist, Screening Room). Embedded lens is self-contained, with a downloadable standalone HTML fallback for Streamlit iframe screen-capture policy restrictions; no second backend, external assets, new requirements, or source-data edits. Tests: 13 Python server/artifact tests, 8 mocked JS DOM tests, 6 Streamlit AppTests (four video-page subcases), portable HTML DOM smoke (0 errors, 4 tiles), JS syntax and Python compile, twins identical and diff whitespace clean. Integrated Streamlit preview on 8501; standalone remains on 8080. Actual browser capture and public Cloud redeploy completion unverified. Publishing integration via this session branch/PR; no main branch checkout or direct push.


### claim: osint-map-workspaces — standalone Laramie County map, Civic Atlas integration, and upgraded explorer
- worker: arena-agent
- status: done
- stage: three standalone pages plus GitHub Pages build wiring/index export implemented; 14 Python tests, JavaScript syntax, Python compilation, generated static index (~14 MB), route smoke checks, and whitespace check pass; preparing push and deployment PR
- scope: NEW `civic_atlas/osint/`; NEW `civic_atlas/build_osint_index.py`; `civic_atlas/server.py` (static routes only); `civic_atlas/test_server.py`; `civic_atlas/README.md`; `.github/workflows/ai-record-pages.yml` (static explorer publication); READ-FIRST.md (claim/work-log only). Existing Civic Atlas UI, pages, entrypoints, corpus, and records untouched.
- started: 2026-10-25T14:00Z
- updated: 2026-10-25T14:25Z
- notes: `/osint-original.html` recreates the original-style workspace with fabricated graph examples removed; `/osint-atlas.html` connects GIS feature attributes to local Atlas lexical search; `/osint.html` is the upgraded standalone. All include the GIS layer catalog, constrained SQL-like filters, 500 ft Turf buffer and source-feature attribute graph. No inferred ownership, threat assessments, or fake relations. The preview is running; no production deployment or external GIS service/browser rendering was independently verified.

- result: Added responsive and accessible route-backed workspaces, allowlisted static serving, and route tests. The existing Civic Atlas landing page and Streamlit experience remain unchanged. All pages answered HTTP 200 and `/api/search` returned records in local smoke checks. External Leaflet/Esri/Turf assets and county services require browser network access.

### 2026-10-28T10:35Z — arena-agent — claim p2-ecosystem-upgrades — five of seven P2 items executed and verified; two recorded as blocked

- result: Built and ran five tools against live data, with 191 unit tests passing. Two P2 items are recorded as blocked rather than claimed complete, and one item was added that the memo did not call for because the work surfaced a defect that outranked it.

Executed and verified:

- **P2.1 monolith partition** — `tools/repo_partition.py` (+22 tests). Measured 1,213.8 MiB tracked across 5,597 files: outbound 771.2 MiB (60.5%), review 252.9 MiB, resident 189.7 MiB; `.git` is 816 MiB. Found 584 exact-duplicate groups wasting 51.6 MiB, including `video/gaveled-down-miller-montage.mp4` and `videos/gaveled-down-miller-montage.mp4` byte-identical at 24,770,554 B each — 23.6 MiB lost to a directory-name plural. Emits `manifest.json`, `measurement.json`, a ready-to-apply `gitattributes-lfs.txt` and `MIGRATION.md`. The 596 MiB of tracked .mp4 contradicts this repo's own `miller-tapes` rule ("videos stay out of git per repo rule"). Nothing was moved: reclaiming tracked mass needs a history rewrite or `git rm`, both owner decisions.
- **P2.3 cold-archive index** — `tools/archive_index.py` (+53 tests), run end-to-end against all five `cheyenne-archives-*` repos via `api.github.com`. Catalogued 5,140 blobs / 6,970,150,704 B (6.97 GB) with `truncated=false` on all six tree listings — larger than the 4.17 GB the repo `size` field reports. Dated **5,116 of 5,140 (99.5%)** across 820 distinct meeting dates from 2008-05-27 to 2026-06-08 and 22 municipal bodies. Extracted 184 documents (23,164,505 B, zero failures); 183 had a text layer, 1 recorded as `image-only-needs-ocr` rather than dropped. Indexed 183 documents into 16 gzip BM25 shards and verified search. Emitted a Frictionless `datapackage.json`. Ambiguity was flagged, never guessed: 215 ambiguous dates, 431 two-digit years, 7 genuine intra-path date conflicts.
- **P2.2 intelligence budget guard** — `tools/intelligence_budget.py` (+28 tests), run live against the real published host `bartimoussmith-oss/civic-newsroom-intelligence-001`. All verification checks pass, including collection SHA-256 `3518b46f…ca3f6c` matching the declared digest and stored bytes matching 493,608,460 exactly. Budget: **493,608,460 / 536,870,912 = 91.95%, severity `warning`, 41.26 MiB headroom, 5 builds to exhaustion** at 8 MiB/run. This is the failure already committed verbatim in `status/intelligence-error.json` (`ValueError: Packed intelligence needs additional approved host: 493607874 bytes`), now measured before it happens. Strictly read-only cross-repository; CI exits 3 on exhausted/unverified and 4 on fetch failure or zero hosts, including under `--quiet`.
- **P2.5 semantic retrieval** — `tools/semantic_retrieval.py` (+31 tests), run offline against the already-committed `minilm-l6-onnx` model (90,405,214 B). Embedded 183 documents into 1,217 passages (norms exactly 1.0, mean pairwise cosine 0.46 — healthy spread, not a collapsed matrix). Verified that retrieval is semantic and not lexical in disguise: the query "neighbors objecting to new construction near their homes" returns a passage about mitigating "the effects on neighbors through the site plan" at cosine 0.469, which the BM25 index does not rank first. RRF fusion uses k=60 to match the existing `rag/query.py`, so the two retrieval paths stay comparable. `candidates` emits an entity-resolution review queue where every row is `status: candidate-unreviewed`; nothing is merged and nothing alleges wrongdoing.
- **P2.6 distribution layer** — `tools/distribution_publish.py` (+50 tests), run against the live ledger. Renders RSS 2.0, Atom 1.0, a machine-readable webhook payload, a Markdown digest and an `.eml` draft, all well-formed and all verified `sent_by_this_tool: false`. Contains no SMTP client, no send call and no HTTP POST; the draft carries `X-Unsent: 1` and a placeholder recipient, per `LEGAL.md` §4.
- **P2.7 architecture tiers** — `docs/ARCHITECTURE-TIERS.md` plus an additive `AGENTS.md` section, and tier-4 `.gitignore` entries for `data/archive-index/`, `data/retrieval/`, `data/partition/`, `data/intelligence-budget/` and `data/distribution/`.

Added, not in the memo — a defect found while building P2.6:

- **Silent-edit detection has a 91.11% noise floor.** Of 225 `SILENT-EDIT` alerts in `data/engine.db`, **205 are page-assembly changes and 1 carries possible editorial signal** (19 uncertain). The detector diffs raw HTML, so site-wide chrome fires an alert on every page of a domain at once. Classes observed verbatim: WordPress asset cache-busters (`block_styles.css?ver=4.36.3` → `?ver=4.36.5`), `data-pmdelayedstyle` timestamps, Akamai mPulse RUM beacons (`s.go-mpulse.net/boomerang`), inline polyfill JavaScript, core-js exception text (`String.prototype.includes must not be null or undefined`), a newsletter-signup widget (`Do you have email set up?`), a related-articles headline recurring across 21 unrelated articles, tracking config (`ppconfig={…deleteIsEnforced…}` recurring 35×) and social-share tokens (21×). Affected pages include obituaries, an opinion column, arrest reports, weather and high-school sports. `tools/distribution_publish.py` triages before publishing and prints the noise floor alongside the signal, so the figure is auditable rather than hidden. Root cause is in `engine/`, which this claim explicitly does not touch; the triage layer is a compensating control, not a repair.

Blocked, not claimed complete:

- **P2.4 record envelope (Frictionless/OCDS)** — not attempted. Reason: `tools/archive_index.py` already emits a Frictionless `datapackage.json` for the whole 6.97 GB corpus, and the OCDS-shaped part of this item depends on entity resolution that does not exist yet — the published intelligence corpus itself declares `verified_entity_resolution: false` and `source_independence: "unresolved"`. Building an OCDS envelope on top of unresolved entities would produce records whose `tender`/`award` parties cannot be verified, which is a fabricated-citation risk rather than a gap. The prerequisite is the P2.5 review queue being worked by a human.
- **Full-corpus OCR and full-archive embedding** — cannot complete in this sandbox. The remote archive is 6.97 GB; the sandbox has 2 CPUs, 3.9 GB RAM and 18 GB free, `tesseract`/`pdftotext`/`qpdf`/`gs` are absent, and `raw.githubusercontent.com` is unreachable (only `api.github.com` works, which caps single-fetch payloads at 1 MB). 183 of 5,140 documents are indexed. The pipeline is shipped and tested end-to-end on a real bounded cross-repo sample, and the full run is one command; it is not done and is not claimed as done.

Not verified, stated plainly: no public URL, GitHub Pages HTTP response, Streamlit deployment or search-index state was reached from this environment. All deployment claims rest on Actions run conclusions and the repositories' own committed status files. Nothing here was exercised in a browser, and per `docs/ECOSYSTEM-AGENT-GUIDE.md`, implemented is not tested, tested is not deployed, deployed is not independently verified live.

No history was rewritten, nothing was force-pushed, no tracked media was deleted, no other repository was written to, and no outbound communication was sent.
