"""Multi-file (bundle) artifacts: safe paths, manifest integrity, run-the-entry checks."""
import shutil
import tempfile
import unittest
from pathlib import Path

from axbranch import artifacts, engine as E
from axbranch.state import Store
from tests.test_engine import Script

LIB = "def add(a, b):\n    return a + b\n"
ENTRY = ("import sys\nfrom calc.core import add\n\nif __name__ == '__main__':\n"
         "    assert add(2, 3) == 5\n    print('bundle ok')\n")
GOOD_FILES = [{'path': 'calc/__init__.py', 'content': ''}, {'path': 'calc/core.py', 'content': LIB},
              {'path': 'run_tests.py', 'content': ENTRY}, {'path': 'README.md', 'content': '# calc\n'}]


class BundleScript(Script):
    def __init__(self, builds, verdicts):
        super().__init__([], verdicts)
        self.bundle_builds = list(builds)

    def __call__(self, prompt, schema, prefer='claude', web=False, cancel=None, **kw):
        if schema is E.PLAN:
            plan, used, notes = super().__call__(prompt, schema, prefer, web, cancel)
            plan.update(artifact_kind='bundle', artifact_filename='run_tests.py')
            return plan, used, notes
        if schema is E.BUILD:
            self.prompts.append((schema, prefer, prompt))
            return {'content': '', 'files': self.bundle_builds.pop(0), 'summary': 's', 'changes_from_previous': ''}, prefer, []
        return super().__call__(prompt, schema, prefer, web, cancel)


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.store = Store(self.tmp / 'ws' / 'axbranch.sqlite3')

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def engine(self, script):
        return E.Engine(self.store, workspace=self.tmp / 'ws', vault=self.tmp / 'v', gai_db=self.tmp / 'x.db', llm=script)

    def test_safe_relpath(self):
        for ok in ('a.py', 'pkg/mod.py', 'pkg\\mod.py', 'docs/READ-ME_1.md'):
            self.assertIsNotNone(artifacts.safe_relpath(ok), ok)
        self.assertEqual(artifacts.safe_relpath('a/./b.py'), 'a/b.py')     # normalized, still inside
        for bad in ('', '/etc/passwd', 'C:/x.py', 'c:x.py', '../x.py', 'a/../../x.py', 'a b.py', '~/.ssh/x'):
            self.assertIsNone(artifacts.safe_relpath(bad), bad)

    def test_bundle_builds_runs_entry_and_passes(self):
        eng = self.engine(BundleScript([GOOD_FILES], ['PASS']))
        pid = self.store.new_project('make a calc package')
        p = eng.run(pid)
        self.assertEqual(p['state'], 'OWNER_REVIEW')
        art = self.store.artifacts(pid)[-1]
        self.assertEqual(art['kind'], 'bundle')
        self.assertEqual(sorted(r for r, _, _ in artifacts.files_of(art)),
                         ['README.md', 'calc/__init__.py', 'calc/core.py', 'run_tests.py'])
        v = self.store.verifications(pid)[-1]
        self.assertTrue(v['checks']['ok'])
        self.assertIn('bundle ok', v['checks']['output'])
        self.assertEqual(eng.consistency(pid), [])
        # Tampering with one file, or adding an unrecorded one, is detected.
        extra = Path(art['path']) / 'evil.py'
        extra.write_text('x', encoding='utf-8')
        self.assertTrue(any('unexpected file: evil.py' in m for m in eng.consistency(pid)))
        extra.unlink()
        (Path(art['path']) / 'calc' / 'core.py').write_text(LIB.replace('+', '-'), encoding='utf-8')
        self.assertTrue(any('calc/core.py' in m for m in eng.consistency(pid)))

    def test_unsafe_paths_are_refused_and_fail_verification(self):
        hostile = GOOD_FILES + [{'path': '../../escape.py', 'content': 'x'}]
        eng = self.engine(BundleScript([hostile, GOOD_FILES], ['PASS', 'PASS']))
        pid = self.store.new_project('make a calc package')
        eng.run(pid)
        self.assertFalse((self.tmp / 'ws' / 'projects' / 'escape.py').exists())
        self.assertFalse(any(p.name == 'escape.py' for p in self.tmp.rglob('escape.py')))
        first = self.store.verifications(pid)[0]
        self.assertEqual(first['verdict'], 'FAIL')                 # model said PASS; the gate refused
        self.assertIn('refused files', first['checks']['output'])
        self.assertEqual(self.store.verifications(pid)[-1]['verdict'], 'PASS')

    def test_missing_entry_fails(self):
        eng = self.engine(BundleScript([GOOD_FILES[:2], GOOD_FILES], ['PASS', 'PASS']))
        pid = self.store.new_project('make a calc package')
        eng.run(pid)
        self.assertIn('entry file run_tests.py is missing', self.store.verifications(pid)[0]['checks']['output'])


if __name__ == '__main__':
    unittest.main()
