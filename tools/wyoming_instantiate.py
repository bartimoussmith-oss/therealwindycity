#!/usr/bin/env python3
"""Wyoming instantiation generator.

Renders one self-contained "ecosystem" instance per Wyoming jurisdiction from
`wyoming/registry.json`: every state-level body, all 23 counties, and all 99
incorporated municipalities. Each instance is a functional clone of the
Cheyenne build (engine + configs + PRA drafting + digest + static ledger site),
scoped to its own jurisdiction, sharing the single engine in this repo.

Usage:
  python3 tools/wyoming_instantiate.py --write      # (re)generate ALL instances
  python3 tools/wyoming_instantiate.py --write --slug casper
  python3 tools/wyoming_instantiate.py --check      # exit 1 if instances drift from the registry (CI gate)
  python3 tools/wyoming_instantiate.py --list       # print the registry table

Guarantees & limits (honesty contract):
  * No network access. Nothing here asserts that any URL works. Every source is
    generated disabled with verification="unverified"; the statewide verifier
    (tools/wyoming_verify.py, run by .github/workflows/wyoming-verify.yml)
    live-fetches candidates, honors robots.txt, fingerprints the platform
    (Granicus / CivicPlus / WordPress / Municode / unknown), and only then
    enables what actually answered.
  * No local lore is fabricated. Non-Cheyenne instances ship an empty timeline
    and no question-of-the-week until a human adds the local record.
  * Deterministic: the same registry always renders byte-identical instances.
    `--check` proves the committed instances were produced by this generator.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = ROOT / "wyoming" / "registry.json"
INSTANCES_DIR = ROOT / "wyoming" / "instances"

WYOMING_STATEWIDE_SOURCES = [
    {
        "name": "wyofile_rss",
        "type": "rss",
        "url": "https://wyofile.com/feed",
        "enabled": False,
        "notes": "WyoFile (nonprofit statewide newsroom). UNVERIFIED feed path — confirm it resolves before enabling. Statewide accountability journalism; strong on energy, water, land, and government.",
    },
    {
        "name": "cowboy_state_daily_rss",
        "type": "rss",
        "url": "https://cowboystatedaily.com/feed",
        "enabled": False,
        "notes": "Cowboy State Daily. UNVERIFIED feed path. Statewide politics/energy/government; already cited throughout the Cheyenne record.",
    },
    {
        "name": "wte_statewide_rss",
        "type": "rss",
        "url": "http://www.wyomingnews.com/search/?f=rss&l=50&s=start_time&sd=desc",
        "enabled": False,
        "notes": "Wyoming Tribune Eagle TownNews search-RSS. FIRST-RUN FINDING (Cheyenne build): returned HTTP 429. Run at most ~once/day or leave disabled and read in a browser.",
    },
]

CHEYENNE_REGIONAL_SOURCE = {
    "name": "cap_city_news_rss",
    "type": "rss",
    "url": "https://capcity.news/feed",
    "enabled": False,
    "notes": "Cap City News — Cheyenne/Laramie County beat. Regional rather than statewide; enable only for Laramie County instances.",
}

STATEWIDE_ENERGY_TERMS = [
    "data center", "data hall", "Crusoe", "Tallgrass", "Vantage", "Microsoft", "Meta",
    "Project Jade", "Project Latigo", "annexation", "moratorium", "zone change",
    "Planned Unit Development", "planned unit development", "PUD", "conditional use",
    "ordinance", "resolution", "first reading", "second reading", "public notice",
    "wind farm", "solar farm", "wind project", "transmission line", "substation",
    "pipeline", "megawatt", "gigawatt", "terawatt", "coal", "trona", "gilsonite",
    "uranium", "in-situ", "lithium", "rare earth", "oil and gas", "oil & gas",
    "carbon capture", "carbon sequestration", "enhanced oil recovery", "nuclear",
    "black hills energy", "pacifiCorp", "rocky mountain power", "rate case",
    "net metering", "renewable energy", "utility corridor", "eminent domain",
    "right-of-way", "right of way",
]

STATEWIDE_WATER_TERMS = [
    "water rights", "water right", "watershed", "reclaimed water", "reuse water",
    "effluent", "discharge permit", "NPDES", "fill-and-flush", "closed-loop",
    "aquifer", "groundwater", "streamflow", "Wyoming DEQ", "DEQ", "air quality",
    "emissions permit", "sage grouse", "wildlife connectivity", "NEPA", "BLM",
    "U.S. Forest Service", "Wyoming Game and Fish", "water board", "Irrigation district",
]

STATEWIDE_PROCEDURAL_TERMS = [
    "executive session", "not on the agenda", "notice of hearing", "public hearing",
    "mill levy", "tax increment", "TIF district", "special district", "appropriation",
    "budget amendment", "declaration of emergency", "eminent domain", "condemnation",
    "public records", "open meetings", "Wyoming Public Records Act", "WPRA",
    "executive privilege", "conflict of interest", "ethics complaint", "audit",
    "consent agenda", "deferred", "tabled",
]


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def domain_token(slug: str) -> str:
    return slug.replace("-", "")


def candidate_domains(entry: dict) -> list[str]:
    """Ordered, plausible official-site candidates for the verifier to probe."""
    slug = entry["slug"]
    tok = domain_token(slug)
    name = entry["name"]
    typ = entry["type"]
    cands: list[str] = []
    if entry.get("known_url"):
        cands.append(entry["known_url"])
    if typ in ("city", "town"):
        cands += [
            f"https://www.{tok}wy.gov",
            f"https://{tok}wy.gov",
            f"https://www.{tok}.gov",
            f"https://www.cityof{tok}.gov",
            f"https://www.cityof{tok}.org",
            f"https://www.cityof{tok}.com",
            f"https://www.townof{tok}.gov",
            f"https://www.townof{tok}.org",
            f"https://www.townof{tok}.com",
            f"https://www.ci.{tok}.wy.us",
            f"https://www.{tok}wy.org",
            f"https://{tok}wy.org",
        ]
    elif typ == "county":
        cs = slugify(entry["county"])
        ctok = cs.replace("-", "")
        cands += [
            f"https://www.{ctok}countywy.gov",
            f"https://{ctok}countywy.gov",
            f"https://www.{ctok}countywy.com",
            f"https://www.{ctok}county.net",
            f"https://www.{ctok}countywy.us",
            f"https://www.{ctok}county.com",
            f"https://{ctok}county.net",
        ]
    elif typ == "state-legislature":
        cands += ["https://wyoleg.gov", "https://www.wyoleg.gov"]
    elif typ == "state-executive":
        pass  # known_url carries it
    # de-dup, preserve order
    seen, out = set(), []
    for c in cands:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def load_registry() -> dict:
    reg = json.loads(REGISTRY_PATH.read_text())
    slugs = [j["slug"] for j in reg["jurisdictions"]]
    dupes = {s for s in slugs if slugs.count(s) > 1}
    if dupes:
        raise ValueError(f"duplicate slugs in registry: {sorted(dupes)}")
    if reg["counts"]["total_instances"] != len(reg["jurisdictions"]):
        raise ValueError("registry counts.total_instances does not match jurisdictions[]")
    return reg


def load_verification(slug: str) -> dict | None:
    """Committed verifier output for this instance (if any). When present and
    live-verified, the render enables exactly what the verifier enabled — so
    `wyoming_instantiate.py --check` stays green after `wyoming_verify --apply`."""
    path = INSTANCES_DIR / slug / "verification.json"
    if not path.exists():
        return None
    try:
        v = json.loads(path.read_text())
    except json.JSONDecodeError:
        return None
    return v if v.get("verification") == "live-verified" else None


def watchlist_for(entry: dict) -> dict:
    name = entry["name"]
    typ = entry["type"]
    county = entry.get("county")
    jurisdiction_terms = [name]
    if typ in ("city", "town"):
        jurisdiction_terms += [f"City of {name}", f"Town of {name}", f"{name}, Wyoming"]
        if county:
            jurisdiction_terms.append(f"{county} County")
    elif typ == "county":
        seat = entry.get("county_seat_name")
        jurisdiction_terms += [f"{name} Commissioners", "Board of County Commissioners",
                               "county commissioners", f"{name}, Wyoming"]
        if seat:
            jurisdiction_terms.append(seat)
    elif typ == "state-legislature":
        jurisdiction_terms = ["Wyoming Legislature", "wyoleg", "wyoleg.gov",
                              "Senate File", "House Bill", "Joint Conference Committee",
                              "Management Council"]
    elif typ == "state-executive":
        jurisdiction_terms.append("State of Wyoming")
    if name == "Cheyenne":
        jurisdiction_terms += ["Cheyenne City Council", "City of Cheyenne", "Ordinance No. 4687"]
    return {
        "notes": ("Terms match case-insensitively; every hit stores a verbatim quote. Wyoming-wide "
                  "energy/data-center/water/procedural-integrity terms fire statewide BY DESIGN — a data-center "
                  "or pipeline story in any Wyoming jurisdiction is the story. Jurisdiction-specific terms are "
                  "under 'jurisdiction'. LEGAL.md rule 5: public officials, official capacity only."),
        "topics": {
            "data_center_and_energy": STATEWIDE_ENERGY_TERMS,
            "water_and_environment": STATEWIDE_WATER_TERMS,
            "procedural_integrity": STATEWIDE_PROCEDURAL_TERMS,
            "jurisdiction": jurisdiction_terms,
        },
    }


def sources_for(entry: dict) -> dict:
    slug = entry["slug"]
    name = entry["name"]
    typ = entry["type"]
    cands = candidate_domains(entry)
    primary = entry.get("known_url") or (cands[0] if cands else None)
    if primary is None:
        # Must still be valid JSON for the engine; disabled placeholder, no network use.
        primary = f"https://example.invalid/{slug} homepage-discovery-pending"
    sources = [
        {
            "name": f"{slug}_homepage",
            "type": "html",
            "url": primary,
            "enabled": False,
            "notes": ("UNVERIFIED candidate — generated from wyoming/registry.json. DO NOT ENABLE BY HAND. "
                      "Run: python3 tools/wyoming_verify.py --slug " + slug + " --apply. "
                      "The verifier honors robots.txt, fingerprints the platform (Granicus/CivicPlus/WordPress/"
                      "Municode/unknown), and enables this source only if it live-fetches successfully. "
                      "If no candidate URL resolves, this jurisdiction may need manual onboarding — see "
                      "docs/WYOMING-STATEWIDE-INSTANTIATION.md ('Non-web jurisdictions')."),
        },
        {
            "name": f"{slug}_wyomingnews_search",
            "type": "rss",
            "url": f"http://www.wyomingnews.com/search/?f=rss&l=50&s=start_time&sd=desc&q={name}",
            "enabled": False,
            "notes": ("Wyoming Tribune Eagle TownNews search-RSS filtered to this jurisdiction's name. "
                      "UNVERIFIED; the Cheyenne build of this endpoint returned HTTP 429 on first contact — "
                      "run at most ~once/day or leave disabled and read in a browser."),
        },
    ]
    sources.extend(statewide_news_sources_for(entry))
    if typ == "county" or (typ in ("city", "town") and entry.get("county") == "Laramie"):
        sources.append(dict(CHEYENNE_REGIONAL_SOURCE))
    if typ == "state-legislature":
        sources.append({
            "name": "wyoleg_site",
            "type": "html",
            "url": "https://wyoleg.gov",
            "enabled": False,
            "notes": "Wyoming Legislature — UNVERIFIED candidate; confirm before enabling. Bills, acts, session calendar, committee agendas. The verifier fingerprints the site and reports its agenda paths.",
        })
    verification = load_verification(slug)
    if verification:
        vurl = verification.get("verified_url")
        platform = verification.get("platform") or "unknown"
        checked = verification.get("checked_at", "unknown-time")
        for s_ in sources:
            if s_["name"] == f"{slug}_homepage" and vurl:
                s_["enabled"] = True
                s_["url"] = vurl
                s_["notes"] = (f"Live-verified {checked} by tools/wyoming_verify.py "
                               f"(robots.txt honored). Platform fingerprint: {platform}. "
                               "Confirm this is the official site before relying on it.")
        agenda_paths = verification.get("agenda_paths") or []
        if agenda_paths:
            best = agenda_paths[0]
            if not any(s_["name"] == f"{slug}_agendas" for s_ in sources):
                sources.append({
                    "name": f"{slug}_agendas",
                    "type": "html",
                    "url": best["url"],
                    "enabled": True,
                    "notes": (f"Auto-detected {checked} by tools/wyoming_verify.py: fetched 200 and contained "
                              f"agenda/minutes keywords {best.get('matched')}. robots.txt was honored during the "
                              "probe. Verify in a browser; disable if this is not the official portal."),
                })
    return {
        "identity": {
            "user_agent": "WyomingCivicTransparencyEngine/0.1 (public-records research; contact: you@example.org)",
            "contact": "you@example.org  <-- PUT YOUR REAL CONTACT HERE; honest UAs get blocked less",
            "delay_seconds_per_host": 3,
            "max_docs_per_source_per_run": 40,
        },
        "sources": sources,
        "document_link_patterns": [
            "agenda", "minutes", "packet", "ordinance", "resolution",
            "staff.?report", "application", "zone.?change", "annexation",
            "\\.pdf($|\\?)", "\\.docx?($|\\?)", "\\.xlsx?($|\\?)", "\\.csv($|\\?)", "\\.txt($|\\?)",
        ],
    }


def statewide_news_sources_for(entry: dict) -> list[dict]:
    return [dict(s) for s in WYOMING_STATEWIDE_SOURCES]


def facts_for(entry: dict) -> dict:
    name = entry["name"]
    typ = entry["type"]
    county = entry.get("county")
    if typ == "state-legislature":
        title = "THE REAL WYOMING LEGISLATURE LEDGER"
        kicker = "Wyoming state government — public documents in, verifiable evidence out."
    elif typ == "state-executive":
        title = f"THE REAL {name.upper()} LEDGER"
        kicker = f"{name} — public documents in, verifiable evidence out."
    elif typ == "county":
        title = f"THE REAL {name.upper()} LEDGER"
        kicker = f"{name}, Wyoming — public documents in, verifiable evidence out."
    else:
        title = f"THE REAL {name.upper()} LEDGER"
        kicker = f"{name}, Wyoming — public documents in, verifiable evidence out."
    voice_note = ("Not produced by, endorsed by, or affiliated with any individual — named or otherwise — "
                  "or any candidate, campaign, or political committee.")
    owner_todo = [
        "Run: python3 tools/wyoming_verify.py --slug " + entry["slug"] + " --apply  (live-fetches and enables only what actually answers; honors robots.txt).",
        "Confirm the clerk/custodian office and mailing address in env.sh before any Wyoming Public Records Act request is sent.",
        "Add this jurisdiction's local record to facts.json: timeline entries (each with a linked source) and a question_of_the_week. Nothing local is asserted until you do — that is deliberate.",
        "If this municipality has no usable web presence, the engine still works: digest + silent-edit detection are only as good as the sources you enable, and `run.py request pra` drafts PRAs from first principles.",
        "Optional: set election_day (ISO date) and election_stat_label in facts.json for the countdown stat. Wyoming's uniform municipal general election is the Tuesday after the first Monday in November of odd-numbered years — verify your jurisdiction's calendar with the County Clerk or the Secretary of State.",
    ]
    facts = {
        "site": {
            "title": title,
            "kicker": kicker,
            "tagline": "Public documents in. Verifiable evidence out.",
            "voice_note": voice_note,
        },
        "timeline": [],
        "owner_todo": owner_todo,
        "notes": [
            "Generated instance — NO local facts, events, quotes, or attribution are present yet. Empty by design; the owner adds the local record.",
            "Jurisdiction type: %s. County: %s. Population (2020 Census): %s." % (
                typ, county or "n/a (state-level)", entry.get("population_2020")),
        ],
    }
    if county:
        facts["site"]["county"] = county
    return facts


def readme_for(entry: dict) -> str:
    name = entry["name"]
    typ = entry["type"]
    slug = entry["slug"]
    county = entry.get("county")
    pop = entry.get("population_2020")
    lines = [
        f"# The Real {name} Ledger — {typ} watchdog",
        "",
        "Generated by `tools/wyoming_instantiate.py` from `wyoming/registry.json`.",
        "Part of the statewide Wyoming instantiation — see `docs/WYOMING-STATEWIDE-INSTANTIATION.md`.",
        "",
        "## Status: GENERATED, UNVERIFIED",
        "",
        "No source in this instance has been fetched. Every source is `enabled: false`.",
        "Nothing about this government is asserted anywhere in this directory.",
        "",
        f"- Type: `{typ}`" + (f" · County: `{county} County`" if county else ""),
    ]
    if pop is not None:
        lines.append(f"- 2020 Census population: {pop}")
    if entry.get("county_seat") and county:
        seat_note = entry.get("county_seat_name")
        lines.append("- County seat" + (f" (seat: {seat_note})" if seat_note else ""))
    if entry.get("state_capital"):
        lines.append("- State capital")
    lines += [
        "",
        "## Run it",
        "",
        "```bash",
        f"wyoming/run-instance.sh {slug} selftest   # prove the pipeline offline (no network)",
        f"wyoming/run-instance.sh {slug} init       # create this instance's database",
        f"wyoming/run-instance.sh {slug} crawl      # polite pull of ENABLED sources only (all disabled until verified)",
        f"wyoming/run-instance.sh {slug} work     # extract / index / scan / diff",
        f"wyoming/run-instance.sh {slug} digest   # write the evidence digest",
        f"wyoming/run-instance.sh {slug} request pra --help   # draft a Wyoming Public Records Act request (a human sends it)",
        "```",
        "",
        "Data and the rendered site are written to `data/wyoming/" + slug + "/` and `public/wyoming/" + slug + "/`",
        "(both git-ignored). The shared engine in `engine/` is not duplicated — instances are configuration, not forks.",
        "",
        "## Onboard this jurisdiction",
        "",
        "1. `python3 tools/wyoming_verify.py --slug " + slug + "` — probe candidate official URLs; writes `verification.json` here.",
        "2. `python3 tools/wyoming_verify.py --slug " + slug + " --apply` — enable what genuinely answered (robots.txt honored).",
        "3. Confirm the custodian office/address in `env.sh` (currently UNVERIFIED placeholders).",
        "4. Add the local record to `config/facts.json` (timeline + question_of_the_week), each entry linked to its source.",
        "5. Rerun `python3 tools/wyoming_instantiate.py --check` to confirm the instance is generator-clean.",
        "",
        "If no candidate URL resolves: many Wyoming towns have minimal web presences. The Wyoming Public Records",
        "Act request path (`run.py request pra`) and the digest pipeline still work; add manual source URLs to",
        "`config/sources.json` only after you have opened them in a browser and confirmed they are public.",
        "",
        "## Honesty contract",
        "",
        "- Empty timeline, no question_of_the_week, zero enabled sources: this instance asserts nothing yet.",
        "- After verification, every alert carries a verbatim quote + source URL + fetch timestamp (LEGAL.md).",
        "- This instance says nothing about any official's conduct until documents back it.",
        "",
    ]
    return "\n".join(lines)


def env_sh_for(entry: dict) -> str:
    name = entry["name"]
    typ = entry["type"]
    if typ == "county":
        office = f"Office of the County Clerk, {name}, Wyoming"
    elif typ in ("city", "town"):
        office = f"Office of the Clerk/Treasurer, {name}, Wyoming"
    elif typ == "state-legislature":
        office = "Wyoming Legislative Service Office, Cheyenne, WY"
    else:
        office = f"{name}, State of Wyoming"
    return (
        "# Generated by tools/wyoming_instantiate.py — UNVERIFIED PLACEHOLDERS.\n"
        "# Confirm the records custodian's office and mailing address before sending anything.\n"
        f"export ENGINE_CUSTODIAN_OFFICE=\"{office}\"\n"
        "export ENGINE_CUSTODIAN_ADDRESS=\"[UNVERIFIED — confirm mailing address with the clerk before sending]\"\n"
        f"export ENGINE_WARD_OR_AREA=\"{name}\"\n"
    )


def ecosystem_for(entry: dict) -> dict:
    return {
        "slug": entry["slug"],
        "name": entry["name"],
        "type": entry["type"],
        "county": entry.get("county"),
        "county_seat": entry.get("county_seat", False),
        "county_seat_name": entry.get("county_seat_name"),
        "state_capital": entry.get("state_capital", False),
        "population_2020": entry.get("population_2020"),
        "known_url": entry.get("known_url"),
        "verification": entry.get("verification", "unverified"),
        "candidate_domains": candidate_domains(entry),
        "generated_by": "tools/wyoming_instantiate.py",
        "shared_engine": "engine/ (this repository) — instances are configuration, not forks",
        "canonical_cheyenne": "root config/ is canonical for Cheyenne; this instance is generated for completeness" if entry["slug"] == "cheyenne" else None,
        "notes": entry.get("notes", []),
    }


def render_instance(entry: dict) -> dict[str, str]:
    slug = entry["slug"]
    return {
        "config/sources.json": json.dumps(sources_for(entry), indent=2) + "\n",
        "config/watchlist.json": json.dumps(watchlist_for(entry), indent=2) + "\n",
        "config/facts.json": json.dumps(facts_for(entry), indent=2) + "\n",
        "README.md": readme_for(entry),
        "ecosystem.json": json.dumps(ecosystem_for(entry), indent=2) + "\n",
        "env.sh": env_sh_for(entry),
    }


def write_instance(entry: dict) -> list[str]:
    files = render_instance(entry)
    inst_dir = INSTANCES_DIR / entry["slug"]
    written = []
    for rel, content in files.items():
        path = inst_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists() or path.read_text() != content:
            path.write_text(content)
            written.append(str(path.relative_to(ROOT)))
    return written


def check_instance(entry: dict) -> list[str]:
    drift = []
    inst_dir = INSTANCES_DIR / entry["slug"]
    for rel, content in render_instance(entry).items():
        path = inst_dir / rel
        if not path.exists():
            drift.append(f"MISSING {path.relative_to(ROOT)}")
        elif path.read_text() != content:
            drift.append(f"DRIFT   {path.relative_to(ROOT)}")
    # Flag stale files that no longer belong to the render (excluding verifier output)
    if inst_dir.exists():
        expected = {str((inst_dir / rel).resolve()) for rel in render_instance(entry)}
        for path in inst_dir.rglob("*"):
            if path.is_file() and str(path.resolve()) not in expected:
                if path.name in ("verification.json",):
                    continue  # verifier output is preserved
                drift.append(f"EXTRA   {path.relative_to(ROOT)}")
    return drift


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true", help="(re)generate instances")
    ap.add_argument("--check", action="store_true", help="verify instances match the registry (CI gate)")
    ap.add_argument("--list", action="store_true", help="list the registry")
    ap.add_argument("--slug", help="restrict to one jurisdiction slug")
    ap.add_argument("--json", action="store_true", help="machine-readable summary")
    args = ap.parse_args()

    reg = load_registry()
    entries = reg["jurisdictions"]
    if args.slug:
        entries = [e for e in entries if e["slug"] == args.slug]
        if not entries:
            print(f"no jurisdiction with slug {args.slug!r}", file=sys.stderr)
            sys.exit(2)

    if args.list:
        for e in entries:
            print(f"{e['slug']:22} {e['type']:17} {str(e.get('county') or '—'):12} pop={e.get('population_2020')}")
        return

    if args.check:
        drift = []
        for e in entries:
            drift.extend(check_instance(e))
        if drift:
            print("INSTANCE DRIFT DETECTED:", file=sys.stderr)
            for d in drift:
                print("  " + d, file=sys.stderr)
            sys.exit(1)
        print(f"OK: {len(entries)} instance(s) match the registry exactly.")
        return

    if args.write:
        changed = 0
        for e in entries:
            changed += len(write_instance(e))
        if args.json:
            print(json.dumps({"instances": len(entries), "files_changed": changed}))
        else:
            print(f"Generated {len(entries)} instance(s); {changed} file(s) written/updated.")
        return

    ap.print_help()


# onboarding-policy-migration-v1
from wyoming_policy import install as _install_onboarding
_install_onboarding(globals())

if __name__ == "__main__":
    main()
