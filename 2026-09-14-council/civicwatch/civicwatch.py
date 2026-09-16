#!/usr/bin/env python3
"""
CivicWatch — deterministic municipal-record pipeline for Cheyenne (Granicus view_id=5).

Zero-generative. Every fact it emits is a verbatim span with (doc, page/line) provenance.

Subcommands:
  crawl   --since 2026-01-01 [--until ...] [--kinds council,psc,finance]   -> downloads agendas, minutes, attachments
  index                                                                   -> extracts text, loads SQLite + FTS5
  extract                                                                 -> votes, speakers, notice dates, contiguity, acreage, PC votes, $$
  search  "phrase"  [--limit 20]                                          -> FTS5 with doc/page provenance
  graph   [--out graph.html]                                              -> entity co-occurrence graph (applicants/agents/owners/items)
  brief   --event 1441 | --clip 1093                                      -> rule-based red-team brief for one meeting
  watch                                                                   -> diff live publisher page vs. DB; report new meetings/attachments

Storage: ./data/{raw,text}/  ./data/civic.db
"""
import argparse, hashlib, json, os, re, sqlite3, sys, time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, parse_qs, urlparse

import requests
from bs4 import BeautifulSoup

BASE = "https://cheyenne.granicus.com/"
PUB = BASE + "ViewPublisher.php?view_id=5"
UA = {"User-Agent": "Mozilla/5.0 (CivicWatch; public-records research)"}
ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"; RAW = DATA / "raw"; TXT = DATA / "text"
for p in (RAW, TXT): p.mkdir(parents=True, exist_ok=True)
DB = DATA / "civic.db"

KIND_MAP = {"council": "City Council", "psc": "Public Services", "finance": "Finance", "special": "Special"}

# ----------------------------------------------------------------------------- db
SCHEMA = """
CREATE TABLE IF NOT EXISTS meetings(id INTEGER PRIMARY KEY, kind TEXT, date TEXT, clip_id INTEGER, event_id INTEGER,
  agenda_url TEXT, minutes_url TEXT, UNIQUE(clip_id,event_id));
CREATE TABLE IF NOT EXISTS docs(id INTEGER PRIMARY KEY, meeting_id INTEGER, role TEXT, meta_id INTEGER, item_no TEXT,
  item_title TEXT, url TEXT, path TEXT, sha1 TEXT, pages INTEGER, words INTEGER, UNIQUE(url));
CREATE TABLE IF NOT EXISTS pages(id INTEGER PRIMARY KEY, doc_id INTEGER, page INTEGER, text TEXT);
CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts USING fts5(text, content='pages', content_rowid='id', tokenize='porter unicode61');
CREATE TRIGGER IF NOT EXISTS pages_ai AFTER INSERT ON pages BEGIN
  INSERT INTO pages_fts(rowid,text) VALUES (new.id,new.text); END;
CREATE TABLE IF NOT EXISTS facts(id INTEGER PRIMARY KEY, doc_id INTEGER, page INTEGER, kind TEXT, key TEXT, value TEXT, span TEXT);
CREATE INDEX IF NOT EXISTS facts_k ON facts(kind,key);
CREATE TABLE IF NOT EXISTS items(id INTEGER PRIMARY KEY, meeting_id INTEGER, item_no TEXT, title TEXT, action TEXT, sponsor TEXT, consent INTEGER);
"""
def db():
    c = sqlite3.connect(DB); c.executescript(SCHEMA); return c

def get(url, binary=False, retries=3):
    for i in range(retries):
        try:
            r = requests.get(url, headers=UA, timeout=90); r.raise_for_status()
            return r.content if binary else r.text
        except Exception as e:
            if i == retries - 1: raise
            time.sleep(2 * (i + 1))

# ----------------------------------------------------------------------------- crawl
def parse_publisher(html):
    s = BeautifulSoup(html, "lxml"); out = []
    for tr in s.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 3: continue
        name = tds[0].get_text(" ", strip=True)
        dtxt = tds[1].get_text(" ", strip=True).replace("\xa0", " ")
        m = re.search(r"([A-Z][a-z]{2})\s+(\d{1,2}),\s+(\d{4})", dtxt)
        if not m: continue
        date = datetime.strptime(" ".join(m.groups()), "%b %d %Y").strftime("%Y-%m-%d")
        links = {a.get_text(strip=True): urljoin(BASE, a["href"]) for a in tr.find_all("a", href=True) if not a["href"].startswith("javascript")}
        q = {}
        for u in links.values():
            q.update({k: v[0] for k, v in parse_qs(urlparse(u).query).items()})
        out.append(dict(kind=name, date=date, clip_id=int(q.get("clip_id", 0) or 0), event_id=int(q.get("event_id", 0) or 0),
                        agenda_url=links.get("Agenda"), minutes_url=links.get("Minutes")))
    return out

def agenda_html_url(m):
    if m["clip_id"]: return f"{BASE}GeneratedAgendaViewer.php?view_id=5&clip_id={m['clip_id']}"
    return f"{BASE}GeneratedAgendaViewer.php?view_id=5&event_id={m['event_id']}"

