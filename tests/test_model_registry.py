"""Reusable trained models on the FIXED test predictor (developer fixture, not a trained model): register -> runnable ->
approve -> connect -> 淸月 plans a model use -> isolated run before production -> recorded -> detach / previous model.
Real AppContainer runs; no model call (the CEO and producer are scripted)."""
import csv
import io
import json
import shutil
import unittest
from pathlib import Path

from axbranch import engine as E, model_registry as R
from axbranch.departments import catalog
from axbranch.state import Rejected, Store
from tests import test_engine as TE
from tests import test_model_compare as MC

READY, STRONG, WEAK = MC.READY, MC.STRONG, MC.WEAK


def inquiries(rows):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator='\n')
    w.writerow(['text', 'customer'])
    w.writerows(rows)
    return buf.getvalue()


@unittest.skipUnless(READY, 'needs OS isolation and the installed pinned training stack (training-env)')
class RegistryTests(unittest.TestCase):
    setUp, tearDown, engine, project = MC.CompareTests.setUp, MC.CompareTests.tearDown, MC.CompareTests.engine, MC.CompareTests.project

    def registered(self, rules=STRONG):
        source = self.project(WEAK, rules)
        eng = self.engine()
        try:
            m = R.register(eng, source)
        finally:
            eng.store.close()
        return source, m

    def follow_up(self, rows=(('my card has not arrived', 'a'), ('please refund me', 'b'))):
        pid = self.store.new_project('후속 업무: 문의 분류 결과로 팀별 건수 집계')
        f = self.tmp / 'inquiries.csv'
        f.write_text(inquiries(rows), encoding='utf-8')
        eng = self.engine()
        try:
            eng.attach_inputs(pid, [str(f)])
        finally:
            eng.store.close()
        return pid

    def use(self, pid, mid, name='inquiries.csv'):
        eng = self.engine()
        try:
            return R.use(eng, pid, mid, name, plan_version=1)
        finally:
            eng.store.close()

    def test_register_keeps_states_apart_and_copies_only_model_files(self):
        source, m = self.registered()
        self.assertEqual((m['runnable'], m['approved']), (None, None))           # registration is not approval
        self.assertFalse(R.evaluation(self.store, m)['done'])
        self.assertEqual(set(m['files']), {'predict.py', 'outputs/trained.json'})
        pkg = R.package_dir(self.ws, m['id'])
        self.assertFalse((pkg / 'outputs' / 'data').exists())                    # no training / evaluation data copied
        self.assertEqual((m['source']['project'], m['source']['version'], m['task']), (source, 1, 'text classification'))
        with self.assertRaises(Rejected):
            R.approve(self.store, self.ws, m['id'])                               # not runnable yet
        eng = self.engine()
        try:
            m = R.check_runnable(eng, m['id'])
        finally:
            eng.store.close()
        self.assertTrue(m['runnable']['ok'], m['runnable'])
        m = R.approve(self.store, self.ws, m['id'])
        self.assertEqual(m['approved']['evaluation_at_approval'], '평가 전 — 학습 전후 비교 기록 없음')

    def approved(self, rules=STRONG):
        source, m = self.registered(rules)
        eng = self.engine()
        try:
            R.check_runnable(eng, m['id'])
        finally:
            eng.store.close()
        return source, R.approve(self.store, self.ws, m['id'])

    def test_use_in_later_work_runs_isolated_records_and_never_substitutes(self):
        source, m = self.approved()
        pid = self.follow_up()
        with self.assertRaisesRegex(Rejected, '연결되지 않은'):
            self.use(pid, m['id'])                                                # not connected to this project
        R.attach(self.store, pid, m['id'])
        rec = self.use(pid, m['id'])
        self.assertEqual((rec['status'], rec['rows'], rec['via']), ('ok', 2, 'project'))
        out = Path(rec['output']).read_text(encoding='utf-8').splitlines()
        self.assertEqual(out, ['text,label', 'my card has not arrived,card_arrival', 'please refund me,refund'])
        R.revoke(self.store, m['id'])
        with self.assertRaisesRegex(Rejected, '사용 승인되지 않은'):
            self.use(pid, m['id'])
        R.approve(self.store, self.ws, m['id'])
        (R.package_dir(self.ws, m['id']) / 'outputs' / 'trained.json').write_text(json.dumps(WEAK), encoding='utf-8')
        with self.assertRaisesRegex(Rejected, '등록 후 바뀜'):
            self.use(pid, m['id'])                                                # changed model file is blocked
        statuses = [e['detail']['status'] for e in self.store.events(pid, {'model_use'})]
        self.assertEqual(statuses, ['failed', 'ok', 'failed', 'failed'])          # every attempt recorded
        self.assertTrue(Path(rec['output']).is_file())                            # earlier result preserved

    def test_input_contract_and_source_isolation(self):
        source, m = self.approved()
        pid = self.store.new_project('wrong input')
        f = self.tmp / 'notes.csv'
        f.write_text('question\nhi\n', encoding='utf-8')
        eng = self.engine()
        try:
            eng.attach_inputs(pid, [str(f)])
        finally:
            eng.store.close()
        R.attach(self.store, pid, m['id'])
        with self.assertRaisesRegex(Rejected, 'text 열이 필요'):
            self.use(pid, m['id'], 'notes.csv')
        with self.assertRaisesRegex(Rejected, '입력 파일이 아니거나'):
            self.use(pid, m['id'], 'test.csv')                                    # the source project's data is not reachable

    def test_department_link_and_restoring_the_previous_selection(self):
        _, first = self.approved()
        _, second = self.approved(rules={**STRONG, 'default': 'card_arrival'})
        pid = self.follow_up()
        R.attach(self.store, pid, second['id'])
        old = self.use(pid, second['id'])
        R.detach(self.store, pid, second['id'])
        R.attach(self.store, pid, first['id'])                                   # back to the earlier model
        self.assertEqual([m['id'] for m, _ in R.available(self.store, pid)], [first['id']])
        self.assertTrue(Path(old['output']).is_file())
        R.detach(self.store, pid, first['id'])
        from axbranch import departments
        departments.attach(self.store, pid, 'research', catalog()[0])
        R.link_department(self.store, first['id'], 'research', catalog()[0])
        (m, via), = R.available(self.store, pid)
        self.assertEqual((m['id'], via), (first['id'], 'department:research'))
        view = {v['id']: v for v in R.view(self.store, self.ws)}
        self.assertEqual(view[second['id']]['used_ok'], 1)
        self.assertEqual([c['what'] for c in view[second['id']]['connections']], ['model_attached', 'model_detached'])

    def test_cheongwol_plans_the_use_and_production_receives_the_predictions(self):
        source, m = self.approved()
        pid = self.follow_up()
        R.attach(self.store, pid, m['id'])
        mid = m['id']

        class UsesModel(TE.Script):
            def __call__(self, prompt, schema, *args, **kw):
                result, used, notes = super().__call__(prompt, schema, *args, **kw)
                if schema is E.PLAN:
                    result['model_uses'] = [{'model': mid, 'input': 'inquiries.csv', 'why': 'classify the inquiries'}]
                return result, used, notes
        script = UsesModel([TE.GOOD], ['PASS'])
        eng = E.Engine(Store(self.ws / 'axbranch.sqlite3'), workspace=self.ws, vault=self.tmp / 'v', gai_db=self.tmp / 'x', llm=script)
        try:
            p = eng.run(pid)
        finally:
            eng.store.close()
        self.assertEqual(p['state'], 'OWNER_REVIEW', p.get('pause_reason'))
        plan_prompt = next(pr for s, _, pr in script.prompts if s is E.PLAN)
        self.assertIn('available_models', plan_prompt)                           # 淸月 saw the model and its scope
        build = next(pr for s, _, pr in script.prompts if s is E.BUILD)
        self.assertIn(f'./model_outputs/{mid}/inquiries.csv.predictions.csv', build)
        (use,) = [e['detail'] for e in self.store.events(pid, {'model_use'})]
        self.assertEqual(use['status'], 'ok')
        from axbranch import improvements
        run = next(t for t in improvements.training_runs(self.store) if t['project'] == source)
        self.assertTrue(run['applied_to_later_work'].startswith('후속 업무에서 사용됨 1회'), run['applied_to_later_work'])

    def test_a_planned_use_of_an_unapproved_model_stops_without_substitution(self):
        source, m = self.registered()
        pid = self.follow_up()
        R.attach(self.store, pid, m['id'])
        mid = m['id']

        class UsesModel(TE.Script):
            def __call__(self, prompt, schema, *args, **kw):
                result, used, notes = super().__call__(prompt, schema, *args, **kw)
                if schema is E.PLAN:
                    result['model_uses'] = [{'model': mid, 'input': 'inquiries.csv', 'why': 'x'}]
                return result, used, notes
        eng = E.Engine(Store(self.ws / 'axbranch.sqlite3'), workspace=self.ws, vault=self.tmp / 'v', gai_db=self.tmp / 'x',
                       llm=UsesModel([TE.GOOD], ['PASS']))
        try:
            p = eng.run(pid)
        finally:
            eng.store.close()
        self.assertEqual(p['state'], 'PAUSED')
        self.assertIn('다른 모델로 대체하지 않았습니다', p['pause_reason'])
        self.assertFalse(self.store.artifacts(pid))                               # nothing was built without it


if __name__ == '__main__':
    unittest.main()
