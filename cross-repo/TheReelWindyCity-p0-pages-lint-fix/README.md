# P0 — `therealwindycity/TheReelWindyCity` GitHub Pages has served a stale build for six days

Prepared 2026-10-28. This directory holds a verified fix for a **different
repository**. It is staged here because the session that produced it cannot write
to the target.

## Status

| | |
|---|---|
| Defect confirmed | yes, against live Actions data and file contents |
| Fix built and verified | yes — `git apply --check` passes against `main@0abfb6c6` |
| Fix landed on target | **NO** |
| Site restored | **NO** |
| Blocking reason | write access to `therealwindycity/TheReelWindyCity` is denied |

## The outage

`Deploy to GitHub Pages` (workflow `373915805`) has failed **45 consecutive
runs**. Last success `2026-10-22T00:51:54Z` at head `ab8570bf`. Newest run at
time of writing: `2026-10-28T05:38:49Z`, head `6e90b60e`, conclusion `failure`.
`total_count=567`, of which 447 succeeded historically.

The failing step is **`Build static site`** (`npm run build`). The `deploy` job
has `needs: build`, so it is skipped every time. Pages is enabled
(`build_type: workflow`, `public: true`, `https_enforced: true`) and therefore
keeps serving the last successfully uploaded artifact.

**The site is up and wrong.** It renders the `ab8570bf` build, six days behind,
while 45 red runs accumulate.

## Root cause

`react/no-unescaped-entities` violations — unescaped apostrophes in JSX text.
Confirmed from CI annotations verbatim, not inferred:

```
[.github:44]                                  `'` can be escaped with `&apos;`, ...
[src/app/page.tsx:7]                          `'` can be escaped with `&apos;`, ...
[src/app/page.tsx:7]                          `'` can be escaped with `&apos;`, ...
[src/app/page.tsx:6]                          `'` can be escaped with `&apos;`, ...
[src/app/explore/public-safety/page.tsx:7]    `'` can be escaped with `&apos;`, ...
```

The five sites:

| File:line | Text | Origin |
|---|---|---|
| `src/components/site-help.tsx:44` | `Messages stay in this page's memory` | `678193d3` |
| `src/app/page.tsx:6` | `What's happening?` | pre-existing |
| `src/app/page.tsx:7` | `What's happening in your community` | pre-existing |
| `src/app/page.tsx:7` | `Check each publisher's date` | pre-existing |
| `src/app/explore/public-safety/page.tsx:7` | `separate from the homepage's local-information overview` | pre-existing |

Introduced by `678193d3` *"Add dismissible site-wide navigation help popup"*
(+48/−1: `src/app/template.tsx`, new `src/components/site-help.module.css`,
`site-help.tsx` +47).

## The part that matters more than the typo

Four of the five violations were **already on `main` before the outage** and did
not break Pages. CI lint went red on them from `2026-10-22T00:48Z` onward — at
heads `195acc55`, `4393777f`, `ab8570bf` — and **Pages deployed successfully at
`ab8570bf` anyway.**

The reason is in `next.config.ts`, which sets no `eslint` key at all. `next build`
therefore lints only Next's default directories (`app`, `pages`, `components`),
and with the project's `src/` layout that means `src/app/` violations never reach
the build's lint pass. Pages only broke once the same class of violation landed in
`src/components/site-help.tsx`.

So the ecosystem had a comprehensive CI workflow — lint, typecheck, 11 test
suites, build, SEO audit, Playwright smoke, triggered on `pull_request` and
`push: [main, "arena/**"]` — running red on `main` for six days while the public
site deployed on a schedule. **A red gate that does not gate the artifact being
published is not a gate.**

Two structural facts make this worse:

- `deploy-pages.yml` runs **hourly on cron** (`17 * * * *`) as well as on every
  push to `main`. An unlinted commit is republished every hour with nobody
  watching.