ITEM_RE = re.compile(r"^\s*(\d{1,2}|[a-z])\s*[\.\)]\s*(.*)$")
def parse_agenda(html):
    """Walk the generated agenda in document order: each <table> is an item; MetaViewer links that follow attach to the last item."""
    s = BeautifulSoup(html, "lxml"); items = []; cur = None; parent_no = ""
    for el in s.body.descendants if s.body else []:
        if getattr(el, "name", None) == "table":
            rows = [r for r in el.get_text("\n", strip=True).split("\n") if r.strip()]
            if not rows: continue
            m = ITEM_RE.match(rows[0])
            if not m: continue
            no = m.group(1); rest = " ".join(rows[1:]) if len(rows) > 1 else (m.group(2) or "")
            if no.isdigit(): parent_no = no
            else: no = f"{parent_no}{no}"
            title = rest; action = ""
            am = re.search(r"ACTION:\s*(.*)", title)
            if am: action = am.group(1).strip(); title = title[:am.start()].strip()
            sp = re.search(r"\((SPONSOR\s*[–-]\s*[^)]+|[A-Z ]+COMMITTEE)\)", title)
            consent = 1 if "[CA]" in title else 0
            cur = dict(item_no=no, title=title.replace("[CA]", "").strip(), action=action, sponsor=(sp.group(1) if sp else ""), consent=consent, metas=[])
            items.append(cur)
        elif getattr(el, "name", None) == "a" and el.get("href") and "meta_id" in el["href"] and cur is not None:
            mm = re.search(r"meta_id=(\d+)", el["href"]); mid = int(mm.group(1))
            if mid not in cur["metas"]: cur["metas"].append(mid)
    return items

def save(url, dest):
    if dest.exists() and dest.stat().st_size > 0: return dest
    b = get(url, binary=True)
    if not b.startswith(b"%PDF-"): raise ValueError("not a PDF (item has no attachment)")
    dest.write_bytes(b); return dest

def cmd_crawl(a):
    c = db(); pubs = parse_publisher(get(PUB))
    want = [m for m in pubs if m["date"] >= a.since and (not a.until or m["date"] <= a.until)]
    if a.kinds:
        ks = [KIND_MAP.get(k, k) for k in a.kinds.split(",")]
        want = [m for m in want if any(k.lower() in m["kind"].lower() for k in ks)]
    print(f"{len(want)} meetings in range")
    for m in want:
        c.execute("INSERT OR IGNORE INTO meetings(kind,date,clip_id,event_id,agenda_url,minutes_url) VALUES(?,?,?,?,?,?)",
                  (m["kind"], m["date"], m["clip_id"], m["event_id"], m["agenda_url"], m["minutes_url"]))
        mid = c.execute("SELECT id FROM meetings WHERE clip_id=? AND event_id=?", (m["clip_id"], m["event_id"])).fetchone()[0]
        tag = f"{m['date']}_{(m['clip_id'] or m['event_id'])}"
        mdir = RAW / tag; mdir.mkdir(exist_ok=True)
        # agenda html
        try:
            ah = get(agenda_html_url(m)); (mdir / "agenda.html").write_text(ah)
            items = parse_agenda(ah)
            c.execute("DELETE FROM items WHERE meeting_id=?", (mid,))
            for it in items:
                c.execute("INSERT INTO items(meeting_id,item_no,title,action,sponsor,consent) VALUES(?,?,?,?,?,?)",
                          (mid, it["item_no"], it["title"], it["action"], it["sponsor"], it["consent"]))
                for meta in it["metas"]:
                    key = "clip_id" if m["clip_id"] else "event_id"
                    url = f"{BASE}MetaViewer.php?view_id=5&{key}={m['clip_id'] or m['event_id']}&meta_id={meta}"
                    p = mdir / f"{meta}.pdf"
                    done = c.execute("SELECT words FROM docs WHERE url=?", (url,)).fetchone()
                    if done and done[0] is not None and (TXT / f"{c.execute('SELECT id FROM docs WHERE url=?', (url,)).fetchone()[0]}.txt").exists(): continue
                    try: save(url, p)
                    except Exception as e: print("  attach fail", meta, e); continue
                    c.execute("INSERT OR IGNORE INTO docs(meeting_id,role,meta_id,item_no,item_title,url,path,sha1) VALUES(?,?,?,?,?,?,?,?)",
                              (mid, "attachment", meta, it["item_no"], it["title"][:200], url, str(p), hashlib.sha1(p.read_bytes()).hexdigest()))
                    index_one(c, c.execute("SELECT id FROM docs WHERE url=?", (url,)).fetchone()[0], p)
        except Exception as e:
            print("  agenda fail", tag, e)
        if m["minutes_url"]:
            p = mdir / "minutes.pdf"
            try:
                save(m["minutes_url"], p)
                c.execute("INSERT OR IGNORE INTO docs(meeting_id,role,meta_id,item_no,item_title,url,path,sha1) VALUES(?,?,?,?,?,?,?,?)",
                          (mid, "minutes", None, "", "MINUTES", m["minutes_url"], str(p), hashlib.sha1(p.read_bytes()).hexdigest()))
                index_one(c, c.execute("SELECT id FROM docs WHERE url=?", (m["minutes_url"],)).fetchone()[0], p)
            except Exception as e: print("  minutes fail", tag, e)
        c.commit(); print(" ", tag, m["kind"], "items:", len(items) if 'items' in dir() else 0)
    print("done")

