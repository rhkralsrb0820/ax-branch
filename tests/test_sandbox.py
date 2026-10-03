"""Containment for generated code: clean env, whole process tree dies, limits hold."""
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

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
