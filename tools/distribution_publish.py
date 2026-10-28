#!/usr/bin/env python3
"""Turn the alert ledger into something a person can actually receive.

The engine detects 303 alerts and terminates them in a database table and one
RSS file. Nothing routes them to a human. This tool builds the distribution
layer: triage, then publish to feeds and drafts.

WHY TRIAGE COMES FIRST. Measured against the live ledger: all 225 SILENT-EDIT
alerts fired on page scaffolding rather than document content — WordPress
asset-version cache-busters (`ver=4.36.3` → `ver=4.36.5`), `<link rel=stylesheet>`
tags, `data-pmdelayedstyle` timestamps, Akamai mPulse RUM beacons
(`s.go-mpulse.net/boomerang`), and inline polyfill JavaScript
(`document.createElement`, `window.addEventListener`, `navigator.userAgent`).
The affected pages include obituaries, an opinion column, and arrest reports.
Publishing those as accountability findings would burn the credibility of the
one capability this ecosystem has that its comparables do not. So every alert is
classified before it is distributed, and the noise floor is published alongside
the signal.

Channels produced:
  rss       RSS 2.0 feed of SIGNAL alerts only, with the triage summary attached
  atom      Atom 1.0 of the same set
  json      Machine-readable alert stream (a webhook payload; posting it is the
            consumer's job)
  digest    Markdown briefing grouped by watchlist term, for a human to read
  email     An .eml DRAFT in outbox/drafts/ — never sent

LEGAL.md §4 forbids automated outbound communication: "The engine drafts… A
person reads, edits, signs, and sends them. There is deliberately no
email/Twilio/auto-submission integration." This tool honours that absolutely.
It contains no SMTP client, no send call, no HTTP POST, and no webhook
delivery. The `--webhook-url` flag is validated and written into the payload
manifest for a human or a separate authorised process to use; this tool never
contacts it.

Stdlib only. Reads data/engine.db read-only.

Examples:
  python tools/distribution_publish.py triage
  python tools/distribution_publish.py publish --out data/distribution
  python tools/distribution_publish.py publish --min-class boilerplate   # firehose
  python tools/distribution_publish.py stats --json
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import html
import json
import re
import sqlite3
import sys
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = "data/engine.db"

# Alert classes, ordered. An alert is published only if its class rank is at or
# above --min-class.
CLASSES = ("boilerplate", "uncertain", "signal")
CLASS_RANK = {name: i for i, name in enumerate(CLASSES)}

# --- scaffolding vocabulary -------------------------------------------------
# Every pattern here was observed in the live ledger, not guessed. Each entry
# carries the evidence that put it on the list.
ASSET_URL_RE = re.compile(
    r"""https?://[^\s"'<>\\]+?\.(?:css|js|mjs|png|jpe?g|gif|svg|webp|ico|woff2?|ttf|map)
        (?:\?[^\s"'<>\\]*)?""",
    re.I | re.X)
CACHE_BUSTER_RE = re.compile(
    r"""(?:\?ver=|&ver=|data-pmdelayedstyle=|\?v=|&v=|cachebust=|_=\d+)""", re.I)
HTML_TAG_RE = re.compile(r"<[^>]{0,2000}>")
# Akamai mPulse real-user-monitoring beacon and the boomerang loader.
RUM_RE = re.compile(r"go-mpulse\.net|BOOMR[\w.]*|boomerang", re.I)
# Inline script / style bodies. Their presence in a diff is a page-assembly
# change, not an editorial one.
SCRIPT_STYLE_BLOCK_RE = re.compile(
    r"(?:<script\b[^>]*>.*?</script>|<style\b[^>]*>.*?</style>)",
    re.I | re.S)
# JavaScript identifier soup. A diff dominated by these is code churn.
JS_TOKENS = frozenset("""document window createElement appendChild addEventListener
attachEvent navigator userAgent match MSIE function var let const return if else
typeof undefined null true false new this prototype setTimeout setInterval JSON
parse stringify object string boolean number console log error warn try catch
throw finally class extends import export default module require exports self
global location href pathname search hash protocol host hostname origin title
readyState querySelector querySelectorAll getElementById getElementsByTagName
setAttribute getAttribute classList add remove toggle contains dataset style
parentNode parentElement childNodes children innerHTML outerHTML textContent
length push pop shift slice splice indexOf forEach map filter reduce concat
join split replace trim toLowerCase toUpperCase encodeURIComponent
decodeURIComponent Math Date getTime random floor ceil round Object Array String
Number Boolean Function Promise then async await void delete in instanceof of
strictEqual head body script link meta div span html xmlns xmlns:xsi xsi:schemaLocation
""".split())
# CSS declaration soup.
CSS_TOKENS = frozenset("""stylesheet media screen print all important px em rem vh vw
margin padding border background color font font-family font-size font-weight
display flex grid block inline none auto relative absolute fixed z-index opacity
transition transform width height max-width min-width top left right bottom
webkit moz ms hover focus active visited before after content cursor pointer
""".split())
# Words that appear in the alert's own framing rather than in the source document.
FRAMING_RE = re.compile(
    r"^Document changed after publication: (\d+) lines added, (\d+) removed\.\s*"
    r"Removed:\s*(.*?)\s*Added:\s*(.*)$", re.S)
QUOTE_JUNK_RE = re.compile(r"""['"\[\],\\]""")

# A residual passage must look like a sentence to count as signal. Requiring a
# capitalised start plus terminal punctuation is a weak test, but it is the right
# weak test: scaffolding almost never produces it, and editorial prose almost
# always does.
SENTENCE_RE = re.compile(
    r"[A-Z][A-Za-z'\-]+(?:\s+[A-Za-z0-9'\-,.;:%$()\-]+){5,}\s*[.!?;:]")

# Site chrome: boilerplate that appears on EVERY page of a publisher's domain and
# therefore changes on every page at once. Observed verbatim in the live ledger —
# a newsletter-signup widget and its help text, plus navigation/menu residue.
# Including these is what made an initial triage report 106 of 225 SILENT-EDIT
# alerts as "signal" when not one of them was an editorial change.
CHROME_PHRASES = (
    "do you have email set up",
    "you may need to create a new email yourself",
    "already have an account",
    "sign in", "sign up", "log in", "log out", "register",
    "subscribe", "newsletter", "notification",
    "select this as your preferred language",
    "skip to content", "skip to main", "toggle navigation",
    "cookie", "privacy policy", "terms of use", "terms and conditions",
    "all rights reserved", "copyright",
    "hours ago", "minutes ago", "days ago",
    "advertisement", "sponsored", "continue reading",
    "share this", "post this", "tweet this", "email this",
    "related articles", "most popular", "trending",
    "home", "news", "sports", "obituaries", "classifieds", "contact us", "about us",
)

# Icon-font glyphs and menu bullets survive tag-stripping as single letters,
# which inflates the residual word count with pure noise.
GLYPH_TOKEN_RE = re.compile(r"\b[A-Za-z]\b")
# Date/time navigation residue ("October 27 2026 t t t t t 4 hours ago").
NAV_DATE_RE = re.compile(
    r"\b(?:January|February|March|April|May|June|July|August|September|October|"
    r"November|December)\s+\d{1,2}\s+\d{4}\b", re.I)

# Code-likeness detection. The final boilerplate class in the live ledger was a
# core-js polyfill exception message — "The this value for
# String.prototype.includes must not be null or undefined );if( instanceof
# RegExp)throw new TypeError(" — arriving as QUOTED STRINGS inside the Removed/
# Added lists, so tag-stripping cannot remove it and it reads as English prose.
# A word list cannot catch that class; code punctuation density can.
CODE_PUNCT_RE = re.compile(r"[;{}()\[\]<>=+*/&|!~^@]|=>|===|!==|&&|\|\|")
# Structural code shapes that survive tag- and quote-stripping. An object literal
# such as `window.ppconfig={productName:'x',deleteIsEnforced:true}` reduces to
# `window ppconfig productName x deleteIsEnforced true`, which no keyword list
# catches because the keywords are ordinary English words. The key:value and
# dotted-member SHAPES are what identify it, and municipal prose does not produce
# either at density.
OBJECT_LITERAL_RE = re.compile(r"\b\w{2,}\s*:\s*\w")
DOTTED_MEMBER_RE = re.compile(r"\b[A-Za-z_]\w*\.[A-Za-z_]\w*\b")
CAMEL_ASSIGN_RE = re.compile(r"\b[a-z]+[A-Z]\w*\b")
MIN_STRUCTURAL_SHAPES = 4
CODE_KEYWORD_RE = re.compile(
    r"\b(?:prototype|instanceof|typeof|TypeError|RangeError|SyntaxError|RegExp|"
    r"undefined|null|function|throw|catch|finally|constructor|arguments|callee|"
    r"toString|valueOf|hasOwnProperty|isPrototypeOf|apply|call|bind|window|document|"
    r"navigator|location|String|Number|Boolean|Object|Array|Symbol|Promise)\b")
# Ratio thresholds. Calibrated on the live ledger: the polyfill residue scores far
# above 0.30 on punctuation density, while genuine municipal prose ("the board "
# "does not have the ability to deny the project") scores near zero.
CODE_PUNCT_RATIO = 0.12
CODE_KEYWORD_MIN = 4


def code_likeness(residue: str) -> dict:
    """Measure how much of a residue is code rather than prose."""
    words = re.findall(r"\S+", residue)
    total = max(len(words), 1)
    punct_hits = len(CODE_PUNCT_RE.findall(residue))
    keyword_hits = len(CODE_KEYWORD_RE.findall(residue))
    ratio = punct_hits / total
    shapes = {
        "object_literal_pairs": len(OBJECT_LITERAL_RE.findall(residue)),
        "dotted_members": len(DOTTED_MEMBER_RE.findall(residue)),
        "camel_case_identifiers": len(CAMEL_ASSIGN_RE.findall(residue)),
    }
    structural = sum(shapes.values())
    return {
        "code_punctuation_hits": punct_hits,
        "code_keyword_hits": keyword_hits,
        "punctuation_density": round(ratio, 4),
        "whitespace_tokens": len(words),
        "structural_code_shapes": structural,
        **shapes,
        "is_code": ((ratio >= CODE_PUNCT_RATIO and keyword_hits >= CODE_KEYWORD_MIN)
                    or keyword_hits >= 12
                    or structural >= MIN_STRUCTURAL_SHAPES),
    }


# Residual content-word counts below this cannot support a claim of editorial
# change. Calibrated on the live ledger: the JavaScript-only alerts carried
# 345–353 "words" that were all identifiers, so word count alone is not the test
# and the sentence test carries the weight.
MIN_CONTENT_WORDS = 8


def strip_scaffolding(snippet: str) -> tuple[str, dict]:
    """Remove page scaffolding from a diff snippet; return residue + counts.

    Order matters. Script/style blocks go first because their contents would
    otherwise survive tag-stripping as bare identifier soup and inflate the
    residual word count — which is exactly the error that made an initial
    measurement report 63% of alerts as substantive when they were JavaScript.
    """
    counts = {
        "script_style_blocks": len(SCRIPT_STYLE_BLOCK_RE.findall(snippet)),
        "asset_urls": len(ASSET_URL_RE.findall(snippet)),
        "cache_busters": len(CACHE_BUSTER_RE.findall(snippet)),
        "html_tags": len(HTML_TAG_RE.findall(snippet)),
        "rum_beacons": len(RUM_RE.findall(snippet)),
    }
    text = SCRIPT_STYLE_BLOCK_RE.sub(" ", snippet)
    text = RUM_RE.sub(" ", text)
    text = ASSET_URL_RE.sub(" ", text)
    text = CACHE_BUSTER_RE.sub(" ", text)
    text = HTML_TAG_RE.sub(" ", text)
    text = QUOTE_JUNK_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text, counts


def strip_chrome(residue: str) -> tuple[str, dict]:
    """Remove site-wide chrome and glyph noise; report what was removed.

    Chrome is removed by phrase, not by word, because the words themselves
    ("email", "account", "news") are perfectly ordinary editorial vocabulary.
    Only the fixed phrases that recur across every page of a domain are chrome.
    """
    counts = {"chrome_phrases": 0, "nav_dates": 0, "glyph_tokens": 0}
    text = residue
    lowered = text.lower()
    for phrase in CHROME_PHRASES:
        occurrences = lowered.count(phrase)
        if occurrences:
            counts["chrome_phrases"] += occurrences
            text = re.sub(re.escape(phrase), " ", text, flags=re.I)
            lowered = text.lower()
    counts["nav_dates"] = len(NAV_DATE_RE.findall(text))
    text = NAV_DATE_RE.sub(" ", text)
    counts["glyph_tokens"] = len(GLYPH_TOKEN_RE.findall(text))
    text = GLYPH_TOKEN_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip(), counts


def content_words(residue: str) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z'\-]{1,}", residue)
    return [w for w in words
            if w.lower() not in JS_TOKENS and w.lower() not in CSS_TOKENS]


def classify_silent_edit(snippet: str) -> dict:
    """Classify one SILENT-EDIT alert as boilerplate, uncertain, or signal.

    Never asserts that a change was editorially meaningful. `signal` means "the
    residue contains sentence-like prose that scaffolding does not explain", and
    the evidence for that is returned so a human can check it in one reading.
    """
    match = FRAMING_RE.match(snippet.strip())
    if match:
        lines_added, lines_removed = int(match.group(1)), int(match.group(2))
        body = f"{match.group(3)} {match.group(4)}"
    else:
        lines_added = lines_removed = None
        body = snippet

    residue, counts = strip_scaffolding(body)
    residue, chrome_counts = strip_chrome(residue)
    counts.update(chrome_counts)
    words = content_words(residue)
    code = code_likeness(residue)
    sentences = SENTENCE_RE.findall(residue)
    # Quoted CSS/JS fragments inside Removed:/Added: lists leave a lot of noise;
    # a genuine editorial change leaves readable sentences. A sentence that is
    # itself code or chrome is not evidence of an editorial change.
    sentences = [s for s in sentences
                 if not any(tok in s for tok in ("http", "www.", ".css", ".js", "ver="))
                 and not any(phrase in s.lower() for phrase in CHROME_PHRASES)
                 and not code_likeness(s)["is_code"]]

    counts.update(code)
    if code["is_code"]:
        classification = "boilerplate"
    elif sentences and len(words) >= MIN_CONTENT_WORDS:
        classification = "signal"
    elif len(words) >= MIN_CONTENT_WORDS or sentences:
        classification = "uncertain"
    else:
        classification = "boilerplate"

    return {
        "class": classification,
        "lines_added": lines_added,
        "lines_removed": lines_removed,
        "residual_content_words": len(words),
        "residual_sentences": len(sentences),
        "scaffolding_removed": counts,
        "evidence_excerpt": (" | ".join(s.strip()[:220] for s in sentences[:3])
                             if sentences else residue[:220]),
        "reason": {
            "signal": ("residue contains sentence-like prose not explained by scaffolding, "
                       "site-wide chrome or code"),
            "uncertain": ("residual vocabulary remains but no sentence-like prose; a human "
                          "must read the source diff"),
            "boilerplate": ("residue is fully explained by asset versions, tags, beacons, "
                            "inline code or a polyfill exception message "
                            if code["is_code"] else
                            "residue is fully explained by asset versions, tags, beacons or code"),
        }[classification],
    }


def classify_watchlist(term: str, snippet: str) -> dict:
    """A watchlist-term hit is signal by construction: a human wrote the term."""
    return {
        "class": "signal",
        "term": term,
        "residual_content_words": len(content_words(snippet)),
        "evidence_excerpt": snippet.strip()[:300],
        "reason": "watchlist term authored by a human matched in a captured document",
    }


# --------------------------------------------------------------------------
# ledger access
# --------------------------------------------------------------------------

# A residue that appears in many unrelated documents' diffs is site-wide chrome by
# definition, whatever it looks like in isolation. This is the test that catches
# related-article widgets, trending rails and navigation headlines — the class
# that survives every per-document heuristic because each individual instance
# reads as genuine editorial prose. Observed live: one headline
# ("Cheyenne finalizes deal to use old …") was the sole evidence for dozens of
# alerts across unrelated articles.
RECURRENCE_THRESHOLD = 3


SIDES = ("removed", "added")


def _normalise_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()[:160]


def _evidence_keys(snippet: str) -> list[str]:
    """Per-side residue identities, for recurrence counting.

    Site-wide chrome arrives as the SAME string on both sides of a diff. A
    genuine editorial change arrives as DIFFERENT strings on each side. Keying
    per side is what makes that distinction observable; keying on the combined
    text lets any unique removed fragment defeat the test.
    """
    match = FRAMING_RE.match(snippet.strip())
    if not match:
        return [k for k in (_normalise_key(snippet),) if k]
    keys = []
    for side, group in (("removed", match.group(3)), ("added", match.group(4))):
        residue, _ = strip_scaffolding(group)
        residue, _ = strip_chrome(residue)
        key = _normalise_key(residue)
        if len(key) >= 12:  # too short to identify anything reliably
            keys.append(f"{side}:{key}")
    return keys


def apply_recurrence_demotion(alerts: list[dict]) -> dict:
    """Demote alerts whose evidence recurs across unrelated documents.

    Runs as a second pass because recurrence is only visible across the whole
    ledger. A demoted alert keeps its original classification in
    `class_before_recurrence` so the demotion is auditable rather than silent.
    """
    silent = [a for a in alerts if a["term"] == "SILENT-EDIT"]
    per_alert_keys = {a["id"]: _evidence_keys(a.get("snippet") or "") for a in silent}
    frequencies: collections.Counter = collections.Counter(
        key for keys in per_alert_keys.values() for key in keys)
    demoted = 0
    for a in silent:
        keys = per_alert_keys[a["id"]]
        # The alert's recurrence is the highest recurrence among its sides: chrome
        # needs to repeat on only one side to be identifiable as chrome.
        occurrences = max((frequencies[key] for key in keys), default=0)
        a["triage"]["evidence_recurrences"] = occurrences
        a["triage"]["recurrent_evidence"] = [
            {"side_key": key, "recurrences": frequencies[key]}
            for key in keys if frequencies[key] >= RECURRENCE_THRESHOLD]
        if occurrences >= RECURRENCE_THRESHOLD and a["alert_class"] != "boilerplate":
            a["triage"]["class_before_recurrence"] = a["alert_class"]
            a["alert_class"] = "boilerplate"
            a["triage"]["class"] = "boilerplate"
            a["triage"]["reason"] = (
                f"residual evidence recurs in {occurrences} unrelated SILENT-EDIT alerts, "
                f"which identifies it as site-wide chrome rather than a per-document change")
            demoted += 1
    return {"recurrence_threshold": RECURRENCE_THRESHOLD,
            "demoted_alerts": demoted,
            "distinct_evidence_keys": len(frequencies),
            "most_common_evidence": [
                {"side": key.split(":", 1)[0],
                 "excerpt": key.split(":", 1)[1],
                 "recurrences": count}
                for key, count in frequencies.most_common(5) if count > 1]}


def load_alerts(db_path: Path, since_days: int | None = None,
                limit: int | None = None) -> tuple[list[dict], dict]:
    if not db_path.exists():
        raise SystemExit(f"ledger not found: {db_path}")
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    query = """
        SELECT a.id, a.document_id, a.term, a.snippet, a.created_at,
               d.url, d.title, d.source, d.sha256, d.published_at, d.last_checked,
               d.local_path, d.size_bytes
          FROM alerts a
          LEFT JOIN documents d ON d.id = a.document_id
    """
    params: list = []
    if since_days:
        cutoff = (dt.datetime.now(dt.timezone.utc)
                  - dt.timedelta(days=since_days)).isoformat(timespec="seconds")
        query += " WHERE a.created_at >= ?"
        params.append(cutoff.replace("+00:00", "Z"))
    query += " ORDER BY a.created_at DESC, a.id DESC"
    if limit:
        query += " LIMIT ?"
        params.append(limit)

    alerts = []
    for row in conn.execute(query, params):
        record = dict(row)
        term = record.get("term") or ""
        snippet = record.get("snippet") or ""
        if term == "SILENT-EDIT":
            triage = classify_silent_edit(snippet)
        else:
            triage = classify_watchlist(term, snippet)
        record["triage"] = triage
        record["alert_class"] = triage["class"]
        # A stable, content-addressed identity so a re-run never duplicates an
        # item in a feed and a consumer can dedupe across channels.
        record["uid"] = hashlib_shard(f"{record['id']}|{record['created_at']}|{term}")
        alerts.append(record)
    conn.close()

    recurrence = apply_recurrence_demotion(alerts)

    counts = collections.Counter(a["alert_class"] for a in alerts)
    terms = collections.Counter(a["term"] for a in alerts)
    meta = {
        "database": str(db_path),
        "read_only": True,
        "alerts": len(alerts),
        "by_class": {name: counts.get(name, 0) for name in CLASSES},
        "by_term": dict(terms.most_common()),
        "since_days": since_days,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }
    if alerts:
        meta["newest_alert"] = alerts[0]["created_at"]
        meta["oldest_alert"] = alerts[-1]["created_at"]
    silent = [a for a in alerts if a["term"] == "SILENT-EDIT"]
    if silent:
        noise = sum(1 for a in silent if a["alert_class"] == "boilerplate")
        meta["silent_edit_noise_floor_percent"] = round(100 * noise / len(silent), 2)
        meta["silent_edit_total"] = len(silent)
        meta["silent_edit_boilerplate"] = noise
        meta["silent_edit_signal"] = sum(1 for a in silent if a["alert_class"] == "signal")
        meta["silent_edit_uncertain"] = sum(1 for a in silent
                                            if a["alert_class"] == "uncertain")
    meta["recurrence_demotion"] = recurrence
    return alerts, meta


def hashlib_shard(text: str) -> str:
    import hashlib
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


def select(alerts: list[dict], min_class: str) -> list[dict]:
    floor = CLASS_RANK[min_class]
    return [a for a in alerts if CLASS_RANK[a["alert_class"]] >= floor]


# --------------------------------------------------------------------------
# channel renderers
# --------------------------------------------------------------------------

FEED_TITLE = "Cheyenne / Laramie County public-records watchlist"
FEED_DESCRIPTION = (
    "Triage-filtered alerts from an automated public-records watchdog. Every item "
    "carries its source URL, capture timestamp and the evidence that produced it. "
    "Boilerplate page-assembly changes are excluded by default.")


def _rfc822(iso: str) -> str:
    try:
        parsed = dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return iso
    return parsed.strftime("%a, %d %b %Y %H:%M:%S +0000")


def render_rss(alerts: list[dict], site_url: str, meta: dict) -> str:
    items = []
    for a in alerts:
        link = a.get("url") or site_url
        title = _entry_title(a)
        description = (
            f"Class: {a['alert_class']}. {a['triage'].get('reason', '')}\n"
            f"Evidence: {a['triage'].get('evidence_excerpt', '')}\n"
            f"Captured: {a['created_at']}  Source: {link}")
        items.append(
            f"    <item>\n"
            f"      <title>{xml_escape(title[:240])}</title>\n"
            f"      <link>{xml_escape(link)}</link>\n"
            f"      <guid isPermaLink=\"false\">{a['uid']}</guid>\n"
            f"      <pubDate>{_rfc822(a['created_at'])}</pubDate>\n"
            f"      <category>{xml_escape(a['term'])}</category>\n"
            f"      <category>{xml_escape(a['alert_class'])}</category>\n"
            f"      <description>{xml_escape(description[:4000])}</description>\n"
            f"    </item>")
    noise = meta.get("silent_edit_noise_floor_percent")
    triage_note = (f" Excluded {meta['by_class']['boilerplate']} boilerplate alert(s); "
                   f"SILENT-EDIT noise floor {noise}%." if noise is not None else
                   f" Excluded {meta['by_class']['boilerplate']} boilerplate alert(s).")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">\n'
        '  <channel>\n'
        f'    <title>{xml_escape(FEED_TITLE)}</title>\n'
        f'    <link>{xml_escape(site_url)}</link>\n'
        f'    <description>{xml_escape(FEED_DESCRIPTION + triage_note)}</description>\n'
        '    <language>en-us</language>\n'
        f'    <lastBuildDate>{_rfc822(meta["generated_at"])}</lastBuildDate>\n'
        f'    <atom:link href="{xml_escape(site_url.rstrip("/") + "/feed-signals.xml")}"'
        ' rel="self" type="application/rss+xml"/>\n'
        + "\n".join(items) + "\n  </channel>\n</rss>\n")