- `repos/{repo}/rulesets` returns `[]` — no rulesets. The branch-protection
  endpoint returns `403 Resource not accessible by integration`, so whether
  required status checks exist **could not be verified**. 24 CI runs on `main`,
  many red, with commits continuing to land, is consistent with no enforcement.

## The fix

`0001-p0-pages-lint-fix.patch` — a `git am` patch, 4 files, **+21/−4**.

1. Escapes the five apostrophes as `&apos;`. Rendered output is unchanged: JSX
   decodes the entity back to an apostrophe, so markup, SEO surface and
   reader-visible text are identical.
2. Adds a whole-repo lint gate to `deploy-pages.yml` between `npm ci` and the
   data-sync steps, so a violation fails the build before anything is uploaded or
   deployed.

`src/app/mynewspace/page.tsx:68` also contains an apostrophe
(`Cheyenne's public record, blurbed`) and is **deliberately not touched** — it is
a JavaScript template literal inside `export const metadata`, where an apostrophe
is correct. Escaping it would corrupt the page title. An earlier automated scan
flagged it; reading the file ruled it out.

## Verification performed

- `git apply --check` passes against the exact `main@0abfb6c6` contents of all
  four files, fetched through `api.github.com`.
- `git am` applies cleanly; each of the five escape sites asserted to occur
  exactly once, so no over-broad replacement.
- Asserted that removing the inserted workflow block reproduces the original
  `deploy-pages.yml` byte for byte — nothing else changed.
- YAML parses; step order is checkout → setup-node → `npm ci` → **lint gate** →
  cache → data syncs → configure-pages → build → upload artifact.
- `deploy` retains `needs: build` and the `github.ref == 'refs/heads/main'` guard;
  hourly cron and artifact upload intact.
- Patch touches exactly 4 files; `mynewspace` is not among them.

## Verification NOT performed

- **No `npm run lint` or `npm run build` was executed.** `npm ci` for this project
  cannot complete in the authoring sandbox (2 CPUs, 3.9 GB RAM). The escape set is
  taken from CI's own annotations, which is strong, but it is not a local green
  run.
- No public URL, Pages HTTP response or browser rendering was checked.
  `therealwindycity.streamlit.app`, `share.streamlit.io` and
  `bartimoussmith-oss.github.io` are all unreachable from the sandbox (TLS closed);
  only `api.github.com` works.
- Whether required status checks are configured on the target's `main` is unknown
  (403).

If lint surfaces violations beyond these five, the new gate will report them on
the first run — which is the gate working, not a regression.

## How to apply

```bash
cd cross-repo/TheReelWindyCity-p0-pages-lint-fix
bash apply.sh
```

Clones the target, applies the patch on branch `arena/p0-pages-lint-fix`, runs
`npm ci && npm run lint` locally if the toolchain is available, pushes, and opens
a PR. It never pushes to `main` directly and never force-pushes. Use
`TARGET_DIR=/path/to/checkout bash apply.sh` against an existing checkout.

## How to confirm it actually worked

Do not treat a merged PR as a restored site.

```bash
# 1. a Pages run must reach conclusion=success at the new head
gh api "repos/therealwindycity/TheReelWindyCity/actions/workflows/373915805/runs?per_page=3" \
  --jq '.workflow_runs[] | "\(.created_at) \(.conclusion) head=\(.head_sha[0:8])"'

# 2. the deploy job must no longer be skipped
gh api "repos/therealwindycity/TheReelWindyCity/actions/runs/{RUN_ID}/jobs" \
  --jq '.jobs[] | "\(.name) \(.conclusion)"'

# 3. the published sitemap check must pass (scripts/check-live-seo.mjs runs in deploy)

# 4. from a machine that can reach the public internet, confirm the live page
#    serves the fixed markup and a current build
curl -s https://therealwindycity.github.io/TheReelWindyCity/ | grep -c "What's happening"
```

Only steps 1–4 together mean deployed. Until then the correct description is
**fix prepared, not landed**.
