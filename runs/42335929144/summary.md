# Engineering control center

Updated 2026-11-07T03:55:31.722Z
Public repositories: 15. Declared connections: 48.
Current video proof lane: success. This is not a deployment result.

## Repair priorities

- P1 | therealwindycity/therealwindycity | Reliability engineer: Reproduce the failed step on the recorded SHA, repair its demonstrated cause, and rerun.
- P2 | bartimoussmith-oss/civic-newsroom | Architect: Map producers, consumers, storage, deployment targets and responsible owners.
- P2 | bartimoussmith-oss/civic-newsroom | Build engineer: Prove installation from a clean checkout with stated tool versions.
- P2 | bartimoussmith-oss/civic-newsroom | Data engineer: Validate input/output schemas, stable identifiers and compatibility across repositories.
- P2 | bartimoussmith-oss/civic-newsroom | Evidence reviewer: Retain origin URLs, capture times, hashes, original records and limitations.
- P2 | bartimoussmith-oss/civic-newsroom | Reliability engineer: Test interruption recovery and persistence without duplication or data loss.
- P2 | bartimoussmith-oss/civic-newsroom | Recovery engineer: Prove a backup restoration and a reversible release before risky repairs.
- P2 | bartimoussmith-oss/civic-newsroom | Supply-chain reviewer: Check lockfiles or equivalent version pinning; missing filenames alone do not prove dependencies are unpinned.
- P2 | bartimoussmith-oss/civic-newsroom | Rights reviewer: Separate code licensing from source-data and media reuse rights; review manually.
- P2 | bartimoussmith-oss/civic-newsroom | Reliability/security reviewer: Review missing concurrency signal in this workflow; verify behavior before editing.
- P2 | bartimoussmith-oss/civic-newsroom | Reliability/security reviewer: Review missing always_save signal in this workflow; verify behavior before editing.
- P2 | bartimoussmith-oss/civic-newsroom | Reliability/security reviewer: Review missing always_save signal in this workflow; verify behavior before editing.
- P2 | bartimoussmith-oss/civic-newsroom | Reliability/security reviewer: Review missing always_save signal in this workflow; verify behavior before editing.
- P2 | bartimoussmith-oss/civic-newsroom-data-001 | Architect: Map producers, consumers, storage, deployment targets and responsible owners.
- P2 | bartimoussmith-oss/civic-newsroom-data-001 | Agent coordinator: Provide tested commands, current status, constraints and acceptance criteria.
- P2 | bartimoussmith-oss/civic-newsroom-data-001 | Build engineer: Prove installation from a clean checkout with stated tool versions.
- P2 | bartimoussmith-oss/civic-newsroom-data-001 | Test engineer: Add offline tests and one real end-to-end producer-to-published-output test.
- P2 | bartimoussmith-oss/civic-newsroom-data-001 | Data engineer: Validate input/output schemas, stable identifiers and compatibility across repositories.
- P2 | bartimoussmith-oss/civic-newsroom-data-001 | Reliability engineer: Test interruption recovery and persistence without duplication or data loss.
- P2 | bartimoussmith-oss/civic-newsroom-data-001 | Recovery engineer: Prove a backup restoration and a reversible release before risky repairs.
- P2 | bartimoussmith-oss/civic-newsroom-data-001 | Release engineer: Tie the live output to its commit, smoke test and rollback instructions.
- P2 | bartimoussmith-oss/civic-newsroom-data-001 | Supply-chain reviewer: Check lockfiles or equivalent version pinning; missing filenames alone do not prove dependencies are unpinned.
- P2 | bartimoussmith-oss/civic-newsroom-data-001 | Rights reviewer: Separate code licensing from source-data and media reuse rights; review manually.
- P2 | bartimoussmith-oss/civic-newsroom-data-001 | Reliability/security reviewer: Review missing always_save signal in this workflow; verify behavior before editing.
- P2 | bartimoussmith-oss/civic-newsroom-data-001 | Reliability/security reviewer: Review missing always_save signal in this workflow; verify behavior before editing.
- P2 | bartimoussmith-oss/civic-newsroom-intelligence-001 | Architect: Map producers, consumers, storage, deployment targets and responsible owners.
- P2 | bartimoussmith-oss/civic-newsroom-intelligence-001 | Agent coordinator: Provide tested commands, current status, constraints and acceptance criteria.
- P2 | bartimoussmith-oss/civic-newsroom-intelligence-001 | Build engineer: Prove installation from a clean checkout with stated tool versions.
- P2 | bartimoussmith-oss/civic-newsroom-intelligence-001 | Data engineer: Validate input/output schemas, stable identifiers and compatibility across repositories.
- P2 | bartimoussmith-oss/civic-newsroom-intelligence-001 | Reliability engineer: Test interruption recovery and persistence without duplication or data loss.

## Verification still required

- Data engineer: Trace one source record through fetch, durable storage, extraction, indexing, publication and repeat run; reconcile IDs, hashes, dates and counts.
- Security reviewer: Review least privilege, secret storage, external inputs, private/raw data boundaries and dependency vulnerabilities. No security certification from filename checks.
- Recovery engineer: Restore a backup in isolation; test interruption, duplicates, migrations, corruption handling and rollback without touching live records.
- Release engineer: Verify actual deployed pages and video playback, mobile behavior, accessibility, source links and release-to-commit identity.
- Independent reviewer: Check claims against original sources; distinguish configured, executed, tested, deployed and independently verified.

## Scope limits

- Public GitHub repos across bartimoussmith-oss and therealwindycity only. Drive, Termux, private repos and hosting accounts remain uninspected.
- Inventory and filename/text signals do not prove controls work. Not observed is not established absence.
- Recent runs are bounded to 100 per repo; only the latest run per workflow and branch is retained. At most 12 failed jobs have logs inspected across the audit.
- At most 12 workflow/docs/manifest files per repo are read to map declared dependencies. Links are not verified data transfers.
- Only allowlisted error types and missing-module names are published. Raw logs, arbitrary exception messages and credentials are never republished.
- Video proof covers the current records_video_v2 builder, not PR #26, all archive features or the live site.
- No application rewrites, merges, deployments, destructive tests or automatic fixes are performed. Specialist roles are review responsibilities, not independently running AI agents.

Full backlog: latest/backlog.json. Evidence and recent runs: latest/repos/*.json.
