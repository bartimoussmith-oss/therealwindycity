#!/usr/bin/env python3
"""Offline tests for the fireflies meeting-intelligence package.

Run:  python3 fireflies/test_fireflies.py        (or python3 -m pytest fireflies/)

Includes a full end-to-end against a synthetic mini-corpus (minutes + ASR +
agenda HTML) and the invariant that defines this package: every stored quote
is a verbatim substring of its source text.
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fireflies.actions import attendance_quote, extract_actions
from fireflies.agenda import (parse_agenda_html, parse_minutes_items,
                              parse_speech_items)
from fireflies.build import analyze_meeting, build_ledger, verify_ledger
from fireflies.outline import align_asr, build_outline
from fireflies.search import search
from fireflies.sources import (Meeting, SourceText, body_slug,
                               guess_date_from_filename, load_meetings,
                               map_body, parse_asr_segments)
from fireflies.summarize import entities, extractive_summary, keywords
from fireflies.textutil import (clip_quote, find_normalized, first_sentence,
                                normalize_ws, ocr_join, quote_body,
                                split_sentences)
from fireflies.topics import build_topics, term_timeline

# ----------------------------------------------------------------- fixtures

MINUTES = """MEETING: City Council Meeting | DATE: 2026-01-05 | CLIP_ID: 9001 | SOURCE: test

RECORD OF PROCEEDINGS FOR THE GOVERNING BODY
OF THE CITY OF CHEYENNE
Office of City Clerk
January 5, 2026
The Governing Body of the City of Cheyenne met in regular session on this date
beginning at 6:00 p.m. in Council Chambers.  Present were: MAYOR - Pat Collins;
COUNCIL MEMBERS - Mr. Brown, Ms. Broyles and Mr. Valdez.

[CA] MINUTES FROM REGULAR MEETING OF THE GOVERNING BODY ON DECEMBER 15, 2025.
Motion (per Consent Agenda) carried.

ORDINANCE –1st READING – Amending section 8.24.020 of the Municipal Code of the
City of Cheyenne, Wyoming.  Mr. Brown moved to approve on first reading, seconded
by Ms. Broyles.  Motion carried.  Voting “yes” – all members of the governing
body present.

RESOLUTION NO. 4687 – Authorizing the Mayor to sign a grant agreement.
Ms. Broyles moved to approve, seconded by Mr. Valdez.  Motion carried.

Staff was directed to bring the revised fee schedule back to committee in
February.  The item was tabled until the next regular meeting.
"""

ASR = """MEETING: city-council | DATE: 2026-01-05 | YT_ID: TESTVIDEO01
SOURCE: test captions
VIDEO: https://www.youtube.com/watch?v=TESTVIDEO01

