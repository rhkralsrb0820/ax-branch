"""Source verification of documents: the cited public originals are read, and claims are checked against them."""
import http.server
import json
import shutil
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from axbranch import engine as E, runtime, sources
from axbranch.state import Store
from tests.test_engine import Script

PAGE = ('<html><head><script>var secret = "not text";</script></head><body><h1>PyInstaller</h1>'
        '<p>PyInstaller bundles a Python application and all its dependencies into a single package.</p></body></html>')


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == '/doc':
            body = PAGE.encode()
            self.send_response(200); self.send_header('Content-Type', 'text/html; charset=utf-8'); self.end_headers()
            self.wfile.write(body)
        elif self.path == '/hop':
            self.send_response(302); self.send_header('Location', 'http://10.0.0.1/inside'); self.end_headers()
        else:
            self.send_response(404); self.end_headers()


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.srv = http.server.HTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.base = f'http://127.0.0.1:{self.srv.server_port}'

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()

    def test_cited_urls_in_order_without_trailing_punctuation(self):
        text = 'See https://pyinstaller.org/en/stable/. Also (https://nuitka.net/doc) and https://pyinstaller.org/en/stable/.'
        self.assertEqual(sources.cited_urls(text), ['https://pyinstaller.org/en/stable/', 'https://nuitka.net/doc'])

    def test_private_and_loopback_addresses_are_refused(self):
        rec = sources.fetch(self.base + '/doc')                       # loopback: never fetched
        self.assertEqual(rec['accessible'], False)
        self.assertIn('non-public', rec['error'])

    def test_reading_extracts_visible_text_and_records_provenance(self):
        real = sources._public
        loopback_ok = lambda host: (True, '') if host == '127.0.0.1' else real(host)
        with mock.patch.object(sources, '_public', loopback_ok), \
                mock.patch.object(sources, '_public_address', side_effect=lambda ip: ip == '127.0.0.1'):
            rec = sources.fetch(self.base + '/doc')
            gone = sources.fetch(self.base + '/missing')
            hop = sources.fetch(self.base + '/hop')                   # redirect target re-checked: private
        self.assertTrue(rec['accessible'])
        self.assertIn('bundles a Python application and all its dependencies', rec['text'])
        self.assertNotIn('not text', rec['text'])                     # script content is not page text
        self.assertEqual(len(rec['sha256']), 64)
        self.assertEqual((gone['accessible'], gone['status']), (False, 404))
        self.assertEqual(hop['accessible'], False)
        self.assertIn('non-public', hop['error'])

    def test_a_claim_is_supported_only_by_a_verbatim_quote_from_a_read_source(self):
        fetched = [{'url': 'https://a.example/x', 'final_url': None, 'accessible': True, 'status': 200, 'error': None,
                    'text': 'PyInstaller bundles a Python application and all its dependencies into a single package.'},
                   {'url': 'https://b.example/y', 'final_url': None, 'accessible': False, 'status': 403, 'error': 'HTTP 403',
                    'text': ''}]
        quote = 'bundles a Python application and all its   dependencies'
        claims = [{'claim': 'one package', 'source_url': 'https://a.example/x', 'quote': quote, 'verdict': 'supported'},
                  {'claim': 'invented', 'source_url': 'https://a.example/x', 'quote': 'compiles Python to C++ machine code',
                   'verdict': 'supported'},
                  {'claim': 'blocked', 'source_url': 'https://b.example/y', 'quote': quote, 'verdict': 'supported'},
                  {'claim': 'not cited', 'source_url': 'https://c.example/z', 'quote': quote, 'verdict': 'supported'}]
        checked = [c['checked_verdict'] for c in sources.check_claims(claims, fetched)]
        self.assertEqual(checked, ['supported', 'unverifiable', 'unverifiable', 'unverifiable'])

    def test_document_probes_are_dropped_visibly_from_the_plan(self):
        eng = E.Engine.__new__(E.Engine)
        plan = eng._sanitize({'title': 't', 'interpretation': 'i', 'artifact_kind': 'markdown', 'artifact_filename': 'r.md',
                              'acceptance_criteria': ['c'], 'verification_lenses': [], 'required_tools': [],
                              'network_access': [], 'pipeline': [{'name': 'w', 'agent_role': 'Writer', 'why': 'y', 'instructions': 'i', 'provider': 'claude', 'web': False, 'capabilities': []}], 'runtime': {
                                  'mode': 'none', 'owner_launch': 'read it', 'launch_args': [],
                                  'probes': [{'name': '문헌 대조', 'args': [], 'stdin': ''}]}})
        self.assertEqual((plan['runtime']['probes'], plan['dropped_document_probes']), ([], ['문헌 대조']))


