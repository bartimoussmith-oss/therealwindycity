(()=>{
 "use strict";
 const E=window.EVOLUTION_DATA;if(!E)return;
 const $=id=>document.getElementById(id);
 const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
 const href=u=>{try{const x=new URL(u);return x.protocol==="https:"?esc(x.href):"#"}catch{return "#"}};
 const a=(url,text)=>`<a href="${href(url)}" target="_blank" rel="noopener noreferrer">${esc(text)}</a>`;
 const ids=new Map(E.items.map(x=>[x.id,x])),reel=new Map();
 let pageNo=0,query="",topic="all",tab="ordinances";
 function save(data,name){const b=new Blob([JSON.stringify(data,null,2)],{type:"application/json"}),u=URL.createObjectURL(b),el=document.createElement("a");el.href=u;el.download=name;el.click();setTimeout(()=>URL.revokeObjectURL(u),30000)}
 function shell(title,content){
  clearInterval(S.timerId);S.phase="history";S.paused=true;document.onkeydown=null;closeModal();scrollTo(0,0);
  $("app").innerHTML=`${masthead(title)}<nav class="archive-nav"><button class="btn btn-ghost" id="evRounds">PLAYED ROUNDS</button><button class="btn btn-ghost" data-ev="ordinances">ORDINANCE TRACKER</button><button class="btn btn-ghost" data-ev="news">NEWS CONTEXT</button><button class="btn btn-ghost" data-ev="evidence">EVIDENCE LAB</button><button class="btn btn-ghost" id="evLive">LIVE WORKSPACE</button></nav>${content}${foot()}`;
  $("evRounds").insertAdjacentHTML("afterend",'<button class="btn btn-ghost" id="evTranscripts">TRANSCRIPTS</button>');
  $("evTranscripts").onclick=window.openTranscripts;
  $("evRounds").onclick=window.openHistory;$("evLive").onclick=()=>window.CivicLive.open();
  document.querySelectorAll("[data-ev]").forEach(b=>b.onclick=()=>open(b.dataset.ev));
  document.querySelector(`[data-ev="${tab}"]`)?.setAttribute("aria-current","page");
 }
 function open(t){tab=t;pageNo=0;query="";if(t==="news")return news();if(t==="evidence")return lab();tracker()}
 function tracker(){
  shell("ORDINANCE TRACKER",`<p class="archive-lede">Follow an ordinance across readings, committee referrals, postponement mentions and amendments. Each stage is a dated source observation, not an inferred legal outcome.</p>
   <div class="archive-note">${E.coverage.items.toLocaleString()} exact-title ordinance groups · ${E.coverage.observations.toLocaleString()} minutes observations. Revised titles can split the same proposal into multiple groups. Identical titles can also describe later proposals. IDs here are local grouping IDs, not official ordinance numbers.</div>
   <div class="archive-tools"><label>Find ordinance text<input type="search" id="itemQuery" placeholder="warrants, Cox Ranch, chapter…" value="${esc(query)}"></label><label>Topic<select id="itemTopic"><option value="all">All topics</option>${Object.entries(E.topics).map(([k,v])=>`<option value="${k}" ${topic===k?"selected":""}>${esc(v.label)}</option>`).join("")}</select></label></div><p id="itemCount" class="archive-meta" aria-live="polite"></p><div id="itemRows" class="archive-list"></div><div id="itemPaging"></div>`);
  $("itemQuery").oninput=x=>{query=x.target.value;pageNo=0;rows()};$("itemTopic").onchange=x=>{topic=x.target.value;pageNo=0;rows()};rows();
 }
 function rows(){
  const found=E.items.filter(x=>(topic==="all"||x.topics.includes(topic))&&x.title.toLowerCase().includes(query.toLowerCase())).sort((a,b)=>b.observations.at(-1).date.localeCompare(a.observations.at(-1).date));
  const pages=Math.max(1,Math.ceil(found.length/20));pageNo=Math.min(pageNo,pages-1);
  $("itemCount").textContent=`${found.length.toLocaleString()} matching exact-title groups. Empty news and video coverage is unknown, not evidence that coverage does not exist.`;
  $("itemRows").innerHTML=found.slice(pageNo*20,pageNo*20+20).map(x=>`<button class="archive-row" data-item="${x.id}"><span><span class="archive-meta">${x.observations[0].date} to ${x.observations.at(-1).date}</span><strong>${esc(x.title)}</strong><small>${x.observations.length} observed rounds · ${x.news.length} topic-context references · ${x.clips.length} video candidates</small></span><span aria-hidden="true">↗</span></button>`).join("")||'<p class="archive-empty">No matching title. OCR, changed titles and unparsed sources may hide a relevant item.</p>';
  $("itemPaging").innerHTML=`<div class="archive-pages"><button class="btn btn-ghost" id="itemPrev" ${!pageNo?"disabled":""}>PREVIOUS</button><span>Page ${pageNo+1} of ${pages}</span><button class="btn btn-ghost" id="itemNext" ${pageNo===pages-1?"disabled":""}>NEXT</button></div>`;
  $("itemPrev").onclick=()=>{pageNo--;rows()};$("itemNext").onclick=()=>{pageNo++;rows()};bind();
 }
 function article(x){return `<article class="archive-panel"><span class="archive-meta">${esc(x.outlet)} · ${esc(x.date)} · ${esc(x.kind)}</span><h3>${a(x.url,x.title)}</h3><p>${esc(x.summary)}</p>${x.dateNote?`<p>${esc(x.dateNote)}</p>`:""}<p class="archive-meta">${esc(x.association)}</p></article>`}
 function item(id){
  const x=ids.get(id);if(!x)return;tab="ordinances";
  shell("ORDINANCE HISTORY",`<button class="btn btn-ghost" id="itemBack">BACK TO TRACKER</button><section class="archive-panel"><h2>${esc(x.title)}</h2><p>${esc(x.grouping)}</p><p>Local grouping ${x.id}. A reading is not automatically passage; a committee recommendation is not council approval; a postponement or amendment mention is not proof that a motion carried.</p><button class="btn btn-ghost" id="exportItem">EXPORT SOURCED TIMELINE</button></section>
   <section class="archive-panel"><h2>Observed rounds</h2>${x.observations.map(o=>`<article class="archive-paper"><p class="archive-meta">${o.date} · ${esc(o.body)} · ${esc(o.evidenceType)}</p>${o.flags.map(f=>`<span class="archive-pill">${esc(f)}</span>`).join("")}<details><summary>Read the sourced excerpt / summary</summary><blockquote>${esc(o.excerpt)}</blockquote>${o.truncated?'<p class="archive-meta">Excerpt truncated; open the full source for all motion details.</p>':""}</details><p>${a(o.source,"Archived / primary record")} · ${a(o.officialSource,"Official minutes")}</p>${o.roundId?`<button class="btn btn-ghost" data-hround="${o.roundId}">OPEN MEETING ROUND</button>`:""}</article>`).join("")}</section>
   <h2 style="font-size:var(--text-lg)">Related news, not an authoritative lifecycle</h2><p class="archive-lede">${esc(x.coverage)} Articles are linked by topic, not asserted to cover each reading or exact version.</p>${x.news.map(id=>article(E.news.find(a=>a.id===id))).join("")||'<div class="archive-empty">News research pending for this item. No claim of zero coverage.</div>'}
   <section class="archive-panel"><h2>Meeting-video evidence candidates</h2><p>Caption keyword matches are discovery leads. Check the original video, speaker and surrounding context before citing or rendering a clip.</p>${clipCards(E.clips.filter(c=>x.clips.includes(c.id)))}</section>`);
  $("itemBack").onclick=tracker;$("exportItem").onclick=()=>save(x,`ordinance-${x.id}.json`);bind();
 }
 function news(){
  shell("NEWS CONTEXT",`<p class="archive-lede">Reporting from multiple outlets beside official announcements. News is a separate evidence layer: a report of a proposal, vote or future date is not interchangeable with the underlying minutes.</p><div class="archive-note">Seed coverage: ${E.coverage.articles} articles and ${E.coverage.officialAnnouncements} official announcement across six topics. This is not all articles, all outlets or all historical items. Shared reporting is not independent corroboration. Full copyrighted articles are not republished.</div><div class="archive-tools"><label>Search article metadata<input id="newsQuery" type="search" placeholder="outlet, topic or date"></label></div><div id="newsRows"></div><section class="archive-panel"><h2>The unsearched backlog is visible</h2><p>Export a research job for every imported meeting and ordinance group. These are pending searches, not finished article matches. No search provider is connected to this static app.</p><button class="btn btn-ghost" id="newsQueue">EXPORT COMPLETE RESEARCH QUEUE</button></section>`);
  const render=()=>{$("newsRows").innerHTML=E.news.filter(x=>JSON.stringify(x).toLowerCase().includes($("newsQuery").value.toLowerCase())).map(article).join("")||'<div class="archive-empty">No seed article matches. The wider web has not been exhaustively searched.</div>'};
  $("newsQuery").oninput=render;render();
  $("newsQueue").onclick=()=>save({status:"pending; not searched",jobs:[...E.items.map(x=>({type:"ordinance",id:x.id,query:"Cheyenne "+x.title,status:"pending",required:["publisher","url","publicationDate","originalReportingGroup","versionMatch","review"]})),...window.HISTORY_DATA.rounds.map(r=>({type:"meeting",id:r.id,query:`Cheyenne ${r.body} ${r.date} news`,status:"pending"}))]},"all-item-news-research-queue.json");
 }
 function clipCards(list){
  return list.length?list.map(c=>`<details><summary>${c.date} · ${esc(E.topics[c.topic].label)} · ${c.start}s–${c.end}s</summary><p>${esc(c.captionExcerpt)}</p><p>${a(c.url,"Open original video at this window")} · ${a(c.source,"Inspect machine captions")}</p><p class="archive-meta">${esc(c.status)}. Proposed 60-second window includes a context buffer, not a verified complete utterance.</p><button class="btn btn-ghost" data-clip="${c.id}">${reel.has(c.id)?"REMOVE FROM REEL":"ADD TO REVIEW REEL"}</button></details>`).join(""):'<p>No timestamped candidate indexed. Missing video is unknown.</p>';
 }
 function lab(){
  shell("EVIDENCE LAB",`<p class="archive-lede">Check document bytes, inspect provenance and build a reviewable clip list. A matching hash proves byte equality to a captured baseline, not that the document is true, official, unchanged before capture or legally authenticated.</p>
   <div class="archive-kpis"><div class="archive-kpi"><strong>${E.fingerprints.length}</strong><span>SHA-256 source baselines</span></div><div class="archive-kpi"><strong>${E.clips.length}</strong><span>unreviewed video windows</span></div><div class="archive-kpi"><strong>${reel.size}</strong><span>clips in this session's review reel</span></div><div class="archive-kpi"><strong>0</strong><span>independent timestamp attestations</span></div></div>
   <section class="archive-panel"><h2>Byte-level change verification</h2><p>The baselines hash the archived extracted text and caption bytes, not unexamined original PDFs. Supporting-document Git blob SHA-1 identifiers in round sources are a different hash scheme. No blockchain or trusted timestamp service is connected.</p><div class="archive-tools"><label>Captured source<select id="hashSource">${E.fingerprints.map(f=>`<option value="${f.id}">${esc(f.label)}</option>`).join("")}</select></label><label>Compare a local copy<input type="file" id="hashFile"></label></div><p class="archive-meta" id="hashBaseline"></p><button class="btn btn-ghost" id="checkRemote">CHECK CURRENT PUBLIC GITHUB BYTES</button> <button class="btn btn-ghost" id="hashManifest">EXPORT HASH MANIFEST</button><p id="hashResult" aria-live="polite"></p><p>Remote check contacts public GitHub only when you click. A changed hash triggers review; it does not prove a silent or malicious edit. This app does not automatically update or preserve observations between visits.</p></section>
   <section class="archive-panel"><h2>Video evidence and stitching handoff</h2><p>The app opens original timestamps and exports a machine-readable edit decision list. It does not pretend an unrendered list is a stitched video. The companion local renderer requires authorized source video files and reviewed segment boundaries.</p><button class="btn btn-ghost" id="exportReel">EXPORT CURRENT REVIEW REEL</button><p id="reelStatus" aria-live="polite"></p>${clipCards(E.clips)}</section>`);
  const selected=()=>E.fingerprints.find(f=>f.id===$("hashSource").value);
  function baseline(){const f=selected();$("hashBaseline").textContent=`SHA-256 ${f.sha256} · ${f.bytes.toLocaleString()} bytes · ${f.changeStatus} · observed ${f.observedAt}`;$("hashResult").textContent=""}
  baseline();$("hashSource").onchange=baseline;
  const digest=async bytes=>Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256",bytes))).map(x=>x.toString(16).padStart(2,"0")).join("");
  const compare=(hash,f)=>{if($("hashResult"))$("hashResult").textContent=`Baseline ${f.label} (${f.id}): ${hash===f.sha256?"MATCH: same bytes as captured baseline.":"DIFFERENT: review this byte change before updating evidence."} SHA-256 ${hash}`};
  $("hashFile").onchange=async ev=>{const baseline=selected();try{const f=ev.target.files[0];if(!f)return;if(f.size>25*1024*1024)throw Error("Local comparison limited to 25 MB.");compare(await digest(await f.arrayBuffer()),baseline)}catch(err){if($("hashResult"))$("hashResult").textContent=err.message}};
  $("checkRemote").onclick=async()=>{
   const f=selected(),button=$("checkRemote"),ctl=new AbortController(),cap=25*1024*1024;
   button.disabled=true;$("hashResult").textContent="Checking public source "+f.label+"…";
   const timer=setTimeout(()=>ctl.abort(),20000);
   try{
    const u=new URL(f.rawUrl);
    if(u.protocol!=="https:"||u.hostname!=="raw.githubusercontent.com"||u.username||u.password)throw Error("Source host not allowed");
    const r=await fetch(u.href,{cache:"no-store",credentials:"omit",referrerPolicy:"no-referrer",signal:ctl.signal,redirect:"error"});
    if(!r.ok)throw Error("Public source returned HTTP "+r.status);
    if(Number(r.headers.get("content-length"))>cap)throw Error("Source exceeds 25 MB cap");
    if(!r.body)throw Error("Streaming response unavailable");
    const reader=r.body.getReader(),chunks=[];let total=0;
    for(;;){const {done,value}=await reader.read();if(done)break;total+=value.byteLength;if(total>cap){await reader.cancel();throw Error("Source exceeds 25 MB cap")}chunks.push(value)}
    const bytes=new Uint8Array(total);let at=0;for(const c of chunks){bytes.set(c,at);at+=c.length}
    compare(await digest(bytes),f);
   }catch(err){if($("hashResult"))$("hashResult").textContent="Check unavailable for "+f.label+": "+err.message+". No change conclusion drawn."}
   finally{clearTimeout(timer);ctl.abort();button.disabled=false}
  };
  $("hashManifest").onclick=()=>save({algorithm:"SHA-256",baselineOnly:true,trustedTimestamp:false,sources:E.fingerprints,observationLedger:E.fingerprintLedger},"source-fingerprint-manifest.json");
  $("exportReel").onclick=()=>{save({schemaVersion:1,rendered:false,rightsConfirmed:false,contextPolicy:"Verify full surrounding context. Visible hard cuts; no synthetic speech.",clips:[...reel.values()].map(c=>({...c,reviewed:false,localVideoFile:null}))},"video-review-edit-list.json");$("reelStatus").textContent=`Exported ${reel.size} review candidates. No footage has been downloaded or rendered.`};bind();
 }
 function bind(){
  document.querySelectorAll("[data-item]").forEach(b=>b.onclick=()=>item(b.dataset.item));
  document.querySelectorAll("[data-hround]").forEach(b=>b.onclick=()=>window.openHistoryRound(b.dataset.hround));
  document.querySelectorAll("[data-clip]").forEach(b=>b.onclick=()=>{const c=E.clips.find(c=>c.id===b.dataset.clip);if(reel.has(c.id))reel.delete(c.id);else reel.set(c.id,c);b.textContent=reel.has(c.id)?"REMOVE FROM REEL":"ADD TO REVIEW REEL";const status=$("reelStatus");if(status)status.textContent=`${reel.size} candidate windows in the session reel.`});
 }
 function roundSection(id){
  const obs=E.observations.filter(o=>o.roundId===id);
  return obs.length?`<section class="archive-panel"><h2>Ordinances observed in this round</h2><p>These are rule-extracted stage mentions. Inspect the motion text; do not equate a mention with an adopted action.</p>${obs.map(o=>`<button class="archive-person-link" data-item="${o.itemId}">${esc(ids.get(o.itemId).title)}</button><p class="archive-meta">${o.flags.map(esc).join(" · ")}</p>`).join("")}</section>`:"";
 }
 window.CivicEvolution={open,bind,roundSection};
})();
