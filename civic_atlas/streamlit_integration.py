"""Streamlit integration: no second HTTP server or localhost URLs required."""
from __future__ import annotations
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

def script_json(value):
    return json.dumps(value, ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')

def portable_lens_html(source_label='Any meeting video', source_url=None):
    """Self-contained lens for the component AND a downloadable top-level page.

    No server access, source scraping, or video bytes embedded. The user selects
    a local file or explicitly grants screen capture. External URLs are links only.
    """
    html = (HERE/'index.html').read_text()
    css = (HERE/'style.css').read_text() + '''
.rail,header,.heading,.tabs,#map-view,footer{display:none!important}
.shell{margin:0}main{padding:16px;max-width:1200px}.lens-intro .pill{display:none}
#lens-view{display:block!important}.lens-toolbar #video-select{display:none}
.lens-layout{grid-template-columns:1fr 1fr}.lens-intro h2{font-size:24px}
@media(max-width:800px){.lens-layout{grid-template-columns:1fr}}
'''
    boot = '''
window.fetch=async function(path){return {ok:true,json:async()=>String(path).includes('/api/catalog')?({meetings:[],agendas:[],topics:[],videos:[],count:0}):[]}};
'''
    source = script_json({'label':source_label,'url':source_url})
    finish = '''
switchView('lens');
const sourceHint = SOURCE_HINT;
const note=document.createElement('p');note.className='capture-status';note.textContent='Selected source: '+sourceHint.label+'. To see this player’s pixels, share its tab/window, or open the video file locally. Crop settings are manual.';
document.querySelector('.lens-intro').after(note);
if(sourceHint.url && /^https:\/\//i.test(sourceHint.url)){
 const a=document.createElement('a');a.href=sourceHint.url;a.target='_blank';a.rel='noopener';a.textContent='Open selected source video ↗';a.style.display='block';a.style.marginBottom='15px';note.after(a);
}
'''.replace('SOURCE_HINT',source)
    html=html.replace('<title>Civic Atlas · The Real Windy City</title>','<title>Dais Lens · The Real Windy City</title>')
    html=html.replace('<link rel="stylesheet" href="/style.css">','<style>'+css+'</style>')
    html=html.replace('<script src="/app.js"></script>', '<script>'+boot+'\n'+(HERE/'app.js').read_text().replace('</script','<\\/script')+'</script>')
    html=html.replace('<script src="/lens.js"></script>', '<script>'+(HERE/'lens.js').read_text().replace('</script','<\\/script')+'\n'+finish+'</script>')
    return html


def render_lens_option(key, source_label='Any meeting video', source_url=None):
    """Opt-in expander beside each player; no capture until user consents."""
    import streamlit as st
    import streamlit.components.v1 as components
    with st.expander('▣ Dais Lens — enlarge each visible seat (optional)'):
        enabled=st.checkbox('Enable Dais Lens for this video',key='atlas_enable_'+key)
        if not enabled:
            st.caption('Your existing video player is unchanged. Enable to open synchronized manual crop views.')
            return
        st.caption('Share the video’s tab/window or choose a local video file. No face identification or emotion scoring. Only faces visible in the camera frame can be enlarged.')
        document=portable_lens_html(source_label,source_url)
        st.download_button('Download standalone Dais Lens',document,'dais-lens.html','text/html',key='atlas_download_'+key)
        st.info('If Streamlit blocks tab sharing inside the embedded panel, download the standalone lens and open it in a desktop browser. Sharing requires browser support and permission; protected video may stay black. The download contains the tool, not the meeting video.')
        components.html(document,height=1050,scrolling=True)


def evidence_map_html(topic, results):
    """Interactive source graph, using only the current result set (no hidden fetch)."""
    data=script_json({'topic':topic,'results':results[:12]})
    return '''<!doctype html><html><head><meta charset="utf-8"><style>
body{margin:0;background:#10181e;color:#e4ecee;font:13px Arial;padding:16px}h3{color:#81d7c0;font-weight:500}svg{width:100%;height:470px;background:radial-gradient(#293b43 1px,transparent 1px);background-size:22px 22px}text{font:10px Arial}.node{cursor:pointer}.node:hover circle{stroke:white}pre{white-space:pre-wrap;font:12px/1.7 monospace;max-height:280px;overflow:auto;color:#bac9d0}a{color:#81d7c0}#detail{padding:15px;border:1px solid #34534c;border-radius:6px}p{color:#91a4af}button{background:#203a33;color:#a8e5d2;border:1px solid #42685d;border-radius:4px;padding:7px 12px}
</style></head><body><h3>Evidence connections · lexical leads, not established relationships</h3><button id="minus">− Zoom</button> <button id="reset">Reset</button> <button id="plus">＋ Zoom</button><svg viewBox="0 0 850 540" aria-label="Source connection map"></svg><div id="detail" aria-live="polite">Select a node to inspect its excerpt and source path. Full source text is available below the map.</div><script>
const D=DATA,NS='http://www.w3.org/2000/svg',root=document.querySelector('svg');let zoom=1;
function add(tag,attrs,parent){let e=document.createElementNS(NS,tag);for(let [k,v] of Object.entries(attrs))e.setAttribute(k,v);parent.append(e);return e}
function inspect(r){let d=document.querySelector('#detail');d.replaceChildren();let h=document.createElement('h3');h.textContent=r.title;let p=document.createElement('p');p.textContent=r.kind+' · '+r.path;let pre=document.createElement('pre');pre.textContent=r.excerpt;let a=document.createElement('a');a.href='https://github.com/bartimoussmith-oss/therealwindycity/blob/main/'+r.path.split('/').map(encodeURIComponent).join('/');a.target='_blank';a.rel='noopener';a.textContent='Open repository source ↗';d.append(h,p,pre,a)}
function draw(){root.replaceChildren();let g=add('g',{transform:'translate(425 270) scale('+zoom+') translate(-425 -270)'},root);D.results.forEach((r,i)=>{let a=i/D.results.length*Math.PI*2,x=425+Math.cos(a)*300,y=270+Math.sin(a)*190;add('line',{x1:425,y1:270,x2:x,y2:y,stroke:'#3e6665','stroke-dasharray':'4 5'},g);let n=add('g',{class:'node',role:'button',tabindex:0,'aria-label':r.title},g);add('circle',{cx:x,cy:y,r:21,fill:'#1d303a',stroke:r.kind==='Meeting transcript'?'#85b2d5':'#d3b57e'},n);let t=add('text',{x,y:y+38,fill:'#d8e6e8','text-anchor':'middle'},n);t.textContent=r.title.length>36?r.title.slice(0,33)+'…':r.title;n.onclick=()=>inspect(r);n.onkeydown=e=>{if(e.key==='Enter')inspect(r)}});add('circle',{cx:425,cy:270,r:65,fill:'#203e35',stroke:'#81d7c0'},g);let t=add('text',{x:425,y:274,fill:'#cdf5e7','text-anchor':'middle'},g);t.textContent=D.topic.length>22?D.topic.slice(0,20)+'…':D.topic;}
document.querySelector('#minus').onclick=()=>{zoom=Math.max(.5,zoom-.2);draw()};document.querySelector('#plus').onclick=()=>{zoom=Math.min(2.5,zoom+.2);draw()};document.querySelector('#reset').onclick=()=>{zoom=1;draw()};draw();
</script></body></html>'''.replace('DATA',data)
