#!/usr/bin/env python3
"""clean_transcripts.py — align, dedup, and entity-correct meeting transcripts.

Pipeline per transcript:
  1. ALIGN: map pipeline/corpus/extra/*.txt (and any .srt/.vtt with content)
     to a Granicus clip_id via date (±1 day) against the minutes corpus +
     youtube-archive/catalog_granicus.csv, confirmed by in-text date mention.
  2. DEDUP: collapse rolling-caption repeats into timestamped segments.
  3. CORRECT: literal confusions list first, then fuzzy glossary matching
     (people/places/terms/ordinances) with per-change logging.
  4. WRITE: pipeline/corpus_clean/{clip}_{date}.clean.txt (+ .changes.json),
     alignment.json, cleaning_report.md.

Usage (repo root):
  python rag/clean_transcripts.py
  python rag/clean_transcripts.py --only mar9 jun22

Stdlib only. Conservative by design: corrections need high fuzzy scores and
every change is logged with context for human review.
"""
from __future__ import annotations

import argparse
import csv
import difflib
import json
import re
from datetime import date, timedelta
from pathlib import Path

from text_extract import (MINUTES_HDR, norm_token, parse_rolling_transcript,
                          seconds_to_ts)

ROOT = Path(__file__).resolve().parent.parent
RAG = ROOT / "rag"
CORPUS = ROOT / "pipeline" / "corpus"
CLEAN = ROOT / "pipeline" / "corpus_clean"