# ----------------------------------------------------------------------------- index
def _pdf_pages_inproc(path):
    import pypdf
    try: r = pypdf.PdfReader(path)
    except Exception as e: return []
    return [(i + 1, (pg.extract_text() or "")) for i, pg in enumerate(r.pages)]

PDF_MEM_MB = int(os.environ.get("CW_PDF_MEM_MB", "700")); PDF_TIMEOUT = int(os.environ.get("CW_PDF_TIMEOUT", "600"))
def pdf_pages(path):
    """pypdf in a memory/time-capped child. A pathological PDF (huge inline images, decompression bombs) then fails
    cleanly -> 0 words -> picked up by ocr.py, instead of taking the whole box down. Output identical to in-process."""
    import subprocess, json as _j, sys as _s
    code = ("import resource,sys,json,civicwatch as cw;resource.setrlimit(resource.RLIMIT_AS,(%d<<20,)*2);"
            "print(json.dumps(cw._pdf_pages_inproc(sys.argv[1])))") % PDF_MEM_MB
    try:
        r = subprocess.run([_s.executable, "-c", code, str(path)], capture_output=True, text=True, timeout=PDF_TIMEOUT, cwd=str(ROOT))
        if r.returncode == 0 and r.stdout.strip(): return [tuple(x) for x in _j.loads(r.stdout)]
        print(f"  pdf_pages capped/failed rc={r.returncode} {Path(path).name}: {r.stderr.strip().splitlines()[-1][:120] if r.stderr.strip() else ''}", flush=True)
    except subprocess.TimeoutExpired: print(f"  pdf_pages timeout {Path(path).name}", flush=True)
    return []

def index_one(c, did, path):
    pgs = pdf_pages(path); words = 0
    c.execute("DELETE FROM pages WHERE doc_id=?", (did,))
    for n, t in pgs:
        words += len(t.split()); c.execute("INSERT INTO pages(doc_id,page,text) VALUES(?,?,?)", (did, n, t))
    c.execute("UPDATE docs SET pages=?,words=? WHERE id=?", (len(pgs), words, did))
    (TXT / f"{did}.txt").write_text("\n\f".join(t for _, t in pgs)); c.commit()
    return len(pgs), words

def cmd_index(a):
    c = db()
    for did, path in c.execute("SELECT id,path FROM docs WHERE pages IS NULL OR pages=0").fetchall():
        pgs = pdf_pages(path); words = 0
        c.execute("DELETE FROM pages WHERE doc_id=?", (did,))
        for n, t in pgs:
            words += len(t.split())
            c.execute("INSERT INTO pages(doc_id,page,text) VALUES(?,?,?)", (did, n, t))
        c.execute("UPDATE docs SET pages=?,words=? WHERE id=?", (len(pgs), words, did))
        (TXT / f"{did}.txt").write_text("\n\f".join(t for _, t in pgs))
        c.commit(); print(f"doc {did}: {len(pgs)}p {words}w {'** SCANNED/EMPTY **' if pgs and words < 20 else ''}")

