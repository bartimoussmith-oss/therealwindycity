#!/usr/bin/env python3
"""Cue every Charles Miller intervention against timestamped YouTube captions.

Reads the MILLER_EVERYTHING compilation in uploads/mega_file.md (484 Miller
Turn blocks + 132 Context/Interruption blocks across 20 `# VIDEO:` sections),
aligns each block to that video's caption track, classifies it, and writes
pipeline/miller_interventions.json — the cue sheet behind pages/2_Miller_Tapes.py.

Captions are NOT committed (11MB, refetchable). Before (re)running:
  mkdir -p pipeline/miller_captions
  for id in <20 ids>; do yt-dlp -q --skip-download --write-auto-subs \\
    --sub-langs "en.*" --sub-format vtt \\
    --extractor-args "youtube:player_client=android" \\
    -o "pipeline/miller_captions/$id.%(ext)s" \\
    "https://www.youtube.com/watch?v=$id"; done
(The android player client is required: the default client reports most City
videos "not available" even though they are public.)

Stdlib only. Usage:  python3 pipeline/build_miller_index.py
"""
import bisect
import html
import json
import re
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MEGA = ROOT / "uploads" / "mega_file.md"
CITY = ROOT / "pipeline" / "cityvideos.json"
CAPDIR = ROOT / "pipeline" / "miller_captions"
OUT = ROOT / "pipeline" / "miller_interventions.json"

# IDs absent from cityvideos.json, resolved via YouTube oEmbed (all City of Cheyenne).
OEMBED_FALLBACK = {
    "69FQxIr9sJA": ("2026-06-08", "City Council - 06-08-26", "City Council"),
    "6dPLuulCpbI": ("2026-07-13", "City Council - 07-13-26", "City Council"),
    "Dfqmg--DVPE": ("2026-01-12", "City Council - 01-12-26", "City Council"),
    "GcTnJFfrApg": ("2026-06-01", "June 1, 2026, Cheyenne Planning Commission Meeting", "Planning Commission"),
    "OxeCnRnBLkU": ("2026-02-09", "City Council - 02-09-26", "City Council"),
    "S49bb5GfUro": ("2026-07-27", "City Council - 07-27-26", "City Council"),
    "bGt1XMfaTTw": ("2026-05-26", "City Council - 05-26-26", "City Council"),
    "mPv73_3Clls": ("2026-04-13", "City Council - 04-13-26", "City Council"),
    "vBJi7WeZ4C0": ("2026-05-11", "City Council - 05-11-26", "City Council"),
    "x6Veeticz3Q": ("2026-01-26", "City Council - 01-26-26", "City Council"),
}

STOP = set("""a an the and or but if then else when while of at by for with about
into over after before between through during above below up down out off on in to from as is are was were
be been being am have has had having do does did doing would could should may might must shall will can
just very really quite so such no not yes yeah uh um ah er oh well hey hi hello thank thanks please sorry
ok okay right now today tonight here there where what which who whom whose why how i me my we us our you
your he him his she her it its they them their this that these those than too also""".split())

RX_FW = re.compile(r"on notice", re.I)
RX_FA = re.compile(r"mayor collins, members|members of the (city )?council"
                   r"|for the (permanent |administrative |public )?record", re.I)
RX_RESP = re.compile(r"^\s*>>[^>?!]{0,200}\?\s*>>")
RX_MIC = re.compile(r"cut.{0,25}microphone|cut.{0,12}\bmic\b|microphone.{0,15}(cut|muted|off)"
                    r"|mic.{0,12}cut|can['\u2019]t hear|lost.{0,15}audio|(?<!un)muted"
                    r"|cut off in zoom|being cut off|was cut off|got cut off", re.I)
RX_POO = re.compile(r"point of order|point-of-order", re.I)
RX_TIME = re.compile(r"time.{0,12}(up|expired|called)|your time|out of time|wrap.{0,8}up"
                     r"|30 seconds|conclud|please finish|time limit|expire[ds]"
                     r"|use.{0,10}time|remaining|one minute|two minutes", re.I)
RX_GAVEL = re.compile(r"gavel", re.I)


def toks(s):
    return re.findall(r"[a-z]+(?:'[a-z]+)?", s.lower())


def content(ts):
    return [t for t in ts if t not in STOP and len(t) > 1]


