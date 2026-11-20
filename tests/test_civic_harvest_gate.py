import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("gate", Path(__file__).resolve().parents[1] / "tools/civic_harvest_gate.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

def summary(**updates):
    item = dict(root="fixture://source", reachable=True, budget_exhausted=False,
                endpoints_listed=1, endpoints_crawled=1, endpoints_remaining=0,
                new=1, unchanged=0, aliases=0, changed=0, errors=0, known_not_refetched=0)
    item.update(updates)
    return "[summary] " + json.dumps(item)

class GateTests(unittest.TestCase):
    def test_valid_summary(self):
        self.assertEqual(len(gate.summaries(summary(), ["fixture://source"])), 1)
    def test_missing_summary(self):
        with self.assertRaises(ValueError): gate.summaries("", ["fixture://source"])
    def test_unreachable(self):
        with self.assertRaises(ValueError): gate.summaries(summary(reachable=False), ["fixture://source"])
    def test_partial(self):
        with self.assertRaises(ValueError): gate.summaries(summary(budget_exhausted=True), ["fixture://source"])
    def test_errors(self):
        with self.assertRaises(ValueError): gate.summaries(summary(errors=1), ["fixture://source"])
    def test_missing_expected_source(self):
        with self.assertRaises(ValueError): gate.summaries(summary(), ["fixture://source", "fixture://other"])
    def test_duplicate_summary(self):
        with self.assertRaises(ValueError): gate.summaries(summary()+"\n"+summary(), ["fixture://source"])
    def test_empty(self):
        with self.assertRaises(ValueError): gate.summaries(summary(new=0), ["fixture://source"])
    def test_boolean_counter_rejected(self):
        with self.assertRaises(ValueError): gate.summaries(summary(new=True), ["fixture://source"])
    def test_bad_counter(self):
        with self.assertRaises(ValueError): gate.summaries(summary(new=-1), ["fixture://source"])
    def test_malformed_json(self):
        with self.assertRaises(ValueError): gate.summaries("[summary] {", ["fixture://source"])
    def test_unexpected_source(self):
        with self.assertRaises(ValueError): gate.summaries(summary(root="fixture://other"), ["fixture://source"])
    def fixture(self, root, value=None):
        data=b"%PDF-test-fixture-not-real-evidence"
        (root/"raw.pdf").write_bytes(data)
        db=root/"evidence.db"
        con=sqlite3.connect(db)
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("CREATE TABLE governance_items(item_id INTEGER, attachment_sha256 TEXT, local_pdf_path TEXT)")
        con.execute("INSERT INTO governance_items VALUES(1,?,?)", (value or hashlib.sha512(data).hexdigest(), "raw.pdf"))
        con.commit()
        return db,con
    def test_valid_raw(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);db,con=self.fixture(root)
            try: self.assertEqual(gate.audit_database(db,root)["records_verified"],1)
            finally: con.close()
    def test_corrupt_raw(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);db,con=self.fixture(root);(root/"raw.pdf").write_bytes(b"changed")
            try:
                with self.assertRaises(ValueError): gate.audit_database(db,root)
            finally: con.close()
    def test_missing_raw(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);db,con=self.fixture(root);(root/"raw.pdf").unlink()
            try:
                with self.assertRaises(FileNotFoundError): gate.audit_database(db,root)
            finally: con.close()
    def test_wal_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);db,con=self.fixture(root)
            try:
                gate.verified_snapshot(db,root/"snapshot.db",root)
                with sqlite3.connect(root/"snapshot.db") as out:
                    self.assertEqual(out.execute("SELECT COUNT(*) FROM governance_items").fetchone()[0],1)
            finally: con.close()
    def test_failed_snapshot_not_promoted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);db,con=self.fixture(root);(root/"raw.pdf").write_bytes(b"changed")
            try:
                with self.assertRaises(ValueError): gate.verified_snapshot(db,root/"snapshot.db",root)
                self.assertFalse((root/"snapshot.db").exists())
            finally: con.close()
    def test_preserves_prior_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);db,con=self.fixture(root);target=root/"snapshot.db";target.write_bytes(b"prior snapshot")
            (root/"raw.pdf").write_bytes(b"changed")
            try:
                with self.assertRaises(ValueError): gate.verified_snapshot(db,target,root)
                self.assertEqual(target.read_bytes(),b"prior snapshot")
            finally: con.close()
    def test_source_cannot_be_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);db,con=self.fixture(root)
            try:
                with self.assertRaises(ValueError): gate.verified_snapshot(db,db,root)
            finally: con.close()
    def test_symlink_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);db,con=self.fixture(root);approved=root/"approved";approved.mkdir()
            (approved/"raw.pdf").symlink_to(root/"raw.pdf")
            try:
                with self.assertRaises(ValueError): gate.audit_database(db,approved)
            finally: con.close()
    def test_sha256_legacy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);value=hashlib.sha256(b"%PDF-test-fixture-not-real-evidence").hexdigest();db,con=self.fixture(root,value)
            try: self.assertEqual(gate.audit_database(db,root)["records_verified"],1)
            finally: con.close()

if __name__ == "__main__": unittest.main(verbosity=2)
