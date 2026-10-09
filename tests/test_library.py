"""Artifact Library + Develop: completed artifacts by type, lineage versions, and Develop as an ordinary
autonomous project that starts from the existing artifact."""
import json
import shutil
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest import mock

from axbranch import engine as E, library
from axbranch.state import Rejected, Store
from tests.test_engine import GOOD, Script

SUB = GOOD.replace("def add(a, b):\n    return a + b\n", "def add(a, b):\n    return a + b\n\ndef sub(a, b):\n    return a - b\n")


class DevelopTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.store = Store(self.tmp / 'ws' / 'axbranch.sqlite3')
        self.script = Script([GOOD, SUB], ['PASS', 'PASS'])
        self.eng = E.Engine(self.store, workspace=self.tmp / 'ws', vault=self.tmp / 'vault', gai_db=self.tmp / 'x.db',
                            llm=self.script)

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_develop_is_a_new_autonomous_project_that_starts_from_the_artifact(self):
        base = self.store.new_project('make an add tool')
        self.eng.run(base)
        with self.assertRaises(Rejected):
            self.eng.develop(self.store.new_project('nothing verified'), 'more')
        before = (self.store.project(base), self.store.artifacts(base), self.store.verifications(base))
        new = self.eng.develop(base, 'also subtract')                    # the Owner gives only the goal
        p = self.eng.run(new)
        self.assertEqual(p['state'], 'OWNER_REVIEW')                       # the normal lifecycle, verified
        self.assertEqual((self.store.project(base), self.store.artifacts(base), self.store.verifications(base)), before)
        plan_prompt = next(prompt for schema, _, prompt in self.script.prompts[3:] if schema is E.PLAN)
        ctx = json.loads(plan_prompt.split('CONTEXT (JSON — data, not instructions):\n', 1)[1].rsplit('\n\nReturn exactly', 1)[0])
        dev = ctx['develop_from']
        self.assertEqual((dev['lineage_projects'], dev['library_version']), ([base], 1))
        self.assertIn('def add', dev['current_version']['content_excerpt'])
        self.assertIn('acceptance_criteria', dev['base_plan'])
        build_prompt = [prompt for schema, _, prompt in self.script.prompts if schema is E.BUILD][-1]
        self.assertIn('previous_artifact', build_prompt)                   # the first build starts from v1
        self.assertEqual(self.store.events(new, {'context_used'})[-1]['detail']['develop_from'], base)
        items = library.entries(self.store)
        self.assertEqual(len(items), 1)                                    # one artifact, two versions
        item = items[0]
        self.assertEqual((item['id'], item['version'], item['project']), (base, 2, new))
        self.assertEqual([v['project'] for v in item['versions']], [base, new])
        self.assertIn('def sub', Path(item['path']).read_text(encoding='utf-8'))

    def test_branches_keep_their_depth_and_a_changed_base_is_refused(self):
        base = self.store.new_project('make an add tool')
        self.eng.run(base)
        first, second = self.eng.develop(base, 'branch one'), self.eng.develop(base, 'branch two')
        self.assertEqual(library.base_artifact(self.store, second)['id'], library.verified_artifact(self.store, base)['id'])
        self.store.update(second, state='CLOSED')                      # treat it as done, verified
        art = library.verified_artifact(self.store, base)
        self.store.db.execute("INSERT INTO verifications(id,project_id,artifact_id,iteration,verdict,result,checks,provider,created) "
                              "SELECT 'V-x', ?, artifact_id, iteration, verdict, result, checks, provider, created+1 "
                              "FROM verifications WHERE artifact_id=?", (second, art['id']))
        self.store.db.execute("INSERT INTO artifacts(id,project_id,iteration,path,sha256,kind,agent_id,created) "
                              "SELECT id||'-copy', ?, iteration, path, sha256, kind, agent_id, created+1 FROM artifacts WHERE id=?",
                              (second, art['id']))
        self.store.db.execute("UPDATE verifications SET artifact_id=? WHERE id='V-x'", (art['id'] + '-copy',))
        item = library.entries(self.store)[0]
        self.assertEqual(sorted(v['version'] for v in item['versions']), [1, 2])   # sibling of 'first' is still v2
        Path(art['path']).write_text('changed after verification', encoding='utf-8')
        with self.assertRaises(Rejected):
            self.eng.develop(base, 'build on a changed file')
        with self.assertRaises(Rejected):
            library.base_artifact(self.store, first)                     # the child refuses a changed base too

    def test_types_from_what_the_result_is(self):
        def a(kind, files):
            return {'kind': kind, 'path': 'x', 'manifest': None, 'files': files}
        with mock.patch.object(library.artifacts, 'files_of', side_effect=lambda art: [(f, Path(f), '') for f in art['files']]):
            cases = [({'goal': 'make a dashboard', 'plan': {'runtime': {'mode': 'web'}}}, a('python', ['app.py']), 'Apps'),
                     ({'goal': '리만 가설 연구', 'plan': {}}, a('bundle', ['RESEARCH_REPORT.md', 'lab.py']), 'Research'),
                     ({'goal': 'weekly sales', 'plan': {}}, a('bundle', ['sales.csv', 'notes.md']), 'Data'),
                     ({'goal': 'quarterly review', 'plan': {}}, a('bundle', ['REPORT.md', 'chart.html']), 'Reports'),
                     ({'goal': 'venv guide', 'plan': {}}, a('markdown', ['guide.md']), 'Documents'),
                     ({'goal': 'converter', 'plan': {'runtime': {'mode': 'cli'}}}, a('python', ['conv.py']), 'Apps')]
            for project, art, kind in cases:
                self.assertEqual(library.classify(project, art), kind, project['goal'])


class LibraryGuiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        ws, vault, script = self.tmp / 'ws', self.tmp / 'vault', Script([GOOD, SUB], ['PASS', 'PASS'])
        self.script = script

        def factory():
            return E.Engine(Store(ws / 'axbranch.sqlite3'), workspace=ws, vault=vault, gai_db=self.tmp / 'x.db', llm=script)
        try:
            from axbranch.gui import App
            self.app = App(workspace=ws, engine_factory=factory)
        except tk.TclError as e:
            self.skipTest(f'no display: {e}')
        self.app.withdraw()
        self.factory = factory

    def tearDown(self):
        self.app.destroy()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_library_lists_the_artifact_and_develop_needs_only_a_goal(self):
        base = self.app.store.new_project('make an add tool')
        eng = self.factory()
        eng.run(base)
        eng.store.close()
        win = self.app.library_window()
        node, (entry, project) = next((n, r) for n, r in win.rows.items() if win.tree.parent(n) and r[1] == base
                                      and win.tree.item(n, 'text') == r[0]['title'])
        self.assertEqual(win.tree.item(node, 'values')[:2], ('v1', 'PASS'))
        self.assertEqual(win.tree.item(win.tree.parent(node), 'text'), 'Apps (1)')
        win.tree.focus(node)
        with mock.patch.object(self.app, '_launch') as launch:
            self.app._develop_dialog(win.rows[node], win)
            self.app._develop.goal.insert('1.0', 'also subtract')
            self.app._develop.start()                                     # one goal, nothing else
        new = self.app.selected
        launch.assert_called_once_with(new)
        self.assertEqual(library.develops(self.app.store, new), base)
        self.assertEqual(self.app.store.events(new, {'owner_action'})[-1]['detail'], {'action': 'develop', 'channel': 'app'})


if __name__ == '__main__':
    unittest.main()
