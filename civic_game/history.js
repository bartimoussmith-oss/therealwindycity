/* Historical ledger: recorded participation is immutable and never simulated. */
(()=>{
 "use strict";
 const D=window.HISTORY_DATA;
 if(!D)return;
 const players=new Map(D.players.map(p=>[p.id,p]));
 const rounds=new Map(D.rounds.map(r=>[r.id,r]));
 const V={tab:"rounds",q:"",year:"all",body:"all",status:"played",sort:"name",page:0,limit:25};
 const $=id=>document.getElementById(id);
 const e=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
 const n=x=>Number(x||0).toLocaleString();
 const safe=u=>{try{const x=new URL(u);return x.protocol==="https:"?e(x.href):"#"}catch{return "#"}};
 const link=(u,label)=>`<a href="${safe(u)}" target="_blank" rel="noopener noreferrer">${e(label)}</a>`;
 const pname=id=>players.get(id)?.name||"Name unavailable";
 const transcriptSources=r=>r.sources.filter(s=>s.type==="transcript");
 const transcriptMap=new Map();
 D.rounds.forEach(r=>transcriptSources(r).forEach(s=>{
  const old=transcriptMap.get(s.url);
  if(!old||(old.round.status!=="played"&&r.status==="played"))transcriptMap.set(s.url,{source:s,round:r});
 }));
 const transcriptIndex=window.TRANSCRIPTS_DATA?window.TRANSCRIPTS_DATA.records.map(x=>({...x,round:{date:x.date||"",body:x.body,title:x.title,id:x.roundIds[0]||null},source:x.sources[0]})):[...transcriptMap.values()].sort((a,b)=>b.round.date.localeCompare(a.round.date)||a.round.body.localeCompare(b.round.body));
 const transcriptRecords=new Map(transcriptIndex.filter(x=>x.id).map(x=>[x.id,x]));
 const catalogByRound=new Map();
 for(const record of transcriptRecords.values())for(const id of record.roundIds){if(!catalogByRound.has(id))catalogByRound.set(id,[]);catalogByRound.get(id).push(record)}
 const availableTranscriptSources=r=>[...new Map([...transcriptSources(r),...(catalogByRound.get(r.id)||[]).map(x=>x.sources[0])].map(s=>[s.url,s])).values()];
 const transcriptCache=new Map(),transcriptInflight=new Map();
 const T={q:"",year:"all",body:"all"};
 function enter(){clearInterval(S.timerId);S.phase="history";S.paused=true;document.onkeydown=null;closeModal();window.scrollTo(0,0)}
 function base(title,body){
  enter();
  $("app").innerHTML=`${masthead(title)}<div class="archive-nav">
   <button class="btn btn-ghost" data-tab="rounds" ${V.tab==="rounds"?'aria-current="page"':""}>PLAYED ROUNDS</button>
   <button class="btn btn-ghost" data-tab="transcripts" ${V.tab==="transcripts"?'aria-current="page"':""}>TRANSCRIPTS</button>
   <button class="btn btn-ghost" data-tab="players" ${V.tab==="players"?'aria-current="page"':""}>PARTICIPANT REGISTER</button>
   <button class="btn btn-ghost" data-tab="coverage" ${V.tab==="coverage"?'aria-current="page"':""}>COVERAGE & SCORING</button>
   <button class="btn btn-ghost" data-evolve="ordinances">ORDINANCE TRACKER</button>
   <button class="btn btn-ghost" data-evolve="news">NEWS CONTEXT</button>
   <button class="btn btn-ghost" data-evolve="evidence">EVIDENCE LAB</button>
   <button class="btn btn-ghost" id="liveWorkspace">LIVE WORKSPACE</button>
   <button class="btn btn-ghost" id="historyHome">PRACTICE GAME</button>
  </div>${body}${foot()}`;
  document.querySelectorAll("[data-tab]").forEach(b=>b.onclick=()=>{V.tab=b.dataset.tab;V.page=0;V.q="";render()});
  $("historyHome").onclick=()=>showTitle();
  document.querySelectorAll("[data-evolve]").forEach(b=>b.onclick=()=>window.CivicEvolution.open(b.dataset.evolve));
  $("liveWorkspace").onclick=()=>window.CivicLive.open();
 }
 function kpis(){
  const c=D.coverage;
  return `<div class="archive-kpis">
   <div class="archive-kpi"><strong>${n(c.playedRounds)}</strong><span>historical rounds supported</span></div>
   <div class="archive-kpi"><strong>${n(c.players)}</strong><span>recorded name labels</span></div>
   <div class="archive-kpi"><strong>${n(c.roundPlayerAppearances)}</strong><span>round / commenter credits</span></div>
   <div class="archive-kpi"><strong>${n(c.indexedOnlyRounds)}</strong><span>index-only rounds, unscored</span></div>
  </div>`;
 }
 function render(){
  if(V.tab==="transcripts")return transcripts();
  if(V.tab==="players")return register();
  if(V.tab==="coverage")return coverage();
  base("PLAYED ROUNDS",`<p class="archive-lede">These meetings already happened. The people, dates and public-comment entries come from the archive, not game play. Replay the documentary sequence or inspect a participant's recorded appearances.</p>${kpis()}
   <div class="archive-note">Snapshot through ${e(D.asOf)}. This is a partial, source-bounded import, not a complete census. Historical participation credits are game-generated; no wins, losses, composure or truthfulness scores are assigned to real people.</div>
   <div class="archive-tools">
    <label>Search meetings or commenter names<input id="roundSearch" type="search" placeholder="Charles Miller, council, 2026…" value="${e(V.q)}"></label>
    <label>Year<select id="roundYear"><option value="all">All years</option>${[...new Set(D.rounds.map(r=>r.date.slice(0,4)))].sort().reverse().map(y=>`<option ${V.year===y?"selected":""}>${y}</option>`).join("")}</select></label>
    <label>Meeting body<select id="roundBody"><option value="all">All bodies</option>${[...new Set(D.rounds.map(r=>r.body))].sort().map(b=>`<option ${V.body===b?"selected":""}>${e(b)}</option>`).join("")}</select></label>
    <label>Evidence status<select id="roundStatus"><option value="all">All indexed rounds</option><option value="played" ${V.status==="played"?"selected":""}>Supported historical rounds</option><option value="indexed" ${V.status==="indexed"?"selected":""}>Index only / unscored</option></select></label>
   </div><p class="archive-meta" id="roundResults" aria-live="polite"></p><div class="archive-list" id="roundList"></div><div id="roundPages"></div>`);
  $("roundSearch").oninput=ev=>{V.q=ev.target.value;V.page=0;renderRoundRows()};
  for(const [id,key] of [["roundYear","year"],["roundBody","body"],["roundStatus","status"]]){
   $(id).onchange=ev=>{V[key]=ev.target.value;V.page=0;renderRoundRows()};
  }
  renderRoundRows();
 }
 function pagination(id,count,refresh){
  const total=Math.max(1,Math.ceil(count/V.limit));V.page=Math.min(V.page,total-1);
  $(id).innerHTML=`<div class="archive-pages"><button class="btn btn-ghost" id="prevPage" ${V.page===0?"disabled":""}>PREVIOUS</button><span class="archive-meta">Page ${V.page+1} of ${total}</span><button class="btn btn-ghost" id="nextPage" ${V.page>=total-1?"disabled":""}>NEXT</button></div>`;
  $("prevPage").onclick=()=>{V.page--;refresh()};$("nextPage").onclick=()=>{V.page++;refresh()};
 }
 function renderRoundRows(){
  const q=V.q.trim().toLowerCase();
  const found=D.rounds.filter(r=>(V.year==="all"||r.date.startsWith(V.year))&&(V.body==="all"||r.body===V.body)&&(V.status==="all"||r.status===V.status)&&(!q||[r.date,r.body,r.title,...r.participants.map(p=>pname(p.playerId))].join(" ").toLowerCase().includes(q)));
  pagination("roundPages",found.length,renderRoundRows);
  $("roundResults").textContent=`${n(found.length)} matching rounds. “No credited roster” means not extracted, not nobody spoke.`;
  $("roundList").innerHTML=found.slice(V.page*V.limit,(V.page+1)*V.limit).map(r=>`<button class="archive-row ${r.status}" data-round="${r.id}">
   <span><span class="archive-meta">${e(r.date)}</span><strong>${e(r.body)}</strong><small>${r.participantCount?n(r.participantCount)+" named commenter labels · "+n(r.commentEntries)+" recorded entries":"No credited roster extracted"} · ${n(r.sourceCount)} source ${r.sourceCount===1?"reference":"references"}</small>
   <span class="archive-pill ${r.status}">${r.status==="played"?"HISTORICAL ROUND":"INDEX ONLY · UNSCORED"}</span> <span class="archive-pill ${availableTranscriptSources(r).length?"transcript-available":""}">${availableTranscriptSources(r).length?"TRANSCRIPT AVAILABLE":"NO TRANSCRIPT LINKED"}</span>${r.issues.length?`<span class="archive-pill review">SOURCE REVIEW</span>`:""}</span><span aria-hidden="true">↗</span></button>`).join("")||'<div class="archive-empty">No matching rounds. Clear the search or broaden the filters.</div>';
  document.querySelectorAll("[data-round]").forEach(b=>b.onclick=()=>round(b.dataset.round));
 }
 function transcripts(){
  base("TRANSCRIPT LIBRARY",`<p class="archive-lede">${n(transcriptIndex.length)} transcript records, now readable inside the game. Search source titles, date labels and meeting bodies, or browse undated material.</p>
   <div class="archive-note">Machine captions and legacy transcripts, not certified verbatim records. Words, names and dates may be wrong. The collection includes interviews and other civic media as well as meetings; record count is not unique meeting count. Search covers metadata, not the entire text of every transcript. Minutes and summaries are not counted as transcripts.</div>
   ${window.TRANSCRIPTS_DATA?`<details class="archive-panel"><summary>Corpus coverage and deduplication</summary><p>${e(window.TRANSCRIPTS_DATA.scope)}</p><p>${n(window.TRANSCRIPTS_DATA.stats.sourceEntriesInspected)} source entries inspected · ${n(window.TRANSCRIPTS_DATA.stats.duplicateOrLinkedRepresentations)} duplicate or linked representations merged · ${n(window.TRANSCRIPTS_DATA.stats.unresolvedDates)} unresolved dates · ${n(window.TRANSCRIPTS_DATA.stats.shortOrPartial)} short or possibly partial records.</p><p>Drive reconciliation: ${n(window.TRANSCRIPTS_DATA.stats.driveTranscriptCandidates)} caption files inspected; ${n(window.TRANSCRIPTS_DATA.stats.driveTranscriptMatchedPublicVideo)} matched to public City video metadata; ${n(window.TRANSCRIPTS_DATA.stats.driveTranscriptSourceUnresolved+window.TRANSCRIPTS_DATA.stats.driveTranscriptTitleConflict)} withheld because their public-source match remains unresolved.</p><p>This is a bounded snapshot, not every private Drive file or a completed census. Public aggregate files also contain legal research and indexes; those sections are excluded.</p></details>`:""}
   <div class="archive-tools"><label>Find a transcript<input id="transcriptSearch" type="search" placeholder="2026-09-14, council, finance…" value="${e(T.q)}"></label>
   <label>Source year label<select id="transcriptYear"><option value="all">All years / undated</option>${[...new Set(transcriptIndex.map(x=>x.round.date.slice(0,4)))].filter(Boolean).sort().reverse().map(y=>`<option value="${e(y)}" ${T.year===y?"selected":""}>${e(y)}</option>`).join("")}<option value="unknown" ${T.year==="unknown"?"selected":""}>Date unresolved</option></select></label>
   <label>Meeting body<select id="transcriptBody"><option value="all">All bodies</option>${[...new Set(transcriptIndex.map(x=>x.round.body))].sort().map(b=>`<option value="${e(b)}" ${T.body===b?"selected":""}>${e(b)}</option>`).join("")}</select></label>
   <button class="btn btn-ghost" id="clearTranscriptFilters">CLEAR FILTERS</button></div>
   <p id="transcriptResults" class="archive-meta" aria-live="polite"></p><button class="btn btn-ghost" id="exportTranscriptCatalog">EXPORT CATALOG & COVERAGE</button><div class="archive-list" id="transcriptList"></div><div id="transcriptPages"></div>`);
  $("transcriptSearch").oninput=ev=>{T.q=ev.target.value;V.page=0;transcriptRows()};
  for(const [id,key] of [["transcriptYear","year"],["transcriptBody","body"]])$(id).onchange=ev=>{T[key]=ev.target.value;V.page=0;transcriptRows()};
  $("clearTranscriptFilters").onclick=()=>{T.q="";T.year="all";T.body="all";V.page=0;transcripts()};
  $("exportTranscriptCatalog").onclick=()=>download(window.TRANSCRIPTS_DATA||{records:transcriptIndex},"transcript-catalog-and-coverage.json");
  transcriptRows();
 }
 function transcriptRows(){
  const q=T.q.trim().toLowerCase();
  const found=transcriptIndex.filter(x=>(T.year==="all"||(T.year==="unknown"?!x.round.date:x.round.date.startsWith(T.year)))&&(T.body==="all"||x.round.body===T.body)&&(!q||`${x.round.date} ${x.round.body} ${x.round.title}`.toLowerCase().includes(q)));
  pagination("transcriptPages",found.length,transcriptRows);
  $("transcriptResults").textContent=`${n(found.length)} matching transcript records of ${n(transcriptIndex.length)}. Source date labels first; unresolved dates at the end.`;
  $("transcriptList").innerHTML=found.slice(V.page*V.limit,(V.page+1)*V.limit).map(x=>`<article class="archive-panel transcript-card"><span class="archive-meta">${x.round.date?"SOURCE DATE LABEL · "+e(x.round.date):"DATE UNRESOLVED"}</span><h2>${e(x.title||x.round.body)}</h2><p>${e(x.round.body)} · ${e(x.kind||"Machine-generated captions")}${x.words?" · "+n(x.words)+" words":""}${x.shortOrPartial?" · SHORT / POSSIBLY PARTIAL":""}</p><div class="transcript-actions">${x.id?`<button class="btn btn-primary" data-read-transcript="${e(x.id)}">READ TRANSCRIPT</button>`:""}${link(x.source.url,x.id?"OPEN SOURCE":"OPEN FULL TRANSCRIPT")}${x.round.id?`<button class="btn btn-ghost" data-transcript-round="${e(x.round.id)}">VIEW MEETING RECORD</button>`:""}${(x.video||x.source.video)?link(x.video||x.source.video,"WATCH SOURCE VIDEO"):""}</div></article>`).join("")||'<div class="archive-empty">No transcripts match these filters. Clear filters to see the available archive. A missing transcript does not mean the meeting did not happen.</div>';
  document.querySelectorAll("[data-transcript-round]").forEach(b=>b.onclick=()=>round(b.dataset.transcriptRound));
  document.querySelectorAll("[data-read-transcript]").forEach(b=>b.onclick=()=>readTranscript(b.dataset.readTranscript));
 }
 async function loadTranscript(record){
  const path=record.chunk;
  if(!/^transcripts\/part-\d{3}\.json$/.test(path))throw new Error("Invalid local transcript path.");
  if(transcriptCache.has(path))return transcriptCache.get(path);
  if(transcriptInflight.has(path))return transcriptInflight.get(path);
  if(transcriptInflight.size>=2)throw new Error("Two transcript files are loading. Please try again shortly.");
  const task=(async()=>{
   const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),20000);
   try{
    const res=await fetch(path,{signal:controller.signal,credentials:"omit",referrerPolicy:"no-referrer",redirect:"error"});
    if(!res.ok||!res.body)throw new Error("The local transcript file could not be loaded.");
    if(Number(res.headers.get("content-length"))>4000000)throw new Error("Transcript file exceeds the size limit.");
    const reader=res.body.getReader(),chunks=[];let size=0;
    while(true){const item=await reader.read();if(item.done)break;size+=item.value.byteLength;if(size>4000000){await reader.cancel();throw new Error("Transcript file exceeds the size limit.")}chunks.push(item.value)}
    const bytes=new Uint8Array(size);let offset=0;for(const chunk of chunks){bytes.set(chunk,offset);offset+=chunk.byteLength}
    const parsed=JSON.parse(new TextDecoder().decode(bytes));
    if(!parsed||Array.isArray(parsed)||typeof parsed!=="object")throw new Error("Invalid transcript file.");
    transcriptCache.set(path,parsed);while(transcriptCache.size>2)transcriptCache.delete(transcriptCache.keys().next().value);
    return parsed;
   }finally{clearTimeout(timer)}
  })();
  transcriptInflight.set(path,task);
  try{return await task}finally{transcriptInflight.delete(path)}
 }
 function showTranscriptText(target,text){
  const fragment=document.createDocumentFragment(),pattern=/\[\[([0-9:]{4,12})\]\]\((https:\/\/www\.youtube\.com\/watch\?[^\s)]+)\)/g;
  let last=0,count=0,match;
  while((match=pattern.exec(text))&&count<5000){
   fragment.append(document.createTextNode(text.slice(last,match.index)));
   const url=new URL(match[2]);
   if(url.hostname==="www.youtube.com"&&/^[A-Za-z0-9_-]{11}$/.test(url.searchParams.get("v")||"")&&/^\d+s?$/.test(url.searchParams.get("t")||"")){
    const a=document.createElement("a");a.href=url.href;a.target="_blank";a.rel="noopener noreferrer";a.referrerPolicy="no-referrer";a.className="transcript-timestamp";a.textContent=`[${match[1]}]`;fragment.append(a);
   }else fragment.append(document.createTextNode(match[0]));
   last=pattern.lastIndex;count++;
  }
  fragment.append(document.createTextNode(text.slice(last)));target.replaceChildren(fragment);
 }
 function readTranscript(id){
  const r=transcriptRecords.get(id);if(!r)return;
  V.tab="transcripts";
  base("TRANSCRIPT READER",`<button class="btn btn-ghost" id="backTranscriptLibrary">BACK TO TRANSCRIPTS</button>
   <section class="archive-panel"><span class="archive-meta">${r.date?"SOURCE DATE LABEL · "+e(r.date):"DATE UNRESOLVED"}</span><h2>${e(r.title)}</h2><p>${e(r.body)} · ${e(r.kind)} · ${n(r.words)} source words</p>
   <div class="archive-note">Unverified machine-caption / legacy text. Speaker names, dates and words may be wrong. This is not a certified transcript or a finding about anyone's conduct. Source date labels are not independently reconciled. ${r.shortOrPartial?"This record is short and may cover only part of the source. ":""}${r.redacted?"Contact details or private-source URLs were omitted from the displayed representation. ":""}Reading does not award or change participation credits.</div>
   <details><summary>Provenance and source versions (${n(r.sources.length)})</summary><ul class="archive-source-list">${r.sources.map(s=>`<li>${link(s.url,s.label)}${s.recordId?" · database record "+e(s.recordId):""}${s.section?" · section: "+e(s.section):""}</li>`).join("")}</ul><p class="archive-meta">Displayed-text SHA-256: <span class="transcript-digest">${e(r.displaySha256)}</span>. This checks representation bytes, not authenticity, accuracy or a trusted timestamp.</p></details>
   <p id="transcriptLoadStatus" role="status">Loading this transcript from the app's public-source snapshot…</p>
   <button class="btn btn-ghost" id="exportTranscript" disabled>EXPORT TRANSCRIPT JSON</button></section>
   <section class="archive-panel transcript-reading"><h2>Transcript text</h2><p>Use your browser's Find command to search within this record. Timestamp information is present only where supplied by the source.</p><pre id="transcriptText" class="transcript-text" tabindex="0" aria-label="Transcript text">Loading…</pre></section>`);
  $("backTranscriptLibrary").onclick=transcripts;
  const target=$("transcriptText"),status=$("transcriptLoadStatus"),button=$("exportTranscript");
  loadTranscript(r).then(async data=>{
   const text=data[r.id];if(typeof text!=="string"){transcriptCache.delete(r.chunk);throw new Error("This transcript is absent from its data file.")}
   const digest=await crypto.subtle.digest("SHA-256",new TextEncoder().encode(text));
   const hex=[...new Uint8Array(digest)].map(x=>x.toString(16).padStart(2,"0")).join("");
   if(hex!==r.displaySha256){transcriptCache.delete(r.chunk);throw new Error("The transcript bytes do not match the catalog fingerprint. Reopen the record to retry.")}
   if(!target.isConnected)return;
   showTranscriptText(target,text);status.textContent="Loaded. Archived-text fingerprint matches the catalog; source accuracy remains unverified.";
   button.disabled=false;button.onclick=()=>{const {round,source,...metadata}=r;download({metadata,text,privacy:"Caption representation; source/provenance and accuracy unverified; review before republishing."},`transcript-${r.id}.json`)};
  }).catch(error=>{if(!target.isConnected)return;target.textContent="Transcript text could not be loaded. You can still open the public source under Provenance and source versions.";status.textContent=error.name==="AbortError"?"Transcript load timed out. Open this record again to retry.":error.message});
 }
 function roster(r){
  return r.participants.length?`<div class="archive-list">${[...r.participants].sort((a,b)=>pname(a.playerId).localeCompare(pname(b.playerId))).map(p=>`<button class="archive-row" data-person="${p.playerId}"><span><strong>${e(pname(p.playerId))}</strong><small>${n(p.entries)} distinct named public-comment ${p.entries===1?"entry":"entries"}</small></span><span class="archive-points">${n(p.points)}<small>participation credits</small></span></button>`).join("")}</div>`:
   '<div class="archive-empty">No scored participant roster has been extracted for this meeting. That does not establish that nobody commented.</div>';
 }
 function bindPeople(){document.querySelectorAll("[data-person]").forEach(b=>b.onclick=()=>person(b.dataset.person))}
 function evidence(ev,index){
  return `<article class="archive-paper"><span class="archive-meta">ENTRY ${index+1} · MINUTES EXCERPT, NOT A VERBATIM SPEECH</span>
   ${ev.context?`<details><summary>Agenda context as recorded</summary><p class="archive-meta">${e(ev.context)}</p></details>`:""}
   <blockquote>${e(ev.excerpt)}</blockquote><p class="archive-meta">${ev.names.map(id=>e(pname(id))).join(" · ")}</p>
   ${link(ev.source+(ev.line?"#L"+ev.line:""),"Inspect the archived minutes passage")}</article>`;
 }
 function round(id){
  const r=rounds.get(id);if(!r)return;
  V.tab="rounds";
  base("THE HISTORICAL RECORD",`<div class="archive-header"><button class="btn btn-ghost" id="backRounds">BACK TO ROUNDS</button><span class="archive-pill ${r.status}">${r.status==="played"?"HISTORICAL ROUND":"INDEX ONLY · UNSCORED"}</span></div>
   <div class="archive-panel"><span class="archive-meta">${e(r.date)}</span><h2>${e(r.body)}</h2><p>${e(r.title)}</p>
   <p>${n(r.sourceCount)} source references · ${n(r.participantCount)} named commenter labels · ${n(r.commentEntries)} recorded public-comment entries.</p>
   <div class="archive-note">This is a documentary record, not a generated reenactment. No imported result or vote count is asserted unless explicitly shown by the source. Credits reflect recorded participation only.</div>
   ${r.events.length?'<button class="btn btn-primary" id="replayRecord">REPLAY THE RECORD</button>':""}
   <button class="btn btn-ghost" id="exportRound">EXPORT THIS ROUND</button></div>
   <section class="archive-panel transcript-panel"><h2>${availableTranscriptSources(r).length?"Meeting transcript":"No transcript linked for this meeting"}</h2>
   ${availableTranscriptSources(r).length?`<p>Read available transcript records in the game or inspect the public sources. Machine-generated captions can contain word, date and speaker errors; not every record is timestamped, and these are not certified minutes.</p>${(catalogByRound.get(r.id)||[]).map((x,i)=>`<p class="archive-meta">${e(x.title)}</p><button class="btn btn-primary" data-read-transcript="${e(x.id)}">READ TRANSCRIPT${(catalogByRound.get(r.id)||[]).length>1?" "+(i+1):""}</button>`).join("")}<div class="transcript-actions">${availableTranscriptSources(r).map(s=>link(s.url,"OPEN SOURCE")).join("")}</div>`:'<p>This imported record may contain minutes, summaries or other sources below. Those are not a verbatim transcript.</p>'}
   <button class="btn btn-ghost" id="roundTranscripts">BROWSE ALL TRANSCRIPTS</button></section>
   ${r.issues.length?`<div class="archive-panel"><h3>Source limitations</h3>${r.issues.map(x=>`<p>${e(x)}</p>`).join("")}</div>`:""}
   ${window.CivicEvolution?window.CivicEvolution.roundSection(r.id):""}
   <section class="archive-panel"><h2>Who took the public-comment floor</h2>${roster(r)}</section>
   <section class="archive-panel"><h2>The participation evidence</h2><p>Names are credited only from explicit public-comment lists in date-validated minutes. A list identifies participation, not what a person argued.</p>${r.events.map(evidence).join("")||"<p>No eligible minutes passages extracted. Scores are withheld, not zero.</p>"}</section>
   ${r.candidates.length?`<section class="archive-panel"><h2>Caption identity review</h2><p>Machine captions can misspell names or include staff introductions. These are review leads, not additional scored participants.</p>${r.candidates.map(c=>`<details><summary>${e(c.label)} · ${e(c.timestamp||"timestamp unavailable")}</summary><p>${e(c.status)}. ${c.matchedPlayer?"Literal match to a credited name in this round.":"No identity / public-comment role confirmation. No points assigned."}</p>${link(c.video,"Check the meeting video")} · ${link(c.source,"Caption archive")}</details>`).join("")}</section>`:""}
   <section class="archive-panel"><h2>Source documents</h2><ul class="archive-source-list">${r.sources.map(s=>`<li>${link(s.url,s.label)} <span class="archive-meta">[${e(s.type)}]</span>${s.officialUrl?" · "+link(s.officialUrl,"Official minutes"):s.video?" · "+link(s.video,"Meeting video"):""}${s.sha?`<details><summary>Content fingerprint</summary><span class="archive-meta">${e(s.sha)}</span></details>`:""}</li>`).join("")}</ul></section>
   <button class="btn btn-ghost" id="correctionRound">EXPORT A CORRECTION DRAFT</button>`);
  $("backRounds").onclick=render;bindPeople();
  $("roundTranscripts").onclick=window.openTranscripts;
  document.querySelectorAll("[data-read-transcript]").forEach(b=>b.onclick=()=>readTranscript(b.dataset.readTranscript));
  window.CivicEvolution?.bind();
  if($("replayRecord"))$("replayRecord").onclick=()=>replay(id,0);
  $("exportRound").onclick=()=>download({round:r,players:r.participants.map(p=>players.get(p.playerId)),methodology:D.methodology},`round-${r.date}-${r.id}.json`);
  $("correctionRound").onclick=()=>correction({roundId:r.id,date:r.date,body:r.body,sources:r.sources.map(s=>s.url)});
 }
 function replay(id,i){
  const r=rounds.get(id);if(!r||!r.events.length)return;
  const ev=r.events[i];V.tab="rounds";
  base("REPLAY THE RECORD",`<div class="archive-header"><span class="archive-event-index">${e(r.date)} · ENTRY ${i+1} / ${r.events.length}</span><button class="btn btn-ghost" id="replayExit">EXIT REPLAY</button></div>
   <p class="archive-lede">${e(r.body)}. Entries follow the archived minutes order, not inferred speaking duration. Names on a shared entry are not asserted to have spoken in that order.</p>
   <div class="archive-replay-progress"><i style="width:${(i+1)/r.events.length*100}%"></i></div>
   ${evidence(ev,i)}
   <div class="archive-panel"><h3>Recorded participants at this entry</h3>${ev.names.map(pid=>`<button class="archive-person-link" data-person="${pid}">${e(pname(pid))}</button>`).join(" · ")}<p>The historical ledger does not change when you replay it. Participation credits cannot be farmed by clicking.</p></div>
   <div class="archive-pages"><button class="btn btn-ghost" id="entryPrev" ${i===0?"disabled":""}>PREVIOUS ENTRY</button><button class="btn btn-primary" id="entryNext">${i===r.events.length-1?"CLOSE HISTORICAL ROUND":"NEXT RECORDED ENTRY"}</button></div>`);
  $("replayExit").onclick=()=>round(id);$("entryPrev").onclick=()=>replay(id,i-1);
  $("entryNext").onclick=()=>i===r.events.length-1?round(id):replay(id,i+1);bindPeople();
 }
 function register(){
  base("THE PARTICIPANTS",`<p class="archive-lede">A register of the people named in eligible public-comment lists. These are recorded name labels, not verified accounts. Similar spellings stay separate until reviewed; equal spellings can still refer to different people.</p>
   <div class="archive-note">Participation credits = 100 per documented round + 10 for each additional distinct public-comment entry in that round. They measure recorded participation in this imported corpus, not civic worth, correctness, influence or a person's total real-life activity.</div>
   <div class="archive-tools"><label>Find a recorded name<input id="personSearch" type="search" placeholder="Search the participant register" value="${e(V.q)}"></label><label>Order<select id="personSort"><option value="name">Name A–Z</option><option value="rounds" ${V.sort==="rounds"?"selected":""}>Documented rounds</option><option value="points" ${V.sort==="points"?"selected":""}>Participation credits</option></select></label></div><p class="archive-meta" id="personResults" aria-live="polite"></p><div class="archive-list" id="personList"></div><div id="personPages"></div>`);
  $("personSearch").oninput=ev=>{V.q=ev.target.value;V.page=0;personRows()};
  $("personSort").onchange=ev=>{V.sort=ev.target.value;V.page=0;personRows()};personRows();
 }
 function personRows(){
  const found=D.players.filter(p=>p.name.toLowerCase().includes(V.q.trim().toLowerCase())).sort((a,b)=>V.sort==="rounds"?b.roundCount-a.roundCount||a.name.localeCompare(b.name):V.sort==="points"?b.points-a.points||a.name.localeCompare(b.name):a.name.localeCompare(b.name));
  pagination("personPages",found.length,personRows);$("personResults").textContent=`${n(found.length)} recorded name labels. Corpus-limited participation, not a global leaderboard.`;
  $("personList").innerHTML=found.slice(V.page*V.limit,(V.page+1)*V.limit).map(p=>`<button class="archive-row" data-person="${p.id}"><span><strong>${e(p.name)}</strong><small>${n(p.roundCount)} documented rounds · ${n(p.entries)} public-comment entries</small></span><span class="archive-points">${n(p.points)}<small>participation credits</small></span></button>`).join("")||'<div class="archive-empty">No recorded name matches. Missing from this import does not mean the person never participated.</div>';bindPeople();
 }
 function person(id){
  const p=players.get(id);if(!p)return;V.tab="players";
  const appearances=p.rounds.map(x=>({...x,round:rounds.get(x.roundId)})).sort((a,b)=>b.round.date.localeCompare(a.round.date));
  base("PARTICIPANT RECORD",`<button class="btn btn-ghost" id="backPeople">BACK TO REGISTER</button><section class="archive-panel"><h2>${e(p.name)}</h2>
   <div class="archive-kpis"><div class="archive-kpi"><strong>${n(p.points)}</strong><span>game-generated participation credits</span></div><div class="archive-kpi"><strong>${n(p.roundCount)}</strong><span>documented historical rounds</span></div><div class="archive-kpi"><strong>${n(p.entries)}</strong><span>named public-comment entries</span></div><div class="archive-kpi"><strong>—</strong><span>truthfulness / influence: not rated</span></div></div>
   <p>${e(p.identity)} Spelling variations are not automatically merged. Official/staff titles in other records do not transfer a role into these public-comment entries.</p>
   <div class="archive-note">Not a user account, endorsement or claim that this person played the app. These credits are computed from the imported minutes only. Attendance and comments missing from the archive are unknown, not zero.</div>
   <button class="btn btn-ghost" id="exportPerson">EXPORT PARTICIPATION RECORD</button> <button class="btn btn-ghost" id="correctPerson">EXPORT CORRECTION DRAFT</button></section>
   <h2 style="font-size:var(--text-lg);margin:24px 0 12px">Historical appearances</h2><div class="archive-list">${appearances.map(a=>`<button class="archive-row played" data-round="${a.roundId}"><span><span class="archive-meta">${e(a.round.date)}</span><strong>${e(a.round.body)}</strong><small>${n(a.entries)} named entries · inspect source passages</small></span><span class="archive-points">+${n(a.points)}<small>participation credits</small></span></button>`).join("")}</div>`);
  $("backPeople").onclick=register;document.querySelectorAll("[data-round]").forEach(b=>b.onclick=()=>round(b.dataset.round));
  $("exportPerson").onclick=()=>download({participant:p,appearances:appearances.map(a=>({date:a.round.date,body:a.round.body,points:a.points,events:a.round.events.filter(ev=>ev.names.includes(p.id))})),methodology:D.methodology},`participant-${p.id}.json`);
  $("correctPerson").onclick=()=>correction({playerId:p.id,name:p.name,identity:p.identity});
 }
 function coverage(){
  const c=D.coverage,m=D.methodology;
  base("COVERAGE & SCORING",`${kpis()}<div class="archive-note">${e(c.scope)}</div>
   <div class="archive-coverage-grid"><section class="archive-panel"><h2>What was actually imported</h2>
   <p>${n(c.repositories)} public repository trees / ${n(c.repositoryFilesInventoried)} files inventoried. This is inventory, not a claim that every file was read.</p>
   <p>${n(c.minutesParsed)} date-validated minutes records and ${n(c.transcriptsParsed)} timestamped transcript records parsed. ${n(c.supportingDocumentsIndexed)} supporting documents linked; ${n(c.duplicateDocumentsSkipped)} duplicate file blobs skipped.</p>
   <p>${n(c.legacyRecordsIndexed)} legacy records indexed without reliable speaker labels. ${n(c.driveFilesRead)} Drive files read; indexes and placeholder captures quarantined. Drive is a bounded snapshot, not a live connection.</p>
   <p>${n(c.captionCandidatesUnscored)} unconfirmed caption-name mentions are review leads with no participation score.</p></section>
   <section class="archive-panel"><h2>Reproducible participation scoring</h2><p>${e(m.formula)}</p><p>${e(m.eligibility)}</p><p>${e(m.meaning)}</p><p>${e(m.unknowns)}</p></section></div>
   <section class="archive-panel"><h2>Identity, duplicates and corrections</h2><p>${e(m.identity)}</p><p>${e(m.deduplication)}</p><p>Original participation-ledger intake policy: ${e(m.privacy)} The separate transcript library has its own corpus disclosure and includes full public-source caption records plus user-supplied captions matched to public City video metadata.</p><p>${e(m.corrections)}</p><p>No live submissions are sent to the City, Google Drive, GitHub or anybody else. Correction drafts download to your device for review. The app does not continuously sync private sources.</p>
   <button class="btn btn-ghost" id="exportCoverage">EXPORT IMPORT MANIFEST</button></section>
   <section class="archive-panel"><h2>Source repositories</h2><ul class="archive-source-list">${D.repositories.map(r=>`<li>${link(r.url,r.name)} · ${n(r.fileCount)} files inventoried${r.treeTruncated?" · TREE TRUNCATED":""}</li>`).join("")}</ul></section>
   <section class="archive-panel"><h2>Quarantine / scoring withheld</h2><p>Unreliable source records remain visible as limitations, not hidden gaps. ${n(D.quarantine.length)} items are withheld.</p>${D.quarantine.map(q=>`<details><summary>${e(q.label)}</summary><p>${e(q.reason)}</p>${q.source?link(q.source,"Inspect source"): '<span class="archive-meta">Private Drive reference withheld from the published app.</span>'}</details>`).join("")}</section>
   <section class="archive-panel"><h2>Drive intake, without private URLs</h2><p>This is the original bounded intake list. The separate transcript catalog also includes user-supplied public-meeting captions after public video metadata matching; its coverage disclosure lists matched and withheld counts. Private Drive URLs and unmatched files are not included.</p>${D.driveIntake.map(d=>`<details><summary>${e(d.label)}</summary><p>${e(d.status)}${d.reason?": "+e(d.reason):""}</p></details>`).join("")}</section>
   <section class="archive-panel"><h2>What still needs work</h2><p>Supporting PDFs are linked but have not all been OCR-parsed for speakers. Older naming formats, OCR errors, caption identities, agenda boundaries and date mismatches need human review. No automatic fuzzy identity merge is performed. Real vote outcomes and influence are not inferred from participation.</p><p>Historical replay is read-only. Practice scores reset with the session and never overwrite the archival ledger. Published data is a static snapshot; future updates require a new reviewed import.</p></section>`);
  $("exportCoverage").onclick=()=>download({asOf:D.asOf,coverage:c,methodology:m,repositories:D.repositories,quarantine:D.quarantine,driveIntake:D.driveIntake},"historical-import-manifest.json");
 }
 function download(data,filename){
  const blob=new Blob([JSON.stringify(data,null,2)],{type:"application/json"});
  const a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download=filename;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(a.href),30000);
 }
 function correction(record){
  openModal(`<h3>Correction draft</h3><p>This downloads a local review file. Nothing is submitted or changed in the historical record.</p><label for="correctionText">Describe the correction and cite the supporting source</label><textarea id="correctionText" rows="5" style="display:block;width:100%;margin:16px 0;padding:12px;background:#0a111c;color:#fff;border:1px solid #627186"></textarea><button class="btn btn-primary" id="saveCorrection">DOWNLOAD DRAFT</button> <button class="btn btn-ghost" id="cancelCorrection">CANCEL</button><p id="correctionStatus" aria-live="polite"></p>`);
  $("cancelCorrection").onclick=closeModal;
  $("saveCorrection").onclick=()=>{
   const note=$("correctionText").value.trim();
   if(!note){$("correctionStatus").textContent="Add a correction note before downloading.";return}
   download({type:"correction-draft",notSubmitted:true,record,note,methodologyVersion:D.methodology.version},"historical-correction-draft.json");
   $("correctionStatus").textContent="Draft downloaded. It has not been submitted.";
  };
 }
 window.openHistory=()=>{V.tab="rounds";V.q="";V.page=0;render()};
 window.openTranscripts=()=>{V.tab="transcripts";V.page=0;render()};
 window.openHistoryRound=round;
 window.openHistoryPerson=person;
})();
