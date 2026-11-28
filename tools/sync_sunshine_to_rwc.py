#!/usr/bin/env python3
"""Fail-closed public snapshot bridge. Only allowlisted fields leave the source vault.
Discovery coverage is not a misconduct finding. Findings require a matching content
hash and an explicit reviewer approval; source evidence labels alone are insufficient.
"""
import argparse
import hashlib
import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

SCHEMA = 'sunshine-public-1.0'
PUBLIC = 'PUB_TIER_1_PUBLIC'
ALLOWED_EVIDENCE = {'TIER_A', 'TIER_B', 'EVID_TIER_A_FACIAL', 'EVID_TIER_B_TRANSCRIPT'}

def readonly(path):
    path=Path(path).resolve()
    if not path.is_file(): raise FileNotFoundError('Required source database is missing')
    c=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=15)
    c.row_factory=sqlite3.Row
    c.execute('PRAGMA query_only=ON')
    return c

def table_exists(c,name):
    return c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone() is not None

def clean_string(value,limit=1000):
    if value is None:return None
    if not isinstance(value,str):raise ValueError('Expected text')
    if len(value)>limit:raise ValueError('Oversized public field')
    # Reject path, credential, private-classification and private-address content.
    forbidden=[r'/home/',r'/Users/',r'(?i)bearer\s+\S+',
      r'(?i)(?:gh[pousr]_|github_pat_|AIza|AKIA)[A-Za-z0-9_-]{12,}',
      r'-----BEGIN [A-Z ]*PRIVATE KEY-----',r'(?i)sk-[a-z0-9_-]{20,}',
      r'\b10\.\d+\.\d+\.\d+\b',r'\b192\.168\.\d+\.\d+\b',
      'PUB_'+'TIER_3_'+'PRIVATE','PUB_'+'TIER_2_'+'COMMERCIAL']
    if any(re.search(p,value) for p in forbidden):raise ValueError('Disallowed public field content')
    return value

def public_url(value):
    clean_string(value,2000)
    u=urlsplit(value)
    if u.scheme!='https' or not u.hostname or u.username or u.password:
        raise ValueError('Public sources require an HTTPS URL without embedded credentials')
    if u.query or u.fragment:raise ValueError('Query-bearing source URLs require separate review')
    if u.hostname in {'localhost','127.0.0.1','0.0.0.0'}:raise ValueError('Local source URL not public')
    if re.fullmatch(r'[\d.]+',u.hostname) or ':' in u.hostname:raise ValueError('Numeric hosts require separate source review')
    return value

def build_public_export(vault_path):
    c=readonly(vault_path)
    try:
        # Required schema errors propagate; never turn failed queries into clearance.
        towns=[]
        for r in c.execute('SELECT municipality,county FROM wy_99_municipalities ORDER BY county,municipality'):
            towns.append({'municipality':clean_string(r['municipality'],120),
              'county':clean_string(r['county'],120),'review_status':'NOT_CLEARED',
              'coverage_type':'SUPPLIED_ROSTER','verified_legal_violations':None})
        candidates=[]
        for r in c.execute('SELECT domain,org_name,city,state FROM panopticon_municipalities ORDER BY state,org_name LIMIT 200'):
            candidates.append({'domain':clean_string(r['domain'],253),'organization_candidate':clean_string(r['org_name'],250),
              'city':clean_string(r['city'],120),'state':clean_string(r['state'],10),
              'review_status':'DISCOVERY_ONLY','government_identity_verified':False})
        findings=[]
        if table_exists(c,'sunshine_publication_approvals'):
            q='''SELECT a.*,d.sha256 AS actual_sha256,d.url AS artifact_url
              FROM sunshine_publication_approvals a JOIN wy_wpma_documents d ON d.id=a.document_id
              WHERE a.publication_tier=? AND a.legal_review_approved=1 AND a.right_of_reply_completed=1'''
            for r in c.execute(q,(PUBLIC,)):
                if r['evidence_tier'] not in ALLOWED_EVIDENCE:continue
                if not re.fullmatch(r'[a-f0-9]{64}',r['sha256'] or '') or r['sha256']!=r['actual_sha256']:continue
                if not r['approved_by'] or not r['approved_utc']:continue
                if r['source_url']!=r['artifact_url']:continue
                findings.append({'municipality':clean_string(r['municipality'],120),
                  'meeting_date':clean_string(r['meeting_date'],30),'source_url':public_url(r['source_url']),
                  'sha256':r['sha256'],'evidence_tier':r['evidence_tier'],
                  'summary':clean_string(r['public_summary'],2000),'quote':clean_string(r['public_quote'],3000),
                  'review_status':'APPROVED_FOR_PUBLICATION'})
        private=[dict(r) for r in c.execute("SELECT id,municipality,county,meeting_date,url,sha256,evidence_tier,flags_json FROM wy_wpma_documents WHERE evidence_tier='TIER_C'")]
        registry_count=c.execute('SELECT COUNT(*) FROM cisa_domain_registry').fetchone()[0] if table_exists(c,'cisa_domain_registry') else None
        payload={'schema_version':SCHEMA,'publication_tier':PUBLIC,'generated_utc':datetime.now(timezone.utc).isoformat(),
          'summary_metrics':{'wyoming_roster_rows':len(towns),'approved_findings':len(findings),
            'nationwide_pilot_candidates':len(candidates),'national_registry_domain_rows':registry_count},
          'wyoming_roster':towns,'approved_findings':findings,'nationwide_discovery':candidates,
          'limitations':['Roster coverage is not a completed municipal audit.',
            'Domain candidates are not reconciled to a national government census.',
            'No public misconduct, hostility, tampering, or litigation-success score is exported.',
            'Unreviewed findings, private infrastructure metadata and raw search results are excluded.',
            'An empty approved-findings list is not a finding of compliance.']}
        return payload,{'generated_utc':payload['generated_utc'],'review_queue':private}
    finally:c.close()

def write_outputs(vault,rwc_repo,private_out=None):
    repo=Path(rwc_repo).resolve()
    if private_out:
        private_path=Path(private_out).resolve()
        if private_path.is_relative_to(repo):raise ValueError('Review queue must remain outside the public repository')
    public,private=build_public_export(vault)
    raw=(json.dumps(public,indent=2,ensure_ascii=False)+'\n').encode()
    targets=[repo/'data/sunshine_public_export.json',repo/'public/sunshine_scorecard.json']
    for p in targets:
        if p.exists() and p.is_symlink():raise ValueError('Snapshot destination must not be a symlink')
        if not p.resolve().is_relative_to(repo):raise ValueError('Snapshot destination outside repository')
        p.parent.mkdir(parents=True,exist_ok=True)
        temp=p.with_suffix('.tmp');temp.write_bytes(raw);temp.replace(p)
    if private_out:
        private_path.mkdir(parents=True,exist_ok=True,mode=0o700)
        os.chmod(private_path,0o700)
        p=private_path/'tier_c_review_queue.json'
        if p.is_symlink():raise ValueError('Review queue must not be a symlink')
        fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
        with os.fdopen(fd,'w') as f:json.dump(private,f,indent=2)
        os.chmod(p,0o600)
    return public,hashlib.sha256(raw).hexdigest()

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--vault',required=True);ap.add_argument('--rwc-repo',required=True)
    ap.add_argument('--private-out');a=ap.parse_args()
    public,sha=write_outputs(a.vault,a.rwc_repo,a.private_out)
    print(json.dumps({'status':'PUBLIC_ALLOWLIST_EXPORT_READY','sha256':sha,'counts':public['summary_metrics']},indent=2))
if __name__=='__main__':main()
