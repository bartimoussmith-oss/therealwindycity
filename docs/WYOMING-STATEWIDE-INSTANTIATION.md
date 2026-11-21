# Instantiating the Cheyenne Ecosystem Across Wyoming

- **Date:** 2026-11-06 (America/Denver)
- **What this covers:** `wyoming/registry.json`, generated `wyoming/instances/*`, the
  generator (`tools/wyoming_instantiate.py`), the live verifier (`tools/wyoming_verify.py`),
  the runner (`wyoming/run-instance.sh`), the CI gate (`.github/workflows/wyoming-verify.yml`),
  and the minimal engine portability shims (`ENGINE_CONFIG_DIR`, `ENGINE_DATA_DIR`, `ENGINE_PUBLIC_DIR`).

## The short version

Every incorporated municipality (99), all 23 county governments, and the principal
state-level bodies (Legislature, Governor, Secretary of State, Attorney General) now
have their own instance of the full Cheyenne ecosystem: watchlist-driven ingestion,
SHA-256 silent-edit detection, PRA drafting, digest generation, and the static ledger
site. Instances share **one** engine in `engine/` — they are configuration, not forks —
and each runs against its own database and output directory.

```bash
wyoming/run-instance.sh casper init      # create Casper's ledger
wyoming/run-instance.sh casper crawl     # pull ENABLED sources only (none are, until verified)
wyoming/run-instance.sh laramie-county digest
wyoming/run-instance.sh wyoming-legislature request pra "..." "2026-01-01 to present"
```

## Coverage

| Tier | Count | Slugs |
|---|---|---|
| State-level bodies | 4 | `wyoming-legislature`, `wyoming-governor`, `wyoming-secretary-of-state`, `wyoming-attorney-general` |
| Counties | 23 | `albany-county` … `weston-county` (all 23; county seat recorded in each registry row) |
| Municipalities | 99 | the complete 2020-Census incorporation list — 19 first-class cities (Wyo. Stat. Title 15) and 80 towns |
| **Total instances** | **126** | `wyoming/registry.json` → `jurisdictions[]` |

Municipality names, types, counties and 2020 populations were transcribed from the
2020 Census incorporation list and cross-checked 2026-11-06. The test suite asserts the
population column sums to the Census total (398,304) and that all 23 counties and 19
first-class cities are present. Reconcile the roster against the Wyoming Secretary of
State's current incorporation list before relying on it legally; incorporations and
dissolutions happen.

### What "other form of government" is (and is not) covered

Covered: state legislative and principal executive offices; every county's Board of
County Commissioners; every incorporated city/town council/board.

Not enumerated: Wyoming's dozens of school districts, conservation districts, hospital
districts, irrigation/improvement districts and other special districts. Their URLs
cannot be verified from this checkout, and inventing 200+ candidate domains would be
fabrication, not coverage. The machinery is ready for them: add one row per district to
`wyoming/registry.json` (`type: "special-district"` or `"school-district"`), rerun
`python3 tools/wyoming_instantiate.py --write`, and the verifier will probe them like
any other jurisdiction. That is a deliberate gap-with-a-door, not a hidden ceiling.

## Architecture

```
wyoming/registry.json            the source of truth (all 126 jurisdictions)
tools/wyoming_instantiate.py     renders wyoming/instances/<slug>/ offline, deterministically
tools/wyoming_verify.py          live prober: robots.txt → fetch → platform fingerprint → agenda-path probe → --apply
tools/test_wyoming_instantiate.py  offline integrity tests (20 tests)
wyoming/instances/<slug>/
  config/sources.json            sources, ALL disabled until live-verified
  config/watchlist.json          statewide energy/water/procedural-integrity terms + jurisdiction terms
  config/facts.json              site shell; NO local lore (owner adds it)
  ecosystem.json                 machine metadata + candidate domains
  env.sh                         custodian placeholders (UNVERIFIED by design)
  README.md                      per-instance runbook
data/wyoming/<slug>/             per-instance SQLite ledger (git-ignored)
public/wyoming/<slug>/           per-instance rendered site (git-ignored)
```