def _doc_label(a: dict) -> str:
    """Human label for an alert's document."""
    return a.get("title") or f"document {a['document_id']}"


def _entry_title(a: dict) -> str:
    """Entry title, truncated. Kept out of the f-string because nested quotes of
    the same kind inside an f-string expression are a SyntaxError before 3.12."""
    return f"[{a['term']}] {_doc_label(a)}"[:240]


def render_atom(alerts: list[dict], site_url: str, meta: dict) -> str:
    entries = []
    for a in alerts:
        link = a.get("url") or site_url
        summary = (f"Class: {a['alert_class']}. {a['triage'].get('reason','')}\n"
                   f"Evidence: {a['triage'].get('evidence_excerpt','')}")
        entries.append(
            f"  <entry>\n"
            f"    <id>{xml_escape(site_url.rstrip('/') + '#alert-' + a['uid'])}</id>\n"
            f"    <title>{xml_escape(_entry_title(a))}</title>\n"
            f'    <link href="{xml_escape(link)}"/>\n'
            f"    <updated>{a['created_at'].replace('Z','+00:00')}</updated>\n"
            f'    <category term="{xml_escape(a["term"])}"/>\n'
            f'    <category term="{xml_escape(a["alert_class"])}"/>\n'
            f"    <summary type=\"text\">{xml_escape(summary[:4000])}</summary>\n"
            f"  </entry>")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<feed xmlns="http://www.w3.org/2005/Atom">\n'
            f'  <title>{xml_escape(FEED_TITLE)}</title>\n'
            f'  <link href="{xml_escape(site_url)}"/>\n'
            f'  <id>{xml_escape(site_url.rstrip("/") + "/")}</id>\n'
            f'  <updated>{meta["generated_at"].replace("Z", "+00:00")}</updated>\n'
            f'  <subtitle type="text">{xml_escape(FEED_DESCRIPTION)}</subtitle>\n'
            + "\n".join(entries) + "\n</feed>\n")


