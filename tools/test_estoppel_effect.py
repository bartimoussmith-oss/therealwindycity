"""Standard-library tests for the additive estoppel-effect research aid."""
from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

try:
    from . import estoppel_effect as effect
except ImportError:  # python tools/test_estoppel_effect.py
    import estoppel_effect as effect


class EstoppelEffectTests(unittest.TestCase):
    def make_event(
        self,
        event_id: str,
        date: str,
        role: str,
        source_type: str,
        text: str,
        tactics: list[str] | None = None,
        *,
        video_id: str | None = None,
        t0: float | None = None,
        t1: float | None = None,
    ) -> dict:
        return {
            "event_id": event_id,
            "date": date,
            "date_source": "test-fixture",
            "title": "City Council test meeting",
            "body": "city-council",
            "source_role": role,
            "source_type": source_type,
            "speaker_attribution": "test attribution label; not verified",
            "tactic_candidates": tactics or [],
            "diagnostic_markers": [],
            "evidence_excerpt": text,
            "source": {
                "source_id": f"source-{event_id}",
                "source_url": f"https://example.invalid/{event_id}",
                "video_id": video_id,
                "t0": t0,
                "t1": t1,
            },
        }

    def test_signal_event_retains_offsets_hash_and_uncertainty(self) -> None:
        text = (
            "The speaker says no vote is being requested. I am making a formal "
            "constructive notice for the permanent administrative record; "
            "please correct the water-rate schedule citation."
        )
        source_hash = effect.sha256_text(text)
        record = {
            "source_id": "cue-1",
            "source_text_sha256": source_hash,
            "date": "2026-01-12",
            "title": "City Council",
            "body": "city-council",
            "source_type": "caption_aligned_intervention_index",
            "source_role": "miller_intervention",
            "speaker_attribution": "compilation label only",
            "text": text,
        }

        hits = effect.find_signal_hits(text)
        notice_hits = [hit for hit in hits if hit["tag"] == "notice_opportunity_to_cure"]
        self.assertTrue(notice_hits)
        self.assertTrue(all(text[hit["start_char"]:hit["end_char"]] == hit["matched_text"] for hit in hits))

        events = effect.extract_events([record])
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertIn("notice_opportunity_to_cure", event["tactic_candidates"])
        self.assertTrue(event["local_negation_marker_present"])
        self.assertEqual(event["source_text_sha256"], source_hash)
        self.assertEqual(event["speaker_attribution"], "compilation label only")
        self.assertEqual(event["source"]["source_id"], "cue-1")
        self.assertIn("formal constructive notice", event["evidence_excerpt"])
        self.assertEqual(event["legal_effect"], "not assessed")

    def test_overlapping_alignment_variants_are_not_independent_records(self) -> None:
        rows = [
            {
                "video": "video-1", "block": "turn", "dup_group": 9, "dup_rank": 0,
                "score": 0.90, "dur": 100, "truncated_align": False,
                "date": "2026-01-12", "mkind": "City Council", "title": "Council",
                "t0": 10, "t1": 110, "n": 1, "text": "Lower-score complete cue.",
            },
            {
                "video": "video-1", "block": "turn", "dup_group": 9, "dup_rank": 1,
                "score": 0.95, "dur": 80, "truncated_align": False,
                "date": "2026-01-12", "mkind": "City Council", "title": "Council",
                "t0": 20, "t1": 100, "n": 2, "text": "Higher-score selected cue with formal constructive notice.",
            },
            {
                "video": "video-1", "block": "turn", "dup_group": 9, "dup_rank": 2,
                "score": 1.0, "dur": 140, "truncated_align": True,
                "date": "2026-01-12", "mkind": "City Council", "title": "Council",
                "t0": 0, "t1": 140, "n": 3, "text": "Truncated alternative.",
            },
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "interventions.json"
            path.write_text(json.dumps(rows), encoding="utf-8")
            records, stats = effect.load_intervention_records(path)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["source_role"], "miller_intervention")
        self.assertEqual(records[0]["alignment_score"], 0.95)
        self.assertEqual(records[0]["t0"], 20.0)
        self.assertEqual(records[0]["duplicate_variant_count"], 2)
        self.assertEqual(stats["alignment_alternates_not_counted_as_independent"], 2)
        self.assertEqual(stats["selected_miller_interventions"], 1)
        self.assertEqual(sum(v["selected"] for v in records[0]["duplicate_variants"]), 1)

    def test_issue_token_filter_suppresses_common_procedural_cues(self) -> None:
        tokens = effect._issue_tokens(
            "Jennifer says for the permanent administrative record: health, safety, "
            "welfare; water rates affect the west industrial corridor."
        )
        for boilerplate in ("jennifer", "administrative", "record", "health", "safety", "welfare"):
            self.assertNotIn(boilerplate, tokens)
        self.assertTrue({"water", "rates", "industrial", "corridor"}.issubset(tokens))

    def test_cross_meeting_candidates_need_tactic_signals_on_both_sides(self) -> None:
        older = self.make_event(
            "older", "2026-02-01", "miller_intervention",
            "caption_aligned_intervention_index",
            "Bluebird water sewer rates affect the north pump station and downstream flow schedule.",
            ["assurance_to_instrument"],
        )
        later = self.make_event(
            "later", "2026-03-01", "unattributed_meeting_context",
            "caption_transcript_database",
            "At the last meeting, Bluebird water sewer rates affect the north pump station and downstream flow schedule.",
            ["cross_meeting_chronology"],
        )

        pairs = effect.rank_comparison_candidates([older, later])
        self.assertEqual(len(pairs), 1)
        pair = pairs[0]
        self.assertEqual(pair["relation_kind"], "cross_meeting_chronology_candidate")
        self.assertEqual(pair["earlier_event_id"], "older")
        self.assertEqual(pair["later_event_id"], "later")
        self.assertTrue(pair["later_explicit_chronology_marker"])
        self.assertEqual(pair["miller_anchor_event_ids"], ["older"])
        self.assertFalse(pair["rank_score_is_probability_or_confidence"])
        self.assertIn("tactic-pattern candidates on both sides", pair["candidate_basis"])
        self.assertEqual(pair["review"]["legal_effect"], "not assessed")

        action_only = self.make_event(
            "action-only", "2026-03-01", "unattributed_meeting_context",
            "caption_transcript_database",
            "At the last meeting, Bluebird water sewer rates affect the north pump station and downstream flow schedule.",
            [],
        )
        self.assertEqual(effect.rank_comparison_candidates([older, action_only]), [])

    def test_same_meeting_source_crosscheck_has_no_temporal_order(self) -> None:
        cue = self.make_event(
            "cue", "2026-04-01", "miller_intervention",
            "caption_aligned_intervention_index",
            "Cobalt water meter replacement schedule serves the east reservoir and pressure district.",
            ["predecision_evidence_gap"],
            video_id="video-2", t0=10, t1=30,
        )
        meeting = self.make_event(
            "meeting", "2026-04-01", "unattributed_meeting_context",
            "caption_transcript_database",
            "Cobalt water meter replacement schedule serves the east reservoir and pressure district.",
        )

        pairs = effect.rank_comparison_candidates([cue, meeting])
        self.assertEqual(len(pairs), 1)
        pair = pairs[0]
        self.assertEqual(pair["relation_kind"], "same_meeting_source_crosscheck")
        self.assertEqual(pair["record_a_event_id"], "cue")
        self.assertEqual(pair["record_b_event_id"], "meeting")
        self.assertFalse(pair["chronological_order_available"])
        self.assertIsNone(pair["earlier_event_id"])
        self.assertIsNone(pair["later_event_id"])
        self.assertIn("not established", pair["same_meeting_source_crosscheck_is_independent_corroboration"])

    def test_same_meeting_sequence_requires_context_after_cue(self) -> None:
        cue = self.make_event(
            "cue", "2026-04-01", "miller_intervention",
            "caption_aligned_intervention_index",
            "Cobalt water meter replacement schedule serves the east reservoir and pressure district.",
            ["predecision_evidence_gap"],
            video_id="video-3", t0=10, t1=30,
        )
        later_context = self.make_event(
            "later-context", "2026-04-01", "meeting_context_cue",
            "caption_aligned_intervention_index",
            "Cobalt water meter replacement schedule serves the east reservoir and pressure district.",
            video_id="video-3", t0=35, t1=50,
        )
        pairs = effect.rank_comparison_candidates([cue, later_context])
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0]["relation_kind"], "same_meeting_sequence_candidate")
        self.assertEqual(pairs[0]["earlier_event_id"], "cue")
        self.assertEqual(pairs[0]["later_event_id"], "later-context")
        self.assertEqual(pairs[0]["same_meeting_sequence_gap_seconds"], 5.0)

        earlier_context = self.make_event(
            "earlier-context", "2026-04-01", "meeting_context_cue",
            "caption_aligned_intervention_index",
            "Cobalt water meter replacement schedule serves the east reservoir and pressure district.",
            video_id="video-3", t0=1, t1=9,
        )
        self.assertEqual(effect.rank_comparison_candidates([cue, earlier_context]), [])

        no_video_cue = self.make_event(
            "no-video-cue", "2026-04-01", "miller_intervention",
            "caption_aligned_intervention_index",
            "Cobalt water meter replacement schedule serves the east reservoir and pressure district.",
            ["predecision_evidence_gap"], t0=10, t1=30,
        )
        no_video_context = self.make_event(
            "no-video-context", "2026-04-01", "meeting_context_cue",
            "caption_aligned_intervention_index",
            "Cobalt water meter replacement schedule serves the east reservoir and pressure district.",
            t0=35, t1=50,
        )
        self.assertEqual(effect.rank_comparison_candidates([no_video_cue, no_video_context]), [])

    def test_review_csv_is_written_with_explicit_human_review_fields(self) -> None:
        cue = self.make_event(
            "cue", "2026-04-01", "miller_intervention",
            "caption_aligned_intervention_index",
            "Cobalt water meter replacement schedule serves the east reservoir and pressure district.",
            ["predecision_evidence_gap"],
        )
        meeting = self.make_event(
            "meeting", "2026-04-01", "unattributed_meeting_context",
            "caption_transcript_database",
            "Cobalt water meter replacement schedule serves the east reservoir and pressure district.",
        )
        pairs = effect.rank_comparison_candidates([cue, meeting])
        report = {"events": [cue, meeting], "comparison_candidates": pairs}

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "review.csv"
            effect.write_review_csv(report, path)
            with path.open(encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.DictReader(stream))

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["relation_kind"], "same_meeting_source_crosscheck")
        self.assertEqual(rows[0]["review_status"], "unreviewed")
        self.assertEqual(rows[0]["legal_effect"], "not assessed")
        self.assertIn("Cobalt water", rows[0]["record_a_excerpt"])


if __name__ == "__main__":
    unittest.main()
