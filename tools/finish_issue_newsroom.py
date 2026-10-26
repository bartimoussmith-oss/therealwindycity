"""Connect compact issue dossiers to complete existing public mirror records."""
import argparse
from hashlib import sha256
from html import escape
import json
from pathlib import Path
from urllib.parse import quote
import issue_newsroom

SITE='https://bartimoussmith-oss.github.io/therealwindycity/'

def dump(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,separators=(',',':')),encoding='utf-8')

def size(path):
    return sum(p.stat().st_size for p in path.rglob('*') if p.is_file())

def integrate(corpus,site,revision):
    site=Path(site)
    if not (site/'index.html').is_file() or not (site/'media/newsroom.html').is_file():
        raise ValueError('Render existing site and copy Media Studio first')
    baseline=size(site)
    out=site/'newsroom'
    report=issue_newsroom.build(corpus,out,revision,True)
    if not report['included_representations']:
        raise ValueError('Refusing empty newsroom')
    before=size(out)
    catalog=json.loads((out/'catalog.json').read_text(encoding='utf-8'))
    issues=json.loads((out/'issues.json').read_text(encoding='utf-8'))
    records={r['id']:r for r in catalog}
    for r in catalog:
        canonical=site/r['path']
        if not canonical.is_file() or sha256(canonical.read_bytes()).hexdigest()!=r['representation_sha256']:
            raise ValueError('Missing or changed full mirror representation: '+r['path'])
        dest=out/'records'/r['id']
        # Remove only the duplicate created moments ago by issue_newsroom.build.
        duplicate=dest/'text.txt'
        if duplicate.exists(): duplicate.unlink()
        url=SITE+quote(r['path'],safe='/')
        body='<nav><a href="../../index.html">Newsroom</a></nav><h1>'+escape(r['title'])+'</h1><p>The complete text remains in the existing public mirror; it is not truncated or duplicated here.</p><p><a href="'+escape(url,quote=True)+'">Read/download the complete mirror representation</a></p><p>Input path: '+escape(r['path'])+'</p><p>SHA-256: '+r['representation_sha256']+'</p><p>This is a generated representation, not a certified original or independent source.</p>'
        (dest/'index.html').write_text(issue_newsroom.page(r['title'],body),encoding='utf-8')
    for issue in issues:
        folder=out/'issues'/issue['id']
        evidence=[]
        body='<nav><a href="../../index.html">All issues</a></nav><h1>'+escape(issue['title'])+'</h1><p class="notice">UNREVIEWED CANDIDATE DOSSIER. Source families and path dates are unverified. Text matches are not verified relationships.</p><p>Every member and matching-line reference is retained. Open the editor to load complete matching passages on demand.</p><a href="../../../media/newsroom.html?issue='+quote(issue['id'],safe='')+'">Create source-linked media draft / inspect passages</a>'
        for m in issue['members']:
            r=records[m['record_id']]
            m['matches']=[{'line':x['line']} for x in m['matches']]
            evidence.append({'record_id':r['id'],'title':r['title'],'source_version':r['representation_sha256'],'source_url':SITE+quote(r['path'],safe='/'),'reader_url':SITE+'newsroom/records/'+r['id']+'/index.html','date_label':r['date_from_path'],'date_status':r['date_status'],'source_family':r['source_family'],'basis':m['basis'],'review':m['review'],'passages':m['matches']})
            body+='<article><h2><a href="../../records/'+r['id']+'/index.html">'+escape(r['title'])+'</a></h2><p>'+escape(m['basis'])+' / '+escape(r['path'])+'</p><details><summary>'+str(len(m['matches']))+' matching line references</summary><p>'+', '.join(str(x['line']) for x in m['matches'])+'</p></details></article>'
        packet={'schema':'issue-media-input-v1','issue_id':issue['id'],'title':issue['title'],'input_revision':revision,'status':'unreviewed_candidate_collection','evidence':evidence,'limitations':'Candidate groupings require review. Dates are unverified path labels. Representations may derive from the same source. Check originals and later developments. No exhaustive historical coverage claimed.','passage_storage':'line references; full text loaded from hash-verified mirror on demand'}
        dump(folder/'editor.json',packet)
        body+='<section><h2>Reporting prompts</h2><p>Prompts are not verified news findings or finished articles.</p><a href="story-queue.json">Evidence-linked reporting queue</a></section>'
        (folder/'index.html').write_text(issue_newsroom.page(issue['title'],body),encoding='utf-8')
    dump(out/'issues.json',issues)
    dump(out/'catalog.json',catalog)
    home=out/'index.html'
    home.write_text(home.read_text(encoding='utf-8').replace('<h1>','<nav><a href="../media/index.html">Media Studio</a> | <a href="../media/projects.html">Ecosystem status</a></nav><h1>',1),encoding='utf-8')
    report.update({'editor_input_packets':len(issues),'integration_revision':revision,'media_adapter':'source-linked editor with hash-verified on-demand passages; findings require human review','media_outputs':['readable HTML','article copy','newsletter copy','social copy','video script','source manifest JSON'],'storage':{'existing_site_bytes':baseline,'newsroom_before_compaction_bytes':before,'newsroom_after_compaction_bytes':size(out),'canonical_records_retained':len(catalog),'truncated_records':0}})
    dump(out/'coverage.json',report)
    verify(site)
    return report

def verify(site):
    site=Path(site);out=site/'newsroom'
    coverage=json.loads((out/'coverage.json').read_text(encoding='utf-8'))
    catalog=json.loads((out/'catalog.json').read_text(encoding='utf-8'))
    issues=json.loads((out/'issues.json').read_text(encoding='utf-8'))
    records={r['id']:r for r in catalog}
    if not catalog or len(catalog)!=coverage['included_representations']:
        raise ValueError('Catalog/coverage mismatch')
    for r in catalog:
        canonical=site/r['path']
        if not canonical.is_file() or sha256(canonical.read_bytes()).hexdigest()!=r['representation_sha256']:
            raise ValueError('Canonical record missing/changed: '+r['path'])
        if not (out/'records'/r['id']/'index.html').is_file():
            raise ValueError('Missing reader link')
    for issue in issues:
        folder=out/'issues'/issue['id']
        packet=json.loads((folder/'editor.json').read_text(encoding='utf-8'))
        if [e['record_id'] for e in packet['evidence']]!=[m['record_id'] for m in issue['members']]:
            raise ValueError('Editor membership mismatch')
        for e,m in zip(packet['evidence'],issue['members']):
            if e['passages']!=m['matches'] or e['source_version']!=records[e['record_id']]['representation_sha256']:
                raise ValueError('Evidence reference mismatch')
        if not (folder/'story-queue.json').is_file(): raise ValueError('Missing queue')
    total=size(site)
    if total>900*1024*1024:
        raise ValueError('Site exceeds 900 MiB release budget after compaction: '+str(total)+' bytes; partition before publishing')
    return coverage

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--corpus');p.add_argument('--site',required=True);p.add_argument('--revision',default='unknown');p.add_argument('--verify-only',action='store_true');a=p.parse_args()
    if not a.verify_only and not a.corpus: p.error('--corpus is required')
    print(json.dumps(verify(a.site) if a.verify_only else integrate(a.corpus,a.site,a.revision),indent=2))
