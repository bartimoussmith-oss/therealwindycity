# Metadata Templates — About, Descriptions, Tags, Playlists

Copy-paste starting points. The uploader script already applies the video-level
templates automatically (see `scripts/build_upload_plan.py`); this file is for
the channel-level text you enter once in YouTube Studio, plus guidance.

## Channel About (paste into Customize channel → About)

```
Cheyenne Public Meetings Archive (Unofficial)

A searchable public archive of City of Cheyenne, Wyoming government meeting
videos — City Council / Governing Body sessions back to 2008 plus committee,
Planning Commission, and work session recordings.

UNOFFICIAL ARCHIVE — not affiliated with, endorsed by, or acting on behalf of
the City of Cheyenne. Official sources:
• City of Cheyenne: https://www.cheyennecity.org
• Meeting videos & agendas (Granicus): https://cheyenne.granicus.com/ViewPublisher.php?view_id=2
• City's official YouTube: https://www.youtube.com/@TheCityofCheyenne

These are recordings of public meetings posted as public records, preserved
here for searchability and long-term access. Meeting agendas and approved
minutes on the City's Granicus page are the authoritative record of actions
taken. Video titles, dates, and descriptions are transcribed from the source
archives; report errors via comments and they will be corrected.

No copyright is claimed in the underlying public meeting recordings. Channel
presentation (titles, playlists, descriptions) is original.
```

Channel keywords (Studio → Settings → Channel → Basic info): `Cheyenne
Wyoming, Cheyenne City Council, public meetings, governing body, Laramie
County, civic archive`

## Banner / avatar guidance

- Banner text: `CHEYENNE PUBLIC MEETINGS ARCHIVE` + small `Unofficial civic project`.
- Do NOT use the City of Cheyenne seal, logo, or flag as your avatar — use a
  plain monogram (e.g. "CCA") or a generic capitol-dome graphic you have rights
  to. This keeps you clear of YouTube's impersonation policy.

## Video description template (already applied by the scripts)

Granicus items:
```
<Meeting name> — City of Cheyenne, Wyoming — <Month D, YYYY>.
Duration (Granicus): <XXh XXm>.

Source: City of Cheyenne Granicus archive (<player URL>).
Agenda: <agenda URL>
Minutes: <minutes URL>

This is a recording of a public meeting posted as a public record. Unofficial
public archive. Not affiliated with or endorsed by the City of Cheyenne.
```

archive.org items:
```
<Title> — City of Cheyenne, Wyoming — <Month D, YYYY>.

Source: Internet Archive community collection (<item URL>).
Original publisher materials courtesy of the City of Cheyenne.

This is a recording of a public meeting posted as a public record. Unofficial
public archive. Not affiliated with or endorsed by the City of Cheyenne.
```

To change wording across all 1,200+ videos, edit the template strings in
`scripts/build_upload_plan.py` and re-run it *before* uploading.

## Title conventions (already applied)

- Council: `Cheyenne City Council Meeting — August 24, 2026`
- Committees: original title + long date, e.g.
  `Finance Committee 01-16-24 — January 16, 2024`
- Titles are capped at YouTube's 100-character limit by the script.

## Playlists (auto-created by the uploader)

1. City Council Meetings
2. Finance Committee
3. Public Services Committee
4. Planning Commission
5. Boards & Commissions
6. Work Sessions & Special Meetings
7. City Hall Extras & PSAs

After upload, pin these playlists to the channel homepage
(Customize channel → Home tab → Add section → Playlists).

## Thumbnails

Default (video stills) is fine for an archive. If you want branded thumbnails
later, YouTube requires phone verification (already done in setup) and images
≤ 2 MB. A cheap high-value approach: one template per playlist
("CITY COUNCIL / AUG 24 2026") rendered with PIL/ImageMagick in batch.

## Publishing order

- **Newest-first** (`--newest-first`): channel is immediately useful; older
  meetings trickle in. Recommended.
- **Oldest-first** (default sort): clean chronological backfill; channel looks
  stale until you reach recent years.
- Either way, upload `unlisted`, spot-check, then bulk-publish weekly.
