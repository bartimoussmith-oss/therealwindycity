# Agent handoff: finish deployment and freshness repairs

**Owner request:** fix the remaining deployment/freshness problems across the projects below. Implement, test, and verify fixes; do not merely repeat the audit. First re-check current state: observations here are from October 21, 2026 and may be superseded.

## Start here

1. Read each repository's agent instructions and coordination file before editing. In this repository, read all of `READ-FIRST.md`, honor active claims, and register your own scope. Preserve source records, existing work, and credentials. Never fabricate collection timestamps, meeting outcomes, transcript verification, or records to make a dashboard look current.
2. Confirm repository access and working-tree state. If access or deployment permissions are missing, report that specific blocker; never request passwords or tokens in chat.
3. This handoff is on `bartimoussmith-oss/therealwindycity`, branch **`arena/f5cf27dc-therealwindycity`**. This Arena session must stay on that branch. Do not rename it or push another branch from this session. An independent agent should follow its own session constraints and the target repository's collaboration rules, using separate checkouts as needed.
4. Use `git` for Git operations and `gh` for GitHub PRs, checks, and deployments. Review and merge through the owner's normal process; do not bypass protections or force-push. Do not cancel jobs, disable schedules, change secrets, or alter Pages settings without establishing necessity and appropriate authorization.

## Projects and observed state

| Repository / service | URL | Observation, not a current guarantee |
|---|---|---|
| `bartimoussmith-oss/therealwindycity` | https://bartimoussmith-oss.github.io/therealwindycity/ | Readable plain-text mirror. New local safeguards described below still need integration and publication. |
| `therealwindycity/The-Real-Windy-City-` | https://therealwindycity.github.io/The-Real-Windy-City-/ | Returned an older minimal archive/Atlas introduction rather than the new evidence-first homepage. |
| `therealwindycity/TheReelWindyCity` | https://therealwindycity.github.io/TheReelWindyCity/ | Returned October 5 as “upcoming” and September 22 as latest transcript, despite a successful recent Pages deployment. |
| Streamlit deployment, associated with this repository; confirm Cloud settings | https://therealwindycity.streamlit.app/ | Fetch returned a Streamlit shell and a client-blocked embedded status page. Application failure was **not** established. |

## A. Publish and validate the fixes already made here

Review these changes on the handoff branch before duplicating work:

- `tools/ai_record_status.py`: generated status panel and snapshot JSON, with collection-check and verified-outcome fields explicitly unknown.
- `tools/build_ai_record.py`: adds the static homepage panel and `indexes/status.json`.
- `tools/check_ai_record.py`: artifact/public smoke checks including expected commit SHA and workflow run ID.
- `tools/test_ai_record_status.py`: six regression tests.
- `.github/workflows/ai-record-pages.yml`: unit tests, artifact verification, and post-deployment verification. Deployment remains restricted to `main`.
- `tools/README-ai-record.md`: semantics, limits, and separate deployment URLs.

Previously validated: six unit tests, Python compilation, and a synthetic build/render of 12 pages plus the artifact checker. **Not validated:** full-corpus build or public serving of these changes. Local test success is not publication.

Tasks:

1. Review the branch diff against `main`, resolve upstream changes without discarding either agent's work, and run tests. If these fixes are already upstream, do not reapply them.
2. Open/reuse a PR from the session branch and follow the owner's merge policy. The handoff being pushed does not itself deploy Pages.
3. Run/observe the full build after integration. Check both existing workflow results and the new post-publication step. Fix any genuine integration defects rather than suppressing checks.
4. Independently fetch the public homepage, `indexes/status.json`, `indexes/meetings.json`, `llms.txt`, corrections, data quality, and at least one actual meeting page. Verify the deployed revision and run ID against the intended successful action.

```bash
python3 -m unittest discover -s tools -p 'test_ai_record_status.py' -v
python3 -m py_compile tools/ai_record_status.py tools/check_ai_record.py tools/build_ai_record.py
# After producing _site with the documented full pipeline:
python3 tools/check_ai_record.py --site _site
# Substitute real action identifiers, not the handoff commit unless that was built:
python3 tools/check_ai_record.py --url https://bartimoussmith-oss.github.io/therealwindycity/ \
  --revision <built-commit-sha> --run <successful-run-id> --attempts 6
```

Limitations to preserve: the current smoke checker is not an exhaustive link audit or browser test. Its stale-upcoming pattern only covers nearby explicit ISO dates, not dates such as “October 5, 2026.” Collection-check/outcome fields intentionally remain null until implemented with provenance. Do not fill them from build time.

## B. Alternate archive: remove the collection/deployment bottleneck

Target: `therealwindycity/The-Real-Windy-City-`.

Historical leads:

- Evidence-first homepage commit: `9557a4b5060b6a13de6e725dce13f1f5557f34c0` (“Add evidence-first archive status and coverage”).
- Newer deployment run `39597299153` was pending: https://github.com/therealwindycity/The-Real-Windy-City-/actions/runs/39597299153
- Earlier run `39594930015` was in progress at **Sync public city website**, before site assembly and upload: https://github.com/therealwindycity/The-Real-Windy-City-/actions/runs/39594930015
- Latest deployment recorded at the time was October 12. This is a lead, not proof a job is still stuck.

Tasks:

