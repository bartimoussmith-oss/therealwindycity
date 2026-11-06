import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

class InstanceRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'wyoming').mkdir()
        self.runner = self.root / 'wyoming/run-instance.sh'
        self.runner.write_text((ROOT / 'wyoming/run-instance.sh').read_text())
        self.instance = self.root / 'wyoming/instances/fixture'
        (self.instance / 'config').mkdir(parents=True)
        (self.instance / 'ecosystem.json').write_text('{}')
        (self.instance / 'env.sh').write_text('export ENGINE_CUSTODIAN_OFFICE="Fixture Clerk"\n')
        (self.root / 'run.py').write_text(r"""import json, os, sys
from pathlib import Path
root = Path(__file__).resolve().parent
args = sys.argv[1:]
data = Path(os.environ['ENGINE_DATA_DIR'])
with (root / 'audit.jsonl').open('a') as out:
    out.write(json.dumps(dict(args=args, data=str(data), office=os.environ.get('ENGINE_CUSTODIAN_OFFICE'))) + '\n')
if args[0] == 'init':
    data.mkdir(parents=True, exist_ok=True)
    (data / 'engine.db').touch()
if args[0] == 'request' and '--help' not in args and not (data / 'engine.db').exists():
    raise SystemExit(9)
if args[0] == 'selftest':
    data.mkdir(parents=True, exist_ok=True)
    (data / 'fixture.txt').write_text('synthetic only')
    if '--fail' in args:
        raise SystemExit(7)
""")
        self.env = {k:v for k,v in os.environ.items() if not k.startswith('ENGINE_')}

    def run_command(self, *args):
        return subprocess.run(['bash', str(self.runner), *args], env=self.env, capture_output=True, text=True)

    def audit(self):
        path = self.root / 'audit.jsonl'
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def test_request_initializes_and_preserves_arguments(self):
        args = ('fixture', 'request', 'pra', 'records with spaces', '2026-01-01 to present')
        result = self.run_command(*args)
        self.assertEqual(result.returncode, 0, result.stderr)
        audit = self.audit()
        self.assertEqual(audit[0]['args'], ['init'])
        self.assertEqual(audit[1]['args'], list(args[1:]))
        self.assertEqual(audit[1]['office'], 'Fixture Clerk')

    def test_unknown_or_traversal_slug_never_executes(self):
        for slug in ('../fixture', '/tmp', 'missing', 'fixture/../../', ''):
            self.assertEqual(self.run_command(slug, 'init').returncode, 2)
        self.assertEqual(self.audit(), [])

    def test_missing_command_never_executes(self):
        self.assertEqual(self.run_command('fixture').returncode, 2)
        self.assertEqual(self.audit(), [])

    def test_help_does_not_initialize(self):
        self.assertEqual(self.run_command('fixture', 'request', '--help').returncode, 0)
        self.assertEqual([r['args'] for r in self.audit()], [['request', '--help']])
        self.assertFalse((self.root / 'data').exists())

    def test_selftest_is_temporary_and_cleaned(self):
        self.env['ENGINE_DATA_DIR'] = str(self.root / 'persistent')
        self.assertEqual(self.run_command('fixture', 'selftest').returncode, 0)
        self.assertFalse(Path(self.audit()[0]['data']).exists())
        self.assertFalse((self.root / 'persistent').exists())

    def test_failed_selftest_cleans_and_preserves_exit_code(self):
        self.assertEqual(self.run_command('fixture', 'selftest', '--fail').returncode, 7)
        self.assertFalse(Path(self.audit()[0]['data']).exists())

    def test_crawl_initializes_storage(self):
        self.assertEqual(self.run_command('fixture', 'crawl').returncode, 0)
        self.assertEqual([r['args'] for r in self.audit()], [['init'], ['crawl']])

    def test_symlinked_instance_is_rejected(self):
        (self.instance.parent / 'alias').symlink_to(self.instance, target_is_directory=True)
        self.assertEqual(self.run_command('alias', 'init').returncode, 2)
        self.assertEqual(self.audit(), [])

if __name__ == '__main__':
    unittest.main()
