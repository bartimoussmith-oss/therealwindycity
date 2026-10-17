#!/usr/bin/env python3
"""ai_record_extract.py - pull text out of every file in the six archive repos.

For each therealwindycity/cheyenne-archives-* repo: shallow-clone it, write
tree_<repo>.json (path, blob sha, size), extract every file to
<text-dir>/<sha>.json, then delete the clone (keeps peak disk to one repo).

  PDF  -> one string per page (PyMuPDF text layer)
  HTML -> visible text (agendas saved from Granicus under a .pdf name)
  else -> recorded as empty/other so the generator can label it honestly

    python3 tools/ai_record_extract.py --text /tmp/text --trees /tmp/trees
"""
import argparse, json, logging, os, shutil, subprocess, sys

REPOS = ["cheyenne-archives-2008-2013", "cheyenne-archives-2014-2017", "cheyenne-archives-2018-2021",
         "cheyenne-archives-2022", "cheyenne-archives-2023-2024", "cheyenne-archives-2025-2026"]


def ls_tree(d):
    out = subprocess.run(["git", "-C", d, "ls-tree", "-r", "-l", "-z", "HEAD"], capture_output=True, check=True).stdout
    tree = []
    for rec in out.split(b"\0"):
        if not rec: continue
        meta, path = rec.split(b"\t", 1)
        mode, typ, sha, size = meta.split()
        tree.append({"path": path.decode("utf-8", "surrogateescape"), "type": typ.decode(), "sha": sha.decode(),
                     "size": int(size) if size != b"-" else 0})
    return {"tree": tree, "truncated": False}


def extract(data):
    import pymupdf
    from bs4 import BeautifulSoup
    if data.startswith(b"%PDF"):
        try:
            doc = pymupdf.open(stream=data, filetype="pdf")
            return {"kind": "pdf", "pages": [pg.get_text() for pg in doc]}
        except Exception as e:
            return {"kind": "pdf-unreadable", "pages": [], "error": str(e)[:200]}
    if not data:
        return {"kind": "empty", "pages": []}
    head = data[:600].lower()
    if b"<html" in head or b"<script" in head or b"<!doctype" in head:
        soup = BeautifulSoup(data, "html.parser")
        for t in soup(["script", "style", "noscript"]): t.decompose()
        return {"kind": "html", "pages": [soup.get_text("\n", strip=True)]}
    return {"kind": "other", "pages": [data[:20000].decode("utf8", "ignore")]}


def main():
    logging.disable(logging.CRITICAL)
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", required=True)
    ap.add_argument("--trees", required=True)
    ap.add_argument("--work", default="/tmp/ai_record_clones")
    a = ap.parse_args()
    import pymupdf
    pymupdf.TOOLS.mupdf_display_errors(False)
    os.makedirs(a.text, exist_ok=True); os.makedirs(a.trees, exist_ok=True); os.makedirs(a.work, exist_ok=True)
    for repo in REPOS:
        d = os.path.join(a.work, repo)
        if os.path.exists(d): shutil.rmtree(d)
        subprocess.run(["git", "clone", "-q", "--depth", "1", f"https://github.com/therealwindycity/{repo}.git", d], check=True)
        tree = ls_tree(d)
        json.dump(tree, open(os.path.join(a.trees, f"tree_{repo}.json"), "w"))
        n = 0
        for x in tree["tree"]:
            if x["type"] != "blob" or x["path"].endswith(".md"): continue
            out = os.path.join(a.text, x["sha"] + ".json")
            if os.path.exists(out): continue
            try:
                data = open(os.path.join(d, x["path"]), "rb").read()
            except OSError:
                data = b""
            rec = {"repo": repo, "path": x["path"], "size": x["size"], "sha": x["sha"]}
            rec.update(extract(data))
            json.dump(rec, open(out, "w"))
            n += 1
        shutil.rmtree(d)
        print(f"{repo}: {len(tree['tree'])} files, {n} newly extracted", flush=True)


if __name__ == "__main__":
    sys.exit(main())
