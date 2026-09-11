"""Miller Tapes — every Charles Miller intervention, auto-playing theater.

Drop-in Streamlit multipage: lives at <repo>/pages/2_Miller_Tapes.py and
auto-appears in the app sidebar. Skinned to match HEROES OF THE PUBLIC
RECORD — presentation only. Stdlib + streamlit only.

Cue sheet pipeline/miller_interventions.json is built by
pipeline/build_miller_index.py (rerunnable; see its docstring). The page
autoplays muted on load (browser policy) with a TAP FOR SOUND banner, then
rolls through every filtered clip back-to-back with Up-Next cards, looping
forever. Sidebar sorting booth filters by meeting kind, intervention type,
incident flags, meeting, and text search.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "pipeline" / "miller_interventions.json"

st.set_page_config(page_title="Miller Tapes", page_icon="\U0001F3AC", layout="wide")

st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Bangers&display=swap');
.stApp{background-color:#f4ecd8;
background-image:radial-gradient(#ddd2b8 1.2px,transparent 1.3px);
background-size:15px 15px}
.mt-mast{background:#141414;border:4px solid #0a0a0a;box-shadow:6px 6px 0 #b4432f;
padding:16px 18px 12px;margin-bottom:10px;transform:rotate(-.4deg)}
.mt-mast h2{font-family:'Bangers',Impact,'Arial Black',sans-serif;font-size:2.4rem;
margin:0;color:#fff;letter-spacing:.5px}
.mt-mast h2 .gold{color:#ffd93b}
.mt-mast p{color:#ffd93b;margin:2px 0 0;font-weight:bold}
</style>
<div class="mt-mast"><h2>\U0001F3AC THE MILLER <span class="gold">TAPES</span></h2>
<p>484 TURNS &middot; 132 INTERRUPTIONS &middot; 20 TAPES &middot; 616 CUED BLOCKS</p></div>""",
            unsafe_allow_html=True)


@st.cache_data
def _load():
    return json.loads(DATA_PATH.read_text())


def _fmt(s):
    s = max(0, int(s))
    h, m, x = s // 3600, (s % 3600) // 60, s % 60
    return f"{h}:{m:02d}:{x:02d}" if h else f"{m:02d}:{x:02d}"


ITEMS = _load()
TYPES = {"testimony": "TESTIMONY", "statement": "STATEMENT",
         "formal_warning": "FORMAL WARNING", "interruption": "INTERRUPTION",
         "response": "RESPONSE"}
FLAG_LABEL = {"mic_cut": "mic cut", "point_of_order": "point of order",
              "time_called": "time called"}
MEETINGS = sorted({f"{r['date']} \u00b7 {r['title']}" for r in ITEMS})

# ------------------------------------------------------------- sorting booth
st.sidebar.header("\U0001F3AA Sorting booth")
collapse = st.sidebar.toggle("Collapse replay angles", value=True,
                             help="On: 286 unique plays. Off: all 616 blocks, "
                                  "including double-angle replays of the same moment.")
kinds = st.sidebar.multiselect("Meeting kind", sorted({r["mkind"] for r in ITEMS}),
                               default=sorted({r["mkind"] for r in ITEMS}))
TYPE_ORDER = [t for t in ("testimony", "statement", "formal_warning", "interruption",
                          "response") if any(r["type"] == t for r in ITEMS)]
types = st.sidebar.multiselect("Intervention type", TYPE_ORDER, default=TYPE_ORDER,
                               format_func=lambda t: TYPES.get(t, t))
flags = st.sidebar.multiselect("Incident flags (any)", list(FLAG_LABEL),
                               format_func=lambda f: FLAG_LABEL[f],
                               help="Keep clips carrying at least one of these.")
incidents = st.sidebar.toggle("Incidents only", value=False,
                              help="Only mic cuts, points of order, time calls, and interruption blocks.")
meet = st.sidebar.multiselect("Meeting", MEETINGS, default=MEETINGS)
query = st.sidebar.text_input("Search the words", value="",
                              help="Case-insensitive substring match on the transcript text.")
sort = st.sidebar.radio("Order", ["Chronological", "Longest first", "Shuffle"],
                        horizontal=True)
if sort == "Shuffle":
    if "mt_seed" not in st.session_state:
        st.session_state.mt_seed = 0
    if st.sidebar.button("\U0001F500 Reshuffle"):
        st.session_state.mt_seed += 1

