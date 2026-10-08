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

    def test_web_mode_runs_command_line_probes_as_commands(self):
        # P-bbad3c v21: a self-test probe (args, no path) was sent to the server as GET '' and judged a
        # product failure — and then reused for "again after flow" and the exact Owner launch.
        code = "import sys\nif 'selftest' in sys.argv: print('PASS selftest'); sys.exit(0)\n" + SERVER.replace('MODE', OK_MODE)
        selftest = {'name': 'self-test', 'args': ['selftest'], 'stdin': '', 'http_method': '', 'http_path': '',
                    'http_body': '', 'expect_exit': 0, 'expect_status': 0, 'expect_contains': ['PASS selftest']}
        ev = self.check(code, {**WEB, 'probes': [selftest, *WEB['probes']]})
        self.assertTrue(ev['ok'], ev)
        self.assertIn('page (again after flow)', [s['name'] for s in ev['steps']])     # an HTTP probe, not the CLI one

    def test_large_response_is_checked_whole(self):
        # v21: a 236 KB research JSON was cut at 200 000 bytes and its last keys reported missing.
        code = SERVER.replace('MODE', OK_MODE).replace(
            "json.dumps({'ticker': 'DEMO', 'sma': 2.0}).encode()", "(json.dumps({'pad': 'x' * 300000, 'tail_key': 1})).encode()")
        ev = self.check(code, {**WEB, 'probes': [WEB['probes'][0], probe('big', '/api/big', ['"tail_key"'])]})
        self.assertTrue(ev['ok'], ev)

    @unittest.skipUnless(runtime.browser(), 'no headless browser on this machine')
    def test_prose_or_missing_click_selector_is_a_misconfigured_probe(self):
        page = b"<html><body><button id=go>Go</button><div id=out>ready</div></body></html>"
        code = SERVER.replace('MODE', OK_MODE).replace("b'<h1>Stock dashboard</h1>'", repr(page))
        for body, why in (('Click the first sample and assert the summary', 'matched nothing'), ('Click: [sample', 'is not a CSS selector'),
                          ('#go||#nope', 'matched nothing')):
            browser_probe = {**probe('click', '/', ['ready']), 'http_method': 'BROWSER', 'http_body': body}
            ev = self.check(code, {**WEB, 'probes': [WEB['probes'][0], browser_probe]})
            step = next(s for s in ev['steps'] if s['name'] == 'click')
            self.assertFalse(step['ok'], step)
            self.assertTrue(step.get('probe_misconfigured'), step)
            self.assertIn('probe misconfigured', step['problems'][0])
            self.assertIn(why, step['problems'][0])
            self.assertIn('#go', step['problems'][0])                   # the ids the CEO can use

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
        page = b'<html><body><h1 id=only-in-injected-script>Ready</h1></body></html>'
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

    def test_collapsed_details_text_is_not_visible_text(self):
        # P-bbad3c v31: --dump-dom serialized closed <details> content and the harness judged it as shown.
        page = ("<html><head><meta charset=\\'utf-8\\'></head><h1>Judgment</h1><details id=\\'more\\'><summary>상세 데이터 보기</summary>"
                "<p id=\\'q\\'>시세 요약 (Quote)</p></details>")
        code = SERVER.replace('MODE', OK_MODE).replace("b'<h1>Stock dashboard</h1>'", f"'{page}'.encode()")
        browser_probe = {**probe('collapsed', '/', ['Judgment']), 'http_method': 'BROWSER',
                         'expect_absent': ['시세 요약 (Quote)']}
        ev = self.check(code, {**WEB, 'probes': [browser_probe]})
        step = next(s for s in ev['steps'] if s['name'] == 'collapsed')
        self.assertTrue(step['ok'], step)
        self.assertEqual(step['details'][0], {'id': 'more', 'open': False, 'summary': '상세 데이터 보기'})
        self.assertEqual(step['offending'][0]['id'], 'q')
        self.assertFalse(step['offending'][0]['in_inner_text'])
        self.assertIn('innerText', step['text_source'])
        self.assertTrue(step['user_agent'] and step['browser_requests'])
        opened = {**browser_probe, 'name': 'opened', 'http_body': 'summary'}     # clicking opens it: now shown
        ev = self.check(code, {**WEB, 'probes': [opened]})
        step = next(s for s in ev['steps'] if s['name'] == 'opened')
        self.assertFalse(step['ok'])
        self.assertEqual(step['clicks'][0]['selector'], 'summary')
        self.assertTrue(step['offending'][0]['in_inner_text'])

    def test_external_connections_and_browser_opens_are_recorded(self):
        code = ("import socket, sys, webbrowser\n"
                "s = socket.socket(); s.settimeout(0.2)\n"
                "try: s.connect(('203.0.113.7', 9))\n"
                "except OSError: pass\n"
                "webbrowser.open('http://127.0.0.1:1/')\n"
                "print('out'); print('err', file=sys.stderr)\n")
        spec = {'mode': 'cli', 'owner_launch': 'double-click', 'launch_args': [], 'probes': []}
        ev = self.check(code, spec)
        net = ev['network']
        self.assertEqual(net['external_count'], 1, net)
        self.assertEqual(net['external_connections'][0]['target'][0], '203.0.113.7')
        self.assertEqual(net['browser_open_requests'][0]['url'], 'http://127.0.0.1:1/')
        step = ev['steps'][0]
        self.assertEqual((step['stdout_tail'].strip(), step['stderr_tail'].strip()), ('out', 'err'))
        self.assertEqual(step['executable'], sys.executable)
        self.assertIn('AXB_AUDIT_LOG', step['env_keys'])
        self.assertEqual(self.check("print('quiet')\n", spec)['network']['external_count'], 0)

    def test_exact_owner_launch_is_observed(self):
        code = ("import webbrowser\nwebbrowser.open('http://127.0.0.1/')\n" + SERVER.replace('MODE', OK_MODE))
        ev = self.check(code, WEB)
        step = ev['steps'][-1]
        self.assertTrue(step['ok'], step)
        self.assertGreaterEqual(step['observed_seconds'], runtime.OBSERVE_SECONDS)
        self.assertTrue(step['alive_after_observation'])
        self.assertEqual([s['name'] for s in step['same_process_flow']], ['analysis api'])
        self.assertEqual(len(step['browser_open_requests']), 1)
        self.assertTrue(step['busy_port_second_launch']['differs_from_busy_port'])
        self.assertEqual(ev['network']['external_count'], 0)

    def test_late_content_and_placeholder_like_selectors(self):
        # Codex review: the text was captured right after load; a selector containing 'NEEDLES' broke the script.
        page = ("<html><body><b id=NEEDLES>x</b><div id=r>Loading</div><script>"
                "setTimeout(() => document.getElementById(\\'r\\').textContent = \\'Ready\\', 2000)</script></body></html>")
        code = SERVER.replace('MODE', OK_MODE).replace("b'<h1>Stock dashboard</h1>'", f"'{page}'.encode()")
        late = {**probe('late', '/', ['Ready']), 'http_method': 'BROWSER', 'http_body': '[id="NEEDLES"]',
                'expect_absent': ['Loading']}
        step = next(s for s in self.check(code, {**WEB, 'probes': [late]})['steps'] if s['name'] == 'late')
        self.assertTrue(step['ok'], step)
        self.assertTrue(step['clicks'][0]['clicked'])

    def test_entry_in_a_subfolder_imports_its_siblings(self):
        (self.tmp / 'sub').mkdir()
        (self.tmp / 'sub' / 'helper.py').write_text("VALUE = 'sibling ok'\n", encoding='utf-8')
        (self.tmp / 'sub' / 'app.py').write_text(
            "import os, helper\nprint(helper.VALUE, os.path.isabs(__file__))\n", encoding='utf-8')
        spec = {'mode': 'cli', 'owner_launch': 'x', 'launch_args': [], 'probes': []}
        ev = runtime.check(spec, 'sub/app.py', sys.executable, str(self.tmp))
        self.assertIn('sibling ok True', ev['steps'][0]['stdout_tail'], ev)

    def test_network_summary_classifies_by_address(self):
        log = self.tmp / 'audit.jsonl'
        rows = [('socket.connect', ['<socket family=AddressFamily.AF_INET6>', ['::ffff:127.0.0.1', 80, 0, 0]]),
                ('socket.connect', ['<socket family=AddressFamily.AF_UNIX>', '/tmp/x.sock']),
                ('socket.getaddrinfo', ['127.example.com', 443, 0, 0, 0]),
                ('socket.getaddrinfo', ['localhost', 80, 0, 0, 0])]
        log.write_text(''.join(__import__('json').dumps({'t': 0, 'pid': 1, 'event': e, 'args': a}) + '\n'
                               for e, a in rows) + '{"broken\n', encoding='utf-8')
        net = runtime.network_summary(str(log))
        self.assertEqual((net['loopback_events'], net['local_ipc_events'], net['external_count'],
                          net['malformed_log_lines']), (2, 1, 1, 1))
        self.assertEqual(net['external_connections'][0]['target'][0], '127.example.com')

    def test_owner_flow_failure_on_the_exact_launch_fails_it(self):
        mode = "if self.path.startswith('/api') and '--port' not in sys.argv: self.connection.close(); return"
        step = self.check(SERVER.replace('MODE', mode), WEB)['steps'][-1]
        self.assertFalse(step['ok'])
        self.assertTrue(any(p.startswith('flow analysis api') for p in step['problems']), step['problems'])

    def test_subprocess_probe_has_no_http_method(self):
        selftest = {**probe('self-test', '', []), 'args': ['selftest']}
        spec, notes = runtime.normalize({**WEB, 'probes': [selftest, probe('page', '/', [])]})
        self.assertEqual([p['http_method'] for p in spec['probes']], ['', 'GET'])
        self.assertIn('subprocess probe', notes[0])


if __name__ == '__main__':
    unittest.main()