[00:01:00] Good evening, welcome to the January 5th, 2026 meeting of the city of
Cheyenne City Council. >> Roll call, please. >> Here.
[00:02:30] The first item tonight is ordinance first reading amending section
8.24.020 of the municipal code. Staff report, please.
[00:05:15] This ordinance amends the fire code fee section. Any questions?
[00:06:20] Could I have a motion, please. >> I move to approve on first reading.
>> Second. >> Seconded by Ms. Broyles. Motion carried.
[00:09:00] Next item, please. resolution number 4687 authorizing the mayor to
sign a grant agreement. Staff report please.
[00:11:00] Motion to approve resolution 4687. >> Second. All in favor signify by
saying I. Motion carried.
"""

AGENDA_HTML = """<html><body>
<a name="agenda100" class="Agenda" href="https://example.test/MediaPlayer.php?clip_id=9001&amp;meta_id=100">CALL MEETING TO ORDER.</a>
<a name="agenda101" class="Agenda" href="https://example.test/MediaPlayer.php?clip_id=9001&amp;meta_id=101">ORDINANCE &ndash; 1st READING &ndash; Amending section 8.24.020 of the Municipal Code of the City of Cheyenne, Wyoming.</a>
<a href="https://example.test/MetaViewer.php?meta_id=200" name="document200" class="Document">Supporting Document</a>
ACTION: \t\tApprove
<a name="agenda102" class="Agenda" href="https://example.test/MediaPlayer.php?clip_id=9001&amp;meta_id=102">RESOLUTION NO. 4687 &ndash; Authorizing the Mayor to sign a grant agreement.</a>
<a href="https://example.test/MetaViewer.php?meta_id=201" name="document201" class="Document">Supporting Document</a>
ACTION: \t\tApprove
</body></html>
"""


def make_mini_repo(root: Path) -> Path:
    (root / "pipeline" / "corpus").mkdir(parents=True)
    (root / "pipeline" / "corpus_yt").mkdir(parents=True)
    (root / "pipeline" / "docs" / "9001").mkdir(parents=True)
    (root / "pipeline" / "corpus" / "9001_2026-01-05.txt").write_text(MINUTES)
    (root / "pipeline" / "corpus_yt" / "2026-01-05-city-council.txt").write_text(ASR)
    (root / "pipeline" / "docs" / "9001" / "2026-01-05_agenda.html").write_text(AGENDA_HTML)
    (root / "pipeline" / "meetings.json").write_text(json.dumps({
        "generated": "2026-01-01T00:00:00",
        "meetings": {"9001": {
            "clip_id": 9001, "date": "2026-01-05", "name": "City Council Meeting",
            "agenda_url": "https://example.test/agenda/9001",
            "mp4_url": "https://example.test/video/9001.mp4"}},
    }))
    return root


# --------------------------------------------------------------- textutils

class TestTextutil(unittest.TestCase):
    def test_sentence_split_keeps_abbreviations(self):
        sents = split_sentences("Mr. Brown moved to approve. Ms. Broyles seconded.")
        self.assertEqual(len(sents), 2)
        self.assertTrue(sents[0].startswith("Mr. Brown"))

    def test_first_sentence_abbrev(self):
        s = first_sentence("Present were: MAYOR - Pat Collins; COUNCIL MEMBERS - Mr. Brown, Ms. Broyles and Mr. Valdez. Next.")
        self.assertIn("Mr. Brown", s)
        self.assertNotIn("Next", s)

    def test_ocr_join_known_words_only(self):
        self.assertEqual(ocr_join("M otion carried"), "Motion carried")
        self.assertEqual(ocr_join("a nd then"), "and then")
        self.assertIn("a mile", ocr_join("walked a mile home"))  # legit article kept

    def test_find_normalized_across_newlines(self):
        raw = "Mr. Brown moved to approve on\nfirst reading tonight."
        idx = find_normalized(raw, "Brown moved to approve on first reading")
        self.assertGreaterEqual(idx, 0)

    def test_clip_and_body(self):
        q = clip_quote("x" * 400)
        self.assertTrue(q.endswith("…"))
        self.assertEqual(len(quote_body(q)), len(q) - 1)


# ------------------------------------------------------------------ agenda

class TestAgenda(unittest.TestCase):
    def test_agenda_html_items_docs_actions(self):
        items = parse_agenda_html(AGENDA_HTML, "ref")
        self.assertEqual(len(items), 3)
        ord_item = items[1]
        self.assertEqual(ord_item.kind, "ordinance")
        self.assertEqual(ord_item.reading, "1st")
        self.assertEqual(ord_item.expected_action.strip(), "Approve")
        self.assertTrue(any(d["url"].endswith("meta_id=200") for d in ord_item.docs))
        self.assertTrue(any(d["kind"] == "video-link" for d in ord_item.docs))
        self.assertIn("8.24.020", ord_item.title)

    def test_minutes_items_multi_item_paragraph(self):
        text = ("[CA] MINUTES FROM REGULAR MEETING.  Motion carried.  "
                "[CA] RESOLUTION – Authorizing something.  Motion carried.")
        items = parse_minutes_items(text, "ref")
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].kind, "minutes")
        self.assertEqual(items[1].kind, "consent")

    def test_minutes_items_real_leads(self):
        items = parse_minutes_items(MINUTES, "ref")
        kinds = [i.kind for i in items]
        self.assertIn("minutes", kinds)
        self.assertIn("ordinance", kinds)
        self.assertIn("resolution", kinds)
        ord_item = next(i for i in items if i.kind == "ordinance")
        self.assertEqual(ord_item.reading, "1st")
        res_item = next(i for i in items if i.kind == "resolution")
        self.assertEqual(res_item.number, "4687")

    def test_speech_items_require_noun(self):
        items = parse_speech_items(
            "Next item, please. resolution number 4687 authorizing the mayor.", "ref")
        self.assertEqual(len(items), 1)
        self.assertTrue(items[0].title_guess)
        self.assertIn("4687", items[0].quote)
        noise = parse_speech_items(
            "We should itemize the second phase of the project carefully.", "ref")
        self.assertEqual(len(noise), 0)

    def test_speech_quotes_are_verbatim(self):
        text = "Next item, please. resolution number 4687 authorizing the mayor."
        for it in parse_speech_items(text, "ref"):
            self.assertIn(quote_body(it.quote), normalize_ws(text))


# ----------------------------------------------------------------- actions

class TestActions(unittest.TestCase):
    def test_motion_and_second(self):
        acts = extract_actions(MINUTES, "minutes", "ref")
        cats = [a.type for a in acts]
        self.assertIn("motion", cats)
        self.assertIn("second", cats)
        self.assertIn("outcome", cats)
        self.assertIn("vote-tally", cats)
        self.assertIn("directive", cats)
        self.assertIn("scheduling", cats)
        motion = next(a for a in acts if a.type == "motion")
        self.assertIn("Brown", motion.who)
        self.assertIn("moved to approve on first reading", motion.quote)

    def test_no_false_positive_second(self):
        acts = extract_actions(
            "The second phase will probably be discussed later this year.", "md", "ref")
        self.assertEqual([a for a in acts if a.type == "second"], [])

    def test_quotes_verbatim(self):
        for a in extract_actions(MINUTES, "minutes", "ref"):
            self.assertIn(quote_body(a.quote), normalize_ws(MINUTES))
        for a in extract_actions(ASR, "asr", "ref"):
            self.assertIn(quote_body(a.quote), normalize_ws(ASR))

    def test_attendance(self):
        att = attendance_quote(MINUTES, "minutes", "ref")
        self.assertIn("Mr. Brown", att["quote"])
        self.assertIn("Present were:", att["quote"])
        self.assertNotIn("The Governing Body of", att["quote"].split("Present were:")[1])

    def test_asr_locator_timestamp(self):
        acts = extract_actions(ASR, "asr", "ref", parse_asr_segments(ASR))
        motion = next(a for a in acts if a.type == "motion")
        self.assertIn("ts", motion.locator)


# --------------------------------------------------------------- summarize

class TestSummarize(unittest.TestCase):
    def test_summary_sentences_are_verbatim(self):
        for s in extractive_summary(MINUTES):
            self.assertIn(quote_body(s["sentence"]), normalize_ws(MINUTES))

    def test_summary_no_duplicates(self):
        text = "Motion carried. Voting yes all present. " * 30 + "Final sentence here today."
        sents = extractive_summary(text, 6)
        bodies = [quote_body(s["sentence"]).lower() for s in sents]
        self.assertEqual(len(bodies), len(set(bodies)))

    def test_keywords_and_entities(self):
        kws = keywords(MINUTES)
        self.assertTrue(kws)
        ents = {(e["type"], e["value"]) for e in entities(MINUTES)}
        self.assertIn(("resolution", "4687"), ents)
        for e in entities(MINUTES):
            if e["example"]:
                self.assertIn(quote_body(e["example"]["quote"]), normalize_ws(MINUTES))


# ----------------------------------------------------------------- outline

class TestOutline(unittest.TestCase):
    def test_anchor_alignment(self):
        segs = parse_asr_segments(ASR)
        items = parse_speech_items(ASR, "ref", segs)
        self.assertTrue(items)
        span = align_asr(items[0], segs)
        self.assertTrue(span)
        self.assertIn(":", span["start"])
        self.assertLessEqual(span["start"], span["end"])
        self.assertIn(span["method"], ("anchor-alignment-v1",))

    def test_monotonic_chapters(self):
        segs = parse_asr_segments(ASR)
        items = parse_speech_items(ASR, "ref", segs)
        outline = build_outline(items, segs)
        starts = [o["start"] for o in outline if o.get("start")]
        self.assertEqual(starts, sorted(starts))


# ------------------------------------------------------------------ search

class TestSearch(unittest.TestCase):
    def test_search_hits_with_locators(self):
        root = make_mini_repo(Path(tempfile.mkdtemp()))
        meetings = load_meetings(root)
        hits = search("grant agreement", meetings)
        self.assertTrue(hits)
        h = hits[0]
        self.assertIn("grant agreement", h["snippet"].lower())
        self.assertLess(h["match_start"], h["match_end"])
        asr_hits = [x for x in hits if x["locator"]["kind"] == "asr"]
        if asr_hits:
            self.assertIn("ts", asr_hits[0]["locator"])


# ------------------------------------------------------------- topics

class TestTopics(unittest.TestCase):
    def test_term_timeline(self):
        root = make_mini_repo(Path(tempfile.mkdtemp()))
        meetings = load_meetings(root)
        rows = term_timeline("4687", meetings, corpus_texts=lambda mt: mt.texts)
        self.assertTrue(rows)
        self.assertTrue(rows[0]["count"] >= 1)
        self.assertIn("4687", rows[0]["example"]["quote"])


# --------------------------------------------------------- end-to-end build

class TestEndToEnd(unittest.TestCase):
    def test_full_cycle_on_mini_corpus(self):
        root = make_mini_repo(Path(tempfile.mkdtemp()))
        out = root / "fireflies"
        stats = build_ledger(root, out)
        self.assertEqual(stats["meetings"], 1)
        self.assertGreaterEqual(stats["items"], 3)
        self.assertGreaterEqual(stats["actions"], 4)

        rec = json.loads((out / "ledger" / "meetings.jsonl").read_text().splitlines()[0])
        self.assertEqual(rec["meeting_id"], "2026-01-05-city-council")
        self.assertEqual(rec["stats"]["segments"], 6)
        self.assertTrue(rec["attendance"]["quote"].startswith("Present were:"))
        # outline chapters with timestamps exist for speech-derived items
        self.assertTrue(any(o.get("start") for o in rec["outline"]))
        # agenda HTML items merged: docs + expected actions present
        self.assertTrue(any(it["expected_action"] for it in rec["items"]))
        # url merged from meetings.json + youtube
        self.assertEqual(rec["urls"].get("mp4"), "https://example.test/video/9001.mp4")
        self.assertIn("youtube.com", rec["urls"].get("youtube", ""))

        for f in ("meetings.jsonl", "agenda_tracker.csv", "topics.json", "INDEX.md"):
            self.assertTrue((out / "ledger" / f).exists(), f)
        self.assertTrue((out / "briefs" / "2026-01-05-city-council.md").exists())

        report = verify_ledger(root, out / "ledger" / "meetings.jsonl")
        self.assertGreater(report["checked"], 10)
        self.assertTrue(report["ok"], f"quote failures: {report['bad'][:3]}")

        topics = build_topics([rec])
        self.assertTrue(any(e["value"] == "4687" for e in topics["entities"]))

    def test_every_quote_verbatim_invariant(self):
        """Directly: every quote in a built ledger is a substring of its sources."""
        from fireflies.textutil import strip_tags, unescape_html
        root = make_mini_repo(Path(tempfile.mkdtemp()))
        out = root / "fireflies"
        build_ledger(root, out)
        rec = json.loads((out / "ledger" / "meetings.jsonl").read_text().splitlines()[0])
        blobs = []
        for s in rec["sources"]:
            raw = (root / s["ref"]).read_text()
            blobs.append(normalize_ws(raw))
            blobs.append(normalize_ws(strip_tags(unescape_html(raw))))
        quotes = [rec["attendance"]["quote"]]
        quotes += [s["sentence"] for s in rec["overview"]["sentences"]]
        quotes += [q["quote"] for it in rec["items"] for q in it["quotes"]]
        quotes += [a["quote"] for a in rec["actions"]]
        for q in quotes:
            self.assertTrue(any(quote_body(q) in b for b in blobs), q[:80])


class TestRealCorpusSmoke(unittest.TestCase):
    """Cheap spot checks against the real corpora when present."""

    def test_real_corpus_loads(self):
        root = Path(__file__).resolve().parent.parent
        if not (root / "pipeline" / "corpus").exists():
            self.skipTest("corpus not present")
        meetings = load_meetings(root)
        self.assertGreater(len(meetings), 100)
        by_id = {m.meeting_id: m for m in meetings}
        self.assertIn("2026-08-10-city-council", by_id)
        mt = by_id["2026-08-10-city-council"]
        self.assertTrue(any(t.kind == "agenda_html" for t in mt.texts))
        rec = analyze_meeting(mt)
        self.assertGreaterEqual(rec["stats"]["items"], 10)
        # every quote verbatim against this meeting's own sources
        blobs = [normalize_ws(t.text) for t in mt.texts]
        for a in rec["actions"][:50]:
            self.assertTrue(any(quote_body(a["quote"]) in b for b in blobs),
                            a["quote"][:60])

    def test_body_slugs(self):
        self.assertEqual(body_slug("City Council Meeting - Agenda Only"), "city-council")
        self.assertEqual(body_slug("First Regular Meeting of the Governing Body"), "city-council")
        self.assertEqual(body_slug("Other/Supporting"), "other-supporting")
        self.assertEqual(map_body("Goal Setting 2025 - Round 2 02-04-25"), "goal-setting")

    def test_date_guesses(self):
        self.assertEqual(guess_date_from_filename("May_18,_2026,_Cheyenne_Planning_Commission_Meeting.md"),
                         "2026-05-18")
        self.assertEqual(guess_date_from_filename("Public_Services_Committee_01-06-25.md"),
                         "2025-01-06")
        self.assertEqual(guess_date_from_filename("998_2025-01-27.txt"),
                         "2025-01-27")


if __name__ == "__main__":
    unittest.main(verbosity=2)
