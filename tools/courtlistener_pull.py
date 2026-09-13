#!/usr/bin/env python3
"""
THE REAL WINDY CITY — COURTLISTENER / WYOMING CASE LAW PULL
Two modes:
1. BULK CSV (free, no rate limit) — sync from s3://com-courtlistener-storage/bulk/
2. API search (needs token) — search Wyoming Supreme Court opinions

Bulk files are PostgreSQL COPY CSVs: courts, dockets, opinion_clusters, opinions (largest), citations
We filter to court=wy (Wyoming Supreme Court) + any opinion citing Title 15 or Cheyenne annexation etc.

Output: cities/cheyenne/law/case_law/{cite}/ {opinion.txt, metadata.json}
+ bulk/ folder + wy_cases.jsonl

Run in Colab:
  !pip install -q courtlistener-api-client boto3
  exec(open('tools/courtlistener_pull.py').read())

Config at top. Token via env COURTLISTENER_API_TOKEN or Colab Secret.
"""
import os, re, json, time, pathlib, csv
from pathlib import Path

OUT_ROOT = "/content/drive/MyDrive/TheRealWindyCity/cheyenne/law/case_law"
if not os.path.isdir("/content/drive"):
    OUT_ROOT = str(Path(__file__).resolve().parent.parent / "cities/cheyenne/law/case_law")

API_BASE = "https://www.courtlistener.com/api/rest/v4"
DELAY = 1.0
UA = "TheRealWindyCity/1.0 (+civic-archive)"

# Wyoming queries relevant to municipal
QUERIES = [
    "Cheyenne annexation",
    "15-1-402",
    "15-1-407",
    "15-1-505",
    "zoning Cheyenne",
    "DDA Cheyenne",
    "BOPU",
    "municipal home rule Wyoming",
    "referendum Wyoming",
]

def get_token():
    tok = os.environ.get("COURTLISTENER_API_TOKEN")
    if tok: return tok
    try:
        from google.colab import userdata
        return userdata.get("COURTLISTENER_API_TOKEN")
    except Exception:
        return None

def api_search(query, token, max_pages=3):
    import urllib.request, urllib.parse
    headers = {"User-Agent": UA}
    if token:
        headers["Authorization"] = f"Token {token}"
    results = []
    url = f"{API_BASE}/search/?q={urllib.parse.quote(query)}&type=o&court=wy&order_by=score+desc"
    for _ in range(max_pages):
        time.sleep(DELAY)
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.loads(r.read().decode("utf-8","replace"))
            results.extend(data.get("results", []))
            print(f"  {query} -> {len(data.get('results',[]))} results (total {data.get('count')})")
            url = data.get("next")
            if not url:
                break
        except Exception as e:
            print(f"  !! API search {query} failed {e}")
            break
    return results

def save_case(case, out_root):
    # case from search API has cluster + opinion snippet
    cid = case.get("cluster_id") or case.get("id") or "unknown"
    cite = (case.get("citation") or [str(cid)])[0] if isinstance(case.get("citation"), list) else case.get("citation") or str(cid)
    safe_cite = re.sub(r"[^A-Za-z0-9._-]+","_", str(cite))[:120]
    folder = Path(out_root) / safe_cite
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "metadata.json").write_text(json.dumps(case, indent=1), encoding="utf-8")
    # try to fetch full opinion if URL available
    if case.get("absolute_url"):
        try:
            import urllib.request
            full_url = f"https://www.courtlistener.com{case['absolute_url']}"
            req = urllib.request.Request(full_url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                html = r.read().decode("utf-8","replace")
            (folder / "page.html").write_text(html, encoding="utf-8")
        except Exception as e:
            print(f"    !! fetch full {cite} {e}")

def bulk_mode(out_root):
    """
    Bulk mode instructions — requires aws cli or boto3, large files.
    For Colab, we just document and attempt small sync via boto3 if available.
    """
    print("Bulk mode: to sync full bulk data, run:")
    print("  aws s3 sync s3://com-courtlistener-storage/bulk/ ./bulk --no-sign-request --exclude '*' --include '*court*' --include '*opinion_cluster*' --include '*opinion*'")
    print("  Then filter where court_id='wy' (Wyoming Supreme Court)")
    # Attempt boto3 list
    try:
        import boto3
        from botocore import UNSIGNED
        from botocore.config import Config
        s3 = boto3.client('s3', config=Config(signature_version=UNSIGNED))
        resp = s3.list_objects_v2(Bucket='com-courtlistener-storage', Prefix='bulk/', MaxKeys=20)
        print(f"  Bulk bucket listing: {len(resp.get('Contents',[]))} objects")
        for obj in resp.get('Contents',[])[:10]:
            print(f"    {obj['Key']} {obj['Size']//1024//1024}MB")
    except Exception as e:
        print(f"  boto3 bulk list failed {e} — install boto3 or use aws cli locally")

def main():
    out_root = Path(OUT_ROOT)
    if str(out_root).startswith("/content/drive") and not os.path.isdir("/content/drive/MyDrive"):
        try:
            from google.colab import drive
            drive.mount("/content/drive")
        except Exception:
            out_root = Path(__file__).resolve().parent.parent / "cities/cheyenne/law/case_law"
    out_root.mkdir(parents=True, exist_ok=True)
    print(f"OUT_ROOT={out_root}")
    token = get_token()
    print(f"Token present: {bool(token)} (free account 5/min, 50/hr, 125/day as of May 2026)")

    # bulk instructions
    bulk_mode(out_root)

    # API search for Wyoming municipal relevance
    if token:
        all_results = []
        for q in QUERIES:
            res = api_search(q, token, max_pages=2)
            for case in res:
                save_case(case, out_root)
            all_results.extend(res)
            time.sleep(2)
        # write consolidated jsonl
        (out_root / "wy_cases.jsonl").write_text("\n".join(json.dumps(r) for r in all_results), encoding="utf-8")
        print(f"\nDone: {len(all_results)} cases -> {out_root}")
    else:
        print("No token — skipping API search. Set COURTLISTENER_API_TOKEN env or Colab Secret to enable.")
        print("You can still use bulk CSVs offline — see bulk_mode()")

if __name__ == "__main__":
    main()
