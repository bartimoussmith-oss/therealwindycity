# ═════════════════════════════════════════════════════════════════════════════
#  THE REAL WINDY CITY — MEDIA BACKFILL CELL
#
#  Fills the record with every indexed meeting's media:
#    · auto-captions (VTT) for all 260 city YouTube meetings  -> pipeline/captions/ (in git)
#    · full-meeting audio (m4a ~64kbps)                      -> GitHub Releases (no git bloat)
#    · full-meeting video (480p mp4)  — ONLY in MODE="full"  -> GitHub Releases (2GB/asset cap)
#
#  Paste into one Colab cell and run. Resumable: re-run anytime, it skips
#  what's already done. Commits in batches of 10 so a disconnect loses nothing.
#
#  ⚙️ EDIT THIS ONE LINE to choose depth:
MODE = "captions"      # "captions" (~25 min) | "audio" (~3-8 h) | "full" (video too; ~1-2 days, huge)
#
#  Honest limits, stated up front:
#    · Video does NOT go into git — GitHub caps files at 100 MB and 260
#      meetings ≈ 130 GB. Releases hold it (2 GB/asset), but that is a lot
#      of bandwidth; captions+audio is the sweet spot.
#    · YouTube auto-captions are machine transcripts — good for search and
#      jumping, not quotable like the clerk-written record.
#    · We honor robots.txt: city-site agendas/minutes are collectible;
#      Granicus historical packets stay with the clerk (PRA bench can draft it).
# ═════════════════════════════════════════════════════════════════════════════
import json, os, re, shutil, subprocess, sys, time
import urllib.request, urllib.error
from pathlib import Path

REPO    = "bartimoussmith-oss/therealwindycity"
WORKDIR = Path("/content/wc-media")

def sh(cmd, cwd=None, timeout=1800, check=False):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    out = ((r.stdout or "") + (r.stderr or "")).strip()
    if check and r.returncode != 0:
        raise RuntimeError(f"CMD FAILED: {' '.join(map(str, cmd[:4]))}\n{out[-500:]}")
    return r.returncode, out

def step(m): print(f"\n{'═'*66}\n  {m}\n{'═'*66}", flush=True)

# ── 0 · token ────────────────────────────────────────────────────────────────
tok = None
try:
    from google.colab import userdata
    tok = userdata.get("GH_PAT")
except Exception:
    pass
if not tok:
    import getpass
    tok = getpass.getpass("GitHub token (GH_PAT): ").strip()
TOKEN = tok

def api(path, data=None, method=None, binary=None, ctype="application/json"):
    url = path if path.startswith("http") else f"https://api.github.com/repos/{REPO}/{path}"
    req = urllib.request.Request(url, method=method or ("POST" if data is not None or binary is not None else "GET"))
    req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Accept", "application/vnd.github+json")
    if binary is not None:
        req.add_header("Content-Type", ctype)
        body = binary
    elif data is not None:
        body = json.dumps(data).encode()
    else:
        body = None
    try:
        with urllib.request.urlopen(req, body=body, timeout=600) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw and raw[:1] in (b"{", b"[") else {})
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read() or b"{}")
        except Exception: return e.code, {}

step("0/6  Preflight")
st, me = api("https://api.github.com/user")
print("  token:", me.get("login"), f"({st})")
assert st == 200 and me.get("login"), "token rejected"
st, rep = api(f"https://api.github.com/repos/{REPO}")
print("  repo:", rep.get("full_name"), "| push:", rep.get("permissions", {}).get("push"))
assert rep.get("permissions", {}).get("push"), "token cannot push"

step("1/6  Clone + tooling")
shutil.rmtree(WORKDIR, ignore_errors=True)
sh(["git", "clone", "--depth", "1", "-b", "main",
    f"https://github.com/{REPO}.git", str(WORKDIR)], check=True, timeout=600)
os.chdir(WORKDIR)
sh(["git", "config", "user.name", "bartimoussmith-oss"], check=True)
sh(["git", "config", "user.email", "236240326+bartimoussmith-oss@users.noreply.github.com"], check=True)
print("  installing yt-dlp…")
sh([sys.executable, "-m", "pip", "install", "-q", "yt-dlp"], check=True, timeout=600)
rc, out = sh(["yt-dlp", "--version"])
print("  yt-dlp", out)

step("2/6  Load the meeting index + manifest")
cv = json.loads(Path("pipeline/cityvideos.json").read_text())
meetings = {d: (m.get("id") if isinstance(m, dict) else m)
            for d, m in cv.get("meetings", {}).items() if m}
