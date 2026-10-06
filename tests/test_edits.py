"""Edit-based builds: localized changes applied byte-exactly to the latest real version."""
import shutil
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from axbranch import artifacts, engine as E
from axbranch.state import Store
from tests.test_engine import LAUNCHABLE, Script


class EditScript(Script):
    """Second build returns edits instead of a whole file."""
    def __init__(self, edit_batches):
        super().__init__([LAUNCHABLE], ['PASS', 'PASS', 'PASS'])
        self.edit_batches = list(edit_batches)

    def __call__(self, prompt, schema, prefer='claude', web=False, cancel=None, **kw):
        if schema is E.BUILD_EDITS:                    # edits-only schema: no content/files fields at all
            self.prompts.append((schema, prefer, prompt))
            return {'edits': self.edit_batches.pop(0), 'summary': 's', 'changes_from_previous': ''}, prefer, []
        if schema is E.BUILD and not self.builds:
            self.prompts.append((schema, prefer, prompt))
            return {'content': '', 'files': [], 'edits': self.edit_batches.pop(0), 'summary': 's',
                    'changes_from_previous': ''}, prefer, []
        return super().__call__(prompt, schema, prefer, web, cancel, **kw)


class EditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.store = Store(self.tmp / 'ws' / 'axbranch.sqlite3')

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_with(self, *batches):
        script = EditScript(batches)
        eng = E.Engine(self.store, workspace=self.tmp / 'ws', vault=self.tmp / 'v', gai_db=self.tmp / 'x', llm=script)
        pid = self.store.new_project('make an add tool')
        eng.run(pid)
        eng.owner_review(pid, works=True, text='print an explanation after the result')
        return eng.run(pid), pid, script

    def test_edits_produce_the_new_version(self):
        edit = {'path': 'add_tool.py', 'find': "        print('result:', add(2, 3))\n",
                'replace': "        print('result:', add(2, 3))\n        print('explained: 2 + 3')\n"}
        p, pid, _ = self.run_with([edit])
        self.assertEqual(p['state'], 'OWNER_REVIEW')
        new = Path(self.store.artifacts(pid)[-1]['path']).read_text(encoding='utf-8')
        self.assertEqual(new, LAUNCHABLE.replace("        print('result:', add(2, 3))\n",
                                                 "        print('result:', add(2, 3))\n        print('explained: 2 + 3')\n"))
        self.assertEqual(len(self.store.events(pid, {'edits_applied'})), 1)

    def test_large_previous_version_gets_an_edits_only_build(self):
        edit = {'path': 'add_tool.py', 'find': "        print('result:', add(2, 3))\n",
                'replace': "        print('result:', add(2, 3))\n        print('explained: 2 + 3')\n"}
        with mock.patch.object(E, 'EDITS_ONLY_ABOVE', 10):             # LAUNCHABLE counts as "large"
            p, pid, script = self.run_with([edit])
        self.assertEqual(p['state'], 'OWNER_REVIEW')
        builds = [(s, pr) for s, _, pr in script.prompts if s in (E.BUILD, E.BUILD_EDITS)]
        self.assertIs(builds[0][0], E.BUILD)                           # first version: whole file
        self.assertIs(builds[1][0], E.BUILD_EDITS)                     # then: edits only, by schema
        self.assertIn('return ONLY edits', builds[1][1])
        self.assertIn("print('explained: 2 + 3')", Path(self.store.artifacts(pid)[-1]['path']).read_text(encoding='utf-8'))

    def test_ambiguous_or_missing_find_is_rejected_then_retried(self):
        bad = {'path': 'add_tool.py', 'find': 'add(2, 3)', 'replace': 'add(3, 3)'}       # occurs twice
        good = {'path': 'add_tool.py', 'find': "print('result:', add(2, 3))", 'replace': "print('result:', add(2, 3), 'ok')"}
        p, pid, script = self.run_with([bad], [good])
        self.assertEqual(p['state'], 'OWNER_REVIEW')
        rejected = self.store.events(pid, {'build_rejected'})
        self.assertEqual(len(rejected), 1)
        self.assertIn('occurs 2 times', rejected[0]['detail']['reason'])
        retry = [pr for s, _, pr in script.prompts if s is E.BUILD][-1]
        self.assertIn('occurs 2 times', retry)                       # the producer is told exactly why

    def test_apply_edits_unit(self):
        art = {'path': str(self.tmp / 'a.py'), 'sha256': '', 'iteration': 1}
        Path(art['path']).write_bytes(b'x = 1\ny = 2\n')              # exact bytes (no CRLF translation)
        files, err = artifacts.apply_edits(art, [{'path': 'a.py', 'find': 'y = 2', 'replace': 'y = 3'}])
        self.assertEqual((files['a.py'], err), ('x = 1\ny = 3\n', None))
        self.assertIn('0 times', artifacts.apply_edits(art, [{'path': 'a.py', 'find': 'z', 'replace': ''}])[1])


if __name__ == '__main__':
    unittest.main()