def parse_mega():
    """Yield (video_id, kind, n, text) for the 616 compilation blocks."""
    blocks, cur, n, kind, buf = [], None, 0, None, []
    in_miller = False
    def flush():
        if cur is not None and kind is not None and buf:
            text = "\n".join(l for l in buf if not l.startswith("## ")).strip()
            blocks.append((cur, kind, n, text))
    for line in MEGA.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("# MILLER_EVERYTHING"):
            in_miller = True
            continue
        if not in_miller:
            continue
        if line.startswith("# ") and not line.startswith("# VIDEO:") and "MILLER" not in line:
            break  # next document in the mega file
        m = re.match(r"^# VIDEO: (\S+)", line)
        if m:
            flush(); cur, kind, buf = m.group(1), None, []
            continue
        m = re.match(r"^### (Miller Turn|Context/Interruption) (\d+)\s*$", line)
        if m:
            flush()
            kind = "turn" if m.group(1) == "Miller Turn" else "context"
            n, buf = int(m.group(2)), []
            continue
        if kind is not None:
            buf.append(line)
    flush()
    return blocks


def parse_vtt(path):
    """Caption track -> word stream [(word, seconds)] with karaoke-dedupe."""
    def to_sec(h, m, s, ms):
        return (int(h or 0)) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000
    cues = []
    for blk in re.split(r"\n\s*\n", path.read_text(encoding="utf-8", errors="replace")):
        m = re.match(r"\s*(?:(\d+):)?(\d{2}):(\d{2})\.(\d{3})\s*-->\s*"
                     r"(?:(\d+):)?(\d{2}):(\d{2})\.(\d{3})[^\n]*\n([\s\S]*)", blk)
        if not m:
            continue
        body = html.unescape(re.sub(r"<[^>]+>", " ", m.group(9)))
        ws = toks(body)
        if ws:
            cues.append((to_sec(*m.group(1, 2, 3, 4)), to_sec(*m.group(5, 6, 7, 8)), ws))
    stream = []
    for s, e, ws in cues:
        tail = [w for w, _ in stream[-12:]]
        drop = 0
        for j in range(min(12, len(ws)), 0, -1):
            if tail[-j:] == ws[:j]:
                drop = j
                break
        for i in range(drop, len(ws)):
            stream.append((ws[i], s + (e - s) * (i / len(ws))))
    return stream


def best_run(needles, pos_index, lo, hi, gap=30, max_cand=600):
    """Best in-order run of needles between lo..hi. Returns (frac, start, end).

    Tries dropping up to 3 leading needles (block edges often start/end on a
    mid-word fragment that never matches) and keeps the variant with the most
    matches against the FULL needle count, tightest span winning ties.
    """
    full = len(needles)
    best = None
    for drop in range(min(4, len(needles))):
        sub = needles[drop:]
        cands = [p for p in pos_index.get(sub[0], []) if lo <= p <= hi][:max_cand]
        for c in cands:
            p, matched = c, 1
            for nd in sub[1:]:
                lst = pos_index.get(nd, [])
                q = bisect.bisect_right(lst, p)
                if q < len(lst) and lst[q] - p <= gap:
                    p, matched = lst[q], matched + 1
            key = (matched, -(p - c))
            if best is None or key > best[0]:
                best = (key, c, p)
    if best is None:
        return 0.0, lo, lo
    return best[0][0] / full, best[1], best[2]


