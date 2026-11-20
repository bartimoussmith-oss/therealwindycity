# Civic Polis hardening: implementation ledger

This first repair batch targets the actual legacy Granicus collector. It is NOT project completion.
Baseline branch: repair/civic-polis-hardening-2026-11-18, created from main at 8afd6949ff6cbfc920d7ad739cb767c13c0bb219.

## Implemented in this batch
- Fail-closed validation of the collector's existing [summary] JSON lines.
- Exact expected-source inventory: missing, duplicate and unexpected summaries rejected.
- Unreachable sources, collection errors, budget-limited runs and unverified empty results rejected.
- Read-only database integrity and foreign-key checks.
- Verification of every governance_items raw-file path and SHA-256 or SHA-512 digest.
- SQLite backup API snapshot, validated before atomic replacement.
- 21 offline regression tests; locally passed under Python 3.12.
- Read-only CI template testing Python 3.11 and 3.12; remote results not yet observed.

## Run
python -m unittest discover -s tests -p test_civic_harvest_gate.py -v

python tools/civic_harvest_gate.py --log granicus.log --expected-root SOURCE_URL --database database/promethean_evidence.db --evidence-root . --snapshot staging/verified.db

Use a log containing only the expected Granicus invocation summaries. Connect Cheyenne has a different contract and must not be silently treated as verified.
Exit 2 means reject; exit 0 means snapshot verified, NOT publication authorized.

## Safety boundaries
No scheduled production workflow is modified. No live records are harvested by these tests.
No raw objects are copied to public hosting. No secrets or deployment permissions are added.
The snapshot is portable as a database but still references raw evidence: raw objects require a separate verified release bundle.
Single trusted writer required. This is not protection against a malicious concurrent filesystem writer.
The legacy collector's summary is declarative, not independent seven-stage event accounting.
Existing missing raw files will cause rejection; do not weaken the check to conceal gaps.
Budget-limited historical crawls remain valid internal partial work, but this strict gate rejects them as complete releases.
The script does not enforce lawful access, robots policy, authority applicability, or legal conclusions.

## Remaining work / not yet validated
- Collector: retain acquisition events and source listings, validate attachment HTTP status, preserve unknown meeting dates as null, and record extraction failures explicitly.
- Evidence: immutable artifact versions, full SHA-256/SHA-512 manifests, durable remote retention and restore tests.
- Telemetry: event-derived counters, verified-empty adapters, resumption and separate partial-collection policy.
- Publication: trusted gate before database publication; stop if: always() from publishing unverified database updates; retain failure diagnostics separately.
- Migration: inspect existing databases and schema; additive migrations, dry-run reconciliation, backups and rollback.
- Authority: versioned Wyoming sources, source-backed predicates, exception handling and human review.
- Entity/GIS: mention-only default, explicit supported relationships, endpoint/service verification and ambiguous-match handling.
- Transcript/media: preserved captions, idempotent FTS ingestion, source time-base verification and safely constructed clips.
- MCP: actual transport integration, allowlisted path containment, read-only enforcement and protocol/security tests.
- Heartbeats: no default key, authenticated verification, freshness/replay controls and secret rotation.
- Release: live staging crawl, recovery drills, CI review, approved merge and independently verified remote cutover.

No courtroom-admissibility, statutory-compliance or production-certification claim is made.
