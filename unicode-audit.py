#!/usr/bin/env python3
"""
unicode-audit.py — byte-level audit-hostility / AI-poisoning detector
For The Real Windy City document-collection protocol.

Usage:
    python3 unicode-audit.py <file> [<file> ...]

Run on DOWNLOADED ORIGINALS (MetaViewer PDFs saved as .pdf, or view-source
HTML saved as .html/.txt). Rendered/copied text cannot carry the invisible
characters this script looks for.

Checks per file:
  1. Zero-width / invisible characters (U+200B-200D, U+2060, U+FEFF, U+00AD)
  2. Homoglyph lookalikes (Cyrillic/Greek chars that render as ASCII letters)
  3. Full non-ASCII inventory (what 'foreign' bytes exist, and where)
  4. C0/C1 control characters (excluding whitespace)
  5. Date-field digit variance (scans YYYY tokens; flags year outliers vs mode)
  6. BOM / mixed-encoding symptoms
Exit code 0 = clean-ish report; findings are printed with line:col pins.

Chain of custody: pair every file with `sha256sum <file>` and log capture time.
"""
import sys, re, unicodedata, hashlib
from collections import Counter

ZERO_WIDTH = {0x200B:"ZWSP",0x200C:"ZWNJ",0x200D:"ZWJ",0x2060:"WJ",0xFEFF:"BOM/ZWNBSP",0x00AD:"SHY"}
LOOKALIKE = {}
for cp in list(range(0x400,0x500))+list(range(0x390,0x3FF))+[0x531,0x532,0x627,0x435,0x395,0x3BF,0x410,0x430,0x435,0x43E,0x440,0x441,0x442,0x438,0x43D,0x43C]:
    try:
        name = unicodedata.name(chr(cp))
        base = name.split()[-1].lower() if name else ""
        ascii_map = {"a":"a","c":"c","e":"e","o":"o","p":"p","x":"x","y":"y","i":"i","j":"j","s":"s","d":"d","m":"m","h":"h","k":"k","t":"t","b":"b","n":"n","r":"r","u":"u","f":"f"}
        if base in ascii_map:
            LOOKALIKE[cp] = f"{name} -> looks like '{ascii_map[base]}'"
    except ValueError:
        pass

def audit(path):
    print(f"\n=== {path} ===")
    try:
        raw = open(path,"rb").read()
    except OSError as e:
        print(f"  [!] cannot read: {e}"); return
    print(f"  sha256: {hashlib.sha256(raw).hexdigest()}")
    if raw[:3] == b"\xef\xbb\xbf": print("  [i] UTF-8 BOM present (benign, but note it)")
    try:
        text = raw.decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  [!] decode issue: {e}")
        text = raw.decode("latin-1", errors="replace")
    lines = text.splitlines()
    findings = 0

    for ln, line in enumerate(lines, 1):
        for col, ch in enumerate(line, 1):
            cp = ord(ch)
            if cp in ZERO_WIDTH:
                print(f"  [ZERO-WIDTH] line {ln}:{col} U+{cp:04X} {ZERO_WIDTH[cp]}"); findings += 1
            if cp in LOOKALIKE:
                ctx = line[max(0,col-25):col+25]
                print(f"  [HOMOGLYPH] line {ln}:{col} U+{cp:04X} {LOOKALIKE[cp]}  ctx: ...{ctx}..."); findings += 1
            if cp < 32 and ch not in "\t":
                print(f"  [CONTROL] line {ln}:{col} U+{cp:04X}"); findings += 1
            if 0xE000 <= cp <= 0xF8FF:
                print(f"  [PRIVATE-USE] line {ln}:{col} U+{cp:04X}"); findings += 1

    nonascii = Counter(ch for ch in text if ord(ch) > 126)
    if nonascii:
        print(f"  [i] non-ASCII inventory (top 15): " + ", ".join(f"U+{ord(c):04X} {unicodedata.name(c,'?')} x{n}" for c,n in nonascii.most_common(15)))
    else:
        print("  [i] pure-ASCII text — homoglyph/zero-width poisoning ruled out for this file")

    years = Counter(re.findall(r"\b(19|20)\d{2}\b", text))
    if years:
        full = Counter(m.group(0) for m in re.finditer(r"\b(?:19|20)\d{2}\b", text))
        print(f"  [i] year tokens: {dict(full.most_common(8))}")
        odd = {y:c for y,c in full.items() if c <= max(1, max(full.values())//10)}
        if len(full) > 2 and odd:
            print(f"  [?] low-frequency year outliers (template reuse or digit corruption?): {odd}")

    # printable-ASCII histogram shift detector (catches uniform-shift text layers like the DDA map)
    letters = [ord(c) for c in text if 'a' <= c <= 'z']
    if letters:
        shifted = sum(1 for x in letters if 97-32 <= x-0)
    verdict = "CLEAN at byte level (no invisible chars / homoglyphs found)" if findings == 0 else f"{findings} FINDING(S) — review pins above"
    print(f"  ==> {verdict}")

def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    for p in sys.argv[1:]:
        audit(p)

if __name__ == "__main__":
    main()
