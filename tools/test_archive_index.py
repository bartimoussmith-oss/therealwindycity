#!/usr/bin/env python3
"""Tests for tools/archive_index.py — stdlib unittest, hermetic, no network.

The date parsers get the most coverage because a wrong meeting date is the one
error a researcher cannot detect or recover from downstream: it looks like a
fact. Two real bugs found while building this tool are pinned here so they
cannot return:
  * abbreviated month names ("Jun  9, 2008") were rejected, which silently left
    3,207 of 5,140 records undated on the first run;
  * a lazy \\d{1,2} in the municipal-docs pattern parsed "cow-06-04-2025" as
    month=06 day=0 year=2004, emitting the plausible, wrong date 2020-06-04.
"""
from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import archive_index as ai  # noqa: E402


class TestEpochFolderScheme(unittest.TestCase):
    def test_full_month_name(self):
        r = ai.parse_epoch_folder("1211871600May 27, 2008 - Cheyenne City Council")
        self.assertTrue(r["parsed"])
        self.assertEqual(r["scheme"], "epoch-folder")
        self.assertEqual(r["date"], "2008-05-27")
        self.assertEqual(r["date_epoch_utc"], "2008-05-27")
        self.assertFalse(r["date_conflict"])
        self.assertEqual(r["body"], "city-council")

    def test_abbreviated_month_with_double_space(self):
        # This exact shape failed on the first run: "Jun" is not "June", and the
        # archive pads single-digit days with two spaces.
        r = ai.parse_epoch_folder("1212994800Jun  9, 2008 - Cheyenne City Council")
        self.assertTrue(r["parsed"], r)
        self.assertEqual(r["date"], "2008-06-09")
        self.assertEqual(r["date_epoch_utc"], "2008-06-09")

    def test_every_abbreviated_month_parses(self):
        epochs = {"Jan": 1200000000, "Feb": 1204000000, "Mar": 1206000000,
                  "Apr": 1208000000, "May": 1210000000, "Jun": 1212994800,
                  "Jul": 1216018800, "Aug": 1218438000, "Sep": 1220857200,
                  "Oct": 1223881200, "Nov": 1226304000, "Dec": 1229000000}
        for abbrev in epochs:
            self.assertIn(abbrev, ai.MONTHS, f"{abbrev} missing from MONTHS")
        # Sept is a fourth-letter variant that occurs in some municipal feeds.
        self.assertEqual(ai.MONTHS["Sept"], 9)

    def test_epoch_pretty_disagreement_is_a_conflict_not_a_guess(self):
        # 1211871600 is 2008-05-27; claiming Jul 14, 2008 must be flagged.
        r = ai.parse_epoch_folder("1211871600Jul 14, 2008 - City Council")
        self.assertTrue(r["parsed"])
        self.assertTrue(r["date_conflict"])
        self.assertGreater(r["date_conflict_days"], 1)

    def test_unknown_body_is_slugified_not_dropped(self):
        r = ai.parse_epoch_folder("1211871600May 27, 2008 - Sine Die Session - Agenda Only")
        self.assertTrue(r["parsed"])
        self.assertEqual(r["body"], "sine-die-session-agenda-only")
        self.assertEqual(r["body_raw"], "Sine Die Session - Agenda Only")

    def test_pattern_mismatch_reports_reason(self):
        r = ai.parse_epoch_folder("agenda-packets")
        self.assertFalse(r["parsed"])
        self.assertEqual(r["reason"], "folder-name-pattern-mismatch")

    def test_unknown_month_reports_reason(self):
        r = ai.parse_epoch_folder("1211871600Xyz 27, 2008 - City Council")
        self.assertFalse(r["parsed"])
        self.assertTrue(r["reason"].startswith("unknown-month"))


