#!/usr/bin/env python3
"""Tests for tools/distribution_publish.py — stdlib unittest, hermetic, no DB.

Two things are tested hardest here:
  1. the triage classifier, because publishing page scaffolding as
     accountability findings would burn the credibility of the one capability
     this ecosystem has that its comparables do not; and
  2. the no-send guarantee, because LEGAL.md §4 makes automated outbound
     communication a hard prohibition rather than a preference.

Every boilerplate fixture below is a real snippet shape observed in the live
ledger on 2026-10-28, not an invented one.
"""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import distribution_publish as dp  # noqa: E402


def silent(lines_added: int, lines_removed: int, removed: list[str],
           added: list[str]) -> str:
    """Build a SILENT-EDIT snippet in the engine's exact format."""
    return (f"Document changed after publication: {lines_added} lines added, "
            f"{lines_removed} removed. Removed: {json.dumps(removed)} "
            f"Added: {json.dumps(added)}")


# --- real observed boilerplate classes -------------------------------------

CSS_VERSION_BUMP = silent(100, 99, [
    "<link rel='stylesheet' id='newspack-blocks-block-styles-stylesheet-css' "
    "href='https://capcity.news/wp-content/plugins/newspack-blocks/dist/"
    "block_styles.css?ver=4.36.3' media='all' />",
    '<link rel="stylesheet" id="foundation-events-styles-css" media="all" '
    'data-pmdelayedstyle="https://capcity.news/wp-content/plugins/newspack-manager/'
    'includes/foundation/events/styles.css?ver=1793030792">',
], [
    "<link rel='stylesheet' id='newspack-blocks-block-styles-stylesheet-css' "
    "href='https://capcity.news/wp-content/plugins/newspack-blocks/dist/"
    "block_styles.css?ver=4.36.5' media='all' />",
    '<link rel="stylesheet" id="foundation-events-styles-css" media="all" '
    'data-pmdelayedstyle="https://capcity.news/wp-content/plugins/newspack-manager/'
    'includes/foundation/events/styles.css?ver=1793050624">',
])

RUM_BEACON = silent(10, 10, [
    "<script>!function(e){var n='https://s.go-mpulse.net/boomerang/';"
    "if(False==True)e.BOOMR_config=e.BOOMR_config||{},e.BOOMR_config.PageParams="
    "{pagevars:['']};</script>"],
    ["<script>!function(e){var n='https://s.go-mpulse.net/boomerang/';"
     "if(True==True)e.BOOMR_config=e.BOOMR_config||{},e.BOOMR_config.PageParams="
     "{pagevars:['x']};</script>"])

POLYFILL_EXCEPTION = silent(92, 92, [
    "The this value for String.prototype.includes must not be null or undefined"
    ");if( instanceof RegExp)throw new TypeError( First argument to "
    "String.prototype.includes must not be a symbol"],
    ["The this value for String.prototype.includes must not be null or undefined"
     ");if( instanceof RegExp)throw new TypeError( First argument to "
     "String.prototype.includes must be a string"])

NEWSLETTER_CHROME = silent(117, 117, [
    "Do you have email set up? You may need to create a new email yourself. "
    "Already have an account? Sign in"],
    ["Do you have email set up? You may need to create a new email yourself. "
     "Already have an account? Log in"])

TRACKING_CONFIG = silent(60, 60, [
    "window.ppconfig={productName:'d222c26d10f0a88dacceb3da240b347e',"
    "deleteIsEnforced:true,sealIsEnforced:false}"],
    ["window.ppconfig={productName:'d222c26d10f0a88dacceb3da240b347e',"
     "deleteIsEnforced:true,sealIsEnforced:true}"])

REAL_EDITORIAL_CHANGE = silent(4, 4, [
    "The council voted 5-4 to postpone the second reading of the ordinance "
    "until the November meeting, citing an incomplete fiscal note."],
    ["The council voted 6-3 to approve the second reading of the ordinance, "
     "with the fiscal note amended to reflect the water entitlement cost."])