def render_json_stream(alerts: list[dict], meta: dict, webhook_url: str | None) -> dict:
    return {
        "schema": "civic-alert-stream-v1",
        "generated_at": meta["generated_at"],
        "triage": meta["by_class"],
        "silent_edit_noise_floor_percent": meta.get("silent_edit_noise_floor_percent"),
        "delivery": {
            "posted_by_this_tool": False,
            "webhook_url_configured": webhook_url,
            "statement": ("This tool never performs an HTTP POST. The URL is recorded "
                          "so an authorised consumer can deliver the payload. LEGAL.md §4 "
                          "requires a human in the loop for outbound communication."),
        },
        "alerts": [{
            "uid": a["uid"],
            "alert_id": a["id"],
            "document_id": a["document_id"],
            "term": a["term"],
            "class": a["alert_class"],
            "created_at": a["created_at"],
            "url": a.get("url"),
            "title": a.get("title"),
            "source": a.get("source"),
            "document_sha256": a.get("sha256"),
            "triage": a["triage"],
            "snippet_verbatim": a.get("snippet"),
        } for a in alerts],
    }


def render_digest(alerts: list[dict], meta: dict) -> str:
    lines = [
        f"# Public-records alert digest — {meta['generated_at'][:10]}",
        "",
        f"Generated {meta['generated_at']} from `{meta['database']}` (read-only).",
        "",
        "## Triage summary",
        "",
        "| Class | Count | Published by default |",
        "|---|---|---|",
        f"| signal | {meta['by_class']['signal']} | yes |",
        f"| uncertain | {meta['by_class']['uncertain']} | no |",
        f"| boilerplate | {meta['by_class']['boilerplate']} | no |",
        "",
    ]
    if meta.get("silent_edit_noise_floor_percent") is not None:
        lines += [
            f"**SILENT-EDIT noise floor: {meta['silent_edit_noise_floor_percent']}%** "
            f"({meta['silent_edit_boilerplate']} of {meta['silent_edit_total']} alerts were "
            f"page-assembly changes — asset version strings, cache-buster query parameters, "
            f"RUM beacons and inline JavaScript — not editorial changes to a document).",
            "",
            "Those alerts are excluded from every channel by default. Publishing them would "
            "present WordPress plugin updates as accountability findings.",
            "",
        ]
    grouped: dict[str, list[dict]] = collections.defaultdict(list)
    for a in alerts:
        grouped[a["term"]].append(a)
    lines += [f"## {len(alerts)} published alert(s) across {len(grouped)} watchlist term(s)", ""]
    for term, group in sorted(grouped.items(), key=lambda kv: -len(kv[1])):
        lines += [f"### {term} — {len(group)} alert(s)", ""]
        for a in group:
            lines += [
                f"- **{_doc_label(a)}**  ",
                f"  captured `{a['created_at']}` · class `{a['alert_class']}` · "
                f"alert id {a['id']}  ",
                f"  source: {a.get('url') or '(no URL recorded)'}  ",
                f"  reason: {a['triage'].get('reason','')}  ",
                f"  evidence: {a['triage'].get('evidence_excerpt','')[:400]}",
                "",
            ]
    lines += [
        "## Caveats",
        "",
        "- `signal` means the residue is not explained by page scaffolding. It does **not** "
        "mean a document was edited for editorial reasons, and it is not a finding of "
        "wrongdoing by anyone.",
        "- `uncertain` alerts are withheld, not dismissed. Re-run with "
        "`--min-class uncertain` to read them.",
        "- Absence of an alert is not evidence that nothing changed. Capture coverage is "
        "bounded by the engine's rate discipline and by robots.txt refusals recorded in "
        "`sources.notes`.",
        "- Every item carries a verbatim snippet and a source URL. Nothing here is a "
        "paraphrase of a record.",
        "",
    ]
    return "\n".join(lines)


