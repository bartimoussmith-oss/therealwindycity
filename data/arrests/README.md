# Arrest records — published with names

**Owner decision (2026-11-27): the arrest records are published unredacted** — each
record carries the person's name, and age where the source printed one, exactly as
Cap City News published them in its compilation of Laramie County law-enforcement
arrest logs. This replaces the 2026-10-17 publish-without-names policy.

| file | contents |
|---|---|
| `master_records.json` / `.csv` | 6,492 entries from 97 weekly Cap City News reports (2021-01-09 to 2025-09-27) |
| `records.json` / `.csv` | the 8/28/26–9/4/26 weekly report captured in `data/snapshots/` (65 entries) |

Each record: `record_id` · `name` · `age` (null when the source gave none) ·
`report_date`/`report_window` · `charges` (verbatim) · `charge_count` · `categories`
(charge groupings only) · `source_url` (the article it was parsed from).

## Read this before using the data

1. **Arrest is not guilt.** Every entry is a *recommended charge at booking*. Cases are
   dropped, reduced and dismissed; this dataset contains no outcomes.
2. **The source is not comprehensive.** Verbatim from Cap City News: the log omits juveniles,
   suspects recommended for charges of a sexual nature, and anyone who bonded or bailed out
   before the information was released.
3. **Same name ≠ same person.** Do not assume two records with the same name are one person,
   or that a record is about someone you know.
4. **Coverage is uneven across years** (missing reports, not fewer arrests). Don't compare years.
5. No demographic field is derived or published.

**Corrections:** if a record is wrong, or you can show a case was dismissed, open an issue and it
will be corrected or annotated.

## How the names were restored (2026-11-27)

- `tools/publish_arrest_names.py` re-ran `tools/import_master_arrest_db.py`'s own cleaning on the
  owner's `MASTER_ARREST_DATABASE.json`, so every record kept its `record_id`; it refused to write
  unless every record's id, source URL and charges matched the committed file. Independently,
  4,977 names re-read from the Cap City News articles agreed with the database (0 differences).
  Cap City News has since taken down its May–September 2025 weekly reports.
- `tools/unredact_captures.py` put the names back into the snapshots, text files and search index
  that ingest had redacted (`[WITHHELD]`), from unredacted copies of the same reports.
- Ingest no longer redacts arrest reports (`engine/redact.py`, `REDACT_ARREST_NAMES`, default off).
- The arrest page (`tools/build_arrest_page.py`) is built open, with names, by default.