pool = [r for r in ITEMS
        if (not collapse or r["dup_rank"] == 0)
        and r["mkind"] in kinds and r["type"] in types
        and (not flags or any(r["flags"][f] for f in flags))
        and (not incidents or r["flags"]["interrupted"])
        and f"{r['date']} \u00b7 {r['title']}" in meet
        and (not query or query.lower() in r["text"].lower())]
if sort == "Longest first":
    pool.sort(key=lambda r: -r["dur"])
elif sort == "Shuffle":
    random.Random(st.session_state.mt_seed).shuffle(pool)

total = sum(r["dur"] for r in pool)
st.markdown(f"Now screening: **{len(pool)}** interventions ({_fmt(total)} of tape) "
            f"\u00b7 {len(MEETINGS)} meetings \u00b7 median caption match 0.97")
if not pool:
    st.warning("No clips match those filters \u2014 loosen the booth and try again.")
    st.stop()

playlist = [{"v": r["video"], "t0": r["t0"], "t1": r["t1"],
             "label": f"Turn {r['n']}" if r["block"] == "turn" else f"Incident {r['n']}",
             "meet": f"{r['date']} \u00b7 {r['title']}",
             "kind": r["mkind"], "type": TYPES.get(r["type"], r["type"]),
             "flags": [FLAG_LABEL[f] for f in FLAG_LABEL if r["flags"][f]],
             "text": (r["text"][:600] + "\u2026") if len(r["text"]) > 600 else r["text"]}
            for r in pool]
pl_json = json.dumps(playlist, ensure_ascii=False).replace("</", "<\\/")

