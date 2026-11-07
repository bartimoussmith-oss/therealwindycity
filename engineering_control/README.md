# Consolidated engineering control center

This is the first executable layer of the overhaul, not a claim that the overhaul is finished. Existing applications, data collectors, monitors and live sites remain unchanged. No old video or statewide work is deleted.

## Execution and evidence

On installation, manual runs and six-hourly scheduled runs, two independent jobs actually build and test the current records_video_v2 wide and phone films. These jobs have read-only repository permission. On completion events for named existing workflows, the control center inspects results without rerunning the video proof lane. The reporting job runs even when a proof lane fails.

The auditor discovers public repositories across both accounts, records commit-pinned inventories, observes engineering controls, samples workflow failure logs, maps declared links and produces a role-assigned repair backlog. It tests its own classification and error filtering before scanning. Report publication is a separate privileged job; it never executes source code from a workflow_run event's branch.

Reports live on engineering-control-reports: latest/summary.md, latest/index.json, latest/backlog.json, latest/changes.json, and one small latest/repos/account__repository.json. Historical run evidence is retained under runs/<run-id>/. Local partial reports are uploaded for 30 days; proof videos for 14 days. Raw logs are not republished; error types and missing-module names are allowlisted.

## Responsibility lanes

Architect: dependency map and product boundaries. Data engineer: schemas, IDs, hashes, deduplication and end-to-end trace. Reliability engineer: failed steps, retained state and retries. Security reviewer: permissions, secrets and sensitive-data boundaries. Recovery engineer: isolated restore and rollback. Release engineer: deployment identity and real interface tests. Independent reviewer: source-backed claims and acceptance evidence. Agent coordinator: reproducible commands and handoffs. These are assigned review responsibilities, not claims that independent AI workers have been spawned.

## Acceptance rules

Configured is not executed. Executed is not tested. Tested is not deployed. Deployed is not independently verified. Each repair must identify an exact failure, preserve a baseline, supply a patch, pass regression and end-to-end tests, and verify the target output. Risky changes require rollback evidence and separate approval. No automatic merges, application rewrites or deployments occur here.

A filename is only a signal. Missing signals require investigation, not an assertion that functionality is absent. Older failed commits do not establish current failures. Changes in findings are not automatically counted as completed repairs. Repository links are declarations, not verified transfers.

## Remaining scope

Drive, local machines, Termux, private repos, host settings, full live-site testing, complete log archives, security scanning, restore drills and source-truth review are not implemented by this phase. They are explicit follow-up verification work, not hidden behind an overall healthy score.
