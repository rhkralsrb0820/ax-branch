"""Resource-aware provider execution: machine-wide slots, memory floor, sleep is not a timeout."""
import shutil
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from axbranch import providers
from axbranch.state import run_lock


class FakeProc:
    """Stands in for a contained CLI: running for a few polls, then exits 0."""
    def __init__(self, polls):
        self.polls, self.log = polls, Path(tempfile.mkdtemp()) / 'out.txt'
        self.log.write_text('x', encoding='utf-8')
        self.proc = mock.Mock(pid=1)

    def wait(self, timeout):
        self.polls -= 1
        return 0 if self.polls <= 0 else None

    def output(self):
        return '{}'

    def stop(self):
        return 0

    def cleanup(self):
        shutil.rmtree(self.log.parent, ignore_errors=True)


class ResourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        patcher = mock.patch.object(providers, 'SLOT_DIR', self.tmp)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_waits_when_all_machine_slots_are_busy(self):
        held = [run_lock(self.tmp / f'slot-{i}.lock') for i in range(providers.MAX_PARALLEL_CLI)]
        for lock in held:
            lock.__enter__()
        ticks, stop = [], threading.Event()
        threading.Timer(3, stop.set).start()
        try:
            with self.assertRaises(providers.Rejected):
                providers._acquire_slot('codex', stop, ticks.append)
        finally:
            for lock in held:
                lock.__exit__(None, None, None)
        self.assertIn('slots busy', ticks[-1]['waiting'])
        slot = providers._acquire_slot('codex', None, None)          # freed -> immediately available
        slot.__exit__(None, None, None)

    def test_low_memory_pauses_instead_of_launching(self):
        with mock.patch.object(providers, 'free_memory_mb', return_value=200), \
                mock.patch.object(providers, 'MEMORY_WAIT', 0), \
                mock.patch.object(providers.sandbox, 'start') as start:
            with self.assertRaises(providers.Rejected) as ctx:
                providers._contained('claude', ['x'], 'p', str(self.tmp), None, None)
        self.assertIn('메모리', str(ctx.exception))
        start.assert_not_called()                                       # nothing was launched

    def test_time_asleep_does_not_count_as_a_timeout(self):
        clock = iter([0, 1, 2, 5000, 5001, 5002, 5003])                   # a 13-hour-like jump mid-call
        ticks = []
        with mock.patch.object(providers, 'TIMEOUT', 100), \
                mock.patch.object(providers.time, 'monotonic', side_effect=lambda: next(clock)), \
                mock.patch.object(providers.sandbox, 'start', return_value=FakeProc(polls=4)):
            code, out = providers._contained('codex', ['x'], 'p', str(self.tmp), None, ticks.append)
        self.assertEqual(code, 0)                                       # finished, not "timed out"
        self.assertGreater(ticks[-1]['slept'], 4000)
        self.assertLess(ticks[-1]['elapsed'], 100)


if __name__ == '__main__':
    unittest.main()
