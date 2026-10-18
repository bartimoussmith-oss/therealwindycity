# drive-import/: data brought in from Google Drive

## master_meetings_database.json.gz

- **What:** caption transcripts of City of Cheyenne public-meeting videos. There are 720 records, mostly 2018–2026: City Council, Finance and Public Services committees, work sessions and Committee of the Whole, Planning Commission, Board of Adjustment, Historic Preservation Board, Urban Renewal Authority, and a few city clips.
- **Source:** Google Drive `MyDrive/WindyCityMeetings/processed_database/master_meetings_database.json` (bartimoussmith@gmail.com), copied 2026-10-17.
- **Size:** 40,119,375 bytes raw, gzipped here to stay under the repo's ~50 MB file rule.
- **SHA-256 (uncompressed):** `9bf6694991633785ab770129c797ab08dad96d69566a3cb3d0dbf188a91aa860`
- **Record shape:** `{id, title, filename, date ("YYYY-MM-DD" or "Unknown"), category, turns[{speaker, text}], raw_text_length}`
- **Used by:** `tools/ai_record_drive.py` → `tools/build_ai_record.py --drive-db` → the AI-readable site
  (meeting pages + `indexes/caption-transcripts.html`).

### `master_meetings_database_linked.json.gz` — import tool ready, run it from Colab

The linked export is 143,461,727 bytes: over GitHub's 100 MB blob limit and this
repo's ~50 MB file rule, and over the Drive connector's 100 MB transfer cap. The
bytes only exist on the machine that already has them, so the compression has to
happen there. `tools/colab_import_linked_db.py` does the whole handoff:

```python
# in Colab, with Drive mounted and GH_PAT in Secrets (Contents: write)
!python3 tools/colab_import_linked_db.py --repo /content/wc --push
```

It profiles the JSON (records, dated span, which fields the linked export adds
over the plain master), gzips it deterministically (`mtime=0`, no embedded
filename — the same source always yields the same SHA-256), writes
`drive-import/manifest.json` with both checksums and sizes, refuses to commit
above the ~50 MB rule, and pushes a `data/meetings-db-linked` branch with the
compare link. Expected output: ~40–48 MB gzipped (the plain master compresses
3.18×). Add `--allow-over` if it lands over 50 MB but under 100 MB.

Nothing consumes the linked file yet: `tools/ai_record_drive.py` reads
`master_meetings_database.json.gz`. Pointing the build at the linked export is a
separate change once the data branch lands.

To refresh the main database, replace the `.gz` file with a newer export and
push. The workflow rebuilds the site.
