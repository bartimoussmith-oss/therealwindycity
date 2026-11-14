"""Offline regression tests for scrapers/granicus_harvester.py.

Run: python3 -m unittest tests/test_granicus_harvester.py -v

A local HTTP server plays a small Granicus site: a publisher listing with three
agendas, a duplicate file published under two URLs, an HTML wrapper that links
to the real PDF, a non-PDF attachment, an oversized response, and one document
whose bytes change between runs. No network access is used.
"""
import contextlib
import io
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scrapers"))
import granicus_harvester as harvester  # noqa: E402


def pdf(label: str) -> bytes:
    return b"%PDF-1.4\n% fixture " + label.encode() + b"\n%%EOF\n"


class FakeGranicus:
    def __init__(self):
        self.files = {
            "/MetaViewer.php?view_id=5&event_id=1&meta_id=101": pdf("a"),
            "/MetaViewer.php?view_id=5&event_id=1&meta_id=102": pdf("shared"),
            "/MetaViewer.php?view_id=5&event_id=2&meta_id=201": pdf("shared"),   # same bytes, second URL
            "/MetaViewer.php?view_id=5&event_id=2&meta_id=202": pdf("b"),        # must survive the duplicate before it
            "/files/packet.pdf": pdf("wrapped"),
            "/MetaViewer.php?view_id=5&event_id=3&meta_id=302": pdf("c"),
        }
        self.html = {
            "/ViewPublisher.php?view_id=5": "".join(
                f'<a href="//{{host}}/AgendaViewer.php?view_id=5&amp;event_id={n}">Agenda {n}</a>' for n in (1, 2, 3)),
            "/AgendaViewer.php?view_id=5&event_id=1":
                '<a href="MetaViewer.php?view_id=5&amp;event_id=1&amp;meta_id=101">A</a>'
                '<a href="MetaViewer.php?view_id=5&amp;event_id=1&amp;meta_id=102">Shared</a>',
            "/AgendaViewer.php?view_id=5&event_id=2":
                '<a href="MetaViewer.php?view_id=5&amp;event_id=2&amp;meta_id=201">Shared again</a>'
                '<a href="MetaViewer.php?view_id=5&amp;event_id=2&amp;meta_id=202">B</a>',
            "/AgendaViewer.php?view_id=5&event_id=3":
                '<a href="MetaViewer.php?view_id=5&amp;event_id=3&amp;meta_id=301">Wrapper</a>'
                '<a href="MetaViewer.php?view_id=5&amp;event_id=3&amp;meta_id=302">C</a>'
                '<a href="MetaViewer.php?view_id=5&amp;event_id=3&amp;meta_id=303">Not a PDF</a>'
                '<a href="MetaViewer.php?view_id=5&amp;event_id=3&amp;meta_id=304">Too large</a>',
            "/MetaViewer.php?view_id=5&event_id=3&meta_id=301": '<html><a href="/files/packet.pdf">open</a></html>',
            "/MetaViewer.php?view_id=5&event_id=3&meta_id=303": "<html>no document here</html>",
        }
        self.big = {"/MetaViewer.php?view_id=5&event_id=3&meta_id=304": b"%PDF" + b"x" * 4096}
        self.hits = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                fake.hits.append(self.path)
                host = self.headers.get("Host")
                if self.path == "/robots.txt":
                    return self._send(200, "text/plain", b"User-agent: *\nDisallow: /\n")
                if self.path in fake.files:
                    return self._send(200, "application/pdf", fake.files[self.path])
                if self.path in fake.big:
                    return self._send(200, "application/pdf", fake.big[self.path])
                if self.path in fake.html:
                    return self._send(200, "text/html", fake.html[self.path].replace("{host}", host).encode())
                self._send(404, "text/plain", b"missing")

            def _send(self, status, kind, body):
                self.send_response(status)
                self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.root = self.base + "/ViewPublisher.php?view_id=5"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class HarvesterTests(unittest.TestCase):
    def setUp(self):
        self.site = FakeGranicus()
        self.work = tempfile.mkdtemp(prefix="harvest-test-")
        self.db = os.path.join(self.work, "evidence.db")
        self.cwd = os.getcwd()
        os.chdir(self.work)  # artifacts/ is written relative to the working directory
        self._limit = harvester.MAX_PDF_BYTES
        harvester.MAX_PDF_BYTES = 2048

    def tearDown(self):
        harvester.MAX_PDF_BYTES = self._limit
        os.chdir(self.cwd)
        self.site.close()
        shutil.rmtree(self.work, ignore_errors=True)

    def run_harvest(self, **options):
        options.setdefault("delay", 0)
        options.setdefault("max_seconds", 60)
        with contextlib.redirect_stdout(io.StringIO()) as log:
            stats = harvester.harvest_and_ingest(self.site.root, "Test", options.pop("historical", True),
                                                 db_path=self.db, **options)
        stats["log"] = log.getvalue()
        return stats

    def rows(self, sql, *params):
        with contextlib.closing(sqlite3.connect(self.db)) as conn:
            return conn.execute(sql, params).fetchall()

    def test_first_run_ingests_every_distinct_document_past_a_duplicate(self):
        stats = self.run_harvest()
        self.assertEqual(stats["new"], 5)               # a, shared, b, wrapped, c
        self.assertEqual(stats["aliases"], 1)           # shared under its second URL
        self.assertEqual(stats["errors"], 1)            # only the oversized response
        self.assertNotIn("IntegrityError", stats["log"])
        self.assertNotIn("UNIQUE constraint", stats["log"])
        urls = {row[0] for row in self.rows("SELECT source_url FROM governance_items")}
        # The attachment listed AFTER the duplicate used to be lost with the rest of its agenda.
        self.assertIn(self.site.base + "/MetaViewer.php?view_id=5&event_id=2&meta_id=202", urls)
        self.assertIn(self.site.base + "/files/packet.pdf", urls)
        self.assertEqual(self.rows("SELECT COUNT(*) FROM document_aliases")[0][0], 1)

    def test_second_run_against_the_same_database_changes_nothing(self):
        self.run_harvest()
        before = self.rows("SELECT item_id, attachment_sha256, source_url FROM governance_items ORDER BY item_id")
        fts_before = self.rows("SELECT COUNT(*) FROM fts_forensic_archive")[0][0]
        stats = self.run_harvest()
        self.assertEqual((stats["new"], stats["changed"]), (0, 0))
        self.assertEqual(stats["unchanged"], 6)         # five rows plus the alias URL
        self.assertNotIn("IntegrityError", stats["log"])
        self.assertEqual(before, self.rows("SELECT item_id, attachment_sha256, source_url FROM governance_items ORDER BY item_id"))
        self.assertEqual(fts_before, self.rows("SELECT COUNT(*) FROM fts_forensic_archive")[0][0])
        self.assertEqual(fts_before, 5)

    def test_fts_rows_are_never_null_and_are_searchable(self):
        self.run_harvest(committee="Finance Committee", meeting_date="2026-10-06")
        self.assertEqual(self.rows("SELECT COUNT(*) FROM fts_forensic_archive WHERE body_text IS NULL")[0][0], 0)
        self.assertEqual(self.rows("SELECT COUNT(*) FROM governance_items WHERE extracted_text IS NULL")[0][0], 0)
        self.assertEqual(self.rows("SELECT COUNT(*) FROM fts_forensic_archive WHERE fts_forensic_archive MATCH 'finance'")[0][0], 5)
        self.assertEqual(self.rows("SELECT DISTINCT meeting_date, committee_or_body FROM governance_items"),
                         [("2026-10-06", "Finance Committee")])

    def test_changed_document_is_logged_once_and_the_original_is_kept(self):
        self.run_harvest()
        url = "/MetaViewer.php?view_id=5&event_id=1&meta_id=101"
        original = self.rows("SELECT attachment_sha256 FROM governance_items WHERE source_url = ?", self.site.base + url)
        self.site.files[url] = pdf("a-revised")
        self.assertEqual(self.run_harvest()["changed"], 1)
        self.assertEqual(self.run_harvest()["changed"], 0)   # the same change is not logged again
        self.assertEqual(self.rows("SELECT COUNT(*) FROM document_tamper_log")[0][0], 1)
        self.assertEqual(original, self.rows("SELECT attachment_sha256 FROM governance_items WHERE source_url = ?", self.site.base + url))

    def test_budget_stops_the_run_and_the_next_run_resumes(self):
        first = self.run_harvest(max_new=2)
        self.assertTrue(first["budget_exhausted"])
        self.assertEqual(first["new"], 2)
        self.assertGreater(first["endpoints_remaining"], 0)
        total = first["new"]
        for _ in range(4):
            total += self.run_harvest(max_new=2)["new"]
        self.assertEqual(total, 5)
        self.assertEqual(self.rows("SELECT COUNT(*) FROM governance_items")[0][0], 5)
        self.assertEqual(self.rows("SELECT COUNT(*) FROM harvest_progress WHERE status = 'ok'")[0][0], 3)

    def test_non_historical_run_only_visits_agendas_it_has_not_seen(self):
        self.run_harvest()
        self.site.hits.clear()
        stats = self.run_harvest(historical=False)
        self.assertEqual(stats["endpoints_crawled"], 1)   # only the listing, which is one request
        self.assertEqual([hit for hit in self.site.hits if "MetaViewer" in hit or "AgendaViewer" in hit], [])
        self.assertEqual(self.site.hits, ["/robots.txt", "/ViewPublisher.php?view_id=5"])

    def test_legacy_database_is_upgraded_in_place(self):
        with contextlib.closing(sqlite3.connect(self.db)) as conn:
            schema = (ROOT / "database" / "schema_rhetorical_profiling.sql").read_text()
            conn.executescript(schema.replace(",\n    robots_advisory_ignored INTEGER DEFAULT 0", ""))
            for table in ("document_tamper_log", "document_aliases", "harvest_progress"):
                conn.execute(f"DROP TABLE {table}")
            import hashlib
            conn.execute(
                "INSERT INTO governance_items (meeting_date, committee_or_body, title, attachment_sha256, source_url) VALUES (?,?,?,?,?)",
                ("2026-10-31", "Cheyenne Governing Body", "Agenda_Supporting Document",
                 hashlib.sha256(pdf("a")).hexdigest(), self.site.base + "/MetaViewer.php?view_id=5&event_id=1&meta_id=101"))
            conn.commit()
        stats = self.run_harvest()
        self.assertEqual((stats["new"], stats["unchanged"], stats["changed"]), (4, 1, 0))
        upgraded = self.rows("SELECT length(attachment_sha256), title FROM governance_items WHERE item_id = 1")
        self.assertEqual(upgraded, [(128, "Agenda_Supporting Document")])   # SHA-256 → SHA-512, row otherwise untouched

    def test_robots_result_is_recorded_and_can_be_enforced(self):
        stats = self.run_harvest()
        self.assertIs(stats["robots_allowed"], False)
        self.assertEqual(self.rows("SELECT DISTINCT robots_advisory_ignored FROM governance_items"), [(1,)])
        os.remove(self.db)
        self.site.hits.clear()
        stats = self.run_harvest(respect_robots=True)
        self.assertEqual(stats["new"], 0)
        self.assertEqual(self.site.hits, ["/robots.txt"])

    def test_cli_accepts_the_options_both_workflows_pass(self):
        env = dict(os.environ, PROMETHEAN_DB=self.db, HARVEST_DELAY_SECONDS="0")
        script = str(ROOT / "scrapers" / "granicus_harvester.py")
        auto = subprocess.run([sys.executable, script, self.site.root, "--prefix", "Cheyenne_Auto_Audit",
                               "--committee", "Cheyenne Governing Body", "--date", "2026-11-02"],
                              env=env, cwd=self.work, capture_output=True, text=True)
        self.assertEqual(auto.returncode, 0, auto.stderr)
        again = subprocess.run([sys.executable, script, self.site.root, "--historical"],
                               env=env, cwd=self.work, capture_output=True, text=True)
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertIn('"new": 0', again.stdout)
        down = subprocess.run([sys.executable, script, "http://127.0.0.1:9/ViewPublisher.php?view_id=5"],
                              env=env, cwd=self.work, capture_output=True, text=True)
        self.assertEqual(down.returncode, 1)   # an unreachable source is a failed run, not a silent success


if __name__ == "__main__":
    unittest.main()