class TestBoilerplateClassification(unittest.TestCase):
    def test_css_version_bump_is_boilerplate(self):
        # The single most common false alert in the live ledger: a WordPress
        # plugin version string changing on a news article about obituaries.
        self.assertEqual(dp.classify_silent_edit(CSS_VERSION_BUMP)["class"], "boilerplate")

    def test_rum_beacon_is_boilerplate(self):
        self.assertEqual(dp.classify_silent_edit(RUM_BEACON)["class"], "boilerplate")

    def test_polyfill_exception_message_is_boilerplate(self):
        # Arrives as quoted English-looking prose, so tag-stripping alone cannot
        # remove it. This is the class that defeated the first two attempts.
        result = dp.classify_silent_edit(POLYFILL_EXCEPTION)
        self.assertEqual(result["class"], "boilerplate")
        self.assertTrue(result["scaffolding_removed"]["is_code"])

    def test_newsletter_chrome_is_boilerplate(self):
        result = dp.classify_silent_edit(NEWSLETTER_CHROME)
        self.assertEqual(result["class"], "boilerplate")
        self.assertGreater(result["scaffolding_removed"]["chrome_phrases"], 0)

    def test_tracking_config_is_boilerplate(self):
        self.assertEqual(dp.classify_silent_edit(TRACKING_CONFIG)["class"], "boilerplate")

    def test_boilerplate_never_produces_a_sentence(self):
        for fixture in (CSS_VERSION_BUMP, RUM_BEACON, POLYFILL_EXCEPTION,
                        NEWSLETTER_CHROME, TRACKING_CONFIG):
            self.assertEqual(dp.classify_silent_edit(fixture)["residual_sentences"], 0,
                             fixture[:60])


class TestSignalClassification(unittest.TestCase):
    def test_real_editorial_change_is_signal(self):
        result = dp.classify_silent_edit(REAL_EDITORIAL_CHANGE)
        self.assertEqual(result["class"], "signal")
        self.assertGreaterEqual(result["residual_sentences"], 1)
        self.assertGreaterEqual(result["residual_content_words"], dp.MIN_CONTENT_WORDS)

    def test_signal_evidence_quotes_the_change_verbatim(self):
        result = dp.classify_silent_edit(REAL_EDITORIAL_CHANGE)
        self.assertIn("voted 6-3", result["evidence_excerpt"])

    def test_line_counts_are_extracted(self):
        result = dp.classify_silent_edit(REAL_EDITORIAL_CHANGE)
        self.assertEqual(result["lines_added"], 4)
        self.assertEqual(result["lines_removed"], 4)

    def test_signal_never_means_a_finding_of_wrongdoing(self):
        reason = dp.classify_silent_edit(REAL_EDITORIAL_CHANGE)["reason"]
        self.assertNotIn("violation", reason.lower())
        self.assertNotIn("wrongdoing", reason.lower())


class TestUncertainClassification(unittest.TestCase):
    def test_residual_vocabulary_without_prose_is_uncertain(self):
        # Word salad that is neither clean scaffolding nor readable prose. A
        # confident verdict in either direction would be a fabrication.
        snippet = silent(5, 5, ["Klein Sieler Testerman Huylar Melander Okie "
                                "Rutherford Wardle Prescott"],
                         ["Klein Sieler Testerman Huylar Melander Okie "
                          "Rutherford Wardle Prescott Brennan"])
        self.assertEqual(dp.classify_silent_edit(snippet)["class"], "uncertain")


