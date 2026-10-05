"""Independent watchdog acceptance: real locks/process trees, scripted providers only."""
import csv
import io
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from axbranch import engine as E, supervisor
from axbranch.state import Store, run_lock
from tests.test_engine import GOOD, LAUNCHABLE, Script


# A controlled hung engine session, without invoking a subscription CLI. The
# descendant proves that recovery kills a tree rather than just the lock holder.
HOLD = """
import json, os, subprocess, sys, time
from pathlib import Path
from axbranch.state import run_lock
folder = Path(sys.argv[1])
with run_lock(folder / 'run.lock'):
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'],
                             creationflags=0x08000000 if os.name == 'nt' else 0)
    (folder / 'child.pid').write_text(str(child.pid), encoding='utf-8')
    (folder / 'HEARTBEAT.json').write_text(json.dumps({
        'os_pid': os.getpid(), 'at': time.time() - 3600,
        'detail': 'controlled hung session', 'state': 'EXECUTING'}), encoding='utf-8')
    (folder / 'ready').touch()
    time.sleep(60)
"""


def alive(pid):
    if os.name == 'nt':
        result = subprocess.run(['tasklist', '/FI', f'PID eq {pid}', '/FO', 'CSV', '/NH'],
                                capture_output=True, text=True, timeout=5,
                                creationflags=subprocess.CREATE_NO_WINDOW, check=True)
        return any(len(row) > 1 and row[1] == str(pid)
                   for row in csv.reader(io.StringIO(result.stdout)))
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


class SupervisorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.tmp = Path(self.temp.name)
        self.ws = self.tmp / 'ws'
        self.store = Store(self.ws / 'axbranch.sqlite3')
        self.addCleanup(self.store.close)
        self.script = Script([GOOD, LAUNCHABLE], ['PASS'], strategy='switch_provider')
        self.engine = E.Engine(self.store, workspace=self.ws, vault=self.tmp / 'vault',
                               gai_db=self.tmp / 'none.db', llm=self.script)
        self.workers = []
        self.addCleanup(self.cleanup_workers)
        self.pid = self.store.new_project('make an add tool')
        self.engine.run(self.pid, stop_at='EXECUTING')
        self.folder = self.ws / 'projects' / self.pid
        self.launch = mock.Mock()
        self.stop = mock.Mock(side_effect=lambda p, w: supervisor.stop_worker(w, pid=p))

    def supervise(self):
        return supervisor.supervise(self.engine, self.pid, launch=self.launch, stop=self.stop)

    def status(self):
        return supervisor.status(self.ws, self.store, self.pid)

    def recoveries(self):
        return [e['detail'] for e in self.store.events(self.pid, {'recovery'})]

    def start_worker(self):
        worker = subprocess.Popen([sys.executable, '-X', 'utf8', '-c', HOLD, str(self.folder)],
                                  cwd=Path(__file__).resolve().parents[1],
                                  env={**os.environ, 'AXB_ROOT': str(self.tmp)},
                                  stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL,
                                  creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                                  start_new_session=os.name != 'nt')
        # Register before waiting: even failed startup must be cleaned up.
        self.workers.append((worker, self.folder / 'child.pid'))
        end = time.monotonic() + 5
        while not (self.folder / 'ready').exists() and time.monotonic() < end:
            self.assertIsNone(worker.poll(), 'lock holder exited before ready')
            time.sleep(0.02)
        self.assertTrue((self.folder / 'ready').exists(), 'lock holder startup timed out')
        child = int((self.folder / 'child.pid').read_text(encoding='utf-8'))
        self.assertTrue(alive(worker.pid))
        self.assertTrue(alive(child))
        return worker, child

    def cleanup_workers(self):
        for worker, child_file in self.workers:
            pids = [worker.pid]
            if child_file.exists():
                pids.append(int(child_file.read_text(encoding='utf-8')))
            for pid in pids:
                if alive(pid):
                    if os.name == 'nt':
                        subprocess.run(['taskkill', '/PID', str(pid), '/T', '/F'],
                                       capture_output=True, timeout=5,
                                       creationflags=subprocess.CREATE_NO_WINDOW)
                    else:
                        try:
                            os.kill(pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
            worker.wait(timeout=5)
            self.assert_gone(pids)

    def assert_gone(self, pids):
        end = time.monotonic() + 5
        remaining = list(pids)
        while remaining and time.monotonic() < end:
            remaining = [pid for pid in remaining if alive(pid)]
            if remaining:
                time.sleep(0.05)
        self.assertEqual(remaining, [], 'test-started processes survived')

    def test_stalled_worker_tree_is_stopped_and_active_resume_is_not_duplicated(self):
        worker, child = self.start_worker()
        rec = self.status()
        self.assertEqual(rec['status'], 'STALLED')
        self.assertEqual(rec['worker_pid'], worker.pid)
        self.assertIn('no engine heartbeat', rec['reason'])
        self.assertEqual(self.supervise(), 'resume')
        worker.wait(timeout=5)
        # Check before teardown: cleanup must not hide a broken stop_worker.
        self.assert_gone([worker.pid, child])
        self.stop.assert_called_once_with(self.pid, worker.pid)
        self.assertEqual([r['action'] for r in self.recoveries()], ['resume'])
        self.launch.assert_called_once_with(self.pid)
        with run_lock(self.folder / 'run.lock'):
            self.engine.beat(self.pid, 'fake resumed worker is active')
            self.assertEqual(self.status()['status'], 'ACTIVE')
            self.assertIsNone(self.supervise())
        self.launch.assert_called_once_with(self.pid)
        self.assertEqual(len(self.recoveries()), 1)

    def test_orphaned_executing_project_resumes(self):
        (self.folder / 'HEARTBEAT.json').unlink()
        self.assertEqual(self.store.project(self.pid)['state'], 'EXECUTING')
        self.assertEqual(self.status()['status'], 'STALLED')
        self.assertEqual(self.supervise(), 'resume')
        self.launch.assert_called_once_with(self.pid)
        self.stop.assert_not_called()
        self.assertEqual(self.recoveries()[0]['action'], 'resume')

    def test_same_failure_resumes_replans_then_needs_owner(self):
        self.assertEqual(self.supervise(), 'resume')
        with mock.patch.object(self.engine, 'replan', wraps=self.engine.replan) as replan:
            self.assertEqual(self.supervise(), 'replan+resume')
        replan.assert_called_once()
        self.assertEqual(replan.call_args.args[0], self.pid)
        self.assertEqual(sum(s is E.STRATEGY for s, _, _ in self.script.prompts), 1)
        self.assertEqual(self.store.project(self.pid)['state'], 'REWORK')
        # Simulate the launched engine reaching the same failing stage again.
        self.engine.run(self.pid, stop_at='EXECUTING')
        self.assertEqual(self.supervise(), 'needs_owner_decision')
        p = self.store.project(self.pid)
        self.assertEqual(p['state'], 'PAUSED')
        self.assertIn('NEEDS_DECISION', p['pause_reason'])
        self.assertEqual(self.status()['status'], 'WAITING_FOR_OWNER')
        self.assertEqual(self.launch.call_args_list, [mock.call(self.pid), mock.call(self.pid)])
        records = self.recoveries()
        self.assertEqual([r['action'] for r in records],
                         ['resume', 'replan+resume', 'needs_owner_decision'])
        self.assertEqual([r['attempt'] for r in records], [1, 2, 3])
        self.assertEqual(len({r['signature'] for r in records}), 1)
        self.assertIsNone(self.supervise())

    def test_waiting_provider_owner_and_completed_are_left_untouched(self):
        cases = [('PAUSED', 'RateLimited: usage limit', 'WAITING_FOR_PROVIDER'),
                 ('PAUSED', 'No provider available', 'WAITING_FOR_PROVIDER'),
                 ('PAUSED', 'approval needed', 'WAITING_FOR_OWNER'),
                 ('PAUSED', 'NEEDS_DECISION: recovery exhausted', 'WAITING_FOR_OWNER'),
                 ('OWNER_REVIEW', None, 'WAITING_FOR_OWNER'),
                 ('PENDING_CLOSE', None, 'WAITING_FOR_OWNER'),
                 ('ARCHIVE_PENDING_APPROVAL', None, 'WAITING_FOR_OWNER'),
                 ('CLOSED', None, 'COMPLETED')]
        for state, reason, label in cases:
            with self.subTest(state=state, reason=reason):
                self.store.update(self.pid, state=state, pause_reason=reason, resume_state='EXECUTING')
                before = self.store.project(self.pid), self.store.events(self.pid)
                self.assertEqual(self.status()['status'], label)
                self.assertIsNone(self.supervise())
                self.assertEqual((self.store.project(self.pid), self.store.events(self.pid)), before)
        self.launch.assert_not_called()
        self.stop.assert_not_called()

    def test_live_provider_slot_wait_is_left_untouched(self):
        with run_lock(self.folder / 'run.lock'):
            (self.folder / 'ACTIVITY.json').write_text(json.dumps({
                'agent': 'CEO', 'provider': 'claude', 'waiting': 'all provider slots busy'}),
                encoding='utf-8')
            self.assertEqual(self.status()['status'], 'WAITING_FOR_PROVIDER')
            self.assertIsNone(self.supervise())
        self.launch.assert_not_called()
        self.stop.assert_not_called()
        self.assertEqual(self.recoveries(), [])

    def test_failed_paused_project_escalates_to_waiting_for_owner(self):
        # supervisor.py:132: Store.pause is a no-op for an already PAUSED project.
        for attempt in range(2):
            self.store.pause(self.pid, 'Rejected: controlled provider failure')
            self.assertEqual(self.status()['status'], 'FAILED')
            self.assertEqual(self.supervise(), 'resume' if attempt == 0 else 'replan+resume')
        self.store.pause(self.pid, 'Rejected: controlled provider failure')
        self.assertEqual(self.supervise(), 'needs_owner_decision')
        self.assertEqual(self.launch.call_count, 2)
        self.assertEqual(self.status()['status'], 'WAITING_FOR_OWNER')
        self.assertIn('NEEDS_DECISION', self.store.project(self.pid)['pause_reason'])
        self.assertIsNone(self.supervise())

    def test_abandoned_recovering_marker_does_not_disable_watchdog(self):
        # supervisor.py:99: a supervisor crash leaves this marker forever authoritative.
        marker = self.folder / 'RECOVERING'
        marker.write_text('supervisor crashed before launch', encoding='utf-8')
        old = time.time() - 86400
        os.utime(marker, (old, old))
        self.supervise()
        self.launch.assert_called_once_with(self.pid)

    def test_unreleased_worker_lock_prevents_replacement_launch(self):
        # supervisor.py:140,152: _settle expiry is ignored; a second worker is launched.
        self.start_worker()
        settle = supervisor._settle
        self.stop.side_effect = None       # model cancellation that has not completed
        with mock.patch.object(supervisor, '_settle', side_effect=lambda e, p: settle(e, p, seconds=0)):
            self.supervise()
        self.launch.assert_not_called()


if __name__ == '__main__':
    unittest.main()
