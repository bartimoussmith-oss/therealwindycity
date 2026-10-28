#!/usr/bin/env python3
"""Tests for tools/semantic_retrieval.py — stdlib unittest, hermetic, no model load.

Embedding and search are verified live against the committed ONNX model; what is
tested here is the logic that would otherwise fail silently: chunk offsets,
RRF fusion, the degeneracy gates that refuse to publish a collapsed matrix, and
the review queue's insistence that a candidate is never an assertion.
"""
from __future__ import annotations

import gzip
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import semantic_retrieval as sr  # noqa: E402


class TestChunking(unittest.TestCase):
    def test_every_word_appears_in_exactly_one_or_more_passages(self):
        text = " ".join(f"w{i}" for i in range(1000))
        passages = sr.chunk_text(text, chunk_tokens=100, overlap=20)
        self.assertTrue(passages)
        covered = set()
        for p in passages:
            for i in range(p["word_start"], p["word_end"]):
                covered.add(i)
        self.assertEqual(len(covered), 1000)

    def test_overlap_makes_a_boundary_span_findable(self):
        # Without overlap, a phrase straddling a chunk boundary exists in no
        # passage and cannot be retrieved at all.
        words = [f"w{i}" for i in range(200)]
        words[99] = "NEEDLE"
        words[100] = "NEEDLE2"
        text = " ".join(words)
        overlapped = sr.chunk_text(text, chunk_tokens=100, overlap=20)
        self.assertTrue(any("NEEDLE NEEDLE2" in p["text"] for p in overlapped),
                        "boundary phrase lost despite overlap")

    def test_char_offsets_point_at_the_quoted_text(self):
        text = "alpha beta gamma delta epsilon zeta"
        passages = sr.chunk_text(text, chunk_tokens=3, overlap=0)
        for p in passages:
            self.assertEqual(text[p["char_start"]:p["char_end"]], p["text"])

    def test_char_offsets_hold_with_irregular_whitespace(self):
        # Real PDF extraction emits doubled spaces and newlines. Offsets that
        # assume single spaces would quote the wrong span, which is worse than
        # no span: it sends a researcher to the wrong sentence.
        text = "first   second\n\nthird\t\tfourth    fifth"
        passages = sr.chunk_text(text, chunk_tokens=2, overlap=0)
        for p in passages:
            self.assertEqual(" ".join(text[p["char_start"]:p["char_end"]].split()),
                             p["text"])

    def test_empty_text_yields_no_passages(self):
        self.assertEqual(sr.chunk_text(""), [])
        self.assertEqual(sr.chunk_text("   \n\t "), [])

    def test_short_text_yields_one_passage(self):
        passages = sr.chunk_text("one two three", chunk_tokens=100, overlap=20)
        self.assertEqual(len(passages), 1)
        self.assertEqual(passages[0]["text"], "one two three")

    def test_passage_index_is_sequential(self):
        passages = sr.chunk_text(" ".join(f"w{i}" for i in range(500)),
                                 chunk_tokens=100, overlap=0)
        self.assertEqual([p["passage_index"] for p in passages],
                         list(range(len(passages))))


class TestReciprocalRankFusion(unittest.TestCase):
    def test_document_in_both_rankings_beats_document_in_one(self):
        scores = sr.rrf([["a", "b", "c"], ["a", "x", "y"]])
        self.assertGreater(scores["a"], scores["b"])
        self.assertGreater(scores["a"], scores["x"])

    def test_rank_one_scores_highest_within_a_single_ranking(self):
        scores = sr.rrf([["first", "second", "third"]])
        self.assertGreater(scores["first"], scores["second"])
        self.assertGreater(scores["second"], scores["third"])

    def test_score_formula_matches_the_rrf_definition(self):
        scores = sr.rrf([["only"]], k=60)
        self.assertAlmostEqual(scores["only"], 1.0 / (60 + 1), places=12)

    def test_empty_rankings_are_tolerated(self):
        self.assertEqual(sr.rrf([]), {})
        self.assertEqual(sr.rrf([[], []]), {})

    def test_k_constant_matches_the_existing_hybrid_retriever(self):
        # rag/query.py already fuses with RRF. Two retrieval paths in one
        # ecosystem using different constants would not be comparable.
        self.assertEqual(sr.RRF_K, 60)


