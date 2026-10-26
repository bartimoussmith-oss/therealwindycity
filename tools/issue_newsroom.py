"""Build candidate issue dossiers from an explicitly approved public Markdown mirror."""
import argparse
from collections import defaultdict
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import re

RULES = {
    'land-use': ('Land use and development', r'\b(?:annex\w*|zon(?:e|ing)|subdivision|land use)\b'),
    'water': ('Water and wastewater', r'\b(?:water|wastewater|sewer|reclamation)\b'),
    'public-money': ('Budgets and public money', r'\b(?:budget|appropriat\w*|expenditure|funding|grant)\b'),
    'procurement': ('Contracts and procurement', r'\b(?:contract|procurement|bid|sole.source)\b'),
    'transportation': ('Roads and transportation', r'\b(?:road|street|traffic|transit|roundabout|sidewalk)\b'),
    'environment': ('Environment and waste', r'\b(?:landfill|contamin\w*|recycl\w*|drainage|flood|stormwater)\b'),
    'public-process': ('Public participation and procedure', r'\b(?:public comment|public hearing|referendum|petition|executive session)\b'),
    'housing': ('Housing and neighborhoods', r'\b(?:housing|residential|neighborhood|affordable)\b'),
    'public-safety': ('Public safety policy', r'\b(?:police|fire department|fire rescue|emergency services)\b'),
    'parks': ('Parks and recreation', r'\b(?:parks?|recreation|greenway|trails?)\b'),
    'economic-development': ('Economic development', r'\b(?:economic development|business park|data.center|LEADS)\b'),
    'utilities': ('Utilities and franchises', r'\b(?:electricity|franchise|utility|utilities|gas service)\b')
}
IDENT = re.compile(r'\b(ordinance|resolution|contract|PUDC)\s*(?:no\.?\s*|#\s*|-)?(\d[A-Za-z0-9]*(?:[-.]\d[A-Za-z0-9]*)*)\b', re.I)
STYLE = 'body{font:18px/1.6 system-ui;max-width:1000px;margin:auto;padding:24px}pre{white-space:pre-wrap;overflow-wrap:anywhere}article,section{border:1px solid #aaa;padding:18px;margin:18px 0}.notice{background:#fff2c7;padding:14px}'

def page(title, body):
    return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+escape(title)+'</title><style>'+STYLE+'</style></head><body>'+body+'</body></html>'

def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')