REPORT = ('# 배포 방법 비교\n\nPyInstaller는 애플리케이션과 의존성을 하나의 패키지로 묶는다 '
          '(https://pyinstaller.org/en/stable/). ' + '자세한 비교와 권고를 정리한다. ' * 20)
SOURCE = {'url': 'https://pyinstaller.org/en/stable/', 'final_url': 'https://pyinstaller.org/en/stable/', 'status': 200,
          'content_type': 'text/html', 'bytes': 100, 'sha256': 'f' * 64, 'accessible': True, 'error': None,
          'text': 'PyInstaller bundles a Python application and all its dependencies into a single package.'}
GOOD_QUOTE = 'bundles a Python application and all its dependencies into a single package'


class ReportScript(Script):
    def __init__(self, claim_checks):
        super().__init__([REPORT], ['PASS'])
        self.claim_checks = claim_checks

    def __call__(self, prompt, schema, *args, **kw):
        result, used, notes = super().__call__(prompt, schema, *args, **kw)
        if schema is E.PLAN:
            result.update(artifact_kind='markdown', artifact_filename='report.md',
                          runtime={'mode': 'none', 'owner_launch': 'read it', 'launch_args': [], 'probes': []})
        if schema is E.VERDICT:
            result['claim_checks'] = self.claim_checks
        return result, used, notes


class SourceGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.store = Store(self.tmp / 'ws' / 'axbranch.sqlite3')

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_report(self, claim_checks):
        script = ReportScript(claim_checks)
        eng = E.Engine(self.store, workspace=self.tmp / 'ws', vault=self.tmp / 'v', gai_db=self.tmp / 'x', llm=script)
        pid = self.store.new_project('Python 배포 방법을 조사한 보고서')
        with mock.patch.object(sources, 'fetch', return_value=dict(SOURCE)) as fetch:
            eng.run(pid, stop_at='REWORK')
        return pid, script, fetch

    def test_a_verbatim_quote_from_the_fetched_source_supports_the_claim(self):
        pid, script, fetch = self.run_report([{'claim': '하나의 패키지', 'source_url': SOURCE['url'],
                                               'quote': GOOD_QUOTE, 'verdict': 'supported'}])
        self.assertEqual(fetch.call_args[0][0], SOURCE['url'])
        v = self.store.verifications(pid)[-1]
        self.assertEqual(v['verdict'], 'PASS', v['result']['findings'])
        self.assertEqual(v['result']['claim_checks'][0]['checked_verdict'], 'supported')
        check = self.store.events(pid, {'source_check'})[-1]['detail']
        self.assertEqual((check['fetched'], check['accessible'], check['supported']), (1, 1, 1))
        self.assertTrue(Path(v['checks']['sources_evidence_file']).is_file())     # what was read is kept
        verdict_prompt = next(pr for s, _, pr in script.prompts if s is E.VERDICT)
        self.assertIn('source_evidence', verdict_prompt)

    def test_an_invented_quote_never_passes(self):
        pid, _, _ = self.run_report([{'claim': 'C++ 컴파일', 'source_url': SOURCE['url'],
                                      'quote': 'compiles your Python program into native C++ code', 'verdict': 'supported'}])
        v = self.store.verifications(pid)[-1]
        self.assertEqual(v['verdict'], 'FAIL')
        self.assertTrue(any('not found in the fetched sources' in f['issue'] for f in v['result']['findings']))
        self.assertFalse(E.product_failure(v))                       # the verifier erred, not the report

    def test_a_contradiction_backed_by_the_source_is_a_product_failure(self):
        pid, _, _ = self.run_report([{'claim': 'PyInstaller는 의존성을 포함하지 않는다', 'source_url': SOURCE['url'],
                                      'quote': GOOD_QUOTE, 'verdict': 'contradicted'}])
        v = self.store.verifications(pid)[-1]
        self.assertEqual(v['verdict'], 'FAIL')
        self.assertTrue(E.product_failure(v))

    def test_fetched_sources_with_no_claim_checked_never_pass(self):
        pid, _, _ = self.run_report([])
        v = self.store.verifications(pid)[-1]
        self.assertEqual(v['verdict'], 'FAIL')
        self.assertTrue(any('no claim was checked' in f['issue'] for f in v['result']['findings']))