# ----------------------------------------------------------------------------- extract (deterministic patterns)
PATTERNS = {
 "contiguity":   re.compile(r"(\d{1,3}\.\d{1,2})\s*%\s*contiguous", re.I),
 "acreage":      re.compile(r"(?:roughly|about|approximately|of)\s+([\d,]+\.\d{1,2}|[\d,]{2,})\s+acres", re.I),
 "notice_mailed":re.compile(r"certified mail(?:ing)?\s+was\s+(?:made|sent)[^.]*?on\s+([A-Z][a-z]+ \d{1,2}, \d{4})", re.I),
 "notice_deadline":re.compile(r"Twenty \(20\) business days[^.]*?is\s+([A-Z][a-z]+ \d{1,2}, \d{4})", re.I),
 "notice_receipt":re.compile(r"earliest confirm(?:ation|ed)\s+(?:of\s+)?(?:delivery|receipt)\s+was\s+(?:dated\s+)?([A-Z][a-z]+ \d{1,2}, \d{4})", re.I),
 "pc_vote":      re.compile(r"Planning Commission[^.]{0,120}?voted\s+(\d\s*[-–to]+\s*\d)[^.]*?(approve|deny|against|recommend)", re.I),
 "pc_recommend": re.compile(r"(?:Commission|Planning Commission)\s+recommend(?:s|ed)?\s+(?:the Governing Body\s+)?(approval|denial|deny)", re.I),
 "staff_rec":    re.compile(r"Staff\s+(?:does\s+)?recommends?\s+(approval|denial)", re.I),
 "criteria_fail":re.compile(r"(?:does not|largely does not|not) (?:comply|meet)[^.]{0,80}?criteri(?:on|a)\s+([\d, and]+)", re.I),
 "applicant":    re.compile(r"APPLICANT:\s*([^\n]+)"),
 "agent":        re.compile(r"AGENT:\s*([^\n]+)"),
 "owner":        re.compile(r"OWNERS?:\s*([^\n]+)"),
 "preparer":     re.compile(r"PREPARED BY:\s*([^\n]+)"),
 "file_no":      re.compile(r"\b(PUDC-\d{2}-\d{1,4})\b"),
 "dollar":       re.compile(r"not to exceed\s+\$\s?([\d,]+(?:\.\d{2})?)", re.I),
 "gf_reserves":  re.compile(r"\$([\d,]+)\s+from General Fund reserves", re.I),
 "views":        re.compile(r"received\s+(\d+)\s+views and\s+(no|\d+)\s+comments", re.I),
 "public_comment":re.compile(r"Staff has received\s+(no|one|\d+)\s+(?:new\s+)?inquir", re.I),
 "postponed":    re.compile(r"POSTPONED FROM ([A-Z]+ \d{1,2}, \d{4})", re.I),
 "flood":        re.compile(r"([^.\n]{20,}\b(?:flood ?plain|flood zones?)\b[^.\n]{10,}\.)", re.I),
 "holding_zone": re.compile(r"([^.]*holding zone[^.]*\.)", re.I),
 "verbal_use":   re.compile(r"([^.]*indicated verbally[^.]*\.)", re.I),
 "landowner_determined": re.compile(r"([^.]*landowner has determined[^.]*\.)", re.I),
 "vote":         re.compile(r"Voting\s+[“\"]?(yes|no)[”\"]?\s*[–-]\s*([^.]+?)\.", re.I),
 "motion_result":re.compile(r"Motion(?: to [^.]+?)?\s+(carried|failed)\.", re.I),
 "speakers":     re.compile(r"Public comments? (?:was|were) made by:\s*([^.]+?)\.", re.I),
 "point_of_order":re.compile(r"([^.]*point(?:s)? of order[^.]*\.)", re.I),
 "year_mismatch":re.compile(r"([A-Z][a-z]+ \d{1,2}, (20\d\d))"),
}
def cmd_extract(a):
    c = db(); c.execute("DELETE FROM facts")
    for did, page, text in c.execute("SELECT doc_id,page,text FROM pages").fetchall():
        for kind, rx in PATTERNS.items():
            for m in rx.finditer(text):
                span = text[max(0, m.start() - 80): m.end() + 80].replace("\n", " ")
                val = m.group(1).strip() if m.groups() else m.group(0)
                key = (m.group(2).strip() if len(m.groups()) > 1 else "")
                c.execute("INSERT INTO facts(doc_id,page,kind,key,value,span) VALUES(?,?,?,?,?,?)", (did, page, kind, key, val[:300], span[:400]))
    c.commit()
    n = c.execute("SELECT COUNT(*) FROM facts").fetchone()[0]; print("facts:", n)
    for k, cnt in c.execute("SELECT kind,COUNT(*) FROM facts GROUP BY kind ORDER BY 2 DESC"): print(f"  {k:22s} {cnt}")

# ----------------------------------------------------------------------------- search
def cmd_search(a):
    c = db()
    q = """SELECT d.id,d.path,m.date,d.item_no,d.item_title,p.page,snippet(pages_fts,0,'[[',']]','…',18)
           FROM pages_fts JOIN pages p ON p.id=pages_fts.rowid JOIN docs d ON d.id=p.doc_id JOIN meetings m ON m.id=d.meeting_id
           WHERE pages_fts MATCH ? ORDER BY rank LIMIT ?"""
    qry = a.query if any(ch in a.query for ch in '"*()') or ' AND ' in a.query or ' OR ' in a.query else '"' + a.query.replace('"', '') + '"'
    for r in c.execute(q, (qry, a.limit)):
        print(f"[{r[2]} item {r[3]} doc{r[0]} p{r[5]}] {r[4][:70]}\n    {r[6]}\n")

# ----------------------------------------------------------------------------- graph
def cmd_graph(a):
    import networkx as nx
    c = db(); G = nx.Graph()
    rows = c.execute("""SELECT d.id,m.date,d.item_no,d.item_title,f.kind,f.value FROM facts f JOIN docs d ON d.id=f.doc_id JOIN meetings m ON m.id=d.meeting_id
                        WHERE f.kind IN ('applicant','agent','owner','file_no','preparer')""").fetchall()
    by_doc = {}
    for did, date, no, title, kind, val in rows:
        by_doc.setdefault(did, {"label": f"{date} #{no}", "title": title, "ents": set()})["ents"].add((kind, re.sub(r"\s+", " ", val)[:60]))
    for did, d in by_doc.items():
        G.add_node(d["label"], type="item", title=d["title"])
        for kind, val in d["ents"]:
            G.add_node(val, type=kind); G.add_edge(d["label"], val)
    deg = sorted(((n, G.degree(n)) for n, dat in G.nodes(data=True) if dat["type"] != "item"), key=lambda x: -x[1])
    print("Top entities by # of agenda items:")
    for n, k in deg[:25]: print(f"  {k:3d}  {G.nodes[n]['type']:9s} {n}")
    nodes = [{"id": n, "group": dat["type"], "title": dat.get("title", "")} for n, dat in G.nodes(data=True)]
    links = [{"source": u, "target": v} for u, v in G.edges()]
    html = GRAPH_HTML.replace("__DATA__", json.dumps({"nodes": nodes, "links": links}))
    Path(a.out).write_text(html); print("wrote", a.out)

