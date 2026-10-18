# Arrest records — de-identified public tier

Owner policy (2026-10-17): **publish the arrest records without names; names
are released only on request, for public-safety and non-discriminatory research
purposes only.**

| file | tier | committed? |
|---|---|---|
| `records.json` | **public** — no names | yes |
| `records.csv` | **public** — no names | yes |
| `name_key.json` | **SEALED** — record_id → name | **no** (gitignored, mode 600) |

Rebuild and re-audit:

```bash
python3 tools/build_arrest_records.py                # build + self-audit
python3 tools/build_arrest_records.py --audit        # audit existing output
python3 tools/build_arrest_records.py --report-leaks # where names already sit
```

The build **fails closed**: if any withheld name or name token appears anywhere
in the public tier it exits 3 and says which file and which name. Verification,
not assertion.

## What a public record contains

`record_id` (opaque, e.g. `LC-20260905-014`) · `report_published` ·
`arrest_window` · `charges` (verbatim, never paraphrased) · `charge_count` ·
`categories` · provenance (`source_url`, `source_capture`, `source_sha256`).

`record_id` is **sequential, not a hash of the name** — there is nothing to
brute-force back to a person.

## Requesting names

Open an issue with the **Arrest record name request** template
(`.github/ISSUE_TEMPLATE/arrest-name-request.md`). State the purpose and the
record IDs. The owner reviews and answers; nothing is released automatically.

Requests are granted for **public safety** and **non-discriminatory research**
only. Not granted: targeting, screening, employment or tenancy decisions,
journalistic ambush, resale, or any use that would identify or rank people by a
protected characteristic.

## Non-discriminatory use — read this before analysing

1. **The source excludes people systematically.** Verbatim from capcity.news:
   the log "is not a comprehensive document", and omits juveniles, suspects
   recommended for charges of a sexual nature, and anyone who bonded or bailed
   out before the information was released. Those exclusions are not random.
   Any rate, trend, or comparison built on this data inherits them.
2. **Arrest is not guilt.** Each entry is a *recommended charge at booking*.
   Cases get dropped, reduced, and dismissed. This tier publishes no outcome,
   because no outcome data exists here.
3. **No demographic field is derived, inferred, or published.** Categories are
   charge groupings only. Nothing encodes race, ethnicity, national origin, sex,
   gender, age, or immigration status — and no category exists as a filter for
   any of them. Charges that touch registry compliance or immigration holds are
   folded into the neutral `warrant_court` bucket rather than given a
   targeting-able label of their own. The verbatim charge text is always kept,
   so categorisation can never hide or distort what the record says.
4. **Do not re-identify.** Joining these records against other public sources to
   recover names defeats the policy and is out of scope of any grant.

## Honesty: this is an access gate, not secrecy

The names in these records are **already public**, and this repo already holds
them in two committed places:

- `data/snapshots/*arrest-report*` — the raw captured article, names intact.
- `data/engine.db` — its full text, indexed and searchable via FTS5 `text_index`.

Both are tracked by git, the repo is public, and the capture is mirrored on
capcity.news. So:

- This tier controls **what this project publishes and surfaces** — the site,
  the API, the dashboard present de-identified records only.
- It does **not** make the names secret, and no amount of derived-file
  redaction would.
- Deleting those files from the current tree would **not** remove them from git
  history, and repo protocol forbids rewriting the remote. It would also break
  the engine's provenance and the `verify_vault.py` verification bridge, which
  greps claims against exactly this captured text.

Run `--report-leaks` for the current measured state. Making the *source capture*
name-free going forward (redact at ingest, keep the sealed key off-repo) is a
real fix and an owner decision — it is deliberately **not** done here, because
it would destroy provenance for data already public.

## Coverage today

One report: **Laramie County weekly arrest report (8/28/26–9/4/26)**, published
2026-09-05 by Cap City News, 65 entries across five date windows. The engine's
`cap_city_news_rss` source pulls these automatically, so coverage grows as the
civic cycle runs. Older reports that exist only in Google Drive (two Oct-2025
weeklies as JSON, one Sept-2025 page source, two saved pages) are not yet
captured — add each with `--source` once fetched.
