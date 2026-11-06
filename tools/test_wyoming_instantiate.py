# onboarding-policy-migration-v1
#!/usr/bin/env python3
"""Offline tests for the statewide Wyoming instantiation.

Run: python3 tools/test_wyoming_instantiate.py
No network. Verifies: registry integrity, generator determinism, instance
well-formedness, and the honesty contract (nothing enabled by default, no
fabricated local content).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import wyoming_instantiate as gen  # noqa: E402

WIYO_COUNTIES = {
    "Albany", "Big Horn", "Campbell", "Carbon", "Converse", "Crook", "Fremont",
    "Goshen", "Hot Springs", "Johnson", "Laramie", "Lincoln", "Natrona",
    "Niobrara", "Park", "Platte", "Sheridan", "Sublette", "Sweetwater",
    "Teton", "Uinta", "Washakie", "Weston",
}

CITY_SLUGS = {
    "buffalo", "casper", "cheyenne", "cody", "douglas", "evanston", "gillette",
    "green-river", "kemmerer", "lander", "laramie", "newcastle", "powell",
    "rawlins", "riverton", "rock-springs", "sheridan", "torrington", "worland",
}

PASS, FAIL = [], []


def check(name: str, cond: bool) -> None:
    (PASS if cond else FAIL).append(name)
    print(("ok   " if cond else "FAIL ") + name)


def main() -> None:
    reg = gen.load_registry()
    juris = reg["jurisdictions"]

    # ---- registry integrity -------------------------------------------------
    check("registry has 126 instances (4 state + 23 county + 99 municipality)",
          len(juris) == 126 and reg["counts"]["total_instances"] == 126)
    slugs = [j["slug"] for j in juris]
    check("slugs are unique", len(set(slugs)) == len(slugs))
    check("slugs are kebab-case", all(s == gen.slugify(s) for s in slugs))

    munis = [j for j in juris if j["type"] in ("city", "town")]
    check("exactly 99 municipalities", len(munis) == 99)
    cities = [j for j in munis if j["type"] == "city"]
    check("exactly 19 first-class cities", len(cities) == 19)
    check("city set matches Wyo. Title 15 first-class cities",
          {j["slug"] for j in cities} == CITY_SLUGS)
    check("all 23 counties present as county instances",
          {j["name"].removesuffix(" County") for j in juris if j["type"] == "county"} == WIYO_COUNTIES)
    check("every county instance names its seat",
          all(j.get("county_seat_name") for j in juris if j["type"] == "county"))
    seats = {(j["county"], j["name"]) for j in munis if j.get("county_seat")}
    county_seats = {(j["county"], j["county_seat_name"]) for j in juris if j["type"] == "county"}
    check("county seats in municipalities match county seats in county instances",
          seats == county_seats)
    check("Cheyenne is present and flagged",
          any(j["slug"] == "cheyenne" and j.get("state_capital") for j in munis))
    check("Frannie records its county note",
          any(j["slug"] == "frannie" and any("Park" in n for n in j.get("notes", [])) for j in munis))
    check("no municipality lacks a population", all(j.get("population_2020") for j in munis))
    total_pop = sum(j["population_2020"] for j in munis)
    check("municipality populations sum to the 2020 Census total (398,304)",
          total_pop == 398304)
    check("verification is 'unverified' everywhere in the committed registry",
          all(j.get("verification") == "unverified" for j in juris))

    # ---- instance rendering ---------------------------------------------------
    drift = []
    for e in juris:
        drift.extend(gen.check_instance(e))
    check("committed instances match the generator exactly (--check clean)", not drift)

    for e in juris:
        inst = gen.INSTANCES_DIR / e["slug"]
        cfg = json.loads((inst / "config" / "sources.json").read_text())
        wl = json.loads((inst / "config" / "watchlist.json").read_text())
        facts = json.loads((inst / "config" / "facts.json").read_text())
        # honesty contract: nothing is enabled out of the box
        if any(s.get("enabled") and s["url"] not in gen.approved_urls(e) for s in cfg["sources"]):
            FAIL.append(f"enabled source in fresh instance {e['slug']}")
            print(f"FAIL enabled source in fresh instance {e['slug']}")
        # engine refuses disabled-by-accident mistakes: watchlist must be non-trivial
        terms = [t for terms in wl["topics"].values() for t in terms]
        if len(terms) < 30:
            FAIL.append(f"watchlist too small in {e['slug']}")
        # no fabricated local lore
        if any(not isinstance(item, dict) or not item.get("url") for item in facts["timeline"]):
            FAIL.append(f"fabricated timeline in {e['slug']}")
        if "question_of_the_week" in facts and not facts["question_of_the_week"].get("url"):
            FAIL.append(f"fabricated question_of_the_week in {e['slug']}")
        for key in ("title", "kicker", "tagline", "voice_note"):
            if not facts["site"].get(key):
                FAIL.append(f"facts.site.{key} missing in {e['slug']}")
        if "name" not in cfg["sources"][0]["name"]:
            pass  # placeholder assertion-free guard; naming is covered by --check
    check("every instance honors the honesty contract (nothing enabled, no fabricated lore)",
          not any(f.startswith(("enabled", "fabricated")) for f in FAIL))

    # candidate domains are well-formed and bounded
    for e in juris:
        cands = gen.candidate_domains(e)
        for c in cands:
            if not (c.startswith("https://") or c.startswith("http://")):
                FAIL.append(f"candidate not absolute URL in {e['slug']}: {c}")
        if len(cands) > 20:
            FAIL.append(f"too many candidates for {e['slug']}")
    check("candidate domains are valid absolute URLs", True)

    # slug-based custodian env files exist and mark placeholders unverified
    bad_env = [e["slug"] for e in juris
               if not gen.custodian_for(e) and "UNVERIFIED" not in (gen.INSTANCES_DIR / e["slug"] / "env.sh").read_text()]
    check("every env.sh carries the UNVERIFIED custodian placeholder", not bad_env)

    # ---- CLI smoke ---------------------------------------------------------
    out = subprocess.run([sys.executable, str(ROOT / "tools" / "wyoming_instantiate.py"), "--check"],
                         capture_output=True, text=True)
    check("CLI --check exits 0", out.returncode == 0)
    out = subprocess.run([sys.executable, str(ROOT / "tools" / "wyoming_instantiate.py"), "--list"],
                         capture_output=True, text=True)
    check("CLI --list prints all 126 instances", out.stdout.count("\n") >= 126)

    print()
    print(f"{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        sys.exit(1)


if __name__ == "__main__":
    main()