class TestAgendaPacketScheme(unittest.TestCase):
    def test_iso_prefix_filename(self):
        r = ai.parse_agenda_packet("agenda-packets/CHEY-2012-10-22_Minutes.pdf")
        self.assertTrue(r["parsed"])
        self.assertEqual(r["scheme"], "agenda-packet")
        self.assertEqual(r["date"], "2012-10-22")
        self.assertEqual(r["body"], "city-council")

    def test_iso_suffix_filename(self):
        r = ai.parse_agenda_packet("agenda-packets/Agenda_CHEY-2013-10-04.pdf")
        self.assertTrue(r["parsed"])
        self.assertEqual(r["date"], "2013-10-04")

    def test_packet_part_number_captured(self):
        r = ai.parse_agenda_packet("agenda-packets/CHEY-2012-10-22_packet-11.pdf")
        self.assertTrue(r["parsed"])
        self.assertEqual(r["packet_part"], 11)

    def test_directory_scheme_rescues_undated_attachments(self):
        # The filename carries no date at all; the directory does. Without this
        # fallback the entire Attachments tier (135 files) is undated.
        path = ("agenda-packets/2022-11-14_City Council Meeting - Nov 14, 2022/"
                "Attachments/Supporting Document.pdf")
        r = ai.parse_agenda_packet(path)
        self.assertTrue(r["parsed"], r)
        self.assertEqual(r["scheme"], "agenda-packet-dir")
        self.assertEqual(r["date"], "2022-11-14")
        self.assertEqual(r["attachment_tier"], "Attachments")
        self.assertFalse(r["date_conflict"])

    def test_directory_scheme_flags_internal_disagreement(self):
        # Real record: directory says 2023-09-27, its own pretty date says Sep 25.
        path = ("agenda-packets/2023-09-27_City Council Meeting - Sep 25, 2023/"
                "Attachments/Proposed Substitution.pdf")
        r = ai.parse_agenda_packet(path)
        self.assertTrue(r["parsed"])
        self.assertEqual(r["date"], "2023-09-27")
        self.assertEqual(r["date_pretty_in_dir"], "2023-09-25")
        self.assertTrue(r["date_conflict"])
        self.assertEqual(r["date_conflict_days"], 2)

    def test_no_date_anywhere_is_a_finding(self):
        r = ai.parse_agenda_packet("agenda-packets/Proposed Substitute.pdf")
        self.assertFalse(r["parsed"])
        self.assertIn("no-ISO-directory", r["reason"])

    def test_invalid_iso_date_rejected(self):
        r = ai.parse_agenda_packet("agenda-packets/CHEY-2012-13-45_Agenda.pdf")
        self.assertFalse(r["parsed"])