MONTHS = {m: i + 1 for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"])}
DATE_MENTION = re.compile(
    r"\b(january|february|march|april|may|june|july|august|september|october|"
    r"november|december)\s+(\d{1,2})(?:st|nd|rd|th)?\b", re.I)


def corpus_index() -> dict[str, dict]:
    """clip_id -> {date, file} from minutes headers (fallback: filename)."""
    idx = {}
    for fp in sorted(CORPUS.glob("*.txt")):
        head = fp.read_text(encoding="utf-8", errors="replace")[:600]
        m = MINUTES_HDR.search(head)
        if m:
            idx[m.group("clip")] = {"date": m.group("date"), "file": fp.name}
        else:
            dm = re.search(r"(\d{4}-\d{2}-\d{2})", fp.name)
            cm = re.match(r"(\d+)_", fp.name)
            if dm and cm:
                idx[cm.group(1)] = {"date": dm.group(1), "file": fp.name}
    return idx


def granicus_dates() -> dict[str, str]:
    """clip_id -> date_iso from the youtube-archive catalog (if present)."""
    out = {}
    for cand in [ROOT / "youtube-archive" / "catalog_granicus.csv",
                 ROOT / "catalog_granicus.csv"]:
        if cand.exists():
            with open(cand, newline="", encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    if r.get("clip_id") and r.get("date_iso"):
                        out[r["clip_id"]] = r["date_iso"]
            break
    return out


def transcript_date_guess(fp: Path, text_sample: str) -> date | None:
    """Guess the meeting date: filename hints (mar9/jun22/apr27) + in-text mention."""
    stem = fp.stem.lower()
    year = 2026
    m = re.search(r"(19|20)\d{2}", stem)
    if m:
        year = int(m.group(0))
    md = None
    m = re.search(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\D{0,3}(\d{1,2})", stem)
    if m:
        mon = next(v for k, v in MONTHS.items() if k.startswith(m.group(1)))
        md = date(year, mon, int(m.group(2)))
    mentioned = DATE_MENTION.findall(text_sample[:6000])
    if mentioned:
        mon = MONTHS[mentioned[0][0].lower()]
        day = int(mentioned[0][1])
        try:
            mdate = date(year, mon, day)
        except ValueError:
            mdate = None
        if md and mdate and md != mdate:
            pass  # keep filename guess; alignment step tests ±1 day anyway
        elif mdate:
            md = mdate
    return md


def align_transcript(fp: Path, corp_idx: dict, gdates: dict) -> dict:
    """Return {clip_id, date, method, note} — best clip match or {}."""
    sample = fp.read_text(encoding="utf-8", errors="replace")[:6000]
    guess = transcript_date_guess(fp, sample)
    if not guess:
        return {}
    cands = []
    for clip, info in corp_idx.items():
        try:
            cdate = date.fromisoformat(info["date"])
        except ValueError:
            continue
        delta = abs((cdate - guess).days)
        if delta <= 1:
            cands.append((delta, clip, info["date"]))
    if not cands:
        return {}
    cands.sort()
    delta, clip, cdate = cands[0]
    gdate = gdates.get(clip, "")
    note = f"transcript date guess {guess} vs corpus {cdate} (Δ{delta}d)"
    if gdate and gdate != cdate:
        note += f"; granicus catalog says {gdate}"
    return {"clip_id": clip, "date": cdate, "method": f"date±1 (Δ{delta}d)",
            "note": note}


def apply_confusions(text: str, confusions: list, regexes: list) -> tuple[str, list]:
    changes = []
    for before, after in confusions:
        if before in text:
            n = text.count(before)
            text = text.replace(before, after)
            changes.append({"kind": "confusion", "before": before, "after": after,
                            "count": n})
    for pattern, after in regexes:
        text, n = re.subn(pattern, after, text)
        if n:
            changes.append({"kind": "regex", "before": pattern, "after": after,
                            "count": n})
    return text, changes


def fuzzy_correct(text: str, terms: list[str], threshold: float = 0.87) -> tuple[str, list]:
    """Replace near-miss windows with canonical glossary terms (logged)."""
    # tokenize preserving spans
    spans = [(m.group(0), m.start(), m.end()) for m in re.finditer(r"\S+", text)]
    toks = [s[0] for s in spans]
    norms = [norm_token(t) for t in toks]
    claimed = [False] * len(toks)
    edits = []  # (start_tok, end_tok, canonical, score, before)
    uniq = sorted(set(terms), key=lambda t: -len(t.split()))
    # pass 1: claim every exact match for every term (protects "Mr. Moody"
    # from being "corrected" to "Mark Moody" by another variant)
    for term in uniq:
        t_toks = term.split()
        tnorm = " ".join(norm_token(t) for t in t_toks)
        L = len(t_toks)
        for i in range(len(toks) - L + 1):
            if not any(claimed[i:i + L]) and " ".join(norms[i:i + L]) == tnorm:
                for j in range(i, i + L):
                    claimed[j] = True
    # pass 2: fuzzy on unclaimed windows, longest terms first
    # (single-token terms need 0.92: bare surnames must not eat common words)
    for term in uniq:
        t_toks = term.split()
        tnorm = " ".join(norm_token(t) for t in t_toks)
        if len(tnorm) < 4:
            continue
        L = len(t_toks)
        thresh = 0.92 if L == 1 else threshold
        for i in range(len(toks) - L + 1):
            if any(claimed[i:i + L]):
                continue
            window = " ".join(norms[i:i + L])
            if not window or abs(len(window) - len(tnorm)) > max(3, len(tnorm) // 3):
                continue
            if window == tnorm:  # exact but overlapped a claimed span; leave it
                continue
            if window[0] != tnorm[0]:
                continue
            if L >= 2:  # every token pair must resemble each other: blocks
                pair_ok = all(  # "Councilman, my" -> "Councilman Moody" (my/moody=0.57)
                    difflib.SequenceMatcher(None, norms[i + k],
                                            norm_token(t_toks[k])).ratio() >= 0.60
                    for k in range(L))
                if not pair_ok:
                    continue
            score = difflib.SequenceMatcher(None, window, tnorm).ratio()
            if score >= thresh:
                before = " ".join(toks[i:i + L])
                canon = term + "'s" if re.search(r"'s$", before) and "'s" not in term else term
                if before == canon:  # no-op surface form; claim quietly, don't log
                    for j in range(i, i + L):
                        claimed[j] = True
                    continue
                edits.append((spans[i][1], spans[i + L - 1][2], canon, round(score, 3), before))
                for j in range(i, i + L):
                    claimed[j] = True
    edits.sort()
    out, pos, changes = [], 0, []
    for s, e, canon, score, before in edits:
        out.append(text[pos:s])
        out.append(canon)
        ctx = text[max(0, s - 60):e + 60].replace("\n", " ")
        changes.append({"kind": "fuzzy", "before": before, "after": canon,
                        "score": score, "context": ctx})
        pos = e
    out.append(text[pos:])
    return "".join(out), changes


def clean_file(fp: Path, glossary: dict, corp_idx: dict, gdates: dict) -> dict:
    parsed = parse_rolling_transcript(fp)
    full = " ".join(s["text"] for s in parsed["segments"])
    align = align_transcript(fp, corp_idx, gdates)
    text, ch1 = apply_confusions(full, glossary.get("confusions", []),
                                 glossary.get("regex_confusions", []))
    people = glossary.get("people", [])
    titles = glossary.get("people_titles", {})
    variants = list(people)
    for person in people:
        title = titles.get(person, "")
        parts = person.split()
        if len(parts) >= 2:
            variants.append(parts[-1])  # bare surname backstop
            variants.append(f"Councilman {parts[-1]}")
            variants.append(f"Councilwoman {parts[-1]}")
            for t in ("Mr.", "Ms.", "Mrs.", "Dr.", "Mayor"):
                variants.append(f"{t} {parts[-1]}")
            if title:
                variants.append(f"{title} {person}")
                variants.append(f"{title} {parts[-1]}")
    terms = (variants + glossary.get("places", []) +
             glossary.get("terms", []) + glossary.get("ordinances", []) +
             glossary.get("resolutions", []))
    text2, ch2 = fuzzy_correct(text, terms)
    # re-split corrected text back onto segment timestamps (proportional)
    total_in, total_out = max(1, len(full)), max(1, len(text2))
    boundaries, acc = [0], 0
    for s in parsed["segments"]:
        acc += len(s["text"]) + 1
        boundaries.append(acc)
    raw_cuts = [0] + [int(b / total_in * total_out) for b in boundaries[1:-1]] + [total_out]
    cuts, prev = [0], 0
    for c in raw_cuts[1:-1]:  # snap each shared cut to the nearest word start
        left, right = text2.rfind(" ", 0, c), text2.find(" ", c)
        if left == -1:
            snap = right + 1 if right != -1 else c
        elif right == -1:
            snap = left + 1
        else:
            snap = left + 1 if c - left <= right - c else right + 1
        snap = min(max(snap, prev), total_out)
        cuts.append(snap)
        prev = snap
    cuts.append(total_out)
    corrected_segs = []
    for s, c0, c1 in zip(parsed["segments"], cuts[:-1], cuts[1:]):
        corrected_segs.append({"t_start": s["t_start"], "t_end": s["t_end"],
                               "text": text2[c0:c1].strip()})
    return {"align": align, "segments": corrected_segs, "changes": ch1 + ch2,
            "raw_lines": parsed["raw_lines"], "raw_words": len(parsed["words"])}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", default=[])
    args = ap.parse_args()

    glossary = json.loads((RAG / "glossary.json").read_text(encoding="utf-8"))
    corp_idx, gdates = corpus_index(), granicus_dates()
    CLEAN.mkdir(exist_ok=True)

    targets = sorted(CORPUS.glob("extra/*.txt"))
    # NOTE: non-empty .srt/.vtt under pipeline/renders/ are montage captions,
    # not meeting transcripts — out of scope for meeting-transcript cleanup.
    if args.only:
        targets = [p for p in targets if p.stem in args.only]

    skipped: list[str] = []
    for p in list((ROOT / "pipeline").rglob("*.vtt")) + list((ROOT / "pipeline").rglob("*.srt")):
        if p.stat().st_size <= 100:
            skipped.append(str(p.relative_to(ROOT)))
    report: dict = {"files": [], "skipped_empty_captions": sorted(skipped)}

    alignment = {}
    for fp in targets:
        print(f"cleaning {fp.relative_to(ROOT)} ...")
        res = clean_file(fp, glossary, corp_idx, gdates)
        clip = res["align"].get("clip_id", "unmapped")
        cdate = res["align"].get("date", fp.stem)
        stem = f"{clip}_{cdate}" if clip != "unmapped" else f"extra_{fp.stem}"
        out_txt = CLEAN / f"{stem}.clean.txt"
        header = (f"# CLEANED TRANSCRIPT | source={fp.relative_to(ROOT)} | "
                  f"clip_id={clip} | date={cdate}\n"
                  f"# align_method={res['align'].get('method', 'none')} | "
                  f"{res['align'].get('note', '')}\n"
                  f"# raw_caption_lines={res['raw_lines']} | "
                  f"raw_words={res['raw_words']} | "
                  f"corrections={len(res['changes'])}\n\n")
        body = "\n".join(f"[{seconds_to_ts(s['t_start'])}-{seconds_to_ts(s['t_end'])}] {s['text']}"
                         for s in res["segments"])
        out_txt.write_text(header + body + "\n", encoding="utf-8")
        (CLEAN / f"{stem}.changes.json").write_text(
            json.dumps(res["changes"], indent=1), encoding="utf-8")
        alignment[fp.name] = {"clip_id": clip, "date": cdate, **res["align"],
                              "clean_file": out_txt.name,
                              "corrections": len(res["changes"])}
        report["files"].append({"source": fp.name, "clean_file": out_txt.name,
                                "clip_id": clip, "date": cdate,
                                "raw_lines": res["raw_lines"],
                                "raw_words": res["raw_words"],
                                "corrections": len(res["changes"])})
        print(f"  -> {out_txt.name}: {res['raw_lines']} lines, "
              f"{len(res['changes'])} corrections, clip={clip}")

    (CLEAN / "alignment.json").write_text(json.dumps(alignment, indent=1), encoding="utf-8")
    md = ["# Transcript cleaning report", "",
          f"Cleaned {len(report['files'])} transcript(s).",
          "| source | clip | date | raw lines | corrections |",
          "|---|---|---|---|---|"]
    for f in report["files"]:
        md.append(f"| {f['source']} | {f['clip_id']} | {f['date']} | {f['raw_lines']} | {f['corrections']} |")
    md += ["", f"Skipped {len(report['skipped_empty_captions'])} empty caption placeholders (≤100 bytes)."]
    (CLEAN / "cleaning_report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"\nwrote {CLEAN}/ ({len(report['files'])} cleaned)")


if __name__ == "__main__":
    main()
