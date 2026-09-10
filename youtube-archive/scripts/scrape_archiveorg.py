#!/usr/bin/env python3
"""
scrape_archiveorg.py — Build a catalog of the 'cochwy-*' collection on archive.org.

Someone (or an automated job) has been mirroring City of Cheyenne meeting videos
— City Council, Finance Committee, Public Services Committee, Planning Commission,
work sessions — to the Internet Archive. This script lists every item via the
archive.org advancedsearch API.

Outputs (in the project root):
  catalog_archiveorg.csv
  catalog_archiveorg.json

File-level download URLs are resolved at download time by download_archiveorg.py
via https://archive.org/metadata/<identifier>.
"""
import csv, json, urllib.parse, urllib.request

QUERY = "identifier:cochwy-*"
FIELDS = ["identifier", "title", "date", "year", "creator", "mediatype", "description"]
PAGE = 1000
HEADERS = {"User-Agent": "Mozilla/5.0 CheyenneArchiveResearch/1.0"}


def search(offset=0):
    params = [("q", QUERY), ("rows", PAGE), ("page", 0), ("output", "json")]
    # advancedsearch pagination uses 'page' param; keep simple: single big page
    params = {"q": QUERY, "fl[]": FIELDS, "rows": 2000, "page": 1, "output": "json"}
    url = "https://archive.org/advancedsearch.php?" + urllib.parse.urlencode(params, doseq=True)
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.load(resp)


def main():
    print("Querying archive.org advancedsearch ...")
    data = search()
    docs = data["response"]["docs"]
    total = data["response"]["numFound"]
    print(f"Found {total} items, retrieved {len(docs)}.")
    docs.sort(key=lambda d: d.get("date", ""))
    with open("catalog_archiveorg.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["identifier", "title", "date", "year",
                                          "creator", "mediatype", "item_url", "metadata_url"])
        w.writeheader()
        for d in docs:
            ident = d.get("identifier", "")
            w.writerow({
                "identifier": ident,
                "title": d.get("title", ""),
                "date": d.get("date", ""),
                "year": d.get("year", ""),
                "creator": d.get("creator", ""),
                "mediatype": d.get("mediatype", ""),
                "item_url": f"https://archive.org/details/{ident}",
                "metadata_url": f"https://archive.org/metadata/{ident}",
            })
    with open("catalog_archiveorg.json", "w", encoding="utf-8") as f:
        json.dump(docs, f, indent=2)
    print("Wrote catalog_archiveorg.csv and catalog_archiveorg.json")


if __name__ == "__main__":
    main()
