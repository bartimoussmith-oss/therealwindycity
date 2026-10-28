# Architecture tiers — where each kind of data belongs

Written 2026-10-28. Additive documentation; it changes no code and no data.

This repository and the five archive repositories beside it hold four
fundamentally different kinds of material, and they are currently all stored the
same way: as tracked git blobs. That single decision is the root cause of most of
the structural problems measured below. This document names the tiers, states
where each belongs, and records what was measured on 2026-10-28 so the next
person does not have to re-derive it.

---

## The measurement that motivates this

Run `python3 tools/repo_partition.py measure` for current numbers. On
2026-10-28 the figures were:

| Tier | Bytes | Share |
|---|---|---|
| outbound (video, ML weights, database, archive images, renders) | 771.2 MiB | 60.5% |
| review (PDFs, structured data, web assets) | 252.9 MiB | 19.9% |
| resident (documents, code) | 189.7 MiB | 14.9% |
| **tracked total** | **1,213.8 MiB** | 5,597 files |
| `.git` object store | 816 MiB | — |

The five archive repositories hold a further **6,970,150,704 bytes (6.97 GB)**
across 5,140 blobs, measured via the git trees API with `truncated: false` on all
six listings.

**60.5% of this repository's tracked mass should never have been in git.** A
596 MiB body of `.mp4` files contradicts this repository's own committed rule
(claim `miller-tapes`): *"videos stay out of git per repo rule (YouTube +
Releases)."* The rule was right; it was not enforced by anything.

---

## Tier 1 — Resident (belongs in git)

**What:** source code, tests, configuration, prose documentation, small
structured metadata, the coordination ledger (`READ-FIRST.md`).

**Why:** this is the material git exists for. It is text, it is diffable, it is
reviewed line by line, and its history is its value. A reviewer reading a diff of
`engine/capture.py` is doing exactly what the tool is for.

**Boundary test:** *would a reviewer read this as a diff?* If yes, it is resident.

**Current state:** 189.7 MiB, which is itself large for text — driven by
`uploads/mega_file.md` at 25,655,705 bytes and `public/master_meetings_database_linked.json`
at 33,313,552 bytes. Both are misfiled: they are data, not prose, and belong in
tier 2 or 3.

**Enforced by:** `tools/repo_partition.py classify`, which assigns every tracked
path a class and a tier.

---

## Tier 2 — Review (belongs in git, but not as an ordinary blob)

**What:** PDFs of public records, agenda packets, minutes, structured data
exports, web assets that the site renders.

**Why:** these are evidence. They must be citable by an immutable identifier,
retrievable years later, and verifiable byte for byte, because a claim about a
public record that cannot be re-verified is not a claim. Git gives all three —
but only if the blob is content-addressed and the pointer is what moves.

**Boundary test:** *does a published assertion depend on this exact byte string?*
If yes, it needs content addressing. That is what Git LFS provides, and what a
plain tracked blob provides only until someone force-pushes.

**Current state:** 252.9 MiB tracked as ordinary blobs. The archive repositories
add 6.97 GB.

**Enforced by:** `tools/archive_index.py`, which catalogues all 6.97 GB, resolves
a meeting date and municipal body for **5,116 of 5,140 blobs (99.5%)**, and emits
a Frictionless `datapackage.json` so the corpus is describable independently of
git. `tools/repo_partition.py` writes a ready-to-apply `.gitattributes` LFS
mapping.

**Open item, owner decision required:** moving 6.97 GB to LFS or to object
storage needs either a history rewrite or `git rm` plus re-add. Both are forbidden
by `READ-FIRST.md` without the owner's explicit instruction. The tooling is
shipped and tested; the decision is not the agent's to make.

---

## Tier 3 — Outbound (does not belong in git at all)

**What:** video, audio, ML weights, database files, archive images, renders.

**Why:** these are large, binary, and not diffable. Git stores each new version as
a whole new blob, so a re-render costs the full file size every time. They have
better homes that already exist in this ecosystem's stated policy:

| Class | Bytes | Home |
|---|---|---|
| video (44 files) | 568.4 MiB | YouTube + GitHub Releases (per the `miller-tapes` rule) |
| ml-model (5 files) | 88.9 MiB | Releases, or the publishing host that already serves them |
| database (4 files) | 83.5 MiB | Object storage, partitioned |
| archive-image (2 files) | 30.3 MiB | Object storage or Releases |
| render (20 files) | ~0 MiB | Regenerated on demand; never stored |

