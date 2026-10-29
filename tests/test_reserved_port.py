"""A delivered web program that defaults to AX Branch's own port fails with that exact reason (not a vague 'nothing
listening'), and planner/producer are told the port is reserved."""
import sys
import tempfile
import unittest
from pathlib import Path

from axbranch import engine as E, runtime

APP = ('import sys, time\n'
       'if "--port" in sys.argv:\n'
       '    import http.server\n'
       '    port = int(sys.argv[sys.argv.index("--port") + 1])\n'
       '    print(f"Serving at http://127.0.0.1:{port}/", flush=True)\n'
       '    http.server.HTTPServer(("127.0.0.1", port), http.server.SimpleHTTPRequestHandler).serve_forever()\n'
       'print("Serving at http://127.0.0.1:8765/", flush=True)\n'
       'time.sleep(60)\n')


class ReservedPortTests(unittest.TestCase):
    def test_owner_launch_on_the_reserved_port_names_the_reason(self):
        work = Path(tempfile.mkdtemp(prefix='axb-port-'))
        (work / 'app.py').write_text(APP, encoding='utf-8')
        spec = {'mode': 'web', 'owner_launch': 'double-click app.py', 'launch_args': ['--port', '{port}'],
                'probes': [{'name': 'page', 'http_method': 'GET', 'http_path': '/', 'expect_status': 0}]}
        ev = runtime.check(spec, 'app.py', sys.executable, str(work))
        owner = next(s for s in ev['steps'] if s['name'].startswith('exact Owner launch'))
        self.assertFalse(owner['ok'])
        self.assertIn('reserved', owner['problems'][0])
        self.assertIn('8765', owner['problems'][0])

    def test_planner_and_producer_are_told(self):
        self.assertIn('8765', E.RUNTIME_RULES)
        self.assertIn('8765', E.EXEC_CONTRACT)


if __name__ == '__main__':
    unittest.main()
