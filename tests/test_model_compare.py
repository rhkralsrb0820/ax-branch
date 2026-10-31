"""Before/after-training comparison on the FIXED test predictor (tests/fixtures/compare_classifier; developer fixture,
not a trained model): real isolated runs, evaluator-held answers, contract checks. Results here are function checks."""
import csv
import hashlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from axbranch import engine as E, isolation, model_compare as M, training
from axbranch.state import Rejected, Store, run_lock

READY = isolation.available()[0] and training.env_python()[1].is_file() and \
    (training.env_python()[0] / 'AXB_INSTALLED').is_file()
FIXTURE = Path(__file__).parent / 'fixtures' / 'compare_classifier' / 'predict.py'
EVAL = [('my card has not arrived', 'card_arrival'), ('where is my new card', 'card_arrival'),
        ('top up failed again', 'top_up_failed'), ('my top up did not work', 'top_up_failed'),
        ('please refund my payment', 'refund'), ('i want a refund', 'refund')]
TRAIN = [('card still not delivered', 'card_arrival'), ('cannot top up', 'top_up_failed'), ('refund request', 'refund')]
WEAK = {'rules': {'card': 'card_arrival'}, 'default': 'refund'}
STRONG = {'rules': {'card': 'card_arrival', 'top up': 'top_up_failed', 'refund': 'refund'}, 'default': 'refund'}


def csv_text(rows):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator='\n')
    w.writerow(['text', 'category'])
    w.writerows(rows)
    return buf.getvalue()