def build(corpus, out, revision, approved_public=False):
    if not approved_public:
        raise ValueError('Explicit approval of the public input mirror is required')
    corpus, out = Path(corpus).resolve(), Path(out).resolve()
    if not (corpus / 'llms.txt').is_file():
        raise ValueError('Expected a generated public mirror with llms.txt, not a repository root')
    if out == corpus or corpus in out.parents or out in corpus.parents:
        raise ValueError('Input and output must be separate non-nested directories')
    if out.exists() and any(out.iterdir()):
        raise ValueError('Use a fresh output directory; refusing to overwrite an existing workspace')
    out.mkdir(parents=True, exist_ok=True)
    records, issues, excluded, hashes = [], {}, [], defaultdict(list)
    for src in sorted(corpus.rglob('*.md')):
        rel = src.relative_to(corpus).as_posix()
        if src.is_symlink() or any(p.is_symlink() for p in src.parents if p != corpus and corpus in p.parents):
            excluded.append({'path':rel, 'reason':'symlink'})
            continue
        if not rel.startswith(('documents/', 'meetings/')):
            excluded.append({'path':rel, 'reason':'outside approved record paths'})
            continue
        raw = src.read_bytes()
        try:
            text = raw.decode('utf-8')
        except UnicodeDecodeError:
            excluded.append({'path':rel, 'reason':'not UTF-8'})
            continue
        rid = sha256(rel.encode()).hexdigest()[:24]
        version = sha256(raw).hexdigest()
        hashes[version].append(rid)
        title_match = re.search(r'^#\s+(.+)', text, re.M)
        title = title_match.group(1) if title_match else rel
        date_match = re.search(r'\b\d{4}-\d{2}-\d{2}\b', rel)
        record = {'id':rid,'path':rel,'title':title,'representation_sha256':version,'date_from_path':date_match.group() if date_match else None,'date_status':'unverified_path_label','source_family':'unresolved','memberships':[],'record_kind':'meeting_page' if rel.startswith('meetings/') else 'document_representation'}
        lines = text.splitlines()
        for slug, (label, pattern) in RULES.items():
            matches = [{'line':i+1,'text':line} for i,line in enumerate(lines) if re.search(pattern,line,re.I)]
            if matches:
                issues.setdefault(slug, {'id':slug,'title':label,'kind':'reporting_desk','members':[]})['members'].append({'record_id':rid,'basis':'lexical_candidate','review':'unreviewed','matches':matches})
                record['memberships'].append(slug)
        identifiers = sorted({(m.group(1).lower(),m.group(2).lower()) for m in IDENT.finditer(text)})
        for kind, identifier in identifiers:
            slug = 'identifier-'+kind+'-'+identifier.replace('.','-')
            pattern = re.compile(r'\b'+re.escape(kind)+r'\s*(?:no\.?\s*|#\s*|-)?'+re.escape(identifier)+r'\b',re.I)
            matches = [{'line':i+1,'text':line} for i,line in enumerate(lines) if pattern.search(line)]
            issues.setdefault(slug,{'id':slug,'title':kind.title()+' '+identifier.upper(),'kind':'identifier_candidate','members':[]})['members'].append({'record_id':rid,'basis':'identifier_candidate','review':'unreviewed','matches':matches})
            record['memberships'].append(slug)
        records.append(record)
        dest = out/'records'/rid
        dest.mkdir(parents=True)
        (dest/'text.txt').write_bytes(raw)
        body = '<nav><a href="../../index.html">Newsroom</a></nav><h1>'+escape(title)+'</h1><p>Full generated public representation; not a certified original or independent source.</p><p>Input path: '+escape(rel)+'</p><p>Representation SHA-256: '+version+'</p><a href="text.txt">Full text download</a><pre>'+escape(text)+'</pre>'
        (dest/'index.html').write_text(page(title,body),encoding='utf-8')
    by_id = {r['id']:r for r in records}
    intro = '<h1>Issue Newsroom</h1><p class="notice">Candidate groupings from the approved public mirror. No claim of exhaustive city history, verified relationships or completed reporting. Topic rules and identifier matches require review.</p><nav><a href="coverage.json">Coverage ledger</a> | <a href="catalog.json">Record catalog</a> | <a href="issues.json">Issue memberships</a> | <a href="unassigned.json">Unassigned records</a></nav>'
    for slug, issue in sorted(issues.items()):
        target = out/'issues'/slug
        target.mkdir(parents=True)
        body = '<nav><a href="../../index.html">All issues</a></nav><h1>'+escape(issue['title'])+'</h1><p class="notice">UNREVIEWED CANDIDATE DOSSIER. Co-occurrence is not proof of a relationship. Multiple records can derive from the same source.</p>'
        drafts = []
        for member in issue['members']:
            r = by_id[member['record_id']]
            body += '<article><h2><a href="../../records/'+r['id']+'/index.html">'+escape(r['title'])+'</a></h2><p>'+escape(member['basis'])+' / '+escape(r['path'])+'</p><details><summary>All matching lines in this representation</summary>'
            for match in member['matches']:
                body += '<p>Line '+str(match['line'])+'</p><pre>'+escape(match['text'])+'</pre>'
            body += '</details></article>'
            for angle in ('historical-explainer','decision-review','follow-up-question'):
                drafts.append({'id':slug+'-'+r['id']+'-'+angle,'issue_id':slug,'record_id':r['id'],'source_version':r['representation_sha256'],'angle':angle,'status':'reporting_prompt_not_publishable_story','evidence_locators':[m['line'] for m in member['matches']],'instructions':'Review full source, original record, dates, qualifications and later developments before asserting a finding. No outcome inferred.'})
        write_json(target/'story-queue.json',drafts)
        body += '<section><h2>Media reporting queue</h2><p>Three different reporting prompts per source representation. These are not distinct verified news events or publication-ready media drops.</p><a href="story-queue.json">Download evidence-linked reporting prompts</a></section>'
        (target/'index.html').write_text(page(issue['title'],body),encoding='utf-8')
        intro += '<article><h2><a href="issues/'+slug+'/index.html">'+escape(issue['title'])+'</a></h2><p>'+str(len(issue['members']))+' related representations / '+escape(issue['kind'])+'</p></article>'
    unassigned = [r['id'] for r in records if not r['memberships']]
    coverage = {'schema':'issue-newsroom-coverage-v1','input_revision':revision,'input_scope':'explicitly approved generated public Markdown mirror: documents/ and meetings/','included_representations':len(records),'candidate_groups':len(issues),'unassigned_records':len(unassigned),'excluded':excluded,'exact_representation_duplicate_groups':[ids for ids in hashes.values() if len(ids)>1],'source_independence':'not established; exact hash deduplication alone is insufficient','full_historical_coverage':False,'classification':'finite lexical rules plus identifier candidates; not semantic entity resolution','privacy':'approval of input mirror required; no private-repo scanning; upstream publication review remains required','media_status':'evidence-linked reporting prompts only; no verified stories or rendered assets'}
    write_json(out/'coverage.json',coverage)
    write_json(out/'catalog.json',records)
    write_json(out/'issues.json',list(issues.values()))
    write_json(out/'unassigned.json',unassigned)
    (out/'index.html').write_text(page('Issue Newsroom',intro),encoding='utf-8')
    return coverage

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--corpus',required=True)
    p.add_argument('--out',required=True)
    p.add_argument('--revision',required=True)
    p.add_argument('--approved-public',action='store_true')
    a = p.parse_args()
    print(json.dumps(build(a.corpus,a.out,a.revision,a.approved_public),indent=2))
