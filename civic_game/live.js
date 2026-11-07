(()=>{
 "use strict";
 const D=window.HISTORY_DATA,E=window.EVOLUTION_DATA;
 const $=id=>document.getElementById(id);
 const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
 const data={mode:"operator-assisted; Zoom live feed not configured",events:[],comparisons:[],identityLinks:[],startedAt:new Date().toISOString(),persisted:false};
 const LIMITS={events:2500,textChars:2000000,note:8000,comparisons:100};
 let current="",role="unverified",consented=false;
 const safe=u=>{try{const x=new URL(u);return x.protocol==="https:"?esc(x.href):null}catch{return null}};
 const link=(u,t)=>safe(u)?`<a href="${safe(u)}" target="_blank" rel="noopener noreferrer">${esc(t)}</a>`:esc(t);
 function download(obj,name){const b=new Blob([JSON.stringify(obj,null,2)],{type:"application/json"}),u=URL.createObjectURL(b),a=document.createElement("a");a.href=u;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(u),30000)}
 function open(){
  clearInterval(S.timerId);S.phase="history";S.paused=true;document.onkeydown=null;closeModal();scrollTo(0,0);
  $("app").innerHTML=`${masthead("LIVE MEETING WORKSPACE")}<nav class="archive-nav"><button class="btn btn-ghost" id="liveBack">HISTORICAL ROUNDS</button><button class="btn btn-ghost" id="liveTracker">ORDINANCE TRACKER</button><button class="btn btn-ghost" id="liveExport">EXPORT SESSION</button><button class="btn btn-ghost" id="clearLive">CLEAR LOCAL SESSION</button></nav>
   <p class="archive-meta">Exports may contain private transcript material or notes. Review before sharing; downloads are local, not published.</p>
   <div class="archive-note">OPERATOR-ASSISTED · LIVE FEED SETUP REQUIRED. Manual notes and permitted WebVTT imports only; no audio, video or Zoom captions are captured. Notes are memory-only: export before reloading. Connecting Zoom to the assistant does not configure this site's SDK/RTMS stream.</div>
   <div class="live-grid"><section class="archive-panel"><h2>Meeting interface</h2><div id="meetingSDKElement" class="live-zoom-slot"><strong>Zoom Meeting SDK container</strong><p>No meeting has been joined. Embedding needs an authorized Zoom SDK app, server-generated signature and meeting details. Streaming transcripts require a separate authorized capture integration such as RTMS.</p><button class="btn btn-ghost" id="zoomReadiness">VIEW CONNECTION REQUIREMENTS</button></div><p class="archive-meta">The game remains the surrounding interface. No generic Zoom page is iframed and no participant is recorded without permission.</p>
   <label class="live-consent"><input type="checkbox" id="liveConsent" ${consented?"checked":""}> I have permission to process the meeting material I add here.</label>
   <div class="archive-tools"><label>Import a permitted transcript (.vtt)<input type="file" id="vttFile" accept=".vtt,text/vtt"></label></div><p id="vttStatus" aria-live="polite"></p></section>
   <section class="archive-panel"><h2>Who has the floor?</h2><div class="archive-tools"><label>Recorded name or operator label<input type="search" list="publicNames" id="speakerName" placeholder="Select or type a speaker" value="${esc(current)}"><datalist id="publicNames">${D.players.map(p=>`<option value="${esc(p.name)}">`).join("")}</datalist></label><label>Role for this session<select id="speakerRole">${["unverified","public commenter","council member","business representative","staff","meeting chair"].map(r=>`<option ${role===r?"selected":""}>${r}</option>`).join("")}</select></label></div>
   <button class="btn btn-primary" id="selectSpeaker">SELECT SPEAKER</button><p class="archive-meta">Names and roles are not inferred from face, voice, Zoom display name or an agenda. A same-name match is a lead, not an identity determination.</p><div id="speakerDossier"></div></section></div>
   <section class="archive-panel"><h2>Live evidence notebook</h2><p>Questions, promises, votes and stances must retain an attributable passage and source. A note is not automatically a fact, promise fulfillment, policy influence or a verified vote.</p>
   <div class="archive-tools"><label>Event type<select id="eventType">${["testimony","question","promise / follow-up","vote record","stated position","role / affiliation","source note"].map(t=>`<option>${t}</option>`).join("")}</select></label><label>Topic / ordinance reference<input id="eventTopic" placeholder="Exact ordinance number or title, if known"></label><label>Due date, if explicitly promised<input type="date" id="eventDue"></label></div>
   <label for="eventText">Exact passage or operator note</label><textarea id="eventText" rows="4" class="live-textarea"></textarea><div class="archive-tools"><label>Public evidence URL<input type="url" id="eventSource" placeholder="https://…"></label><label>Evidence status<select id="eventStatus"><option>unverified operator note</option><option>source-linked quote; accuracy unreviewed</option><option>operator-reviewed against cited source</option></select></label></div><button class="btn btn-primary" id="addEvent">LOG EVENT</button><p id="eventStatusText" aria-live="polite"></p><div id="liveEvents" class="archive-list"></div></section>
   <section class="archive-panel"><h2>Possible contradiction / change-of-position review</h2><p>Compare two recorded passages without deciding dishonesty. A difference may reflect changed conditions, different scope, a correction, a changed view or transcription error. Promises remain pending until there is evidence of fulfillment or withdrawal.</p><div class="archive-tools"><label>Earlier evidence<select id="compareA"></select></label><label>Later evidence<select id="compareB"></select></label></div><label for="compareNote">Review question, including context and uncertainty</label><textarea id="compareNote" rows="3" class="live-textarea"></textarea><button class="btn btn-ghost" id="compareEvidence">SAVE REVIEW PAIR</button><div id="comparisonList"></div></section>`;
  $("liveBack").insertAdjacentHTML("afterend",'<button class="btn btn-ghost" id="liveTranscripts">TRANSCRIPTS</button>');
  $("liveTranscripts").onclick=window.openTranscripts;
  $("liveBack").onclick=window.openHistory;$("liveTracker").onclick=()=>window.CivicEvolution.open("ordinances");
  $("liveExport").onclick=()=>download({...data,exportedAt:new Date().toISOString(),warning:"Contains operator notes and possibly private imported transcript material. Review before sharing. Not merged into historical records."},"live-meeting-review-session.json");
  $("clearLive").onclick=()=>{openModal('<h3>Clear the local session?</h3><p>This deletes this page’s notes, imported cues, review pairs and identity links. Download an export first if needed. Historical records are unaffected.</p><button class="btn btn-primary" id="confirmClearLive">CLEAR SESSION</button> <button class="btn btn-ghost" id="cancelClearLive">KEEP SESSION</button>');$("cancelClearLive").onclick=closeModal;$("confirmClearLive").onclick=()=>{data.events.length=0;data.comparisons.length=0;data.identityLinks.length=0;current="";role="unverified";consented=false;open()}};
  $("liveConsent").onchange=ev=>{consented=ev.target.checked};
  $("speakerName").onkeydown=ev=>{if(ev.key==="Enter")select()};
  $("selectSpeaker").onclick=select;$("speakerRole").onchange=ev=>{role=ev.target.value};
  $("zoomReadiness").onclick=()=>{openModal(`<h3>Zoom connection requirements</h3><p>This preview has no SDK signature backend or RTMS service. Connecting a general Zoom account alone does not activate embedded meetings or authorize capture.</p><ul><li>Authorized Zoom Meeting SDK app and server-side short-lived signatures restricted to allowed meetings and users.</li><li>Meeting number, passcode where required, host/admin permission and participant notice.</li><li>For live transcripts: authorized RTMS app, credits/entitlement, authenticated ingestion and retention controls.</li><li>Confirmed source-to-person identity links; never identify people through voiceprints or face recognition.</li><li>Desktop component view and a separately tested mobile client-view path.</li></ul><p>${link("https://developers.zoom.us/docs/meeting-sdk/","Zoom Meeting SDK documentation")} · ${link("https://developers.zoom.us/docs/rtms/","RTMS documentation")}</p><button class="btn btn-ghost" id="closeZoomInfo">CLOSE</button>`);$("closeZoomInfo").onclick=closeModal;};
  $("vttFile").onchange=importVtt;$("addEvent").onclick=addEvent;$("compareEvidence").onclick=compare;
  renderEvents();dossier();
 }
 function select(){current=$("speakerName").value.trim().slice(0,120);role=$("speakerRole").value;dossier()}
 function dossier(){
  if(!current){$("speakerDossier").innerHTML='<p class="archive-meta">Select a speaker to inspect evidence available in this corpus.</p>';return}
  const p=D.players.find(p=>p.name.toLowerCase()===current.toLowerCase());
  const attached=data.identityLinks.find(l=>l.operatorLabel===current);
  const mentions=E.observations.filter(o=>o.excerpt.toLowerCase().includes(current.toLowerCase())).slice(-20).reverse();
  $("speakerDossier").innerHTML=`<h3>${esc(current)}</h3><p>Session role: ${esc(role)} (operator-assigned, not verified).</p>
   ${p?`<p>Same-name archive lead: ${p.roundCount} documented public-comment rounds under this recorded label. ${attached?"Operator linked this session label to that label. This is not independent identity verification.":"Not confirmed to be the same person."}</p><button class="btn btn-ghost" id="linkIdentity">${attached?"REMOVE OPERATOR IDENTITY LINK":"CONFIRM LABEL LINK FOR THIS SESSION"}</button> <button class="btn btn-ghost" id="openPublicPerson">INSPECT SOURCED PARTICIPATION</button>`:'<p>No exact public-comment name label found. Council members and staff may appear in item passages without appearing in the public-comment register. This does not establish that this is a new speaker.</p>'}
   <p>${data.events.filter(e=>e.speaker===current).length} events under this label in the current session. This view is corpus-limited, not this person’s entire public history.</p>
   <details><summary>${mentions.length}${mentions.length===20?"+":""} item-text name mentions available</summary><p>Literal string matches, not confirmed identity, stance, voting behavior, causation or policy influence. Name matches inside another name are possible.</p>${mentions.map(o=>`<p>${esc(o.date)} · ${link(o.source,o.excerpt.slice(0,170)+"…")}</p>`).join("")||'<p>No exact-string mentions extracted.</p>'}</details>`;
  if(p){$("openPublicPerson").onclick=()=>window.openHistoryPerson(p.id);$("linkIdentity").onclick=()=>{const idx=data.identityLinks.findIndex(l=>l.operatorLabel===current);if(idx>=0)data.identityLinks.splice(idx,1);else data.identityLinks.push({operatorLabel:current,recordedPlayerId:p.id,verification:"operator-confirmed label link only",at:new Date().toISOString()});dossier()}}
 }
 function addEvent(){
  if(!consented){$("eventStatusText").textContent="Confirm permission to process this material first.";return}
  const text=$("eventText").value.trim(),url=$("eventSource").value.trim();
  if(data.events.length>=LIMITS.events||text.length>LIMITS.note||data.events.reduce((n,e)=>n+e.text.length,0)+text.length>LIMITS.textChars){$("eventStatusText").textContent="Session or note limit reached. Export and clear before adding more material.";return}
  if(url.length>2000){$("eventStatusText").textContent="Evidence URL is too long.";return}
  if(!current||!text){$("eventStatusText").textContent="Select a speaker and add a passage or note.";return}
  if(url&&!safe(url)){$("eventStatusText").textContent="Use an HTTPS public evidence URL, or leave it blank for an unverified note.";return}
  const status=$("eventStatus").value;
  if(status!=="unverified operator note"&&!url){$("eventStatusText").textContent="A source-linked status requires an evidence URL.";return}
  data.events.push({id:"local-"+(data.events.length+1),speaker:current,role,roleVerification:"operator-assigned",type:$("eventType").value,topic:$("eventTopic").value.trim().slice(0,300),dueDate:$("eventDue").value||null,text,source:url||null,status,at:new Date().toISOString(),origin:"operator input",historicalScoreImpact:0});
  $("eventText").value="";$("eventStatusText").textContent="Logged locally for review. No historical score changed.";renderEvents();dossier();
 }
 async function importVtt(ev){
  const file=ev.target.files[0];if(!file)return;
  if(!consented){$("vttStatus").textContent="Confirm permission before importing a transcript.";ev.target.value="";return}
  if(file.size>2*1024*1024){$("vttStatus").textContent="Transcript import limited to 2 MB.";return}
  const text=await file.text();if(!text.trimStart().startsWith("WEBVTT")){$("vttStatus").textContent="Not a WebVTT file. No events imported.";return}
  let count=0,remaining=LIMITS.textChars-data.events.reduce((n,e)=>n+e.text.length,0);
  for(const block of text.split(/\r?\n\r?\n/)){
   const timing=block.match(/(\d{2}:)?\d{2}:\d{2}\.\d{3}\s+-->\s+((?:\d{2}:)?\d{2}:\d{2}\.\d{3})/);
   if(!timing)continue;
   const line=block.slice(block.indexOf(timing[0])+timing[0].length).trim();
   const vm=line.match(/^<v(?:\.[^ >]+)?\s+([^>]+)>([\s\S]*)/),colon=line.match(/^([^:\n]{2,90}):\s*([\s\S]+)/);
   const label=vm?.[1]||colon?.[1]||"Unattributed caption",body=(vm?.[2]||colon?.[2]||line).replace(/<[^>]*>/g,"").trim();
   if(!body)continue;
   if(data.events.length>=LIMITS.events||body.length>remaining)break;
   data.events.push({id:"local-"+(data.events.length+1),speaker:label.slice(0,120),role:"unverified",type:"caption",text:body,source:null,status:"imported captions; speaker identity and accuracy unverified",at:timing[0],origin:"operator-imported WebVTT",historicalScoreImpact:0});count++;remaining-=body.length;
   if(count>=2000)break;
  }
  $("vttStatus").textContent=`${count} caption cues imported locally. Session cap: ${LIMITS.events} events / ${LIMITS.textChars.toLocaleString()} text characters. No speaker identities, roles, promises or votes automatically verified.`;renderEvents();dossier();
 }
 function renderEvents(){
  $("liveEvents").innerHTML=data.events.slice(-100).reverse().map(x=>`<article class="archive-panel"><span class="archive-meta">${esc(x.at)} · ${esc(x.type)} · ${esc(x.status)}</span><h3>${esc(x.speaker)}</h3><p>${esc(x.text)}</p>${x.topic?`<p>Topic label: ${esc(x.topic)}</p>`:""}${x.dueDate?`<p>Operator-entered due date: ${esc(x.dueDate)} · fulfillment unknown</p>`:""}${x.source?link(x.source,"Inspect supplied evidence"):"<p class=\"archive-meta\">No public evidence URL supplied.</p>"}</article>`).join("")||'<p class="archive-empty">No session events. Nothing is being captured automatically.</p>';
  for(const id of ["compareA","compareB"])$(id).innerHTML='<option value="">Choose evidence</option>'+data.events.map(e=>`<option value="${e.id}">${esc(e.id+" · "+e.speaker+" · "+e.text.slice(0,70))}</option>`).join("");
  $("comparisonList").innerHTML=data.comparisons.map(c=>`<article class="archive-panel"><h3>Potential tension / follow-up, not a finding</h3><p>${esc(c.note)}</p><p>${esc(data.events.find(e=>e.id===c.a)?.text)}</p><p>${esc(data.events.find(e=>e.id===c.b)?.text)}</p><p class="archive-meta">Operator review pair. No automated dishonesty, promise breach or causation judgment.</p></article>`).join("");
 }
 function compare(){
  const a=$("compareA").value,b=$("compareB").value,note=$("compareNote").value.trim();
  if(data.comparisons.length>=LIMITS.comparisons||note.length>2000){$("comparisonList").insertAdjacentHTML("afterbegin",'<p role="status">Review-pair limit reached or note exceeds 2,000 characters. Export and clear if needed.</p>');return}
  if(!a||!b||a===b||!note){$("comparisonList").insertAdjacentHTML("afterbegin",'<p role="status">Choose two different entries and add a contextual review question.</p>');return}
  data.comparisons.push({a,b,note,classification:"potential tension / follow-up; unverified",at:new Date().toISOString()});renderEvents();
 }
 window.CivicLive={open};
})();
