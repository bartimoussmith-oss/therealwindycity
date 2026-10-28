# EXECUTIVE MEMORANDUM — Connected Repository Ecosystem: Inventory, Capability, and Upgrade Path

- **Date:** 2026-10-28 (America/Denver)
- **Prepared by:** Executive Systems Strategist agent, branch `arena/7c946ca1-therealwindycity`
- **Method:** Live GitHub API enumeration of both identities + workflow-run forensics + file-level inspection. The 2026-10-25 registry (`civic_atlas/media/projects.json`) was treated as a hypothesis, not a source of truth.
- **Verification boundary:** Outbound network from this sandbox is github.com-only. **No public URL, Streamlit deployment, Google indexing state, or Pages HTTP response was independently fetched.** All deployment claims below rest on GitHub Actions conclusions and the repos' own committed status files. Items outside that boundary are marked `[UNVERIFIED]`.

---

## PART 0 — HEADLINE

Two findings dominate everything else in this memorandum.

**1. The public front end has been dark for ~6 days, and the cause is almost certainly a one-character-class fix.**
`therealwindycity/TheReelWindyCity` → workflow `Deploy to GitHub Pages`: **last success 2026-10-22T00:51:54Z at head `ab8570bf`. Every run since has failed** — 13 consecutive failures enumerated individually, and the most recent 60-run window is 60/60 failure, out of 567 total retained runs (447 historically successful). The failing step is `Build static site` (`npm run build`) on **every** run. The first failing head is `678193d3` ("Add dismissible site-wide navigation help popup"), a +48/−1 commit touching exactly three files. Highest-probability mechanism: the added `src/components/site-help.tsx` contains the JSX text `this page's memory`, which trips `react/no-unescaped-entities`; the same rule is **confirmed failing** in the repo's `CI` workflow on `main` (annotations retrieved verbatim). `[MECHANISM: HIGH CONFIDENCE — NOT LOG-CONFIRMED; Actions log download is blocked from this sandbox]`

**2. The deployment gate is structurally absent, which is why finding 1 went unnoticed for six days.**
`CI` has run on `main` exactly **ten times** in repo history; the last was **2026-10-22T01:00:31Z**, and it failed on `npm run lint`. Since then, `main` has received dozens of commits — all from watcher automations ("Record discovered upcoming-meetings postings", "Copy public place documents", "Record Wyoming watch baselines"). **Nothing on `main` is gated.** The hourly Pages cron fails, retries hourly, and opens no issue. Red state is invisible unless someone reads the Actions tab.

This is not a build bug. It is a control-plane gap, and the build bug is only its most recent symptom.

---

## PART 1 — CHRONOLOGICAL / DATA AUDIT

### 1.1 True inventory: 14 repositories across 2 identities

The 2026-10-25 registry documents 7 projects. The live enumeration finds **14 repositories**, including a 4-repo successor family and a 6-repo archive family created or populated after the registry snapshot.

