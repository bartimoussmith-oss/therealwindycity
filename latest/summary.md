# Engineering control center

Updated 2026-11-08T22:30:13.142Z. Evidence policy: version 2.
Public repositories: 17. Declared connections: 48.
Current video proof lane: success. Not a deployment result.

## Repair priorities

- P2 | bartimoussmith-oss/cheyenne-laramie-analysis-001 | Architect: Map producers, consumers, storage, deployment targets and owners.
- P2 | bartimoussmith-oss/cheyenne-laramie-analysis-001 | Agent coordinator: Provide tested commands, current status, constraints and acceptance criteria.
- P2 | bartimoussmith-oss/cheyenne-laramie-analysis-001 | Build engineer: Prove installation from a clean checkout with stated tool versions.
- P2 | bartimoussmith-oss/cheyenne-laramie-analysis-001 | Test engineer: Add offline tests and a real producer-to-published-output test.
- P2 | bartimoussmith-oss/cheyenne-laramie-analysis-001 | Data engineer: Validate schemas, stable IDs and compatibility between producers and consumers.
- P2 | bartimoussmith-oss/cheyenne-laramie-analysis-001 | Evidence reviewer: Retain source URLs, capture dates, hashes, original records and limitations.
- P2 | bartimoussmith-oss/cheyenne-laramie-analysis-001 | Recovery engineer: Test isolated backup restoration and reversible releases.
- P2 | bartimoussmith-oss/cheyenne-laramie-analysis-001 | Release engineer: Tie live output to its commit, smoke test and rollback instructions.
- P2 | bartimoussmith-oss/cheyenne-laramie-analysis-001 | Supply-chain reviewer: Review lockfiles or equivalent pins; missing filenames alone do not establish unpinned dependencies.
- P2 | bartimoussmith-oss/cheyenne-laramie-analysis-001 | Rights reviewer: Separate code licensing from source-data and media reuse rights.
- P2 | bartimoussmith-oss/cheyenne-laramie-analysis-001 | Reliability/security reviewer: Review missing always_save signal; inspect equivalent controls before editing.
- P2 | bartimoussmith-oss/cheyenne-laramie-archive | Architect: Map producers, consumers, storage, deployment targets and owners.
- P2 | bartimoussmith-oss/cheyenne-laramie-archive | Agent coordinator: Provide tested commands, current status, constraints and acceptance criteria.
- P2 | bartimoussmith-oss/cheyenne-laramie-archive | Build engineer: Prove installation from a clean checkout with stated tool versions.
- P2 | bartimoussmith-oss/cheyenne-laramie-archive | Test engineer: Add offline tests and a real producer-to-published-output test.
- P2 | bartimoussmith-oss/cheyenne-laramie-archive | Recovery engineer: Test isolated backup restoration and reversible releases.
- P2 | bartimoussmith-oss/cheyenne-laramie-archive | Release engineer: Tie live output to its commit, smoke test and rollback instructions.
- P2 | bartimoussmith-oss/cheyenne-laramie-archive | Supply-chain reviewer: Review lockfiles or equivalent pins; missing filenames alone do not establish unpinned dependencies.
- P2 | bartimoussmith-oss/cheyenne-laramie-archive | Rights reviewer: Separate code licensing from source-data and media reuse rights.
- P2 | bartimoussmith-oss/cheyenne-laramie-archive | Reliability/security reviewer: Review missing always_save signal; inspect equivalent controls before editing.
- P2 | bartimoussmith-oss/civic-newsroom | Architect: Map producers, consumers, storage, deployment targets and owners.
- P2 | bartimoussmith-oss/civic-newsroom | Build engineer: Prove installation from a clean checkout with stated tool versions.
- P2 | bartimoussmith-oss/civic-newsroom | Data engineer: Validate schemas, stable IDs and compatibility between producers and consumers.
- P2 | bartimoussmith-oss/civic-newsroom | Evidence reviewer: Retain source URLs, capture dates, hashes, original records and limitations.
- P2 | bartimoussmith-oss/civic-newsroom | Reliability engineer: Prove interrupted runs resume without lost records or duplicates.
- P2 | bartimoussmith-oss/civic-newsroom | Recovery engineer: Test isolated backup restoration and reversible releases.
- P2 | bartimoussmith-oss/civic-newsroom | Release engineer: Tie live output to its commit, smoke test and rollback instructions.
- P2 | bartimoussmith-oss/civic-newsroom | Supply-chain reviewer: Review lockfiles or equivalent pins; missing filenames alone do not establish unpinned dependencies.
- P2 | bartimoussmith-oss/civic-newsroom | Rights reviewer: Separate code licensing from source-data and media reuse rights.
- P2 | bartimoussmith-oss/civic-newsroom | Reliability/security reviewer: Review missing concurrency signal; inspect equivalent controls before editing.

## Verification still required

- Data engineer: Trace a real record through collection, storage, extraction, indexing, publication and repeat run.
- Security reviewer: Inspect permissions, secrets, sensitive data boundaries and dependency vulnerabilities.
- Recovery engineer: Prove backup restore, interruption recovery, deduplication and rollback in isolation.
- Release engineer: Verify actual live pages, phone/desktop media playback and release-to-commit identity.
- Independent reviewer: Check claims against source records and distinguish configured, executed, tested, deployed and verified.

## Scope limits

- Public GitHub repositories across both named accounts only; Drive, private repositories, local devices and hosts are not inspected.
- Engineering file signals are not proof of implementation correctness. Missing signals require review. Archived-content folders are excluded from engineering evidence.
- At most 100 recent runs per repository; latest run per workflow/branch retained. At most 12 failed jobs have bounded logs inspected; raw messages and secrets are not republished.
- At most 12 engineering workflow/docs/manifest files per repository are sampled for declared dependencies. References are not verified transfers.
- Video proof covers records_video_v2, not PR #26 or the live site. No application repair, merge, deployment, destructive test or security certification is performed.

Full backlog: latest/backlog.json. Evidence: latest/repos/*.json.