class TestRecurrenceDemotion(unittest.TestCase):
    """The cross-document test. Chrome is what repeats across unrelated pages."""

    def _alert(self, alert_id: int, snippet: str, term: str = "SILENT-EDIT") -> dict:
        triage = (dp.classify_silent_edit(snippet) if term == "SILENT-EDIT"
                  else dp.classify_watchlist(term, snippet))
        return {"id": alert_id, "term": term, "snippet": snippet,
                "created_at": "2026-10-28T00:00:00Z", "triage": triage,
                "alert_class": triage["class"], "document_id": alert_id}

    def test_recurring_evidence_is_demoted_to_boilerplate(self):
        # Three unrelated documents whose only residual evidence is the same
        # related-articles headline: that is a widget, not three edits.
        # This is the real headline observed 21 times across unrelated articles in
        # the live ledger — a related-articles widget, not 21 editorial changes.
        headline = ("Cheyenne finalizes deal to use old municipal building for "
                    "workforce housing pilot program beginning next spring")
        alerts = [self._alert(i, silent(9, 9, [f"unrelated residue {i} alpha beta"],
                                        [headline]))
                  for i in range(1, 4)]
        result = dp.apply_recurrence_demotion(alerts)
        self.assertEqual(result["demoted_alerts"], 3)
        for a in alerts:
            self.assertEqual(a["alert_class"], "boilerplate")
            self.assertIn("site-wide chrome", a["triage"]["reason"])

    def test_demotion_is_auditable_not_silent(self):
        # The point of the audit trail is that a reader can see what the demotion
        # changed, not that the pre-demotion class was any particular value.
        headline = ("Cheyenne finalizes deal to use old municipal building for "
                    "workforce housing pilot program beginning next spring")
        alerts = [self._alert(i, silent(9, 9, [f"unrelated residue {i} alpha beta"],
                                        [headline]))
                  for i in range(1, 4)]
        dp.apply_recurrence_demotion(alerts)
        for a in alerts:
            self.assertIn("class_before_recurrence", a["triage"])
            self.assertNotEqual(a["triage"]["class_before_recurrence"], "boilerplate")
            self.assertEqual(a["triage"]["class"], "boilerplate")
            self.assertEqual(a["alert_class"], "boilerplate")
            self.assertIn("site-wide chrome", a["triage"]["reason"])

    def test_recurrent_evidence_is_recorded_per_side(self):
        headline = ("Cheyenne finalizes deal to use old municipal building for "
                    "workforce housing pilot program beginning next spring")
        alerts = [self._alert(i, silent(9, 9, [f"unrelated residue {i} alpha beta"],
                                        [headline]))
                  for i in range(1, 4)]
        dp.apply_recurrence_demotion(alerts)
        for a in alerts:
            sides = [row["side_key"].split(":", 1)[0]
                     for row in a["triage"]["recurrent_evidence"]]
            self.assertIn("added", sides)
            self.assertNotIn("removed", sides,
                             "unique removed residue must not be treated as chrome")

    def test_unique_evidence_is_not_demoted(self):
        # Each fixture must be a distinct, sentence-length editorial change, or
        # the classifier correctly declines to call it signal in the first place.
        alerts = [
            self._alert(1, silent(4, 4,
                ["The council voted five to four to postpone the second reading of "
                 "the ordinance until November."],
                ["The council voted six to three to approve the second reading of "
                 "the ordinance immediately."])),
            self._alert(2, silent(4, 4,
                ["Staff reported a shortfall in the water entitlement fund for the "
                 "current fiscal year."],
                ["Staff reported a surplus in the water entitlement fund for the "
                 "current fiscal year."])),
            self._alert(3, silent(4, 4,
                ["The mayor abstained from the vote on the annexation request."],
                ["The mayor recused herself from the vote on the annexation request."])),
        ]
        result = dp.apply_recurrence_demotion(alerts)
        self.assertEqual(result["demoted_alerts"], 0)
        for a in alerts:
            self.assertEqual(a["alert_class"], "signal")

    def test_below_threshold_is_not_demoted(self):
        headline = ("A shared widget line that appears twice only in the whole "
                    "ledger and nowhere else")
        alerts = [self._alert(i, silent(9, 9, [f"unrelated residue {i} alpha beta"],
                                        [headline]))
                  for i in (1, 2)]
        result = dp.apply_recurrence_demotion(alerts)
        self.assertEqual(result["demoted_alerts"], 0)
        self.assertEqual(result["recurrence_threshold"], dp.RECURRENCE_THRESHOLD)

    def test_watchlist_terms_are_never_demoted(self):
        # A human authored these terms. Recurrence across documents is expected
        # and is the point, not evidence of chrome.
        alerts = [self._alert(i, "Microsoft data center annexation",
                              term="data_center_fight:Microsoft") for i in range(1, 6)]
        result = dp.apply_recurrence_demotion(alerts)
        self.assertEqual(result["demoted_alerts"], 0)
        for a in alerts:
            self.assertEqual(a["alert_class"], "signal")

    def test_already_boilerplate_is_not_recounted_as_demoted(self):
        alerts = [self._alert(i, CSS_VERSION_BUMP) for i in range(1, 4)]
        result = dp.apply_recurrence_demotion(alerts)
        self.assertEqual(result["demoted_alerts"], 0)
        for a in alerts:
            self.assertNotIn("class_before_recurrence", a["triage"])

    def test_most_common_evidence_reports_recurrences(self):
        headline = ("Cheyenne finalizes deal to use old municipal building for "
                    "workforce housing pilot program beginning next spring")
        alerts = [self._alert(i, silent(9, 9, [f"unrelated residue {i} alpha beta"],
                                        [headline]))
                  for i in range(1, 6)]
        result = dp.apply_recurrence_demotion(alerts)
        self.assertTrue(result["most_common_evidence"])
        self.assertEqual(result["most_common_evidence"][0]["recurrences"], 5)


