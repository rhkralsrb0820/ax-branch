"""Provider CLIs run behind wrappers (npm's codex.CMD / claude.CMD -> node -> CLI). Timeout or Owner
stop must kill the REAL CLI, not just the wrapper (orphan proven live 2026-10-04)."""
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from axbranch import providers


@unittest.skipUnless(os.name == 'nt', 'cmd.exe wrapper shape is Windows-specific')
class ProviderTreeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.marker = self.tmp / 'alive.txt'
        child = self.tmp / 'cli.py'
        child.write_text(f"import time, pathlib\nfor i in range(30):\n    print('working', i, flush=True)\n"
                         f"    pathlib.Path(r'{self.marker}').write_text(str(i))\n    time.sleep(1)\n", encoding='utf-8')
        self.wrapper = self.tmp / 'fakecli.cmd'
        self.wrapper.write_text(f'@echo off\r\n"{sys.executable}" "{child}"\r\n', encoding='utf-8')
        # Independent of this machine's live state: own slot folder, memory floor not in play.
        for patcher in (mock.patch.object(providers, 'SLOT_DIR', self.tmp / 'slots'),
                        mock.patch.object(providers, 'free_memory_mb', return_value=10**6)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def assert_tree_dead(self):
        before = self.marker.read_text()
        time.sleep(3)
        self.assertEqual(self.marker.read_text(), before, 'the CLI behind the wrapper kept running')

    def test_timeout_kills_the_cli_behind_the_wrapper(self):
        ticks = []
        with mock.patch.object(providers, 'TIMEOUT', 3):
            with self.assertRaises(providers.Rejected) as ctx:
                providers._contained('codex', ['cmd', '/c', str(self.wrapper)], 'prompt', str(self.tmp), None, ticks.append)
        self.assertIn('프로세스 트리 전체를 종료', str(ctx.exception))
        self.assert_tree_dead()
        self.assertTrue(ticks and ticks[-1]['elapsed'] >= 3 and ticks[-1]['provider'] == 'codex')
        self.assertTrue(any(t['output_bytes'] > 0 for t in ticks))          # live output was visible

    def test_owner_stop_kills_the_cli_behind_the_wrapper(self):
        stop = threading.Event()
        threading.Timer(2, stop.set).start()
        with self.assertRaises(providers.Rejected) as ctx:
            providers._contained('claude', ['cmd', '/c', str(self.wrapper)], 'prompt', str(self.tmp), stop, None)
        self.assertIn('중단', str(ctx.exception))
        self.assert_tree_dead()


class AuthorityTests(unittest.TestCase):
    """The recorded authority of a turn must be what the adapter flags actually enforce."""
    def args_of(self, name, web):
        seen = {}

        def fake(provider, args, prompt, cwd, cancel, on_tick):
            seen['args'] = args
            raise providers.Rejected('stop here')
        with mock.patch.object(providers, '_contained', fake), mock.patch.object(providers.shutil, 'which', lambda b: b):
            with self.assertRaises(providers.Rejected):
                providers.RUN[name]('p', {'type': 'object', 'properties': {}, 'required': [], 'additionalProperties': False}, web)
        return ' '.join(seen['args'])

    def test_recorded_authority_matches_the_enforcing_flags(self):
        for web in (False, True):
            with self.subTest(web=web):
                claude, codex = self.args_of('claude', web), self.args_of('codex', web)
                self.assertEqual(providers.authority('claude', web)['web_research'], '--tools WebSearch,WebFetch' in claude)
                self.assertIn('--disallowedTools Bash,Write,Edit,NotebookEdit,Task', claude)
                self.assertIn('--restricted', claude)
                self.assertIn('{"mcpServers":{}}', claude)
                self.assertIn('--no-session-persistence', claude)
                self.assertIn('--sandbox read-only', codex)
                self.assertIn('features.shell_tool=false', codex)
                self.assertIn('--ephemeral', codex)
                self.assertIn(f'web_search="{"live" if web else "disabled"}"', codex)
                self.assertEqual(providers.authority('codex', web)['web_research'], web)
                self.assertFalse(providers.authority('claude', web)['shell'] or providers.authority('codex', web)['file_write'])
        self.assertIsNone(providers.authority('gemini', False))                   # unknown provider: fail closed


if __name__ == '__main__':
    unittest.main()