GRAPH_HTML = """<!doctype html><meta charset=utf-8><title>CivicWatch entity graph</title>
<style>body{margin:0;font:12px system-ui;background:#111;color:#ddd}svg{width:100vw;height:100vh}text{fill:#ddd;pointer-events:none}
.legend{position:fixed;top:8px;left:8px;background:#0008;padding:6px 10px;border-radius:6px}</style>
<div class=legend>drag nodes · scroll to zoom · <b>circle</b>=agenda item, <b>square</b>=entity</div><svg></svg>
<script>
const data=__DATA__;const col={item:'#4ea1ff',applicant:'#ff7f0e',agent:'#2ca02c',owner:'#d62728',file_no:'#9467bd',preparer:'#8c564b'};
const svg=document.querySelector('svg'),W=innerWidth,H=innerHeight,NS='http://www.w3.org/2000/svg';
const g=document.createElementNS(NS,'g');svg.appendChild(g);
const nodes=data.nodes.map(n=>({...n,x:W/2+(Math.random()-.5)*W*.8,y:H/2+(Math.random()-.5)*H*.8,vx:0,vy:0}));
const idx=Object.fromEntries(nodes.map(n=>[n.id,n]));const links=data.links.map(l=>({s:idx[l.source],t:idx[l.target]}));
const deg={};links.forEach(l=>{deg[l.s.id]=(deg[l.s.id]||0)+1;deg[l.t.id]=(deg[l.t.id]||0)+1});
const L=links.map(()=>{const e=document.createElementNS(NS,'line');e.setAttribute('stroke','#555');g.appendChild(e);return e});
const N=nodes.map(n=>{const isItem=n.group==='item';const e=document.createElementNS(NS,isItem?'circle':'rect');const r=4+Math.sqrt(deg[n.id]||1)*2;
 if(isItem)e.setAttribute('r',r);else{e.setAttribute('width',2*r);e.setAttribute('height',2*r)}e.setAttribute('fill',col[n.group]||'#999');
 const t=document.createElementNS(NS,'title');t.textContent=n.id+(n.title?'\\n'+n.title:'');e.appendChild(t);
 const lab=document.createElementNS(NS,'text');lab.textContent=(deg[n.id]||0)>=2||!isItem?n.id.slice(0,28):'';lab.setAttribute('font-size',isItem?9:11);
 g.appendChild(e);g.appendChild(lab);n.el=e;n.lab=lab;n.r=r;
 e.onmousedown=ev=>{n.fixed=true;const mv=m=>{n.x=(m.clientX-tx)/sc;n.y=(m.clientY-ty)/sc};const up=()=>{removeEventListener('mousemove',mv);removeEventListener('mouseup',up);n.fixed=false};addEventListener('mousemove',mv);addEventListener('mouseup',up)};
 return e});
let tx=0,ty=0,sc=1;svg.onwheel=e=>{e.preventDefault();const k=e.deltaY<0?1.1:0.9;sc*=k;tx=e.clientX-(e.clientX-tx)*k;ty=e.clientY-(e.clientY-ty)*k};
function tick(){for(const a of nodes)for(const b of nodes){if(a===b)continue;let dx=a.x-b.x,dy=a.y-b.y,d2=dx*dx+dy*dy+0.01,f=1200/d2;a.vx+=dx*f;a.vy+=dy*f}
 for(const l of links){let dx=l.t.x-l.s.x,dy=l.t.y-l.s.y,d=Math.sqrt(dx*dx+dy*dy)||1,f=(d-60)*0.01;l.s.vx+=dx/d*f;l.s.vy+=dy/d*f;l.t.vx-=dx/d*f;l.t.vy-=dy/d*f}
 for(const n of nodes){if(!n.fixed){n.vx+=(W/2-n.x)*0.002;n.vy+=(H/2-n.y)*0.002;n.x+=n.vx*=0.85;n.y+=n.vy*=0.85}
  if(n.el.tagName==='circle'){n.el.setAttribute('cx',n.x);n.el.setAttribute('cy',n.y)}else{n.el.setAttribute('x',n.x-n.r);n.el.setAttribute('y',n.y-n.r)}
  n.lab.setAttribute('x',n.x+n.r+2);n.lab.setAttribute('y',n.y+4)}
 links.forEach((l,i)=>{L[i].setAttribute('x1',l.s.x);L[i].setAttribute('y1',l.s.y);L[i].setAttribute('x2',l.t.x);L[i].setAttribute('y2',l.t.y)});
 g.setAttribute('transform',`translate(${tx},${ty}) scale(${sc})`);requestAnimationFrame(tick)}tick();
</script>"""