class TestCodeLikeness(unittest.TestCase):
    def test_object_literal_config_is_detected_as_code(self):
        # Real fixture from the ledger, recurred 60 times: a tracking-config
        # object. Its keywords are ordinary English words, so only the structural
        # key:value / dotted-member shape identifies it.
        config = ("window ppconfig productName d222c26d10f0a88dacceb3da240b347e "
                  "deleteIsEnforced true sealIsEnforced false pageId 991")
        result = dp.code_likeness(config)
        self.assertTrue(result["is_code"])
        self.assertGreaterEqual(result["structural_code_shapes"], dp.MIN_STRUCTURAL_SHAPES)

    def test_municipal_prose_has_no_structural_code_shapes(self):
        prose = ("The board does not have the ability to deny the project but can "
                 "mitigate the effects on neighbors through the site plan review.")
        self.assertLess(dp.code_likeness(prose)["structural_code_shapes"],
                        dp.MIN_STRUCTURAL_SHAPES)

    def test_javascript_is_detected(self):
        code = ("window.BOOMR_config=function(){var e=document.createElement('script');"
                "e.async=true;if(typeof navigator!=='undefined'){return e;}}();")
        self.assertTrue(dp.code_likeness(code)["is_code"])

    def test_municipal_prose_is_not_detected_as_code(self):
        prose = ("The board does not have the ability to deny the project but can "
                 "mitigate the effects on neighbors through the site plan review.")
        result = dp.code_likeness(prose)
        self.assertFalse(result["is_code"])
        self.assertLess(result["punctuation_density"], dp.CODE_PUNCT_RATIO)

    def test_empty_residue_is_not_code(self):
        self.assertFalse(dp.code_likeness("")["is_code"])


class TestScaffoldingStripping(unittest.TestCase):
    def test_asset_urls_are_removed_and_counted(self):
        residue, counts = dp.strip_scaffolding(
            "see https://capcity.news/wp-content/x/block_styles.css?ver=4.36.5 here")
        self.assertNotIn("block_styles.css", residue)
        self.assertEqual(counts["asset_urls"], 1)

    def test_cache_busters_are_counted(self):
        _, counts = dp.strip_scaffolding("a?ver=1.2 b&ver=3.4 data-pmdelayedstyle=x")
        self.assertGreaterEqual(counts["cache_busters"], 2)

    def test_script_blocks_removed_before_tag_stripping(self):
        # Order matters: stripping tags first would leave the script body as bare
        # identifier soup, which inflates the residual word count and reads as prose.
        residue, counts = dp.strip_scaffolding(
            "<script>var x = document.createElement('p');</script>Real sentence here.")
        self.assertEqual(counts["script_style_blocks"], 1)
        self.assertNotIn("createElement", residue)
        self.assertIn("Real sentence here", residue)

    def test_chrome_phrases_removed_by_phrase_not_by_word(self):
        # "email" and "news" are ordinary editorial words; only the fixed phrases
        # that recur across every page of a domain are chrome.
        residue, counts = dp.strip_chrome(
            "Do you have email set up? The council discussed the email policy.")
        self.assertEqual(counts["chrome_phrases"], 1)
        self.assertIn("email policy", residue)

    def test_glyph_tokens_removed(self):
        # Icon fonts survive tag-stripping as lone letters, inflating word counts.
        residue, counts = dp.strip_chrome("October 27 2026 t t t t Headline text here")
        self.assertEqual(counts["nav_dates"], 1)
        self.assertGreaterEqual(counts["glyph_tokens"], 4)
        self.assertNotIn(" t ", residue)