def render_email_draft(alerts: list[dict], meta: dict, sender: str,
                       recipient_placeholder: str) -> str:
    """An RFC-822 draft. Written to outbox/drafts/ and never transmitted."""
    body = render_digest(alerts, meta)
    headers = [
        f"Date: {meta['generated_at']}",
        f"From: {sender}",
        f"To: {recipient_placeholder}",
        f"Subject: [DRAFT — NOT SENT] {len(alerts)} public-records alert(s), "
        f"{meta['generated_at'][:10]}",
        "X-Unsent: 1",
        "X-Draft-Notice: This is a draft produced by tools/distribution_publish.py. "
        "LEGAL.md section 4 requires a human to read, edit, sign and send it. "
        "No automated transmission is implemented or authorised.",
        "MIME-Version: 1.0",
        'Content-Type: text/plain; charset="utf-8"',
        "",
        body,
    ]
    return "\n".join(headers)


# --------------------------------------------------------------------------
# stages
# --------------------------------------------------------------------------

def stage_triage(args) -> int:
    alerts, meta = load_alerts(ROOT / args.db, args.since_days, args.limit)
    if args.json:
        print(json.dumps({
            "meta": meta,
            "samples": [{
                "alert_id": a["id"], "term": a["term"], "class": a["alert_class"],
                "title": a.get("title"), "url": a.get("url"),
                "created_at": a["created_at"], "triage": a["triage"],
            } for a in alerts[:args.samples]],
        }, indent=2))
        return 0
    print(f"ledger {meta['database']} — {meta['alerts']} alerts (read-only)")
    print(f"  newest {meta.get('newest_alert')}   oldest {meta.get('oldest_alert')}")
    print("  by class:")
    for name in CLASSES:
        print(f"    {name:12s} {meta['by_class'][name]:5d}")
    if meta.get("silent_edit_noise_floor_percent") is not None:
        print(f"  SILENT-EDIT noise floor: {meta['silent_edit_noise_floor_percent']}% "
              f"({meta['silent_edit_boilerplate']}/{meta['silent_edit_total']} boilerplate, "
              f"{meta['silent_edit_uncertain']} uncertain, {meta['silent_edit_signal']} signal)")
        rec = meta["recurrence_demotion"]
        print(f"  recurrence demotion: {rec['demoted_alerts']} alerts reclassified as "
              f"site-wide chrome (threshold {rec['recurrence_threshold']})")
        for row in rec["most_common_evidence"][:3]:
            print(f"    x{row['recurrences']:3d} [{row['side']:7s}] {row['excerpt'][:88]}")
    print("  by term:")
    for term, count in list(meta["by_term"].items())[:12]:
        print(f"    {count:5d}  {term}")
    print("\n  samples:")
    for a in alerts[:args.samples]:
        print(f"    [{a['alert_class']:11s}] {a['term']:34s} "
              f"{str(a.get('title') or '')[:52]}")
        print(f"                   words={a['triage'].get('residual_content_words')} "
              f"sentences={a['triage'].get('residual_sentences', 0)}  "
              f"{a['triage'].get('reason','')[:88]}")
    return 0