JS = """
<div id="mt-wrap" style="font-family:Arial,sans-serif">
<div id="mt-stage" style="position:relative;background:#000;border:4px solid #0a0a0a">
<div style="position:relative;padding-bottom:56.25%;height:0;overflow:hidden">
<div id="mt-player" style="position:absolute;top:0;left:0;width:100%;height:100%"></div>
</div>
<div id="mt-card" style="display:none;position:absolute;inset:0;background:rgba(10,10,10,.93);
color:#fff;align-items:center;justify-content:center;flex-direction:column;text-align:center;z-index:5">
<div style="color:#ffd93b;font-weight:bold;letter-spacing:2px">UP NEXT</div>
<div id="mt-card-t" style="font-size:26px;font-weight:bold;margin:6px 0"></div>
<div id="mt-card-s" style="color:#ddd"></div>
</div>
<div id="mt-sound" style="position:absolute;left:0;right:0;bottom:0;background:#ffd93b;
color:#0a0a0a;font-weight:bold;padding:8px 12px;display:flex;gap:10px;align-items:center;z-index:6">
<button onclick="sound()" style="background:#0a0a0a;color:#ffd93b;border:none;font-weight:bold;
font-size:15px;padding:8px 16px;cursor:pointer">\U0001F50A TAP FOR SOUND</button>
<span style="font-size:13px">Picture starts muted (browser rules) &mdash; one tap brings the audio.</span>
</div>
</div>
<div style="background:#141414;color:#fff;padding:10px 12px;border:4px solid #0a0a0a;border-top:none">
<div id="mt-title" style="font-weight:bold;font-size:17px"></div>
<div id="mt-sub" style="color:#ffd93b;font-size:13px;margin:2px 0"></div>
<div id="mt-text" style="font-style:italic;font-size:13px;color:#ddd;margin:6px 0;max-height:66px;overflow:hidden"></div>
<div style="display:flex;gap:8px;align-items:center;margin-top:6px">
<button onclick="prev()" style="background:#b4432f;color:#fff;border:none;font-weight:bold;
padding:7px 14px;cursor:pointer">&#9198; PREV</button>
<button onclick="next()" style="background:#b4432f;color:#fff;border:none;font-weight:bold;
padding:7px 14px;cursor:pointer">NEXT &#9197;</button>
<span id="mt-pos" style="color:#ffd93b;font-size:13px"></span>
</div>
<div id="mt-next" style="color:#6d7b86;font-size:12px;margin-top:6px"></div>
</div>
</div>
<script src="https://www.youtube.com/iframe_api"></script>
<script>
var PL = %%PLAYLIST%%;
var idx = 0, player = null, started = false;
function $(id){return document.getElementById(id);}
function fmt(s){s=Math.max(0,Math.floor(s));var h=Math.floor(s/3600),m=Math.floor(s%3600/60),
x=s%60;return (h?h+":":"")+("0"+m).slice(-2)+":"+("0"+x).slice(-2);}
function render(){var c=PL[idx],n=PL[(idx+1)%PL.length];
$("mt-title").textContent=(idx+1)+" / "+PL.length+" \\u2014 "+c.label;
$("mt-sub").textContent=c.meet+" \\u00b7 "+c.kind+" \\u00b7 "+fmt(c.t0)+"\\u2192"+fmt(c.t1)+
" \\u00b7 "+c.type+(c.flags.length?" \\u00b7 "+c.flags.join(", "):"");
$("mt-text").textContent="\\u201C"+c.text+"\\u201D";
$("mt-next").textContent="UP NEXT: "+n.label+" ("+n.meet+")";}
function load(i){idx=((i%PL.length)+PL.length)%PL.length;var c=PL[idx];render();
if(started&&player&&player.loadVideoById){$("mt-card-t").textContent=c.label;
$("mt-card-s").textContent=c.meet+" \\u00b7 starts in 5\\u2026";
$("mt-card").style.display="flex";
setTimeout(function(){$("mt-card").style.display="none";
player.loadVideoById({videoId:c.v,startSeconds:Math.floor(c.t0)});},5000);}}
function jump(i){if(player&&player.loadVideoById)load(i);}
function next(){if(player&&player.loadVideoById)load(idx+1);}
function prev(){if(player&&player.loadVideoById)load(idx-1);}
function sound(){if(player&&player.unMute){player.unMute();player.setVolume(100);
$("mt-sound").style.display="none";}}
function onYouTubeIframeAPIReady(){render();
player=new YT.Player("mt-player",{width:"100%",height:"100%",videoId:PL[0].v,
playerVars:{autoplay:1,start:Math.floor(PL[0].t0),rel:0},
events:{onReady:function(e){e.target.mute();e.target.setVolume(0);e.target.playVideo();
started=true;
setInterval(function(){if(!player||!player.getCurrentTime)return;
try{var t=player.getCurrentTime(),c=PL[idx];
$("mt-pos").textContent="tape "+fmt(t)+" \\u00b7 clip "+fmt(Math.max(0,t-c.t0))+" / "+fmt(c.t1-c.t0);
if(t>=c.t1-0.25)next();}catch(err){}},500);},
onStateChange:function(e){if(e.data===YT.PlayerState.ENDED)next();},
onError:function(e){next();}}});}
</script>
"""

components.html(JS.replace("%%PLAYLIST%%", pl_json), height=860, scrolling=False)

with st.expander(f"\U0001F4DC Queue ({len(pool)} clips) \u2014 every row links its exact tape moment"):
    rows = []
    for i, r in enumerate(pool[:400]):
        lab = f"Turn {r['n']}" if r["block"] == "turn" else f"Incident {r['n']}"
        url = f"https://www.youtube.com/watch?v={r['video']}&t={int(r['t0'])}s"
        fl = ",".join(f for f in FLAG_LABEL if r["flags"][f])
        rows.append(f"#{i+1} [{lab} \u2014 {r['date']} \u00b7 {_fmt(r['t0'])}\u2192{_fmt(r['t1'])}"
                    f"{(' \u00b7 ' + fl) if fl else ''}]({url})")
    if len(pool) > 400:
        rows.append(f"*\\u2026and {len(pool) - 400} more in the player above.*")
    st.markdown("\n\n".join(rows))

with st.expander("How this was made (rerunnable)"):
    st.markdown("""Cue sheet `pipeline/miller_interventions.json` is built by
`pipeline/build_miller_index.py` from the MILLER_EVERYTHING compilation plus
timestamped YouTube caption tracks (refetchable, not committed):
616/616 blocks cued, median caption match 0.97, mic-cut / point-of-order /
time-called flags auto-detected, replay angles grouped into 286 unique plays,
and all three verified-tape timestamps land inside their cued segments.
Rerun `python3 pipeline/build_miller_index.py` any time the compilation or
captions change; this page picks the new cue sheet up on reload.""")