# ----------------------------------------------------------------------------- brief (rule engine)
RULES = [
 # (name, severity, test(facts_by_kind, item) -> message or None)
 ("PC_DENIED_STAFF_APPROVE", "HIGH", lambda F, it: "Planning Commission recommended DENIAL but staff recommends approval" if
     any("den" in (v.lower()) for v in F.get("pc_recommend", [])) and any("approv" in v.lower() for v in F.get("staff_rec", [])) else None),
 ("PC_UNANIMOUS_DENY", "HIGH", lambda F, it: f"Planning Commission vote {F['pc_vote'][0]} to deny — Council overrule required" if
     F.get("pc_vote") and re.search(r"6\s*[-–]\s*0|5\s*[-–]\s*0|7\s*[-–]\s*0", F["pc_vote"][0]) else None),
 ("STAFF_DENY", "HIGH", lambda F, it: "City staff recommends DENIAL" if any("den" in v.lower() for v in F.get("staff_rec", [])) else None),
 ("CRITERIA_FAIL", "HIGH", lambda F, it: f"Staff analysis: fails review criteria {', '.join(sorted(set(F['criteria_fail'])))}" if F.get("criteria_fail") else None),
 ("NOTICE_LATE_RECEIPT", "MED", lambda F, it: notice_check(F)),
 ("LOW_CONTIGUITY", "MED", lambda F, it: f"Contiguity only {F['contiguity'][0]}% (statutory floor is adjacency; <35% is a flag-lot pattern)" if
     F.get("contiguity") and float(F["contiguity"][0]) < 35 else None),
 ("HOLDING_ZONE", "MED", lambda F, it: "Staff describes assigned zone as a 'holding zone' — placeholder for follow-on rezone" if F.get("holding_zone") else None),
 ("VERBAL_USE_ONLY", "MED", lambda F, it: "End use disclosed only verbally, not on application: " + F["verbal_use"][0][:160] if F.get("verbal_use") else None),
 ("LANDOWNER_DETERMINES", "MED", lambda F, it: "Statutory welfare finding attributed to the landowner, not the governing body" if F.get("landowner_determined") else None),
 ("FLOOD", "LOW", lambda F, it: "Floodplain referenced in staff analysis: " + F["flood"][0][:160] if F.get("flood") else None),
 ("STALE_REPORT", "MED", lambda F, it: f"Postponed from {F['postponed'][0]}; check whether staff report was updated" if F.get("postponed") else None),
 ("NO_PUBLIC_COMMENT_HIGH_VIEWS", "LOW", lambda F, it: f"'No comments' claimed with {F['views'][0]} page views" if
     F.get("views") and int(F["views"][0]) >= 100 else None),
 ("BIG_MONEY", "LOW", lambda F, it: f"Not-to-exceed ${F['dollar'][0]}" if F.get("dollar") and float(F["dollar"][0].replace(',', '')) >= 250000 else None),
 ("GF_RESERVES", "MED", lambda F, it: "General Fund reserve draws: $" + ", $".join(F["gf_reserves"][:8]) if F.get("gf_reserves") else None),
 ("CONSENT_NONROUTINE", "LOW", lambda F, it: "Filed on CONSENT agenda but touches FLUM/overrule/gaming/reserves" if it and it["consent"] and
     re.search(r"overrul|future land use|gaming|re-?appropriat|climate", it["title"], re.I) else None),
]
def notice_check(F):
    try:
        d = datetime.strptime(F["notice_deadline"][0], "%B %d, %Y"); r = datetime.strptime(F["notice_receipt"][0], "%B %d, %Y")
        if r > d: return f"Notice: deadline {d.date()} but earliest confirmed receipt {r.date()} (mailed {F.get('notice_mailed', ['?'])[0]}). Statute keys on mailing — use as record-quality point, not as void."
    except Exception: return None