Engine portability is env-driven and default-identical to before:
`ENGINE_CONFIG_DIR` (sources/watchlist/facts), `ENGINE_DATA_DIR` (snapshots/db/out),
`ENGINE_PUBLIC_DIR` (rendered site), `ENGINE_CUSTODIAN_OFFICE` / `ENGINE_CUSTODIAN_ADDRESS` /
`ENGINE_WARD_OR_AREA` (PRA/comment drafting). The root Cheyenne configuration is untouched,
and `engine/publish.py` renders the root site byte-identically (verified).

## Platform heterogeneity — "even if their systems don't match Cheyenne's"

The Cheyenne build works against plain HTML/RSS + a document-link filter; it does not
depend on Granicus or any other vendor. That was deliberate and it is what makes
instantiation workable for towns that have *no* detectable stack:

1. **Detectable structured platforms** (Granicus, CivicPlus/WebTrack AgendaCenter, IQM2,
   Legistar, Municode, WordPress, Drupal) are fingerprinted by the verifier; the agenda/
   minutes path, when it answers 200 with agenda-like keywords, becomes an enabled
   `<slug>_agendas` source automatically.
2. **WordPress towns** get `/feed`-style RSS detection for free from the platform fingerprint.
3. **No detectable stack / minimal town** — the engine still functions end-to-end:
   PRA drafting (the tool works regardless of the town's systems), digest with true-quiet
   reporting, silent-edit detection on any public pages you enable manually, and the
   statewide news-search RSS filtered by the jurisdiction's name (rate-limit caveat noted).
4. **Non-web jurisdictions** — a town with no website is still a ledger: enable nothing,
   draft PRAs, file them by post, and let `data/wyoming/<slug>/` fill with whatever public
   records you obtain. The README in each instance says exactly this.

Granicus portals (cheyenne.granicus.com and equivalents) are **not** auto-enabled: their
robots.txt disallows crawling in the Cheyenne case, the verifier refuses them when robots
disallow, and the PRA/browser-download path is the lawful route, exactly as in the root build.

## Verification lifecycle (the "success" half of "creation and success")

```
registry.json  ──generate──▶  instances (all sources disabled, verification="unverified")
                                   │
                       weekly wyoming-verify.yml sweep (or manual run)
                                   │
              candidates probed politely ──▶ verification.json committed per instance
                                   │
              live-verified hosts ──--apply──▶ sources.json re-rendered with enables — deterministically
                                   │
              human opens URLs, confirms official-ness, edits env.sh custodian, adds local lore to facts.json
```

`wyoming-verify.yml` runs the offline tests on every relevant change; the weekly sweep runs
Mondays 11:23 UTC and commits only what it genuinely verified. It never enables a source
that did not answer 200, never overrides robots.txt, and records its uncertainty in
`verification.json` — including "probe may be blocked, rate-limited, or sandboxed," because
*unreachable* is not the same claim as *does not exist*.

## Honesty contract (non-negotiable, inherited from the root build)

- Generated instances assert **nothing** about any government until documents back them.
- Empty `timeline`, no `question_of_the_week`, zero enabled sources: a true starting state.
- Every emitted claim carries a verbatim quote + source URL + fetch timestamp (LEGAL.md).
- No people are named in watchlists; official-capacity content only.
- Local lore (the Cheyenne timeline, Ordinance No. 4687, etc.) stays in the root Cheyenne
  build. New instances get empty canvases and the owner paints them.
- `tools/wyoming_instantiate.py --check` is the integrity gate: committed instances must
  equal generator output from the committed registry. Verification state flows *through* the
  generator (committed `verification.json` is an input), so an applied sweep stays green.

## Limitations and known-unknowns

- **URLs are unverified by construction.** They are candidates, chosen conservatively.
  Expect the weekly sweep to enable a minority in week one; expect humans to hand-correct
  the rest. That is the designed workflow, not a defect.
- **Platform fingerprints are heuristics**, not contracts. A 200 with "agenda" in the body
  proves fetchability, not official-ness. Humans confirm before reliance.
- **Sanctions/home-rule heterogeneity**: Wyoming counties and towns run everything from
  one-page sites to CivicPlus to Granicus to nothing. Some towns will always require manual
  onboarding; the tool marks rather than hides that.
- **School districts and special districts** are an added row away, not yet added.
- **Population/type data** is 2020 Census; types (city/town) follow Wyo. Stat. Title 15
  as reflected in the Census list. East Thermopolis is catalogued separately from
  Thermopolis as the 2020 Census lists them (both incorporated).

## Adding or correcting a jurisdiction

1. Edit `wyoming/registry.json` (add/fix the row; keep `counts` in sync — the loader validates it).
2. `python3 tools/wyoming_instantiate.py --write && python3 tools/test_wyoming_instantiate.py`
3. Commit the registry, the regenerated instances, and this file's numbers if the count changed.
4. For districts: `type: "school-district"` or `"special-district"`; extend `candidate_domains`
   in `tools/wyoming_instantiate.py` if you know the district site patterns.

## Legality

LEGAL.md applies to every instance: public documents only; robots.txt honored; ≥3s per host;
≤40 docs per source per run; drafts are drafts, humans send; no personal data in watchlists.
The verifier is one polite fetch per candidate plus agenda-path probes on a host that
already answered — never a crawl. Wyo. Stat. §§ 16-4-201 to 16-4-205 (Wyoming Public Records
Act) is the correct citation statewide; FOIA is federal and the root build says so, in writing.

## Operating the sweep — dispatch, permissions, and the 403 case

> **Repair gate landed (2026-11-06):** PR #28 (`repair/statewide-activation-safety-2026-11-06`)
> is MERGED. The sweep now requires offline integrity tests before live sweeps, never commits on
> reports-only dispatches, stages only `verification.json` + `config/sources.json` (globs), pushes
> only from `main` and fails rather than auto-rebasing on concurrent-update conflicts, and
> `pages/21_Arrest_Records.py` labels its synthetic literals as fiction. Remaining known-gaps
> (verifier official-site authentication, robots.txt failure behavior, durable per-instance
> overrides, contact placeholders, custodians, local facts) are still open — nothing about
> statewide operation is verified live until the first sweep completes and you read the results.


The workflow is `wyoming-verify` (`.github/workflows/wyoming-verify.yml`). It runs
automatically **every Monday 11:23 UTC** on the default branch — no button required.
It only ever runs from the default branch (schedule never fires on PRs/feature branches).

Manual triggers:

```bash
# one jurisdiction first (recommended)
gh workflow run wyoming-verify.yml -f slug=casper -f apply=true

# full sweep
gh workflow run wyoming-verify.yml -f apply=true

# report-only, enables nothing
gh workflow run wyoming-verify.yml -f apply=false

# watch it
gh run list --workflow wyoming-verify.yml --limit 3
gh run watch <run-id>
```

**Known failure: `Resource not accessible by integration` (HTTP 403).** If your
automation token (CI/agent) cannot call the dispatches endpoint, the token lacks Actions
write access. This is a permissions problem, not a workflow problem: the workflow is
registered and `active`. Workarounds, in order of preference:

1. Run it from the **Actions tab** in a browser: `Actions → wyoming-verify → Run workflow`.
2. Run it from a machine with your own credentials: `gh workflow run wyoming-verify.yml -f slug=casper -f apply=true`.
3. Grant the automation token the `actions: write` permission on this repository.
4. Do nothing — the weekly schedule runs it for you.

A 200 with agenda/minutes keywords enables a source; anything else stays disabled.
Read a jurisdiction's result with:

```bash
git pull
cat wyoming/instances/<slug>/verification.json
```

Note: the sweep's auto-commit excludes `env.sh` by design (custodian placeholders are
always human-confirmed), and commits carry `[skip ci]`.
