"""A small Owner revision re-runs only affected stages: unchanged, explicitly unaffected and provenance-intact analysis is
reused; anything else is re-run, and every decision is recorded."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from axbranch import departments as D, engine as E
from axbranch.state import Store
from tests.test_departments import DepartmentScript
from tests.test_engine import GOOD

REVISED = GOOD + '\n# Owner asked for a heading change only\n'


class RevisionScript(DepartmentScript):
    def __init__(self, reuse):
        super().__init__()
        self.builds, self.verdicts = [GOOD, REVISED], ['PASS', 'PASS', 'PASS']
        self.reuse = reuse

    def __call__(self, prompt, schema, *args, **kw):
        if schema is E.DIAGNOSIS:
            self.contexts.append((schema, None))
            first = next(c for s, c in self.contexts if s is E.PLAN)
            return {'diagnosis': 'presentation change only', 'root_cause': 'Owner wording request',
                    'change_summary': 'change the heading', 'interpretation': 'Build an add() helper',
                    'artifact_kind': 'python', 'artifact_filename': '../evil/add tool.py',
                    'acceptance_criteria': ['add(2,3)==5'], 'verification_lenses': ['software engineering'],
                    'runtime': {'mode': 'cli', 'owner_launch': 'double-click', 'launch_args': [], 'probes': []},
                    'network_access': [], 'pipeline': [dict(s) for s in self.pipeline], 'removed_criteria': [],
                    'reuse_stages': self.reuse, 'evidence_class': 'PRODUCT_CHANGE'}, 'claude', []
        return super().__call__(prompt, schema, *args, **kw)


class RevisionReuseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='axb-reuse-'))
        self.store = Store(self.tmp / 'ws' / 'axbranch.sqlite3')

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def revise(self, reuse, tamper=False):
        script = RevisionScript(reuse)
        pid = self.store.new_project('팀별 문의 우선순위 도구')
        for d in ('research', 'operations'):
            D.attach(self.store, pid, d, D.catalog()[0])
        eng = E.Engine(self.store, workspace=self.tmp / 'ws', vault=self.tmp / 'v', gai_db=self.tmp / 'x', llm=script)
        self.assertEqual(eng.run(pid)['state'], 'OWNER_REVIEW')
        if tamper:                                     # the recorded analysis bytes changed after they were produced
            self.store.db.execute("UPDATE stage_outputs SET output=? WHERE project_id=? AND stage=0",
                                  (json.dumps({'output': 'edited later', 'key_points': ['x'], 'evidence': ['row 1'],
                                               'counterpoints': ['y']}), pid))
            self.store.db.commit()
        eng.owner_review(pid, text='Change the heading wording only; keep the analysis.')
        eng.run(pid)
        works = sum(1 for s, _ in script.contexts if s is E.WORK)
        return pid, works

    def test_unaffected_analysis_is_reused_on_a_presentation_revision(self):
        pid, works = self.revise([{'name': 'analyse', 'reason': 'heading wording does not change the numbers'}])
        self.assertEqual(works, 1)                                            # research ran once, not twice
        reused = [e['detail'] for e in self.store.events(pid, {'stage_reused'}) if e['detail'].get('owner_revision')]
        self.assertEqual([r['stage'] for r in reused], ['analyse'])
        self.assertIn('heading wording', reused[0]['decision_reason'])
        self.assertTrue(reused[0]['output_sha256'])

    def test_without_an_explicit_unaffected_decision_the_stage_reruns(self):
        pid, works = self.revise([])
        self.assertEqual(works, 2)
        why = [e['detail']['why'] for e in self.store.events(pid, {'stage_discarded'})]
        self.assertTrue(any('without an explicit unaffected-stage decision' in w for w in why), why)

    def test_changed_recorded_bytes_are_never_reused(self):
        pid, works = self.revise([{'name': 'analyse', 'reason': 'unaffected'}], tamper=True)
        self.assertEqual(works, 2)
        why = [e['detail']['why'] for e in self.store.events(pid, {'stage_discarded'})]
        self.assertTrue(any('result bytes changed' in w for w in why), why)


if __name__ == '__main__':
    unittest.main()
