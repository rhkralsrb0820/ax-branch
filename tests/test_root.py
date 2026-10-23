"""Workspace root resolution: a packaged exe inside a vault-less workspace root (the demo package) opens that
workspace; a source run never adopts a stray workspace/ next to the code."""
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import axbranch


class RootTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / 'workspace').mkdir()
        (self.tmp / 'workspace' / 'axbranch.sqlite3').write_bytes(b'')
        self.exe = self.tmp / 'AXBranch-0.1.57' / 'AXBranch.exe'
        self.exe.parent.mkdir()
        env = {k: v for k, v in os.environ.items() if k != 'AXB_ROOT'}
        self.env = mock.patch.dict(os.environ, env, clear=True)
        self.env.start()

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_packaged_exe_opens_the_workspace_root_it_sits_in(self):
        with mock.patch.object(sys, 'frozen', True, create=True), mock.patch.object(sys, 'executable', str(self.exe)):
            self.assertEqual(axbranch._root(), self.tmp.resolve())

    def test_source_run_ignores_a_vaultless_workspace(self):
        code = self.tmp / 'ax-branch' / 'axbranch' / '__init__.py'
        code.parent.mkdir(parents=True)
        (self.tmp / 'ax-branch' / 'workspace').mkdir()
        (self.tmp / 'ax-branch' / 'workspace' / 'axbranch.sqlite3').write_bytes(b'')
        with mock.patch.object(axbranch, '__file__', str(code)):
            self.assertNotEqual(axbranch._root(), (self.tmp / 'ax-branch').resolve())


if __name__ == '__main__':
    unittest.main()
