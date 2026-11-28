# Sunshine public integration

## Scope

This additive Streamlit page displays a bounded public snapshot, not the source vault or the internal research API. Existing pages, data sources, app entrypoints and agent instructions remain unchanged. Creating a local review branch does not deploy the live site.

The snapshot separates a supplied Wyoming roster, nationwide domain-discovery candidates, and explicitly approved findings. It provides no automatic accusation, compliance clearance, hostility score, tampering verdict, litigation prediction, or fabricated fallback finding. An empty findings list means no findings were approved for publication, not that all governments complied.

## Approval gate

The source database must contain the expected collection tables. Missing database files or failed required queries stop the export.

If the source contains a `sunshine_publication_approvals` table, a finding is eligible only when all of the following match:

- Its explicit publication classification is `PUB_TIER_1_PUBLIC`.
- Its evidence classification is an allowed facial-record or transcript-confirmed tier.
- Legal review and right-of-reply review are marked complete.
- A reviewer and review timestamp are present.
- Its SHA-256 matches the current source artifact row.
- Its approved source URL matches the artifact row.
- Approved public fields pass the text and URL gate.

The collector does not create approvals. Automatic evidence labels are insufficient. Reviewers must inspect actual records and governing authorities; a database boolean is not a substitute for that work.

Only allowlisted fields are exported. Unknown columns, internal flags, raw text, private paths, infrastructure metadata, behavioral scores, and source-system credentials are excluded. Separate unreviewed queues must be written outside the repository with directory mode 700 and file mode 600.

## Operation

Run the bridge explicitly with `--vault`, `--rwc-repo` and optional `--private-out` paths. It writes:

- `data/sunshine_public_export.json`
- `public/sunshine_scorecard.json`

The page reads the public snapshot only. It does not call an internal API, open local research databases, send notices, submit comments, or make legal filings. Its records-request worksheet is an unsent, jurisdiction-neutral drafting aid without asserted statutory deadlines or predetermined allegations.

## Verification and limitations

Run `python -m unittest discover -s tests -p test_sunshine_public_bridge.py -v` and syntax-check the new page. Inspect the full staged diff and public JSON before a commit or PR. Test missing snapshots and malformed data. Secret-pattern scanning is a useful gate but not proof against every possible secret format; human review remains necessary.

Domain counts are not government counts, and a seeded roster is not completed audit coverage. Discovery rows are labeled accordingly. Snapshot source freshness is its displayed generation time. No external source refresh occurs on page load.
