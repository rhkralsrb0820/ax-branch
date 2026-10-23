"""Model training harness: train.py runs once per version in the training stack, its outputs are kept and reused,
runtime checks load them, and a failed run is a deterministic failure."""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from axbranch import capabilities as C, engine as E, training
from axbranch.state import Store
from tests.test_bundle import BundleScript

TRAIN = ("import json, pathlib\nout = pathlib.Path('outputs'); out.mkdir()\n"
         "(out / 'model.json').write_text(json.dumps({'weights': [0.5, 1.5]}))\n"
         "(out / 'metrics.json').write_text(json.dumps({'dev_accuracy': 0.8, 'split': 'dev'}))\n")
EVAL = ("import json, pathlib, sys\nif '--self-test' in sys.argv:\n    print('self-test ok'); raise SystemExit(0)\n"
        "model = json.loads(pathlib.Path('outputs/model.json').read_text())\nprint('eval ok', sum(model['weights']))\n")
FILES = [{'path': 'train.py', 'content': TRAIN}, {'path': 'evaluate.py', 'content': EVAL}]
PROBE = {'name': 'evaluate', 'args': [], 'stdin': '', 'http_method': '', 'http_path': '', 'http_body': '',
         'http_headers': [], 'expect_exit': 0, 'expect_status': 0, 'expect_contains': ['eval ok 2.0'], 'expect_absent': []}


class TrainingScript(BundleScript):
    def __call__(self, prompt, schema, prefer='claude', web=False, cancel=None, **kw):
        result, used, notes = super().__call__(prompt, schema, prefer, web, cancel, **kw)
        if schema is E.PLAN:
            result.update(artifact_filename='evaluate.py',
                          runtime={'mode': 'cli', 'owner_launch': 'python evaluate.py', 'launch_args': [], 'probes': [PROBE]})
            result['pipeline'][-1]['capabilities'] = ['model_training']
        return result, used, notes


class TrainingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.store = Store(self.tmp / 'ws' / 'axbranch.sqlite3')
        # The stack is stood in by this interpreter; the run itself is real and contained.
        works = (('local_cpu_lora', lambda d: {'ok': True, 'evidence': {'adapter_changed': True}}),)
        self.patches = [mock.patch.object(C, 'options', lambda n, training=None: works if n in C.TRAINING_NAMES else ()),
                        mock.patch.object(training, 'ensure_env', lambda d: {'python': sys.executable}),
                        mock.patch.object(training, 'env_python', lambda d=None: (self.tmp, Path(sys.executable)))]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.store.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_project(self, files, stop_at=None):
        eng = E.Engine(self.store, workspace=self.tmp / 'ws', vault=self.tmp / 'v', gai_db=self.tmp / 'x', llm=TrainingScript([files] * 2, ['PASS'] * 2))
        pid = self.store.new_project('train a tiny model and evaluate it')
        return eng, pid, eng.run(pid, stop_at=stop_at)

    def test_training_runs_once_and_runtime_checks_load_its_outputs(self):
        eng, pid, p = self.run_project(FILES)
        self.assertEqual(p['state'], 'OWNER_REVIEW', p['pause_reason'])
        v = self.store.verifications(pid)[-1]
        job = v['checks']['training']
        self.assertTrue(job['ok'])
        self.assertEqual(job['metrics'], {'dev_accuracy': 0.8, 'split': 'dev'})
        self.assertEqual(sorted(f['path'] for f in job['files']), ['metrics.json', 'model.json'])   # marker excluded
        self.assertTrue(all(len(f['sha256']) == 64 for f in job['files']))
        self.assertTrue(v['checks']['runtime']['steps'][-1]['ok'], v['checks']['runtime']['steps'])  # loaded ./outputs
        grants = [e for e in self.store.events(pid, {'capability_attached'}) if e['detail']['who'] == 'Model training']
        self.assertEqual(len(grants), 1)
        # Resume / re-verification of the same version: the finished training is reused, not repeated.
        again = eng._training_run(pid, self.store.artifacts(pid)[-1])
        self.assertTrue(again['reused'])
        self.assertEqual(again['key'], job['key'])
        self.assertEqual(len([e for e in self.store.events(pid, {'capability_attached'})
                              if e['detail']['who'] == 'Model training']), 1)

    def test_owner_run_uses_the_verified_outputs_and_stack(self):
        # Demo v8: verified with the training stack and ./outputs, but 결과 실행 used the plain interpreter.
        eng, pid, p = self.run_project(FILES)
        self.assertEqual(p['state'], 'OWNER_REVIEW', p['pause_reason'])
        started = []
        path, _ = eng.launch_verified(pid, popen=lambda cmd, **kw: started.append((cmd, kw)))
        cmd, kw = started[0]
        self.assertIn(str(training.env_python()[1]), cmd)
        self.assertTrue((Path(kw['cwd']) / 'outputs' / 'model.json').is_file())

    def test_failed_training_is_a_deterministic_failure_and_is_not_kept_as_done(self):
        broken = [{'path': 'train.py', 'content': 'raise SystemExit(3)\n'}, FILES[1]]
        eng, pid, p = self.run_project(broken, stop_at='REWORK')
        v = self.store.verifications(pid)[-1]
        self.assertEqual(v['verdict'], 'FAIL')
        self.assertIn('MODEL TRAINING FAILED: train.py exited 3', v['checks']['output'])
        self.assertFalse(list((self.tmp / 'ws' / 'projects' / pid).rglob('AXB_DONE.json')))

    def test_missing_train_script_is_not_a_success(self):
        eng, pid, p = self.run_project([FILES[1]], stop_at='REWORK')
        v = self.store.verifications(pid)[-1]
        self.assertEqual(v['verdict'], 'FAIL')
        self.assertIn('no train.py', v['checks']['output'])


if __name__ == '__main__':
    unittest.main()