print(f"  {len(meetings)} indexed meetings, {min(meetings)} → {max(meetings)}")
MAN = Path("pipeline/media_manifest.json")
if MAN.exists():
    manifest = json.loads(MAN.read_text())
else:
    manifest = {"generated_at": "", "source": "tools/colab_media_backfill.py",
                "note": "Auto-captions are machine transcripts — search/jump-grade, "
                        "not quotable like the clerk record. Audio/Video assets live "
                        "in GitHub Releases (media-<year> tags).",
                "meetings": {}}
mm = manifest["meetings"]
CAP = Path("pipeline/captions"); CAP.mkdir(parents=True, exist_ok=True)

def commit_all(msg):
    rc, staged = sh(["git", "add", "-A"])
    rc, out = sh(["git", "status", "--porcelain"])
    if not out:
        return
    sh(["git", "commit", "-qm", msg], check=True)
    for attempt in range(2):
        rc, out = sh(["git", "push", f"https://x-access-token:{TOKEN}@github.com/{REPO}.git",
                      "HEAD:main"])
        if rc == 0:
            return
        sh(["git", "pull", "--rebase", "-q", "origin", "main"])
    raise RuntimeError("push failed twice: " + out[-300:])

# ── 3 · captions for every meeting ───────────────────────────────────────────
step("3/6  Auto-captions (VTT) — resumable")
done = sum(1 for v in mm.values() if v.get("captions"))
todo = [d for d in sorted(meetings) if not mm.get(d, {}).get("captions")]
print(f"  already done: {done} | to fetch: {len(todo)}")
batch = 0
for i, date in enumerate(todo, 1):
    ytid = meetings[date]
    out_tpl = str(CAP / f"{date}_%(id)s")
    rc, out = sh(["yt-dlp", "--skip-download", "--write-auto-subs",
                  "--sub-langs", "en.*,en", "--convert-subs", "vtt",
                  "-o", out_tpl, f"https://www.youtube.com/watch?v={ytid}"],
                 timeout=300)
    vtt = next((f for f in sorted(CAP.glob(f"{date}_*.vtt"))), None)
    if vtt:
        final = CAP / f"{date}.vtt"
        if final.exists():
            final.unlink()
        vtt.rename(final)
        mm.setdefault(date, {})["yt"] = ytid
        mm[date]["captions"] = f"pipeline/captions/{date}.vtt"
        batch += 1
    else:
        mm.setdefault(date, {})["yt"] = ytid
        mm[date]["captions"] = None      # tried; none available
        batch += 1
    if i % 10 == 0:
        manifest["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        MAN.write_text(json.dumps(manifest, indent=1))
        commit_all(f"media: captions batch ({i}/{len(todo)})")
        print(f"  {i}/{len(todo)} committed", flush=True)
    time.sleep(1.5)                       # be polite
manifest["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
MAN.write_text(json.dumps(manifest, indent=1))
commit_all("media: captions pass complete")
n_caps = sum(1 for v in mm.values() if v.get("captions"))
print(f"  captions on disk: {n_caps} meetings")

# ── 4 · audio → GitHub Releases ─────────────────────────────────────────────
def get_or_make_release(year):
    tag = f"media-{year}"
    st, rels = api(f"releases?per_page=100")
    for r in (rels if isinstance(rels, list) else []):
        if r.get("tag_name") == tag:
            return r
    st, rel = api("releases", {"tag_name": tag, "name": f"Meeting audio {year}",
                               "body": "Full-meeting audio pulled from the City of "
                                       "Cheyenne's YouTube channel (public record)."})
    assert st in (200, 201), f"release create failed {st}: {rel}"
    return rel

def upload_asset(rel, name, path):
    have = {a["name"] for a in rel.get("assets", [])}
    if name in have:
        return None
    up = rel["upload_url"].replace("{?name,label}", "")
    with open(path, "rb") as f:
        data = f.read()
    req = urllib.request.Request(f"{up}?name={name}", data=data, method="POST")
    req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Content-Type", "application/octet-stream")
    with urllib.request.urlopen(req, timeout=3600) as r:
        return json.loads(r.read()).get("browser_download_url")

if MODE in ("audio", "full"):
    step("4/6  Full-meeting audio → GitHub Releases")
    todo = [d for d in sorted(meetings) if not mm.get(d, {}).get("audio")]
    print(f"  to fetch: {len(todo)} (this is the long part)")
    rel_cache = {}
    for i, date in enumerate(todo, 1):
        ytid = meetings[date]
        year = date[:4]
        tmp = Path("/content/wc-tmp-audio")
        shutil.rmtree(tmp, ignore_errors=True); tmp.mkdir()
        rc, out = sh(["yt-dlp", "-f", "bestaudio/best", "-x",
                      "--audio-format", "m4a", "--audio-quality", "64K",
                      "-o", str(tmp / "%(id)s.%(ext)s"),
                      f"https://www.youtube.com/watch?v={ytid}"], timeout=3600)
        f = next(iter(tmp.glob("*.m4a")), None) if rc == 0 else None
        if f:
            if year not in rel_cache:
                rel_cache[year] = get_or_make_release(year)
                st, rel_cache[year] = api(f"releases/tags/media-{year}")
            url = upload_asset(rel_cache[year], f"{date}_meeting.m4a", f)
            if url:
                mm.setdefault(date, {})["audio"] = url
                print(f"  {date}: uploaded", flush=True)
            else:
                print(f"  {date}: already on the release")
            # refresh asset list for next time
            st, r2 = api(f"releases/tags/media-{year}")
            if st == 200: rel_cache[year] = r2
        else:
            print(f"  {date}: audio unavailable")
        if i % 10 == 0:
            manifest["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            MAN.write_text(json.dumps(manifest, indent=1))
            commit_all(f"media: audio manifest batch ({i}/{len(todo)})")
        time.sleep(1.5)
    manifest["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    MAN.write_text(json.dumps(manifest, indent=1))
    commit_all("media: audio pass complete")
    print(f"  audio linked: {sum(1 for v in mm.values() if v.get('audio'))} meetings")
else:
    step("4/6  Audio skipped (MODE != audio/full) — edit MODE and re-run to add it")

# ── 5 · video (only MODE="full") ─────────────────────────────────────────────
if MODE == "full":
    step("5/6  Full-meeting video (480p) → GitHub Releases — the BIG one")
    print("  WARNING: hundreds of GB at 260 meetings; consider archive.org instead.")
    todo = [d for d in sorted(meetings) if not mm.get(d, {}).get("video")]
    rel_cache = {}
    for i, date in enumerate(todo, 1):
        ytid = meetings[date]
        year = date[:4]
        tmp = Path("/content/wc-tmp-video"); shutil.rmtree(tmp, ignore_errors=True); tmp.mkdir()
        rc, out = sh(["yt-dlp", "-f", "bv*[height<=480]+ba/b[height<=480]",
                      "--merge-output-format", "mp4",
                      "-o", str(tmp / "%(id)s.%(ext)s"),
                      f"https://www.youtube.com/watch?v={ytid}"], timeout=7200)
        f = next(iter(tmp.glob("*.mp4")), None) if rc == 0 else None
        if f and f.stat().st_size < 2_000_000_000:   # release asset cap
            if year not in rel_cache:
                st, rel_cache[year] = api(f"releases/tags/media-video-{year}")
                if st != 200:
                    st, rel_cache[year] = api("releases", {
                        "tag_name": f"media-video-{year}",
                        "name": f"Meeting video {year}"})
            url = upload_asset(rel_cache[year], f"{date}_meeting.mp4", f)
            if url:
                mm.setdefault(date, {})["video"] = url
                print(f"  {date}: uploaded", flush=True)
        else:
            print(f"  {date}: skipped (missing or ≥2GB)")
        if i % 5 == 0:
            manifest["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            MAN.write_text(json.dumps(manifest, indent=1))
            commit_all(f"media: video manifest batch ({i}/{len(todo)})")
        time.sleep(1.5)
    manifest["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    MAN.write_text(json.dumps(manifest, indent=1))
    commit_all("media: video pass complete")
else:
    step("5/6  Video skipped (MODE != full)")

# ── 6 · self-install + finish ────────────────────────────────────────────────
step("6/6  Install the tool into the repo + wrap up")
tools = Path("tools"); tools.mkdir(exist_ok=True)
# (this tool is kept in the repo at tools/colab_media_backfill.py —
#  committed by the maintainer; no fragile self-extraction here)
n_caps = sum(1 for v in mm.values() if v.get("captions"))
n_aud  = sum(1 for v in mm.values() if v.get("audio"))
n_vid  = sum(1 for v in mm.values() if v.get("video"))
print(f"""
  ─────────────────────────────────────────────────────────────────
   MEDIA BACKFILL DONE ✅
     captions: {n_caps} meetings   (in git — instantly searchable)
     audio:    {n_aud} meetings   (GitHub Releases)
     video:    {n_vid} meetings   (GitHub Releases)

   The 🎬 Video vault → "📼 Recordings & captions" view on the site
   picks all of this up automatically. Re-run this cell anytime to
   pick up new meetings — it skips what's already done.
  ─────────────────────────────────────────────────────────────────""")
