# Issue Newsroom implementation and agent handoff

Branch: feature/issue-newsroom, starting at 69d43f69d9ab385904f60d55dcd885b8314e2720. Owner-requested scope: new tools/issue_newsroom.py, tools/test_issue_newsroom.py and this runbook only. No other agent's implementation paths, source records, app twins, workflows or dependencies are changed. Before subsequent integration, read current READ-FIRST.md, AGENTS.md and the ecosystem guide and register a current claim through the repository coordination process. This file is not a global task lock.

## Run and test
python -m unittest discover -s tools -p 'test_issue_newsroom.py' -v
python tools/issue_newsroom.py --corpus /tmp/ai-record --out /tmp/issue-newsroom --revision SOURCE_REVISION --approved-public

Input must be an explicitly approved generated PUBLIC Markdown mirror, with llms.txt, not a repository root. Only documents/ and meetings/ Markdown are consumed. No private-repository or Drive scanning occurs. The flag is an operator attestation, not independent privacy verification. Use a fresh non-nested output directory. Upstream original-document privacy review remains mandatory.

## Outputs
Full-text record reading/download pages, twelve finite reporting desks, identifier-candidate dossiers, all matching source lines, record catalog, memberships, coverage, excluded/unassigned queues and three reporting prompts per included member. Input representations are versioned by SHA-256. Dates extracted from paths remain explicitly unverified. Exact duplicates are reported, not counted as independent evidence. Identifier collisions across years/bodies and line-based false positives need review.

No semantic clustering, exhaustive issue discovery, complete city history, verified relationships, full original-binary ingestion, editorial approval UI, production deployment, real-corpus execution, automatic Media Studio import, or publication-ready stories are claimed. Prompts are not finished media drops. Complete input text is retained; rendered record text escapes HTML rather than executing input markup.

## Verification
A preceding local candidate passed synthetic-fixture checks for full text, overlapping groups, unassigned records, HTML escaping and approval/overwrite guards. The committed tests must actually be run on this exact revision before claiming CI success. No real corpus or browser result has yet been established.

## Next bounded integration tasks
1. Add isolated branch CI after coordinating the workflow path; do not trigger production.
2. Reuse the existing approved mirror build to run this builder; preserve existing artifacts.
3. Inspect coverage, false/missed matches, identifier namespace collisions, source metadata and independent source families.
4. Add reviewed issue/record/span adapters to the existing Media Studio story contract, retaining claim evidence and immutable versions.
5. Add explicit multi-source dossiers and editorial selection; do not publish every reporting prompt as a story.
6. Review privacy/provenance, artifact sizes, source links, browser behavior and live revision before seeking a production merge. Never publish synthetic test fixtures as real records.
