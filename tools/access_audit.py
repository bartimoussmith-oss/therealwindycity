#!/usr/bin/env python3
"""access_audit.py - re-run the 2026-10-16 ecosystem access test.

Measures, from the live GitHub API, what an analyst (human or AI) can
actually read in the therealwindycity archive series:

  1. inventory  - file counts / sizes / extensions per archive repo, forks, stars
  2. integrity  - stratified random sample of archive files, classified as
                  TEXT (machine-readable PDF), SCANNED/NO_TEXT (needs OCR),
                  HTML_AGENDA (agenda saved as .pdf but really Granicus HTML),
                  STUB (error page / empty file), PARSE_ERR
  3. coverage   - which phrases in the transcripts repo are findable in the
                  website's "Ask the record" index (public/data/transcript-vectors.json
                  in TheReelWindyCity)

Requires: the `gh` CLI (authenticated), `pip install pypdf beautifulsoup4`.
Files are fetched through api.github.com blob endpoints, so it works where
raw.githubusercontent.com is blocked.

    python3 tools/access_audit.py inventory
    python3 tools/access_audit.py integrity --per-repo 40 --seed 42
    python3 tools/access_audit.py coverage --phrase "35-7-1046" --phrase "Musco"

Results are measurements of a sample, not a full census. Re-run with a larger
--per-repo for tighter numbers.
"""
import argparse, collections, io, json, logging, os, random, re, subprocess, sys
from concurrent.futures import ThreadPoolExecutor

ORG = "therealwindycity"
ARCHIVES = ["cheyenne-archives-2008-2013", "cheyenne-archives-2014-2017",
            "cheyenne-archives-2018-2021", "cheyenne-archives-2022",
            "cheyenne-archives-2023-2024", "cheyenne-archives-2025-2026"]
CACHE = os.environ.get("ACCESS_AUDIT_CACHE", "/tmp/access_audit_cache")


def gh_json(path):
    out = subprocess.run(["gh", "api", path], capture_output=True, check=True)
    return json.loads(out.stdout)


def tree(repo):
    br = gh_json(f"repos/{ORG}/{repo}")["default_branch"]
    return gh_json(f"repos/{ORG}/{repo}/git/trees/{br}?recursive=1")


def blob(repo, sha):
    os.makedirs(CACHE, exist_ok=True)
    fn = os.path.join(CACHE, sha)
    if not os.path.exists(fn) or os.path.getsize(fn) == 0:
        with open(fn, "wb") as fh:
            subprocess.run(["gh", "api", "-H", "Accept: application/vnd.github.raw",
                            f"repos/{ORG}/{repo}/git/blobs/{sha}"],
                           stdout=fh, stderr=subprocess.DEVNULL)
    return open(fn, "rb").read()


def classify(data):
    head = data[:400].lower()
    if data.startswith(b"%PDF"):
        from pypdf import PdfReader
        try:
            rd = PdfReader(io.BytesIO(data))
            txt = "".join((rd.pages[i].extract_text() or "") for i in range(min(len(rd.pages), 3)))
        except Exception:
            return "PARSE_ERR"
        n = sum(c.isalnum() for c in txt)
        return "TEXT" if n > 200 else "SCANNED/NO_TEXT"
    if b"<html" in head or b"<script" in head:
        from bs4 import BeautifulSoup
        t = BeautifulSoup(data, "html.parser").get_text(" ", strip=True)
        hits = len(re.findall(r"call to order|roll call|ordinance no|resolution no|"
                              r"consent agenda|public hearing|adjourn", t, re.I))
        if hits >= 3 and "Juneteenth" not in t:
            return "HTML_AGENDA"
        return "STUB" if len(t) < 300 else "HTML_OTHER"
    return "STUB" if len(data.strip()) < 300 else "OTHER"


def cmd_inventory(_):
    total = 0
    for repo in ARCHIVES + ["The-Real-Windy-City-", "TheReelWindyCity"]:
        t = tree(repo)
        files = [x for x in t["tree"] if x["type"] == "blob"]
        ext = collections.Counter(x["path"].rsplit(".", 1)[-1].lower() for x in files if "." in x["path"])
        meta = gh_json(f"repos/{ORG}/{repo}")
        size = sum(x.get("size", 0) for x in files) / 1e9
        if repo in ARCHIVES:
            total += ext["pdf"] + ext["bin"]
        print(f"{repo:30s} files={len(files):5d} {size:5.2f} GB forks={meta['forks_count']} "
              f"stars={meta['stargazers_count']} top={ext.most_common(4)}")
    print(f"archive documents (pdf+bin): {total}")


def cmd_integrity(a):
    random.seed(a.seed)
    jobs = []
    for repo in ARCHIVES:
        files = [x for x in tree(repo)["tree"] if x["type"] == "blob"
                 and not x["path"].endswith(".md") and x.get("size", 0) < 20_000_000]
        jobs += [(repo, f) for f in random.sample(files, min(a.per_repo, len(files)))]
    with ThreadPoolExecutor(8) as ex:
        datas = list(ex.map(lambda j: blob(j[0], j[1]["sha"]), jobs))
    by = collections.defaultdict(collections.Counter)
    rows = []
    for (repo, f), d in zip(jobs, datas):
        k = classify(d)
        by[repo][k] += 1
        rows.append({"repo": repo, "path": f["path"], "size": f["size"], "class": k})
    tot = collections.Counter()
    for repo in ARCHIVES:
        print(f"{repo:30s} {dict(by[repo])}")
        tot.update(by[repo])
    n = sum(tot.values())
    print("TOTAL", {k: f"{v} ({100*v/n:.0f}%)" for k, v in tot.most_common()}, "n =", n)
    if a.out:
        json.dump(rows, open(a.out, "w"), indent=1)
        print("wrote", a.out)


def cmd_coverage(a):
    idx = json.loads(subprocess.run(
        ["gh", "api", "-H", "Accept: application/vnd.github.raw",
         f"repos/{ORG}/TheReelWindyCity/contents/public/data/transcript-vectors.json"],
        capture_output=True, check=True).stdout)
    items = idx["items"]
    kinds = collections.Counter(i["kind"] for i in items)
    print(f"site index: {len(items)} items {dict(kinds)} generated {idx.get('generatedAt')}")
    for p in a.phrase:
        hit = sum(1 for i in items if re.search(re.escape(p), i["text"], re.I))
        print(f"  {p!r:32s} items containing it in site index: {hit}")


def main():
    logging.disable(logging.CRITICAL)
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("inventory")
    i = sp.add_parser("integrity")
    i.add_argument("--per-repo", type=int, default=40)
    i.add_argument("--seed", type=int, default=42)
    i.add_argument("--out")
    c = sp.add_parser("coverage")
    c.add_argument("--phrase", action="append", default=[])
    a = ap.parse_args()
    {"inventory": cmd_inventory, "integrity": cmd_integrity, "coverage": cmd_coverage}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
