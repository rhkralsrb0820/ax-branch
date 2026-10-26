"""Phase A: OS-enforced isolation of generated programs (real AppContainer backend + adapter tests).
Canaries are synthetic; no Owner file, credential or network endpoint is used."""
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from axbranch import engine as E, isolation as I, runtime, sandbox
from axbranch.state import Store

REAL = os.name == 'nt' and I.available()[0]


def probe(code):
    return ('import os, socket, subprocess, sys\n'
            'def t(name, f):\n'
            '    try:\n'
            '        f(); print(name, "ALLOWED")\n'
            '    except Exception as e:\n'
            '        print(name, "DENIED", type(e).__name__)\n' + code)


@unittest.skipUnless(REAL, 'AppContainer backend not available on this machine')
class RealBackendTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='axb-iso-test-'))
        self.outside = self.tmp / 'outside'
        self.outside.mkdir()
        self.canary = self.outside / 'canary.txt'
        self.canary.write_text('SYNTHETIC-CANARY', encoding='utf-8')
        self.work = self.tmp / 'work'
        self.work.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_isolated(self, code, **manifest):
        (self.work / 'p.py').write_text(probe(code), encoding='utf-8')
        m = I.Manifest(purpose='test', **manifest)
        rc, out = sandbox.run([sys.executable, '-I', 'p.py'], self.work, 60, isolate=m)
        return rc, out, m

    def test_os_denies_outside_files_network_children_and_credentials(self):
        srv = socket.socket()
        srv.bind(('127.0.0.1', 0))
        srv.listen(1)
        srv.settimeout(8)
        accepted = []
        def accept():
            try:
                accepted.append(srv.accept())
            except OSError:                      # timed out or closed: nothing connected
                pass
        threading.Thread(target=accept, daemon=True).start()
        os.environ['AXB_TEST_FAKE_TOKEN'] = 'SYNTHETIC-CREDENTIAL'
        try:
            rc, out, m = self.run_isolated(
                f't("own_write", lambda: open("own.txt", "w").write("x"))\n'
                f't("outside_read", lambda: open(r"{self.canary}").read())\n'
                f't("outside_write", lambda: open(r"{self.outside / "evil.txt"}", "w").write("x"))\n'
                f't("profile_list", lambda: os.listdir(r"{Path.home()}"))\n'
                f't("loopback", lambda: socket.create_connection(("127.0.0.1", {srv.getsockname()[1]}), timeout=3))\n'
                f't("internet", lambda: socket.create_connection(("1.1.1.1", 443), timeout=3))\n'
                f't("child", lambda: subprocess.run(["cmd", "/c", "echo x"], capture_output=True))\n'
                'print("token_visible", "AXB_TEST_FAKE_TOKEN" in os.environ)\n')
        finally:
            os.environ.pop('AXB_TEST_FAKE_TOKEN', None)
            srv.close()
        self.assertEqual(rc, 0, out)
        self.assertIn('own_write ALLOWED', out)
        for denied in ('outside_read', 'outside_write', 'profile_list', 'loopback', 'internet', 'child'):
            self.assertIn(f'{denied} DENIED', out)
        self.assertIn('token_visible False', out)
        self.assertFalse((self.outside / 'evil.txt').exists())
        self.assertEqual(accepted, [])
        self.assertTrue(m.package_sid.startswith('S-1-15-2-'))

    def test_a_previous_run_grant_is_useless_to_the_next_run(self):
        first = self.tmp / 'first-run'
        first.mkdir()
        (first / 'left.txt').write_text('from run 1', encoding='utf-8')
        I.grant(first, I._sid_string(I._package_sid('AXBranch.Run.stale-test')), write=True)   # a run's leftover grant
        rc, out, _ = self.run_isolated(f't("stale_read", lambda: open(r"{first / "left.txt"}").read())\n')
        self.assertIn('stale_read DENIED', out)

    def test_descendants_are_killed_with_the_run(self):
        marker = self.work / 'child.pid'
        rc, out, _ = self.run_isolated(
            'p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])\n'
            f'open(r"{marker}", "w").write(str(p.pid))\n', child_processes=True)
        self.assertEqual(rc, 0, out)
        pid = int(marker.read_text())
        time.sleep(0.5)
        alive = subprocess.run(['tasklist', '/FI', f'PID eq {pid}', '/NH'], capture_output=True).stdout.decode(errors='replace')
        self.assertNotIn(str(pid), alive)

    def test_verification_self_test_runs_inside_the_boundary(self):
        store = Store(self.tmp / 'ws' / 'axbranch.sqlite3')
        eng = E.Engine(store, workspace=self.tmp / 'ws', vault=self.tmp / 'v', gai_db=self.tmp / 'x', llm=None)
        prog = self.tmp / 'art' / 'app.py'
        prog.parent.mkdir()
        prog.write_text('import sys\nif __name__ == "__main__":\n'
                        f'    open(r"{self.canary}").read()\n    print("read the canary")\n', encoding='utf-8')
        isolated = eng.checks(prog, 'python')
        self.assertFalse(isolated['ok'])
        self.assertIn('PermissionError', isolated['output'])
        self.assertEqual(isolated['isolation']['backend'], 'appcontainer')
        exception = eng.checks(prog, 'python', isolate=False)        # only under a recorded Owner exception
        self.assertTrue(exception['ok'], exception)
        self.assertEqual(exception['isolation'], {'backend': 'job_object_only', 'owner_exception': True})
        store.close()

    def test_runtime_cli_mode_is_isolated_and_server_mode_is_blocked(self):
        app = self.work / 'app.py'
        app.write_text(f'import sys\ntry:\n    open(r"{self.canary}").read(); print("LEAK")\n'
                       'except PermissionError:\n    print("denied")\n', encoding='utf-8')
        ev = runtime.check({'mode': 'cli', 'probes': []}, 'app.py', sys.executable, str(self.work), isolate=True)
        self.assertNotIn('LEAK', str(ev))
        self.assertTrue(ev['isolation'] and all(m['backend'] == 'appcontainer' for m in ev['isolation']))
        server = runtime.check({'mode': 'server', 'launch_args': ['--port', '{port}'], 'probes': []}, 'app.py',
                               sys.executable, str(self.work), isolate=True)
        self.assertFalse(server['ok'])
        self.assertIn('loopback', server['isolation_blocked'])
        self.assertEqual(server['steps'], [])                     # nothing was launched


