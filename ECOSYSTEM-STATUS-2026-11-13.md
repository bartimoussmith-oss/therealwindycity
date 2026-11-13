# Ecosystem status — November 13, 2026

## Scope and verification boundary

Prepared from the read-only GitHub and public-page inspection reported in the November 13 conversation. This is a dated observation, not continuous monitoring, a complete code audit, or a declaration that the ecosystem has been repaired. No runtime tests, current Actions-log audit, browser interaction tests, or Drive transfer verification were performed. Repository update timestamps are not collection timestamps.

## Current status

| Layer | Status | Evidence and limitation | Next acceptance check |
|---|---|---|---|
| Main therealwindycity platform | Implemented components; operational health unverified | Root contains Streamlit, civic atlas, pipeline, RAG, database, agent, Wyoming and deployment components. Presence is not proof of execution. | Test entry points; match deployed revision to successful workflow; inspect collection freshness separately. |
| Civic Cheyenne frontend | Homepage reachable in preceding inspection | https://therealwindycity.github.io/TheReelWindyCity/ returned an updated community-information homepage. This does not verify all routes, current revision, or ingestion. | Inspect current workflow results, deployed revision, meeting catalogs and source-check times. |
| Civic Newsroom family | Repositories present; current end-to-end operation unverified | civic-newsroom, civic-newsroom-data-001, civic-newsroom-law-001 and civic-newsroom-intelligence-001 appeared in live inventory. Failed page extraction is not proof of an outage. | Verify publication manifests, hashes, partition budgets, deployment and browser retrieval. |
| Cheyenne–Laramie archive and analysis | Repositories present; completeness unverified | cheyenne-laramie-archive and cheyenne-laramie-analysis-001 appeared in inventory with November 12 metadata updates. Archive README explicitly disclaims verified historical completeness. | Inspect actual manifests and measured discovered/collected/extracted/indexed counts. |
| Promethean command center | Default-branch scaffold only at inspection | promethean-command-center root listing contained only README.md. This does not exclude work on other branches or elsewhere. | Implement and test the application, source adapters, configuration and deployment. |
| Promethean Wyoming data | Default-branch scaffold only at inspection | promethean-wyoming-data root listing contained only README.md. Repository description is not implementation evidence. | Publish provenance-preserving registry data, GUI, validation and deployment. |
| Historical archives and transcripts | Current freshness and completeness unverified | Historical inventory and audits are leads, not current pipeline verification. | Measure coverage, OCR/extraction, transcript locators and ingestion freshness separately. |
| Private Drive, scanner and casework layers | Inventory presence only | No private contents, transfer outcomes, transcription results or device runtime were audited. | Perform authorized private verification without publishing sensitive contents. |
| Cross-service integrations | Not assessed | Gmail, Calendar, Facebook, Meta Ads, YouTube Analytics, Zoom and Fireflies were outside this inspection. | Verify each integration independently; connection presence is not workflow health. |

## Coordination gaps

The preceding inspection read civic_atlas/media/projects.json with observed_at 2026-10-25T20:13:00-06:00. It is explicitly a partial snapshot, not a health monitor, and omits newer families. Preserve it as historical evidence until its renderer and schema can be checked before migration.

The federation manifest was re-read while preparing this update. It lists only the primary therealwindycity and secondary TheReelWindyCity repositories. It is not a complete estate inventory. Do not add private repository details to a public registry without approval.

## Priority queue for agents

1. Recheck the October 28 audit's public-record integrity leads, including demonstration arrest records and malformed meeting dates. They are historical findings, not defects reconfirmed by this update.
2. Build a canonical inventory across both GitHub identities, with repository roles, public/private boundaries, source authority and deployment URLs.
3. Refresh the dashboard registry after checking its consumer schema; preserve previous observations and distinguish evidence dates from collection times.
4. Track implementation, tests, deployment, public revision and collection freshness as separate states. Unknown must remain unknown.
5. Finish the two Promethean scaffolds or label them explicitly as planned; do not report README-only repositories as delivered applications.
6. Verify source → archive → extraction/index → analysis → publication links using stable identifiers and provenance.
7. Add bounded, read-only automated checks with visible failures before calling this continuous monitoring.

## Agent guardrails

Read repository instructions and active scope claims before edits. Preserve source records, historical audits and unrelated work. Do not fabricate timestamps, coverage, outcomes or test results. Do not treat a green build, HTTP response or repository description as proof of fresh data. Any automated monitor, repair, deployment, merge, secret change or schedule change is separate work requiring appropriate review and authorization.

## What this update changes

Adds a current, evidence-scoped status document only. It does not modify projects.json, federation membership, application code, workflows, secrets or deployed services. No subsystem is marked repaired by this documentation commit.