class SourceFailureRegressionTests(unittest.TestCase):
    def gate(self, claims, fetched):
        from types import SimpleNamespace
        eng = E.Engine.__new__(E.Engine)
        eng.store = SimpleNamespace(event=lambda *a, **kw: None)
        return eng._claim_gate('p', {'iteration': 2}, {'claim_checks': claims}, fetched)

    def test_all_inaccessible_sources_cannot_silently_pass(self):
        blocked = {**SOURCE, 'accessible': False, 'status': 429, 'error': 'HTTP 429', 'text': ''}
        findings = self.gate([], [blocked])
        self.assertTrue(findings)
        self.assertTrue(all(f['kind'] == 'harness' for f in findings))

    def test_explicitly_unverifiable_claim_cannot_silently_pass(self):
        findings = self.gate([{'claim': 'material factual claim', 'source_url': SOURCE['url'],
                               'quote': '', 'verdict': 'unverifiable'}], [SOURCE])
        self.assertTrue(findings)
        self.assertTrue(all(f['kind'] == 'harness' for f in findings))

    def test_fabricated_contradiction_is_a_harness_failure(self):
        findings = self.gate([{'claim': 'material factual claim', 'source_url': SOURCE['url'],
                               'quote': 'an invented quotation absent from the original',
                               'verdict': 'contradicted'}], [SOURCE])
        self.assertTrue(findings)
        self.assertTrue(all(f['kind'] == 'harness' for f in findings))

    def test_invalid_url_is_recorded_instead_of_crashing(self):
        rec = sources.fetch('https://[invalid')
        self.assertFalse(rec['accessible'])
        self.assertTrue(rec['error'])

    def test_unknown_charset_is_recorded_instead_of_crashing(self):
        import io
        from types import SimpleNamespace
        response = io.BytesIO(b'public source content')
        response.status = 200
        response.headers = {'Content-Type': 'text/plain; charset=nonexistent-codec'}
        with mock.patch.object(sources, '_public', return_value=(True, '')):
            rec = sources.fetch('https://example.com', opener=SimpleNamespace(open=lambda *a, **kw: response))
        self.assertFalse(rec['accessible'])
        self.assertTrue(rec['error'])

    def test_read_timeout_is_recorded_instead_of_crashing(self):
        import io
        from types import SimpleNamespace
        class Response(io.BytesIO):
            status = 200
            headers = {'Content-Type': 'text/plain'}
            def read(self, *args):
                raise TimeoutError('body read timed out')
        response = Response()
        with mock.patch.object(sources, '_public', return_value=(True, '')):
            rec = sources.fetch('https://example.com', opener=SimpleNamespace(open=lambda *a, **kw: response))
        self.assertFalse(rec['accessible'])
        self.assertTrue(rec['error'])




class SourceTransportTests(unittest.TestCase):
    def test_connection_uses_the_checked_sockaddr_without_second_dns_lookup(self):
        import socket
        infos = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443))]
        sock = mock.Mock()
        with mock.patch.object(sources.socket, 'getaddrinfo', return_value=infos) as dns, \
                mock.patch.object(sources.socket, 'socket', return_value=sock):
            self.assertIs(sources._connect_public(('example.com', 443), 3), sock)
        dns.assert_called_once()
        sock.connect.assert_called_once_with(('93.184.216.34', 443))

    def test_connection_rejects_rebound_private_address_before_connecting(self):
        import socket
        infos = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', 443))]
        with mock.patch.object(sources.socket, 'getaddrinfo', return_value=infos), \
                mock.patch.object(sources.socket, 'socket') as socket_factory:
            with self.assertRaisesRegex(OSError, 'non-public'):
                sources._connect_public(('initially-public.example', 443), 3)
        socket_factory.assert_not_called()

    def test_environment_proxy_is_not_installed_in_the_reader(self):
        import os
        with mock.patch.dict(os.environ, {'http_proxy': 'http://127.0.0.1:8888',
                                         'https_proxy': 'http://127.0.0.1:8888'}), \
                mock.patch.object(sources.urllib.request, 'build_opener', wraps=sources.urllib.request.build_opener) as build:
            sources.fetch('http://127.0.0.1/')
        self.assertEqual(build.call_args.args[0].proxies, {})

    def test_embedded_credentials_are_refused(self):
        opener = mock.Mock()
        rec = sources.fetch('https://user:secret@example.com/', opener=opener)
        self.assertFalse(rec['accessible'])
        opener.open.assert_not_called()


if __name__ == '__main__':
    unittest.main()
