"""Runtime Acceptance with real processes: servers that work, drop connections, crash; CLIs; windows."""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from axbranch import runtime

SERVER = '''import sys, json
from http.server import BaseHTTPRequestHandler, HTTPServer
port = int(sys.argv[sys.argv.index('--port') + 1]) if '--port' in sys.argv else 0   # no args: OS-chosen, announced
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        MODE
        body = b'<h1>Stock dashboard</h1>' if self.path == '/' else json.dumps({'ticker': 'DEMO', 'sma': 2.0}).encode()
        self.send_response(200); self.end_headers(); self.wfile.write(body)
srv = HTTPServer(('127.0.0.1', port), H)
print(f'Serving at http://127.0.0.1:{srv.server_port}/', flush=True)
srv.serve_forever()
'''
OK_MODE = 'pass'
DROP_MODE = "if self.path.startswith('/api'): self.connection.close(); return"   # page loads, its API call dies


def probe(name, path, contains, status=200):
    return {'name': name, 'args': [], 'stdin': '', 'http_method': 'GET', 'http_path': path, 'http_body': '',
            'expect_exit': -1, 'expect_status': status, 'expect_contains': contains}


WEB = {'mode': 'web', 'owner_launch': 'double-click app.py', 'launch_args': ['--port', '{port}', '--no-browser'],
       'probes': [probe('page', '/', ['Stock dashboard']), probe('analysis api', '/api/analyze?t=DEMO', ['"sma"'])]}


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def check(self, code, spec):
        (self.tmp / 'app.py').write_text(code, encoding='utf-8')
        return runtime.check(spec, 'app.py', sys.executable, str(self.tmp))

    def test_working_web_app_passes(self):
        ev = self.check(SERVER.replace('MODE', OK_MODE), WEB)
        self.assertTrue(ev['ok'], ev)
        self.assertEqual([s['name'] for s in ev['steps']],
                         ['server start', 'page', 'analysis api', 'page (again after flow)', 'server survived',
                          'exact Owner launch (no arguments)'])

    def test_dropped_connection_is_caught(self):
        ev = self.check(SERVER.replace('MODE', DROP_MODE), WEB)
        self.assertFalse(ev['ok'])
        api = next(s for s in ev['steps'] if s['name'] == 'analysis api')
        self.assertTrue(any('connection lost' in p for p in api['problems']), api)

    def test_crash_before_listening_is_caught(self):
        ev = self.check("raise SystemExit('missing dependency: yfinance')\n", WEB)
        self.assertFalse(ev['ok'])
        self.assertIn('exited', ev['steps'][0]['problems'][0])

    def test_cli_that_only_runs_tests_on_launch_fails_a_real_probe(self):
        spec = {'mode': 'cli', 'owner_launch': 'double-click', 'launch_args': [],
                'probes': [{'name': 'demo report', 'args': ['demo'], 'stdin': '', 'http_method': '', 'http_path': '',
                            'http_body': '', 'expect_exit': 0, 'expect_status': 0, 'expect_contains': ['Report']}]}
        ev = self.check("print('PASS: self-test')\n", spec)
        self.assertFalse(ev['ok'])
        ok = self.check("import sys\nprint('Report for', sys.argv[1:])\n", spec)
        self.assertTrue(ok['ok'], ok)

    def test_web_contract_is_enforced_even_if_the_plan_forgot_it(self):
        spec = {**WEB, 'launch_args': []}                       # what a live plan actually returned
        ev = self.check(SERVER.replace('MODE', OK_MODE), spec)
        self.assertTrue(ev['ok'], ev)
        self.assertEqual(ev['launch_args'], ['--port', '{port}', '--no-browser'])
        self.assertTrue(ev['notes'])

    def test_browser_cannot_open_during_verification(self):
        spec = {'mode': 'cli', 'owner_launch': 'x', 'launch_args': [],
                'probes': [{'name': 'browser', 'args': [], 'stdin': '', 'http_method': '', 'http_path': '',
                            'http_body': '', 'expect_exit': 0, 'expect_status': 0, 'expect_contains': ['browser=']}]}
        ev = self.check("import os, webbrowser\nprint('browser=' + os.environ.get('BROWSER', 'DEFAULT'))\n"
                        "assert os.environ.get('BROWSER')\n", spec)
        self.assertTrue(ev['ok'], ev)

    def test_exact_owner_launch_must_serve_too(self):
        # Works with --port, but a double-click (no args) crashes: must FAIL.
        code = SERVER.replace('MODE', OK_MODE).replace(
            "port = int(", "if '--port' not in sys.argv: raise SystemExit('boom')\nport = int(", 1)
        ev = self.check(code, WEB)
        self.assertFalse(ev['ok'])
        self.assertFalse(ev['steps'][-1]['ok'])
        self.assertEqual(ev['steps'][-1]['name'], 'exact Owner launch (no arguments)')

    @unittest.skipUnless(runtime.browser(), 'no headless browser on this machine')
    def test_rendered_page_is_checked_not_just_served(self):
        page = ("<html><body><div id=r>loading</div><script>"
                "fetch('/api/analyze?t=DEMO').then(r=>r.json()).then(j=>{"
                "document.getElementById('r').textContent='SMA '+j.sma+' rendered'})</script></body></html>")
        code = SERVER.replace('MODE', OK_MODE).replace("b'<h1>Stock dashboard</h1>'", repr(page.encode()))
        browser_probe = {'name': 'rendered analysis', 'args': [], 'stdin': '', 'http_method': 'BROWSER',
                         'http_path': '/', 'http_body': '', 'expect_exit': -1, 'expect_status': 0,
                         'expect_contains': ['SMA 2 rendered']}
        spec = {**WEB, 'probes': [probe('analysis api', '/api/analyze?t=DEMO', ['"sma"']), browser_probe]}
        ev = self.check(code, spec)
        self.assertTrue(ev['ok'], ev)
        # The same words present only inside <script> (never rendered) must not count.
        broken = code.replace("textContent='SMA '+j.sma+' rendered'", "textContent='error'; var s='SMA 2 rendered'")
        ev = self.check(broken, spec)
        self.assertFalse(ev['ok'])
        self.assertIn('rendered page lacks', str(next(s for s in ev['steps'] if s['name'] == 'rendered analysis')['problems']))

    @unittest.skipUnless(runtime.browser(), 'no headless browser on this machine')
    def test_browser_clicks_primary_flow_in_order(self):
        page = ("<html><body><div id=r>loading</div><script>"
                "document.addEventListener('DOMContentLoaded',()=>setTimeout(()=>{"
                "const start=document.createElement('button'); start.id='start';"
                "start.textContent='Start'; document.body.append(start);"
                "start.onclick=()=>setTimeout(()=>{"
                "const analyze=document.createElement('button'); analyze.id='analyze';"
                "analyze.textContent='Analyze'; document.body.append(analyze);"
                "analyze.onclick=()=>fetch('/api/analyze?t=DEMO').then(r=>r.json()).then(j=>{"
                "document.getElementById('r').textContent='SMA '+j.sma+' rendered'});"
                "},450);},600));</script></body></html>")
        code = SERVER.replace('MODE', OK_MODE).replace("b'<h1>Stock dashboard</h1>'", repr(page.encode()))
        code = code.replace('self.end_headers()',
                            "self.send_header('Content-Type', 'text/html' if self.path == '/' else 'application/json'); "
                            "self.send_header('Content-Length', str(len(body))); self.end_headers()")
        browser_probe = {**probe('click analysis', '/', ['SMA 2 rendered']), 'http_method': 'BROWSER',
                         'http_body': '#start || #analyze'}
        ev = self.check(code, {**WEB, 'probes': [browser_probe]})
        self.assertTrue(ev['ok'], ev)
        self.assertIn('SMA 2 rendered', ev['steps'][1]['rendered_tail'])
        ev = self.check(code, {**WEB, 'probes': [{**browser_probe, 'http_body': ''}]})
        self.assertFalse(ev['ok'], ev)
        self.assertIn('rendered page lacks', str(ev['steps'][1]['problems']))
        self.assertEqual((self.tmp / 'app.py').read_text(encoding='utf-8'), code)

    @unittest.skipUnless(runtime.browser(), 'no headless browser on this machine')
    def test_click_proxy_works_with_apps_that_guard_their_host(self):
        # Like the real stock analyzer: requests whose Host is not 127.0.0.1:<own port> are refused.
        page = ("<html><body><div id=r>loading</div><button id=go>Go</button><script>"
                "document.getElementById('go').onclick=()=>fetch('/api/analyze?t=DEMO').then(r=>r.json())"
                ".then(j=>{document.getElementById('r').textContent='SMA '+j.sma+' rendered'});</script></body></html>")
        guard = ("if self.headers.get('Host') != '127.0.0.1:%d' % self.server.server_port:\n"
                 "            self.send_response(403); self.end_headers(); self.wfile.write(b'bad host'); return")
        code = SERVER.replace('MODE', guard).replace("b'<h1>Stock dashboard</h1>'", repr(page.encode()))
        code = code.replace('self.end_headers()\n', "self.send_header('Content-Type', 'text/html' if self.path == '/' "
                                                     "else 'application/json'); self.end_headers()\n", 1)
        browser_probe = {**probe('guarded click', '/', ['SMA 2 rendered']), 'http_method': 'BROWSER', 'http_body': '#go'}
        ev = self.check(code, {**WEB, 'probes': [browser_probe]})
        self.assertTrue(ev['ok'], ev)

    @unittest.skipUnless(runtime.browser(), 'no headless browser on this machine')
    def test_injected_click_script_cannot_satisfy_expect_contains(self):
        page = b'<html><body><h1>Ready</h1></body></html>'
        code = SERVER.replace('MODE', OK_MODE).replace("b'<h1>Stock dashboard</h1>'", repr(page))
        needles = ['#only-in-injected-script', 'const deadline = performance.now() + 5000']
        browser_probe = {**probe('script source is not evidence', '/', needles), 'http_method': 'BROWSER',
                         'http_body': '#only-in-injected-script'}
        ev = self.check(code, {**WEB, 'probes': [browser_probe]})
        self.assertFalse(ev['ok'], ev)
        step = ev['steps'][1]
        self.assertEqual(step['problems'], [f'rendered page lacks {needles}'])
        self.assertIn('Ready', step['rendered_tail'])
        for needle in needles:
            self.assertNotIn(needle, step['rendered_tail'])

    def test_expect_absent_catches_a_fabricated_value_that_contains_the_expected_one(self):
        # 2026-10-05: '103 104' was merged into 103104; a probe expecting '104' still passed.
        code = SERVER.replace('MODE', OK_MODE).replace(
            "json.dumps({'ticker': 'DEMO', 'sma': 2.0})", "json.dumps({'ticker': 'MIXED', 'close': [102, 103104]})")
        probe_ = {**probe('mixed separators', '/api/analyze', ['MIXED', '104']), 'expect_absent': ['103104']}
        ev = self.check(code, {**WEB, 'probes': [probe_]})
        self.assertFalse(ev['ok'])
        self.assertIn("must not contain ['103104']", str(ev['steps'][1]['problems']))
        fixed = code.replace('[102, 103104]', '[102, 103, 104]')
        self.assertTrue(self.check(fixed, {**WEB, 'probes': [probe_]})['ok'])

    def test_window_must_stay_up(self):
        spec = {'mode': 'gui', 'owner_launch': 'double-click', 'launch_args': [], 'probes': []}
        self.assertTrue(self.check('import time\ntime.sleep(30)\n', spec)['ok'])
        self.assertFalse(self.check('raise RuntimeError("no display")\n', spec)['ok'])


if __name__ == '__main__':
    unittest.main()