def cmd_brief(a):
    c = db()
    if a.event: mid = c.execute("SELECT id FROM meetings WHERE event_id=?", (a.event,)).fetchone()
    else: mid = c.execute("SELECT id FROM meetings WHERE clip_id=?", (a.clip,)).fetchone()
    if not mid: sys.exit("meeting not crawled")
    mid = mid[0]
    m = c.execute("SELECT kind,date FROM meetings WHERE id=?", (mid,)).fetchone()
    out = [f"# CivicWatch brief — {m[0]} {m[1]}\n", "Deterministic rule hits only. Every line cites doc id + page; verify the span before quoting.\n"]
    items = {r[0]: dict(item_no=r[0], title=r[1], action=r[2], sponsor=r[3], consent=r[4]) for r in
             c.execute("SELECT item_no,title,action,sponsor,consent FROM items WHERE meeting_id=?", (mid,))}
    docs = c.execute("SELECT id,item_no,item_title,path,pages,words FROM docs WHERE meeting_id=? AND role='attachment' ORDER BY CAST(item_no AS INT),item_no", (mid,)).fetchall()
    hits_total = 0; sponsor_count = {}
    for it in items.values():
        s = re.sub(r"SPONSOR\s*[–-]\s*", "", it["sponsor"]); sponsor_count[s] = sponsor_count.get(s, 0) + 1
    for did, no, title, path, pages, words in docs:
        F = {}
        for kind, val, page, span in c.execute("SELECT kind,value,page,span FROM facts WHERE doc_id=?", (did,)):
            F.setdefault(kind, []).append(val); F.setdefault(kind + "__loc", []).append((page, span))
        yrs = [int(y) for y in re.findall(r", (20\d\d)", " ".join(F.get("year_mismatch", [])))]
        if yrs and (max(yrs) - min(yrs)) >= 1 and min(yrs) < 2026: F["year_note"] = [f"document mixes years {sorted(set(yrs))}"]
        it = items.get(no)
        hits = []
        for name, sev, fn in RULES:
            try: msg = fn(F, it)
            except Exception: msg = None
            if msg: hits.append((sev, name, msg))
        if F.get("year_note"): hits.append(("LOW", "YEAR_MIX", F["year_note"][0]))
        if not hits and words and words > 20: continue
        hits_total += len(hits)
        out.append(f"\n## Item {no} — {title[:110]}  \n*doc {did} · {pages}p · {words}w{'  · ⚠ no extractable text (scanned?)' if words is not None and words < 20 else ''}*")
        if it and it["sponsor"]: out.append(f"Sponsor: {it['sponsor']}  ·  Action: {it['action']}  ·  Consent: {'yes' if it['consent'] else 'no'}")
        for kind in ("file_no", "applicant", "agent", "owner", "acreage", "contiguity", "pc_vote", "pc_recommend", "staff_rec"):
            if F.get(kind): out.append(f"- {kind}: {'; '.join(dict.fromkeys(F[kind]))[:200]}")
        for sev, name, msg in sorted(hits, key=lambda h: {"HIGH": 0, "MED": 1, "LOW": 2}[h[0]]):
            out.append(f"- **[{sev}] {name}** — {msg}")
        # provenance for top facts
        for kind in ("pc_recommend", "staff_rec", "criteria_fail", "notice_receipt", "contiguity", "holding_zone", "verbal_use", "landowner_determined"):
            for page, span in F.get(kind + "__loc", [])[:1]: out.append(f"    > p{page}: …{span[:220]}…")
    out.insert(2, f"\n**Sponsorship concentration:** " + ", ".join(f"{k or '(committee)'}: {v}" for k, v in sorted(sponsor_count.items(), key=lambda x: -x[1])[:5]) + f"  \n**Rule hits:** {hits_total} across {len(docs)} attachments\n")
    text = "\n".join(out); Path(a.out).write_text(text); print(text[:4000]); print(f"\n… wrote {a.out}")

# ----------------------------------------------------------------------------- votes (from minutes)
ITEM_HDR = re.compile(r"^\s*(?:\[CA\]\s*)?(ORDINANCE|RESOLUTION|Public Hearing|Consideration|Contract|Agreement|Lease|Grant|Appointment|Bid)[^\n]*", re.I)
def parse_minutes(text):
    """Split minutes into item blocks; extract result, dissenters, public speakers, points of order."""
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"(?<![.:])\n(?!\s*\n)(?!\s*(?:\[CA\]|ORDINANCE|RESOLUTION|PUBLIC HEARING|Public Hearing))", " ", text)  # unwrap soft line breaks
    blocks = re.split(r"\n(?=\s*(?:\[CA\]\s*)?(?:ORDINANCE|RESOLUTION|PUBLIC HEARING|Public Hearing)\b)", text)
    out = []
    for b in blocks:
        head = b.strip().split("\n")[0][:220]
        res = [m.group(0) for m in re.finditer(r"Motion(?: to [^.]{0,60})? (?:carried|failed)\.", b)]
        no = [m.group(1) for m in re.finditer(r"with the exception of ((?:(?:Mr|Dr|Ms|Mrs)\. [A-Z][a-z]+(?:,? and |, )?)+) voting [“\"]?no", b)]
        no += [m.group(1) for m in re.finditer(r"Voting [“\"]?no[”\"]? – all members[^.]*?exception of ((?:(?:Mr|Dr|Ms|Mrs)\. [A-Z][a-z]+(?:,? and |, )?)+) voting [“\"]?yes", b)]
        yes_all = bool(re.search(r"Voting [“\"]?yes[”\"]? – all members of the governing body\s*(?:present)?\s*\.", b))
        failed_all = bool(re.search(r"Voting [“\"]?no[”\"]? – all members", b))
        spk = re.findall(r"Public comments? (?:was|were) made by:\s*([^.]+?)\.", b)
        poo = re.findall(r"During comments made by ([A-Z][a-zA-Z]+ [A-Z][a-zA-Z]+)[^.]*point(?:s)? of order", b)
        post = re.findall(r"(?:postpone|refer)[^.]*?(?:report|until)[^.]*?([A-Z][a-z]+ \d{1,2}, \d{4})", b)
        if res or no or spk:
            out.append(dict(item=head, results=res, dissent=no, unanimous=(yes_all and not no) or failed_all, speakers=spk, points_of_order=poo, postponed_to=post))
    return out

