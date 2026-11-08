"""Offline tests for wy_channel_harvest.py (fake API, no network, no key needed).

Run:  python3 -m unittest youtube-channels/test_wy_channel_harvest.py -v
"""
import csv
import json
import tempfile
import unittest
from pathlib import Path

import wy_channel_harvest as h


def fake_api(endpoint, key, **p):
    """Stand-in for the YouTube API with two channels and a two-page uploads list."""
    if endpoint == "search":
        q = p["q"]
        if q.startswith("Cheyenne City Council"):
            return {"items": [
                {"id": {"channelId": "UC_CHEY"}, "snippet": {"channelTitle": "City of Cheyenne Council"}},
                {"id": {"channelId": "UC_OTHER"}, "snippet": {"channelTitle": "Random Vlogger"}},
            ]}
        return {"items": []}  # nothing found for everything else
    if endpoint == "channels":
        if p["id"] == "UC_CHEY":
            return {"items": [{"snippet": {"customUrl": "@CheyenneCouncil"},
                               "contentDetails": {"relatedPlaylists": {"uploads": "UU_CHEY"}},
                               "statistics": {"videoCount": "3"}}]}
        return {"items": []}
    if endpoint == "playlistItems":
        if p.get("pageToken") == "P2":
            return {"items": [{"contentDetails": {"videoId": "v3", "videoPublishedAt": "2026-03-01T10:00:00Z"},
                               "snippet": {"title": "Meeting 3"}}]}
        return {"items": [
            {"contentDetails": {"videoId": "v1", "videoPublishedAt": "2026-01-02T10:00:00Z"},
             "snippet": {"title": "Meeting 1"}},
            {"contentDetails": {"videoId": "v2", "videoPublishedAt": "2026-02-02T10:00:00Z"},
             "snippet": {"title": "Meeting 2"}},
        ], "nextPageToken": "P2"}
    raise AssertionError(endpoint)


class HarvestTests(unittest.TestCase):
    def test_targets_count(self):
        self.assertEqual(len(h.CORE_ENTITIES), 13)
        self.assertEqual(len(h.WY_TOWNS), 93)  # as pasted; repo registry lists 99
        self.assertEqual(len(h.build_targets()), 106)
        self.assertEqual(len(h.build_targets(core_only=True)), 13)

    def test_match_score(self):
        self.assertEqual(h.match_score("Cheyenne City Council", "City of Cheyenne Council"), 1.0)
        self.assertEqual(h.match_score("Cheyenne City Council", "Random Vlogger"), 0.0)
        self.assertEqual(h.match_score("Afton Wyoming", "Afton Wyoming"), 1.0)

    def test_full_pipeline_and_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            targets = [("Cheyenne City Council", "Cheyenne City Council", "core"),
                       ("Afton", "Afton Wyoming", "town")]
            self.assertTrue(h.run(out, "KEY", targets, call=fake_api, sleep=0))

            with (out / "videos.csv").open(encoding="utf-8") as fh:
                videos = list(csv.DictReader(fh))
            self.assertEqual([v["video_id"] for v in videos], ["v1", "v2", "v3"])
            self.assertEqual(videos[0]["url"], "https://www.youtube.com/watch?v=v1")
            self.assertEqual(videos[0]["published"], "2026-01-02")

            with (out / "channels.csv").open(encoding="utf-8") as fh:
                rows = {r["entity"]: r for r in csv.DictReader(fh)}
            self.assertEqual(rows["Cheyenne City Council"]["status"], "found")
            self.assertEqual(rows["Cheyenne City Council"]["channel_url"],
                             "https://www.youtube.com/@CheyenneCouncil")
            self.assertEqual(rows["Cheyenne City Council"]["videos_listed"], "3")
            self.assertEqual(rows["Afton"]["status"], "no channel found")
            self.assertEqual(rows["Afton"]["needs_review"], "yes")

            with (out / "channel_candidates.csv").open(encoding="utf-8") as fh:
                cands = list(csv.DictReader(fh))
            self.assertEqual(len(cands), 2)  # both search hits kept for review

    def test_resume_skips_finished_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            targets = [("Cheyenne City Council", "Cheyenne City Council", "core")]
            h.run(out, "KEY", targets, call=fake_api, sleep=0)

            calls = []

            def counting(endpoint, key, **p):
                calls.append(endpoint)
                return fake_api(endpoint, key, **p)

            h.run(out, "KEY", targets, call=counting, sleep=0)
            self.assertEqual(calls, [])  # nothing re-requested on resume

    def test_quota_stops_cleanly_and_saves(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            targets = [("Cheyenne City Council", "Cheyenne City Council", "core"),
                       ("Afton", "Afton Wyoming", "town")]

            def quota(endpoint, key, **p):
                raise h.QuotaExceeded("quotaExceeded")

            self.assertFalse(h.run(out, "KEY", targets, call=quota, sleep=0))
            self.assertTrue((out / "channels.csv").exists())
            self.assertTrue((out / "cache.json").exists())
            json.loads((out / "cache.json").read_text())  # valid JSON


if __name__ == "__main__":
    unittest.main()
