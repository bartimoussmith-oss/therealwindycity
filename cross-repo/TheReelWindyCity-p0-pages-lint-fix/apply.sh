#!/usr/bin/env bash
# Apply the P0 GitHub Pages fix to therealwindycity/TheReelWindyCity.
#
# WHY THIS IS A SCRIPT AND NOT A LANDED COMMIT
#   The agent session that produced this patch can read therealwindycity/
#   TheReelWindyCity through api.github.com but cannot write to it: contents PUT,
#   git/blobs and git/refs all return 403 "Resource not accessible by integration"
#   even though the token reports push=true on that repository. AGENTS.md also
#   requires explicit approval for cross-repository writes. So the change is
#   shipped as a verified patch plus this applier, per the constraint recorded in
#   READ-FIRST.md claim p2-ecosystem-upgrades.
#
# WHAT IT DOES
#   Clones the target repo, applies the patch on a branch, pushes it and opens a
#   pull request. It never pushes to main directly and never force-pushes.
#
# USAGE
#   bash apply.sh                      # clone into ./TheReelWindyCity, push, open PR
#   TARGET_DIR=/path/to/checkout bash apply.sh   # use an existing checkout
#
# REQUIREMENTS
#   gh authenticated with push access to therealwindycity/TheReelWindyCity, and
#   network reachability to github.com (not just api.github.com).
set -euo pipefail

REPO="therealwindycity/TheReelWindyCity"
BRANCH="arena/p0-pages-lint-fix"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATCH="$HERE/0001-p0-pages-lint-fix.patch"
TARGET_DIR="${TARGET_DIR:-$HERE/TheReelWindyCity}"

[ -f "$PATCH" ] || { echo "missing patch: $PATCH" >&2; exit 1; }

# The patch was built against this exact commit. Applying to a later main can
# still succeed, but if it does not, that is information, not something to force.
BUILT_AGAINST="0abfb6c6abe2"
echo "patch built against ${REPO}@${BUILT_AGAINST}"

if [ -d "$TARGET_DIR/.git" ]; then
  echo "using existing checkout: $TARGET_DIR"
  cd "$TARGET_DIR"
  git fetch origin main
else
  echo "cloning $REPO -> $TARGET_DIR"
  git clone "https://github.com/$REPO.git" "$TARGET_DIR"
  cd "$TARGET_DIR"
fi

CURRENT_MAIN="$(git rev-parse origin/main)"
echo "origin/main is now ${CURRENT_MAIN:0:12}"
if [ "${CURRENT_MAIN:0:12}" != "$BUILT_AGAINST" ]; then
  echo "NOTE: main has moved since the patch was prepared."
  echo "      git am uses context, so it may still apply cleanly. If it does not,"
  echo "      re-derive the five escape sites rather than forcing the patch."
fi

git checkout -B "$BRANCH" origin/main
if git am --3way "$PATCH"; then
  echo "patch applied"
else
  echo "git am failed. Aborting without touching main." >&2
  git am --abort || true
  exit 1
fi

# Local gate: run the same lint the workflow now runs, if the toolchain is there.
if [ -d node_modules ] || command -v npm >/dev/null 2>&1; then
  echo "installing dependencies and running lint locally"
  npm ci
  npm run lint
else
  echo "npm unavailable; skipping local lint. The Pages workflow is the real check."
fi

git push -u origin "$BRANCH"
gh pr create --repo "$REPO" --base main --head "$BRANCH" \
  --title "Fix react/no-unescaped-entities violations and gate deployment on lint" \
  --body "$(cat <<'EOF'
Restores GitHub Pages, which has served a stale build since 2026-10-22T00:51:54Z (head `ab8570bf`). 45 consecutive Pages runs failed at **Build static site** with the deploy step skipped, so the public site stayed up but six days behind.

## The five escape sites

Confirmed from CI annotations, not assumed:

| File:line | Text |
|---|---|
| `src/components/site-help.tsx:44` | `page's` (introduced by `678193d3`) |
| `src/app/page.tsx:6` | `What's` |
| `src/app/page.tsx:7` | `What's` |
| `src/app/page.tsx:7` | `publisher's` |
| `src/app/explore/public-safety/page.tsx:7` | `homepage's` |

Rendered output is unchanged — JSX decodes `&apos;` back to an apostrophe, so markup, the SEO surface and reader-visible text are identical.

`src/app/mynewspace/page.tsx:68` also contains an apostrophe and is **deliberately left alone**: it is a JavaScript template literal inside `export const metadata`, where an apostrophe is correct. Escaping it would corrupt the page title.

## Why the workflow change belongs in the same PR

`next.config.ts` sets no `eslint.eslintDirs`, so `next build` lints only Next's default dirs (`app`, `pages`, `components`). Violations under `src/app/` therefore did **not** fail the Pages build.

The evidence: CI lint went red on `src/app/page.tsx` and `src/app/explore/public-safety/page.tsx` from `2026-10-22T00:48Z` onward **while Pages kept deploying successfully**. Pages only broke once the same class of violation landed in `src/components/`. A red gate that does not gate the artifact being published is not a gate.

`deploy-pages.yml` now runs the whole-repo eslint pass between `npm ci` and the data-sync steps. This matters more than it looks: the workflow runs hourly on cron as well as on every push to `main`, so an unlinted commit was being republished every hour with nobody watching.

## Verified

YAML parses; step order is checkout → setup-node → `npm ci` → **lint gate** → cache → data syncs → configure-pages → build → upload artifact; `deploy` retains `needs: build` and the `github.ref == 'refs/heads/main'` guard; hourly cron intact; removing the inserted block reproduces the original workflow byte for byte. Each of the five sites was asserted to occur exactly once, and the edits were verified to change nothing except those apostrophes. `git apply --check` passes against `main@0abfb6c6`.

## Not verified

No build or lint run was executed by the authoring agent — `npm ci` for this project could not complete in that sandbox. The authoritative check is this workflow turning green on `main`.
EOF
)"
echo "PR opened against $REPO"