def stage_publish(args) -> int:
    alerts, meta = load_alerts(ROOT / args.db, args.since_days, args.limit)
    published = select(alerts, args.min_class)
    out = ROOT / args.out
    (out / "drafts").mkdir(parents=True, exist_ok=True)

    if args.webhook_url and not args.webhook_url.startswith(("https://", "http://")):
        raise SystemExit(f"--webhook-url must be an http(s) URL, got {args.webhook_url!r}")

    feed_meta = dict(meta)
    feed_meta["published"] = len(published)
    feed_meta["min_class"] = args.min_class

    (out / "feed-signals.xml").write_text(
        render_rss(published, args.site_url, feed_meta), encoding="utf-8")
    (out / "feed-signals.atom").write_text(
        render_atom(published, args.site_url, feed_meta), encoding="utf-8")
    stream = render_json_stream(published, feed_meta, args.webhook_url)
    (out / "alert-stream.json").write_text(json.dumps(stream, indent=2) + "\n",
                                           encoding="utf-8")
    digest = render_digest(published, feed_meta)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    (out / f"digest-{stamp}.md").write_text(digest, encoding="utf-8")
    (out / "digest-latest.md").write_text(digest, encoding="utf-8")
    draft = render_email_draft(published, feed_meta, args.sender, args.to)
    draft_fp = out / "drafts" / f"alert-digest-{stamp}.eml"
    draft_fp.write_text(draft, encoding="utf-8")
    (out / "channels.json").write_text(json.dumps({
        "schema": "distribution-channels-v1",
        "generated_at": feed_meta["generated_at"],
        "min_class": args.min_class,
        "published_alerts": len(published),
        "withheld_alerts": len(alerts) - len(published),
        "channels": {
            "rss": {"path": "feed-signals.xml", "transport": "static-file",
                    "sent_by_this_tool": False},
            "atom": {"path": "feed-signals.atom", "transport": "static-file",
                     "sent_by_this_tool": False},
            "json-webhook-payload": {"path": "alert-stream.json",
                                     "transport": "file-only",
                                     "posted_by_this_tool": False,
                                     "configured_url": args.webhook_url},
            "markdown-digest": {"path": f"digest-{stamp}.md",
                                "transport": "static-file", "sent_by_this_tool": False},
            "email-draft": {"path": str(draft_fp.relative_to(out)),
                            "transport": "draft-file-never-sent",
                            "sent_by_this_tool": False,
                            "recipient_placeholder": args.to},
        },
        "legal_basis": ("LEGAL.md §4: the engine drafts; a person reads, edits, signs and "
                        "sends. No SMTP client, no send call and no HTTP POST exist in "
                        "tools/distribution_publish.py."),
    }, indent=2) + "\n", encoding="utf-8")

    print(f"published {len(published)} of {len(alerts)} alerts "
          f"(min-class={args.min_class}; withheld {len(alerts) - len(published)})")
    if meta.get("silent_edit_noise_floor_percent") is not None:
        print(f"  SILENT-EDIT noise floor {meta['silent_edit_noise_floor_percent']}% "
              f"— {meta['silent_edit_boilerplate']} boilerplate alerts withheld")
    print(f"  → {out.relative_to(ROOT)}/feed-signals.xml      (RSS 2.0)")
    print(f"  → {out.relative_to(ROOT)}/feed-signals.atom     (Atom 1.0)")
    print(f"  → {out.relative_to(ROOT)}/alert-stream.json     (webhook payload, NOT posted)")
    print(f"  → {out.relative_to(ROOT)}/digest-{stamp}.md    (Markdown briefing)")
    print(f"  → {out.relative_to(ROOT)}/drafts/alert-digest-{stamp}.eml  (DRAFT, never sent)")
    if args.webhook_url:
        print(f"  webhook URL recorded for an authorised consumer: {args.webhook_url}")
        print("  this tool did not contact it")
    return 0


