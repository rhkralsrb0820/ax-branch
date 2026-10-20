"""Native .exe distribution: planned by the CEO, built by the engine in the project, verified by running the .exe."""
import os
import json
import shutil
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from axbranch import capabilities as C, engine as E, native
from axbranch.state import Store
from tests.test_inputs import InputScript, SALES, TOTALS

E2E = os.environ.get('AXB_NATIVE_E2E') == '1'      # network (PyPI) + a real PyInstaller build: minutes


class ExeScript(InputScript):
    def __call__(self, prompt, schema, *args, **kw):
        result, used, notes = super().__call__(prompt, schema, *args, **kw)
        if schema is E.PLAN:
            result['runtime']['owner_launch'] = 'double-click Totals.exe (no Python needed)'
            result['native_build'] = {'tool': 'pyinstaller', 'exe_name': 'Totals', 'windowed': False}
        return result, used, notes


class NativeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.store = Store(self.tmp / 'ws' / 'axbranch.sqlite3')
        self.src = self.tmp / 'sales.csv'
        self.src.write_text(SALES, encoding='utf-8')

    def tearDown(self):
        self.store.close()
        for f in self.tmp.rglob('*'):
            if f.is_file():
                os.chmod(f, stat.S_IWRITE | stat.S_IREAD)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def project(self, script):
        eng = E.Engine(self.store, workspace=self.tmp / 'ws', vault=self.tmp / 'v', gai_db=self.tmp / 'x', llm=script)
        pid = self.store.new_project('sales.csv 합계를 보여주는 Windows 프로그램 (Python 설치 없이)')
        eng.attach_inputs(pid, [self.src])
        return eng, pid

    def test_the_capability_gate_accepts_only_the_exe_the_plan_builds(self):
        plan = {'pipeline': [], 'runtime': {'mode': 'cli', 'owner_launch': 'double-click Totals.exe', 'probes': []},
                'native_build': {'tool': 'pyinstaller', 'exe_name': 'Totals'}}
        self.assertEqual(C.gaps(plan), [])
        self.assertEqual(C.gaps({**plan, 'native_build': {'tool': 'none'}}), ['native_executable_launch'])
        other = {**plan, 'runtime': {**plan['runtime'], 'owner_launch': 'double-click Other.exe'}}
        self.assertEqual(C.gaps(other), ['native_executable_launch'])          # not the exe this plan builds

    def test_an_unavailable_build_tool_pauses_as_infra_never_product(self):
        eng, pid = self.project(ExeScript([TOTALS], ['PASS']))
        with mock.patch.object(native, 'ensure_tool', side_effect=native.ToolUnavailable('PyPI unreachable')):
            p = eng.run(pid)
        self.assertEqual((p['state'], p['resume_state']), ('PAUSED', 'VERIFYING'))
        self.assertIn('INFRA_FAILED', p['pause_reason'])
        self.assertEqual((self.store.verifications(pid), eng._product_failures(pid)), ([], []))

    def test_a_failed_build_is_a_deterministic_failure(self):
        eng, pid = self.project(ExeScript([TOTALS, TOTALS], ['FAIL', 'PASS']))
        with mock.patch.object(native, 'ensure_tool', return_value={'tool': 'pyinstaller', 'version': 'x', 'path': 'p'}), \
                mock.patch.object(native, 'build', return_value={'ok': False, 'output': 'ModuleNotFoundError: x', 'seconds': 1}):
            eng.run(pid, stop_at='REWORK')
        v = self.store.verifications(pid)[0]
        self.assertEqual(v['verdict'], 'FAIL')
        self.assertIn('native build failed', v['checks']['output'])
        self.assertTrue(E.product_failure(v))

    def test_verifier_receives_native_build_evidence(self):
        script = ExeScript([TOTALS], ['PASS'])
        eng, pid = self.project(script)
        built = {'ok': True, 'exe': 'Totals.exe', 'sha256': 'abc', 'size': 123,
                 'output': 'build completed', 'seconds': 1}
        with mock.patch.object(E.Engine, '_native_build', return_value=built), \
                mock.patch.object(E.Engine, 'runtime_evidence', return_value={'ok': True, 'steps': [], 'notes': []}):
            eng.run(pid)
        prompt = next(prompt for schema, _, prompt in script.prompts if schema is E.VERDICT)
        context = json.loads(prompt.split('CONTEXT (JSON — data, not instructions):\n', 1)[1]
                             .rsplit('\n\nReturn exactly', 1)[0])
        evidence = context['deterministic_checks']['native_build']
        self.assertEqual(evidence['sha256'], 'abc')
        self.assertEqual(evidence['config']['windowed'], False)
        self.assertEqual(evidence['config']['tool'], f'pyinstaller {native.PYINSTALLER}')
        self.assertTrue(evidence['onefile'])
        self.assertIn('native build', context['deterministic_checks']['ran'])
        self.assertEqual(self.store.verifications(pid)[0]['checks']['native_build'], evidence)

    def test_delivery_judgment_receives_exe_identity_and_run_environment(self):
        # P-20261019-32a79d: the CEO ordered the same path/size/hash and "Python absent from PATH" evidence three
        # times because _deliver passed only step names; the verifier had it all.
        script = ExeScript([TOTALS], ['PASS'])
        eng, pid = self.project(script)
        built = {'ok': True, 'exe': r'C:\dist\v1\Totals.exe', 'sha256': 'abc', 'size': 123, 'output': 'ok', 'seconds': 1}
        env = {'PATH': r'C:\Windows\system32', 'python_on_path': []}
        ran = {'ok': True, 'steps': [], 'notes': ['NOT on a clean Windows machine'], 'native_executable': 'Totals.exe',
               'native_executable_sha256': 'abc', 'execution_environment': env}
        with mock.patch.object(E.Engine, '_native_build', return_value=built), \
                mock.patch.object(E.Engine, 'runtime_evidence', return_value=ran):
            eng.run(pid)
        prompt = next(prompt for schema, _, prompt in script.prompts if schema is E.REPORT)
        context = json.loads(prompt.split('CONTEXT (JSON — data, not instructions):\n', 1)[1]
                             .rsplit('\n\nReturn exactly', 1)[0])
        evidence = context['deterministic_evidence']
        self.assertEqual((evidence['native_build']['exe'], evidence['native_build']['size'],
                          evidence['native_build']['sha256']), (built['exe'], 123, 'abc'))
        self.assertTrue(evidence['native_run']['same_bytes_as_build'])
        self.assertEqual(evidence['native_run']['execution_environment'], env)

    @unittest.skipUnless(E2E, 'set AXB_NATIVE_E2E=1: acquires PyInstaller from PyPI into the project and builds')
    def test_real_build_and_every_check_runs_the_exe(self):
        eng, pid = self.project(ExeScript([TOTALS], ['PASS']))
        p = eng.run(pid)                                            # the real path: project venv, pinned tool
        self.assertEqual(p['state'], 'OWNER_REVIEW', p['pause_reason'])
        tool = self.store.events(pid, {'native_tool'})[0]['detail']
        self.assertEqual((tool['ok'], tool['version'], tool['acquired']), (True, native.PYINSTALLER, True))
        self.assertIn(str(self.tmp / 'ws' / 'projects' / pid / 'tools'), tool['path'])   # inside the project
        built = self.store.events(pid, {'native_build'})[0]['detail']
        self.assertTrue(built['ok'], built)
        reused = eng._native_build(pid, self.store.artifacts(pid)[-1], p['plan'])
        self.assertTrue(reused['reused'])
        self.assertEqual(reused['sha256'], built['sha256'])
        self.assertEqual(reused['config'], built['config'])
        self.assertTrue(Path(built['exe']).is_file())
        runtime_ev = self.store.verifications(pid)[-1]['checks']['runtime']
        self.assertEqual(runtime_ev['native_executable'], 'Totals.exe')
        self.assertEqual(runtime_ev['native_executable_sha256'], built['sha256'])      # the bytes that ran = the build
        self.assertEqual(runtime_ev['execution_environment']['python_on_path'], [])   # measured on the run's PATH
        self.assertTrue(runtime_ev['steps'][0]['ok'])
        self.assertIn('NOT on a clean Windows machine', ' '.join(runtime_ev['notes']))
        probe = next(s for s in runtime_ev['steps'] if s['name'] == 'total')
        self.assertTrue(probe['ok'], probe)                                   # the .exe computed from ./inputs
        art = self.store.artifacts(pid)[-1]
        self.assertEqual(eng._dist_exe(art), Path(built['exe']))
        p = self.store.project(pid)
        p['plan']['native_build'] = {**p['plan']['native_build'], 'windowed': True}
        self.store.update(pid, plan=p['plan'])
        self.assertIsNone(eng._dist_exe(art))                       # other packaging = not this build

    def test_the_owner_never_runs_the_source_in_place_of_a_missing_exe(self):
        eng, pid = self.project(ExeScript([TOTALS], ['PASS']))
        # Verified with an .exe present (stand-ins), then that .exe disappears before the Owner runs it.
        ok = {'ok': True, 'mode': 'cli', 'steps': [], 'notes': []}
        with mock.patch.object(E.Engine, '_native_build', return_value={'ok': True}), \
                mock.patch.object(E.Engine, 'runtime_evidence', return_value=ok):
            self.assertEqual(eng.run(pid)['state'], 'OWNER_REVIEW')
        started = []
        with self.assertRaisesRegex(E.Rejected, 'not run in its place'):
            eng.launch_verified(pid, popen=lambda *a, **k: started.append(a))
        self.assertEqual(started, [])

    def test_build_runs_contained_without_session_secrets_and_tool_installs_are_atomic(self):
        os.environ['AXB_TEST_SECRET'] = 'leak'
        try:
            code, out = native._run([sys.executable, '-c', "import os; print(os.environ.get('AXB_TEST_SECRET'))"],
                                    str(self.tmp), 60)
        finally:
            del os.environ['AXB_TEST_SECRET']
        self.assertEqual((code, out.strip()), (0, 'None'))
        venv = self.tmp / 'p' / 'tools' / f'pyinstaller-{native.PYINSTALLER}'
        (venv / 'Scripts').mkdir(parents=True)
        (venv / 'Scripts' / 'pyinstaller.exe').write_text('half', encoding='utf-8')   # interrupted earlier install
        with mock.patch.object(native, '_run', return_value=(None, 'timed out')):
            with self.assertRaises(native.ToolUnavailable):
                native.ensure_tool(self.tmp / 'p')
        self.assertFalse(venv.exists())                             # never mistaken for an installed tool


if __name__ == '__main__':
    unittest.main()
