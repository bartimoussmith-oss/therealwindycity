#!/usr/bin/env python3
"""Statewide Wyoming verifier — the automation engine behind instantiation.

Live-fetches each generated instance's candidate official URLs, honors
robots.txt, fingerprints the site platform, probes common agenda/minutes
paths, and (with --apply) enables exactly what genuinely answered.

This tool performs real network I/O. It is designed to run in GitHub Actions
(.github/workflows/wyoming-verify.yml), where outbound network exists. In a
network-restricted sandbox it reports UNREACHABLE for everything and enables
nothing — which is the correct, honest failure mode.

Politeness contract (LEGAL.md): identifying User-Agent, per-host delay
(default 3s), small timeouts, public pages only, no logins, robots.txt wins.

Usage:
  python3 tools/wyoming_verify.py --all                     # probe every instance
  python3 tools/wyoming_verify.py --slug casper             # probe one
  python3 tools/wyoming_verify.py --slug casper --apply     # enable what verified, IN-PLACE
  python3 tools/wyoming_verify.py --all --apply --json      # CI mode: summary JSON on stdout

Outputs:
  wyoming/instances/<slug>/verification.json   (always)
  config/sources.json enabled-flags            (only with --apply, only for what verified)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.robotparser
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

INSTANCES_DIR = ROOT / "wyoming" / "instances"
UA = "WyomingCivicTransparencyEngine/0.1 (public-records research; polite probe; contact: you@example.org)"

AGENDA_PATH_PROBES = [
    "/government/agendas", "/government/agendas-minutes", "/agendas", "/agenda-center",
    "/AgendaCenter", "/Agenda-Center", "/civicplus/agenda-center",
    "/meetings", "/meeting-calendar", "/calendar", "/minutes", "/meeting-minutes",
    "/city-council/agendas", "/town-council/agendas", "/council/agendas",
    "/government/meetings", "/government/minutes", "/your-government",
]

PLATFORM_FINGERPRINTS = [
    ("granicus", ("granicus.com", "granicus egovernar", "viewpublisher.php")),
    ("civicplus", ("civicplus.com", "/civicplus/", "civicplus-agenda")),
    ("municode", ("municode.com", "codelibrary.municode", "library.municode")),
    ("wordpress", ("wp-content", "wp-json", "wp-includes")),
    ("granicus-agenda", ("agenda-detail.php", "AgendaOnline")),
    ("iqm2", ("iqm2.com", "iqm2 agenda")),
    ("legistar", ("legistar.com", "granicuslegistar")),
    ("pagefront", ("pagefront",)),
    ("drupal", ("drupal.settings", "sites/default/files")),
    ("squarespace-or-wix", ("squarespace", "wix.com/website", "static.parastorage")),
]


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class PoliteFetcher:
    def __init__(self, delay_s: float = 3.0, timeout_s: float = 12.0):
        self.delay = delay_s
        self.timeout = timeout_s
        self._last_hit: dict[str, float] = {}

    def _wait(self, host: str) -> None:
        last = self._last_hit.get(host, 0.0)
        wait = self.delay - (time.monotonic() - last)
        if wait > 0:
            time.sleep(wait)

    def get(self, url: str, max_bytes: int = 400_000) -> tuple[int | None, str, str | None]:
        """Returns (status, text, error). status None => unreachable/blocked."""
        host = urllib.parse.urlsplit(url).netloc
        self._wait(host)
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,application/rss+xml,*/*"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                self._last_hit[host] = time.monotonic()
                status = getattr(resp, "status", 200)
                raw = resp.read(max_bytes)
                ctype = resp.headers.get("content-type", "")
                text = raw.decode("utf-8", errors="replace")
                return status, text, None
        except urllib.error.HTTPError as e:
            self._last_hit[host] = time.monotonic()
            return e.code, "", f"http-{e.code}"
        except Exception as e:  # URLError, timeout, ssl, etc.
            self._last_hit[host] = time.monotonic()
            return None, "", f"{type(e).__name__}: {e}"

    def robots_allows(self, url: str) -> tuple[bool, str]:
        """Returns (allowed, detail). Fail-closed=False: an unreadable robots.txt is reported, not silently passed."""
        parts = urllib.parse.urlsplit(url)
        robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
        rp = urllib.robotparser.RobotFileParser()
        status, text, err = self.get(robots_url, max_bytes=64_000)
        if err or status != 200:
            return True, f"robots.txt unreadable ({err or status}) — proceeding per LEGAL.md caution, human review required"
        try:
            rp.parse(text.splitlines())
            allowed = rp.can_fetch(UA, url)
            return allowed, ("robots.txt allows" if allowed else "robots.txt DISALLOWS")
        except Exception as e:
            return True, f"robots.txt parse error ({e}) — human review required"


def fingerprint(html: str) -> str:
    low = html.lower()
    for label, needles in PLATFORM_FINGERPRINTS:
        if any(n in low for n in needles):
            return label
    return "unknown"


def load_ecosystem(inst_dir: Path) -> dict:
    return json.loads((inst_dir / "ecosystem.json").read_text())


def verify_instance(slug: str, fetcher: PoliteFetcher, apply: bool) -> dict:
    inst_dir = INSTANCES_DIR / slug
    eco = load_ecosystem(inst_dir)
    candidates: list[str] = eco.get("candidate_domains") or ([eco["known_url"]] if eco.get("known_url") else [])
    result = {
        "slug": slug,
        "name": eco["name"],
        "type": eco["type"],
        "checked_at": now_iso(),
        "candidates": [],
        "verified_url": None,
        "platform": None,
        "agenda_paths": [],
        "verification": "unverified",
        "applied": False,
        "notes": [],
    }
    verified = None
    for url in candidates:
        allowed, robot_note = fetcher.robots_allows(url)
        entry = {"url": url, "robots": robot_note, "status": None, "reachable": False, "platform": None}
        if not allowed:
            entry["robots_allowed"] = False
            result["candidates"].append(entry)
            continue
        status, text, err = fetcher.get(url)
        entry["status"] = status
        entry["error"] = err
        entry["reachable"] = status == 200 and bool(text)
        if entry["reachable"]:
            entry["platform"] = fingerprint(text)
        result["candidates"].append(entry)
        if verified is None and entry["reachable"]:
            verified = (url, entry["platform"], text)
    if verified:
        url, platform, text = verified
        result["verified_url"] = url
        result["platform"] = platform
        result["verification"] = "live-verified"
        # Probe agenda/minutes paths on the verified host only.
        parts = urllib.parse.urlsplit(url)
        base = f"{parts.scheme}://{parts.netloc}"
        for path in AGENDA_PATH_PROBES:
            allowed, robot_note = fetcher.robots_allows(base + path)
            if not allowed:
                continue
            status, text2, err = fetcher.get(base + path, max_bytes=200_000)
            if status == 200 and text2:
                low = text2.lower()
                hits = [kw for kw in ("agenda", "minutes", "packet", "meeting") if kw in low]
                if hits:
                    result["agenda_paths"].append({"url": base + path, "matched": hits})
        result["notes"].append(
            "Live-fetch succeeded; platform fingerprint is a heuristic, not a guarantee. "
            "Open the URL in a browser and confirm this is the official government site before enabling.")
    else:
        result["notes"].append(
            "No candidate URL answered with 200 from this network. This does NOT prove the jurisdiction "
            "has no site — the probe may be blocked, rate-limited, or sandboxed. Verify manually.")

    out_path = inst_dir / "verification.json"
    out_path.write_text(json.dumps(result, indent=2) + "\n")

    if apply and verified:
        # Re-render the instance through the generator so sources.json stays
        # deterministic w.r.t. the committed verification.json (keeps
        # `wyoming_instantiate.py --check` green).
        sys.path.insert(0, str(ROOT / "tools"))
        import wyoming_instantiate as gen
        reg = gen.load_registry()
        entry = next((e for e in reg["jurisdictions"] if e["slug"] == slug), None)
        if entry is None:
            result["notes"].append("apply skipped: slug not present in wyoming/registry.json")
        else:
            gen.write_instance(entry)
            result["applied"] = True
            result["notes"].append("sources.json re-rendered from registry + verification.json; enabled flags reflect exactly what live-verified.")
    out_path.write_text(json.dumps(result, indent=2) + "\n")
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--slug", help="one instance slug")
    ap.add_argument("--all", action="store_true", help="every instance")
    ap.add_argument("--apply", action="store_true", help="enable what verified (in-place)")
    ap.add_argument("--json", action="store_true", help="print summary JSON")
    ap.add_argument("--delay", type=float, default=3.0, help="per-host politeness delay (seconds, default 3)")
    ap.add_argument("--timeout", type=float, default=12.0, help="per-request timeout (seconds)")
    args = ap.parse_args()

    if not args.all and not args.slug:
        ap.error("choose --all or --slug <slug>")
    all_slugs = sorted(p.name for p in INSTANCES_DIR.iterdir() if p.is_dir()) if INSTANCES_DIR.exists() else []
    slugs = [args.slug] if args.slug else all_slugs

    fetcher = PoliteFetcher(delay_s=args.delay, timeout_s=args.timeout)
    results = []
    for slug in slugs:
        inst = INSTANCES_DIR / slug
        if not inst.exists():
            print(f"[skip] {slug}: no instance directory", file=sys.stderr)
            continue
        try:
            results.append(verify_instance(slug, fetcher, args.apply))
        except Exception as e:
            print(f"[error] {slug}: {type(e).__name__}: {e}", file=sys.stderr)
            results.append({"slug": slug, "verification": "error", "error": f"{type(e).__name__}: {e}"})

    summary = {
        "checked_at": now_iso(),
        "total": len(results),
        "live_verified": sum(1 for r in results if r.get("verification") == "live-verified"),
        "unverified": sum(1 for r in results if r.get("verification") == "unverified"),
        "errors": sum(1 for r in results if r.get("verification") == "error"),
        "applied": sum(1 for r in results if r.get("applied")),
    }
    if args.json:
        print(json.dumps(summary))
    else:
        print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