class AdapterTests(unittest.TestCase):
    def test_no_silent_fallback_when_the_backend_fails(self):
        tmp = Path(tempfile.mkdtemp(prefix='axb-iso-adapter-'))
        original = I.launch
        I.launch = lambda *a, **k: (_ for _ in ()).throw(I.IsolationUnavailable('simulated backend failure'))
        try:
            (tmp / 'p.py').write_text('open("ran.txt", "w").write("x")', encoding='utf-8')
            with self.assertRaises(I.IsolationUnavailable):
                sandbox.run([sys.executable, 'p.py'], tmp, 30, isolate=I.Manifest(purpose='t'))
            self.assertFalse((tmp / 'ran.txt').exists())
        finally:
            I.launch = original
            shutil.rmtree(tmp, ignore_errors=True)

    def test_grants_only_inside_run_folders_and_foreign_interpreters_refused(self):
        with self.assertRaises(I.IsolationUnavailable):
            I.check_grants(I.Manifest(purpose='t', reads=[str(Path.home())]))
        with self.assertRaises(I.IsolationUnavailable):
            I.check_grants(I.Manifest(purpose='t', writes=[tempfile.gettempdir()]))
        with self.assertRaises(I.IsolationUnavailable):
            I.isolated_args([r'C:\some\venv\Scripts\python.exe', 'x.py'])
        with self.assertRaises(I.IsolationUnavailable):
            I.launch(['x'], '.', {}, None, None, None, I.Manifest(purpose='t', network='internet'))

    def test_engine_pauses_with_an_actionable_reason_and_honours_a_recorded_exception(self):
        tmp = Path(tempfile.mkdtemp(prefix='axb-iso-engine-'))
        store = Store(tmp / 'ws' / 'axbranch.sqlite3')
        try:
            eng = E.Engine(store, workspace=tmp / 'ws', vault=tmp / 'v', gai_db=tmp / 'x', llm=None)
            pid = store.new_project('isolation test')
            self.assertTrue(eng._isolate(pid))
            eng._isolation_blocked(pid, 'simulated backend failure')
            p = store.project(pid)
            self.assertEqual(p['state'], 'PAUSED')
            self.assertIn('--allow-unisolated', p['pause_reason'])
            store.event(pid, 'isolation_exception', allow=True, reason='Owner accepts job-only checks', by='owner-cli')
            self.assertFalse(eng._isolate(pid))
        finally:
            store.close()
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()
