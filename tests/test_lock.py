"""One session per project: GUI threads, CLI processes and Codex sessions cannot overlap."""
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from axbranch import engine as E
from axbranch.state import Busy, Store, run_lock
from tests.test_engine import GOOD, Script

HOLD = ("import sys, time\nsys.path.insert(0, sys.argv[2])\nfrom axbranch.state import run_lock\n"
        "with run_lock(sys.argv[1]):\n    print('held', flush=True)\n    time.sleep(60)\n")


class LockTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.store = Store(self.tmp / 'ws' / 'axbranch.sqlite3')

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_second_thread_is_refused_and_changes_nothing(self):
        entered, release = threading.Event(), threading.Event()
        script = Script([GOOD], ['PASS'])

        def slow(prompt, schema, **kw):
            if schema is E.BUILD:
                entered.set()
                release.wait(10)
            return script(prompt, schema, **kw)
        pid = self.store.new_project('make an add tool')
        def first_session():      # like the GUI: its own connection, opened in its own thread
            store = Store(self.tmp / 'ws' / 'axbranch.sqlite3')
            try:
                E.Engine(store, workspace=self.tmp / 'ws', vault=self.tmp / 'v', gai_db=self.tmp / 'x.db', llm=slow).run(pid)
            finally:
                store.close()
        worker = threading.Thread(target=first_session)
        worker.start()
        self.assertTrue(entered.wait(10))
        events = len(self.store.events(pid))
        second = E.Engine(self.store, workspace=self.tmp / 'ws', vault=self.tmp / 'v', gai_db=self.tmp / 'x.db', llm=slow)
        with self.assertRaises(Busy):
            second.run(pid)
        with self.assertRaises(Busy):
            second.close(pid, 'save')
        self.assertEqual(len(self.store.events(pid)), events)      # refused before writing anything
        self.assertEqual(self.store.project(pid)['state'], 'EXECUTING')
        release.set()
        worker.join(10)
        self.assertEqual(self.store.project(pid)['state'], 'OWNER_REVIEW')

    def test_other_process_holds_lock_and_crash_releases_it(self):
        lock = self.tmp / 'run.lock'
        holder = subprocess.Popen([sys.executable, '-c', HOLD, str(lock), str(Path(__file__).resolve().parents[1])],
                                  stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(holder.stdout.readline().strip(), 'held')
            with self.assertRaises(Busy):
                with run_lock(lock):
                    pass
        finally:
            holder.kill()          # a crash, not a clean exit
            holder.wait()
            holder.stdout.close()
        with run_lock(lock):       # the OS released it: no stale lock
            pass


if __name__ == '__main__':
    unittest.main()
