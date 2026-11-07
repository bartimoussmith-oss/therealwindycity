const fs = require('fs');
const rules = [
 ['architecture','Architect',/(^|\/)(architecture|system[-_]map|ecosystem|federation)/i,'Map producers, consumers, storage, deployment targets and responsible owners.'],
 ['agent_handoff','Agent coordinator',/(^|\/)AGENTS\.md$/i,'Provide tested commands, current status, constraints and acceptance criteria.'],
 ['setup','Build engineer',/(^|\/)(requirements[^/]*\.txt|pyproject\.toml|package\.json|Cargo\.toml|go\.mod|Dockerfile)$/i,'Prove installation from a clean checkout with stated tool versions.'],
 ['tests','Test engineer',/(^|\/)(tests?\/|test_[^/]+|[^/]+[.-](test|spec)\.)/i,'Add offline tests and one real end-to-end producer-to-published-output test.'],
 ['data_contract','Data engineer',/schema|contract|validation/i,'Validate input/output schemas, stable identifiers and compatibility across repositories.'],
 ['provenance','Evidence reviewer',/provenance|manifest|sources?[_.-]/i,'Retain origin URLs, capture times, hashes, original records and limitations.'],
 ['checkpoint','Reliability engineer',/checkpoint|resume|manifest|state/i,'Test interruption recovery and persistence without duplication or data loss.'],
 ['recovery','Recovery engineer',/backup|restore|rollback|recovery/i,'Prove a backup restoration and a reversible release before risky repairs.'],
 ['deployment','Release engineer',/deploy|release|CHANGELOG/i,'Tie the live output to its commit, smoke test and rollback instructions.'],
 ['dependency_lock','Supply-chain reviewer',/(^|\/)(uv\.lock|poetry\.lock|package-lock\.json|pnpm-lock\.yaml|yarn\.lock|Cargo\.lock)$/i,'Check lockfiles or equivalent version pinning; missing filenames alone do not prove dependencies are unpinned.'],
 ['rights','Rights reviewer',/(^|\/)(LICENSE[^/]*|COPYING[^/]*|NOTICE[^/]*)$/i,'Separate code licensing from source-data and media reuse rights; review manually.'],
];
function assess(paths, complete, archived) {
 const runtime = !archived && paths.some(p=>/\.(py|js|cjs|mjs|ts|go|rs)$/.test(p));
 return rules.map(([id,role,pattern,next])=>{
   const evidence=paths.filter(p=>pattern.test(p)).slice(0,6);
   const applicable=runtime||['architecture','agent_handoff','provenance','rights'].includes(id);
   return {id,role,state:!applicable?'not_applicable_to_detected_role':evidence.length?'signal_observed':complete?'not_observed':'unknown',evidence,next,runtime_verified:false};
 });
}
function signals(text) {
 const result=new Set();
 for(const m of text.matchAll(/\b(ModuleNotFoundError|ImportError|AssertionError|SyntaxError|TypeError|ValueError|KeyError|FileNotFoundError|PermissionError|RuntimeError)\b/g)) result.add(m[1]);
 for(const m of text.matchAll(/No module named ['"]([A-Za-z0-9_.-]+)['"]/g)) result.add('Missing module: '+m[1]);
 if(/Resource not accessible by integration/.test(text)) result.add('GitHub token permission restriction');
 if(/Process completed with exit code [1-9][0-9]*/.test(text)) result.add('Nonzero command exit');
 return [...result];
}
function selftest() {
 const assert=require('node:assert/strict');
 assert.equal(assess(['app.py'],false,false).find(x=>x.id==='tests').state,'unknown');
 assert.equal(assess(['app.py'],true,false).find(x=>x.id==='tests').state,'not_observed');
 assert.equal(assess(['app.py','tests/test_app.py'],true,false).find(x=>x.id==='tests').state,'signal_observed');
 assert.equal(assess(['records.pdf'],true,false).find(x=>x.id==='setup').state,'not_applicable_to_detected_role');
 assert.equal(assess(['app.py'],true,true).find(x=>x.id==='setup').state,'not_applicable_to_detected_role');
 assert.deepEqual(signals('secret=do-not-publish\nAssertionError: sensitive message'),['AssertionError']);
 assert.deepEqual(signals("ModuleNotFoundError: No module named 'pillow'"),['ModuleNotFoundError','Missing module: pillow']);
 assert.deepEqual(signals('all checks passed'),[]);
 console.log('Auditor self-tests passed: unknown/absence, applicability, test signals, and no raw error leakage.');
}
async function run({github,context,core}) {
 const out='engineering-control-output';fs.mkdirSync(out,{recursive:true});
 const report={schema:1,started_at:new Date().toISOString(),run_url:`https://github.com/${context.repo.owner}/${context.repo.repo}/actions/runs/${context.runId}`,video_proof_result:process.env.VIDEO_PROOF_RESULT||'unknown',repositories:[],edges:[],backlog:[],gaps:[],limitations:['Public GitHub repos across bartimoussmith-oss and therealwindycity only. Drive, Termux, private repos and hosting accounts remain uninspected.', 'Inventory and filename/text signals do not prove controls work. Not observed is not established absence.', 'Recent runs are bounded to 100 per repo; only the latest run per workflow and branch is retained. At most 12 failed jobs have logs inspected across the audit.', 'At most 12 workflow/docs/manifest files per repo are read to map declared dependencies. Links are not verified data transfers.', 'Only allowlisted error types and missing-module names are published. Raw logs, arbitrary exception messages and credentials are never republished.', 'Video proof covers the current records_video_v2 builder, not PR #26, all archive features or the live site.', 'No application rewrites, merges, deployments, destructive tests or automatic fixes are performed. Specialist roles are review responsibilities, not independently running AI agents.']};
 const persist=()=>fs.writeFileSync(`${out}/full.json`,JSON.stringify(report,null,2));
 const entries=[];let inventory=[];let logsRead=0;
 for(const username of ['bartimoussmith-oss','therealwindycity']) {
  try {inventory.push(...await github.paginate(github.rest.repos.listForUser,{username,type:'owner',per_page:100}));}
  catch(e){report.gaps.push({scope:username,check:'repo_inventory',http:e.status||null});}
 }
 inventory=inventory.filter(r=>!r.private);const known=new Set(inventory.map(r=>r.full_name));
 for(const repo of inventory) {
  const a={owner:repo.owner.login,repo:repo.name};
  const r={repository:repo.full_name,archived:repo.archived,fork:repo.fork,checked_at:new Date().toISOString(),controls:[],runs:[],pull_requests:[],gaps:[]};report.repositories.push(r);
  try {
   const head=(await github.rest.repos.getCommit({...a,ref:repo.default_branch})).data;r.head=head.sha;
   const tree=(await github.rest.git.getTree({...a,tree_sha:head.commit.tree.sha,recursive:'1'})).data;
   const paths=tree.tree.filter(x=>x.type==='blob').map(x=>x.path);r.tree_complete=!tree.truncated;r.files_seen=paths.length;
   r.controls=assess(paths,!tree.truncated,repo.archived);
   for(const c of r.controls.filter(c=>c.state==='not_observed')) report.backlog.push({id:repo.full_name+':'+c.id,priority:'P2',repository:repo.full_name,role:c.role,status:'needs_inspection',evidence:'No filename signal observed in complete tree; equivalent implementation may exist.',task:c.next,done_when:'Implementation reviewed, relevant test passed, and evidence attached.'});
   const selected=paths.filter(p=>/^\.github\/workflows\/.*\.ya?ml$/.test(p)||/(^|\/)(AGENTS\.md|README\.md|[^/]*(manifest|federation|registry)[^/]*\.json)$/i.test(p)).slice(0,12);
   const workflowSignals={};
   for(const path of selected) {
    try {
     const file=(await github.rest.repos.getContent({...a,path,ref:r.head})).data;
     if(file.encoding!=='base64'||file.size>180000){r.gaps.push({check:'sample',path,reason:'content too large or unavailable'});continue;}
     const text=Buffer.from(file.content,'base64').toString('utf8');
     if(path.startsWith('.github/workflows/')) workflowSignals[path]={timeout:/timeout-minutes:/.test(text),concurrency:/concurrency:/.test(text),always_save:/always\(\)/.test(text)&&/upload-artifact|git push|createOrUpdateFileContents/.test(text),explicit_permissions:/permissions:/.test(text)};
     for(const m of text.matchAll(/github\.com\/([A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+)/g)){
      const to=m[1].replace(/\.git$/,'').replace(/\.$/,'');
      if(known.has(to)&&to!==repo.full_name)report.edges.push({from:repo.full_name,to,path,sha:r.head,status:'declared_reference_only'});
     }
    }catch(e){r.gaps.push({check:'sample',path,http:e.status||null});}
   }
   r.workflow_signals=workflowSignals;
   for(const [path,s] of Object.entries(workflowSignals))for(const [control,present]of Object.entries(s))if(!present)report.backlog.push({id:repo.full_name+':'+path+':'+control,priority:'P2',repository:repo.full_name,role:'Reliability/security reviewer',status:'needs_inspection',evidence:{path,sha:r.head,signal:control},task:'Review missing '+control+' signal in this workflow; verify behavior before editing.',done_when:'Control implemented or documented as inapplicable, with a test.'});
  }catch(e){r.gaps.push({check:'tree_or_head',http:e.status||null});}
  try {
   const data=(await github.rest.actions.listWorkflowRunsForRepo({...a,per_page:100})).data;const seen=new Set();
   for(const x of data.workflow_runs){
    const key=x.workflow_id+':'+x.head_branch;if(seen.has(key))continue;seen.add(key);
    const item={name:x.name,id:x.id,url:x.html_url,sha:x.head_sha,branch:x.head_branch,status:x.status,conclusion:x.conclusion,created_at:x.created_at};r.runs.push(item);
    if(!['failure','timed_out','startup_failure','action_required'].includes(x.conclusion))continue;
    item.failed_jobs=[];
    try {
     const jobs=await github.paginate(github.rest.actions.listJobsForWorkflowRun,{...a,run_id:x.id,per_page:100});
     for(const job of jobs.filter(j=>['failure','timed_out'].includes(j.conclusion)).slice(0,3)){
      const j={name:job.name,url:job.html_url,steps:(job.steps||[]).filter(s=>['failure','timed_out'].includes(s.conclusion)).map(s=>({name:s.name,number:s.number})),log_status:'not_sampled',error_signals:[]};item.failed_jobs.push(j);
      if(logsRead>=12)continue;logsRead++;
      try {
       const response=await github.rest.actions.downloadJobLogsForWorkflowRun({...a,job_id:job.id});let text='';const d=response.data;
       if(typeof d==='string'&&!d.startsWith('https://'))text=d.slice(0,300000);
       else if(d instanceof ArrayBuffer||Buffer.isBuffer(d))text=Buffer.from(d).toString('utf8').slice(0,300000);
       else {
        const url=typeof d==='string'?d:response.url;const u=new URL(url);if(u.protocol!=='https:')throw Error('unsafe log endpoint');
        const res=await fetch(u,{signal:AbortSignal.timeout(20000)});if(!res.ok)throw Error('log unavailable');
        const reader=res.body.getReader();let size=0;try{while(size<300000){const part=await reader.read();if(part.done)break;size+=part.value.length;text+=Buffer.from(part.value).toString('utf8');}}finally{await reader.cancel();}
       }
       j.error_signals=signals(text);j.log_status='bounded_read';
      }catch(e){j.log_status='unavailable';j.http=e.status||null;}
     }
    }catch(e){r.gaps.push({check:'failed_jobs',run:x.id,http:e.status||null});}
    report.backlog.push({id:repo.full_name+':run:'+x.id,priority:x.head_sha===r.head?'P1':'review',repository:repo.full_name,role:'Reliability engineer',status:'confirmed_run_failure_not_current_product_diagnosis',evidence:item,task:'Reproduce the failed step on the recorded SHA, repair its demonstrated cause, and rerun.',done_when:'A new run passes the same checks; output is independently verified. Older failure is not current HEAD failure.'});
   }
   const prs=await github.paginate(github.rest.pulls.list,{...a,state:'open',per_page:100});
   r.pull_requests=prs.map(p=>({number:p.number,title:p.title,url:p.html_url,head:p.head.sha,updated_at:p.updated_at,draft:p.draft,mergeability:'unverified'}));
  }catch(e){r.gaps.push({check:'actions_or_prs',http:e.status||null});}
  persist();
 }
 report.manual_verification=[
  {role:'Data engineer',task:'Trace one source record through fetch, durable storage, extraction, indexing, publication and repeat run; reconcile IDs, hashes, dates and counts.'},
  {role:'Security reviewer',task:'Review least privilege, secret storage, external inputs, private/raw data boundaries and dependency vulnerabilities. No security certification from filename checks.'},
  {role:'Recovery engineer',task:'Restore a backup in isolation; test interruption, duplicates, migrations, corruption handling and rollback without touching live records.'},
  {role:'Release engineer',task:'Verify actual deployed pages and video playback, mobile behavior, accessibility, source links and release-to-commit identity.'},
  {role:'Independent reviewer',task:'Check claims against original sources; distinguish configured, executed, tested, deployed and independently verified.'},
 ];
 report.finished_at=new Date().toISOString();
 report.edges=[...new Map(report.edges.map(e=>[e.from+':'+e.to+':'+e.path,e])).values()];
 report.backlog.sort((a,b)=>({P1:0,P2:1,review:2}[a.priority]??3)-({P1:0,P2:1,review:2}[b.priority]??3));
 report.summary={repositories:report.repositories.length,declared_edges:report.edges.length,backlog:report.backlog.length,logs_sampled:logsRead};persist();
 const clean=s=>String(s).replace(/[|\r\n]/g,' ').slice(0,220);
 const lines=['# Engineering control center','',`Updated ${report.finished_at}`,`Public repositories: ${report.summary.repositories}. Declared connections: ${report.summary.declared_edges}.`, `Current video proof lane: ${report.video_proof_result}. This is not a deployment result.`, '', '## Repair priorities','',...report.backlog.slice(0,30).map(b=>`- ${b.priority} | ${clean(b.repository)} | ${clean(b.role)}: ${clean(b.task)}`),'','## Verification still required','',...report.manual_verification.map(v=>'- '+v.role+': '+v.task),'','## Scope limits','',...report.limitations.map(l=>'- '+l),'','Full backlog: latest/backlog.json. Evidence and recent runs: latest/repos/*.json.'];
 const md=lines.join('\n')+'\n';fs.writeFileSync(`${out}/summary.md`,md);
 const branch='engineering-control-reports';let base;
 try{base=(await github.rest.git.getRef({...context.repo,ref:'heads/'+branch})).data.object.sha;}catch(e){if(e.status!==404)throw e;base=(await github.rest.repos.getCommit({...context.repo,ref:'main'})).data.sha;await github.rest.git.createRef({...context.repo,ref:'refs/heads/'+branch,sha:base});}
 let previous=[];try{const p=(await github.rest.repos.getContent({...context.repo,path:'latest/backlog.json',ref:branch})).data;previous=JSON.parse(Buffer.from(p.content,'base64').toString('utf8'));}catch(e){report.gaps.push({check:'previous_snapshot',http:e.status||null});}
 const before=new Set(previous.map(b=>b.id)),now=new Set(report.backlog.map(b=>b.id));
 const delta={newly_observed:[...now].filter(id=>!before.has(id)),no_longer_observed:[...before].filter(id=>!now.has(id)),warning:'No longer observed is not a verified repair; coverage may have changed.'};
 const index={...report,repositories:report.repositories.map(r=>({repository:r.repository,report:'latest/repos/'+r.repository.replace('/','__')+'.json'})),backlog:undefined};
 const add=(path,obj)=>entries.push({path,mode:'100644',type:'blob',content:typeof obj==='string'?obj:JSON.stringify(obj,null,2)});
 add('latest/summary.md',md);add('latest/index.json',index);add('latest/backlog.json',report.backlog);add('latest/changes.json',delta);add('runs/'+context.runId+'/index.json',index);add('runs/'+context.runId+'/summary.md',md);add('runs/'+context.runId+'/backlog.json',report.backlog);
 for(const r of report.repositories){const path='latest/repos/'+r.repository.replace('/','__')+'.json';add(path,r);add('runs/'+context.runId+'/repos/'+r.repository.replace('/','__')+'.json',r);}
 persist();const commit=(await github.rest.git.getCommit({...context.repo,commit_sha:base})).data;
 const tree=(await github.rest.git.createTree({...context.repo,base_tree:commit.tree.sha,tree:entries})).data;
 const next=(await github.rest.git.createCommit({...context.repo,message:'engineering: evidence, workflow results and repair backlog [skip ci]',tree:tree.sha,parents:[base]})).data;
 await github.rest.git.updateRef({...context.repo,ref:'heads/'+branch,sha:next.sha,force:false});
 await core.summary.addRaw(md).addLink('Readable control report',`https://github.com/${context.repo.owner}/${context.repo.repo}/blob/${branch}/latest/summary.md`).write();
 if(report.gaps.some(g=>g.check==='repo_inventory'))core.setFailed('Incomplete account inventory; partial evidence published.');
}
module.exports={assess,signals,run};
if(require.main===module&&process.argv.includes('--self-test'))selftest();
