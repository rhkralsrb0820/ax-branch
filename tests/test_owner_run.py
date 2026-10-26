"""Owner execution uses AppContainer by default. Legacy audit-hook probes below describe only
the explicitly reduced-protection path; they are not evidence of an OS filesystem boundary."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from axbranch import engine as E, runtime, sandbox, isolation
from axbranch.state import Store, Rejected
from tests.test_engine import BROKEN, GOOD, Script

PROBE = r'''import socket, sys
srv = socket.socket(); srv.bind(('127.0.0.1', 0)); srv.listen(1)
c = socket.socket(); c.connect(srv.getsockname()); print('loopback ok')
try:
    socket.getaddrinfo('example.com', 80); print('example.com resolved')
except PermissionError as e:
    print('example.com REFUSED', e)
except OSError as e:
    print('example.com not refused by AX Branch:', type(e).__name__)
try:
    socket.getaddrinfo('unapproved.example.net', 80); print('unapproved resolved')
except PermissionError as e:
    print('unapproved REFUSED')
except OSError as e:
    print('unapproved not refused:', type(e).__name__)
'''


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / '_axb_launch.py').write_text(runtime.AUDIT, encoding='utf-8')
        (self.tmp / 'probe.py').write_text(PROBE, encoding='utf-8')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_probe(self, allow):
        env = {'SYSTEMROOT': __import__('os').environ.get('SYSTEMROOT', ''), 'AXB_AUDIT_LOG': str(self.tmp / 'audit.jsonl'),
               'AXB_ALLOW_HOSTS': allow}
        r = subprocess.run([sys.executable, '-X', 'utf8', '_axb_launch.py', 'probe.py'], cwd=self.tmp, env=env,
                           capture_output=True, text=True, timeout=60)
        return r.stdout + r.stderr

    def test_verification_refuses_everything_non_local(self):
        out = self.run_probe('')
        self.assertIn('loopback ok', out)
        self.assertIn('example.com REFUSED', out)
        self.assertIn('unapproved REFUSED', out)
        log = [json.loads(line) for line in (self.tmp / 'audit.jsonl').read_text(encoding='utf-8').splitlines()]
        self.assertTrue(any(e['blocked'] and 'example.com' in json.dumps(e['args']) for e in log))   # evidence kept

    def test_owner_run_allows_only_approved_domains(self):
        out = self.run_probe('example.com')
        self.assertIn('loopback ok', out)
        self.assertNotIn('example.com REFUSED', out)          # resolved, or a plain network error offline
        self.assertIn('unapproved REFUSED', out)


class OwnerRunTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.store = Store(self.tmp / 'ws' / 'axbranch.sqlite3')

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_result_run_goes_through_the_launcher_and_records_what_is_enforced(self):
        eng = E.Engine(self.store, workspace=self.tmp / 'ws', vault=self.tmp / 'v', gai_db=self.tmp / 'x',
                       llm=Script([BROKEN, GOOD], ['FAIL', 'PASS']))
        pid = self.store.new_project('make an add tool')
        eng.run(pid)
        popen = mock.Mock()
        shown = []
        with mock.patch.object(sandbox, 'run', return_value=(0, 'VISIBLE RESULT')) as launch:
            _, path = eng.open_result(pid, show_text=lambda *a: shown.append(a), popen=popen)
        self.assertIsInstance(launch.call_args.kwargs['isolate'], isolation.Manifest)
        self.assertIn('VISIBLE RESULT', shown[0][1])
        popen.assert_not_called()
        run = self.store.events(pid, {'owner_run'})[-1]['detail']
        self.assertEqual(run['network']['enforced_by'], 'AppContainer')
        self.assertEqual(run['isolation']['purpose'], 'Owner result execution')

    def verified(self):
        eng = E.Engine(self.store, workspace=self.tmp / 'ws', vault=self.tmp / 'v', gai_db=self.tmp / 'x',
                       llm=Script([GOOD], ['PASS']))
        pid = self.store.new_project('make an add tool')
        eng.run(pid)
        return eng, pid

    def test_owner_result_backend_failure_never_falls_back(self):
        eng, pid = self.verified()
        popen = mock.Mock()
        with mock.patch.object(sandbox, 'run', side_effect=isolation.IsolationUnavailable('unavailable')):
            with self.assertRaisesRegex(Rejected, 'no unrestricted fallback'):
                eng.launch_verified(pid, popen=popen)
        popen.assert_not_called()
        self.assertFalse(self.store.events(pid, {'owner_run'}))
        self.assertTrue(self.store.events(pid, {'owner_run_blocked'}))

    def test_unsupported_owner_web_launch_is_blocked_before_execution(self):
        eng, pid = self.verified()
        plan = self.store.project(pid)['plan']
        plan['runtime']['mode'] = 'web'
        self.store.update(pid, plan=plan)
        with mock.patch.object(sandbox, 'run') as launch:
            with self.assertRaisesRegex(Rejected, 'no program started'):
                eng.launch_verified(pid)
        launch.assert_not_called()

    def test_owner_exception_does_not_inherit_credentials(self):
        eng, pid = self.verified()
        self.store.event(pid, 'isolation_exception', allow=True, reason='synthetic test only')
        popen = mock.Mock()
        with mock.patch.dict('os.environ', {'AXB_SYNTHETIC_TOKEN': 'not-a-real-secret'}):
            eng.launch_verified(pid, popen=popen)
        self.assertNotIn('AXB_SYNTHETIC_TOKEN', popen.call_args.kwargs['env'])
        self.assertEqual(self.store.events(pid, {'owner_run'})[-1]['detail']['isolation']['backend'],
                         'external_unisolated')



class BrowserPhaseTests(unittest.TestCase):
    def test_a_timeout_says_where_the_browser_stalled(self):
        self.assertIn('browser start', runtime.phases(0.0, [], 95.0, False, 0)['stalled_at'])
        p = runtime.phases(0.0, [0.4, 1.2], 95.0, False, 3)
        self.assertEqual((p['first_request_ms'], p['last_request_ms'], p['outcome']), (400, 1200, 'time limit'))
        self.assertIn('never exited', p['stalled_at'])
        self.assertIsNone(runtime.phases(0.0, [0.5], 2.0, True, 1)['stalled_at'])


if __name__ == '__main__':
    unittest.main()
