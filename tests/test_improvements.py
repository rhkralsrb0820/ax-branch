"""Improvement candidates: evidence -> proposal -> prepared evaluation -> Owner-approved comparison -> apply -> rollback.
No model call: evaluation projects are created through the real start path and their outcomes are recorded directly."""
import shutil
import tempfile
import unittest
from pathlib import Path

from axbranch import engine as E, improvements as I
from axbranch.departments import catalog
from axbranch.state import Rejected, Store

FAIL = {'verdict': 'FAIL', 'findings': [], 'note': 'x'}
PASS = {'verdict': 'PASS', 'findings': [], 'note': 'x'}


class ImprovementTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='axb-imp-'))
        self.ws = self.tmp / 'ws'
        self.store = Store(self.ws / 'axbranch.sqlite3')

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def engine(self):
        return E.Engine(Store(self.ws / 'axbranch.sqlite3'), workspace=self.ws, vault=self.tmp / 'v', gai_db=self.tmp / 'x', llm=None)

    def verify(self, pid, verdict):
        aid = self.store.add_artifact(pid, 1, self.tmp / 'a.py', 'sha', 'python', None)
        ok = verdict == 'PASS'
        self.store.add_verification(pid, aid, 1, verdict, PASS if ok else FAIL, {'ok': ok, 'exit_code': 0 if ok else 1}, 'codex')
        return self.store.verifications(pid)[-1]

    def end(self, pid, state):                   # test shortcut for a run that stopped in this state
        self.store.db.execute('UPDATE projects SET state=? WHERE id=?', (state, pid))
        self.store.db.commit()

    def failing_project(self, resolved):
        pid = self.store.new_project('재고 웹앱')
        sig = E.failure_code(self.verify(pid, 'FAIL'))
        self.assertTrue(sig)
        self.store.event(pid, 'decision', what='strategy: replan', why='검증 전에 자체 시험을 먼저 통과시키도록 계획 변경', by='claude')
        self.store.event(pid, 'decision', what='repeated failure signature', why=sig, by='engine')
        if resolved:
            self.verify(pid, 'PASS')
        return pid, sig

    def test_candidate_lifecycle_needs_evidence_comparison_and_owner(self):
        pid, sig = self.failing_project(resolved=False)
        I.observe(self.store, pid)
        (c,) = I.all_(self.store)
        self.assertEqual((c['state'], c['signature'], c.get('proposal')), ('CANDIDATE', sig, None))
        with self.assertRaises(Rejected):
            I.prepare_eval(self.store, c['id'])                      # no resolution yet: nothing to compare
        self.verify(pid, 'PASS')
        I.observe(self.store, pid)
        I.observe(self.store, pid)                                   # idempotent
        c = I.get(self.store, c['id'])
        self.assertIn('자체 시험', c['proposal']['rule'])
        self.assertEqual(len(c['evidence']), 1)
        with self.assertRaises(Rejected):
            I.approve(self.store, c['id'])                           # never applied unverified
        c = I.prepare_eval(self.store, c['id'])
        self.assertEqual(c['state'], 'EVAL_READY')
        launched = []
        with self.assertRaises(Rejected):
            I.start_eval(self.store, self.engine, catalog()[0], c['id'], launched.append)   # Owner approval required
        c = I.start_eval(self.store, self.engine, catalog()[0], c['id'], launched.append, approved=True)
        self.assertEqual((c['state'], len(launched)), ('EVALUATING', 2))
        arms = {p['arm']: p['project'] for p in c['eval']['projects']}
        for p in launched:
            self.assertFalse(self.store.events(p, {'experience_policy'})[-1]['detail']['enabled'])
        self.assertEqual([r['id'] for r in I.for_project(self.store, arms['variant'])], [c['id']])
        self.assertEqual(I.for_project(self.store, arms['baseline']), [])
        # Outcomes: the baseline repeats the failure, the variant passes.
        self.verify(arms['baseline'], 'FAIL')
        self.end(arms['baseline'], 'PAUSED')
        I.observe(self.store, arms['baseline'])
        self.assertEqual(I.get(self.store, c['id'])['state'], 'EVALUATING')   # the variant is still active
        self.verify(arms['variant'], 'PASS')
        self.end(arms['variant'], 'OWNER_REVIEW')
        I.observe(self.store, arms['variant'])
        c = I.get(self.store, c['id'])
        self.assertEqual(c['state'], 'COMPARED')
        self.assertTrue(c['comparison']['better'])
        self.assertEqual(len(I.all_(self.store)), 1)                 # evaluation projects registered nothing new
        c = I.approve(self.store, c['id'])
        other = self.store.new_project('다른 업무')
        self.assertEqual([r['id'] for r in I.for_project(self.store, other)], [c['id']])
        eng = self.engine()
        try:
            ctx = eng._improvements(other, 'planning')
        finally:
            eng.store.close()
        self.assertEqual(ctx['applied_improvements']['rules'][0]['id'], c['id'])
        self.assertEqual(self.store.events(other, {'improvements_used'})[-1]['detail']['ids'], [c['id']])
        I.rollback(self.store, c['id'])
        self.assertEqual(I.for_project(self.store, other), [])
        self.assertEqual([h['to'] for h in I.get(self.store, c['id'])['history']][-3:], ['COMPARED', 'APPLIED', 'ROLLED_BACK'])

    def test_a_worse_variant_cannot_be_applied(self):
        pid, _ = self.failing_project(resolved=True)
        I.observe(self.store, pid)
        cid = I.all_(self.store)[0]['id']
        I.prepare_eval(self.store, cid)
        c = I.start_eval(self.store, self.engine, catalog()[0], cid, lambda p: None, approved=True)
        arms = {p['arm']: p['project'] for p in c['eval']['projects']}
        self.verify(arms['baseline'], 'PASS'); self.end(arms['baseline'], 'OWNER_REVIEW')
        self.verify(arms['variant'], 'FAIL'); self.end(arms['variant'], 'PAUSED')
        I.observe(self.store, arms['variant'])
        self.assertFalse(I.get(self.store, cid)['comparison']['not_worse'])
        with self.assertRaises(Rejected):
            I.approve(self.store, cid)
        self.assertEqual(I.reject(self.store, cid, 'worse')['state'], 'REJECTED')

    def test_web_routes(self):
        from axbranch import web
        pid, _ = self.failing_project(resolved=True)
        I.observe(self.store, pid)
        app = web.App(self.ws, 0, engine_factory=self.engine, launcher=lambda *a: None)
        got = web.route(app, self.store, 'GET', '/api/improvements', {}, {})
        cid = got['candidates'][0]['id']
        self.assertEqual(web.route(app, self.store, 'POST', f'/api/improvement/{cid}/prepare', {}, {})['state'], 'EVAL_READY')
        with self.assertRaises(Rejected):          # the page must send an explicit approval
            web.route(app, self.store, 'POST', f'/api/improvement/{cid}/evaluate', {}, {'approve': 'yes'})
        self.assertIn('improvements', app.project(self.store, pid))
        c = I.start_eval(self.store, self.engine, catalog()[0], cid, lambda p: None, approved=True)
        evals = {p['project'] for p in c['eval']['projects']}
        ov = app.overview(self.store)
        self.assertFalse(evals & {r['id'] for r in ov['projects']})          # not in the work list
        self.assertEqual(ov['evaluation_projects'], 2)
        self.assertIn(pid, {r['id'] for r in ov['projects']})
        listed = web.route(app, self.store, 'GET', '/api/improvements', {}, {})['candidates'][0]['eval']['projects']
        self.assertEqual({p['project'] for p in listed}, evals)            # found from the candidate instead
        self.assertTrue(all(p['state'] == 'CREATED' for p in listed))
        self.assertEqual(app.project(self.store, listed[0]['project'])['improvements']['evaluation']['candidate'], cid)

    def test_learning_paths_report_real_state(self):
        paths = {p['id']: p for p in I.learning_paths(self.store)}
        self.assertEqual(paths['finetune']['status'], '미지원')
        self.assertEqual(paths['rules']['status'], '적용된 규칙 없음')


if __name__ == '__main__':
    unittest.main()
