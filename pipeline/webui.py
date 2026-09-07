#!/usr/bin/env python3
"""
webui.py — browser interface for the Cheyenne pipeline
======================================================
Run:  python3 webui.py            (http://localhost:8717)
      python3 webui.py --port 9000 --host 0.0.0.0

Everything the CLI does, from tabs in your browser:
  MEETINGS  search the index, pull docs/videos/captions per meeting
  CLIPS     cut timestamped segments on the fly (stream-local, no big downloads),
            batch paste a turns.json spec, play results inline
  RENDER    build a reel (meeting clips + your commentary + title cards),
            render it, play + download

Jobs run in a background worker; the page shows a live log.
Dependencies: whatever cheyenne_pipeline.py needs (requests, ffmpeg; yt-dlp/curl_cffi optional).
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import queue
import re
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote

import cheyenne_pipeline as P

ROOT = Path(__file__).resolve().parent
PORT = 8717

# ---------------------------------------------------------------- jobs

JOBS: dict[str, dict] = {}
JOB_Q: "queue.Queue[str]" = queue.Queue()
LOCK = threading.Lock()
_next = [0]


class JobLog(io.TextIOBase):
    def __init__(self, jid: str):
        self.jid = jid

    def write(self, s):
        if s.strip():
            with LOCK:
                JOBS[self.jid]["log"].append(s.rstrip())
                del JOBS[self.jid]["log"][-200:]
        return len(s)

    def flush(self):
        pass


def submit(kind: str, label: str, fn, *a, **kw) -> str:
    with LOCK:
        _next[0] += 1
        jid = f"job{_next[0]:04d}"
        JOBS[jid] = {"id": jid, "kind": kind, "label": label, "status": "queued",
                     "log": [], "error": None, "result": None, "t": time.time()}
    JOB_Q.put((jid, fn, a, kw))
    return jid


def worker():
    while True:
        jid, fn, a, kw = JOB_Q.get()
        with LOCK:
            JOBS[jid]["status"] = "running"
        try:
            with contextlib.redirect_stdout(JobLog(jid)):
                res = fn(*a, **kw)
            with LOCK:
                JOBS[jid]["status"] = "done"
                JOBS[jid]["result"] = str(res) if res is not None else None
        except SystemExit as e:
            with LOCK:
                JOBS[jid]["status"] = "error"
                JOBS[jid]["error"] = str(e)
        except Exception as e:
            with LOCK:
                JOBS[jid]["status"] = "error"
                JOBS[jid]["error"] = f"{e.__class__.__name__}: {e}"
                JOBS[jid]["log"].append(traceback.format_exc(limit=3))
        JOB_Q.task_done()


# ---------------------------------------------------------------- helpers

def meetings_index():
    try:
        return P.load_index()
    except SystemExit:
        return {}


def safe_file(kind: str, name: str) -> Path:
    base = {"clips": P.CLIPS, "renders": P.RENDERS, "videos": P.VIDEOS,
            "docs": P.DOCS, "root": ROOT}[kind]
    p = (base / name).resolve()
    if not str(p).startswith(str(base.resolve())):
        raise ValueError("bad path")
    return p


def list_dir(kind: str):
    base = {"clips": P.CLIPS, "renders": P.RENDERS, "videos": P.VIDEOS}[kind]
    out = []
    for p in sorted(base.glob("**/*"), key=lambda x: x.stat().st_mtime if x.exists() else 0,
                    reverse=True):
        if p.is_file() and not p.name.startswith("."):
            out.append({"name": str(p.relative_to(base)), "size": p.stat().st_size,
                        "mtime": time.strftime("%Y-%m-%d %H:%M", time.localtime(p.stat().st_mtime))})
    return out[:200]


def docs_tree():
    out = []
    for d in sorted(P.DOCS.glob("*"), reverse=True):
        if d.is_dir() and d.name.isdigit():
            files = [{"name": f.name, "size": f.stat().st_size}
                     for f in sorted(d.glob("*")) if f.is_file()]
            if files:
                out.append({"meeting": int(d.name), "files": files})
    return out[:120]


# ---------------------------------------------------------------- job wrappers

def j_index():
    P.cmd_index(_NS(lambda: None))
    return "index refreshed"


def j_docs(meeting: str, max_docs: int):
    cid, m = P.resolve(meeting)
    P.fetch_meeting_docs(cid, m, max_docs)
    return f"docs for {cid} done"


def j_video(meeting: str, seconds: float):
    cid, m = P.resolve(meeting)
    P.fetch_video(cid, m, seconds=seconds)
    return f"video {cid} done"


def j_captions(meeting: str):
    cid = int(meeting) if meeting.isdigit() else P.resolve(meeting)[0]
    P.http_get(f"{P.BASE}videos/{cid}/captions.vtt")
    dest = P.DOCS / f"{cid}_captions.vtt"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(P.http_get(f"{P.BASE}videos/{cid}/captions.vtt").content)
    return f"captions {cid} -> docs/{dest.name}"


def j_clip(meeting, start, end, name):
    path = P.smart_clip(meeting, start, end, name=name)
    return f"clip -> {path.name}"


def j_segments(spec):
    made = []
    for i, seg in enumerate(spec):
        name = seg.get("name") or f"seg_{i+1:02d}"
        out = P.CLIPS / (name if name.endswith(".mp4") else name + ".mp4")
        if out.exists():
            print(f"[=] exists, skipping {out.name}")
            continue
        print(f"[*] {i+1}/{len(spec)}: {name} <- {seg.get('meeting') or seg.get('url')}")
        if seg.get("url"):
            P.stream_clip(seg["url"], seg["start"], seg["end"], name=name,
                          normalize=seg.get("normalize", False))
        else:
            P.smart_clip(str(seg["meeting"]), seg["start"], seg["end"],
                         name=name, normalize=seg.get("normalize", False))
        made.append(out.name)
    return f"{len(made)} clips created"


def j_project(plan: dict):
    plan = dict(plan)
    plan["output"] = plan.get("output") or f"ui_reel_{int(time.time())}.mp4"
    plan_file = ROOT / "ui_plan.json"
    plan_file.write_text(json.dumps(plan))
    P.cmd_project(_NS(lambda: None, plan=str(plan_file)))
    return f"rendered renders/{plan['output']}"


def _save_commentary(name, data):
    P.COMMENT.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", name)
    (P.COMMENT / safe).write_bytes(data)
    return f"saved commentary/{safe}"


def j_ask(question, auto):
    spec = P.ask_engine(question)
    P.ASKS.mkdir(exist_ok=True)
    n = len(list(P.ASKS.glob("ask_*.json"))) + 1
    out = P.ASKS / f"ask_{n:03d}.json"
    out.write_text(json.dumps(spec, indent=1))
    if auto and any(s.get("start") for s in spec["segments"]):
        P.cmd_answer(_NS(lambda: None, plan=str(out)))
    return f"{out.name}: {len(spec['segments'])} segments"


def j_verify(quote):
    import io as _io, contextlib as _cl
    buf = _io.StringIO()
    with _cl.redirect_stdout(buf):
        P.cmd_verify(type("A", (), {"quote": quote})())
    return buf.getvalue() or "no output"


def j_turns(meeting, text):
    return P.parse_turns(text, meeting)


def j_answer_batch():
    P.cmd_answer(_NS(lambda: None, plan=str(P.ASKS)))
    return "batch render done"


def j_autopass():
    import io as _io, contextlib as _cl
    buf = _io.StringIO()
    with _cl.redirect_stdout(buf):
        P.cmd_autopass(type("A", (), {})())
    return buf.getvalue().strip().splitlines()[-1] if buf.getvalue() else "autopass done"


class _NS:
    def __init__(self, fn, plan=None):
        self.fn = fn
        self.plan = plan
        self.keep_work = False


# ---------------------------------------------------------------- HTTP

PAGE = r"""<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Cheyenne Pipeline</title><style>
:root{--bg:#101418;--pan:#171d24;--lin:#232c36;--tx:#dbe4ee;--dim:#8296ab;--ac:#4da3ff;--ok:#39c98e;--er:#ff6b6b}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--tx);font:14px/1.45 system-ui,sans-serif}
header{padding:10px 18px;background:var(--pan);border-bottom:1px solid var(--lin);display:flex;gap:14px;align-items:center}
header h1{font-size:16px;margin:0}header .dim{color:var(--dim);font-size:12px}
nav{display:flex;gap:6px;padding:8px 18px;background:var(--pan);border-bottom:1px solid var(--lin)}
nav button{background:none;border:1px solid var(--lin);color:var(--dim);padding:6px 14px;border-radius:6px;cursor:pointer;font-size:13px}
nav button.on{color:var(--tx);border-color:var(--ac);background:#4da3ff22}
main{padding:16px 18px;max-width:1180px;margin:0 auto}
.panel{display:none}.panel.on{display:block}
.row{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin:10px 0}
input,select,textarea{background:#0c1014;border:1px solid var(--lin);color:var(--tx);border-radius:6px;padding:7px 9px;font-size:13px}
input[type=text],input[type=number]{width:auto}textarea{width:100%;min-height:130px;font-family:ui-monospace,monospace}
button.act{background:var(--ac);border:none;color:#04121f;font-weight:600;padding:8px 14px;border-radius:6px;cursor:pointer}
button.ghost{background:none;border:1px solid var(--lin);color:var(--tx);padding:6px 12px;border-radius:6px;cursor:pointer}
table{width:100%;border-collapse:collapse;margin:8px 0}th,td{padding:6px 8px;border-bottom:1px solid var(--lin);text-align:left;font-size:13px}
th{color:var(--dim);font-weight:500}tr:hover td{background:#1b232c}
.badge{display:inline-block;min-width:22px;text-align:center;border-radius:4px;padding:1px 5px;font-size:11px;margin-right:3px}
.y{background:#39c98e22;color:var(--ok)}.n{color:#4a5a68}
.card{background:var(--pan);border:1px solid var(--lin);border-radius:10px;padding:14px;margin:12px 0}
.card h3{margin:0 0 8px;font-size:14px;color:var(--ac)}
#log{background:#0a0e12;border:1px solid var(--lin);border-radius:8px;padding:10px;height:210px;overflow-y:auto;font:12px/1.5 ui-monospace,monospace;white-space:pre-wrap}
.job{border-left:3px solid var(--ac);padding-left:8px;margin-bottom:6px}.job.err{border-color:var(--er)}.job.done{border-color:var(--ok)}
.job .lab{color:var(--dim)}video{max-width:100%;border-radius:8px;background:#000;margin-top:8px}
.dim{color:var(--dim)}.small{font-size:12px}a{color:var(--ac);text-decoration:none}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:14px}@media(max-width:900px){.grid2{grid-template-columns:1fr}}
.flist{max-height:260px;overflow-y:auto}
</style></head><body>
<header><h1>Cheyenne Municipal Pipeline</h1><span class=dim id=idx>index: loading…</span>
<span class=dim style="margin-left:auto">stream-local clips · no full downloads</span></header>
<nav>
<button data-p=meetings class=on>Meetings</button>\n<button data-p=ask>Ask & Verify</button>
<button data-p=clips>Clips</button>
<button data-p=render>Render reel</button>
<button data-p=files>Files</button>
<button data-p=log class=last>Job log</button>
</nav>
<main>

<div class="panel" id="panel-ask">
 <div class="grid2">
 <div class=card><h3>Ask the record — question to reel spec</h3>
  <textarea id=aq style="min-height:64px">What has the council spent on the Municipal Building?</textarea>
  <div class=row><button class=act onclick=askQ(false)>Find quotes</button>
  <button class=ghost onclick=askQ(true)>Find + render now</button>
  <span class=small dim>searches all 470+ meeting transcripts; timestamps auto-fill from your sync transcripts in corpus/extra/</span></div>
  <div id=askres class=flist></div>
  <div class=row><button class=ghost onclick=api('answer_batch','render all asks',{})>Render ALL ready asks</button>
  <span class=small dim>renders every spec in asks/ that has timestamps (batch)</span></div>
 </div>
 <div class=card><h3>Verify a quote before you publish</h3>
  <textarea id=vq style="min-height:64px" placeholder="Paste the exact quote..."></textarea>
  <div class=row><button class=act onclick=verifyQ()>Verify against all transcripts</button></div>
  <div id=vres class=flist></div>
 </div>
 </div>
</div>
<div class="panel on" id=panel-meetings>
 <div class=row>
  <input type=text id=q placeholder="search date/name (2026-08, Jul 27, special…)" style="flex:1;min-width:220px">
  <select id=lim><option>25</option><option>50</option><option>100</option><option>300</option></select>
  <button class=ghost onclick=loadMeetings()>Search</button>
  <button class=ghost onclick=api('index','Re-index archive',{})>Re-index</button>
  <button class=ghost onclick=api('autopass','autopass: new meetings',{})>Check for NEW meetings</button>
 </div>
 <div class=card><h3>Search meeting transcripts (minutes corpus)</h3>
  <div class=row><input type=text id=sq style="flex:1;min-width:220px" placeholder="annexation, municipal building, DDA, Lipscomb…">
  <button class=act onclick=tsearch()>Search transcripts</button>
  <button class=ghost onclick=api('corpus','build corpus',{})>Build/refresh corpus</button></div>
  <div id=sres class=flist></div>
  <div class=small dim>corpus = official minutes text (built via the button or CLI `corpus`); feeds NotebookLM bundle in notebooklm/</div>
 </div>
 <table id=mt><thead><tr><th>clip</th><th>date</th><th>name</th><th>mp4</th><th>ag</th><th>min</th><th>actions</th></tr></thead><tbody></tbody></table>
 <div class=small dim>docs = agenda + minutes + every supporting packet page · video = full download (big!) · captions = WebVTT</div>
</div>

<div class=panel id=panel-clips>
 <div class="grid2">
 <div class=card><h3>Cut a clip (stream-local)</h3>
  <div class=row><input type=text id=cm placeholder="meeting (clip id, e.g. 1091)" size=10>
  <input type=text id=cs placeholder="start 01:22:10"><input type=text id=ce placeholder="end 01:25:00">
  <input type=text id=cn placeholder="name" size=14"><button class=act onclick=cutOne()>Cut</button></div>
  <div class=small dim>Uses the local video if present; otherwise fetches only the stream segments for your window. Timestamps = your “Sync to video time” numbers.</div>
 </div>
 <div class=card><h3>Batch spec (JSON list)</h3>
  <textarea id=spec>[
 {"meeting": 1071, "start": "00:04:10", "end": "00:07:00", "name": "mar9_miller"},
 {"meeting": 1103, "start": "01:22:00", "end": "01:25:00", "name": "jun22_miller"}
]</textarea>
  <div class=row><button class=act onclick=runSpec()>Create all</button>
  <span class=small dim>entries may use "url" (an m3u8) instead of "meeting"</span></div>
 </div>
 </div>
 <div class=card><h3>Turn-list importer (paste sync-to-video transcript)</h3>
  <div class=row><input type=text id=tm placeholder="meeting clip id (e.g. 1071)" size=10>
  <button class=act onclick=importTurns()>Parse turns</button>
  <span class=small dim>every "HH:MM:SS | description" line becomes a clip spec below</span></div>
  <textarea id=ttx placeholder="00:04:10 | Charles Miller - public comment&#10;00:07:00 Chairman closes the hearing"></textarea>
 </div>
 <div class=card><h3>Clips</h3><div id=cliplist class=flist></div></div>
</div>

<div class=panel id=panel-render>
 <div class=card><h3>Reel project (JSON)</h3>
  <textarea id=plan>{
 "output": "my_reel.mp4",
 "segments": [
  {"type": "title", "text": "MLK Park, by the numbers", "duration": 4},
  {"type": "clip", "meeting": 1091, "start": "00:04:10", "end": "00:06:30", "name": "reel_a"},
  {"type": "file", "path": "commentary/my_take.mp4"},
  {"type": "clip", "meeting": 1103, "start": "01:22:00", "end": "01:25:00",
   "overlay_audio": "commentary/voiceover.mp3", "duck": true, "name": "reel_b"},
  {"type": "title", "text": "$0 for treatment", "duration": 4}
 ]
}</textarea>
  <div class=row><button class=act onclick=runPlan()>Render</button>
  <label class=ghost style=display:inline-block>Upload commentary file<input type=file style=display:none onchange=upFile(this)></label>
  <span class=small dim>lands in commentary/ — use as {"type":"file","path":"commentary/NAME"}</span></div>
  <span class=small dim>clip segments stream their window automatically; file paths are relative to the pipeline folder</span></div>
 </div>
 <div class=card><h3>Renders</h3><div id=rendlist class=flist></div></div>
</div>

<div class=panel id=panel-files>
 <div class=grid2>
 <div class=card><h3>Videos (full meetings)</h3><div id=vidlist class=flist></div></div>
 <div class=card><h3>Documents by meeting</h3><div id=doctree class=flist></div></div>
 </div>
</div>

<div class=panel id=panel-log><div id=log></div></div>

</main><script>
const $=s=>document.querySelector(s);
const esc=t=>String(t).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
async function jget(u){const r=await fetch(u);if(!r.ok)throw new Error(await r.text());return r.json()}
async function jpost(u,b){const r=await fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});if(!r.ok)throw new Error(await r.text());return r.json()}
function api(kind,label,body){return jpost('/api/'+kind,body).then(j=>{toast(`${label} → ${j.id} queued`);return j}).catch(e=>toast(label+' FAILED: '+e.message,true))}
let toastT;function toast(msg,err){let d=document.createElement('div');d.textContent=msg;d.style.cssText=`position:fixed;bottom:16px;right:16px;background:${err?'#ff6b6b':'#173b2c'};color:#fff;padding:10px 16px;border-radius:8px;z-index:9;max-width:70%`;document.body.appendChild(d);clearTimeout(toastT);toastT=setTimeout(()=>d.remove(),4200)}
document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>{document.querySelectorAll('nav button').forEach(x=>x.classList.toggle('on',x===b));document.querySelectorAll('.panel').forEach(p=>p.classList.toggle('on',p.id==='panel-'+b.dataset.p));if(b.dataset.p==='clips')loadClips();if(b.dataset.p==='files')loadFiles();if(b.dataset.p==='render')loadRenders();});

async function tsearch(){try{const q=$('#sq').value.trim();if(!q)return;const r=await jget('/api/search?q='+encodeURIComponent(q));
$('#sres').innerHTML=r.hits.length?'':'<span class=dim>no hits (build the corpus first, or try fewer terms)</span>';
for(const h of r.hits){$('#sres').innerHTML+=`<div style="padding:6px 0;border-bottom:1px solid var(--lin)"><b>${esc(h.file)}</b> <span class=dim>score ${h.score}</span><div class=small>${esc(h.snippet.slice(0,260))}…</div></div>`}}catch(e){toast(e.message,true)}}
async function askQ(auto){try{const q=$('#aq').value.trim();if(!q)return;
const r=await jpost('/api/ask',{question:q,auto});toast('ask queued: '+r.id)}catch(e){toast(e.message,true)}}
async function verifyQ(){try{const q=$('#vq').value.trim();if(!q)return;
const r=await jget('/api/verify?dummy=1');}catch(e){}
try{const r=await fetch('/api/verify',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({quote:$('#vq').value.trim()})}).then(x=>x.json());
$('#vres').innerHTML='<pre style="white-space:pre-wrap">'+esc(r.verdict)+'</pre>'}catch(e){toast(e.message,true)}}
async function importTurns(){try{const t=$('#ttx').value;if(!t.trim())return toast('paste transcript lines first',true);
const r=await jpost('/api/turns',{meeting:$('#tm').value.trim()||null,text:t});
$('#spec').value=JSON.stringify(r.spec,null,1);toast(r.spec.length+' turns parsed into the batch box');document.querySelector('nav button[data-p=clips]').click()}catch(e){toast(e.message,true)}}
async function upFile(inp){try{const f=inp.files[0];if(!f)return;const buf=await f.arrayBuffer();
const hex=[...new Uint8Array(buf)].map(b=>b.toString(16).padStart(2,'0')).join('');
const r=await jpost('/api/upload',{name:f.name,data_hex:hex});toast('uploaded '+f.name)}catch(e){toast(e.message,true)}}
async function loadMeetings(){try{const q=$('#q').value.trim(),lim=$('#lim').value;const ms=await jget(`/api/meetings?search=${encodeURIComponent(q)}&limit=${lim}`);
$('#idx').textContent=`index: ${ms.total} meetings`;const tb=$('#mt tbody');tb.innerHTML='';
for(const m of ms.items){tb.innerHTML+=`<tr><td>${m.clip_id}</td><td>${m.date||'?'}</td><td>${esc(m.name)}</td>
<td>${m.mp4?'<span class="badge y">Y</span>':'<span class=n>–</span>'}</td><td>${m.agenda?'<span class="badge y">Y</span>':'<span class=n>–</span>'}</td><td>${m.minutes?'<span class="badge y">Y</span>':'<span class=n>–</span>'}</td>
<td><button class=ghost onclick="api('docs','docs ${m.clip_id}',{meeting:'${m.clip_id}'})">docs</button>
<button class=ghost onclick="api('video','video ${m.clip_id}',{meeting:'${m.clip_id}',seconds:0})">video</button>
<button class=ghost onclick="api('captions','captions ${m.clip_id}',{meeting:'${m.clip_id}'})">captions</button>
<button class=ghost onclick="prefillClip(${m.clip_id})">clip</button></td></tr>`}}catch(e){toast(e.message,true)}}
function prefillClip(id){$('#cm').value=id;document.querySelector('nav button[data-p=clips]').click()}
function cutOne(){api('clip','clip',{meeting:$('#cm').value.trim(),start:$('#cs').value.trim(),end:$('#ce').value.trim(),name:$('#cn').value.trim()}).then(()=>setTimeout(loadClips,2500))}
function runSpec(){let spec;try{spec=JSON.parse($('#spec').value)}catch(e){return toast('spec JSON: '+e.message,true)}
api('segments','batch clips',{spec}).then(()=>setTimeout(loadClips,2500))}
function runPlan(){let plan;try{plan=JSON.parse($('#plan').value)}catch(e){return toast('plan JSON: '+e.message,true)}
api('project','render',{plan}).then(()=>setTimeout(loadRenders,2500))}

async function loadClips(){try{const fs=await jget('/api/files?type=clips');$('#cliplist').innerHTML=fs.length?'':'<span class=dim>none yet</span>';
for(const f of fs){$('#cliplist').innerHTML+=`<div style="padding:6px 0;border-bottom:1px solid var(--lin)">
<b>${esc(f.name)}</b> <span class=dim>${(f.size/1e6).toFixed(1)} MB · ${f.mtime}</span>
<a href="/file/clips/${encodeURIComponent(f.name)}" download>download</a>
<button class=ghost onclick="play('/file/clips/${encodeURIComponent(f.name)}',this)">play</button><div></div></div>`}}catch(e){toast(e.message,true)}}
async function loadRenders(){try{const fs=await jget('/api/files?type=renders');$('#rendlist').innerHTML=fs.length?'':'<span class=dim>none yet</span>';
for(const f of fs){$('#rendlist').innerHTML+=`<div style="padding:6px 0;border-bottom:1px solid var(--lin)">
<b>${esc(f.name)}</b> <span class=dim>${(f.size/1e6).toFixed(1)} MB · ${f.mtime}</span>
<a href="/file/renders/${encodeURIComponent(f.name)}" download>download</a>
<button class=ghost onclick="play('/file/renders/${encodeURIComponent(f.name)}',this)">play</button><div></div></div>`}}catch(e){toast(e.message,true)}}
async function loadFiles(){try{const vs=await jget('/api/files?type=videos');$('#vidlist').innerHTML=vs.length?'':'<span class=dim>none (good — use clips instead)</span>';
for(const f of vs){$('#vidlist').innerHTML+=`<div style="padding:4px 0"><b>${esc(f.name)}</b> <span class=dim>${(f.size/1e6).toFixed(0)} MB</span> <a href="/file/videos/${encodeURIComponent(f.name)}" download>download</a></div>`}
const ds=await jget('/api/docs');$('#doctree').innerHTML=ds.length?'':'<span class=dim>none yet — pull docs from the Meetings tab</span>';
for(const d of ds){$('#doctree').innerHTML+=`<div style="padding:6px 0;border-bottom:1px solid var(--lin)"><b>meeting ${d.meeting}</b>${d.files.map(f=>`<div class=small><a href="/file/docs/${d.meeting}/${encodeURIComponent(f.name)}" target=_blank>${esc(f.name)}</a> <span class=dim>${(f.size/1024).toFixed(0)} KB</span></div>`).join('')}</div>`}}catch(e){toast(e.message,true)}}
function play(u,btn){let v=btn.nextElementSibling;if(!v||v.tagName!=='VIDEO'){v=document.createElement('video');v.controls=true;v.src=u;btn.after(v)}else{v.remove()}}

async function poll(){try{const s=await jget('/api/status');const el=$('#log');
el.innerHTML=s.jobs.map(j=>`<div class="job ${j.status}"><span class=lab>[${j.id}] ${j.label} — ${j.status}${j.error?' · '+esc(j.error):''}</span>\n${j.log.map(esc).join('\n')}</div>`).join('\n');
const running=s.jobs.some(j=>j.status==='queued'||j.status==='running');
el.scrollTop=el.scrollHeight;}catch(e){}}
loadMeetings();setInterval(poll,1800);poll();
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        try:
            if u.path == "/":
                b = PAGE.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)
            elif u.path == "/api/meetings":
                idx = meetings_index()
                search = (q.get("search") or [""])[0].lower()
                limit = int((q.get("limit") or ["50"])[0])
                items = sorted(idx.items(), key=lambda kv: (kv[1].get("date") or "", kv[0]), reverse=True)
                if search:
                    items = [(c, v) for c, v in items if search in
                             (str(v.get("name", "")) + " " + str(v.get("date", "")) + " " + str(c)).lower()]
                self._json({"total": len(idx), "items": [
                    {"clip_id": c, "date": v.get("date"), "name": v.get("name", ""),
                     "mp4": bool(v.get("mp4_url")), "agenda": bool(v.get("agenda_url")),
                     "minutes": bool(v.get("minutes_url") or v.get("city_minutes_pdf"))}
                    for c, v in items[:limit]]})
            elif u.path == "/api/files":
                self._json(list_dir((q.get("type") or ["clips"])[0]))
            elif u.path == "/api/docs":
                self._json(docs_tree())
            elif u.path == "/api/search":
                q = (q.get("q") or [""])[0]
                hits = P.corpus_search(q, 8) if q and P.CORPUS.exists() else []
                self._json({"hits": hits})
            elif u.path == "/api/status":
                with LOCK:
                    jobs = sorted(JOBS.values(), key=lambda j: j["t"], reverse=True)[:12]
                self._json({"jobs": jobs})
            elif u.path == "/file/":
                raise ValueError("missing path")
            elif u.path.startswith("/file/"):
                _, _, kind, rest = u.path.split("/", 3)
                name = unquote(rest)
                p = safe_file({"clips": "clips", "renders": "renders", "videos": "videos",
                               "docs": "docs"}[kind], name)
                if not p.exists():
                    return self._json({"error": "not found"}, 404)
                ctype = ("video/mp4" if p.suffix == ".mp4" else
                         "text/html; charset=utf-8" if p.suffix == ".html" else
                         "text/vtt" if p.suffix == ".vtt" else
                         "application/pdf" if p.suffix == ".pdf" else
                         "application/octet-stream")
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(p.stat().st_size))
                if (q.get("download") or [""])[0]:
                    self.send_header("Content-Disposition", f'attachment; filename="{p.name}"')
                self.end_headers()
                with open(p, "rb") as f:
                    while chunk := f.read(65536):
                        self.wfile.write(chunk)
            else:
                self._json({"error": "no such endpoint"}, 404)
        except Exception as e:
            self._json({"error": f"{e.__class__.__name__}: {e}"}, 400)

    def do_POST(self):
        try:
            body = self._body()
            u = urlparse(self.path)
            if u.path == "/api/ask":
                jid = submit("ask", f"ask: {body['question'][:50]}", j_ask,
                             body["question"], bool(body.get("auto")))
            elif u.path == "/api/verify":
                try:
                    res = j_verify(body["quote"])
                    self._json({"verdict": res})
                except Exception as e:
                    self._json({"verdict": f"{e.__class__.__name__}: {e}"})
                return
            elif u.path == "/api/turns":
                self._json({"spec": j_turns(body.get("meeting"), body.get("text", ""))})
            elif u.path == "/api/answer_batch":
                jid = submit("batch", "render ALL ask specs", j_answer_batch)
            elif u.path == "/api/autopass":
                jid = submit("autopass", "check for new meetings", j_autopass)
            elif u.path == "/api/upload":
                jid = submit("upload", "save commentary file",
                             lambda n, d: _save_commentary(n, d),
                             body["name"], bytes.fromhex(body["data_hex"]))
            elif u.path == "/api/index":
                jid = submit("index", "re-index archive", j_index)
            elif u.path == "/api/docs":
                jid = submit("docs", f"docs {body['meeting']}", j_docs,
                             body["meeting"], int(body.get("max_docs") or 0))
            elif u.path == "/api/video":
                jid = submit("video", f"video {body['meeting']}", j_video,
                             body["meeting"], float(body.get("seconds") or 0))
            elif u.path == "/api/captions":
                jid = submit("captions", f"captions {body['meeting']}", j_captions, body["meeting"])
            elif u.path == "/api/clip":
                jid = submit("clip", f"clip {body.get('name') or body['meeting']}", j_clip,
                             body["meeting"], body["start"], body["end"], body.get("name") or "")
            elif u.path == "/api/segments":
                jid = submit("segments", f"batch {len(body['spec'])} clips", j_segments, body["spec"])
            elif u.path == "/api/project":
                jid = submit("project", "render reel", j_project, body["plan"])
            else:
                return self._json({"error": "no such endpoint"}, 404)
            self._json({"id": jid, "status": JOBS[jid]["status"]})
        except Exception as e:
            self._json({"error": f"{e.__class__.__name__}: {e}"}, 400)


def main():
    global PORT
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--host", default="0.0.0.0")
    args = ap.parse_args()
    PORT = args.port
    for d in (P.VIDEOS, P.DOCS, P.CLIPS, P.RENDERS):
        d.mkdir(parents=True, exist_ok=True)
    threading.Thread(target=worker, daemon=True).start()
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"[+] Cheyenne pipeline UI -> http://localhost:{args.port}")
    if args.host == "0.0.0.0":
        print("    (bound to all interfaces — reachable from other devices on your network)")
    srv.serve_forever()


if __name__ == "__main__":
    main()
