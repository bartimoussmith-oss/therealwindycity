#!/usr/bin/env python3
"""
upload_youtube.py — Bulk-upload the Cheyenne archive to your YouTube channel.

Reads upload_plan.csv (built by build_upload_plan.py), uploads each downloaded
video with its title/description/tags, and files it into the right playlist.
State is saved after every video, so you can stop and resume freely.

QUOTA REALITY CHECK (YouTube Data API v3):
  * The API is free but capped at 10,000 quota units/day per project.
  * Each video upload costs 1,600 units  ->  ~6 uploads/day by default.
  * Captions cost 200 units each; playlist creates/updates cost 50.
  * Quota resets at midnight Pacific. Extra quota requires Google's
    extension review (free, but slow — see docs/YOUTUBE_CHANNEL_SETUP.md).
  * 1,200 videos / 6 per day = ~200 days via the API alone. Practical
    alternatives: (a) request a quota extension, (b) ALSO upload in batches
    through YouTube Studio in your browser (community-observed ~10-50/day on
    newer channels), (c) run newest-first so the channel is useful immediately.

Setup (one time):
  1. Create the channel (docs/YOUTUBE_CHANNEL_SETUP.md) and phone-verify it
     (required for videos longer than 15 minutes — council meetings are hours).
  2. In Google Cloud Console: new project -> enable "YouTube Data API v3" ->
     create OAuth client (Desktop app) -> download client_secrets.json into
     this folder. Add yourself as a test user if the app is in Testing mode.
  3. pip install -r requirements.txt

Usage:
  python scripts/upload_youtube.py --max 6                    # one day's quota
  python scripts/upload_youtube.py --max 6 --privacy unlisted # review first (default)
  python scripts/upload_youtube.py --max 2 --dry-run          # show what would upload
  python scripts/upload_youtube.py --only-date 2026-08-24     # single video test
  python scripts/upload_youtube.py --newest-first             # recommended
  python scripts/upload_youtube.py --skip-captions            # save quota
"""
import argparse, csv, glob, json, os, random, sys, time

SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube"]
CATEGORY_NEWS_POLITICS = "25"
VALID_PRIVACY = ("public", "private", "unlisted")


def load_plan(path):
    with open(path, newline="", encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if r.get("action") == "upload"]


def resolve_file(expected: str, source_id: str, source: str):
    """Find the downloaded video; tolerate extension differences."""
    if expected and os.path.exists(expected):
        return expected
    base = f"videos/archiveorg/ia_{source_id}" if source == "archiveorg" else None
    if base:
        hits = [p for ext in (".mp4", ".mpeg4", ".mov", ".webm", ".mkv")
                for p in glob.glob(base + ext)]
        if hits:
            return hits[0]
    return None


def find_caption(video_path: str):
    stem = os.path.splitext(video_path)[0]
    for ext in (".vtt", ".srt"):
        if os.path.exists(stem + ext):
            return stem + ext
    return None