1. Inspect current default branch, Pages configuration, actual workflow, logs, concurrency groups, and deployment statuses. Confirm what artifact is assembled and which homepage path it includes. Do not assume the delay is the only defect.
2. Separate potentially slow external city collection from static publication. Make collection bounded (network and job timeouts, bounded retries). Publish from an explicit validated saved snapshot when collection is unavailable, with its real source-check age and collection error visible. Preserve last-known-good state; never replace it with an empty or partially written snapshot.
3. Do not simply background collection, ignore all failures, or mark a stale snapshot as fresh. Validate artifacts before promotion and retain diagnostics. If no valid snapshot exists, fail clearly or publish an explicit unavailable state without invented figures.
4. Ensure static-only homepage fixes can publish without waiting for a full city crawl. Choose a separate workflow/job or another repository-appropriate architecture; inspect current state before choosing.
5. Confirm the evidence-first homepage, `city/coverage.html`, `city/freshness.json`, and every newly added internal link are in the deployed artifact. Test in a real browser, including successful status JSON loading, unavailable/malformed JSON, and JavaScript disabled. Do not leave “Loading…” indefinitely; provide a truthful fallback.
6. Keep the distinction between a qualified October 19 supplied-caption reconstruction and the regular catalog's latest indexed transcript. Do not label reconstruction as audio- or official-minute-verified unless someone actually performs and records that verification.
7. Preserve the limited scope of the 101 zero-native-text pages among 862 examined page instances. Do not convert that audit into a repository-wide OCR backlog without document-ID matching and a defined denominator.

Acceptance: a successful deployment serves the intended homepage revision; slow/failed collection cannot indefinitely block a static homepage update; failures preserve good data and expose uncertainty; no unsupported timestamps, outcomes, or total-corpus audit claims.

## C. Civic Cheyenne: fix date-driven cards, not just deployment

Target: `therealwindycity/TheReelWindyCity`.

Tasks:

1. Locate homepage cards and their data sources. The returned page showed Public Services Committee **October 5, 2026**, labeled “Upcoming — agenda posted,” plus Finance October 6 and latest transcript September 22. A successful deployment on October 21 did not correct that presentation.
2. Remove dependence on fixed demonstration/seed dates for live “next meeting” cards. Derive upcoming status from current, source-linked records and **America/Denver** time, accounting for missing meeting times, cancellation, and rescheduling. Treat date-only records conservatively; document the same-day cutoff rather than assuming a completed meeting.
3. When no current confirmed meeting is available, show “No upcoming meeting confirmed in this snapshot” (or equivalent), the real collection-check time if known, and an official schedule link. Do not invent the next meeting or infer held/completed status merely because a date passed.
4. Calculate “latest transcript” from available transcript files/validated holdings, not an arbitrary hard-coded date or missing-file catalog entry. Keep supplied reconstructions separately labeled.
5. Reconcile homepage counts with the generated source catalog. Explain count definitions; do not force totals to agree with another site whose holdings or denominator differ.
6. Add deterministic tests with an injected clock: before/after October 5, after October 21, same-day boundaries, DST/timezone boundary, no upcoming entries, canceled/rescheduled records, missing collection timestamp, missing transcript files, and unavailable or stale data. Test natural-language date labels as well as ISO dates.
7. Verify both HTML/accessible text and hydrated browser state. A JS-only correction does not fix stale static content returned to search/fetch tools. Publish and verify the exact revision plus key hub/meeting links.

Acceptance: October 5 is never called upcoming when the injected clock is after it; absent current evidence produces an honest fallback; calendar status is not misrepresented as verified outcomes; initial HTML and browser presentation agree.

## D. Streamlit: diagnose first, then fix confirmed defects

1. Confirm actual Streamlit Cloud repository, branch, entrypoint, and deployment logs with authorized access. Do not assume a blocked embedded statuspage.io request means the app is down.
2. Open the app in a browser; distinguish shell/network issues from Python startup exceptions, missing dependencies, or data-path errors. Record the actual error and affected route before editing.
3. Reproduce confirmed failures locally with the repository's requirements. Use Streamlit AppTest where feasible for home and any changed pages. Preserve `streamlit_app.py` and `Transparency_Index_App.py` as byte-identical twins if either is changed.
4. Keep secret-bearing configuration out of Git. If Cloud permissions/logs are unavailable, state the remaining blocker instead of guessing or changing unrelated code.
5. After a fix, verify the real app renders useful content, not merely HTTP 200 or a Streamlit shell. Do not remove unrelated functionality to make a smoke test pass.

Acceptance: a specific confirmed defect has a reproducible test and verified fix, or browser/log evidence establishes no app defect and documents the fetch limitation. Unknown health must not be reported as healthy or broken.

## Final report required from the receiving agent

For **each project**, supply:

- Root cause, changed files, commit and PR URL, and tests actually run.
- Workflow/deployment run URL and intended revision.
- Public URLs checked and check time (with timezone).
- What was verified by raw fetch, what was verified in a browser, and what remains unknown.
- Separate statuses for **source fixed**, **tests passed**, **deployment succeeded**, and **public revision verified**.
- Any pending authorization or access blocker.

Do not mark the whole task done because one workflow is green. Do not claim fresh collection, complete coverage, OCR completion, verified speech, or verified outcomes without the corresponding source evidence.