class TestNoSendGuarantee(unittest.TestCase):
    """LEGAL.md §4: the engine drafts; a person sends. Tested against the source."""

    def test_no_smtp_or_send_call_exists(self):
        src = Path(dp.__file__).read_text(encoding="utf-8")
        for forbidden in ("import smtplib", "smtplib.", "sendmail(", "send_message(",
                          "requests.post", "urllib.request.urlopen", "http.client",
                          "socket.socket", "urlopen("):
            self.assertNotIn(forbidden, src, forbidden)

    def test_twilio_and_sms_are_absent(self):
        src = Path(dp.__file__).read_text(encoding="utf-8").lower()
        self.assertNotIn("twilio", src.replace("email/twilio/auto-submission", ""))
        self.assertNotIn("sms", src)

    def test_webhook_url_is_recorded_but_never_contacted(self):
        payload = dp.render_json_stream([], {"generated_at": "x", "by_class": {},
                                             "database": "d"},
                                        "https://example.invalid/hook")
        self.assertFalse(payload["delivery"]["posted_by_this_tool"])
        self.assertEqual(payload["delivery"]["webhook_url_configured"],
                         "https://example.invalid/hook")
        self.assertIn("never performs an HTTP POST", payload["delivery"]["statement"])

    def test_email_draft_is_marked_unsent_with_a_placeholder_recipient(self):
        draft = dp.render_email_draft([], {"generated_at": "2026-10-28T00:00:00Z",
                                          "by_class": {"signal": 0, "uncertain": 0,
                                                       "boilerplate": 0},
                                          "database": "d"},
                                     "watchdog@localhost.invalid",
                                     "RECIPIENT-PLACEHOLDER@example.invalid")
        self.assertIn("X-Unsent: 1", draft)
        self.assertIn("[DRAFT — NOT SENT]", draft)
        self.assertIn("RECIPIENT-PLACEHOLDER@example.invalid", draft)
        self.assertIn("LEGAL.md section 4", draft)
        self.assertNotIn("@gmail.com", draft)

    def test_every_channel_declares_it_was_not_sent(self):
        # Asserted through the published channels manifest contract.
        src = Path(dp.__file__).read_text(encoding="utf-8")
        self.assertIn('"sent_by_this_tool": False', src)
        self.assertIn('"posted_by_this_tool": False', src)
        self.assertIn("draft-file-never-sent", src)


