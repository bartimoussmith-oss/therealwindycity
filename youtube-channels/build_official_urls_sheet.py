#!/usr/bin/env python3
"""Build the Wyoming official-URL spreadsheet (CSV) from the researched data.

Sources: wyoming/registry.json (county, population), core_channel_discovery.csv
(YouTube channels), and town_websites.csv (official websites found by search).
"""
import csv, json
from pathlib import Path

HERE = Path(__file__).parent
REPO = HERE.parent
reg = json.loads((REPO / "wyoming/registry.json").read_text(encoding="utf-8"))
by_name = {j["name"]: j for j in reg["jurisdictions"]}

# Core bodies: website URLs taken from search results (see notes column)
core_sites = {
    "Wyoming Legislature": ("https://wyoleg.gov", "wyoleg.gov (Legislature site)"),
    "Cheyenne City Council": ("https://www.cheyennecity.org", "cheyennecity.org (city government page)"),
    "Laramie County Commissioners": ("https://www.laramiecountywy.gov", "laramiecountywy.gov social-channels page"),
    "Casper City Council": ("https://www.casperwy.gov", "casperwy.gov (Wikipedia, Wikidata)"),
    "Laramie City Council": ("https://www.cityoflaramie.org", "cityoflaramie.org council page"),
    "Sheridan City Council": ("https://ci.sheridan.co.us", "ci.sheridan.co.us agenda center"),
    "Gillette City Council": ("https://www.gillettewy.gov", "gillettewy.gov"),
    "Jackson Town Council": ("https://www.jacksonwy.gov", "jacksonwy.gov government page"),
    "Teton County Commissioners": ("https://www.tetoncountywy.gov", "tetoncountywy.gov Board of County Commissioners page"),
    "Sweetwater County Commissioners": ("https://www.sweetwatercountywy.gov", "sweetwatercountywy.gov (Wikipedia)"),
    "Natrona County Commissioners": ("https://www.natronacounty-wy.gov", "natronacounty-wy.gov"),
    "Wyoming Supreme Court": ("https://www.courts.state.wy.us", "courts.state.wy.us live-broadcast page"),
    "Wyoming Department of Transportation": ("https://www.dot.state.wy.us", "dot.state.wy.us"),
}

# Towns: official website as found by search (Wikipedia/Wikidata infobox,
# town-hall directories, or the town's own pages). Conflicts noted.
town_sites = {}
for r in csv.DictReader(open(HERE / "town_websites.csv", encoding="utf-8")):
    town_sites[r["town"]] = (r["official_website"], r["source"], r["status"])

rows = []
# Core bodies
for name in core_sites:
    site, src = core_sites[name]
    rows.append({"entity": name, "type": "state/county/city body", "county": "", "population_2020": "",
                 "official_website": site, "website_source": src,
                 "youtube_channel": "", "website_status": "found" if site else "not yet looked up"})
# Enrich core rows with YouTube from discovery sheet
yt = {r["entity"]: r for r in csv.DictReader(open(HERE / "core_channel_discovery.csv", encoding="utf-8"))}
for r in rows:
    if r["entity"] in yt and yt[r["entity"]]["channel_url"]:
        r["youtube_channel"] = yt[r["entity"]]["channel_url"]

# Towns (every town from the user list)
from wy_channel_harvest import WY_TOWNS
for t in WY_TOWNS:
    j = by_name.get(t, {})
    if t in town_sites:
        site, src, status = town_sites[t]
    else:
        site, src, status = "", "", "not yet looked up"
    rows.append({"entity": t, "type": j.get("type", "town"), "county": j.get("county", ""),
                 "population_2020": j.get("population_2020", ""),
                 "official_website": site, "website_source": src,
                 "youtube_channel": "", "website_status": status})

fields = ["entity", "type", "county", "population_2020", "official_website",
          "website_source", "youtube_channel", "website_status"]
out = HERE / "wyoming_official_urls.csv"
with out.open("w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=fields)
    w.writeheader(); w.writerows(rows)
print(len(rows), "rows ->", out)
