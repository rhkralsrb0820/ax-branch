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

    def test_native_two_process_profile_cannot_start_a_third_process(self):
        child = ('import subprocess,sys\n'
                 'try:\n p=subprocess.Popen([sys.executable,"-c","print(123)"]); p.wait(); print("THIRD_ALLOWED")\n'
                 'except OSError as e:\n print("THIRD_BLOCKED",getattr(e,"winerror",None))\n')
        rc, out, _ = self.run_isolated(
            f'p=subprocess.run([sys.executable,"-c",{child!r}],capture_output=True,text=True)\n'
            'print(p.stdout); print(p.stderr); print("CHILD_EXIT",p.returncode)\n',
            child_processes=True, max_processes=2)
        self.assertEqual(rc, 0, out)
        self.assertIn('CHILD_EXIT 0', out)
        self.assertIn('THIRD_BLOCKED', out)
        self.assertNotIn('THIRD_ALLOWED', out)

    def test_native_bootloader_profile_keeps_outside_file_and_network_denials(self):
        rc, out, _ = self.run_isolated(
            f't("outside",lambda:open(r"{self.canary}").read())\n'
            't("network",lambda:socket.create_connection(("1.1.1.1",443),timeout=3))\n'
            'open("inside.txt","w").write("allowed")\nprint("INSIDE_OK")\n',
            child_processes=True, max_processes=2, allow_custom_acl=True)
        self.assertEqual(rc, 0, out)
        self.assertIn('INSIDE_OK', out)
        for name in ('outside', 'network'):
            line = next(line for line in out.splitlines() if line.startswith(name + ' '))
            self.assertIn(' DENIED ', line)
            error = json.loads(line.split(' DENIED ', 1)[1])
            self.assertEqual(error['type'], 'PermissionError', line)

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

    def test_runtime_cli_mode_is_isolated(self):
        app = self.work / 'app.py'
        app.write_text(f'import sys\ntry:\n    open(r"{self.canary}").read(); print("LEAK")\n'
                       'except PermissionError:\n    print("denied")\n', encoding='utf-8')
        ev = runtime.check({'mode': 'cli', 'probes': []}, 'app.py', sys.executable, str(self.work), isolate=True)
        self.assertNotIn('LEAK', str(ev))
        self.assertTrue(ev['isolation'] and all(m['backend'] == 'appcontainer' for m in ev['isolation']))

    SERVER = """
import http.server, json, socket, subprocess, sys
def attempt(f):
    try:
        f(); return "ALLOWED"
    except Exception as e:
        return "DENIED " + type(e).__name__
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/probe":
            body = json.dumps({{"owner_file": attempt(lambda: open(r"{canary}").read()),
                "host_service": attempt(lambda: socket.create_connection(("127.0.0.1", {hport}), timeout=3)),
                "internet": attempt(lambda: socket.create_connection(("1.1.1.1", 443), timeout=3)),
                "child": attempt(lambda: subprocess.run(["cmd", "/c", "echo x"], capture_output=True))}}).encode()
        else:
            body = b"<html><body><h1>Inventory</h1><p>3 items</p></body></html>"
        self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers()
        self.wfile.write(body)
    def log_message(self, *a): pass
port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else {default}
print(f"Serving at http://127.0.0.1:{{port}}/", flush=True)
http.server.HTTPServer(("127.0.0.1", port), H).serve_forever()
"""

    def test_generated_web_server_is_verified_inside_its_container_through_the_run_channel(self):
        host = socket.socket()
        host.bind(('127.0.0.1', 0))
        host.listen(5)
        host.settimeout(15)
        hits = []

        def accept():
            try:
                hits.append(host.accept())
            except OSError:
                pass
        threading.Thread(target=accept, daemon=True).start()
        default = 18900 + os.getpid() % 90
        (self.work / 'app.py').write_text(self.SERVER.format(canary=self.canary, hport=host.getsockname()[1],
                                                             default=default), encoding='utf-8')
        spec = {'mode': 'web', 'owner_launch': f'python app.py, then open http://127.0.0.1:{default}/',
                'launch_args': ['--port', '{port}'],
                'probes': [{'name': 'page', 'http_method': 'GET', 'http_path': '/', 'expect_status': 200,
                            'expect_contains': ['3 items']},
                           {'name': 'containment', 'http_method': 'GET', 'http_path': '/probe', 'expect_status': 200,
                            'expect_contains': ['"owner_file": "DENIED', '"host_service": "DENIED',
                                                '"internet": "DENIED', '"child": "DENIED']},
                           {'name': 'rendered', 'http_method': 'BROWSER', 'http_path': '/', 'expect_contains': ['3 items']}]}
        try:
            ev = runtime.check(spec, 'app.py', sys.executable, str(self.work), isolate=True)
        finally:
            host.close()
        self.assertTrue(ev['ok'], [(s['name'], s.get('problems')) for s in ev['steps']])
        self.assertEqual(hits, [])                                         # the host service was never reached
        runs = ev['isolation']
        self.assertTrue(runs and all(m['backend'] == 'appcontainer' and m['serve'] for m in runs))
        # Cleanup: the bridge processes are gone, the run pipes no longer exist, the run profiles are deleted.
        time.sleep(1)
        ps = subprocess.run(['powershell', '-NoProfile', '-Command',
                             "(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*axb_bridge.py*' }).Count"],
                            capture_output=True).stdout.decode(errors='replace').strip()
        self.assertIn(ps, ('', '0'))
        import winreg
        for m in runs:
            with self.assertRaises(OSError):
                open(rf'\\.\pipe\axb-{m["run_id"]}-ctl', 'rb')
            with self.assertRaises(OSError):
                winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Software\\Classes\\Local Settings\\Software\\Microsoft'
                               '\\Windows\\CurrentVersion\\AppContainer\\Mappings\\' + m['package_sid'])

    def test_a_run_channel_pipe_refuses_any_other_run(self):
        other_sid = I._sid_string(I._package_sid('AXBranch.Run.channel-owner-test'))
        name = rf'\\.\pipe\axb-cross-{os.getpid()}'
        handle, _ = I._pipe(name, other_sid, 3)                             # a pipe that belongs to ANOTHER run
        try:
            rc, out, _ = self.run_isolated(f't("foreign_pipe", lambda: open(r"{name}", "r+b", buffering=0))\n')
        finally:
            I._k32.CloseHandle(handle)
        self.assertIn('foreign_pipe DENIED', out)

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