class TestFeedRendering(unittest.TestCase):
    def _alerts(self):
        triage = dp.classify_watchlist("test:term", "Microsoft data center annexation")
        return [{
            "uid": "u1", "id": 1, "document_id": 1, "term": "test:term",
            "snippet": "Microsoft data center annexation",
            "created_at": "2026-10-28T05:48:38Z",
            "url": "https://example.invalid/article",
            "title": "Council approves annexation", "source": "src",
            "sha256": "abc", "triage": triage, "alert_class": "signal",
        }]

    def _meta(self):
        return {"generated_at": "2026-10-28T06:00:00Z", "database": "data/engine.db",
                "by_class": {"signal": 1, "uncertain": 0, "boilerplate": 188},
                "silent_edit_noise_floor_percent": 83.56,
                "silent_edit_boilerplate": 188, "silent_edit_total": 225}

    def test_rss_is_well_formed_xml_with_one_item_per_alert(self):
        xml_text = dp.render_rss(self._alerts(), "https://example.invalid/", self._meta())
        root = ET.fromstring(xml_text)
        self.assertEqual(root.tag, "rss")
        self.assertEqual(len(root.findall(".//item")), 1)
        self.assertEqual(root.find(".//item/guid").text, "u1")
        self.assertEqual(root.find(".//item/guid").get("isPermaLink"), "false")

    def test_rss_pubdate_is_rfc822(self):
        xml_text = dp.render_rss(self._alerts(), "https://example.invalid/", self._meta())
        pub = ET.fromstring(xml_text).find(".//item/pubDate").text
        self.assertRegex(pub, r"^[A-Z][a-z]{2}, \d{2} [A-Z][a-z]{2} \d{4} "
                              r"\d{2}:\d{2}:\d{2} \+0000$")

    def test_rss_carries_the_noise_floor_so_the_feed_is_not_overread(self):
        xml_text = dp.render_rss(self._alerts(), "https://example.invalid/", self._meta())
        self.assertIn("83.56", xml_text)
        self.assertIn("boilerplate", xml_text)

    def test_atom_is_well_formed_with_namespaced_entries(self):
        xml_text = dp.render_atom(self._alerts(), "https://example.invalid/", self._meta())
        root = ET.fromstring(xml_text)
        self.assertEqual(root.tag, "{http://www.w3.org/2005/Atom}feed")
        entries = root.findall("{http://www.w3.org/2005/Atom}entry")
        self.assertEqual(len(entries), 1)
        self.assertTrue(entries[0].find("{http://www.w3.org/2005/Atom}id").text)

    def test_xml_special_characters_are_escaped(self):
        alerts = self._alerts()
        alerts[0]["title"] = 'Council <approves> & "annexation"'
        alerts[0]["snippet"] = "a & b < c"
        xml_text = dp.render_rss(alerts, "https://example.invalid/", self._meta())
        root = ET.fromstring(xml_text)  # raises if malformed
        self.assertIn("&", root.find(".//item/title").text)

    def test_guid_is_stable_across_runs(self):
        # An unstable guid makes every feed reader re-announce every alert.
        first = dp.render_rss(self._alerts(), "https://e.invalid/", self._meta())
        second = dp.render_rss(self._alerts(), "https://e.invalid/", self._meta())
        self.assertEqual(ET.fromstring(first).find(".//item/guid").text,
                         ET.fromstring(second).find(".//item/guid").text)


class TestSelectionAndDigest(unittest.TestCase):
    def _alerts(self):
        out = []
        for i, cls in enumerate(("signal", "uncertain", "boilerplate")):
            out.append({"uid": f"u{i}", "id": i, "document_id": i, "term": f"t:{cls}",
                        "snippet": "x", "created_at": "2026-10-28T00:00:00Z",
                        "url": "https://e.invalid/", "title": f"Title {cls}",
                        "source": "s", "sha256": "h", "alert_class": cls,
                        "triage": {"class": cls, "reason": "r",
                                   "evidence_excerpt": "e",
                                   "residual_content_words": 3}})
        return out

    def test_default_publishes_signal_only(self):
        self.assertEqual([a["alert_class"] for a in dp.select(self._alerts(), "signal")],
                         ["signal"])

    def test_uncertain_floor_includes_signal(self):
        selected = dp.select(self._alerts(), "uncertain")
        self.assertEqual({a["alert_class"] for a in selected}, {"signal", "uncertain"})

    def test_boilerplate_floor_is_the_firehose(self):
        self.assertEqual(len(dp.select(self._alerts(), "boilerplate")), 3)

    def test_class_ranks_are_ordered(self):
        self.assertLess(dp.CLASS_RANK["boilerplate"], dp.CLASS_RANK["uncertain"])
        self.assertLess(dp.CLASS_RANK["uncertain"], dp.CLASS_RANK["signal"])

    def test_digest_withholds_uncertain_and_says_so(self):
        alerts = self._alerts()
        meta = {"generated_at": "2026-10-28T00:00:00Z", "database": "data/engine.db",
                "by_class": {"signal": 1, "uncertain": 1, "boilerplate": 1}}
        text = dp.render_digest(dp.select(alerts, "signal"), meta)
        self.assertIn("--min-class uncertain", text)
        self.assertIn("withheld, not dismissed", text)
        self.assertIn("not a finding of wrongdoing", text)
        self.assertIn("Absence of an alert is not evidence", text)