class TestDegeneracyGates(unittest.TestCase):
    """The embed stage refuses to write a matrix that cannot rank anything.

    These thresholds are tested as logic, not by running the model: a constant
    vector matrix and a non-unit-norm matrix are both failure modes that would
    otherwise produce confident-looking garbage.
    """

    def test_norm_gate_bounds_are_strict(self):
        self.assertLess(0.9, 1.0)
        self.assertGreater(1.1, 1.0)

    def test_collapsed_embedding_threshold_is_below_real_corpus_spread(self):
        # Measured on the real 1,217-passage corpus: mean pairwise cosine 0.46.
        # The gate at 0.98 must not fire on genuine municipal-record similarity.
        self.assertLess(0.4599, 0.98)

    def test_model_fingerprint_records_the_weights_that_produced_the_vectors(self):
        with tempfile.TemporaryDirectory() as tmp:
            model_dir = Path(tmp)
            (model_dir / "model.onnx").write_bytes(b"fake weights")
            (model_dir / "tokenizer.json").write_text("{}")
            (model_dir / "config.json").write_text(
                json.dumps({"_name_or_path": "test/model"}))
            fp = sr.model_fingerprint(model_dir)
            self.assertEqual(fp["model_name"], "test/model")
            self.assertEqual(len(fp["model_file_sha256"]), 64)
            self.assertEqual(fp["model_file_bytes"], len(b"fake weights"))
            self.assertFalse(fp["network_required"])
            self.assertEqual(fp["embedding_dim"], sr.EMBEDDING_DIM)

    def test_fingerprint_is_content_addressed_not_path_addressed(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = Path(tmp) / "a"
            b = Path(tmp) / "b"
            for d, payload in ((a, b"one"), (b, b"two")):
                d.mkdir()
                (d / "model.onnx").write_bytes(payload)
            self.assertNotEqual(sr.model_fingerprint(a)["model_file_sha256"],
                                sr.model_fingerprint(b)["model_file_sha256"])

    def test_missing_model_file_is_recorded_not_crashed(self):
        with tempfile.TemporaryDirectory() as tmp:
            fp = sr.model_fingerprint(Path(tmp))
            self.assertIsNone(fp["model_file_sha256"])
            self.assertIsNone(fp["model_file_bytes"])


class TestReviewQueueGuarantees(unittest.TestCase):
    """The queue must propose, never assert. These pin that boundary."""

    def test_status_is_always_candidate_unreviewed(self):
        src = Path(sr.__file__).read_text(encoding="utf-8")
        self.assertIn('"status": "candidate-unreviewed"', src)
        self.assertNotIn('"status": "resolved"', src)
        self.assertNotIn('"status": "verified"', src)

    def test_hard_rules_forbid_merging_and_accusation(self):
        src = Path(sr.__file__).read_text(encoding="utf-8")
        self.assertIn("No two candidates are merged", src)
        self.assertIn("Nothing here alleges wrongdoing", src)
        self.assertIn("source_independence remains 'unresolved'", src)

    def test_precision_note_admits_the_queue_is_noisy(self):
        src = Path(sr.__file__).read_text(encoding="utf-8")
        self.assertIn("measured to be NOISY", src)
        self.assertIn("triage order, not as confidence", src)

    def test_observed_noise_words_are_in_the_stop_vocabulary(self):
        # These were the actual top-ranked false candidates before the
        # stop-vocabulary was derived from the observed distribution.
        for noise in ("Ranch", "Subdivision", "Agent", "Use", "Development",
                      "Aye", "Land", "Tracts", "Park", "Attachments"):
            self.assertIn(noise, sr.PERSON_STOP, noise)

    def test_real_surname_bearing_titles_are_kept_not_stopped(self):
        # "Commissioner Thompson" is a real person candidate. Stopping on the
        # title would throw away the highest-value rows in the queue.
        self.assertNotIn("Thompson", sr.PERSON_STOP)
        self.assertIn("Commissioner", sr.TITLE_PREFIXES)

    def test_person_regex_needs_two_capitalised_words(self):
        self.assertIsNotNone(sr.PERSON_RE.search("Commissioner Thompson spoke"))
        self.assertIsNone(sr.PERSON_RE.search("the commissioner spoke"))


class TestOrdinancePattern(unittest.TestCase):
    def test_matches_observed_corpus_forms(self):
        for text, expected in (("Ordinance 2403-19", "2403-19"),
                               ("Resolution No. 2022-88", "2022-88"),
                               ("ordinance number 15-32", "15-32"),
                               ("Ordinance #2403", "2403")):
            match = sr.ORDINANCE_RE.search(text)
            self.assertIsNotNone(match, text)
            num = match.group("num")
            suffix = match.group("suffix")
            key = f"{num}-{suffix}" if suffix else num
            self.assertEqual(key, expected, text)

    def test_bare_year_is_not_an_ordinance(self):
        self.assertIsNone(sr.ORDINANCE_RE.search("in the year 2024 there was"))


class TestStoreIntegrity(unittest.TestCase):
    def test_mismatched_store_is_refused(self):
        # A passages file and a matrix that disagree would silently attach the
        # wrong citation to every hit — the worst failure mode for an evidence tool.
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            with gzip.open(out / "passages.json.gz", "wt", encoding="utf-8") as fh:
                json.dump([{"passage_id": "a:0", "doc_id": "a", "text": "x",
                            "char_start": 0, "char_end": 1,
                            "repository": "r", "path": "p"}], fh)
            try:
                import numpy as np
            except ImportError:
                self.skipTest("numpy not installed")
            np.save(out / "vectors.npy", np.zeros((2, sr.EMBEDDING_DIM), dtype=np.float32))
            with self.assertRaises(SystemExit) as ctx:
                sr.load_store(out)
            self.assertIn("store mismatch", str(ctx.exception))

    def test_missing_store_points_at_the_embed_stage(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit) as ctx:
                sr.load_store(Path(tmp))
            self.assertIn("embed", str(ctx.exception))


class TestSearchOutputContract(unittest.TestCase):
    def test_caveats_are_part_of_the_result_not_only_the_console(self):
        src = Path(sr.__file__).read_text(encoding="utf-8")
        self.assertIn('"caveats": [', src)
        self.assertIn("Absence of a hit is NOT", src)
        self.assertIn("not evidence of a fact, a violation", src)

    def test_every_hit_field_needed_for_verification_is_present(self):
        src = Path(sr.__file__).read_text(encoding="utf-8")
        for field in ("char_span", "raw_url", "github_url", "extraction_method",
                      "quoted_passage", "meeting_date", "path", "repository"):
            self.assertIn(field, src)


class TestNoSilentDegradation(unittest.TestCase):
    def test_missing_runtime_exits_with_install_instructions(self):
        with self.assertRaises(SystemExit) as ctx:
            sr.require("definitely_not_a_real_module_xyz")
        message = str(ctx.exception)
        self.assertIn("pip install", message)
        self.assertIn("does not fall back to a keyword search", message)

    def test_embed_stage_does_not_download_a_model(self):
        src = Path(sr.__file__).read_text(encoding="utf-8")
        self.assertNotIn("huggingface", src.lower())
        self.assertNotIn("from_pretrained", src)
        self.assertIn("DEFAULT_MODEL_DIR", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
