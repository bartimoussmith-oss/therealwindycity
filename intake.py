#!/usr/bin/env python3
"""
intake.py — transcript intake pipeline for The Real Windy City archive.
Built for the ~100-file batch. No external dependencies.

Usage:
    python3 intake.py [directory]        # default: ./uploads

Per file:
  1. md5 dedupe registry (uploads/.intake-registry.md)
  2. session title/date parsed from filename
  3. NOVELTY vs mega_file.md via 3 fixed-offset content probes (body line 3,
     chars 3000/20000/40000 x140) — 0 hits = NEW TO RECORD
  4. keyword battery (fiscal + movement + government strings), counts
  5. one markdown block per file appended to uploads/.intake-report.md
Deduped files are reported as DUPLICATE(xN) with reference to first hash.
"""
import sys, os, hashlib, re, glob
from collections import Counter

KEYWORDS = ["2%","assessment","franchise","reserves","sixth penny","6th penny","SRF",
 "lead service","rate increase","annex","DDA","BOPU","Belvoir","solar","wind farm","wind turbine","wind lease","wind energy",
 "NextEra","battery","gas plant","Flock","camera","administrative warrant","public record",
 "Food Freedom","urban farm","WY Fresh","Kniseley","Charles Miller","referendum","petition",
 "grants","historic horse racing","data center","Microsoft","landfill",
 "storm sewer interceptor","compliance","abatement","Homeless","encampment","TCE","passenger rail","Metagold","no public"]

def md5(path):
    h = hashlib.md5()
    with open(path,'rb') as f:
        for chunk in iter(lambda: f.read(1<<20), b''): h.update(chunk)
    return h.hexdigest()

def body(path):
    try:
        text = open(path, encoding='utf-8', errors='replace').read()
    except OSError:
        return ""
    lines = [l for l in text.splitlines() if l.strip() and not l.startswith('#')]
    return " ".join(lines) if lines else text

def probes(b):
    return [b[3000:3140], b[20000:20140], b[40000:40140]]

def main():
    d = sys.argv[1] if len(sys.argv)>1 else 'uploads'
    mega_path = os.path.join(d,'mega_file.md')
    mega = body(mega_path) if os.path.exists(mega_path) else None
    reg_path = os.path.join(d,'.intake-registry.md')
    rep_path = os.path.join(d,'.intake-report.md')
    seen = {}
    if os.path.exists(reg_path):
        for line in open(reg_path):
            m = re.match(r'([0-9a-f]{32})\s+(.*)', line.strip())
            if m: seen[m.group(1)] = m.group(2)
    files = sorted(f for f in glob.glob(os.path.join(d,'*.md'))
                   if os.path.basename(f) not in ('mega_file.md','.intake-report.md')
                   and '/ws-' not in f and 'index' not in os.path.basename(f).lower()
                   and 'docket' not in os.path.basename(f).lower()
                   and not os.path.basename(f).startswith(('drops','redteam','aipoison','unicode')))
    reg = open(reg_path,'a'); rep = open(rep_path,'a')
    for f in files:
        h = md5(f); name = os.path.basename(f)
        if h in seen:
            print(f"DUPLICATE  {name}  == {seen[h]}"); continue
        seen[h] = name; reg.write(f"{h}  {name}\n")
        b = body(f)
        if mega:
            hits = [mega.count(p) for p in probes(b) if len(p)>60]
            novel = "NEW TO RECORD" if hits and all(x==0 for x in hits) else \
                    ("IN COMPILATION" if hits and any(x>0 for x in hits) else "SHORT-FILE (probe n/a)")
        else:
            novel = "NO MEGA_FILE"
        kc = Counter()
        low = b.lower()
        for k in KEYWORDS: kc[k] = low.count(k.lower())
        active = ", ".join(f"{k}:{n}" for k,n in kc.most_common() if n>0) or "(none)"
        print(f"{novel:16} {name}\n    keywords: {active}")
        rep.write(f"\n## {name}\n- md5: {h}\n- novelty: {novel}\n- keywords: {active}\n- length: {len(b)} chars\n")
    reg.close(); rep.close()

if __name__ == '__main__':
    main()
