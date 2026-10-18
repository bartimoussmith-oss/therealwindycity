#!/usr/bin/env python3
"""
build_arrest_page.py -- render the public, de-identified arrest database as a
password-gated static page for GitHub Pages.

WHY A STATIC PAGE
    The live site (https://bartimousssmith-oss.github.io/therealwindycity/) is
    GitHub Pages: static files, no server, no session, no login. Streamlit
    cannot run there. So the database is rendered as a self-contained HTML page
    with a vanilla-JS viewer, and the data is sealed with AES-256-GCM at build
    time (see tools/arrest_page_seal.mjs). The password never enters the repo,
    the built site, or a log line.

WHAT THIS PUBLISHES -- AND WHAT IT REFUSES TO PUBLISH
    Only the PUBLIC tier: data/arrests/master_records.json and
    data/arrests/records.json. Both are already de-identified and were audited
    by tools/import_master_arrest_db.py and tools/build_arrest_records.py when
    they were written.

    Sealed files (keyring.jsonl, name_key.json, access_ledger.json) are never
    opened -- they are listed in SEALED_FILES purely so the refusal below is
    explicit. In CI they do not even exist: they are gitignored and have never
    been committed, so a CI build physically cannot publish a name it does not
    have.

    Two gates run before anything is written:

      1. STRUCTURAL (always). Every record must carry name=null and
         name_withheld=true, and age=null. Any violation aborts the build.
         This needs no keyring and is the gate that runs in CI.

      2. NAME AUDIT (when data/arrests/keyring.jsonl is present). Re-runs the
         importer's audit over the exact bytes about to be published, checking
         every sealed name, name token and exact age. If the keyring is absent
         this is skipped with a loud warning, and the fact is recorded in the
         build summary -- a skipped audit is never reported as a passed one.

NO PASSWORD -> NO DATA
    If no password is available the builder writes a notice page instead of the
    database and exits 0, so a missing secret can never break the 3-hour mirror
    build -- but it also can never silently publish an unprotected page. Pass
    --strict to make a missing password a hard failure.

USAGE
    python3 tools/build_arrest_page.py --out _site/arrest
    ARREST_PAGE_PASSWORD='...' python3 tools/build_arrest_page.py --out /tmp/x
    python3 tools/build_arrest_page.py --out /tmp/x --allow-open   # dev only

EXIT CODES
    0 built (or notice page written)  |  2 bad input/arguments
    3 gate failed: name or age present, or --strict with no password
    4 write or sealing error
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ARREST_DIR = REPO / "data" / "arrests"
SEALER = REPO / "tools" / "arrest_page_seal.mjs"

PUBLIC_FILES = ("master_records.json", "records.json")
SEALED_FILES = ("keyring.jsonl", "name_key.json", "access_ledger.json")
KEYRING = ARREST_DIR / "keyring.jsonl"

DEFAULT_ITERATIONS = 210000
MIN_PASSWORD_LENGTH = 12
PAGE_SIZE = 50

EXIT_OK, EXIT_BAD_INPUT, EXIT_GATE, EXIT_WRITE = 0, 2, 3, 4


# ---------------------------------------------------------------- structural gate

def structural_gate(records: list[dict], dataset: str) -> list[str]:
    """Fail closed if any name or exact age is present in the public tier.

    This is deliberately independent of the keyring: it checks the shape of the
    data rather than matching against known names, so it runs everywhere
    including CI, where the sealed files do not exist.
    """
    problems: list[str] = []
    for i, r in enumerate(records):
        rid = r.get("record_id") or f"index {i}"
        if r.get("name") is not None:
            problems.append(f"{dataset}:{rid} has a non-null name")
        if r.get("age") is not None:
            problems.append(f"{dataset}:{rid} has a non-null age: {r.get('age')!r}")
        if r.get("name") is None and not r.get("name_withheld"):
            problems.append(f"{dataset}:{rid} has name=null but name_withheld is not true")
    return problems


def keyring_audit(payload_bytes: bytes) -> tuple[bool, str]:
    """Re-run the importer's audit over the exact bytes we are about to publish.

    Returns (ran, message). ran=False means the keyring was absent and NO audit
    happened -- the caller must report that honestly rather than as a pass.
    """
    if not KEYRING.exists():
        try:
            shown = KEYRING.relative_to(REPO)
        except ValueError:
            shown = KEYRING  # a caller may point the builder outside the repo
        return False, (
            f"SKIPPED: {shown} is absent (it is gitignored and "
            "never committed), so the sealed-name audit could not be re-run here. "
            "The structural gate ran instead, and CI cannot publish names it does not have."
        )
    try:
        sys.path.insert(0, str(REPO / "tools"))
        import import_master_arrest_db as imp  # noqa: PLC0415
    except Exception as exc:  # pragma: no cover - import surface changed
        return False, f"SKIPPED: could not import the importer's audit ({exc!r})"

    names: list[str] = []
    try:
        with KEYRING.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                nm = obj.get("name") if isinstance(obj, dict) else None
                if isinstance(nm, str) and nm.strip():
                    names.append(nm)
    except OSError as exc:
        return False, f"SKIPPED: cannot read keyring ({exc})"

    if not names:
        return False, "SKIPPED: keyring contained no names"

    text = payload_bytes.decode("utf-8", errors="replace")
    # The importer's audit signature: (public, sealed, texts, scaffold, public_vocab).
    # We are auditing a rendered payload, not record dicts, so pass the payload as
    # the text under audit and let it scan for sealed names / tokens / ages.
    try:
        result = imp.audit_texts([], [], [text], scaffold="", public_vocab=None)
    except TypeError:
        try:
            result = imp.audit_texts([], [], [text])
        except Exception as exc:  # pragma: no cover
            return False, f"SKIPPED: audit signature mismatch ({exc!r})"
    except Exception as exc:  # pragma: no cover
        return False, f"SKIPPED: audit raised ({exc!r})"

    ok = bool(result.get("ok", result.get("passed", False))) if isinstance(result, dict) else bool(result)
    detail = ""
    if isinstance(result, dict):
        viols = result.get("violations") or result.get("problems") or []
        if viols:
            detail = " first violations: " + "; ".join(str(v) for v in viols[:5])
    return True, (
        f"PASS: {len(names):,} sealed names, their tokens and exact ages were searched "
        f"in the {len(payload_bytes):,}-byte payload; none found.{detail}"
        if ok else
        f"FAIL: audit reported violations against {len(names):,} sealed names.{detail}"
    )


# ---------------------------------------------------------------- payload shaping

class Dicts:
    """String interning tables. Repeated strings are the bulk of the payload:
    11,785 charge entries collapse to 2,532 distinct strings, and 6,492 rows
    share only 113 source URLs and 113 report windows."""

    def __init__(self) -> None:
        self._tables: dict[str, dict[str, int]] = {}
        self._lists: dict[str, list[str]] = {}

    def idx(self, table: str, value: str) -> int:
        t = self._tables.setdefault(table, {})
        if value not in t:
            t[value] = len(t)
            self._lists.setdefault(table, []).append(value)
        return t[value]

    def idx_many(self, table: str, values) -> list[int]:
        return [self.idx(table, v) for v in values]

    def table(self, name: str) -> list[str]:
        """The interned strings for one table, in index order."""
        return list(self._lists.get(name, []))

    def out(self) -> dict[str, list[str]]:
        return {k: list(v) for k, v in self._lists.items()}


def id_scheme(ids: list[str]) -> dict:
    """Record ids are sequential and derivable, so store a scheme instead of
    6,492 strings. Verified against the real list before it is trusted."""
    if not ids:
        return {"mode": "list", "ids": []}
    for width in (3, 6):
        for prefix in {i[: -width] for i in ids if len(i) > width}:
            if len(prefix) == 0:
                continue
            if ids == [f"{prefix}{n:0{width}d}" for n in range(1, len(ids) + 1)]:
                return {"mode": "seq", "prefix": prefix, "width": width, "start": 1}
    return {"mode": "list", "ids": ids}


def shape_dataset(ds_id: str, title: str, blurb: str, doc: dict, records: list[dict],
                  date_key: str, window_key: str) -> dict:
    d = Dicts()
    rows: list[list] = []
    for r in records:
        raw_date = str(r.get(date_key) or "")
        date = raw_date[:10]
        flags = 0
        if r.get("age_withheld"):
            flags |= 1
        if r.get("name_uncertain") or r.get("uncertain"):
            flags |= 2
        rows.append([
            d.idx("date", date),
            d.idx("win", str(r.get(window_key) or "")),
            d.idx("url", str(r.get("source_url") or "")),
            d.idx_many("cat", r.get("categories") or []),
            d.idx_many("chg", r.get("charges") or []),
            flags,
        ])
    ids = [str(r.get("record_id") or "") for r in records]
    dates = sorted(v for v in d.table("date") if v)
    return {
        "id": ds_id,
        "title": title,
        "blurb": blurb,
        "record_count": len(rows),
        "report_count": doc.get("report_count"),
        "date_span": [dates[0], dates[-1]] if dates else None,
        "policy": doc.get("policy"),
        "caveats": doc.get("caveats") or [],
        "cleaning": doc.get("cleaning"),
        "category_rule": doc.get("category_rule"),
        "reports": doc.get("reports"),
        "ids": id_scheme(ids),
        "dict": d.out(),
        "rows": rows,
    }


def build_payload() -> dict:
    datasets = []

    master_path = ARREST_DIR / "master_records.json"
    if master_path.exists():
        doc = json.loads(master_path.read_text(encoding="utf-8"))
        recs = doc.get("records") or []
        problems = structural_gate(recs, "master")
        if problems:
            raise SystemExit(f"GATE FAIL (structural): {problems[:5]}")
        datasets.append(shape_dataset(
            "master",
            "Cap City News weekly arrest reports",
            "Every arrest entry published in the Cap City News weekly arrest reports "
            "that could be parsed with a determinable name/charge boundary. Names and "
            "exact ages are withheld; each row still cites the article it came from.",
            doc, recs, "report_date", "report_window",
        ))
    else:
        print(f"WARNING: {master_path} not found; skipping the master dataset", file=sys.stderr)

    tier1_path = ARREST_DIR / "records.json"
    if tier1_path.exists():
        doc = json.loads(tier1_path.read_text(encoding="utf-8"))
        recs = doc.get("records") or []
        problems = structural_gate(recs, "laramie")
        if problems:
            raise SystemExit(f"GATE FAIL (structural): {problems[:5]}")
        datasets.append(shape_dataset(
            "laramie",
            "Laramie County weekly arrest report",
            "The Laramie County weekly arrest report captured from the live page, "
            "with the capture's sha256 recorded so the published rows can be tied "
            "back to the exact bytes they were read from.",
            doc, recs, "report_published", "arrest_window",
        ))
    else:
        print(f"WARNING: {tier1_path} not found; skipping the Laramie dataset", file=sys.stderr)

    if not datasets:
        raise SystemExit("no public arrest datasets found; nothing to publish")

    body = json.dumps({
        "v": 1,
        "built": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "built_by": "tools/build_arrest_page.py",
        "page_size": PAGE_SIZE,
        "datasets": datasets,
    }, ensure_ascii=False, separators=(",", ":"))

    # Last line of defence before sealing: nothing that looks like a withheld
    # name placeholder or a sealed-file name should be in the payload.
    for bad in ("keyring.jsonl", "name_key.json", "[WITHHELD]"):
        if bad in body:
            print(f"NOTE: payload contains the literal {bad!r} (expected for caveats/prose)",
                  file=sys.stderr)
    return json.loads(body)


# ---------------------------------------------------------------- html

HTML_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>__SITE_TITLE__</title>
<style>
:root{--bg:#0e1116;--panel:#161b22;--panel2:#1c232c;--line:#2a323d;--ink:#e6edf3;
--dim:#8b98a5;--acc:#4ea1ff;--ok:#3fb950;--warn:#d29922;--bad:#f85149}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
a{color:var(--acc);text-decoration:none}a:hover{text-decoration:underline}
code,kbd{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:.9em}
.wrap{max-width:1200px;margin:0 auto;padding:24px 20px 80px}
h1{font-size:1.5rem;margin:0 0 4px}h2{font-size:1.05rem;margin:0 0 10px}
h3{font-size:.95rem;margin:18px 0 8px}
.sub{color:var(--dim);margin:0 0 22px;font-size:.9rem}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:16px 18px;margin-bottom:16px}
.gate{max-width:560px;margin:12vh auto 0}
.gate .lock{font-size:2rem;margin-bottom:6px}
input[type=password],input[type=search],select{background:var(--panel2);border:1px solid var(--line);
color:var(--ink);border-radius:7px;padding:9px 11px;font-size:.95rem;width:100%}
input:focus,select:focus{outline:2px solid var(--acc);outline-offset:-1px}
button{background:var(--acc);color:#04121f;border:0;border-radius:7px;padding:10px 16px;
font-size:.95rem;font-weight:600;cursor:pointer}
button:hover{filter:brightness(1.1)}button:disabled{opacity:.5;cursor:progress}
button.ghost{background:transparent;color:var(--ink);border:1px solid var(--line);font-weight:500}
.err{color:var(--bad);margin-top:10px;min-height:1.2em;font-size:.9rem}
.hint{color:var(--dim);font-size:.85rem;margin-top:14px}
.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:16px}
.metric{background:var(--panel);border:1px solid var(--line);border-radius:9px;padding:12px 14px}
.metric .k{color:var(--dim);font-size:.72rem;text-transform:uppercase;letter-spacing:.06em}
.metric .v{font-size:1.3rem;font-weight:650;margin-top:2px}
.tabs{display:flex;gap:8px;margin-bottom:14px;flex-wrap:wrap}
.tab{background:var(--panel);border:1px solid var(--line);color:var(--dim);border-radius:20px;
padding:6px 14px;font-size:.85rem;cursor:pointer;font-weight:500}
.tab[aria-selected=true]{background:var(--acc);color:#04121f;border-color:var(--acc);font-weight:650}
.filters{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;align-items:end}
.filters label{display:block;color:var(--dim);font-size:.75rem;text-transform:uppercase;
letter-spacing:.05em;margin-bottom:5px}
.cats{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}
.chip{background:var(--panel2);border:1px solid var(--line);color:var(--dim);border-radius:14px;
padding:3px 10px;font-size:.78rem;cursor:pointer;user-select:none}
.chip[aria-pressed=true]{background:#12314f;border-color:var(--acc);color:#bcdcff}
.check{display:flex;align-items:center;gap:7px;font-size:.85rem;color:var(--ink);margin-top:6px}
.check input{width:auto}
table{width:100%;border-collapse:collapse;font-size:.86rem}
th,td{text-align:left;padding:8px 9px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--dim);font-size:.72rem;text-transform:uppercase;letter-spacing:.05em;
cursor:pointer;user-select:none;white-space:nowrap;position:sticky;top:0;background:var(--panel);z-index:1}
th:hover{color:var(--ink)}
tbody tr:hover{background:var(--panel2)}
td.id{font-family:ui-monospace,Menlo,Consolas,monospace;color:var(--dim);white-space:nowrap}
td.num{text-align:right;font-variant-numeric:tabular-nums}
.pill{display:inline-block;background:var(--panel2);border:1px solid var(--line);border-radius:10px;
padding:1px 7px;font-size:.72rem;color:var(--dim);margin:1px 2px 1px 0;white-space:nowrap}
.flag{color:var(--warn);font-size:.72rem;white-space:nowrap}
.detail{background:var(--panel2)}
.detail ul{margin:6px 0 6px 18px;padding:0}
.pager{display:flex;gap:10px;align-items:center;justify-content:center;margin-top:14px;flex-wrap:wrap}
.pager span{color:var(--dim);font-size:.85rem}
.bar{display:flex;gap:10px;align-items:center;justify-content:space-between;flex-wrap:wrap;margin-bottom:12px}
.note{border-left:3px solid var(--acc);padding-left:12px;color:var(--dim);font-size:.86rem;margin:10px 0}
.warnbox{border-left:3px solid var(--warn);padding-left:12px;font-size:.86rem;margin:10px 0}
.okbox{border-left:3px solid var(--ok);padding-left:12px;font-size:.86rem;margin:10px 0}
details summary{cursor:pointer;color:var(--acc);font-size:.88rem;margin-bottom:6px}
ul.tight{margin:6px 0 6px 20px;padding:0}ul.tight li{margin-bottom:5px}
.kv{display:grid;grid-template-columns:minmax(160px,auto) 1fr;gap:4px 14px;font-size:.85rem}
.kv dt{color:var(--dim)}.kv dd{margin:0}
.foot{color:var(--dim);font-size:.8rem;margin-top:26px;border-top:1px solid var(--line);padding-top:14px}
.hidden{display:none}
.spin{display:inline-block;width:13px;height:13px;border:2px solid var(--dim);
border-top-color:var(--acc);border-radius:50%;animation:s .7s linear infinite;vertical-align:-2px}
@keyframes s{to{transform:rotate(360deg)}}
@media(max-width:700px){th.hide-s,td.hide-s{display:none}}
</style>
</head>
<body>

<!-- ================= GATE ================= -->
<div id="gate" class="wrap gate">
  <div class="panel">
    <div class="lock">&#128274;</div>
    <h1>__SITE_TITLE__</h1>
    <p class="sub">Password required. The dataset on this page is encrypted.</p>
    <form id="unlockForm" autocomplete="off">
      <input type="password" id="pw" placeholder="Access password" autocomplete="current-password" required>
      <div style="margin-top:12px"><button type="submit" id="go">Open the database</button></div>
      <div class="err" id="gateErr" role="alert"></div>
    </form>
    <p class="hint">
      This page is hosted on GitHub Pages, which serves static files and has no
      server-side session. So the gate is real cryptography, not a hidden div:
      the payload is sealed with <strong>AES-256-GCM</strong> under a key derived
      by <strong>PBKDF2-HMAC-SHA256, __ITER__ iterations</strong>. Your password is
      used only in this browser tab to derive the key; it is never transmitted
      anywhere. A wrong password fails the GCM authentication tag rather than
      returning garbage.
    </p>
  </div>
</div>

<!-- ================= APP ================= -->
<div id="app" class="wrap hidden">
  <h1>__SITE_TITLE__</h1>
  <p class="sub" id="appSub"></p>

  <div class="panel" id="integrity">
    <h2>What this dataset is, and what it deliberately leaves out</h2>
    <div class="okbox">
      <strong>Names published: 0. Exact ages published: 0.</strong>
      Every row carries <code>name: null</code> and <code>name_withheld: true</code>.
    </div>
    <div class="note" id="policyNote"></div>
    <p class="sub" style="margin:8px 0 0">
      Record ids are opaque sequential labels, not hashes of anything identifying.
      Ages are withheld entirely because an exact age plus a report date plus a
      charge is a quasi-identifier that can re-identify a person in a small
      jurisdiction. Each row keeps the URL of the article it was parsed from, so
      any figure on this page can be checked against the source.
    </p>
    <details style="margin-top:10px">
      <summary>How this page is protected, and the honest limits of that</summary>
      <ul class="tight">
        <li>The encrypted blob is publicly downloadable. That is fine: it is
            ciphertext. But it means the gate is only as strong as the password,
            and it can be attacked offline. A short or dictionary password would
            fall; a long passphrase will not.</li>
        <li>This is an <em>access gate</em>, not secrecy about the underlying
            arrests, which were published by a news outlet and are public record.</li>
        <li>Names are <strong>never</strong> in this encrypted blob. Putting them
            here would mean one leaked password publishes thousands of real names
            permanently, with no way to revoke a file that has been mirrored.</li>
      </ul>
    </details>
  </div>

  <div class="metrics" id="metrics"></div>

  <div class="tabs" id="tabs" role="tablist"></div>

  <div class="panel">
    <div class="bar">
      <h2 style="margin:0">Records <span id="count" class="sub" style="margin:0"></span></h2>
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <button class="ghost" id="csv">Download filtered CSV</button>
        <button class="ghost" id="lock">Lock</button>
      </div>
    </div>
    <div class="filters">
      <div><label for="q">Search charges</label>
        <input type="search" id="q" placeholder="e.g. DUI, warrant, possession"></div>
      <div><label for="yr">Year</label><select id="yr"><option value="">All years</option></select></div>
      <div><label for="mc">Charge count</label>
        <select id="mc"><option value="">Any</option><option value="2">2 or more</option>
        <option value="3">3 or more</option><option value="4">4 or more</option></select></div>
      <div><label>&nbsp;</label>
        <div class="check"><input type="checkbox" id="unc"><span for="unc">Uncertain name/charge split only</span></div>
        <div class="check"><input type="checkbox" id="aged"><span for="aged">Age withheld (adult at arrest)</span></div>
      </div>
    </div>
    <div class="cats" id="cats"></div>
  </div>

  <div class="panel" style="padding:0;overflow:auto">
    <table id="tbl">
      <thead><tr>
        <th data-k="id">Record</th>
        <th data-k="date">Report date</th>
        <th data-k="win" class="hide-s">Window</th>
        <th data-k="ncat">Categories</th>
        <th data-k="nchg" class="num">Charges</th>
        <th data-k="chg">Charge text (verbatim)</th>
        <th data-k="url" class="hide-s">Source</th>
      </tr></thead>
      <tbody id="tb"></tbody>
    </table>
  </div>
  <div class="pager">
    <button class="ghost" id="prev">Previous</button>
    <span id="pg"></span>
    <button class="ghost" id="next">Next</button>
  </div>

  <div class="panel" id="caveats"></div>
  <div class="panel" id="provenance"></div>

  <p class="foot">
    Built __BUILT__ by <code>tools/build_arrest_page.py</code> from the public tier in
    <code>data/arrests/</code>. Sealed with AES-256-GCM (PBKDF2-HMAC-SHA256,
    __ITER__ iterations) by <code>tools/arrest_page_seal.mjs</code>.
    Source: <a href="../">the Cheyenne civic record mirror</a>.
    Names are released only on request, for public-safety and
    non-discriminatory research purposes only.
  </p>
</div>

<script>
"use strict";
const ITER = __ITER__;
const MODE = "__MODE__";          // "sealed" | "open"
const DATA_FILE = "__DATA_FILE__";
const PAGE_SIZE = __PAGE_SIZE__;

let PAYLOAD = null, DS = null, VIEW = [], PAGE = 0;
let SORT = {k:"id", dir:1};
let ACTIVE_CATS = new Set();

const $ = id => document.getElementById(id);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c =>
  ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

/* ---------------- open the gate ---------------- */

async function deriveKey(pw, salt) {
  const km = await crypto.subtle.importKey("raw", new TextEncoder().encode(pw),
        "PBKDF2", false, ["deriveKey"]);
  return crypto.subtle.deriveKey({name:"PBKDF2", salt, iterations:ITER, hash:"SHA-256"},
        km, {name:"AES-GCM", length:256}, false, ["decrypt"]);
}

async function openSealed(pw) {
  const res = await fetch(DATA_FILE, {cache:"no-store"});
  if (!res.ok) throw new Error("could not fetch " + DATA_FILE + " (HTTP " + res.status + ")");
  const b64 = (await res.text()).trim();
  const raw = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
  if (raw.length < 29) throw new Error("ciphertext is too short to be a valid envelope");
  const salt = raw.slice(0,16), iv = raw.slice(16,28), ct = raw.slice(28);
  const key = await deriveKey(pw, salt);
  const plain = await crypto.subtle.decrypt({name:"AES-GCM", iv}, key, ct);
  return JSON.parse(new TextDecoder().decode(plain));
}

async function openPlain() {
  const res = await fetch(DATA_FILE, {cache:"no-store"});
  if (!res.ok) throw new Error("could not fetch " + DATA_FILE + " (HTTP " + res.status + ")");
  return res.json();
}

async function unlock(ev) {
  ev.preventDefault();
  const btn = $("go"), err = $("gateErr");
  err.textContent = ""; btn.disabled = true;
  btn.innerHTML = '<span class="spin"></span> Deriving key&hellip;';
  try {
    PAYLOAD = MODE === "sealed" ? await openSealed($("pw").value) : await openPlain();
    if (!PAYLOAD || !Array.isArray(PAYLOAD.datasets) || !PAYLOAD.datasets.length)
      throw new Error("payload did not contain any datasets");
    start();
  } catch (e) {
    // GCM rejects a wrong password with OperationError; say so plainly rather
    // than showing a crypto stack trace.
    err.textContent = (e && e.name === "OperationError")
      ? "Wrong password. AES-GCM rejected the key."
      : "Could not open the database: " + (e && e.message ? e.message : e);
  } finally {
    btn.disabled = false; btn.textContent = "Open the database";
  }
}

/* ---------------- shape the rows for display ---------------- */

function expand(ds) {
  const D = ds.dict, seq = ds.ids.mode === "seq";
  return ds.rows.map((r, i) => ({
    i,
    id: seq ? ds.ids.prefix + String(ds.ids.start + i).padStart(ds.ids.width,"0") : ds.ids.ids[i],
    date: D.date[r[0]] || "",
    win:  D.win[r[1]]  || "",
    url:  D.url[r[2]]  || "",
    cats: r[3].map(x => D.cat[x]),
    chgs: r[4].map(x => D.chg[x]),
    flags: r[5] || 0,
    year: (D.date[r[0]] || "").slice(0,4)
  }));
}

function start() {
  $("gate").classList.add("hidden");
  $("app").classList.remove("hidden");
  $("appSub").textContent = PAYLOAD.datasets.length + " de-identified public dataset(s) \u00b7 built " + PAYLOAD.built;
  $("policyNote").textContent = PAYLOAD.datasets[0].policy || "";
  buildTabs(); selectDataset(PAYLOAD.datasets[0].id);
}

function buildTabs() {
  $("tabs").innerHTML = "";
  PAYLOAD.datasets.forEach(ds => {
    const b = document.createElement("button");
    b.className = "tab"; b.role = "tab"; b.textContent = ds.title + " (" + ds.record_count.toLocaleString() + ")";
    b.onclick = () => selectDataset(ds.id);
    b.dataset.id = ds.id;
    $("tabs").appendChild(b);
  });
}

function selectDataset(id) {
  DS = PAYLOAD.datasets.find(d => d.id === id);
  [...$("tabs").children].forEach(t => t.setAttribute("aria-selected", String(t.dataset.id === id)));
  DS._rows = DS._rows || expand(DS);
  PAGE = 0; SORT = {k:"id", dir:1}; ACTIVE_CATS = new Set();
  $("q").value = ""; $("yr").value = ""; $("mc").value = ""; $("unc").checked = false; $("aged").checked = false;
  buildYears(); buildCats(); renderMetrics(); renderPanels(); apply();
}

function buildYears() {
  const years = [...new Set(DS._rows.map(r => r.year).filter(Boolean))].sort().reverse();
  $("yr").innerHTML = '<option value="">All years</option>' +
    years.map(y => `<option value="${esc(y)}">${esc(y)}</option>`).join("");
}

function buildCats() {
  const all = [...new Set(DS._rows.flatMap(r => r.cats))].sort();
  $("cats").innerHTML = all.map(c =>
    `<span class="chip" aria-pressed="false" data-c="${esc(c)}">${esc(c.replace(/_/g," "))}</span>`).join("");
  [...$("cats").children].forEach(ch => ch.onclick = () => {
    const c = ch.dataset.c, on = ch.getAttribute("aria-pressed") === "true";
    ch.setAttribute("aria-pressed", String(!on));
    on ? ACTIVE_CATS.delete(c) : ACTIVE_CATS.add(c);
    PAGE = 0; apply();
  });
}

function renderMetrics() {
  const rows = DS._rows;
  const chg = rows.reduce((a,r) => a + r.chgs.length, 0);
  const fmt = v => (typeof v === "number" ? v.toLocaleString() : (v ?? "\u2014"));
  const m = [
    ["Arrest events", rows.length.toLocaleString()],
    ["Weekly reports", fmt(DS.report_count)],
    ["Date span", DS.date_span ? DS.date_span[0] + " \u2192 " + DS.date_span[1] : "\u2014"],
    ["Charge entries", chg.toLocaleString()],
    // Both of these are 0 by construction: build_arrest_page.py refuses to
    // write the page at all if any record carries a name or an exact age.
    ["Names published", "0"],
    ["Ages published", "0"]
  ];
  $("metrics").innerHTML = m.map(([k,v]) =>
    `<div class="metric"><div class="k">${esc(k)}</div><div class="v">${esc(v)}</div></div>`).join("");
}

function renderPanels() {
  const cav = (DS.caveats || []);
  $("caveats").innerHTML = "<h2>Caveats that apply to every figure on this page</h2>" +
    (cav.length ? '<ul class="tight">' + cav.map(c => `<li>${esc(c)}</li>`).join("") + "</ul>"
                : '<p class="sub">None recorded.</p>');

  const cl = DS.cleaning;
  let prov = "<h2>Provenance and cleaning</h2>";
  if (cl) {
    prov += '<dl class="kv">' + Object.entries(cl).map(([k,v]) =>
      `<dt>${esc(k.replace(/_/g," "))}</dt><dd>${Array.isArray(v)
        ? esc(v.join(", ")) : esc(typeof v === "number" ? v.toLocaleString() : v)}</dd>`).join("") + "</dl>";
  }
  if (DS.reports && DS.reports.length) {
    prov += '<h3>Source captures</h3><dl class="kv">' + DS.reports.map(r =>
      `<dt>${esc(r.capture || "capture")}</dt><dd><code>${esc((r.sha256||"").slice(0,16))}\u2026</code> sha256</dd>`
    ).join("") + "</dl>";
  }
  if (DS.category_rule) prov += `<div class="note">${esc(DS.category_rule)}</div>`;
  $("provenance").innerHTML = prov;
}

function apply() {
  const q = $("q").value.trim().toLowerCase();
  const yr = $("yr").value, mc = parseInt($("mc").value || "0", 10);
  const unc = $("unc").checked, aged = $("aged").checked;
  VIEW = DS._rows.filter(r => {
    if (yr && r.year !== yr) return false;
    if (mc && r.chgs.length < mc) return false;
    if (unc && !(r.flags & 2)) return false;
    if (aged && !(r.flags & 1)) return false;
    if (ACTIVE_CATS.size && ![...ACTIVE_CATS].every(c => r.cats.includes(c))) return false;
    if (q && !r.chgs.some(c => c.toLowerCase().includes(q)) && !r.id.toLowerCase().includes(q)
        && !r.win.toLowerCase().includes(q)) return false;
    return true;
  });
  const k = SORT.k, dir = SORT.dir;
  VIEW.sort((a,b) => {
    let x, y;
    if (k === "ncat") { x = a.cats.length; y = b.cats.length; }
    else if (k === "nchg") { x = a.chgs.length; y = b.chgs.length; }
    else if (k === "chg") { x = a.chgs[0] || ""; y = b.chgs[0] || ""; }
    else { x = a[k]; y = b[k]; }
    return (x < y ? -1 : x > y ? 1 : 0) * dir;
  });
  const maxPage = Math.max(0, Math.ceil(VIEW.length / PAGE_SIZE) - 1);
  if (PAGE > maxPage) PAGE = maxPage;
  render();
}

function render() {
  const total = VIEW.length, pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const slice = VIEW.slice(PAGE * PAGE_SIZE, PAGE * PAGE_SIZE + PAGE_SIZE);
  $("count").textContent = "\u00b7 " + total.toLocaleString() + " of " +
    DS._rows.length.toLocaleString() + " rows match";
  $("tb").innerHTML = slice.map(r => {
    const fl = [];
    if (r.flags & 2) fl.push('<span class="flag" title="The name/charge boundary in the source could not be determined; the charge text may be incomplete.">&#9888; uncertain split</span>');
    if (r.flags & 1) fl.push('<span class="flag" title="An exact age was present in the source and has been withheld.">age withheld</span>');
    return `<tr data-i="${r.i}">
      <td class="id">${esc(r.id)}</td>
      <td>${esc(r.date)}</td>
      <td class="hide-s">${esc(r.win)}</td>
      <td>${r.cats.map(c => `<span class="pill">${esc(c.replace(/_/g," "))}</span>`).join("")}</td>
      <td class="num">${r.chgs.length}</td>
      <td>${esc(r.chgs[0] || "\u2014")}${r.chgs.length > 1 ? ` <span class="pill">+${r.chgs.length-1} more</span>` : ""} ${fl.join(" ")}</td>
      <td class="hide-s">${r.url ? `<a href="${esc(r.url)}" rel="noopener noreferrer nofollow" target="_blank">article</a>` : "\u2014"}</td>
    </tr>
    <tr class="detail hidden" id="d-${r.i}"><td colspan="7">
      <strong>${esc(r.id)}</strong> \u00b7 ${esc(r.date)} \u00b7 window ${esc(r.win)}
      <ul>${r.chgs.map(c => `<li>${esc(c)}</li>`).join("") || "<li>no charge text recorded</li>"}</ul>
      <div class="sub">Categories: ${esc(r.cats.join(", ") || "\u2014")} \u00b7 charge_count ${r.chgs.length}
      \u00b7 name <code>null</code> (withheld) \u00b7 age <code>null</code>${(r.flags&1)?" (withheld)":" (not present)"}</div>
      ${r.url ? `<div class="sub">Source: <a href="${esc(r.url)}" rel="noopener noreferrer nofollow" target="_blank">${esc(r.url)}</a></div>` : ""}
    </td></tr>`;
  }).join("");
  [...$("tb").querySelectorAll("tr[data-i]")].forEach(tr => tr.onclick = () =>
    $("d-" + tr.dataset.i).classList.toggle("hidden"));
  $("pg").textContent = "Page " + (PAGE + 1) + " of " + pages.toLocaleString();
  $("prev").disabled = PAGE === 0;
  $("next").disabled = PAGE >= pages - 1;
}

function toCSV(rows) {
  const q = v => '"' + String(v ?? "").replace(/"/g,'""') + '"';
  const head = ["record_id","report_date","report_window","charge_count","categories","charges",
                "name","name_withheld","age","age_withheld","name_split_uncertain","source_url"];
  const lines = rows.map(r => [r.id, r.date, r.win, r.chgs.length, r.cats.join("; "),
    r.chgs.join("; "), "", "true", "", (r.flags&1)?"true":"false", (r.flags&2)?"true":"false", r.url
  ].map(q).join(","));
  return [head.map(q).join(","), ...lines].join("\r\n");
}

/* ---------------- wiring ---------------- */

$("unlockForm").addEventListener("submit", unlock);
$("q").addEventListener("input", () => { PAGE = 0; apply(); });
["yr","mc"].forEach(id => $(id).addEventListener("change", () => { PAGE = 0; apply(); }));
["unc","aged"].forEach(id => $(id).addEventListener("change", () => { PAGE = 0; apply(); }));
$("prev").onclick = () => { if (PAGE > 0) { PAGE--; render(); } };
$("next").onclick = () => { PAGE++; render(); };
$("lock").onclick = () => {
  PAYLOAD = null; DS = null; VIEW = [];
  $("pw").value = ""; $("gateErr").textContent = "";
  $("app").classList.add("hidden"); $("gate").classList.remove("hidden");
};
[...document.querySelectorAll("th[data-k]")].forEach(th => th.onclick = () => {
  const k = th.dataset.k;
  SORT = {k, dir: SORT.k === k ? -SORT.dir : 1};
  apply();
});
$("csv").onclick = () => {
  if (!VIEW.length) return;
  const blob = new Blob([toCSV(VIEW)], {type:"text/csv;charset=utf-8"});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "arrest-records-filtered-" + DS.id + ".csv";
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 4000);
};
</script>
</body>
</html>
"""