**Boundary test:** *can this be regenerated or re-downloaded, and is it
non-textual?* If yes, it is outbound.

**Enforced by:** `tools/repo_partition.py bundle`, which writes a
`MIGRATION.md` with the exact commands and an ordered plan, and
`tools/intelligence_budget.py plan`, which computes how a published corpus splits
across hosts.

**Duplicate waste measured:** 584 duplicate groups consuming **51.6 MiB**. The
two material ones: `video/gaveled-down-miller-montage.mp4` and
`videos/gaveled-down-miller-montage.mp4` are byte-identical at 24,770,554 bytes
each — **23.6 MiB of pure waste from a directory-name plural**. The other 582
groups total 27.7 MiB.

---

## Tier 4 — Derived (must never be committed)

**What:** vector stores, embedding matrices, BM25 shards, search indices,
partition manifests, budget reports, triage output, digests, feed files, email
drafts.

**Why:** every one of these is reproducible from tiers 1–3. Committing them makes
the repository larger, makes merges conflict on generated content, and — the real
danger — makes a stale artifact indistinguishable from a fresh one. A committed
index that predates the documents it indexes returns confident wrong answers.

**Boundary test:** *can this be rebuilt by running a command?* If yes, it is
derived and it is gitignored.

**Current state, all gitignored as of 2026-10-28:**

| Path | Produced by | Rebuild command |
|---|---|---|
| `data/archive-index/` | `tools/archive_index.py` | `catalog` → `extract` → `index` |
| `data/retrieval/` | `tools/semantic_retrieval.py` | `embed` (≈61 s for 1,217 passages) |
| `data/partition/` | `tools/repo_partition.py` | `measure` |
| `data/intelligence-budget/` | `tools/intelligence_budget.py` | `audit` |
| `data/distribution/` | `tools/distribution_publish.py` | `publish` |
| `data/selftest/` | existing | existing |
| `rag/vectordb/` | existing | existing |

`rag/vectordb_sample/chroma.sqlite3` (23.4 MB, 1,687 chunks) is committed and is
tier 4 material. It is not deleted here — `READ-FIRST.md` forbids removing content
this session did not create — but it is recorded as misfiled.

---

## Cross-cutting invariants

These hold regardless of tier, and every tool in this repository is written to
respect them.

**1. Nothing rewrites history.** No tool built here runs `git filter-branch`,
`git filter-repo`, `git rm`, `git push --force`, or any history-altering command.
Reclaiming the 771.2 MiB of outbound mass requires one of those, and that is an
owner decision. The tools measure, plan and emit exact commands instead.

**2. Nothing writes to another repository.** `tools/intelligence_budget.py` is
strictly read-only across repositories and records `read_only: true` plus a scope
statement in every report. `AGENTS.md` requires explicit approval for
cross-repository writes and deployments; no approval was given, so none was taken.

**3. Every retrieval result carries its provenance.** A hit without a source URL,
a verbatim path, a capture timestamp and a character span cannot be verified, and
an unverifiable citation is worse than no citation. `tools/archive_index.py` and
`tools/semantic_retrieval.py` both emit `raw_url`, `github_url`, `repository`,
`path`, `meeting_date`, `document_class` and `char_span` on every hit.

**4. Absence of a hit is never evidence of absence.** Both search tools print this
warning on every result set, because partial coverage plus a confident negative is
how a researcher concludes a record does not exist.

**5. Ambiguity is flagged, never silently resolved.** 215 dates in the archive are
ambiguous (both components ≤ 12), 431 carry two-digit years, and 7 have genuine
intra-path conflicts. All are recorded per-record as `date_ambiguous`,
`two_digit_year` and `date_conflict`. None were guessed at.

**6. A candidate is never an assertion.** `tools/semantic_retrieval.py candidates`
emits an entity-resolution review queue in which every row carries
`status: candidate-unreviewed` and an explicit statement that no two candidates
are merged and nothing alleges wrongdoing. Merging entities is a human decision,
and `source_independence` in the published intelligence corpus remains
`"unresolved"` — so support counts are triage order, not corroboration.

