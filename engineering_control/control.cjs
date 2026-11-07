const fs = require('fs');
const rules = [
 ['architecture','Architect',/(^|\/)(?:architecture(?:[._-][^/]*)?|ecosystem(?:[._-][^/]*)?|system[-_]map(?:[._-][^/]*)?|federation(?:[._-][^/]*)?)\.(md|json|ya?ml)$/i,'Map producers, consumers, storage, deployment targets and owners.'],
 ['agent_handoff','Agent coordinator',/(^|\/)AGENTS\.md$/i,'Provide tested commands, current status, constraints and acceptance criteria.'],
 ['setup','Build engineer',/(^|\/)(requirements[^/]*\.txt|pyproject\.toml|package\.json|Cargo\.toml|go\.mod|Dockerfile)$/i,'Prove installation from a clean checkout with stated tool versions.'],
 ['tests','Test engineer',/(^|\/)(?:tests?\/.*\.(?:py|[cm]?js|tsx?|go|rs)|test_[^/]+\.py|[^/]+[.-](?:test|spec)\.[cm]?[jt]s)$/i,'Add offline tests and a real producer-to-published-output test.'],
 ['data_contract','Data engineer',/(^|\/)(?:schemas?\/.*\.(?:json|ya?ml)|[^/]+[._-]schema\.(?:json|ya?ml)|(?:validate|validation|contracts?)(?:[._-][^/]*)?\.(?:py|[cm]?js|ts|json|ya?ml))$/i,'Validate schemas, stable IDs and compatibility between producers and consumers.'],
 ['provenance','Evidence reviewer',/(^|\/)(?:provenance(?:[._-][^/]*)?|sources?(?:[._-][^/]*)?|[^/]*manifest)\.(md|json|ya?ml|py|[cm]?js)$/i,'Retain source URLs, capture dates, hashes, original records and limitations.'],
 ['checkpoint','Reliability engineer',/(^|\/)(?:(?:checkpoint|resume|state|manifest)(?:[._-][^/]*)?|[^/]+[._-](?:checkpoint|state|manifest))\.(json|ya?ml|py|[cm]?js|ts|md)$/i,'Prove interrupted runs resume without lost records or duplicates.'],
 ['recovery','Recovery engineer',/(^|\/)(?:backup|restore|rollback|recovery)(?:[._-][^/]*)?\.(md|py|sh|ps1|[cm]?js|ya?ml)$/i,'Test isolated backup restoration and reversible releases.'],
 ['deployment','Release engineer',/(^|\/)(?:deploy(?:ment)?|release|CHANGELOG)(?:[._-][^/]*)?\.(md|py|sh|ps1|[cm]?js|ya?ml)$/i,'Tie live output to its commit, smoke test and rollback instructions.'],
 ['dependency_lock','Supply-chain reviewer',/(^|\/)(uv\.lock|poetry\.lock|package-lock\.json|pnpm-lock\.yaml|yarn\.lock|Cargo\.lock)$/i,'Review lockfiles or equivalent pins; missing filenames alone do not establish unpinned dependencies.'],
 ['rights','Rights reviewer',/(^|\/)(LICENSE[^/]*|COPYING[^/]*|NOTICE[^/]*)$/i,'Separate code licensing from source-data and media reuse rights.'],
];
function engineeringPath(p) {
 return !/(^|\/)(?:snapshots|corpus(?:_yt|_clean)?|uploads|ai-record-ocr|scanner-results|node_modules|vendor)(?:\/|$)/i.test(p) && !/^data\/(?:out|text)\//i.test(p);
}
function assess(paths, complete, archived) {
 const eligible=paths.filter(engineeringPath);
 const runtime=!archived&&eligible.some(p=>/\.(py|[cm]?js|tsx?|go|rs)$/.test(p));
 return rules.map(([id,role,pattern,next])=>{
  const evidence=eligible.filter(p=>pattern.test(p)).slice(0,6);
  const applicable=runtime||['architecture','agent_handoff','provenance','rights'].includes(id);
  return {id,role,state:!applicable?'not_applicable_to_detected_role':evidence.length?'signal_observed':complete?'not_observed':'unknown',evidence,next,runtime_verified:false,evidence_policy:'engineering paths and explicit filenames only; contents and behavior still require review'};
 });
}
function signals(text) {
 const result=new Set();
 for(const m of text.matchAll(/\b(ModuleNotFoundError|ImportError|AssertionError|SyntaxError|TypeError|ValueError|KeyError|FileNotFoundError|PermissionError|RuntimeError)\b/g))result.add(m[1]);
 for(const m of text.matchAll(/No module named ['"]([A-Za-z0-9_.-]+)['"]/g))result.add('Missing module: '+m[1]);
 for(const tool of ['ffprobe','ffmpeg','node','python','python3','git']) {
  const escaped=tool.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
  if(new RegExp("No such file or directory: ['\"]"+escaped+"['\"]").test(text)||new RegExp(escaped+': command not found').test(text))result.add('Missing executable: '+tool);
 }
 if(/Resource not accessible by integration/.test(text))result.add('GitHub token permission restriction');
 if(/Process completed with exit code [1-9][0-9]*/.test(text))result.add('Nonzero command exit');
 return [...result];
}
function selftest() {
 const a=require('node:assert/strict');
 const state=(p,id,complete=true,archived=false)=>assess(p,complete,archived).find(x=>x.id===id);
 a.equal(state(['app.py'],'tests',false).state,'unknown');
 a.equal(state(['app.py'],'tests').state,'not_observed');
 a.equal(state(['app.py','tests/test_app.py'],'tests').state,'signal_observed');
 a.equal(state(['records.pdf'],'setup').state,'not_applicable_to_detected_role');
 a.equal(state(['app.py'],'setup',true,true).state,'not_applicable_to_detected_role');
 const noise=['app.py','data/snapshots/hash_pumphouse-contract-process','data/snapshots/hash_statewide-election','data/snapshots/hash_restore-school-funding','data/snapshots/hash_release-report','uploads/backup.md','pipeline/corpus_yt/validation.py'];
 for(const id of ['data_contract','checkpoint','recovery','deployment'])a.equal(state(noise,id).state,'not_observed',id);
 for(const [path,id]of [['schemas/record.json','data_contract'],['tools/validate_records.py','data_contract'],['tools/restore_backup.sh','recovery'],['pipeline/state.json','checkpoint'],['DEPLOY.md','deployment'],['docs/ARCHITECTURE-TIERS.md','architecture']])a.equal(state(['app.py',path],id).state,'signal_observed',path);
 a.deepEqual(signals('secret=do-not-publish\nAssertionError: sensitive message'),['AssertionError']);
 a.deepEqual(signals("ModuleNotFoundError: No module named 'pillow'"),['ModuleNotFoundError','Missing module: pillow']);
 a.deepEqual(signals("FileNotFoundError: [Errno 2] No such file or directory: 'ffprobe'"),['FileNotFoundError','Missing executable: ffprobe']);
 a.deepEqual(signals('all checks passed'),[]);
 console.log('Auditor regression tests passed: archived news rejected, legitimate engineering paths retained, uncertainty preserved, safe missing-tool extraction verified.');
}
async function run({github,context,core}) {
 const out='engineering-control-output';fs.mkdirSync(out,{recursive:true});
 const report={schema:2,started_at:new Date().toISOString(),run_url:`https://github.com/${context.repo.owner}/${context.repo.repo}/actions/runs/${context.runId}`,video_proof_result:process.env.VIDEO_PROOF_RESULT||'unknown',repositories:[],edges:[],backlog:[],gaps:[],limitations:['Public GitHub repositories across both named accounts only; Drive, private repositories, local devices and hosts are not inspected.', 'Engineering file signals are not proof of implementation correctness. Missing signals require review. Archived-content folders are excluded from engineering evidence.', 'At most 100 recent runs per repository; latest run per workflow/branch retained. At most 12 failed jobs have bounded logs inspected; raw messages and secrets are not republished.', 'At most 12 engineering workflow/docs/manifest files per repository are sampled for declared dependencies. References are not verified transfers.', 'Video proof covers records_video_v2, not PR #26 or the live site. No application repair, merge, deployment, destructive test or security certification is performed.']};
 const persist=()=>fs.writeFileSync(`${out}/full.json`,JSON.stringify(report,null,2));
 let inventory=[],logsRead=0;
 for(const username of ['bartimoussmith-oss','therealwindycity'])try{inventory.push(...await github.paginate(github.rest.repos.listForUser,{username,type:'owner',per_page:100}));}catch(e){report.gaps.push({check:'repo_inventory',scope:username,http:e.status||null});}
 inventory=inventory.filter(r=>!r.private);const known=new Set(inventory.map(r=>r.full_name));
 for(const repo of inventory) {
  const args={owner:repo.owner.login,repo:repo.name};
  const r={repository:repo.full_name,archived:repo.archived,fork:repo.fork,checked_at:new Date().toISOString(),controls:[],runs:[],pull_requests:[],gaps:[]};report.repositories.push(r);
  try {
   const head=(await github.rest.repos.getCommit({...args,ref:repo.default_branch})).data;r.head=head.sha;
   const tree=(await github.rest.git.getTree({...args,tree_sha:head.commit.tree.sha,recursive:'1'})).data;
   const paths=tree.tree.filter(x=>x.type==='blob').map(x=>x.path);r.files_seen=paths.length;r.tree_complete=!tree.truncated;r.controls=assess(paths,r.tree_complete,repo.archived);
   for(const c of r.controls.filter(x=>x.state==='not_observed'))report.backlog.push({id:r.repository+':'+c.id,priority:'P2',repository:r.repository,role:c.role,status:'needs_inspection',task:c.next,evidence:'No eligible engineering filename signal observed; equivalent implementation may exist.',done_when:'Implementation reviewed and relevant tests and output verified.'});
   const candidates=paths.filter(p=>engineeringPath(p)&&(/^\.github\/workflows\/.*\.ya?ml$/.test(p)||/(^|\/)(AGENTS\.md|README\.md|[^/]*(manifest|federation|registry)[^/]*\.json)$/i.test(p)));
   const selected=candidates.slice(0,12);r.sample_coverage={candidates:candidates.length,selected:selected.length};r.workflow_signals={};
   for(const path of selected)try{
    const file=(await github.rest.repos.getContent({...args,path,ref:r.head})).data;
    if(file.encoding!=='base64'||file.size>180000){r.gaps.push({check:'sample',path,reason:'Content too large or unavailable'});continue;}
    const text=Buffer.from(file.content,'base64').toString('utf8');
    if(path.startsWith('.github/workflows/'))r.workflow_signals[path]={timeout:/timeout-minutes:/.test(text),concurrency:/concurrency:/.test(text),always_save:/always\(\)/.test(text)&&/upload-artifact|git push|createOrUpdateFileContents/.test(text),explicit_permissions:/permissions:/.test(text)};
    for(const m of text.matchAll(/github\.com\/([A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+)/g)){const to=m[1].replace(/\.git$/,'').replace(/\.$/,'');if(known.has(to)&&to!==r.repository)report.edges.push({from:r.repository,to,path,sha:r.head,status:'declared_reference_only'});}
   }catch(e){r.gaps.push({check:'sample',path,http:e.status||null});}
   for(const [path,checks]of Object.entries(r.workflow_signals))for(const [id,present]of Object.entries(checks))if(!present)report.backlog.push({id:r.repository+':'+path+':'+id,priority:'P2',repository:r.repository,role:'Reliability/security reviewer',status:'needs_inspection',evidence:{path,sha:r.head,signal:id},task:'Review missing '+id+' signal; inspect equivalent controls before editing.',done_when:'Control tested or documented as inapplicable.'});
  }catch(e){r.gaps.push({check:'tree_or_head',http:e.status||null});}
  try {
   const runs=(await github.rest.actions.listWorkflowRunsForRepo({...args,per_page:100})).data.workflow_runs;const seen=new Set();
   for(const x of runs){
    const key=x.workflow_id+':'+x.head_branch;if(seen.has(key))continue;seen.add(key);
    const item={name:x.name,id:x.id,url:x.html_url,sha:x.head_sha,branch:x.head_branch,status:x.status,conclusion:x.conclusion,created_at:x.created_at};r.runs.push(item);
    if(!['failure','timed_out','startup_failure','action_required'].includes(x.conclusion))continue;item.failed_jobs=[];
    try {
     const jobs=await github.paginate(github.rest.actions.listJobsForWorkflowRun,{...args,run_id:x.id,per_page:100});
     for(const job of jobs.filter(j=>['failure','timed_out'].includes(j.conclusion)).slice(0,3)){
      const j={name:job.name,url:job.html_url,steps:(job.steps||[]).filter(s=>['failure','timed_out'].includes(s.conclusion)).map(s=>({name:s.name,number:s.number})),log_status:'not_sampled',error_signals:[]};item.failed_jobs.push(j);if(logsRead>=12)continue;logsRead++;
      try {
       const response=await github.rest.actions.downloadJobLogsForWorkflowRun({...args,job_id:job.id});const d=response.data;let text='';
       if(typeof d==='string'&&!d.startsWith('https://'))text=d.slice(0,300000);
       else if(d instanceof ArrayBuffer||Buffer.isBuffer(d))text=Buffer.from(d).toString('utf8').slice(0,300000);
       else {const u=new URL(typeof d==='string'?d:response.url);if(u.protocol!=='https:')throw Error('Unsafe log URL');const res=await fetch(u,{signal:AbortSignal.timeout(20000)});if(!res.ok)throw Error('Logs unavailable');const reader=res.body.getReader();let n=0;try{while(n<300000){const part=await reader.read();if(part.done)break;n+=part.value.length;text+=Buffer.from(part.value).toString('utf8');}}finally{await reader.cancel();}}
       j.log_status='bounded_read';j.error_signals=signals(text);
      }catch(e){j.log_status='unavailable';j.http=e.status||null;}
     }
    }catch(e){r.gaps.push({check:'failed_jobs',run:x.id,http:e.status||null});}
    report.backlog.push({id:r.repository+':run:'+x.id,priority:x.head_sha===r.head?'P1':'review',repository:r.repository,role:'Reliability engineer',status:'confirmed_run_failure_not_current_product_diagnosis',evidence:item,task:'Reproduce the recorded failed step and repair its demonstrated cause.',done_when:'Replacement run passes the same checks and output is verified; older failure does not establish current HEAD failure.'});
   }
   r.pull_requests=(await github.paginate(github.rest.pulls.list,{...args,state:'open',per_page:100})).map(p=>({number:p.number,title:p.title,url:p.html_url,head:p.head.sha,updated_at:p.updated_at,draft:p.draft,mergeability:'unverified'}));
  }catch(e){r.gaps.push({check:'actions_or_prs',http:e.status||null});}
  persist();
 }
 report.manual_verification=[{role:'Data engineer',task:'Trace a real record through collection, storage, extraction, indexing, publication and repeat run.'},{role:'Security reviewer',task:'Inspect permissions, secrets, sensitive data boundaries and dependency vulnerabilities.'},{role:'Recovery engineer',task:'Prove backup restore, interruption recovery, deduplication and rollback in isolation.'},{role:'Release engineer',task:'Verify actual live pages, phone/desktop media playback and release-to-commit identity.'},{role:'Independent reviewer',task:'Check claims against source records and distinguish configured, executed, tested, deployed and verified.'}];
 report.finished_at=new Date().toISOString();report.edges=[...new Map(report.edges.map(e=>[e.from+':'+e.to+':'+e.path,e])).values()];report.backlog.sort((a,b)=>({P1:0,P2:1,review:2}[a.priority]??3)-({P1:0,P2:1,review:2}[b.priority]??3));report.summary={repositories:report.repositories.length,declared_edges:report.edges.length,backlog:report.backlog.length,logs_sampled:logsRead};persist();
 const branch='engineering-control-reports';let base;
 try{base=(await github.rest.git.getRef({...context.repo,ref:'heads/'+branch})).data.object.sha;}catch(e){if(e.status!==404)throw e;base=(await github.rest.repos.getCommit({...context.repo,ref:'main'})).data.sha;await github.rest.git.createRef({...context.repo,ref:'refs/heads/'+branch,sha:base});}
 let previous=[];try{const p=(await github.rest.repos.getContent({...context.repo,path:'latest/backlog.json',ref:branch})).data;previous=JSON.parse(Buffer.from(p.content,'base64').toString('utf8'));}catch(e){report.gaps.push({check:'previous_snapshot',http:e.status||null});}
 const before=new Set(previous.map(b=>b.id)),now=new Set(report.backlog.map(b=>b.id));const delta={newly_observed:[...now].filter(id=>!before.has(id)),no_longer_observed:[...before].filter(id=>!now.has(id)),warning:'Evidence policy changed to version 2: removed findings may be corrected false positives, not completed repairs.'};
 const clean=s=>String(s).replace(/[|\r\n]/g,' ').slice(0,220);
 const lines=['# Engineering control center','',`Updated ${report.finished_at}. Evidence policy: version 2.`,`Public repositories: ${report.summary.repositories}. Declared connections: ${report.summary.declared_edges}.`,`Current video proof lane: ${report.video_proof_result}. Not a deployment result.`,'','## Repair priorities','',...report.backlog.slice(0,30).map(b=>`- ${b.priority} | ${clean(b.repository)} | ${clean(b.role)}: ${clean(b.task)}`),'','## Verification still required','',...report.manual_verification.map(v=>'- '+v.role+': '+v.task),'','## Scope limits','',...report.limitations.map(l=>'- '+l),'','Full backlog: latest/backlog.json. Evidence: latest/repos/*.json.'];const md=lines.join('\n')+'\n';fs.writeFileSync(`${out}/summary.md`,md);
 const index={...report,repositories:report.repositories.map(r=>({repository:r.repository,report:'latest/repos/'+r.repository.replace('/','__')+'.json'})),backlog:undefined};const entries=[];const add=(path,value)=>entries.push({path,mode:'100644',type:'blob',content:typeof value==='string'?value:JSON.stringify(value,null,2)});
 for(const prefix of ['latest','runs/'+context.runId]){add(prefix+'/summary.md',md);add(prefix+'/index.json',index);add(prefix+'/backlog.json',report.backlog);for(const r of report.repositories)add(prefix+'/repos/'+r.repository.replace('/','__')+'.json',r);}add('latest/changes.json',delta);persist();
 const old=(await github.rest.git.getCommit({...context.repo,commit_sha:base})).data;const tree=(await github.rest.git.createTree({...context.repo,base_tree:old.tree.sha,tree:entries})).data;const commit=(await github.rest.git.createCommit({...context.repo,message:'engineering: corrected evidence policy, workflow results and repair backlog [skip ci]',tree:tree.sha,parents:[base]})).data;await github.rest.git.updateRef({...context.repo,ref:'heads/'+branch,sha:commit.sha,force:false});
 await core.summary.addRaw(md).addLink('Readable report',`https://github.com/${context.repo.owner}/${context.repo.repo}/blob/${branch}/latest/summary.md`).write();if(report.gaps.some(g=>g.check==='repo_inventory'))core.setFailed('Incomplete account inventory; partial evidence published.');
}
module.exports={assess,signals,run};
if(require.main===module&&process.argv.includes('--self-test'))selftest();