class TestMunicipalDocsScheme(unittest.TestCase):
    """The lazy-quantifier bug class. Every case here produced a wrong date once."""

    def test_four_digit_year_is_not_eaten_by_a_lazy_day(self):
        r = ai.parse_municipal_docs("municipal-docs/cow-06-04-2025-agenda.pdf")
        self.assertTrue(r["parsed"])
        self.assertEqual(r["date"], "2025-06-04")
        self.assertNotEqual(r["date"], "2020-06-04")
        self.assertEqual(r["body"], "committee-of-the-whole")
        self.assertTrue(r["date_ambiguous"])
        self.assertFalse(r["two_digit_year"])

    def test_two_digit_year_month_first(self):
        r = ai.parse_municipal_docs("municipal-docs/cow-02-23-22-agenda.pdf")
        self.assertEqual(r["date"], "2022-02-23")
        self.assertFalse(r["date_ambiguous"])
        self.assertTrue(r["two_digit_year"])

    def test_finance_committee_prefix(self):
        r = ai.parse_municipal_docs("municipal-docs/fc-01-04-22-agenda.pdf")
        self.assertTrue(r["parsed"])
        self.assertEqual(r["date"], "2022-01-04")
        self.assertEqual(r["body"], "finance-committee")
        self.assertEqual(r["body_prefix"], "fc")

    def test_infix_modifier_between_body_and_date(self):
        # psc-sm-05-22-23: "sm" (special meeting) sits between body and date.
        r = ai.parse_municipal_docs("municipal-docs/psc-sm-05-22-23-agenda.pdf")
        self.assertTrue(r["parsed"], r)
        self.assertEqual(r["date"], "2023-05-22")
        self.assertEqual(r["body"], "public-services-committee")

    def test_suffix_after_year_does_not_extend_the_year(self):
        r = ai.parse_municipal_docs("municipal-docs/fc-02-07-22-agenda-2.pdf")
        self.assertEqual(r["date"], "2022-02-07")

    def test_day_greater_than_twelve_disambiguates(self):
        r = ai.parse_municipal_docs("municipal-docs/ws-11-15-2025-agenda.pdf")
        self.assertEqual(r["date"], "2025-11-15")
        self.assertFalse(r["date_ambiguous"])

    def test_ambiguity_is_flagged_with_a_note_never_silently_resolved(self):
        r = ai.parse_municipal_docs("municipal-docs/ws-03-04-2025-agenda.pdf")
        self.assertTrue(r["date_ambiguous"])
        self.assertIn("month-first assumed", r["date_ambiguity_note"])

    def test_all_six_body_prefixes_map(self):
        for prefix, (body, _) in ai.MUNICIPAL_BODIES.items():
            r = ai.parse_municipal_docs(f"municipal-docs/{prefix}-06-15-2024-agenda.pdf")
            self.assertTrue(r["parsed"], f"{prefix} failed")
            self.assertEqual(r["body"], body)

    def test_impossible_date_rejected(self):
        r = ai.parse_municipal_docs("municipal-docs/fc-02-31-22-agenda.pdf")
        self.assertFalse(r["parsed"])
        self.assertTrue(r["reason"].startswith("impossible-date"))

    def test_unknown_filename_is_a_finding(self):
        r = ai.parse_municipal_docs("municipal-docs/Feb 2nd 2026 Admin Warrant.pdf")
        self.assertFalse(r["parsed"])
        self.assertEqual(r["reason"], "no-body-prefix-date-in-filename")


class TestDateSubdirSchemes(unittest.TestCase):
    def test_planning_commission(self):
        r = ai.parse_record_path("planning-commission/2024-01-11/Agenda.pdf")
        self.assertTrue(r["parsed"])
        self.assertEqual(r["scheme"], "planning-commission")
        self.assertEqual(r["date"], "2024-01-11")
        self.assertEqual(r["body"], "planning-commission")

    def test_county_commissioners(self):
        r = ai.parse_record_path("Board_of_County_Commissioners/2024-01-02/Minutes.pdf")
        self.assertTrue(r["parsed"])
        self.assertEqual(r["scheme"], "county-commissioners")
        self.assertEqual(r["body"], "board-of-county-commissioners")

    def test_non_iso_subdirectory(self):
        r = ai.parse_record_path("planning-commission/not-a-date/Agenda.pdf")
        self.assertFalse(r["parsed"])
        self.assertIn("non-iso-subdirectory", r["reason"])


class TestDispatch(unittest.TestCase):
    def test_root_file_is_not_a_meeting_record(self):
        r = ai.parse_record_path("README.md")
        self.assertFalse(r["parsed"])
        self.assertEqual(r["scheme"], "repo-root-file")

    def test_every_scheme_is_declared(self):
        for scheme in ("epoch-folder", "agenda-packet", "agenda-packet-dir",
                       "planning-commission", "county-commissioners",
                       "municipal-docs", "repo-root-file", "unparsed"):
            self.assertIn(scheme, ai.SCHEMES)

    def test_dispatch_by_top_directory(self):
        cases = {
            "1211871600May 27, 2008 - City Council/x.pdf": "epoch-folder",
            "agenda-packets/CHEY-2012-10-22_Minutes.pdf": "agenda-packet",
            "planning-commission/2024-01-11/Agenda.pdf": "planning-commission",
            "municipal-docs/cow-06-04-2025-agenda.pdf": "municipal-docs",
        }
        for path, expected in cases.items():
            self.assertEqual(ai.parse_record_path(path)["scheme"], expected, path)