**7. Failures are loud, not quiet.** `tools/intelligence_budget.py` exits 3 on an
exhausted or unverified budget and 4 on a fetch failure or zero audited hosts,
**including under `--quiet`** — because a gate that reports success for a run that
audited nothing is worse than no gate. This was a real defect, found and fixed:
the fetch-error check originally sat inside the non-quiet branch.

**8. Derived artifacts record what produced them.** The embedding store records the
model's SHA-256 and refuses to load if the passage count and matrix rows disagree,
because mismatched stores attach the wrong citation to every hit.

---

## Capability tiers (what the ecosystem can actually do)

Separate from storage tiers, because the two are conflated in the current layout.

| Capability | State | Where |
|---|---|---|
| Capture of public records | working | `engine/` |
| Change detection after publication | **degraded — see below** | `engine/`, `data/engine.db` |
| Cold-archive inventory and dating | working, 99.5% coverage | `tools/archive_index.py` |
| Full-text search over the archive | working, 183 of 5,140 docs | `tools/archive_index.py index/search` |
| Semantic search over the archive | working, 1,217 passages | `tools/semantic_retrieval.py` |
| Lexical + semantic fusion | working (RRF, k=60) | `--fuse-bm25`, matches `rag/query.py` |
| Entity resolution | **not built — queue only** | `tools/semantic_retrieval.py candidates` |
| Distribution to a human | working, drafts and feeds only | `tools/distribution_publish.py` |
| Automated outbound contact | **forbidden by LEGAL.md §4** | — |
| Budget/exhaustion forecasting | working, live-verified | `tools/intelligence_budget.py` |

### The change-detection finding

Silent-edit detection is the capability this ecosystem has that its comparables do
not: it re-fetches a published document and reports that it changed after
publication. Measured against the live ledger on 2026-10-28:

- 303 alerts total; 225 are `SILENT-EDIT`.
- **205 of 225 (91.11%) are page-assembly changes, not editorial changes.**
- 19 are uncertain.
- **1 carries possible editorial signal.**

The 205 break down into classes, each observed verbatim:

| Class | Evidence |
|---|---|
| WordPress asset cache-busters | `block_styles.css?ver=4.36.3` → `?ver=4.36.5` |
| Delayed-style timestamps | `data-pmdelayedstyle=…?ver=1793030792` → `1793050624` |
| Akamai mPulse RUM beacons | `s.go-mpulse.net/boomerang`, `BOOMR_config` |
| Inline polyfill JavaScript | `document.createElement`, `window.addEventListener` |
| core-js exception text | `The this value for String.prototype.includes must not be null or undefined` |
| Newsletter/signup widget | `Do you have email set up? You may need to create a new email yourself.` |
| Related-articles rail | one headline recurring across 21 unrelated articles |
| Tracking configuration | `ppconfig={…deleteIsEnforced…sealIsEnforced…}`, recurred 35× |
| Social-share widget | `data-email-share-error-title`, recurred 21× |

Affected pages include obituaries, an opinion column, arrest reports, weather
stories and high-school sports coverage. The detector compares **raw HTML**, so
any change to site-wide chrome fires an alert on every page of the domain
simultaneously.

The consequence is not cosmetic. A feed containing 225 "document changed after
publication" alerts, of which 205 are a plugin version bump, trains every reader
to ignore the feed — including on the one day it reports a real change.
`tools/distribution_publish.py` therefore triages before it publishes, and
publishes the noise floor alongside the signal so the figure is auditable rather
than hidden.

**Root-cause fix, not in scope for this session:** the detector must diff
extracted article content, not raw HTML. `engine/` is outside the claimed scope
(`READ-FIRST.md` forbids touching it without an active claim naming it), so the
fix is recorded here rather than applied. The triage layer is a compensating
control, not a repair.

---

## What this document does not do

- It does not delete, move or rewrite anything.
- It does not claim that any migration has happened. Every figure above is a
  measurement of the state on 2026-10-28, reproducible by the named command.
- It does not assert that the 1 remaining signal alert is a real editorial change.
  It is classified `signal` because its residue is not explained by scaffolding,
  chrome or code — which is a statement about the residue, not about intent.
- It does not resolve the entity candidates. No two names are merged anywhere in
  this document or in the tooling.
- It does not verify any live deployment. No public URL, Pages response or
  search-index state could be reached from the environment in which this was
  written.