def stage_stats(args) -> int:
    alerts, meta = load_alerts(ROOT / args.db, args.since_days, args.limit)
    by_term_class: dict[str, dict] = collections.defaultdict(
        lambda: {name: 0 for name in CLASSES})
    for a in alerts:
        by_term_class[a["term"]][a["alert_class"]] += 1
    report = {
        "schema": "distribution-stats-v1",
        **meta,
        "by_term_and_class": dict(sorted(by_term_class.items())),
    }
    text = json.dumps(report, indent=2)
    if args.json:
        print(text)
        return 0
    out = ROOT / args.out
    out.mkdir(parents=True, exist_ok=True)
    (out / "stats.json").write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--since-days", type=int, default=None)
    ap.add_argument("--limit", type=int, default=None)
    sub = ap.add_subparsers(dest="stage", required=True)

    t = sub.add_parser("triage", help="classify alerts and report the noise floor")
    t.add_argument("--samples", type=int, default=6)
    t.add_argument("--json", action="store_true")
    t.set_defaults(func=stage_triage)

    p = sub.add_parser("publish", help="render every channel (never sends anything)")
    p.add_argument("--out", default="data/distribution")
    p.add_argument("--min-class", choices=CLASSES, default="signal")
    p.add_argument("--site-url",
                   default="https://bartimoussmith-oss.github.io/therealwindycity/")
    p.add_argument("--webhook-url", default=None,
                   help="recorded in the payload manifest; NEVER contacted by this tool")
    p.add_argument("--sender", default="watchdog@localhost.invalid")
    p.add_argument("--to", default="RECIPIENT-PLACEHOLDER@example.invalid")
    p.set_defaults(func=stage_publish)

    s = sub.add_parser("stats", help="per-term, per-class statistics")
    s.add_argument("--out", default="data/distribution")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=stage_stats)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
