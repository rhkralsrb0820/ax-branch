"""What is actually enforced when a generated Python program runs: the audit-hook launcher refuses every non-local
connection during verification and, for the Owner's [결과 실행], everything but loopback and approved domains.
Best effort inside Python (not an OS firewall); files are not restricted. These tests run real child processes."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from axbranch import engine as E, runtime
from axbranch.state import Store
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
        path, _ = eng.launch_verified(pid, popen=popen)
        args, kwargs = popen.call_args
        self.assertEqual(args[0][-2:], ['_axb_launch.py', path.name])
        self.assertTrue((path.parent / '_axb_launch.py').is_file())
        self.assertEqual(kwargs['env']['AXB_ALLOW_HOSTS'], '')                 # nothing approved: loopback only
        run = self.store.events(pid, {'owner_run'})[-1]['detail']
        self.assertIn('not an OS firewall', run['network']['enforced_by'])
        self.assertIn('not restricted', run['files'])



class BrowserPhaseTests(unittest.TestCase):
    def test_a_timeout_says_where_the_browser_stalled(self):
        self.assertIn('browser start', runtime.phases(0.0, [], 95.0, False, 0)['stalled_at'])
        p = runtime.phases(0.0, [0.4, 1.2], 95.0, False, 3)
        self.assertEqual((p['first_request_ms'], p['last_request_ms'], p['outcome']), (400, 1200, 'time limit'))
        self.assertIn('never exited', p['stalled_at'])
        self.assertIsNone(runtime.phases(0.0, [0.5], 2.0, True, 1)['stalled_at'])


if __name__ == '__main__':
    unittest.main()