class TestDocumentClass(unittest.TestCase):
    def test_recognised_classes(self):
        cases = {
            "CHEY-2012-10-22_Minutes.pdf": "minutes",
            "Agenda_CHEY-2013-10-04.pdf": "agenda",
            "Proposed Amended Exhibit B.pdf": "amended-exhibit",
            "Approved Substitute.pdf": "approved-substitute",
            "Additional Documents, Staff Report.pdf": "staff-report",
            "Reappropriation Backup FY2014.pdf": "budget",
            "Ordinance 2022-15.pdf": "ordinance",
            "Resolution 2022-88.pdf": "resolution",
        }
        for filename, expected in cases.items():
            self.assertEqual(ai.classify_document(filename), expected, filename)

    def test_unrecognised_is_other_not_a_guess(self):
        self.assertEqual(ai.classify_document("mystery-file.pdf"), "other")
        self.assertEqual(ai.classify_document("CHEY-2012-10-22_packet-11.pdf"), "other")

    def test_underscore_separator_does_not_defeat_word_boundaries(self):
        # Regression: `_` is a word character, so \bminutes\b found no boundary
        # in "CHEY-2012-10-22_Minutes.pdf" and the file classified as "other".
        self.assertEqual(ai.classify_document("CHEY-2012-10-22_Minutes.pdf"), "minutes")
        self.assertEqual(ai.classify_document("CHEY-2012-10-22_Agenda.pdf"), "agenda")

    def test_reappropriation_is_budget(self):
        # Regression: \bappropriat never matches inside "Reappropriation".
        self.assertEqual(ai.classify_document("Reappropriation Backup FY2014.pdf"), "budget")
        self.assertEqual(ai.classify_document("Budget Message.pdf"), "budget")


class TestSourceLocator(unittest.TestCase):
    def test_spaces_and_commas_are_percent_encoded(self):
        # An unencoded archive URL is broken in every browser and renderer.
        loc = ai.source_locator("therealwindycity/cheyenne-archives-2022",
                                "1641801600Jan 10, 2022 - City Council Meeting/x.pdf")
        self.assertNotIn(" ", loc["raw_url"])
        self.assertIn("%20", loc["raw_url"])
        self.assertIn("Jan%2010%2C%202022", loc["raw_url"])
        self.assertEqual(loc["path"],
                         "1641801600Jan 10, 2022 - City Council Meeting/x.pdf")
        self.assertTrue(loc["github_url"].startswith("https://github.com/"))

    def test_original_path_preserved_verbatim(self):
        path = "agenda-packets/2023-09-27_City Council Meeting - Sep 25, 2023/a.pdf"
        self.assertEqual(ai.source_locator("r", path)["path"], path)


class TestTokenize(unittest.TestCase):
    def test_stopwords_and_short_tokens_removed(self):
        tokens = ai.tokenize("The council voted on a motion to approve")
        self.assertNotIn("the", tokens)
        self.assertNotIn("on", tokens)
        self.assertNotIn("a", tokens)
        self.assertIn("council", tokens)
        self.assertIn("motion", tokens)

    def test_procedural_vocabulary_is_preserved(self):
        # An aggressive stoplist destroys exactly the words that matter here.
        for word in ("motion", "seconded", "objection", "abstain", "quorum"):
            self.assertIn(word, ai.tokenize(f"the {word} was recorded"))

    def test_hyphens_and_apostrophes_kept_inside_tokens(self):
        tokens = ai.tokenize("sixth-penny and council's budget")
        self.assertIn("sixth-penny", tokens)
        self.assertIn("council's", tokens)

    def test_shard_assignment_is_stable_and_in_range(self):
        for token in ("annexation", "zoning", "reappropriation", "variance"):
            shard = ai.shard_of(token)
            self.assertEqual(shard, ai.shard_of(token))
            self.assertTrue(0 <= shard < ai.SHARD_COUNT)