def cmd_votes(a):
    c = db(); q = "SELECT m.date,d.id FROM docs d JOIN meetings m ON m.id=d.meeting_id WHERE d.role='minutes'"
    if a.date: q += f" AND m.date='{a.date}'"
    rows = []
    for date, did in c.execute(q + " ORDER BY m.date").fetchall():
        text = "\n".join(t for (t,) in c.execute("SELECT text FROM pages WHERE doc_id=? ORDER BY page", (did,)))
        for v in parse_minutes(text):
            if a.grep and not re.search(a.grep, v["item"], re.I): continue
            rows.append((date, did, v))
    tally = {}
    for date, did, v in rows:
        print(f"[{date} doc{did}] {v['item'][:120]}")
        for r in v["results"]: print("    ", r)
        if v["dissent"]: print("     NO:", "; ".join(v["dissent"]))
        elif v["unanimous"]: print("     unanimous")
        if v["speakers"]: print("     speakers:", v["speakers"][0][:200])
        if v["points_of_order"]: print("     point-of-order vs:", ", ".join(v["points_of_order"]))
        if v["postponed_to"]: print("     postponed/referred to:", v["postponed_to"][0])
        for d in v["dissent"]:
            for n in re.findall(r"(?:Mr\.|Dr\.|Ms\.|Mrs\.) [A-Z][a-z]+", d): tally[n] = tally.get(n, 0) + 1
    if tally: print("\nDissent tally:", dict(sorted(tally.items(), key=lambda x: -x[1])))

# ----------------------------------------------------------------------------- diff (same item across meetings)
def cmd_diff(a):
    """For each attachment in meeting A, find same PUDC file_no in earlier meetings and report identical vs changed packets."""
    c = db()
    mid = c.execute("SELECT id,date FROM meetings WHERE event_id=? OR clip_id=?", (a.event or -1, a.clip or -1)).fetchone()
    if not mid: sys.exit("meeting not crawled")
    mid, date = mid
    for did, no, title, sha in c.execute("SELECT id,item_no,item_title,sha1 FROM docs WHERE meeting_id=? AND role='attachment'", (mid,)):
        fnos = [r[0] for r in c.execute("SELECT DISTINCT value FROM facts WHERE doc_id=? AND kind='file_no'", (did,))]
        if not fnos: continue
        prior = c.execute(f"""SELECT DISTINCT m.date,d.id,d.item_no,d.sha1,d.words FROM facts f JOIN docs d ON d.id=f.doc_id JOIN meetings m ON m.id=d.meeting_id
                              WHERE f.kind='file_no' AND f.value IN ({','.join('?'*len(fnos))}) AND m.date<? AND d.role='attachment' ORDER BY m.date""", (*fnos, date)).fetchall()
        if not prior: continue
        print(f"\n{date} item {no} — {title[:80]}  [{', '.join(fnos)}]")
        for pd, pid, pno, psha, pw in prior:
            tag = "IDENTICAL PACKET" if psha == sha else f"changed ({pw} words vs current)"
            print(f"    {pd} item {pno} doc{pid}: {tag}")

# ----------------------------------------------------------------------------- watch
def cmd_watch(a):
    c = db(); pubs = parse_publisher(get(PUB)); new = []
    for m in pubs:
        if not c.execute("SELECT 1 FROM meetings WHERE clip_id=? AND event_id=?", (m["clip_id"], m["event_id"])).fetchone(): new.append(m)
    print(f"{len(new)} meetings not in DB"); 
    for m in new[:20]: print(" ", m["date"], m["kind"], m["agenda_url"])
    # attachment diff for upcoming events already crawled
    for mid, eid, date in c.execute("SELECT id,event_id,date FROM meetings WHERE event_id>0 AND date>=date('now','-2 day')"):
        try: items = parse_agenda(get(f"{BASE}GeneratedAgendaViewer.php?view_id=5&event_id={eid}"))
        except Exception: continue
        have = {r[0] for r in c.execute("SELECT meta_id FROM docs WHERE meeting_id=?", (mid,))}
        fresh = [(it["item_no"], meta) for it in items for meta in it["metas"] if meta not in have]
        if fresh: print(f"  {date} event {eid}: {len(fresh)} NEW attachments (substitutes/amendments?) -> {fresh[:10]}")

# ----------------------------------------------------------------------------- main
if __name__ == "__main__":
    ap = argparse.ArgumentParser(); sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("crawl"); p.add_argument("--since", default="2026-01-01"); p.add_argument("--until"); p.add_argument("--kinds")
    sp.add_parser("index"); sp.add_parser("extract"); sp.add_parser("watch")
    p = sp.add_parser("search"); p.add_argument("query"); p.add_argument("--limit", type=int, default=20)
    p = sp.add_parser("graph"); p.add_argument("--out", default=str(ROOT / "graph.html"))
    p = sp.add_parser("diff"); p.add_argument("--event", type=int); p.add_argument("--clip", type=int)
    p = sp.add_parser("votes"); p.add_argument("--date"); p.add_argument("--grep")
    p = sp.add_parser("brief"); p.add_argument("--event", type=int); p.add_argument("--clip", type=int); p.add_argument("--out", default=str(ROOT / "brief.md"))
    a = ap.parse_args(); globals()["cmd_" + a.cmd](a)