@unittest.skipUnless(READY, 'needs OS isolation and the installed pinned training stack (training-env)')
class CompareTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='axb-compare-test-'))
        self.ws = self.tmp / 'ws'
        self.store = Store(self.ws / 'axbranch.sqlite3')

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def engine(self):
        return E.Engine(Store(self.ws / 'axbranch.sqlite3'), workspace=self.ws, vault=self.tmp / 'v', gai_db=self.tmp / 'x', llm=None)

    def project(self, baseline, trained, train=TRAIN, fixture_flag=None):
        pid = self.store.new_project('문의 분류 (고정 시험 예측기, 학습 아님)')
        self.store.update(pid, plan={'artifact_filename': 'predict.py', 'artifact_kind': 'python', 'acceptance_criteria': ['x'],
                                     'runtime': {'mode': 'cli', 'owner_launch': 'python predict.py', 'launch_args': [], 'probes': []},
                                     'pipeline': []})
        folder = self.ws / 'projects' / pid / 'artifacts' / 'v1'
        folder.mkdir(parents=True)
        shutil.copyfile(FIXTURE, folder / 'predict.py')
        aid = self.store.add_artifact(pid, 1, folder / 'predict.py', hashlib.sha256((folder / 'predict.py').read_bytes()).hexdigest(), 'python', None)
        out = self.ws / 'projects' / pid / 'training' / 'k'
        (out / 'data').mkdir(parents=True)
        (out / 'data' / 'test.csv').write_text(csv_text(EVAL), encoding='utf-8')
        if train is not None:
            (out / 'data' / 'train.csv').write_text(csv_text(train), encoding='utf-8')
        (out / 'baseline.json').write_text(json.dumps(baseline), encoding='utf-8')
        (out / 'trained.json').write_text(json.dumps(trained), encoding='utf-8')
        if fixture_flag is not None:
            (out / 'fixture_flag.json').write_text(json.dumps(fixture_flag), encoding='utf-8')
        self.store.event(pid, 'training_run', artifact=aid, ok=True, dir=str(out), files=[])
        self.store.add_verification(pid, aid, 1, 'PASS', {'verdict': 'PASS', 'findings': []}, {'ok': True}, 'fixture')
        self.out = out
        return pid

    def compare(self, pid, **kw):
        eng = self.engine()
        try:
            prepared = M.prepare(eng, pid)
            return prepared, M.run(eng, pid, prepared['cid'], approved=True, **kw)
        finally:
            eng.store.close()

    def test_better_same_worse_with_evaluator_held_answers(self):
        for base, tr, verdict in ((WEAK, STRONG, 'trained_better'), (STRONG, dict(STRONG), 'same'), (STRONG, WEAK, 'trained_worse')):
            prepared, v = self.compare(self.project(base, tr))
            r = v['result']
            self.assertEqual((r['status'], r['verdict']), ('complete', verdict))
            self.assertEqual(r['effect'], 'function_check_only')                 # fixture: never a real effect
            self.assertEqual(r['trained']['samples'], 6)
        spec = prepared['spec']
        self.assertEqual(set(spec['arms']), {'baseline', 'trained'})
        self.assertTrue(spec['arms']['trained']['files']['outputs/trained.json'])
        folder = self.ws / 'projects' / spec['project'] / 'comparisons' / spec['cid']
        self.assertNotIn('label', (folder / 'inputs.jsonl').read_text(encoding='utf-8'))   # predictor input has no answers
        self.assertEqual(spec['leakage'], {'checked': True, 'overlap': 0, 'eval_internal_duplicates': 0,
                                           'note': spec['leakage']['note']})

    def test_a_failed_or_malformed_arm_leaves_the_comparison_incomplete(self):
        for mode, problem in (('crash', '종료 코드 3'), ('missing', '누락 2건'), ('duplicate', '중복 1건'), ('badformat', '잘못된 형식 1건')):
            _, v = self.compare(self.project(WEAK, {**STRONG, 'mode': mode}))
            self.assertEqual(v['result']['status'], 'incomplete', mode)
            self.assertIn(problem, v['result']['problems'][0], mode)
            self.assertNotIn('verdict', v['result'])

    def test_inputs_or_model_changed_after_preparation_is_invalid(self):
        for change in ('model', 'eval'):
            pid = self.project(WEAK, STRONG)
            eng = self.engine()
            try:
                prepared = M.prepare(eng, pid)
                if change == 'model':
                    (self.out / 'trained.json').write_text(json.dumps(WEAK), encoding='utf-8')
                else:
                    folder = self.ws / 'projects' / pid / 'comparisons' / prepared['cid']
                    (folder / 'answers.jsonl').write_text('{}\n', encoding='utf-8')
                v = M.run(eng, pid, prepared['cid'], approved=True)
            finally:
                eng.store.close()
            self.assertEqual(v['result']['status'], 'invalid', change)
            self.assertFalse([e for e in self.store.events(pid, {'comparison_arm'})])   # nothing ran

    def test_overlap_or_unknown_training_data_blocks_an_effect_claim(self):
        leaky = TRAIN + [EVAL[0]]
        _, v = self.compare(self.project(WEAK, STRONG, train=leaky, fixture_flag=False))
        self.assertEqual(v['spec']['leakage']['overlap'], 1)
        self.assertEqual((v['result']['verdict'], v['result']['effect']), ('trained_better', 'not_verified'))
        _, v = self.compare(self.project(WEAK, STRONG, train=None, fixture_flag=False))
        self.assertFalse(v['spec']['leakage']['checked'])
        self.assertEqual(v['result']['effect'], 'not_verified')
        _, v = self.compare(self.project(WEAK, STRONG, fixture_flag=False))       # clean, complete, better
        self.assertEqual(v['result']['effect'], 'confirmed_in_this_evaluation')
        self.assertIn('일반적인 품질 향상을 뜻하지 않습니다', v['result']['note'])

    def test_needs_approval_resumes_after_interruption_and_never_runs_twice(self):
        pid = self.project(WEAK, STRONG)
        eng = self.engine()
        try:
            prepared = M.prepare(eng, pid)
            cid = prepared['cid']
            with self.assertRaises(Rejected):
                M.run(eng, pid, cid)                                                  # Owner approval required
            real, calls = M._run, []

            def interrupted(engine, artifact, trained, args, timeout, input_file=None):
                calls.append(args[1])
                if args[1] == 'trained':
                    raise KeyboardInterrupt                                           # the process dies mid-comparison
                return real(engine, artifact, trained, args, timeout, input_file)
            with mock.patch.object(M, '_run', interrupted), self.assertRaises(KeyboardInterrupt):
                M.run(eng, pid, cid, approved=True)
            self.assertTrue(M.view(eng, pid, cid)['resumable'])
            folder = self.ws / 'projects' / pid / 'comparisons' / cid
            with run_lock(folder / 'run.lock'), self.assertRaisesRegex(Rejected, '이미 실행 중'):
                M.run(eng, pid, cid, approved=True)                                   # another run holds it
            counted = []
            with mock.patch.object(M, '_run', lambda *a, **k: counted.append(a[3][1]) or real(*a, **k)):
                v = M.run(eng, pid, cid, approved=True)
            self.assertEqual(counted, ['trained'])                                    # the finished arm is not rerun
            self.assertEqual(v['result']['status'], 'complete')
            self.assertEqual(M.run(eng, pid, cid, approved=True)['result'], v['result'])   # no second result
        finally:
            eng.store.close()

    def test_web_prepare_approved_run_and_status(self):
        import time
        from axbranch import web
        pid = self.project(WEAK, STRONG)
        app = web.App(self.ws, 0, engine_factory=self.engine, launcher=lambda *a: None)
        prepared = web.project_action(app, self.store, pid, 'compare-prepare', {}, 'web')
        cid = prepared['cid']
        with self.assertRaises(Rejected):
            web.project_action(app, self.store, pid, 'compare-run', {'cid': cid}, 'web')     # explicit approval
        web.project_action(app, self.store, pid, 'compare-run', {'cid': cid, 'approve': True}, 'web')
        for _ in range(240):
            if not app.comparing:
                break
            time.sleep(0.5)
        got = web.route(app, self.store, 'GET', '/api/improvements', {}, {})
        (c,) = got['comparisons']
        self.assertEqual((c['state'], c['result']['verdict']), ('비교 완료', 'trained_better'))
        run = next(t for t in got['training'] if t['project'] == pid)
        self.assertTrue(run['effect'].startswith('기능 확인만'))
        self.assertTrue(run['applied_to_later_work'].startswith('연결된 기능 없음'))

    def test_unsupported_results_say_what_is_missing(self):
        pid = self.project(WEAK, STRONG)
        (self.out / 'data' / 'test.csv').write_text('question,answer\nx,y\n', encoding='utf-8')
        eng = self.engine()
        try:
            with self.assertRaisesRegex(Rejected, 'text 열과 label 또는 category'):
                M.prepare(eng, pid)
        finally:
            eng.store.close()


class ScoringTests(unittest.TestCase):
    def test_scores_and_prediction_checks_are_computed_here(self):
        answers = {'a': 'x', 'b': 'y', 'c': 'y'}
        self.assertEqual(M.score(answers, {'a': 'x', 'b': 'y', 'c': 'x'}),
                         {'accuracy': 0.6667, 'macro_f1': 0.6667, 'errors': 1, 'samples': 3})
        got, problems = M.check_predictions('{"id":"a","label":"x"}\n{"id":"a","label":"x"}\n{"id":"z","label":"x"}\nbad\n', ['a', 'b'])
        self.assertEqual(got, {'a': 'x'})
        self.assertEqual(problems, ['예측 누락 1건', '예측 중복 1건', '예측 알 수 없는 ID 1건', '예측 잘못된 형식 1건'])


if __name__ == '__main__':
    unittest.main()
