"""A result whose verified behaviour depends on its kept training outputs runs isolated with them (real AppContainer,
the already installed pinned training stack; nothing is trained or downloaded here)."""
import hashlib
import shutil
import tempfile
import unittest
from pathlib import Path

from axbranch import engine as E, isolation, training
from axbranch.state import Store

READY = isolation.available()[0] and training.env_python()[1].is_file() and \
    (training.env_python()[0] / 'AXB_INSTALLED').is_file()
APP = ("import torch\n"
       "label = open('outputs/model.txt', encoding='utf-8').read().strip()\n"
       "print('label', label, 'torch', torch.__version__, float(torch.ones(2).sum()))\n")


@unittest.skipUnless(READY, 'needs OS isolation and the installed pinned training stack (training-env)')
class TrainedRunTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='axb-trained-'))
        self.ws = self.tmp / 'ws'
        self.store = Store(self.ws / 'axbranch.sqlite3')

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_isolated_owner_run_gets_the_training_outputs_and_the_stack(self):
        pid = self.store.new_project('trained classifier (synthetic outputs, no training here)')
        self.store.update(pid, plan={'artifact_filename': 'app.py', 'artifact_kind': 'python', 'acceptance_criteria': ['x'],
                                     'runtime': {'mode': 'cli', 'owner_launch': 'python app.py', 'launch_args': [], 'probes': []},
                                     'pipeline': []})
        folder = self.ws / 'projects' / pid / 'artifacts' / 'v1'
        folder.mkdir(parents=True)
        (folder / 'app.py').write_text(APP, encoding='utf-8')
        aid = self.store.add_artifact(pid, 1, folder / 'app.py', hashlib.sha256((folder / 'app.py').read_bytes()).hexdigest(), 'python', None)
        out = self.ws / 'projects' / pid / 'training' / 'k'
        out.mkdir(parents=True)
        (out / 'model.txt').write_text('positive', encoding='utf-8')
        self.store.event(pid, 'training_run', artifact=aid, ok=True, dir=str(out), files=[{'path': 'model.txt'}])
        self.store.add_verification(pid, aid, 1, 'PASS', {'verdict': 'PASS', 'findings': []}, {'ok': True}, 'codex')
        eng = E.Engine(Store(self.ws / 'axbranch.sqlite3'), workspace=self.ws, vault=self.tmp / 'v', gai_db=self.tmp / 'x', llm=None)
        shown = {}
        try:
            how, _ = eng.open_result(pid, show_text=lambda title, text, p: shown.update(text=text))
        finally:
            eng.store.close()
        self.assertEqual(how, 'run')
        self.assertIn('label positive torch 2.', shown['text'])
        self.assertIn('AppContainer', shown['text'])
        used = [e['detail'] for e in self.store.events(pid, {'trained_output_used'})]
        self.assertEqual([u['use'] for u in used], ['owner_run'])


if __name__ == '__main__':
    unittest.main()
