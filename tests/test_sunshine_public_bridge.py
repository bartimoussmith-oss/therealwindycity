import importlib.util
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
SPEC=importlib.util.spec_from_file_location('sunshine_bridge',Path(__file__).resolve().parents[1]/'tools/sync_sunshine_to_rwc.py')
bridge=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(bridge)
SCHEMA='''
CREATE TABLE wy_99_municipalities(municipality TEXT,county TEXT);
CREATE TABLE panopticon_municipalities(domain TEXT,org_name TEXT,city TEXT,state TEXT,flags_json TEXT);
CREATE TABLE wy_wpma_documents(id INTEGER,municipality TEXT,county TEXT,meeting_date TEXT,url TEXT,sha256 TEXT,evidence_tier TEXT,flags_json TEXT);
CREATE TABLE sunshine_publication_approvals(document_id INTEGER,publication_tier TEXT,evidence_tier TEXT,legal_review_approved INTEGER,right_of_reply_completed INTEGER,sha256 TEXT,approved_by TEXT,approved_utc TEXT,source_url TEXT,municipality TEXT,meeting_date TEXT,public_summary TEXT,public_quote TEXT);
'''
class PublicBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.db=self.root/'source.db'
        self.c=sqlite3.connect(self.db);self.c.executescript(SCHEMA)
        self.c.execute('INSERT INTO wy_99_municipalities VALUES(?,?)',('Example Town','Example County'))
        self.canary='sensitive-review-'+str(id(self))
        self.c.execute('INSERT INTO panopticon_municipalities VALUES(?,?,?,?,?)',('example.gov','Example Town','Example','WY',self.canary))
        self.c.execute('INSERT INTO wy_wpma_documents VALUES(?,?,?,?,?,?,?,?)',(1,'Example Town','Example County','2026-01-01','https://example.gov/minutes.pdf','a'*64,'TIER_A','[]'))
        self.c.commit()
    def tearDown(self):self.c.close();self.tmp.cleanup()
    def approve(self,**overrides):
        row={'document_id':1,'publication_tier':bridge.PUBLIC,'evidence_tier':'TIER_A','legal_review_approved':1,'right_of_reply_completed':1,
          'sha256':'a'*64,'approved_by':'test reviewer','approved_utc':'2026-11-27T00:00:00Z','source_url':'https://example.gov/minutes.pdf',
          'municipality':'Example Town','meeting_date':'2026-01-01','public_summary':'Reviewed fixture summary','public_quote':'Fixture quote'}
        row.update(overrides)
        self.c.execute('INSERT INTO sunshine_publication_approvals VALUES('+','.join('?' for _ in row)+')',tuple(row.values()));self.c.commit()
    def test_label_alone_does_not_publish(self):
        public,_=bridge.build_public_export(self.db);self.assertEqual(public['approved_findings'],[])
    def test_approved_matching_hash_exports(self):
        self.approve();public,_=bridge.build_public_export(self.db);self.assertEqual(len(public['approved_findings']),1)
    def test_stale_hash_rejected(self):
        self.approve(sha256='b'*64);public,_=bridge.build_public_export(self.db);self.assertEqual(public['approved_findings'],[])
    def test_unreviewed_evidence_rejected(self):
        self.approve(evidence_tier='TIER_C');public,_=bridge.build_public_export(self.db);self.assertEqual(public['approved_findings'],[])
    def test_no_reply_review_no_publication(self):
        self.approve(right_of_reply_completed=0);public,_=bridge.build_public_export(self.db);self.assertEqual(public['approved_findings'],[])
    def test_private_canary_excluded(self):
        public,_=bridge.build_public_export(self.db);self.assertNotIn(self.canary,json.dumps(public))
    def test_private_queue_outside_repo(self):
        repo=self.root/'repo';repo.mkdir()
        with self.assertRaises(ValueError):bridge.write_outputs(self.db,repo,repo/'private')
    def test_private_permissions(self):
        self.c.execute("UPDATE wy_wpma_documents SET evidence_tier='TIER_C'");self.c.commit()
        out=self.root/'review';repo=self.root/'repo';repo.mkdir()
        bridge.write_outputs(self.db,repo,out)
        self.assertEqual((out/'tier_c_review_queue.json').stat().st_mode&0o777,0o600)
        self.assertEqual(out.stat().st_mode&0o777,0o700)
    def test_missing_database_fails_closed(self):
        with self.assertRaises(FileNotFoundError):bridge.build_public_export(self.root/'absent.db')
    def test_private_classification_rejected(self):
        with self.assertRaises(ValueError):bridge.clean_string('PUB_'+'TIER_3_'+'PRIVATE'+'_REVIEW')
    def test_credential_in_approved_text_rejected(self):
        self.approve(public_summary='gh'+'p_'+'x'*40)
        with self.assertRaises(ValueError):bridge.build_public_export(self.db)
    def test_secret_query_url_rejected(self):
        with self.assertRaises(ValueError):bridge.public_url('https://example.gov/minutes?access=token')
    def test_public_allowlist_omits_internal_flags(self):
        public,_=bridge.build_public_export(self.db)
        self.assertNotIn('flags_json',json.dumps(public));self.assertNotIn('illegality_score',json.dumps(public))
if __name__=='__main__':unittest.main(verbosity=2)
