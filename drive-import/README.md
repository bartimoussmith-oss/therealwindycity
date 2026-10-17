# drive-import/: data brought in from Google Drive

## master_meetings_database.json.gz

- **What:** caption transcripts of City of Cheyenne public-meeting videos. There are 720 records, mostly 2018–2026: City Council, Finance and Public Services committees, work sessions and Committee of the Whole, Planning Commission, Board of Adjustment, Historic Preservation Board, Urban Renewal Authority, and a few city clips.
- **Source:** Google Drive `MyDrive/WindyCityMeetings/processed_database/master_meetings_database.json` (bartimoussmith@gmail.com), copied 2026-10-17.
- **Size:** 40,119,375 bytes raw, gzipped here to stay under the repo's ~50 MB file rule.
- **SHA-256 (uncompressed):** `9bf6694991633785ab770129c797ab08dad96d69566a3cb3d0dbf188a91aa860`
- **Record shape:** `{id, title, filename, date ("YYYY-MM-DD" or "Unknown"), category, turns[{speaker, text}], raw_text_length}`
- **Used by:** `tools/ai_record_drive.py` → `tools/build_ai_record.py --drive-db` → the AI-readable site
  (meeting pages + `indexes/caption-transcripts.html`).

### Not yet imported: `master_meetings_database_linked.json`

This 143 MB file is too large for the Drive connector, which caps transfers at 100 MB. To add it, run the following in Colab and the result can be downloaded and merged in:

```python
import gzip, shutil
src = '/content/drive/MyDrive/WindyCityMeetings/processed_database/master_meetings_database_linked.json'
with open(src, 'rb') as fi, gzip.open(src + '.gz', 'wb', compresslevel=9) as fo:
    shutil.copyfileobj(fi, fo)
```

To refresh the main database, replace the `.gz` file with a newer export and push. The workflow rebuilds the site.