def align(ct, cw, pos_index):
    """Content tokens -> (t0, t1, score). Head anchors freely, tail is bounded."""
    head = ct[:12]
    hfrac, hpos, _ = best_run(head, pos_index, 0, len(cw) - 1)
    tail = ct[-12:]
    tlim = hpos + max(800, 2 * len(ct))
    tfrac, _, tpos = best_run(tail, pos_index, hpos, min(tlim, len(cw) - 1))
    mid = ct[len(ct) // 2 - 6:len(ct) // 2 + 6]
    p, mhit = hpos, 0
    for nd in mid:
        lst = pos_index.get(nd, [])
        q = bisect.bisect_right(lst, p)
        if q < len(lst) and lst[q] <= tpos:
            p, mhit = lst[q], mhit + 1
    score = (hfrac + tfrac + (mhit / max(1, len(mid)))) / 3
    t0 = max(0.0, cw[hpos][1] - 1.0)
    t1 = cw[tpos][1] + 2.0
    return t0, t1, round(score, 4)


def classify(kind, text):
    if kind == "context":
        typ = "interruption"
    elif RX_FW.search(text):
        typ = "formal_warning"
    elif RX_RESP.search(text):
        typ = "response"
    elif RX_FA.search(text):
        typ = "testimony"
    else:
        typ = "statement"
    flags = {"mic_cut": bool(RX_MIC.search(text)),
             "point_of_order": bool(RX_POO.search(text)),
             "time_called": bool(RX_TIME.search(text)),
             "gavel": bool(RX_GAVEL.search(text))}
    flags["interrupted"] = (flags["mic_cut"] or flags["point_of_order"]
                            or flags["time_called"] or kind == "context")
    return typ, flags


def main():
    blocks = parse_mega()
    n_turn = sum(1 for b in blocks if b[1] == "turn")
    n_ctx = sum(1 for b in blocks if b[1] == "context")
    vids = sorted({b[0] for b in blocks})
    print(f"parsed: {len(blocks)} blocks ({n_turn} turns + {n_ctx} interruptions), {len(vids)} videos")
    assert len(blocks) == 616 and len(vids) == 20, "compilation shape changed!"

    city = json.loads(CITY.read_text())
    meta = {v["id"]: (d, v["title"], v["kind"]) for d, v in city["meetings"].items()}
    meta.update(OEMBED_FALLBACK)
    missing = [v for v in vids if v not in meta]
    assert not missing, f"videos without date/title: {missing}"

    caps = {}
    for v in vids:
        p = CAPDIR / f"{v}.en.vtt"
        assert p.exists(), f"missing captions for {v} (see docstring to fetch)"
        ws = parse_vtt(p)
        cw = [(w, t) for w, t in ws if (w not in STOP and len(w) > 1)]
        idx = {}
        for i, (w, _) in enumerate(cw):
            idx.setdefault(w, []).append(i)
        caps[v] = (cw, idx)

    out, missed, trunc = [], 0, 0
    for v, kind, n, text in blocks:
        cw, idx = caps[v]
        ct = content(toks(text))
        # Compilation artifacts: a block thousands of tokens long has alien
        # transcripts concatenated past its genuine head. Align on the first
        # 150 content tokens (verified verbatim zone) and flag it.
        pinched = len(ct) > 1500
        if pinched:
            ct, trunc = ct[:150], trunc + 1
        t0, t1, score = align(ct, cw, idx)
        if score < 0.5:
            missed += 1
        typ, flags = classify(kind, text)
        date, title, mkind = meta[v]
        out.append({"video": v, "date": date, "title": title, "mkind": mkind,
                    "block": kind, "n": n, "t0": round(t0, 1), "t1": round(t1, 1),
                    "dur": round(t1 - t0, 1), "type": typ, "flags": flags,
                    "score": score, "truncated_align": pinched, "text": text})

    # duplicate replay angles: union-find on >80% overlap, rank longest-first
    parent = list(range(len(out)))
    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    by_vid = {}
    for i, r in enumerate(out):
        by_vid.setdefault(r["video"], []).append(i)
    for js in by_vid.values():
        for x in range(len(js)):
            for y in range(x + 1, len(js)):
                a, b = out[js[x]], out[js[y]]
                ov = min(a["t1"], b["t1"]) - max(a["t0"], b["t0"])
                if ov > 0.8 * min(a["dur"], b["dur"]):
                    parent[find(js[x])] = find(js[y])
    groups = {}
    for i, r in enumerate(out):
        groups.setdefault(find(i), []).append(r)
    for gid, g in enumerate(sorted(groups.values(), key=lambda g: (g[0]["video"], g[0]["t0"]))):
        g.sort(key=lambda r: -r["dur"])
        for rank, r in enumerate(g):
            r["dup_group"], r["dup_rank"] = gid, rank
    out.sort(key=lambda r: (r["date"], r["video"], r["t0"]))

    # gold checks against the verified-tape index
    fails = []
    for date, v in city["verified_tape"].items():
        vid = v["id"]
        for feat, val in v.items():
            if feat == "id":
                continue
            for h, m, s in re.findall(r"(\d{2}):(\d{2}):(\d{2})", val):
                t = int(h) * 3600 + int(m) * 60 + int(s)
                ok = any(r["video"] == vid and r["t0"] <= t <= r["t1"] for r in out)
                print(f"gold {vid} {h}:{m}:{s} ({feat}): {'PASS' if ok else 'FAIL'}")
                if not ok:
                    fails.append((vid, val))

    OUT.write_text(json.dumps(out, ensure_ascii=False))
    scores = sorted(r["score"] for r in out)
    durs = sorted(r["dur"] for r in out)
    print(f"aligned: {len(out) - missed}/{len(out)}, missed: {missed}, pinched: {trunc}")
    print(f"score min/med: {scores[0]:.2f}/{statistics.median(scores):.2f}, "
          f"dur med/max: {durs[len(durs)//2]:.0f}s/{durs[-1]:.0f}s, "
          f"total: {sum(durs)/3600:.1f}h")
    from collections import Counter
    print("types:", dict(Counter(r["type"] for r in out)))
    print("flags:", {k: sum(1 for r in out if r["flags"][k])
                     for k in ("mic_cut", "point_of_order", "time_called", "gavel", "interrupted")})
    print(f"dup groups: {len(groups)} "
          f"({sum(1 for g in groups.values() if len(g) > 1)} with replays)")
    if fails:
        sys.exit(f"GOLD FAILURES: {fails}")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