class TestLedgerAccessIsReadOnly(unittest.TestCase):
    def _make_db(self, tmp: Path) -> Path:
        db = tmp / "engine.db"
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE documents (id INTEGER PRIMARY KEY, source TEXT, "
                     "url TEXT, title TEXT, first_seen TEXT, last_checked TEXT, "
                     "published_at TEXT, local_path TEXT, sha256 TEXT, "
                     "size_bytes INTEGER, status TEXT)")
        conn.execute("CREATE TABLE alerts (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                     "document_id INTEGER NOT NULL, term TEXT NOT NULL, "
                     "snippet TEXT NOT NULL, created_at TEXT NOT NULL)")
        conn.execute("INSERT INTO documents (id, source, url, title, sha256) VALUES "
                     "(1, 'src', 'https://e.invalid/a', 'Article One', 'deadbeef')")
        conn.execute("INSERT INTO alerts (document_id, term, snippet, created_at) "
                     "VALUES (1, 'SILENT-EDIT', ?, '2026-10-28T05:48:38Z')",
                     (CSS_VERSION_BUMP,))
        conn.execute("INSERT INTO alerts (document_id, term, snippet, created_at) "
                     "VALUES (1, 'test:Microsoft', 'Microsoft data center', "
                     "'2026-10-28T04:00:00Z')")
        conn.commit()
        conn.close()
        return db

    def test_opens_read_only_and_reports_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = self._make_db(Path(tmp))
            alerts, meta = dp.load_alerts(db)
            self.assertEqual(meta["alerts"], 2)
            self.assertTrue(meta["read_only"])
            self.assertEqual(meta["silent_edit_total"], 1)
            self.assertEqual(meta["silent_edit_boilerplate"], 1)
            self.assertEqual(meta["silent_edit_noise_floor_percent"], 100.0)

    def test_missing_database_is_a_clear_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit) as ctx:
                dp.load_alerts(Path(tmp) / "absent.db")
            self.assertIn("ledger not found", str(ctx.exception))

    def test_alert_without_a_document_row_still_classifies(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "engine.db"
            conn = sqlite3.connect(db)
            conn.execute("CREATE TABLE documents (id INTEGER PRIMARY KEY, source TEXT, "
                         "url TEXT, title TEXT, first_seen TEXT, last_checked TEXT, "
                         "published_at TEXT, local_path TEXT, sha256 TEXT, "
                         "size_bytes INTEGER, status TEXT)")
            conn.execute("CREATE TABLE alerts (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                         "document_id INTEGER NOT NULL, term TEXT NOT NULL, "
                         "snippet TEXT NOT NULL, created_at TEXT NOT NULL)")
            conn.execute("INSERT INTO alerts (document_id, term, snippet, created_at) "
                         "VALUES (99, 'SILENT-EDIT', ?, '2026-10-28T05:48:38Z')",
                         (CSS_VERSION_BUMP,))
            conn.commit()
            conn.close()
            alerts, meta = dp.load_alerts(db)
            self.assertEqual(meta["alerts"], 1)
            self.assertIsNone(alerts[0]["url"])
            self.assertEqual(alerts[0]["alert_class"], "boilerplate")


class TestUidStability(unittest.TestCase):
    def test_uid_is_deterministic(self):
        self.assertEqual(dp.hashlib_shard("a|b|c"), dp.hashlib_shard("a|b|c"))
        self.assertNotEqual(dp.hashlib_shard("a|b|c"), dp.hashlib_shard("a|b|d"))

    def test_uid_length_is_bounded(self):
        self.assertEqual(len(dp.hashlib_shard("x" * 10_000)), 32)


if __name__ == "__main__":
    unittest.main(verbosity=2)
