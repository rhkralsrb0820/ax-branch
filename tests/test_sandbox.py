"""Containment for generated code: clean env, whole process tree dies, limits hold."""
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from axbranch import sandbox

# Starts a detached-looking grandchild that would write a marker after 3 s, then exits at once.
ORPHAN = ("import subprocess, sys\n"
          "subprocess.Popen([sys.executable, '-c', \"import time,pathlib; time.sleep(3); "
          "pathlib.Path(r'MARKER').write_text('escaped')\"])\n"
          "print('parent done')\n")


class SandboxTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_code(self, code, timeout=30):
        (self.tmp / 'p.py').write_text(code, encoding='utf-8')
        return sandbox.run([sys.executable, '-I', 'p.py'], str(self.tmp), timeout)

    def test_parent_secrets_do_not_reach_generated_code(self):
        os.environ['AXB_TEST_SECRET'] = 'top-secret-token'
        try:
            code, out = self.run_code("import os\nprint(sorted(os.environ))\n"
                                      "assert 'AXB_TEST_SECRET' not in os.environ\n"
                                      "assert not any('TOKEN' in k or 'KEY' in k for k in os.environ)\n")
        finally:
            del os.environ['AXB_TEST_SECRET']
        self.assertEqual(code, 0, out)

    def test_failed_process_creation_releases_files_job_and_scratch(self):
        for split in (False, True):
            proc = sandbox.Contained.__new__(sandbox.Contained)
            with mock.patch.object(sandbox.subprocess, 'Popen', side_effect=FileNotFoundError('missing CLI')):
                with self.assertRaisesRegex(FileNotFoundError, 'missing CLI'):
                    proc.__init__(['missing-cli'], str(self.tmp), '', split=split)
            try:
                self.assertFalse(proc.tmp.exists(), 'failed construction leaked its temporary folder')
                self.assertIsNone(proc.job, 'failed construction leaked a Job Object')
                for handle in (proc._out, proc._in, proc._err):
                    self.assertTrue(handle is None or handle.closed)
            finally:  # also clean the old implementation when this regression is mutation-tested
                if proc.job is not None:
                    sandbox._k32.CloseHandle(proc.job)
                for handle in (proc._out, proc._in, proc._err):
                    if handle is not None:
                        handle.close()
                proc.cleanup()

    def test_failed_stdin_setup_releases_scratch_before_launch(self):
        proc = sandbox.Contained.__new__(sandbox.Contained)
        with mock.patch.object(Path, 'write_bytes', side_effect=OSError('disk full')), \
                mock.patch.object(sandbox.subprocess, 'Popen') as launch:
            with self.assertRaisesRegex(OSError, 'disk full'):
                proc.__init__(['unused'], str(self.tmp), '')
        launch.assert_not_called()
        self.assertFalse(proc.tmp.exists())

    @unittest.skipUnless(os.name == 'nt', 'Windows suspended process startup')
    def test_failed_resume_kills_suspended_process_and_releases_job(self):
        proc = sandbox.Contained.__new__(sandbox.Contained)
        try:
            with mock.patch.object(sandbox._ntdll, 'NtResumeProcess', return_value=-1):
                with self.assertRaisesRegex(OSError, 'NtResumeProcess failed'):
                    proc.__init__([sys.executable, '-c', 'import time; time.sleep(30)'], str(self.tmp), '')
            self.assertIsNotNone(proc.proc.poll())
            self.assertIsNone(proc.job)
            self.assertFalse(proc.tmp.exists())
        finally:
            if proc.proc is not None:
                proc.stop()
            proc.cleanup()

    def test_grandchild_is_killed_when_the_check_ends(self):
        marker = self.tmp / 'escaped.txt'
        code, out = self.run_code(ORPHAN.replace('MARKER', marker.as_posix()))
        self.assertEqual(code, 0, out)
        time.sleep(5)
        self.assertFalse(marker.exists(), 'a process outlived the check')

    def test_timeout_kills_the_whole_tree(self):
        marker = self.tmp / 'late.txt'
        start = time.monotonic()
        code, out = self.run_code(ORPHAN.replace('MARKER', marker.as_posix()) + "import time\ntime.sleep(60)\n", timeout=2)
        self.assertIsNone(code)
        self.assertLess(time.monotonic() - start, 15)
        time.sleep(4)
        self.assertFalse(marker.exists())

    @unittest.skipUnless(os.name == 'nt', 'Job Object limit is Windows-specific')
    def test_process_count_is_capped(self):
        code, out = self.run_code(
            "import subprocess, sys\nprocs=[]\n"
            "try:\n"
            "    for _ in range(20):\n"
            "        procs.append(subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(5)']))\n"
            "except OSError:\n"
            "    print('capped at', len(procs)); sys.exit(0)\n"
            "sys.exit(1)\n")
        self.assertEqual(code, 0, out)
        self.assertIn(f'capped at {sandbox.MAX_PROCESSES - 1}', out)


if __name__ == '__main__':
    unittest.main()