**Identity A — `bartimoussmith-oss` (user; this checkout's owner)**

| # | Repo | Lang | Size | Last push | Role |
|---|---|---|---|---|---|
| 1 | `therealwindycity` | HTML | **1,943,854 KB** | 2026-10-28T07:22Z | Monolith: archive + research + Streamlit app + civic engine. **This checkout.** |
| 2 | `TheReelWindyCity` | JavaScript | 1,500,214 KB | 2026-10-21T15:25Z | **Fork** (`fork=true`) of the org repo of the same name |
| 3 | `civic-newsroom` | Python | 118 KB | 2026-10-26T20:03Z | Successor: clean code + publishing orchestration |
| 4 | `civic-newsroom-data-001` | Python | 101,016 KB | 2026-10-26T07:11Z | Successor: normalized public data partition |
| 5 | `civic-newsroom-law-001` | Python | 7,030 KB | 2026-10-26T16:25Z | Successor: primary legal-authority corpus |
| 6 | `civic-newsroom-intelligence-001` | Python | 306,744 KB | 2026-10-26T11:00Z | Successor: derived retrieval indexes / candidates |
| 7 | `The-Real-Windy-City-` | Python | 52,119 KB | 2026-10-23T04:38Z | Duplicate name of org repo #9 — see 1.4 |
| 8 | `V-MAX-Colab-Protocol` | TypeScript | 19,325 KB | **2026-02-19T03:25Z** | Unrelated legacy; **8 months dormant**; `node_modules/` committed to git |

**Identity B — `therealwindycity` (org)**

| # | Repo | Lang | Size | Last push | Role |
|---|---|---|---|---|---|
| 9 | `TheReelWindyCity` | JavaScript | 109,473 KB | 2026-10-28T05:58Z | **Public front end** — Next.js static export → Pages |
| 10 | `The-Real-Windy-City-` | Python | 52,119 KB | 2026-10-23T04:38Z | Verbatim timestamped 2026 transcript archive → Pages |
| 11 | `cheyenne-archives-2008-2013` | — | 502,452 KB | 2026-09-28T23:07Z | PDF packet mirror |
| 12 | `cheyenne-archives-2014-2017` | — | 730,160 KB | 2026-09-28T23:07Z | PDF packet mirror |
| 13 | `cheyenne-archives-2018-2021` | — | 672,587 KB | 2026-09-28T23:08Z | PDF packet mirror |
| 14 | `cheyenne-archives-2022` | — | 763,785 KB | 2026-09-28T23:04Z | PDF packet mirror |
| 15 | `cheyenne-archives-2023-2024` | — | 951,653 KB | 2026-09-28T23:06Z | PDF packet mirror |
| 16 | `cheyenne-archives-2025-2026` | — | 554,067 KB | 2026-09-28T23:06Z | PDF packet mirror |

*(16 rows because of the two same-named cross-identity duplicates; 14 distinct code/data assets.)*

**Total tracked footprint: ~6.14 GB.** Archive family alone = 4,174,704 KB (~4.17 GB) of PDF, **30 days stale** (all six last touched 2026-09-28), **zero workflows**, **zero Pages**, **zero open issues**. They are cold storage — which is a legitimate role, but it is an *undeclared* one: nothing in the registry states that these are inert by design rather than abandoned by accident.

### 1.2 Workflow health, measured

| Repo | Workflow | Runs sampled | Failures | Last run | Verdict |
|---|---|---|---|---|---|
| `bartimoussmith-oss/therealwindycity` | Scanner best-effort live and recovery | 33 | **0** | 2026-10-28T07:22Z | Healthy |
| ″ | Scanner historical backfill | 31 | **0** | 2026-10-28T05:56Z | Healthy |
| ″ | civic-cycle | 21 | **0** | 2026-10-28T05:43Z | Healthy |
| ″ | ai-record-pages | 9 | **0** | 2026-10-27T14:52Z | Healthy |
| ″ | meeting-watch | 3 | **0** | 2026-10-28T06:11Z | Healthy |
| ″ | Scheduled Audit & Telemetry Sync | 2 | **0** | 2026-10-27T11:12Z | Healthy |
| **`therealwindycity/TheReelWindyCity`** | **Deploy to GitHub Pages** | **45 / 567 total** | **45 (100% of window)** | 2026-10-28T05:38Z | **BROKEN 6 DAYS** |
| ″ | Citizen Connect Incident Sync | 4 | **4** | 2026-10-27T16:38Z | **100% failing** |
| ″ | Live Wyoming Watch | 4 | **4** | 2026-10-27T18:41Z | **100% failing** |
| ″ | Live Municipal Watch | 43 | 1 | 2026-10-28T05:57Z | Healthy |
| ″ | Live Place Archives | 4 | 0 | 2026-10-27T19:36Z | Healthy |
| ″ | CI (on `main`) | 10 lifetime | last 5 failing | **2026-10-22T01:00Z** | **Dormant + red** |
| `civic-newsroom` | publish-app | 8 recent | 2 | 2026-10-26T19:59Z | Recovered, verified |
| `civic-newsroom` | build-intelligence | recent | 2 | 2026-10-26T08:40Z | Recovered via partition |
| `civic-newsroom-data-001` | export-ai / publish-public-data | 2 | 0 | 2026-10-26T07:10Z | Healthy |
| `civic-newsroom-law-001` | ingest-law | 1 | 0 | 2026-10-26T16:23Z | Healthy |
| `civic-newsroom-intelligence-001` | publish-intelligence | 1 | 0 | 2026-10-26T10:58Z | Healthy |
| `therealwindycity/The-Real-Windy-City-` | Deploy site | 6 | **0** | 2026-10-27T15:20Z | Healthy, daily |
| ″ | Fetch meeting transcripts | recent | **skipped** | 2026-10-23T04:38Z | **Stale 5 days** |
| 6× `cheyenne-archives-*` | — | none | — | — | No automation |

`bartimoussmith-oss/therealwindycity` declares **16 workflows**; only 6 appear in the recent-run window. The other 10 (`Laramie Archive Fresh Start`, `Launch Laramie transcription`, `Laramie Archive Transcriber`, `Validate Laramie Socrata datasets`, `Socrata read-only connection diagnostic`, `Citizen Connect network discovery`, `newsroom-diagnose`, `issue-newsroom-check`, `Scanner transcription test`, `Apply remaining remediation`) are dormant or one-shot. **Ten of sixteen workflows in the flagship repo have not run recently.** That is automation sprawl: each unused workflow is a maintenance liability and a false signal of capability.

### 1.3 Deployment state, honestly separated

All four Pages-enabled repos have `build_type: workflow`, `public: true`, `https_enforced: true`:

| Pages URL | Config | Deploy evidence | Live bytes |
|---|---|---|---|
| `bartimoussmith-oss.github.io/therealwindycity/` | enabled | `ai-record-pages` success 2026-10-27 | `[UNVERIFIED]` |
| `bartimoussmith-oss.github.io/civic-newsroom/` | enabled | `publish-app` success; own `status/app.json` records `build: success`, `deploy: success`, **`intelligence_deployed_browser_test: success`** | `[UNVERIFIED]` |
| `therealwindycity.github.io/TheReelWindyCity/` | enabled | **45/45 fail — serving `ab8570bf`, a 2026-10-22 build** | `[UNVERIFIED]` |
| `therealwindycity.github.io/The-Real-Windy-City-/` | enabled | `Deploy site` success daily through 2026-10-27 | `[UNVERIFIED]` |

Streamlit Cloud (`therealwindycity.streamlit.app`) is asserted by `READ-FIRST.md`. `[UNVERIFIED — not reachable from this sandbox]`

Note the asymmetry: **`civic-newsroom` verifies its own deployed bytes with a headless browser after deploy and records the result in a committed status file. The public front end does not, and has been silently broken for six days.** The newer, smaller repo has better release engineering than the flagship.

### 1.4 Data-integrity defects, verbatim

- **Parser output committed as a primary key.** `therealwindycity/TheReelWindyCity` `main` contains the directory `data/meetings/2026/city-council-in progress open video only in windows media player/`, and `data/sync-state.json` carries `"date": "in progress open video only in windows media player"` as a meeting date. A Windows Media Player error string was parsed as a date, passed no validation, was committed, and is now a filesystem path on the default branch of the public front end.
- **The agenda sync is wedged and self-silencing.** `data/sync-blocked.json`: `reason: "scheduled-watch-sync-failed"`, `retryAfterMs: 86400000` (24 h), `attempts: 1`, `attemptedAt: 2026-10-27T19:31:52Z`. The watcher detects the failure, writes a marker, and stays quiet for a day — by design. Design consequence: a wedged pipeline looks identical to a healthy idle one.
- **The fix exists and is unmerged.** PR **#22** ("Fix stale upcoming-agenda view; un-wedge the agenda ingestion pipeline") diagnoses **three compounding root causes** — no date gate on `upcoming[]`; sync artifacts written to `data/` while the build reads only `src/data/official-meetings.json` (so a *successful* sync changed nothing the site displayed); and two portal-shape bugs (Granicus emits protocol-relative `//host/path` links that `fetch()` rejects; the modern portal has **no combined agenda PDF at all** — `AgendaViewer` redirects to `GeneratedAgendaViewer`, an HTML page that *is* the agenda, so the extractor failed `NO_PDF_LINK`). **+2,840/−121 across 21 files. Open since 2026-10-11 — 17 days.**
- **Fabricated records in a published surface.** `bartimoussmith-oss/therealwindycity` `pages/21_Arrest_Records.py` ships two hardcoded literals — `ARR-7819` and `ARR-7820` — with a statute citation (`18-19.1`) and disposition `PENDING DETENTION`, inside the same Streamlit app as the real 6,492-record sealed dataset. Flagged in the repo's own `arrest-records` claim on 2026-10-18 as left in place under additive-only protocol. **Ten days later it is still there.** In an accountability product this is the highest-severity defect in the corpus: it is a false public record inside a tool whose entire value proposition is record integrity.
- **Cross-identity forks drifting.** `bartimoussmith-oss/TheReelWindyCity` is a fork of `therealwindycity/TheReelWindyCity`, 1.50 GB vs 109 MB, last pushed 2026-10-21 vs 2026-10-28. `bartimoussmith-oss/The-Real-Windy-City-` and `therealwindycity/The-Real-Windy-City-` share a name and identical size/push timestamps. Two authorities, same names, divergent content. An agent following `AGENTS.md` cannot determine which is canonical.
- **Dangling coordination authority.** `AGENTS.md` (on this branch) routes agents to `coordination/tasks.json` and `docs/agent-coordination.md`. **`coordination/` contains 0 files on `origin/main`.** Both live only on the unmerged draft PR #25 branch in the *other* repository. The entry-point document sends agents to files that do not exist in the tree they are standing in.
- **Dead concurrency locks.** Three claims in `READ-FIRST.md` carry `status: active` with `updated:` stamps 10–13 days old (`estoppel-effect-algorithm` 10-18, `oci-deploy` 10-15, `arrest-records` 10-18). The file's own rule declares anything untouched 6+ hours *assumed abandoned*. The lock registry is therefore simultaneously "three active claims" and "zero active claims," and no artifact records which reading governs. (Twin invariant passes: `streamlit_app.py` and `Transparency_Index_App.py` are byte-identical.)

### 1.5 Reconstructed timeline of the outage

| UTC | Event | Evidence |
|---|---|---|
| 2026-10-04 | Agenda sync wedges; 24 h retry loop begins | PR #22 body |
| 2026-10-11 | PR #22 opened with three-root-cause fix | PR metadata |
| 2026-10-21T14:44 | CI on `main` **passes** | run history |
| 2026-10-22T00:17–00:51 | 4 human commits land (`195acc55`, `4393777f`, `ab8570bf`); Pages deploys **succeed** | run history |
| **2026-10-22T00:51:54** | **Last successful public deploy — head `ab8570bf`** | run 39702251810 |
| 2026-10-22T01:00 | `678193d3` (+48/−1, 3 files) → Pages `Build static site` **fails**; CI on `main` fails on `npm run lint` | run 39703125912, annotations |
| 2026-10-22 → 10-28 | 13+ Pages runs, 100% failure at the same step. CI never runs on `main` again. | per-run step enumeration |
| 2026-10-26 | `civic-newsroom` family ships: partitioned data, hash-pinned intelligence, verified deploy | committed status files |
| 2026-10-27T19:31 | `sync-blocked.json` written; watcher silences for 24 h | file contents |
| 2026-10-28T07:22 | This audit. Front end still serving a 6-day-old build. | — |

---

## PART 2 — VULNERABILITY BREAKDOWN

### 2.1 What this ecosystem actually does (capability, not aspiration)

Measured from code and committed data, not descriptions:

- **18 years of primary records under version control.** ~4.17 GB of Cheyenne council agendas, packets, supporting documents and minutes, 2008–2026, banded into six year-range repos.
- **Silent-edit detection.** `data/engine.db` holds 153 documents, **574 versions**, 303 alerts, 996 jobs, 568 FTS5 rows; `data/out/` contains emitted diffs (`silent-edit-doc93-seq2.diff.txt` …). The system re-fetches public documents and **diffs them against prior captures** — it detects when a published record changes without notice. This is the single most differentiated capability in the stack.
- **Hash-verified, tamper-rejecting data publication.** `civic-newsroom-intelligence-001` pins revision `5a32d3f5`, `collection_sha256 3518b46f…`, and publishes **6,065 records / 432,020 passages / 7,916 identifier mentions / 867,452 language candidates / 493,608,460 bytes**. The browser accepts only an explicitly allowed repository, a commit-pinned base, and verified file hashes; parts are reassembled and re-hashed client-side. Deploy is gated on browser retrieval checks and **rejection of tampered data and unexpected hosts**.
- **Adversarially honest self-reporting.** `status/intelligence-error.json` commits its own terminal exception verbatim, including the byte count that broke it. `intelligence-publication.json` ships `verified_entity_resolution: false` and `source_independence: "unresolved"` as *fields in the published contract*. `GOOGLE-READINESS.md` states plainly that a successful deployment is not indexing and that no AI-Mode inclusion date can be promised.
- **Verbatim timestamped transcript archive** with daily Pages deploy and per-meeting links to official city video.
- **A portable multi-agent runtime** (`agent/`) with planner → parallel workers in isolated detached git worktrees → **independent verifier that re-checks every claim with tools** → synthesizer that writes only from verified material; three-tier tool verdicts (`deny`/`confirm`/`allow`), workspace path jailing, audited tool calls with result hashes, and a paste-bridge provider for zero-key operation.
- **Redaction gating** (`engine/redact.py`) that fails closed — 5/5 planted names abort the build at exit 3.

### 2.2 Structural vulnerabilities

**V1 — No gate on the public production path. Severity: CRITICAL.**
`Deploy to GitHub Pages` runs on `push` to `main` *and* on an hourly cron. `CI` runs on `push` to `main` but has executed 10 times lifetime and is red. Watcher automations commit to `main` continuously and never trigger a meaningful gate. Failure produces no issue, no notification, no badge. **Six days of 100% failure was discovered only by manual API enumeration.** Any single malformed auto-commit can take the public site down indefinitely and nothing will say so.

**V2 — Build failure is indistinguishable from stale success, publicly. Severity: CRITICAL.**
Because Pages serves the last successful artifact, the site at `therealwindycity.github.io/TheReelWindyCity/` is *up* and *wrong*: it advertises meetings that already happened. PR #22 documents precisely this class of bug ("advertised the Oct 5 Public Services and Oct 6 Finance committee meetings a full week after they happened"). The outage and the stale-data defect are the same failure mode wearing two hats. A green-looking site is not evidence of a working pipeline.

**V3 — Unvalidated external text becomes schema, keys, and paths. Severity: HIGH.**
`"in progress open video only in windows media player"` is now a **directory name on the default branch** and a **`date` field** in `sync-state.json`. There is no schema validation between "we scraped a string" and "we committed it as a typed field." Downstream, any consumer that sorts by date, builds a URL from a meeting ID, or renders a calendar will silently misbehave. This is the classic injection surface of scraping systems, and it is unguarded.

**V4 — Two coordination authorities, neither canonical. Severity: HIGH.**
`AGENTS.md` points at `coordination/tasks.json` (absent from `main`, present only on unmerged PR #25 in the other repo). `docs/ECOSYSTEM-AGENT-GUIDE.md` explicitly warns "do not silently create a second coordination authority" — while the registry it maintains omits **half the repos**, including the entire successor family that is now the most active work in the ecosystem. Cross-identity same-named repos compound this. An agent cannot determine, from the repo it is standing in, who owns what or which copy is real.

**V5 — Fabricated records in a live accountability surface. Severity: HIGH (reputational/legal).**
See 1.4. Two invented arrest rows with a statute citation and a detention disposition, in the same app as a real sealed dataset of 6,492 records. The additive-only protocol was invoked to justify not touching them; the protocol's own purpose is preventing *loss*, not preserving *falsehood*. Nothing labels them as fiction to a visitor.

**V6 — Monolith mass approaching platform limits. Severity: MEDIUM-HIGH.**
1.94 GB in the flagship repo, 6.14 GB ecosystem-wide, 44 `.mp4` files and 41 PDFs tracked, `node_modules/` committed in `V-MAX-Colab-Protocol`. `READ-FIRST.md` already records a 22 MB tape master as "the largest thing in here" — the repo has since grown ~2 GB past that framing. Clone time, Actions checkout time, and GitHub's soft limits all degrade non-linearly. `civic-newsroom`'s own `AGENTS.md` already encodes the correct answer ("Bound file/repository/site sizes, record measured bytes, and use a root manifest; do not clone all partitions into one Pages artifact") — the monolith simply predates it.

**V7 — Partition budget headroom is 3.7%. Severity: MEDIUM.**
`civic-newsroom-intelligence-001` declares a **512 MiB** publication budget; the pinned release is **493,608,460 bytes (470.7 MiB)**. The 2026-10-26 build failed with `ValueError: Packed intelligence needs additional approved host: 493607874 bytes` and was resolved by publishing to this host. **The next corpus growth increment exhausts the budget.** A `-002` partition will be needed, and nothing schedules that decision.

**V8 — Stale cold storage with no declared SLA. Severity: MEDIUM.**
Six archive repos untouched 30 days, no workflows, no Pages, no issues, and no artifact stating whether that is *by design* or *by neglect*. `The-Real-Windy-City-`'s `Fetch meeting transcripts` last ran **skipped** on 2026-10-23 — five days without transcript ingestion, while the site deploys daily and looks healthy.

**V9 — Dead concurrency locks. Severity: MEDIUM.**
See 1.4. The claim registry cannot answer "is this scope taken?" — the precondition for safe multi-agent work in a repo whose own history includes being "flattened more than once."

**V10 — Automation sprawl. Severity: LOW-MEDIUM.**
10 of 16 workflows in the flagship repo have not run recently; `TheReelWindyCity` carries `Lint rule locator` and `Integration stage diagnostics` (both red on the PR #25 branch). Dormant workflows misrepresent capability to any reader — human or agent — and rot silently against runner-image migrations (both repos already emit the `ubuntu-latest → Ubuntu 26` and Node 20 deprecation notices).

### 2.3 Second- and third-order effects

**0–3 months.** If V1/V2 are unaddressed, the public site continues serving a 2026-10-22 build through the **2026-11-02 Public Services and 2026-11-03 Finance committee meetings** (both confirmed present in `data/detected-upcoming.json`, discovered 2026-10-28T05:57Z). Detection *works* — the watcher found them. Publication does not. Second order: the ecosystem's credibility asset is timeliness; a site advertising last month's meetings as upcoming during two live committee meetings converts an infrastructure bug into a public trust event. Third order: PR #22 ages further, its diff conflicts against six days of watcher auto-commits, and the fix becomes harder to land the longer it waits — the classic unmergeable-PR spiral.

**3–6 months.** V7 bites: intelligence corpus grows past 512 MiB, `build-intelligence` fails terminally, and the newsroom's verified-deploy chain breaks. Because `civic-newsroom` self-reports honestly, this one *will* be visible in `status/intelligence-error.json` — a genuine improvement over V1. V6 compounds: a 2 GB+ monolith makes every Actions checkout slower, raising the cost of the hourly cron that is currently failing hourly. V4 compounds: with two same-named repos per identity pair and a registry covering half the estate, the probability that a new agent edits the wrong copy rises with each session.

**6–12 months.** The strategic fork resolves itself. `civic-newsroom`'s architecture — partitioned, hash-pinned, budget-bounded, browser-verified, adversarially self-reporting — is *structurally superior* to the monolith's. Two outcomes: (a) deliberate migration, with the monolith demoted to source archive (exactly what `civic-newsroom/AGENTS.md` already declares: "Existing repositories remain source archives"), or (b) continued parallel operation of both, doubling maintenance across 14 repos with no canonical map. (b) is the default trajectory and it is the expensive one.

### 2.4 Incentive and behavioral read (low-trust framing)

Actors here are mostly *automations*, and their incentives are legible:

- **The watcher optimizes for silence.** `sync-blocked.json`'s 24-hour quiet window exists to prevent notification spam. Its effect is to make failure indistinguishable from idleness. A component that is rewarded for not alarming will not alarm.
- **The cron optimizes for attempt count, not outcome.** Hourly retries produce 45 consecutive failures and 45 green "run started" rows. Volume of activity is being mistaken for health — by the dashboard, and potentially by any reviewer glancing at it.
- **The additive-only protocol optimizes against destruction, and therefore for accumulation.** It has correctly prevented flattening (a real, repeated historical injury). Applied to `pages/21`'s fabricated records, the same rule *protects a defect*. The protocol needs an explicit carve-out: additive-only governs content an agent did not create; it cannot govern the truthfulness of a published claim.
- **The registry optimizes for snapshot stability.** `projects.json` is dated, evidence-scoped, and honest about being partial. That is good practice — but nobody owns refreshing it, and it is now three days and seven repositories stale.

---

## PART 3 — COMPARABLE SYSTEMS AND POSITIONING

### 3.1 Where each layer sits against known systems

| Layer here | Comparable system | Delta |
|---|---|---|
| Silent-edit detection over 574 document versions | **Wikipedia Watchlist / edit diffs**; **GovDiff**-style legislative text comparison; **DocumentCloud** version tracking | **Ahead.** Most civic tools snapshot; almost none diff-and-alert on *quiet amendment of already-published records*. This is the ecosystem's genuinely novel asset. |
| Agenda/minutes monitoring + alerts | **Documenters.org** (human-in-loop meeting coverage), **Open States** (legislative), **LegiScan**, **Granicus/Legistar vendor platforms** (the incumbent whose data this mirrors) | **Comparable on ingestion, behind on distribution.** Documenters' moat is *people attending meetings*; the vendor platforms' moat is *being the system of record*. Neither has this repo's diff capability. |
| PRA/FOIA request drafting | **MuckRock**, **FOIA Machine**, **RequestMap** | **Comparable, deliberately narrower.** `LEGAL.md` forbids auto-submission (human-in-the-loop by design). MuckRock's advantage is workflow + community; this ecosystem's is Wyoming-specific statutory grounding (`Wyo. Stat. §§ 16-4-201…205`). |
| Hash-pinned, tamper-rejecting data publication | **dat/great-escape**, **IPFS content addressing**, **Frictionless Data** packages, **OCDS** (Open Contracting Data Standard) | **Ahead of typical civic practice, behind formal standards.** The verification chain is real and stronger than most. But it is a *bespoke* envelope; OCDS/Frictionless would make it interoperable with tools that already exist. |
| Banded PDF archive (4.17 GB, 18 yrs) | **Internet Archive / Wayback**, **state digital archives**, **library HathiTrust-style partitioning** | **Behind on access.** Cold, unindexed, no Pages, no full-text search, 30 days stale. Wayback provides what these repos do not: discoverability. Value is locked until indexed. |
| Multi-agent runtime w/ independent verifier | **AutoGen**, **CrewAI**, **LangGraph**, **OpenHands**, **Claude Code sub-agents** | **Comparable architecture, distinctive constraints.** Planner→workers→verifier→synthesizer with tool-level re-checking matches state of practice. The differentiators are *deployment realism* (Termux/Chromebook/no-key paste bridge) and *safety posture* (detached worktrees, nothing auto-applied, deny/confirm/allow). |
| Static-export newsroom front end | **Next.js static export + Pages** (standard), **Astro**, **Eleventy** | **Standard.** No advantage; the value is in the data behind it. The `output: "export"` choice is what makes a single lint-class error capable of a 6-day outage — no server-side fallback exists. |
| Search/retrieval over 432k passages | **OpenSearch/Elasticsearch**, **Meilisearch**, **Typesense**, vector stores (**pgvector**, **Qdrant**), **Tantivy** | **Behind.** Published index is lexical/AND-token based; `verified_entity_resolution: false` and `source_independence: "unresolved"` are self-declared. Semantic retrieval and entity resolution are the acknowledged gaps. |

### 3.2 What is actually differentiated

Three things, in order of defensibility:

1. **Quiet-amendment detection with emitted diffs and verbatim provenance.** Nobody in the comparable set does this at municipal scale with this evidentiary discipline (`LEGAL.md`: every claim carries verbatim quote + source URL + fetch timestamp; unverifiable items go to a notes bin, never the ledger).
2. **Adversarial honesty as a data contract.** Publishing `verified_entity_resolution: false` *inside the machine-readable publication descriptor*, and committing one's own terminal exception with the byte count that caused it, is rarer than it should be and is a genuine trust asset with journalists and lawyers — the actual audience.
3. **Sealed, fail-closed redaction with a release gate.** AES-256-GCM under PBKDF2-HMAC-SHA256/210k, build aborts on any planted name (5/5, exit 3), names released only via a documented request template. This is a publishable-records posture most civic projects lack entirely.

What is *not* differentiated: the Next.js front end, the Streamlit app, the banded PDF storage, the agent runtime's core loop.

---

## PART 4 — UPGRADE PATH

### P0 — restore the public surface (0–7 days)

| # | Action | Acceptance criterion |
|---|---|---|
| P0.1 | Fix the `Build static site` failure in `therealwindycity/TheReelWindyCity`. Start from `678193d3`'s three files; escape apostrophes in JSX text (`site-help.tsx` "this page's memory"; also the confirmed `src/app/page.tsx` "What's happening?" / "publisher's date" and `src/app/explore/public-safety/page.tsx`). Retrieve the real Actions log from an unrestricted network before assuming — **the bisect is certain, the mechanism is inferred.** | `Deploy to GitHub Pages` green on `main`; deployed revision matches head; the 2026-11-02 and 2026-11-03 committee meetings appear as upcoming. |
| P0.2 | Merge or supersede **PR #22**. It fixes the wedge, the date gate, and the `data/` vs `src/data/` disconnect. Rebase against six days of watcher auto-commits first. | `sync-blocked.json` clears; upcoming view self-heals on hourly rebuild. |
| P0.3 | **Make failure loud.** Add a step to the Pages workflow that opens/updates a single pinned issue on build failure and closes it on success; add a status badge to the README. | A 2-hour outage produces a filed issue without human action. |
| P0.4 | Remove or explicitly label the two fabricated arrest literals in `pages/21_Arrest_Records.py`. Add a protocol carve-out to `READ-FIRST.md`: additive-only protects *content*, never *false published claims*. | No unmarked synthetic record reachable in any deployed surface. |

### P1 — close the control-plane gap (1–4 weeks)

| # | Action | Acceptance criterion |
|---|---|---|
| P1.1 | **Gate `main`.** Path-filtered required checks: skip CI on watcher auto-commit paths (`data/**` artifacts), enforce lint+typecheck+build on source paths and all PRs. | CI runs on every source-touching commit; a red build cannot deploy. |
| P1.2 | **Validate scraped data at the boundary.** JSON Schema for `sync-state.json` / `detected-upcoming.json` / `official-meetings.json`: `date` must parse as ISO-8601, `body` must be an enum, `agendaUrl` must be https and parseable. Reject and quarantine non-conforming values; never write them as keys or paths. | The `"in progress open video only in windows media player"` class of value cannot be committed. Regression test added. |
| P1.3 | **Regenerate `civic_atlas/media/projects.json`** to cover all 14 repos with measured sizes, workflow health, and Pages state. Declare the six `cheyenne-archives-*` repos as *intentional cold storage* with an explicit freshness SLA, or automate them. | Registry row count == live repo count; every row carries a date and evidence link. |
| P1.4 | **Declare one canonical authority.** Resolve cross-identity duplicates: pick canonical for `TheReelWindyCity` and `The-Real-Windy-City-`, mark the others as mirrors in-repo (README banner) or archive them. Fix `AGENTS.md`'s dangling `coordination/` reference — either land PR #25 or point at what exists on `main`. | An agent starting cold can determine canonical repo, owner, and coordination file from `main` alone. |
| P1.5 | **Reconcile `READ-FIRST.md` claim locks.** Move the three stale `active` claims to `done`/`abandoned` with dated notes per the file's own 6-hour rule. | Zero claims simultaneously active and abandoned. |
| P1.6 | **Retire dormant automation.** Delete or explicitly mark the 10 non-running flagship workflows, `V-MAX-Colab-Protocol` (8 months dormant, `node_modules/` in git), `Lint rule locator`, `Integration stage diagnostics`. Address the Node 20 → 24 and `ubuntu-latest` → Ubuntu 26 (2026-10-19) runner migrations *before* they become forced. | Workflow count reflects actual capability; zero deprecation warnings. |

### P2 — structural upgrades (1–3 months)

| # | Action | Rationale |
|---|---|---|
| P2.1 | **Partition the monolith using the pattern already proven.** Move `pipeline/renders/`, `.mp4`, and PDF blobs to GitHub Releases or LFS; keep code + manifests in git. Target <500 MB tracked. | `civic-newsroom/AGENTS.md` already states the rule. The monolith is 1.94 GB and pays for it on every hourly checkout. |
| P2.2 | **Pre-plan `civic-newsroom-intelligence-002`.** Budget is 470.7/512 MiB used. Automate the split trigger rather than discovering it as a terminal `ValueError`. | The 2026-10-26 failure was handled well but reactively. |
| P2.3 | **Index the cold archive.** The 4.17 GB / 18-year PDF corpus is the ecosystem's largest untapped asset and currently has no full-text search, no Pages, no discoverability. OCR + text layer + a search index would convert inert storage into the single largest differentiator against Wayback-style comparables. `ai-record-ocr/` suggests tooling already exists. | Value is locked behind absence of access. |
| P2.4 | **Adopt a standard record envelope.** Map the bespoke publication contract onto **Frictionless Data** or **OCDS** shapes while preserving source-local IDs through adapters (the guide already requires ID preservation). | Interoperability with existing civic tooling; reduces the bespoke-maintenance surface. |
| P2.5 | **Close the retrieval gap deliberately.** `verified_entity_resolution: false` and `source_independence: "unresolved"` are honest but are also the ceiling on analytical value. Add embedding-based retrieval and an explicit, reviewable entity-resolution stage with human sign-off — never automatic accusation, per existing policy. | The 867,452 unreviewed language candidates are signal nobody can currently use. |
| P2.6 | **Build the distribution layer.** Everything terminates in a file, a badge, or a Pages site. No newsletter, no webhook, no RSS-to-reader path for the 303 alerts. Comparables (Documenters, MuckRock) win on reaching people. | Detection without distribution produces evidence nobody reads. |
| P2.7 | **Formalize the three-tier architecture** in `AGENTS.md`: **archive** (monolith + banded PDFs + transcripts, read-only sources) → **app** (TheReelWindyCity front end, Streamlit) → **publication** (civic-newsroom family, hash-pinned). | This is already the de facto design and is stated in `civic-newsroom/AGENTS.md`. Making it explicit ends the parallel-maintenance trajectory. |

---

## PART 5 — PROBABILISTIC OUTCOME MATRIX

| Scenario | 0–3 mo | 3–6 mo | 6–12 mo | Primary driver |
|---|---|---|---|---|
| **A. P0 lands this week** — front end restored, failure made loud, PR #22 merged | **0.55** | 0.45 | 0.35 | Fix is small and precisely located; requires an unrestricted-network session to read the real build log |
| **B. Status quo drift** — outage persists, PRs age, registry stays stale | **0.35** | 0.40 | 0.30 | No owner is assigned by any governing document; watcher silences itself by design |
| **C. Deliberate consolidation** onto `civic-newsroom` architecture; monolith demoted to archive | 0.05 | 0.10 | **0.20** | Architecture is already superior and already documented as the successor |
| **D. Partition-budget cascade** — intelligence corpus exceeds 512 MiB, verified-deploy chain breaks | 0.03 | 0.12 | 0.15 | 3.7% headroom; self-reporting means it will be *visible*, not silent |
| **E. Trust event** — fabricated records or stale "upcoming" meetings surface publicly during a live meeting cycle | 0.07 | 0.08 | 0.10 | Two confirmed defects; 2026-11-02/11-03 committee meetings fall inside the window |
| **F. Wrong-copy edit incident** — an agent modifies a non-canonical same-named repo | 0.10 | 0.15 | 0.20 | 4 cross-identity name collisions; dangling coordination authority; dead claim locks |

*(Probabilities are per-horizon, not a partition; they do not sum to 1.)*

**Highest-leverage single intervention:** P0.1 + P0.3 together. Restoring the build fixes six days of outage; making failure loud is what prevents the *next* six-day outage. P0.1 without P0.3 buys time, not resilience — the identical failure mode recurs on the next unguarded commit to `main`.

---

## PART 6 — [RESEARCH VECTOR]

Items below 95% confidence that require either an unrestricted-network session or an owner-supplied document. **Nothing here was guessed.**

1. `[RESEARCH VECTOR]` **The actual `npm run build` stderr** for `therealwindycity/TheReelWindyCity` run `39703125912` (or any run ≥ that). Actions log download is blocked from this sandbox (`results-receiver.actions.githubusercontent.com` → EOF). Query: retrieve run log from an unrestricted network, or `git clone` + `npm ci && NEXT_PUBLIC_BASE_PATH=/TheReelWindyCity npm run build` locally. *The bisect (`ab8570bf` good → `678193d3` bad) is certain; the apostrophe mechanism is inferred from CI annotations on a different workflow.*
2. `[RESEARCH VECTOR]` **Whether the four Pages URLs and the Streamlit app actually serve**, and what revision. Outbound from this sandbox is github.com-only. Required: HTTP GET of each URL, compared against head SHAs.
3. `[RESEARCH VECTOR]` **Owner decision on cross-identity canonical repos** — which of `bartimoussmith-oss/TheReelWindyCity` vs `therealwindycity/TheReelWindyCity`, and which of the two `The-Real-Windy-City-`, is authoritative. Not inferable from any artifact on `main`.
4. `[RESEARCH VECTOR]` **Whether the six `cheyenne-archives-*` repos are intentionally cold** or accidentally abandoned. 30 days untouched with zero automation is consistent with both. Requires owner statement or a freshness SLA artifact.
5. `[RESEARCH VECTOR]` **Why `Fetch meeting transcripts` last ran `skipped`** (2026-10-23) in `therealwindycity/The-Real-Windy-City-`, and whether five days without transcript ingestion is expected.
6. `[RESEARCH VECTOR]` **Why `Citizen Connect Incident Sync` and `Live Wyoming Watch` are 4/4 failing.** Not inspected in this pass; both are recent additions with small sample sizes.
7. `[RESEARCH VECTOR]` **Owner intent on `pages/21_Arrest_Records.py`.** Remove, label as fiction, or retain? The additive-only protocol was invoked to defer this on 2026-10-18; deferral is now the defect.

---

## PART 7 — SESSION SYNTHESIS

`[KNOWLEDGE BULLET]` **Civic-records monitoring stacks fail in a characteristic, diagnosable pattern, and the pattern is a control-plane gap rather than a code defect.** Observable signature: (a) a watcher automation commits continuously to the default branch, (b) the build/deploy workflow runs on push *and* on a cron, (c) CI is technically configured for the default branch but has run a handful of times lifetime and is red, (d) static-export hosting serves the last successful artifact so the public site stays *up and wrong* rather than down. Consequence: a one-file, one-character-class regression takes the public surface offline for days while every dashboard that matters looks either green or merely busy, and the failure self-silences because the watcher writes a "blocked" marker with a long retry window to avoid notification spam. Diagnostic sequence that resolves it in minutes: enumerate workflow-run conclusions per workflow via `actions/workflows/{id}/runs` (**always check `total_count` — a 60-run sample of all-failures can hide 447 historical successes and invert the conclusion**), bisect last-success → first-failure by `head_sha`, enumerate the failing *step name* per run via `actions/runs/{id}/jobs`, then read `check-runs/{job_id}/annotations` — annotations survive even when the log ZIP endpoint is unreachable, and frequently carry the exact linter/compiler message. Hardening that actually works, in order of leverage: make failure file an issue automatically; path-filter required checks so watcher commits skip CI but source commits cannot bypass it; and JSON-Schema-validate every scraped string before it becomes a typed field, a key, or a directory path. Two adjacent lessons: an unescaped-apostrophe lint rule (`react/no-unescaped-entities`) can be a total-outage vector in a `output: "export"` Next.js app with no server fallback; and in a repo governed by an additive-only protocol, the protocol needs an explicit carve-out, because a rule written to prevent content destruction will otherwise be invoked to preserve a fabricated public record.
