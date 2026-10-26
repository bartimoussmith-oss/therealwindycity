"""Integrate public-mirror issue dossiers with the Media Studio editor."""
import argparse
from html import escape
import json
from pathlib import Path
import re
from urllib.parse import quote
import issue_newsroom

SITE = 'https://bartimoussmith-oss.github.io/therealwindycity/'

def integrate(corpus, site, revision):
    site = Path(site)
    if not (site/'index.html').is_file() or not (site/'media'/'newsroom.html').is_file():
        raise ValueError('Render existing site and copy Media Studio first')
    out = site/'newsroom'
    report = issue_newsroom.build(corpus,out,revision,True)
    if report['included_representations'] == 0:
        raise ValueError('Refusing empty newsroom')
    catalog = json.loads((out/'catalog.json').read_text(encoding='utf-8'))
    issues = json.loads((out/'issues.json').read_text(encoding='utf-8'))
    records = {r['id']:r for r in catalog}
    for issue in issues:
        evidence = []
        for m in issue['members']:
            r = records[m['record_id']]
            evidence.append({'record_id':r['id'],'title':r['title'],'source_version':r['representation_sha256'],'source_url':SITE+quote(r['path'],safe='/'),'reader_url':SITE+'newsroom/records/'+r['id']+'/index.html','date_label':r['date_from_path'],'date_status':r['date_status'],'source_family':r['source_family'],'basis':m['basis'],'review':m['review'],'passages':m['matches']})
        packet = {'schema':'issue-media-input-v1','issue_id':issue['id'],'title':issue['title'],'input_revision':revision,'status':'unreviewed_candidate_collection','evidence':evidence,'limitations':'Candidate groupings require review. Dates are path labels, not verified event dates. Related representations may derive from the same source. Original records and later developments must be checked. No exhaustive city-history coverage claimed.'}
        folder = out/'issues'/issue['id']
        (folder/'editor.json').write_text(json.dumps(packet,ensure_ascii=False),encoding='utf-8')
        page = folder/'index.html'
        text = page.read_text(encoding='utf-8')
        nav = '<section><h2>Create media from this issue</h2><p>Open all linked records and candidate passages in the Media Studio editor. Add a reviewed finding; no government outcome is inferred automatically.</p><a href="../../../media/newsroom.html?issue='+quote(issue['id'],safe='')+'">Create source-linked media draft</a></section>'
        page.write_text(text.replace('</body>',nav+'</body>'),encoding='utf-8')
    home = out/'index.html'
    text = home.read_text(encoding='utf-8')
    home.write_text(text.replace('<h1>','<nav><a href="../media/index.html">Media Studio</a> | <a href="../media/projects.html">Ecosystem status</a></nav><h1>',1),encoding='utf-8')
    report['editor_input_packets'] = len(issues)
    report['integration_revision'] = revision
    report['media_adapter'] = 'source-linked browser editor; findings require human review'
    report['media_outputs'] = ['readable HTML','article copy','newsletter copy','social copy','video script','source manifest JSON']
    (out/'coverage.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    verify(site)
    return report

def verify(site):
    site = Path(site)
    out = site/'newsroom'
    coverage = json.loads((out/'coverage.json').read_text(encoding='utf-8'))
    issues = json.loads((out/'issues.json').read_text(encoding='utf-8'))
    records = json.loads((out/'catalog.json').read_text(encoding='utf-8'))
    if not records or len(records) != coverage['included_representations']:
        raise ValueError('Catalog/coverage mismatch')
    for r in records:
        if not (out/'records'/r['id']/'index.html').is_file() or not (out/'records'/r['id']/'text.txt').is_file():
            raise ValueError('Missing record representation')
    for i in issues:
        packet = json.loads((out/'issues'/i['id']/'editor.json').read_text(encoding='utf-8'))
        if len(packet['evidence']) != len(i['members']):
            raise ValueError('Editor dropped issue evidence')
        if not (out/'issues'/i['id']/'story-queue.json').is_file():
            raise ValueError('Missing reporting queue')
    total = sum(p.stat().st_size for p in site.rglob('*') if p.is_file())
    if total > 900*1024*1024:
        raise ValueError('Site exceeds 900 MiB release budget; partition before publishing')
    return coverage

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--corpus')
    p.add_argument('--site',required=True)
    p.add_argument('--revision',default='unknown')
    p.add_argument('--verify-only',action='store_true')
    a = p.parse_args()
    if not a.verify_only and not a.corpus:
        p.error('--corpus is required for generation')
    print(json.dumps(verify(a.site) if a.verify_only else integrate(a.corpus,a.site,a.revision),indent=2))
