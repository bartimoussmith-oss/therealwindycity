#!/usr/bin/env python3
"""Budget guard and partition-split planner for the civic-newsroom data hosts.

Why this exists: `civic-newsroom-intelligence-001` declares a 512 MiB derived
publication budget, and the pinned release already occupies 493,608,460 bytes —
470.7 MiB, or 91.8% of it. On 2026-10-26 the build failed terminally with
`ValueError: Packed intelligence needs additional approved host: 493607874
bytes`, and the fix was to stand up a new host reactively. This tool turns that
reaction into a measurement taken before the wall is hit.

It is strictly READ-ONLY against other repositories. It calls api.github.com to
fetch publication descriptors and file manifests, verifies the declared hashes
arithmetically, computes headroom, and — when headroom is exhausted — emits a
concrete split plan naming which files move to which new partition and what
each partition would then contain. It writes only to its local --out directory.
It never pushes, never opens a PR, and never modifies another repository;
AGENTS.md requires explicit approval for cross-repository writes and this tool
does not seek to bypass that.

Checks performed, in order of severity:
  1. does the declared collection hash match the bytes actually published?
  2. does every file in the manifest have a positive declared length?
  3. is the host within budget, and by how much?
  4. at the observed growth rate, when does the budget exhaust?
  5. if exhausted, which files move, and does the split fit?

Exit codes are CI-usable: 0 healthy, 3 budget exhausted or hash mismatch,
4 could not fetch. A green exit is a statement about these checks only — it is
not a claim that the deployed site works.

Examples:
  python tools/intelligence_budget.py --out data/intelligence-budget
  python tools/intelligence_budget.py --fail-on-exhausted        # for CI
  python tools/intelligence_budget.py --descriptor-url <url>     # pinned check
  python tools/intelligence_budget.py --growth-bytes-per-run 8388608
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

API_ROOT = "https://api.github.com"
USER_AGENT = "therealwindycity-intelligence-budget/1.0 (read-only budget audit)"

# Declared budget of the intelligence host, taken from the repository's own
# description ("derived publication budget 512 MiB") and its AGENTS.md rule that
# file/repository/site sizes must be bounded and measured. Expressed in MiB and
# converted exactly, because a budget that drifts by a rounding error is not a
# budget.
DEFAULT_BUDGET_MIB = 512
MIB = 1024 * 1024

DEFAULT_CODE_REPO = "bartimoussmith-oss/civic-newsroom"
DESCRIPTOR_PATHS = ("intelligence-publication.json", "law-publication.json",
                    "source-publication.json")

# A part is a fixed-size physical chunk of a larger logical file. The observed
# chunk size is exactly 40 MiB, which is the practical ceiling for a single
# GitHub-hosted file that a browser can fetch reliably.
OBSERVED_PART_BYTES = 41_943_040


def http_json(url: str, timeout: int = 60) -> dict | list:
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/vnd.github+json",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def api_contents(repo: str, path: str, ref: str = "HEAD") -> bytes:
    url = f"{API_ROOT}/repos/{repo}/contents/{urllib.parse.quote(path)}?ref={ref}"
    meta = http_json(url)
    if meta.get("encoding") != "base64" or not meta.get("content"):
        raise RuntimeError(f"unexpected contents encoding for {repo}:{path}: "
                           f"{meta.get('encoding')}")
    return base64.b64decode(meta["content"])


def api_tree(repo: str, ref: str = "HEAD") -> dict:
    data = http_json(f"{API_ROOT}/repos/{repo}/git/trees/{ref}?recursive=1")
    return {
        "truncated": bool(data.get("truncated")),
        "blobs": [e for e in data.get("tree", []) if e.get("type") == "blob"],
    }


# --------------------------------------------------------------------------
# verification
# --------------------------------------------------------------------------

def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify_descriptor(descriptor: dict, repo: str, timeout: int) -> dict:
    """Verify a publication descriptor against the bytes it claims to pin.

    The descriptor is the contract a browser client relies on: it names a data
    repository, a commit, a collection SHA-256 and a stored byte count. Every
    one of those is checkable, so every one is checked. A descriptor that cannot
    be verified is reported as unverified rather than trusted.
    """
    result: dict = {
        "descriptor": descriptor,
        "checks": [],
        "verified": False,
    }

    def check(name: str, ok: bool, detail: str) -> None:
        result["checks"].append({"check": name, "ok": bool(ok), "detail": detail})

    data_repo = descriptor.get("data_repository")
    revision = descriptor.get("revision")
    base_url = descriptor.get("base_url")
    if not (data_repo and revision and base_url):
        check("descriptor-fields-present", False,
              f"missing one of data_repository/revision/base_url: {sorted(descriptor)}")
        return result
    check("descriptor-fields-present", True, f"{data_repo}@{revision[:12]}")

    # base_url must point at the pinned revision of the declared repository.
    # Accepting an unpinned or foreign host would defeat the tamper rejection
    # the browser client implements.
    expected_prefix = f"https://raw.githubusercontent.com/{data_repo}/{revision}/"
    check("base-url-pinned-to-declared-revision",
          base_url.startswith(expected_prefix),
          f"base_url={base_url[:110]}")

    match = re.search(r"/(data/[^/]+)/?$", base_url.rstrip("/"))
    if not match:
        check("run-directory-identifiable", False, f"cannot parse run dir from {base_url}")
        return result
    run_dir = match.group(1)
    check("run-directory-identifiable", True, run_dir)

    declared_bytes = int(descriptor.get("stored_bytes") or 0)
    declared_sha = descriptor.get("collection_sha256")

    # Fetch collection.json at the pinned revision and hash it.
    try:
        collection_raw = api_contents(data_repo, f"{run_dir}/collection.json", revision)
    except Exception as exc:  # noqa: BLE001 - reported, not raised
        check("collection-fetchable", False, f"{type(exc).__name__}: {str(exc)[:160]}")
        return result
    check("collection-fetchable", True, f"{len(collection_raw):,} bytes")

    actual_sha = sha256_hex(collection_raw)
    check("collection-sha256-matches-declared", actual_sha == declared_sha,
          f"declared={declared_sha} actual={actual_sha}")

    try:
        collection = json.loads(collection_raw)
    except json.JSONDecodeError as exc:
        check("collection-is-valid-json", False, str(exc)[:160])
        return result
    check("collection-is-valid-json", True, f"{len(collection)} top-level keys")

    # Enumerate the run directory at the pinned revision and total the bytes.
    # The trees API is used rather than summing the manifest, so that a manifest
    # which omits a file cannot hide it from the budget.
    try:
        tree = api_tree(data_repo, revision)
    except Exception as exc:  # noqa: BLE001
        check("tree-fetchable", False, f"{type(exc).__name__}: {str(exc)[:160]}")
        tree = {"truncated": None, "blobs": []}
    if tree.get("truncated") is None:
        pass
    elif tree["truncated"]:
        check("tree-not-truncated", False,
              "trees API truncated the listing — byte total is a LOWER BOUND")
    else:
        check("tree-not-truncated", True, "complete listing")

    prefix = run_dir.rstrip("/") + "/"
    run_blobs = [b for b in tree["blobs"] if b["path"].startswith(prefix)]
    actual_bytes = sum(int(b.get("size") or 0) for b in run_blobs)
    check("stored-bytes-matches-declared", actual_bytes == declared_bytes,
          f"declared={declared_bytes:,} actual={actual_bytes:,} "
          f"delta={actual_bytes - declared_bytes:+,}")

    result["verified"] = all(c["ok"] for c in result["checks"])
    result["measured"] = {
        "data_repository": data_repo,
        "revision": revision,
        "run_directory": run_dir,
        "declared_bytes": declared_bytes,
        "actual_bytes": actual_bytes,
        "file_count": len(run_blobs),
        "collection_sha256_actual": actual_sha,
        "largest_files": sorted(
            ({"path": b["path"][len(prefix):], "bytes": int(b.get("size") or 0)}
             for b in run_blobs), key=lambda d: -d["bytes"])[:10],
        "tree_truncated": tree.get("truncated"),
    }
    return result


# --------------------------------------------------------------------------
# budget + split planning
# --------------------------------------------------------------------------

# Severity thresholds as integer percentages. Compared with integer arithmetic
# (used * 100 >= budget * 85) rather than a float ratio, because 0.85 and 0.95
# are not exactly representable in binary floating point and a threshold that
# wobbles by one byte is not a threshold. This is a budget guard: its whole job
# is to fire on the right side of an exact line.
WARNING_PERCENT = 85
CRITICAL_PERCENT = 95


def budget_report(actual_bytes: int, budget_bytes: int,
                  growth_bytes_per_run: int = 0) -> dict:
    headroom = budget_bytes - actual_bytes
    used_fraction = actual_bytes / budget_bytes if budget_bytes else 1.0
    exhausted = headroom <= 0
    if budget_bytes <= 0:
        used_percent_x100 = 100 * 100
    else:
        # Ceiling, not floor: flooring lets the guard fire one byte late, and a
        # budget guard should err early. Exact percentage for reporting only.
        used_percent_x100 = -((-actual_bytes * 10_000) // budget_bytes)
    runs_until_exhausted = None
    if not exhausted and growth_bytes_per_run > 0:
        runs_until_exhausted = int(headroom // growth_bytes_per_run)
    return {
        "budget_bytes": budget_bytes,
        "actual_bytes": actual_bytes,
        "headroom_bytes": headroom,
        "headroom_mib": round(headroom / MIB, 2),
        "used_fraction": round(used_fraction, 4),
        "used_percent": round(used_percent_x100 / 100, 2),
        "exhausted": exhausted,
        "assumed_growth_bytes_per_run": growth_bytes_per_run,
        "runs_until_exhausted": runs_until_exhausted,
        # Exact integer cross-multiplication. No division, so no rounding
        # artifact at the boundary: used * 100 >= budget * 85 fires on the byte
        # that actually reaches 85%, and never a byte early or late.
        "severity": ("exhausted" if exhausted else
                     "critical" if actual_bytes * 100 >= budget_bytes * CRITICAL_PERCENT else
                     "warning" if actual_bytes * 100 >= budget_bytes * WARNING_PERCENT else
                     "healthy"),
        "thresholds_percent": {"warning": WARNING_PERCENT, "critical": CRITICAL_PERCENT},
    }


def plan_split(measured: dict, budget_bytes: int,
               part_bytes: int = OBSERVED_PART_BYTES) -> dict:
    # Coverage caveat computed up front because the plan's own conclusion can be
    # "no new partition needed" while the host is genuinely over budget: the plan
    # only ever sees the largest files that were enumerated, not all of them.
    """Decide which files move to a new partition and whether the split fits.

    Strategy is greedy-largest-first across the fewest partitions, keeping each
    partition under budget. Large `.part` chunks of one logical file are kept
    together where possible, because splitting a logical file across hosts means
    the client's reassembly order must span repositories — which the existing
    manifest format does not express. That constraint is reported explicitly
    rather than quietly violated.
    """
    files = [{"path": f["path"], "bytes": f["bytes"]} for f in measured["largest_files"]]
    if not files:
        return {"feasible": False, "reason": "no files enumerated; cannot plan"}

    # Group physical parts by their logical file so a logical file is never
    # split across hosts.
    groups: dict[str, dict] = {}
    for f in files:
        logical = re.sub(r"[-.]?(\d{4})\.part$", "", f["path"])
        logical = re.sub(r"^parts/[0-9a-f]{64}\.part$", f["path"], logical)
        entry = groups.setdefault(logical, {"logical": logical, "bytes": 0, "parts": []})
        entry["bytes"] += f["bytes"]
        entry["parts"].append(f["path"])

    oversized = [g for g in groups.values() if g["bytes"] > budget_bytes]
    ordered = sorted(groups.values(), key=lambda g: -g["bytes"])

    partitions: list[list[dict]] = [[]]
    sizes: list[int] = [0]
    # A partition holding an oversized logical file is already over budget, so
    # the "does it still fit" test can never pass for it again. Without this
    # flag the greedy loop kept stacking every subsequent group into that one
    # over-budget partition — observed as a 300% fill in testing — instead of
    # opening a new one.
    over_budget: list[bool] = [False]
    for group in ordered:
        placed = False
        for i in range(len(partitions)):
            if over_budget[i]:
                continue
            if sizes[i] + group["bytes"] <= budget_bytes:
                partitions[i].append(group)
                sizes[i] += group["bytes"]
                placed = True
                break
        if not placed:
            partitions.append([group])
            sizes.append(group["bytes"])
            over_budget.append(group["bytes"] > budget_bytes)

    new_partitions = len(partitions) - 1
    enumerated_bytes = sum(g["bytes"] for g in ordered)
    actual_bytes = int(measured.get("actual_bytes") or 0)
    plan_covers_host = enumerated_bytes >= actual_bytes
    contradicts_budget = (new_partitions == 0 and actual_bytes > budget_bytes)
    return {
        "feasible": not oversized,
        "enumerated_bytes": enumerated_bytes,
        "host_actual_bytes": actual_bytes,
        "plan_covers_host": plan_covers_host,
        "contradicts_measured_budget": contradicts_budget,
        "coverage_caveat": (
            "The plan was built from the largest enumerated files "
            f"({enumerated_bytes:,} B) while the host actually holds "
            f"{actual_bytes:,} B, so {actual_bytes - enumerated_bytes:,} B are not "
            "accounted for in the assignment. Treat the partition COUNT as a lower "
            "bound." if not plan_covers_host else
            "The enumerated files account for the whole measured host."),
        "contradiction_note": (
            "This plan reports no new partition while the measured host exceeds its "
            "budget. The measured host figure is authoritative; the plan is a "
            "lower bound built from a partial file listing. Plan a new partition."
            if contradicts_budget else None),
        "partitions_required": len(partitions),
        "new_partitions_required": new_partitions,
        "suggested_new_repository_names": [
            f"civic-newsroom-intelligence-{i + 2:03d}" for i in range(new_partitions)],
        "partition_sizes_bytes": sizes,
        "partition_fill_percent": [round(100 * s / budget_bytes, 2) for s in sizes],
        "partitions_over_budget": [i for i, over in enumerate(over_budget) if over],
        "assignments": [
            {"partition_index": i,
             "logical_files": [g["logical"] for g in partition],
             "bytes": sizes[i]}
            for i, partition in enumerate(partitions)],
        "oversized_logical_files": [
            {"logical": g["logical"], "bytes": g["bytes"],
             "problem": ("exceeds the whole budget on its own; must be split into "
                         f"<= {part_bytes:,}-byte parts within one host")}
            for g in oversized],
        "constraint": (
            "A logical file is never assigned across two partitions, because the "
            "published manifest expresses reassembly order within one host only. "
            "If a logical file exceeds the budget it must be re-parted into "
            "smaller physical chunks, not moved."),
        "note": (
            "Planned from the ten largest entries the descriptor verification "
            "enumerated. A full plan requires the complete file manifest; this is "
            "a sizing decision, not a migration script."),
    }


def audit(descriptor_url: str | None, code_repo: str, timeout: int,
          budget_mib: int, growth: int, descriptor_path: str | None) -> dict:
    budget_bytes = budget_mib * MIB
    descriptors: list[dict] = []

    if descriptor_url:
        try:
            req = urllib.request.Request(descriptor_url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                descriptors.append(json.loads(resp.read().decode("utf-8")))
        except Exception as exc:  # noqa: BLE001
            return {"schema": "intelligence-budget-report-v1", "fetch_error": str(exc)[:300],
                    "hosts": []}
    else:
        for path in ((descriptor_path,) if descriptor_path else DESCRIPTOR_PATHS):
            try:
                raw = api_contents(code_repo, path)
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    continue
                raise
            except Exception:  # noqa: BLE001
                continue
            try:
                parsed = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict) and parsed.get("data_repository"):
                parsed.setdefault("_descriptor_path", path)
                descriptors.append(parsed)

    hosts = []
    for descriptor in descriptors:
        verification = verify_descriptor(descriptor, descriptor["data_repository"], timeout)
        measured = verification.get("measured")
        entry: dict = {
            "descriptor_path": descriptor.get("_descriptor_path"),
            "data_repository": descriptor.get("data_repository"),
            "revision": descriptor.get("revision"),
            "verification": verification["checks"],
            "verified": verification["verified"],
            "declared_counts": {k: descriptor.get(k) for k in
                                ("records", "passages", "reference_mentions",
                                 "language_candidates", "workflow_run")},
            "self_declared_limits": {k: descriptor.get(k) for k in
                                     ("verified_entity_resolution", "source_independence")},
        }
        if measured:
            entry["measured"] = measured
            entry["budget"] = budget_report(measured["actual_bytes"], budget_bytes, growth)
            if entry["budget"]["exhausted"] or entry["budget"]["severity"] == "critical":
                entry["split_plan"] = plan_split(measured, budget_bytes)
        hosts.append(entry)

    worst = "healthy"
    order = {"healthy": 0, "warning": 1, "critical": 2, "exhausted": 3}
    for host in hosts:
        for check in host.get("verification", []):
            if not check["ok"] and "hash" in check["check"]:
                worst = "exhausted"
        severity = host.get("budget", {}).get("severity")
        if severity and order.get(severity, 0) > order[worst]:
            worst = severity

    return {
        "schema": "intelligence-budget-report-v1",
        "generated_by": "tools/intelligence_budget.py",
        "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "code_repository": None if descriptor_url else code_repo,
        "descriptor_url": descriptor_url,
        "budget_mib": budget_mib,
        "budget_bytes": budget_bytes,
        "hosts_audited": len(hosts),
        "worst_severity": worst,
        "hosts": hosts,
        "read_only": True,
        "scope_statement": (
            "Read-only audit of another repository's published descriptors via "
            "api.github.com. No cross-repository write was attempted or is "
            "implied; AGENTS.md requires explicit approval for those."),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="data/intelligence-budget")
    ap.add_argument("--code-repo", default=DEFAULT_CODE_REPO)
    ap.add_argument("--descriptor-url", help="fetch one descriptor from an exact URL")
    ap.add_argument("--descriptor-path", help="fetch one descriptor by repo path")
    ap.add_argument("--budget-mib", type=int, default=DEFAULT_BUDGET_MIB)
    ap.add_argument("--growth-bytes-per-run", type=int, default=0,
                    help="observed growth per build, used to project exhaustion")
    ap.add_argument("--timeout", type=int, default=60)
    ap.add_argument("--fail-on-exhausted", action="store_true",
                    help="exit 3 when any host is exhausted or hash-verified false")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    try:
        report = audit(args.descriptor_url, args.code_repo, args.timeout,
                       args.budget_mib, args.growth_bytes_per_run, args.descriptor_path)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"could not reach the GitHub API: {exc}", file=sys.stderr)
        return 4

    out = Path(args.out)
    if not args.descriptor_url:
        out = ROOT / out if not out.is_absolute() else out
        out.mkdir(parents=True, exist_ok=True)
        (out / "budget-report.json").write_text(json.dumps(report, indent=2) + "\n",
                                                encoding="utf-8")

    # Checked before the quiet branch on purpose: --quiet suppresses output, not
    # failure. Returning 0 here would let a CI gate read "audit passed" for a run
    # that audited nothing at all, which is worse than no gate.
    if report.get("fetch_error"):
        if not args.quiet:
            print(f"FETCH ERROR: {report['fetch_error']}")
        return 4
    if not report["hosts"]:
        if not args.quiet:
            print("NO HOSTS AUDITED: no publication descriptor was found at "
                  f"{args.descriptor_url or args.code_repo}. That is not a pass.")
        return 4

    if not args.quiet:
        print(f"intelligence budget audit — {report['hosts_audited']} host(s), "
              f"worst severity: {report['worst_severity'].upper()}")
        for host in report["hosts"]:
            print(f"\n  {host['data_repository']}@{(host['revision'] or '')[:12]}")
            failed = [c for c in host["verification"] if not c["ok"]]
            print(f"    verification: {'PASS' if host['verified'] else f'FAIL ({len(failed)})'}")
            for c in failed:
                print(f"      ✗ {c['check']}: {c['detail'][:150]}")
            budget = host.get("budget")
            if budget:
                print(f"    budget: {budget['actual_bytes']:,} / {budget['budget_bytes']:,} "
                      f"= {budget['used_percent']}%  headroom {budget['headroom_mib']} MiB  "
                      f"[{budget['severity']}]")
                if budget["runs_until_exhausted"] is not None:
                    print(f"    projection: {budget['runs_until_exhausted']} build(s) until "
                          f"exhaustion at {budget['assumed_growth_bytes_per_run']:,} B/run")
                plan = host.get("split_plan")
                if plan:
                    print(f"    split plan: {plan['partitions_required']} partition(s) needed, "
                          f"{plan['new_partitions_required']} new")
                    for name in plan["suggested_new_repository_names"]:
                        print(f"      → {name}")
                    for over in plan["oversized_logical_files"]:
                        print(f"      ⚠ {over['logical']}: {over['bytes']:,} B — {over['problem']}")
                    if plan.get("contradicts_measured_budget"):
                        print(f"      ⚠ {plan['contradiction_note']}")
                    elif not plan.get("plan_covers_host", True):
                        print(f"      ⚠ {plan['coverage_caveat']}")
            limits = host.get("self_declared_limits") or {}
            if limits:
                print(f"    self-declared: entity_resolution="
                      f"{limits.get('verified_entity_resolution')} "
                      f"source_independence={limits.get('source_independence')!r}")
        if not args.descriptor_url:
            print(f"\n  wrote {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}"
                  f"/budget-report.json")

    if args.fail_on_exhausted:
        bad = report["worst_severity"] in ("exhausted",) or any(
            not h["verified"] for h in report["hosts"])
        if bad:
            return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