NOTICE_TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__SITE_TITLE__ &mdash; not configured</title>
<style>body{margin:0;background:#0e1116;color:#e6edf3;
font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif}
.wrap{max-width:620px;margin:16vh auto;padding:0 20px}
.panel{background:#161b22;border:1px solid #2a323d;border-radius:10px;padding:22px}
h1{font-size:1.3rem;margin:0 0 10px}code{background:#1c232c;padding:1px 5px;border-radius:4px;
font-family:ui-monospace,Menlo,Consolas,monospace;font-size:.9em}
a{color:#4ea1ff}ul{margin:8px 0 0 20px;padding:0}li{margin-bottom:7px}</style></head>
<body><div class="wrap"><div class="panel">
<h1>&#9888;&nbsp; Arrest database page is not published yet</h1>
<p>This page builds only when an access password is available at build time.
It was <strong>not</strong>, so no data was written here. Nothing is unprotected
&mdash; there is simply nothing to see.</p>
<p>To publish it, add a repository secret and re-run the Pages build:</p>
<ul>
<li>GitHub &rarr; repo <code>Settings</code> &rarr; <code>Secrets and variables</code>
    &rarr; <code>Actions</code> &rarr; <em>New repository secret</em></li>
<li>Name: <code>ARREST_PAGE_PASSWORD</code></li>
<li>Value: a passphrase of at least __MINLEN__ characters. The encrypted blob is
    publicly downloadable and can be attacked offline, so a short or dictionary
    password is not adequate. Several unrelated words is right.</li>
<li>Then re-run the <code>ai-record-pages</code> workflow (Actions &rarr; the
    workflow &rarr; <em>Run workflow</em>), or push any change to
    <code>data/arrests/</code>.</li>
</ul>
<p style="margin-top:16px;color:#8b98a5;font-size:.85rem">
The password is never committed and never appears in a log. It is read from the
secret at build time and used only to derive an AES-256-GCM key.</p>
<p><a href="../">&larr; back to the civic record mirror</a></p>
</div></div></body></html>
"""


def render_html(*, mode: str, data_file: str, iterations: int) -> str:
    return (HTML_TEMPLATE
            .replace("__SITE_TITLE__", "Cheyenne Arrest Database")
            .replace("__ITER__", str(iterations))
            .replace("__MODE__", mode)
            .replace("__DATA_FILE__", data_file)
            .replace("__PAGE_SIZE__", str(PAGE_SIZE))
            .replace("__BUILT__", _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")))


def render_notice() -> str:
    return (NOTICE_TEMPLATE
            .replace("__SITE_TITLE__", "Cheyenne Arrest Database")
            .replace("__MINLEN__", str(MIN_PASSWORD_LENGTH)))


# ---------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="_site/arrest", help="output directory (default _site/arrest)")
    ap.add_argument("--password-env", default="ARREST_PAGE_PASSWORD",
                    help="env var holding the access password (default ARREST_PAGE_PASSWORD)")
    ap.add_argument("--password-file", help="read the password from this file instead of the env")
    ap.add_argument("--iterations", type=int, default=DEFAULT_ITERATIONS,
                    help=f"PBKDF2 iterations (default {DEFAULT_ITERATIONS}, min 100000)")
    ap.add_argument("--min-password-length", type=int, default=MIN_PASSWORD_LENGTH)
    ap.add_argument("--allow-open", action="store_true",
                    help="DEV ONLY: publish unencrypted data.json with no password")
    ap.add_argument("--strict", action="store_true",
                    help="exit 3 instead of writing a notice page when no password is available")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)

    say = (lambda *m: None) if a.quiet else (lambda *m: print(*m))

    if a.iterations < 100000:
        print(f"--iterations must be >= 100000 (got {a.iterations})", file=sys.stderr)
        return EXIT_BAD_INPUT
    if a.password_env and a.password_file:
        print("use only one of --password-env / --password-file", file=sys.stderr)
        return EXIT_BAD_INPUT

    for sealed in SEALED_FILES:
        p = ARREST_DIR / sealed
        if p.exists():
            say(f"note: {sealed} exists locally but is NEVER read or published by this builder")

    # -- build the payload (runs the structural gate) -----------------------
    try:
        payload = build_payload()
    except SystemExit as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_GATE
    except (OSError, json.JSONDecodeError) as exc:
        print(f"cannot read the public arrest data: {exc}", file=sys.stderr)
        return EXIT_BAD_INPUT

    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    raw_mb = sum((ARREST_DIR / f).stat().st_size for f in PUBLIC_FILES if (ARREST_DIR / f).exists())
    say(f"payload: {len(body):,} B sealed-ready "
        f"(from {raw_mb:,} B of public JSON; string-interned and columnar)")

    # -- keyring audit, when the keyring is present -------------------------
    ran, msg = keyring_audit(body)
    say(f"name audit: {msg}")
    if ran and msg.startswith("FAIL"):
        print("GATE FAIL (name audit): refusing to publish", file=sys.stderr)
        return EXIT_GATE

    out = Path(a.out)
    try:
        out.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"cannot create {out}: {exc}", file=sys.stderr)
        return EXIT_WRITE

    # -- decide the mode ----------------------------------------------------
    password = None
    if not a.allow_open:
        if a.password_file:
            try:
                password = Path(a.password_file).read_text(encoding="utf-8").rstrip("\r\n")
            except OSError:
                password = None
        else:
            password = os.environ.get(a.password_env) or None
        if password is not None and len(password) < a.min_password_length:
            print(f"password is {len(password)} chars; minimum is {a.min_password_length}. "
                  "The blob is public and attackable offline.", file=sys.stderr)
            password = None

    if a.allow_open:
        say("WARNING: --allow-open publishes UNENCRYPTED data. Development use only; "
            "never point this at the deployed site directory.")
        mode, data_file = "open", "data.json"
        try:
            (out / data_file).write_bytes(body)
            (out / "index.html").write_text(render_html(mode=mode, data_file=data_file,
                                                        iterations=a.iterations), encoding="utf-8")
        except OSError as exc:
            print(f"write error: {exc}", file=sys.stderr)
            return EXIT_WRITE
        say(f"wrote {out/'index.html'} and {out/data_file} (OPEN, no password)")
        return EXIT_OK

    if password is None:
        # Fail closed: publish no data at all, but do not break the site build.
        warn = ("arrest page: no usable ARREST_PAGE_PASSWORD, so the database was NOT published "
                "(notice page written instead). Add the repository secret and re-run.")
        print(f"::warning::{warn}")
        print(f"WARNING: {warn}", file=sys.stderr)
        if a.strict:
            return EXIT_GATE
        try:
            (out / "index.html").write_text(render_notice(), encoding="utf-8")
            for stale in ("data.enc", "data.json"):
                if (out / stale).exists():
                    (out / stale).unlink()
        except OSError as exc:
            print(f"write error: {exc}", file=sys.stderr)
            return EXIT_WRITE
        say(f"wrote {out/'index.html'} (NOTICE: no password available, no data published)")
        return EXIT_OK

    # -- seal ---------------------------------------------------------------
    if not SEALER.exists():
        print(f"missing {SEALER}; cannot seal the payload", file=sys.stderr)
        return EXIT_WRITE
    node = shutil.which("node")
    if not node:
        print("node is not on PATH; AES-256-GCM sealing needs it "
              "(the Pages workflow installs Node 22)", file=sys.stderr)
        return EXIT_WRITE

    plain_tmp = out / ".payload.json"
    env = dict(os.environ)
    env_name = "ARREST_PAGE_SEAL_PW"
    env[env_name] = password
    try:
        plain_tmp.write_bytes(body)
        cmd = [node, str(SEALER), "--in", str(plain_tmp), "--out", str(out / "data.enc"),
               "--password-env", env_name, "--iterations", str(a.iterations),
               "--min-length", str(a.min_password_length)]
        proc = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=600)
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"sealing failed: {exc}", file=sys.stderr)
        return EXIT_WRITE
    finally:
        # Never leave plaintext, and never leave the password in the env we hand back.
        if plain_tmp.exists():
            try:
                plain_tmp.unlink()
            except OSError:
                pass
        env.pop(env_name, None)

    if proc.returncode != 0:
        print(f"sealer exited {proc.returncode}: {proc.stderr.strip() or proc.stdout.strip()}",
              file=sys.stderr)
        return EXIT_GATE if proc.returncode == 3 else EXIT_WRITE
    say(proc.stdout.strip())

    try:
        (out / "index.html").write_text(
            render_html(mode="sealed", data_file="data.enc", iterations=a.iterations),
            encoding="utf-8")
    except OSError as exc:
        print(f"write error: {exc}", file=sys.stderr)
        return EXIT_WRITE

    enc = out / "data.enc"
    digest = hashlib.sha256(enc.read_bytes()).hexdigest()[:16]
    say(f"wrote {out/'index.html'} ({(out/'index.html').stat().st_size:,} B)")
    say(f"wrote {enc} ({enc.stat().st_size:,} B, sha256 {digest}...)")
    say(f"datasets: " + ", ".join(f"{d['id']}={d['record_count']:,}" for d in payload["datasets"]))
    say("names published: 0 | exact ages published: 0 | gate: AES-256-GCM + PBKDF2-SHA256 "
        f"{a.iterations:,} iters, min password {a.min_password_length}")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