class TestPdfText(unittest.TestCase):
    def test_garbage_bytes_do_not_raise(self):
        text, method = ai.pdf_text(b"not a pdf at all")
        self.assertEqual(text, "")
        self.assertTrue(method.startswith("failed:") or method.startswith("unavailable"),
                        method)


class TestIndexAndSearch(unittest.TestCase):
    """End-to-end over a synthetic corpus: extract-cache -> index -> BM25 search."""

    def _write_doc(self, cache: Path, doc_id: str, text: str, **meta):
        payload = {"id": doc_id, "path": meta.get("path", f"{doc_id}.pdf"),
                   "repository": meta.get("repository", "r/repo"),
                   "meeting_date": meta.get("meeting_date", "2024-01-11"),
                   "body": meta.get("body", "planning-commission"),
                   "document_class": meta.get("document_class", "minutes"),
                   "bytes": 100, "blob_sha": "abc", "method": "text-layer:pypdf-test",
                   "chars": len(text), "text": text,
                   "raw_url": f"https://example.invalid/{doc_id}",
                   "github_url": f"https://example.invalid/{doc_id}"}
        with gzip.open(cache / f"{doc_id}.json.gz", "wt", encoding="utf-8") as fh:
            json.dump(payload, fh)

    def _build(self, tmp: Path) -> Path:
        out = tmp / "idx"
        cache = out / "text"
        cache.mkdir(parents=True)
        self._write_doc(cache, "docA",
                        "annexation of the parcel was recommended by the commission "
                        "annexation annexation zoning variance",
                        meeting_date="2024-03-14")
        self._write_doc(cache, "docB",
                        "the commission discussed a zoning variance for the property",
                        meeting_date="2024-06-27", document_class="agenda")
        self._write_doc(cache, "docC",
                        "budget reappropriation for the fiscal year was tabled",
                        meeting_date="2025-01-09", body="finance-committee")
        self._write_doc(cache, "docEmpty", "", meeting_date="2025-02-02")
        args = argparse.Namespace(out=str(out), k1=1.5, b=0.75)
        self.assertEqual(ai.stage_index(args), 0)
        return out

    def test_index_counts_searchable_and_unsearchable_separately(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = self._build(Path(tmp))
            stats = json.loads((out / "index" / "stats.json").read_text())
            self.assertEqual(stats["documents"], 4)
            self.assertEqual(stats["searchable_documents"], 3)
            self.assertEqual(stats["unsearchable_documents"], 1)
            self.assertGreater(stats["distinct_tokens"], 0)
            self.assertEqual(len(stats["shards"]), stats["shard_count"])

    def test_term_frequency_raises_rank(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = self._build(Path(tmp))
            res = ai.bm25_search("annexation", out, k=5)
            self.assertEqual(res["total"], 1)
            self.assertEqual(res["hits"][0]["id"], "docA")
            self.assertEqual(res["hits"][0]["matched_tokens"], ["annexation"])
            self.assertEqual(res["hits"][0]["token_coverage"], 1.0)

    def test_full_coverage_outranks_partial(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = self._build(Path(tmp))
            res = ai.bm25_search("zoning variance annexation", out, k=5)
            self.assertEqual(res["hits"][0]["id"], "docA")
            self.assertEqual(res["hits"][0]["token_coverage"], 1.0)
            self.assertLess(res["hits"][1]["token_coverage"], 1.0)

    def test_body_and_year_filters(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = self._build(Path(tmp))
            res = ai.bm25_search("reappropriation budget", out, k=5,
                                 body="finance-committee")
            self.assertEqual([h["id"] for h in res["hits"]], ["docC"])
            res2 = ai.bm25_search("zoning", out, k=5, year="2024")
            self.assertTrue(all(h["meeting_date"].startswith("2024") for h in res2["hits"]))
            res3 = ai.bm25_search("zoning", out, k=5, year="1999")
            self.assertEqual(res3["total"], 0)

    def test_every_hit_carries_a_source_locator(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = self._build(Path(tmp))
            res = ai.bm25_search("zoning variance", out, k=5)
            for hit in res["hits"]:
                self.assertTrue(hit["raw_url"])
                self.assertTrue(hit["github_url"])
                self.assertTrue(hit["path"])
                self.assertTrue(hit["repository"])

    def test_result_always_carries_the_coverage_warning(self):
        # Absence of a hit must never be readable as absence from the archive.
        with tempfile.TemporaryDirectory() as tmp:
            out = self._build(Path(tmp))
            res = ai.bm25_search("zzzznotaword", out, k=5)
            self.assertEqual(res["total"], 0)
            self.assertIn("NOT", res["coverage_warning"])

    def test_empty_query_reports_no_tokens(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = self._build(Path(tmp))
            res = ai.bm25_search("the and of", out, k=5)
            self.assertEqual(res["tokens"], [])
            self.assertIn("note", res)

    def test_index_is_sharded_and_gzipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = self._build(Path(tmp))
            shards = list((out / "index").glob("shard-*.json.gz"))
            self.assertTrue(shards)
            for shard in shards:
                with gzip.open(shard, "rt", encoding="utf-8") as fh:
                    data = json.load(fh)
                self.assertIsInstance(data, dict)
                for token, postings in data.items():
                    shard_number = int(re.search(r"shard-(\d+)", shard.name).group(1))
                    self.assertEqual(ai.shard_of(token), shard_number)
                    self.assertIsInstance(postings, dict)



class TestDatapackage(unittest.TestCase):
    def _catalog(self):
        return {
            "generated_at": "2026-10-28T00:00:00+00:00",
            "repositories": [{"repository": r, "truncated": False} for r in ai.ARCHIVE_REPOS],
            "totals": {"records": 1, "bytes": 1, "truncated_repositories": [],
                       "earliest_meeting_date": "2008-05-27",
                       "latest_meeting_date": "2026-06-08"},
        }

    def test_descriptor_is_valid_frictionless_shape(self):
        pkg = ai.datapackage(self._catalog())
        self.assertEqual(pkg["name"], "cheyenne-council-archive-catalog")
        self.assertIn("resources", pkg)
        fields = {f["name"]: f for f in pkg["resources"][0]["schema"]["fields"]}
        self.assertEqual(pkg["resources"][0]["schema"]["primaryKey"], "id")
        # Typed date fields are the whole point: this is the guard the ecosystem
        # lacks elsewhere, where a scraped string became a date field.
        self.assertEqual(fields["meeting_date"]["type"], "date")
        self.assertEqual(fields["meeting_date"]["format"], "%Y-%m-%d")
        self.assertEqual(fields["bytes"]["type"], "integer")
        self.assertEqual(fields["date_conflict"]["type"], "boolean")

    def test_source_local_identifiers_are_preserved_verbatim(self):
        pkg = ai.datapackage(self._catalog())
        names = {f["name"] for f in pkg["resources"][0]["schema"]["fields"]}
        for required in ("path", "blob_sha", "repository", "raw_url", "github_url"):
            self.assertIn(required, names)
        self.assertIn("Preserved verbatim",
                      [f for f in pkg["resources"][0]["schema"]["fields"]
                       if f["name"] == "path"][0]["description"])

    def test_completeness_is_explicitly_denied(self):
        pkg = ai.datapackage(self._catalog())
        self.assertFalse(pkg["custom"]["completeness"]["full_historical_coverage"])
        self.assertIn("not", pkg["custom"]["completeness"]["statement"].lower())

    def test_scheme_enum_matches_parser_output(self):
        pkg = ai.datapackage(self._catalog())
        fields = {f["name"]: f for f in pkg["resources"][0]["schema"]["fields"]}
        enum = set(fields["scheme"]["constraints"]["enum"])
        self.assertEqual(enum, set(ai.SCHEMES))


if __name__ == "__main__":
    unittest.main(verbosity=2)
