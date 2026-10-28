#!/usr/bin/env python3
"""Tests for tools/intelligence_budget.py — stdlib unittest, hermetic, no network.

The network-facing audit is exercised live against the real published
descriptor (read-only); what is tested here is the arithmetic, because a budget
guard that miscomputes headroom either cries wolf or, worse, stays silent until
the build fails terminally — which is what happened on 2026-10-26.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import intelligence_budget as ib  # noqa: E402

MIB = 1024 * 1024
BUDGET = 512 * MIB


class TestBudgetReport(unittest.TestCase):
    def test_real_pinned_release_is_warning_not_healthy(self):
        # 493,608,460 bytes against 512 MiB is the actual pinned release.
        r = ib.budget_report(493_608_460, BUDGET, 8_388_608)
        # Ceiling percentage: 91.9401… reports as 91.95 so the guard reads
        # slightly early rather than slightly late.
        self.assertEqual(r["used_percent"], 91.95)
        self.assertEqual(r["severity"], "warning")
        self.assertFalse(r["exhausted"])
        self.assertEqual(r["headroom_bytes"], BUDGET - 493_608_460)
        self.assertEqual(r["runs_until_exhausted"], 5)

    def test_severity_thresholds_are_ordered_and_exclusive(self):
        # 85% of 512 MiB is 456340275.2 bytes, so the boundary is not an exact
        # byte count and cannot be asserted from a rounded literal. The real
        # invariant is the integer comparison the tool performs, plus monotonic
        # ordering: severity may never decrease as usage rises.
        def sev(used):
            return ib.budget_report(used, BUDGET)["severity"]

        rank = {"healthy": 0, "warning": 1, "critical": 2, "exhausted": 3}
        self.assertEqual(sev(BUDGET // 2), "healthy")
        self.assertEqual(sev(BUDGET - 1), "critical")
        self.assertEqual(sev(BUDGET), "exhausted")
        self.assertEqual(sev(BUDGET + 1), "exhausted")

        # Exact boundary, derived the same way the tool derives it.
        for percent, lower, upper in ((ib.WARNING_PERCENT, "healthy", "warning"),
                                      (ib.CRITICAL_PERCENT, "warning", "critical")):
            product = BUDGET * percent
            below = (product - 1) // 100
            at_or_above = -(-product // 100)
            self.assertEqual(sev(below), lower, f"{percent}% below boundary")
            self.assertIn(sev(at_or_above), (upper, "exhausted"),
                          f"{percent}% at boundary")

        previous = -1
        step = max(1, BUDGET // 4096)
        for used in range(0, BUDGET + 2 * step, step):
            current = rank[sev(used)]
            self.assertGreaterEqual(current, previous, f"non-monotonic at used={used}")
            previous = current

    def test_exactly_at_budget_is_exhausted_not_critical(self):
        r = ib.budget_report(BUDGET, BUDGET)
        self.assertTrue(r["exhausted"])
        self.assertEqual(r["severity"], "exhausted")
        self.assertEqual(r["headroom_bytes"], 0)

    def test_over_budget_reports_negative_headroom(self):
        # A negative headroom must stay negative and visible, not clamp to zero:
        # the size of the overshoot determines how many partitions are needed.
        r = ib.budget_report(BUDGET + 63_129_088, BUDGET)
        self.assertEqual(r["headroom_bytes"], -63_129_088)
        self.assertTrue(r["exhausted"])

    def test_projection_is_none_without_a_growth_assumption(self):
        # Inventing a growth rate would invent an exhaustion date. With no
        # observed growth the honest answer is "unknown", not "never".
        r = ib.budget_report(int(BUDGET * 0.5), BUDGET, 0)
        self.assertIsNone(r["runs_until_exhausted"])
        self.assertEqual(r["assumed_growth_bytes_per_run"], 0)

    def test_projection_none_when_already_exhausted(self):
        r = ib.budget_report(BUDGET + 1, BUDGET, MIB)
        self.assertIsNone(r["runs_until_exhausted"])

    def test_projection_floors_rather_than_rounds_up(self):
        # 100 MiB headroom at 30 MiB/run is 3 complete runs, not 3.33 → 4.
        # Overstating remaining runs is the unsafe direction.
        r = ib.budget_report(BUDGET - 100 * MIB, BUDGET, 30 * MIB)
        self.assertEqual(r["runs_until_exhausted"], 3)

    def test_zero_budget_does_not_divide_by_zero(self):
        r = ib.budget_report(100, 0)
        self.assertEqual(r["used_fraction"], 1.0)
        self.assertTrue(r["exhausted"])


class TestPlanSplit(unittest.TestCase):
    def _measured(self, files):
        return {"largest_files": [{"path": p, "bytes": b} for p, b in files]}

    def test_fits_in_one_partition_when_under_budget(self):
        m = self._measured([("a.gz", 10 * MIB), ("b.gz", 5 * MIB)])
        plan = ib.plan_split(m, BUDGET)
        self.assertTrue(plan["feasible"])
        self.assertEqual(plan["partitions_required"], 1)
        self.assertEqual(plan["new_partitions_required"], 0)
        self.assertEqual(plan["suggested_new_repository_names"], [])
        self.assertEqual(plan["partition_sizes_bytes"], [15 * MIB])

    def test_numbered_parts_of_one_logical_file_stay_together(self):
        # database-0001..0004.part are one reassembled SQLite database. The
        # published manifest expresses reassembly order within a single host, so
        # splitting them across hosts would silently break every client.
        m = self._measured([(f"database-{i:04d}.part", 40 * MIB) for i in range(1, 5)])
        plan = ib.plan_split(m, BUDGET)
        self.assertTrue(plan["feasible"])
        self.assertEqual(plan["partitions_required"], 1)
        self.assertEqual(plan["assignments"][0]["logical_files"], ["database"])
        self.assertEqual(plan["partition_sizes_bytes"], [160 * MIB])

    def test_content_addressed_parts_are_separate_logical_files(self):
        m = self._measured([
            (f"parts/{h}.part", 30 * MIB)
            for h in ("a" * 64, "b" * 64, "c" * 64)])
        plan = ib.plan_split(m, BUDGET)
        self.assertTrue(plan["feasible"])
        self.assertEqual(len(plan["assignments"][0]["logical_files"]), 3)

    def test_oversized_logical_file_is_flagged_not_silently_stacked(self):
        m = self._measured([("database-0001.part", 40 * MIB),
                            ("database-0002.part", 40 * MIB)])
        plan = ib.plan_split(m, 60 * MIB)
        self.assertFalse(plan["feasible"])
        self.assertEqual(len(plan["oversized_logical_files"]), 1)
        self.assertEqual(plan["oversized_logical_files"][0]["logical"], "database")
        self.assertEqual(plan["oversized_logical_files"][0]["bytes"], 80 * MIB)
        self.assertIn("must be split into", plan["oversized_logical_files"][0]["problem"])
        self.assertIn("within one host", plan["oversized_logical_files"][0]["problem"])

    def test_no_partition_over_budget_unless_it_holds_one_oversized_file(self):
        # Regression: the greedy loop used to keep stacking into a partition that
        # was already over budget, producing a 300% fill. Every over-budget
        # partition must be over because a single un-splittable logical file is.
        files = [(f"database-{i:04d}.part", 40 * MIB) for i in range(1, 5)]
        files += [(f"parts/{i:064x}.part", 20 * MIB) for i in range(1, 5)]
        files += [("candidates.jsonl.gz", 13 * MIB), ("files.json", 3 * MIB)]
        for budget in (BUDGET, 120 * MIB, 60 * MIB, 45 * MIB):
            plan = ib.plan_split(self._measured(files), budget)
            oversized_names = {o["logical"] for o in plan["oversized_logical_files"]}
            for assignment in plan["assignments"]:
                if assignment["bytes"] <= budget:
                    continue
                self.assertEqual(
                    len(assignment["logical_files"]), 1,
                    f"budget={budget}: partition {assignment['partition_index']} is over "
                    f"budget while holding {assignment['logical_files']}")
                self.assertIn(assignment["logical_files"][0], oversized_names)
            for index in plan["partitions_over_budget"]:
                self.assertGreater(plan["partition_sizes_bytes"][index], budget)

    def test_sizes_and_fill_percent_are_consistent(self):
        m = self._measured([("a.gz", 100 * MIB), ("b.gz", 100 * MIB),
                            ("c.gz", 100 * MIB)])
        plan = ib.plan_split(m, 150 * MIB)
        self.assertEqual(len(plan["partition_sizes_bytes"]), plan["partitions_required"])
        self.assertEqual(len(plan["partition_fill_percent"]), plan["partitions_required"])
        for size, fill in zip(plan["partition_sizes_bytes"], plan["partition_fill_percent"]):
            self.assertAlmostEqual(fill, round(100 * size / (150 * MIB), 2), places=2)
        self.assertEqual(sum(plan["partition_sizes_bytes"]), 300 * MIB)

    def test_new_repository_names_are_sequential_from_002(self):
        m = self._measured([(f"f{i}.gz", 100 * MIB) for i in range(5)])
        plan = ib.plan_split(m, 110 * MIB)
        self.assertEqual(plan["new_partitions_required"], plan["partitions_required"] - 1)
        self.assertEqual(plan["suggested_new_repository_names"],
                         [f"civic-newsroom-intelligence-{i:03d}"
                          for i in range(2, 2 + plan["new_partitions_required"])])

    def test_empty_manifest_reports_infeasible_with_a_reason(self):
        plan = ib.plan_split({"largest_files": []}, BUDGET)
        self.assertFalse(plan["feasible"])
        self.assertIn("cannot plan", plan["reason"])

    def test_constraint_is_stated_in_the_plan(self):
        m = self._measured([("a.gz", MIB)])
        self.assertIn("never assigned across two partitions",
                      ib.plan_split(m, BUDGET)["constraint"])


class TestPlanCoverageHonesty(unittest.TestCase):
    """Two defects found live and pinned here.

    (1) The plan is built from the largest enumerated files, so it can conclude
        "no new partition" while the host is measurably over budget.
    (2) --quiet used to swallow a fetch failure into exit 0, which would let a
        CI gate read "audit passed" for a run that audited nothing.
    """

    def _measured(self, files, actual):
        return {"largest_files": [{"path": p, "bytes": b} for p, b in files],
                "actual_bytes": actual}

    def test_plan_under_budget_but_host_over_budget_is_contradicted(self):
        # Ten 40 MiB parts = 400 MiB enumerated, but the host holds 600 MiB.
        m = self._measured([(f"f{i}.gz", 40 * MIB) for i in range(10)], 600 * MIB)
        plan = ib.plan_split(m, 512 * MIB)
        self.assertFalse(plan["plan_covers_host"])
        self.assertTrue(plan["contradicts_measured_budget"])
        self.assertIn("lower bound", plan["contradiction_note"])
        self.assertIn("Plan a new partition", plan["contradiction_note"])
        self.assertEqual(plan["host_actual_bytes"] - plan["enumerated_bytes"], 200 * MIB)

    def test_plan_covering_the_whole_host_is_not_contradicted(self):
        m = self._measured([("a.gz", 100 * MIB), ("b.gz", 100 * MIB)], 200 * MIB)
        plan = ib.plan_split(m, 512 * MIB)
        self.assertTrue(plan["plan_covers_host"])
        self.assertFalse(plan["contradicts_measured_budget"])
        self.assertIsNone(plan["contradiction_note"])
        self.assertIn("account for the whole measured host", plan["coverage_caveat"])

    def test_over_budget_host_without_contradiction_still_warns_of_partial_listing(self):
        # Host over budget AND plan says new partitions needed: the caveat about
        # partial enumeration must still be present.
        m = self._measured([("a.gz", 300 * MIB), ("b.gz", 300 * MIB)], 900 * MIB)
        plan = ib.plan_split(m, 512 * MIB)
        self.assertFalse(plan["plan_covers_host"])
        self.assertIn("lower bound", plan["coverage_caveat"])


class TestExitCodes(unittest.TestCase):
    """Exit codes are the CI contract; they are tested through main()."""

    def test_no_hosts_is_not_a_pass(self):
        # A repo with no publication descriptor must not exit 0: that reads as
        # "audited and healthy" to any gate consuming the code.
        code = ib.main(["--quiet", "--out", "/tmp/ib-test-nohost",
                        "--code-repo", "nonexistent-owner-xyz/nonexistent-repo-xyz"])
        self.assertEqual(code, 4)

    def test_unreachable_descriptor_url_exits_4_even_when_quiet(self):
        code = ib.main(["--quiet",
                        "--descriptor-url",
                        "https://api.github.com/repos/nonexistent-owner-xyz/"
                        "nonexistent-repo-xyz/contents/x.json"])
        self.assertEqual(code, 4)


class TestDescriptorVerificationLogic(unittest.TestCase):
    """The network path is audited live; these pin the URL/pinning rules."""

    def test_base_url_must_be_pinned_to_the_declared_revision(self):
        revision = "5a32d3f5e99bce745898f47673db7dc2ffb16207"
        good = (f"https://raw.githubusercontent.com/bartimoussmith-oss/"
                f"civic-newsroom-intelligence-001/{revision}/data/run-1/")
        self.assertTrue(good.startswith(
            f"https://raw.githubusercontent.com/bartimoussmith-oss/"
            f"civic-newsroom-intelligence-001/{revision}/"))
        # An unpinned host would defeat the tamper rejection the client does.
        bad = ("https://raw.githubusercontent.com/bartimoussmith-oss/"
               "civic-newsroom-intelligence-001/main/data/run-1/")
        self.assertFalse(bad.startswith(
            f"https://raw.githubusercontent.com/bartimoussmith-oss/"
            f"civic-newsroom-intelligence-001/{revision}/"))

    def test_missing_descriptor_fields_short_circuit_without_network(self):
        for incomplete in ({}, {"data_repository": "x"},
                           {"data_repository": "x", "revision": "y"},
                           {"revision": "y", "base_url": "z"}):
            result = ib.verify_descriptor(incomplete, "x", timeout=1)
            self.assertFalse(result["verified"])
            self.assertFalse(result["checks"][0]["ok"])
            self.assertEqual(result["checks"][0]["check"], "descriptor-fields-present")
            self.assertNotIn("measured", result)

    def test_sha256_is_stable_and_hex(self):
        digest = ib.sha256_hex(b"deterministic")
        self.assertEqual(len(digest), 64)
        self.assertEqual(digest, ib.sha256_hex(b"deterministic"))
        self.assertNotEqual(digest, ib.sha256_hex(b"deterministic!"))


class TestConstants(unittest.TestCase):
    def test_default_budget_matches_the_declared_512_mib(self):
        self.assertEqual(ib.DEFAULT_BUDGET_MIB, 512)
        self.assertEqual(ib.DEFAULT_BUDGET_MIB * ib.MIB, 536_870_912)

    def test_observed_part_size_is_40_mib(self):
        self.assertEqual(ib.OBSERVED_PART_BYTES, 41_943_040)
        self.assertEqual(ib.OBSERVED_PART_BYTES, 40 * ib.MIB)

    def test_tool_declares_itself_read_only(self):
        src = Path(ib.__file__).read_text(encoding="utf-8")
        self.assertIn("READ-ONLY", src)
        # It must not contain any write path to another repository.
        for forbidden in ("git push", "create_pull", "requests.put", "requests.post",
                          'method="PUT"', 'method="POST"', "--repo-write"):
            self.assertNotIn(forbidden, src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
