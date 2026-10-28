# Agent entry point

Read READ-FIRST.md and repository-specific instructions before editing. AGENT.md documents the local runtime; this file does not replace it.

Read docs/ECOSYSTEM-AGENT-GUIDE.md and civic_atlas/media/projects.json for the shared project inventory, evidence states, dependencies and acceptance gates. The browser view is civic_atlas/media/projects.html. These are dated observations, not live monitoring. Recheck branches, open PRs, checks and public endpoints before acting.

Coordinate with the existing therealwindycity/TheReelWindyCity integration work: PR #25, branch arena/civic-build-center-2026-10-21, docs/agent-coordination.md and coordination/tasks.json. That guide is branch-scoped; do not claim it is on main or overwrite its registry. No coordinator or task owner is assigned by this document.

Preserve source archives and privacy boundaries. No private content, credentials, unreviewed personal information or private repository inventory in public artifacts. Do not call a task complete because files exist or a PR merged. Record source, test, deployment and runtime evidence separately. Claim a bounded scope with the human coordinator before overlapping edits. New cross-repository writes and deployments require explicit approval.

## Storage tiers and derived artifacts (added 2026-10-28)

Four tiers of material live in this ecosystem, and conflating them is the root cause of most structural problems here. `docs/ARCHITECTURE-TIERS.md` is the full statement; this is the binding summary.

1. **Resident** — code, tests, prose, small metadata. Belongs in git as ordinary blobs. Test: *would a reviewer read this as a diff?*
2. **Review** — PDFs of public records and structured exports that a published assertion depends on. Belongs in git, but needs content addressing (LFS) rather than plain tracked blobs. Test: *does a published claim depend on this exact byte string?*
3. **Outbound** — video, audio, ML weights, databases, archive images, renders. Does not belong in git. Homes already exist: YouTube and GitHub Releases for video, object storage for databases, regeneration for renders. Test: *is it non-textual and reproducible or re-downloadable?*
4. **Derived** — indices, vector stores, embedding matrices, partition manifests, budget reports, triage output, digests, feed files, email drafts. Must never be committed. Every path under `data/` produced by a `tools/` script is gitignored. Test: *can it be rebuilt by running a command?*

Measured 2026-10-28: 1,213.8 MiB tracked in this repository, of which 771.2 MiB (60.5%) is outbound material, plus 51.6 MiB of exact duplicates. The five `cheyenne-archives-*` repositories hold 6,970,150,704 bytes across 5,140 blobs, fully enumerable via the trees API with `truncated=false`.

Invariants that bind every agent and every tool in this ecosystem:

- Nothing rewrites history. No `filter-branch`, `filter-repo`, `git rm` of tracked media, or force-push. Reclaiming outbound mass requires one of those and is an owner decision. Tools measure, plan and emit exact commands instead.
- Nothing writes to another repository without explicit approval, which `AGENTS.md` already requires. `tools/intelligence_budget.py` is strictly read-only cross-repository and records `read_only: true` in every report.
- Every retrieval result carries provenance: source URL, verbatim path, repository, capture timestamp and character span. An unverifiable citation is worse than no citation.
- Absence of a hit is never evidence of absence, and both search tools print that warning on every result set.
- Ambiguity is flagged per record, never silently resolved. Dates that could be read two ways, two-digit years and intra-path date conflicts are all recorded as flags.
- A candidate is never an assertion. Entity-resolution output carries `status: candidate-unreviewed`, never merges two candidates, and never alleges wrongdoing.
- Failures are loud. A gate must not report success for a run that audited nothing, including under a quiet flag.
- Derived artifacts record what produced them, and refuse to load when their components disagree.

Evidence state for the tooling added under this section, as of 2026-10-28: 191 unit tests pass (`tools/test_repo_partition.py` 22, `tools/test_archive_index.py` 53, `tools/test_intelligence_budget.py` 28, `tools/test_semantic_retrieval.py` 31, `tools/test_distribution_publish.py` 50, `tools/test_estoppel_effect.py` 7). The budget audit and the archive catalogue were run live against `api.github.com`. No deployment, no public URL response and no search-index state was independently verified, and nothing here was run in a browser.