def get_service(secrets_path: str, token_path: str):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(secrets_path, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w") as f:
            f.write(creds.to_json())
    return build("youtube", "v3", credentials=creds)


def resumable_upload(service, path, body, chunk_mb=8):
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload
    media = MediaFileUpload(path, chunksize=chunk_mb * 1024 * 1024, resumable=True)
    req = service.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    retries = 0
    while response is None:
        try:
            status, response = req.next_chunk()
            if status:
                print(f"\r  uploading... {int(status.progress() * 100)}%", end="", flush=True)
        except HttpError as e:
            if e.resp.status in (500, 502, 503, 504):
                retries += 1
                if retries > 8:
                    raise
                time.sleep(2 ** retries + random.random())
            else:
                raise
    print("\r  uploading... 100%")
    return response


def ensure_playlist(service, title, cache):
    if title in cache:
        return cache[title]
    # look for existing playlist with same title on the channel
    page = None
    while True:
        resp = service.playlists().list(part="snippet", mine=True,
                                        maxResults=50, pageToken=page).execute()
        for pl in resp.get("items", []):
            if pl["snippet"]["title"].strip().lower() == title.strip().lower():
                cache[title] = pl["id"]
                return pl["id"]
        page = resp.get("nextPageToken")
        if not page:
            break
    body = {"snippet": {"title": title,
                        "description": f"City of Cheyenne, Wyoming — {title}. "
                                       "Unofficial public archive."},
            "status": {"privacyStatus": "public"}}
    created = service.playlists().insert(part="snippet,status", body=body).execute()
    cache[title] = created["id"]
    print(f"  created playlist '{title}' ({created['id']})")
    return created["id"]


def add_to_playlist(service, playlist_id, video_id):
    service.playlistItems().insert(
        part="snippet",
        body={"snippet": {"playlistId": playlist_id,
                          "resourceId": {"kind": "youtube#video", "videoId": video_id}}}
    ).execute()


def upload_caption(service, video_id, path):
    from googleapiclient.http import MediaFileUpload
    media = MediaFileUpload(path, mimetype="text/vtt" if path.endswith(".vtt") else "text/plain",
                            resumable=False)
    return service.captions().insert(
        part="snippet", body={"snippet": {"videoId": video_id, "language": "en",
                                          "name": "English (auto-imported)",
                                          "isDraft": False}}, media_body=media).execute()


def main():
    ap = argparse.ArgumentParser(description="Bulk upload Cheyenne archive to YouTube.")
    ap.add_argument("--plan", default="upload_plan.csv")
    ap.add_argument("--secrets", default="client_secrets.json")
    ap.add_argument("--token", default="yt_token.json")
    ap.add_argument("--state", default="upload_state.json")
    ap.add_argument("--max", type=int, default=6, help="max uploads this run (quota!)")
    ap.add_argument("--privacy", default="unlisted", choices=VALID_PRIVACY)
    ap.add_argument("--category", default=CATEGORY_NEWS_POLITICS)
    ap.add_argument("--newest-first", action="store_true")
    ap.add_argument("--only-date", default="")
    ap.add_argument("--only-source", default="", choices=("", "granicus", "archiveorg"))
    ap.add_argument("--skip-captions", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    plan = load_plan(args.plan)
    if args.only_date:
        plan = [r for r in plan if r["date_iso"] == args.only_date]
    if args.only_source:
        plan = [r for r in plan if r["source"] == args.only_source]
    plan.sort(key=lambda r: r["date_iso"] or "", reverse=args.newest_first)

    state = {}
    if os.path.exists(args.state):
        state = json.load(open(args.state, encoding="utf-8"))
    todo = [r for r in plan if f"{r['source']}:{r['source_id']}" not in state]
    print(f"Plan rows: {len(plan)} | already uploaded: {len(plan) - len(todo)} | "
          f"to do: {len(todo)}")

    # resolve local files first so dry runs and missing-file reports are instant
    ready, missing = [], []
    for r in todo:
        path = resolve_file(r["expected_file"], r["source_id"], r["source"])
        (ready if path else missing).append((r, path))
    if missing:
        print(f"\n{len(missing)} rows have no downloaded file yet (download first):")
        for r, _ in missing[:10]:
            print(f"  {r['date_iso']} {r['source']}:{r['source_id']} -> {r['expected_file']}")
        if len(missing) > 10:
            print(f"  ... and {len(missing) - 10} more")
    ready = ready[:args.max]
    print(f"\nReady to upload this run: {len(ready)} (cap: --max {args.max})")
    for r, path in ready:
        print(f"  {r['date_iso']} | {os.path.basename(path)} | {r['youtube_title'][:70]}")
    if args.dry_run or not ready:
        print("\nDry run — nothing uploaded." if args.dry_run else "\nNothing to do.")
        return

    if not os.path.exists(args.secrets):
        sys.exit(f"Missing {args.secrets} — see docs/YOUTUBE_CHANNEL_SETUP.md step 2.")
    service = get_service(args.secrets, args.token)
    playlists = {}
    done = 0
    for r, path in ready:
        key = f"{r['source']}:{r['source_id']}"
        print(f"\n[{done + 1}/{len(ready)}] {r['youtube_title']}")
        print(f"  file: {path} ({os.path.getsize(path) / 1e6:.0f} MB)")
        body = {"snippet": {"title": r["youtube_title"][:100],
                            "description": r["description"],
                            "tags": [t.strip() for t in r["tags"].split(",") if t.strip()][:20],
                            "categoryId": args.category,
                            "defaultLanguage": "en"},
                "status": {"privacyStatus": args.privacy,
                           "selfDeclaredMadeForKids": False}}
        try:
            resp = resumable_upload(service, path, body)
            vid = resp["id"]
            print(f"  uploaded: https://youtu.be/{vid}")
            try:
                pid = ensure_playlist(service, r["playlist"], playlists)
                add_to_playlist(service, pid, vid)
                print(f"  playlist: {r['playlist']}")
            except Exception as e:  # noqa: BLE001
                print(f"  WARNING playlist step failed (video is up): {e}")
            if not args.skip_captions:
                cap = find_caption(path)
                if cap:
                    try:
                        upload_caption(service, vid, cap)
                        print(f"  caption: {os.path.basename(cap)}")
                    except Exception as e:  # noqa: BLE001
                        print(f"  WARNING caption failed (non-fatal): {e}")
            state[key] = {"video_id": vid, "title": r["youtube_title"],
                          "uploaded_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
            json.dump(state, open(args.state, "w", encoding="utf-8"), indent=2)
            done += 1
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            print(f"  FAILED: {msg[:300]}")
            if "quotaExceeded" in msg:
                print("\nDaily API quota exhausted. State saved — run again after "
                      "midnight Pacific (or request a quota extension).")
                break
            print("Continuing with next video...")
    print(f"\nUploaded this run: {done}. Total in state file: {len(state)}.")


if __name__ == "__main__":
    main()
