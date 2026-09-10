# YouTube Channel Setup — Step by Step

Time: ~1–2 hours one-time, plus waiting on Google for quota (optional).

## Step 1 — Google account

Use a dedicated Google account for the archive (not your personal daily driver
if you can avoid it). Turn on 2-Step Verification. If multiple people will help,
you can later add them as channel managers (YouTube Studio → Settings →
Permissions).

## Step 2 — Create the channel

1. Go to https://www.youtube.com, sign in, click your avatar → **Create a channel**.
2. **Name (important):** pick something that cannot be confused with the city
   government itself. Good patterns:
   - `Cheyenne Council Archive`
   - `Cheyenne WY Public Meetings Archive`
   - `Capitol City Civic Archive — Cheyenne WY`
   
   Then append `(Unofficial)` in the About section and banner (see
   `METADATA_TEMPLATES.md`). Avoid: "City of Cheyenne", "Official",
   the city seal/logo as your avatar. YouTube removes impersonating channels.
3. **Handle:** `@CheyenneCouncilArchive` or similar (youtube.com/@YourHandle).
4. Upload a simple avatar (e.g. text monogram) and banner (see templates doc).

## Step 3 — Phone-verify (REQUIRED)

Unverified accounts can't upload videos longer than **15 minutes** — every
council meeting exceeds that. Verified accounts get **12 hours / 256 GB**.

1. Go to https://www.youtube.com/verify and complete phone verification.
2. Confirm in YouTube Studio → Settings → Channel → **Feature eligibility**:
   - "Longer videos" → Enabled
   - "Custom thumbnails" → Enabled

## Step 4 — Create the API credentials (for the bulk uploader)

1. Go to https://console.cloud.google.com → new project, e.g.
   `cheyenne-archive`.
2. **APIs & Services → Library** → enable **YouTube Data API v3**.
3. **APIs & Services → OAuth consent screen**:
   - User type: External → app name `Cheyenne Archive Uploader`.
   - Scopes: add `.../auth/youtube.upload` and `.../auth/youtube`.
   - Test users: add the Google account that owns the channel.
     (Stay in Testing mode — fine for a personal uploader. Publishing the app
     triggers a Google verification review you don't need.)
4. **Credentials → Create Credentials → OAuth client ID** → type **Desktop app**
   → Download JSON → save it as `client_secrets.json` in the project folder.
5. First uploader run opens a browser for you to authorize; the token is cached
   as `yt_token.json`. **Never share either file publicly.**

## Step 5 — Understand the quota (plan your timeline)

- The API is **free** but capped at **10,000 quota units/day/project**.
- One video upload = **1,600 units** → **~6 uploads/day** default.
- Playlist create/add = 50 units; caption insert = 200 units.
- Quota resets at **midnight Pacific**.
- The uploader stops cleanly on `quotaExceeded` and resumes next run.

Your options to go faster:
1. **Request a quota extension** (free): in Cloud Console → YouTube Data API →
   Quotas → request increase, or via Google's API quota extension form. This
   triggers a compliance audit (weeks–months). Worth doing, but don't wait on it.
2. **Browser uploads in parallel:** YouTube Studio web uploads don't consume API
   quota. Community-observed daily caps run ~10–20/day on new channels and up
   to ~50–100 on established ones (Google publishes no number). You can
   hand-upload batches using the titles/descriptions straight from
   `upload_plan.csv` while the script burns its 6/day.
3. **Multiple projects won't help** — quota is per project but the *channel's*
   upload behavior is still rate-limited by YouTube's spam systems. Don't try
   to dodge limits; a strike hurts the whole project.

Realistic math for 1,226 videos:
- API only (6/day): ~200 days.
- API + 20/day by hand: ~7 weeks.
- Start **newest-first** so the channel has current value immediately.

## Step 6 — Publish settings used by the uploader

- `privacy=unlisted` default → review in Studio → bulk-flip to Public.
- Category: News & Politics (ID 25).
- `madeForKids=false`, language `en`.
- Playlists auto-created per `upload_plan.csv` (Council, Finance, Planning…).
- Captions attached when the archive.org download included `.vtt`/`.srt`.

## Step 7 — After the first uploads

- Check one video end-to-end: title, description links, playlist, captions,
  and that processing reached HD.
- In YouTube Studio → Settings → Channel → Advanced: set the channel country
  (United States) and consider adding relevant keywords (see templates doc).
- Add the playlists to the channel homepage layout (Customize channel → tabs).
