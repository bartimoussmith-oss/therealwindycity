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
