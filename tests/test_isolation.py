"""Phase A: OS-enforced isolation of generated programs (real AppContainer backend + adapter tests).
Canaries are synthetic; no Owner file, credential or network endpoint is used."""
import os
import json
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
    return ('import os, socket, subprocess, sys, json\n'
            'def t(name, f):\n'
            '    try:\n'
            '        f(); print(name, "ALLOWED")\n'
            '    except Exception as e:\n'
            '        outcome = "DENIED" if isinstance(e, PermissionError) or getattr(e, "winerror", None) in (367, 1260) '
            'else "UNREACHABLE" if isinstance(e, TimeoutError) else "ERROR"\n'
            '        print(name, outcome, json.dumps({"type": type(e).__name__, '
            '"errno": getattr(e, "errno", None), "winerror": getattr(e, "winerror", None)}))\n' + code)


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
        # The exact synthetic canary and local endpoint work without isolation. A timeout
        # or missing fixture must not masquerade as evidence of OS policy enforcement.
        self.assertEqual(self.canary.read_text(encoding='utf-8'), 'SYNTHETIC-CANARY')
        control = socket.create_connection(srv.getsockname(), timeout=3)
        peer, _ = srv.accept()
        peer.close()
        control.close()
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
        for denied in ('outside_read', 'outside_write', 'profile_list', 'internet', 'child'):
            self.assertIn(f'{denied} DENIED', out)
            line = next(line for line in out.splitlines() if line.startswith(f'{denied} DENIED '))
            error = json.loads(line.split(' DENIED ', 1)[1])
            if denied == 'internet':
                self.assertEqual(error['winerror'], 10013, (denied, error, out))   # WSAEACCES, not timeout/offline
            elif denied == 'child':
                self.assertIn(error['winerror'], (5, 367, 1260), (denied, error, out))
            else:
                self.assertEqual(error['type'], 'PermissionError', (denied, error, out))
        # Windows can silently drop isolated loopback packets rather than return WSAEACCES.
        # Record that as observed unreachability, NOT an explicit OS access-denied error.
        loopback = next(line for line in out.splitlines() if line.startswith('loopback '))
        self.assertTrue(loopback.startswith(('loopback DENIED ', 'loopback UNREACHABLE ')), loopback)
        loop_error = json.loads(loopback.split(' ', 2)[2])
        if ' DENIED ' in loopback:
            self.assertEqual(loop_error['winerror'], 10013, loop_error)
        else:
            self.assertEqual(loop_error['type'], 'TimeoutError', loop_error)
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

    def test_owner_result_launch_is_isolated_and_exports_safe_outputs(self):
        from axbranch import artifacts
        store = Store(self.tmp / 'owner-ws' / 'axbranch.sqlite3')
        try:
            eng = E.Engine(store, workspace=self.tmp / 'owner-ws', vault=self.tmp / 'v', gai_db=self.tmp / 'x')
            pid = store.new_project('synthetic protected Owner launch')
            entry = self.tmp / 'fixture.py'
            entry.write_text('import os\n'
                             f'try:\n    open(r"{self.canary}").read()\n    print("LEAK")\n'
                             'except PermissionError:\n    print("OUTSIDE_DENIED")\n'
                             'print("TOKEN_VISIBLE", "AXB_TEST_FAKE_TOKEN" in os.environ)\n'
                             'open("answer.txt", "w").write("allowed output")\n', encoding='utf-8')
            aid = store.add_artifact(pid, 1, entry, artifacts.sha(entry.read_bytes()), 'python', None)
            store.add_verification(pid, aid, 1, 'PASS', {}, {'ok': True}, 'codex')
            store.update(pid, plan={'artifact_filename': 'fixture.py', 'runtime': {'mode': 'cli'}})
            shown = []
            os.environ['AXB_TEST_FAKE_TOKEN'] = 'SYNTHETIC-CREDENTIAL'
            try:
                how, path = eng.open_result(pid, show_text=lambda title, text, path: shown.append(text))
            finally:
                os.environ.pop('AXB_TEST_FAKE_TOKEN', None)
            self.assertEqual(how, 'run')
            self.assertIn('OUTSIDE_DENIED', shown[0])
            self.assertIn('TOKEN_VISIBLE False', shown[0])
            self.assertNotIn('LEAK', shown[0])
            self.assertEqual((path.parent / 'answer.txt').read_text(), 'allowed output')
            event = store.events(pid, {'owner_run'})[-1]['detail']
            self.assertEqual(event['isolation']['backend'], 'appcontainer')
            self.assertEqual(event['exit_code'], 0)
            self.assertIn('answer.txt', [f['path'] for f in event['output_files']])
        finally:
            store.close()


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
