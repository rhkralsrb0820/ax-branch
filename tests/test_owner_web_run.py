"""Owner-opened web results (owner_runs): real AppContainer + server channel, synthetic canaries only."""
import hashlib
import json
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from axbranch import engine as E, isolation as I, owner_runs, web
from axbranch.state import Rejected, Store

REAL = os.name == 'nt' and I.available()[0]

APP = """
import http.server, json, socket, subprocess, sys, urllib.parse
def attempt(f):
    try:
        f(); return "ALLOWED"
    except Exception as e:
        return "DENIED " + type(e).__name__
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        url = urllib.parse.urlsplit(self.path)
        if url.path == "/probe":
            q = urllib.parse.parse_qs(url.query)
            body = json.dumps({{"read": attempt(lambda: open(q["path"][0]).read()),
                "host_service": attempt(lambda: socket.create_connection(("127.0.0.1", int(q["port"][0])), timeout=3)),
                "internet": attempt(lambda: socket.create_connection(("1.1.1.1", 443), timeout=3)),
                "child": attempt(lambda: subprocess.run(["cmd", "/c", "echo x"], capture_output=True))}}).encode()
        elif url.path == "/quit":
            body = b"bye"
        else:
            body = "<html><body><h1>재고 {name}</h1></body></html>".encode()
        self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers()
        self.wfile.write(body)
        if url.path == "/quit":
            import os; os._exit(0)
    def log_message(self, *a): pass
port = int(sys.argv[sys.argv.index("--port") + 1])
http.server.HTTPServer(("127.0.0.1", port), H).serve_forever()
"""


@unittest.skipUnless(REAL, 'AppContainer backend not available on this machine')
class OwnerWebRunTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='axb-owner-web-test-'))
        self.ws = self.tmp / 'ws'
        self.store = Store(self.ws / 'axbranch.sqlite3')
        self.canary = self.tmp / 'owner-secret.txt'
        self.canary.write_text('SYNTHETIC-OWNER-FILE', encoding='utf-8')
        self.app, self.httpd = web.serve(self.ws, 0, launcher=lambda *a: None, engine_factory=self.engine)
        self.app.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def tearDown(self):
        self.app.owner_runs.stop_all()
        self.httpd.shutdown()
        self.httpd.server_close()
        self.store.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def engine(self):
        return E.Engine(Store(self.ws / 'axbranch.sqlite3'), workspace=self.ws, vault=self.tmp / 'v',
                        gai_db=self.tmp / 'x', llm=None)

    def project(self, name='A', mode='web', args=('--port', '{port}')):
        pid = self.store.new_project(f'synthetic web result {name}')
        folder = self.ws / 'projects' / pid / 'artifacts' / 'v1'
        folder.mkdir(parents=True)
        path = folder / 'app.py'
        path.write_text(APP.format(name=name), encoding='utf-8')
        plan = {'artifact_filename': 'app.py', 'artifact_kind': 'python', 'acceptance_criteria': ['x'],
                'runtime': {'mode': mode, 'owner_launch': 'x', 'launch_args': list(args), 'probes': []}, 'pipeline': []}
        self.store.update(pid, plan=plan, iteration=1)
        aid = self.store.add_artifact(pid, 1, path, hashlib.sha256(path.read_bytes()).hexdigest(), 'python', None)
        self.store.add_verification(pid, aid, 1, 'PASS', {'verdict': 'PASS', 'findings': []}, {'ok': True}, 'codex')
        return pid

    def act(self, pid, action):
        return web.project_action(self.app, self.store, pid, action, {}, 'web')

    def test_open_use_isolate_and_stop(self):
        pid, other = self.project('A'), self.project('B')
        host = socket.socket()
        host.bind(('127.0.0.1', 0))
        host.listen(1)
        host.settimeout(10)
        hits = []
        def accept():
            try:
                hits.append(host.accept())
            except OSError:                       # closed or timed out: nothing connected
                pass
        threading.Thread(target=accept, daemon=True).start()
        r = self.act(pid, 'result')
        self.assertEqual(r['how'], 'web')
        self.assertIn('재고 A', urllib.request.urlopen(r['url'], timeout=10).read().decode('utf-8'))
        again = self.act(pid, 'result')                                    # no duplicate run
        self.assertEqual((again['url'], again['reused']), (r['url'], True))
        b = self.act(other, 'result')
        self.assertNotEqual(b['url'], r['url'])                             # one run per project
        other_dir = self.app.owner_runs.runs[other]['cwd'] / 'app.py'
        for target, label in ((self.canary, 'owner file'), (other_dir, 'other project run')):
            probe = json.loads(urllib.request.urlopen(
                f"{r['url']}probe?path={urllib.parse.quote(str(target))}&port={host.getsockname()[1]}", timeout=30).read())
            self.assertTrue(probe['read'].startswith('DENIED'), (label, probe))
            self.assertTrue(probe['host_service'].startswith('DENIED'), probe)
            self.assertTrue(probe['internet'].startswith('DENIED'), probe)
            self.assertTrue(probe['child'].startswith('DENIED'), probe)
        host.close()
        self.assertEqual(hits, [])
        # The result's origin cannot use AX Branch's API (no token; foreign Origin refused even with the token).
        origin = r['url'].rstrip('/')
        for headers in ({'Origin': origin}, {'Origin': origin, 'X-AXB-Token': self.app.token}):
            req = urllib.request.Request(f'http://127.0.0.1:{self.app.port}/api/overview', headers=headers)
            with self.assertRaises(urllib.error.HTTPError) as refused:
                urllib.request.urlopen(req, timeout=10)
            self.assertEqual(refused.exception.code, 403)
        run = self.app.owner_runs.runs[pid]
        stopped = self.act(pid, 'result-stop')
        self.assertFalse(stopped['running'])
        self.assertFalse(run['cwd'].exists())                               # run folder (and its grants) removed
        self.assertFalse(run['proc'].alive())
        with self.assertRaises(OSError):
            open(rf"\\.\pipe\axb-{run['run_id']}-ctl", 'rb')
        with self.assertRaises(OSError):
            urllib.request.urlopen(r['url'], timeout=5)
        kinds = [e['kind'] for e in self.store.events(pid, {'owner_web_run_start', 'owner_web_run_stop'})]
        self.assertEqual(kinds, ['owner_web_run_start', 'owner_web_run_stop'])

    def test_exited_or_expired_runs_are_cleaned(self):
        pid = self.project('A')
        r = self.act(pid, 'result')
        run = self.app.owner_runs.runs[pid]
        try:
            urllib.request.urlopen(f"{r['url']}quit", timeout=10).read()
        except OSError:
            pass
        time.sleep(1)
        self.assertFalse(self.app.owner_runs.status(pid)['running'])        # program exited -> reaped
        self.assertFalse(run['cwd'].exists())
        self.act(pid, 'result')
        run = self.app.owner_runs.runs[pid]
        original = owner_runs.LIFETIME
        owner_runs.LIFETIME = 0
        try:
            self.assertFalse(self.app.owner_runs.status(pid)['running'])    # lifetime reached -> stopped
        finally:
            owner_runs.LIFETIME = original
        self.assertFalse(run['proc'].alive())

    def test_unsupported_launches_are_refused_without_starting(self):
        no_port = self.project('C', args=('--no-browser',))
        with self.assertRaises(Rejected) as why:
            self.act(no_port, 'result')
        self.assertIn('{port}', str(why.exception))
        self.assertEqual(self.app.owner_runs.runs, {})


if __name__ == '__main__':
    unittest.main()
