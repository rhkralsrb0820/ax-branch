"""The Owner-data contract carried from the CEO plan to the producer, verified by really executing it, and honoured by
the runner. No model call: the CEO/producer are scripted and the fixed developer test app stands in for a generated
program (tests/fixtures/owner_data_app; NOT AI-produced)."""
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

from axbranch import engine as E, isolation as I, owner_runs, runtime, userdata, web
from axbranch.state import Store
from tests import test_engine as TE
from tests.test_engine import Script

REAL = os.name == 'nt' and I.available()[0]
FIXTURE = Path(__file__).parent / 'fixtures' / 'owner_data_app'
APP = (FIXTURE / 'v1_inventory_app.py').read_text(encoding='utf-8')
DATA = {'needed': True, 'formats': ['.json'], 'schema_version': 1, 'compatible_from': 1,
        'write': {'http_method': 'POST', 'http_path': '/update', 'http_body': 'item={marker}&qty=3',
                  'http_headers': ['Content-Type: application/x-www-form-urlencoded']},
        'read': {'http_path': '/', 'expect_contains': ['{marker}']}}
SPEC = {'mode': 'web', 'owner_launch': 'double-click inventory_app.py', 'launch_args': ['--port', '{port}'],
        'probes': [], 'data': DATA}


class NormalizeTests(unittest.TestCase):
    def test_contract_is_normalized_and_never_widened(self):
        spec, _ = runtime.normalize({**SPEC, 'data': {**DATA, 'formats': ['json', '.exe', '.py'], 'compatible_from': 9}})
        d = spec['data']
        self.assertEqual((d['formats'], d['dir'], d['compatible_from']), (['.json'], 'data', 1))
        self.assertNotIn('invalid', d)
        no_marker, notes = runtime.normalize({**SPEC, 'data': {**DATA, 'write': {**DATA['write'], 'http_body': 'item=x'}}})
        self.assertIn('data.write must carry {marker}', no_marker['data']['invalid'])
        self.assertTrue(notes)
        self.assertEqual(runtime.normalize({'mode': 'web', 'launch_args': ['--port', '{port}']})[0]['data'], {'needed': False})
        self.assertEqual(runtime.normalize({**SPEC, 'mode': 'cli'})[0]['data'], {'needed': False})   # web programs only


class RoundTripTests(unittest.TestCase):
    """Verification executes the contract (not isolated here; the isolated path is covered by the flow test)."""
    def check(self, app_text, spec=SPEC):
        work = Path(tempfile.mkdtemp(prefix='axb-dc-'))
        (work / 'inventory_app.py').write_text(app_text, encoding='utf-8')
        (work / 'inputs').mkdir()
        shutil.copyfile(FIXTURE / 'inventory.csv', work / 'inputs' / 'inventory.csv')
        try:
            return runtime.check(spec, 'inventory_app.py', sys.executable, str(work))
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def steps(self, ev):
        return {s['name']: s for s in ev['steps'] if s['name'].startswith('data:')}

    def test_a_program_that_keeps_its_data_passes(self):
        ev = self.check(APP)
        data = self.steps(ev)
        self.assertEqual(len(data), 3, data)
        self.assertTrue(all(s['ok'] for s in data.values()), data)
        self.assertEqual(data['data: kept under ./data/ by the runner']['files'], ['data/inventory.json'])

    def test_data_outside_the_contract_fails_even_if_declared(self):
        outside = APP.replace("DATA_PATH = os.path.join('data', 'inventory.json')", "DATA_PATH = 'store.json'")
        outside = outside.replace("    os.makedirs('data', exist_ok=True)\n", '')
        ev = self.check(outside)
        self.assertFalse(ev['ok'])
        self.assertFalse(self.steps(ev)['data: kept under ./data/ by the runner']['ok'])

    def test_an_unverifiable_declaration_fails(self):
        ev = self.check(APP, {**SPEC, 'data': {**DATA, 'read': {'http_path': '/', 'expect_contains': ['재고']}}})
        self.assertFalse(ev['ok'])
        self.assertIn('data: contract', [s['name'] for s in ev['steps']])


class PlannedWebApp(Script):
    """CEO plans a web app WITH a data contract; the producer's output is the fixture (a stand-in for generated code)."""
    def __call__(self, prompt, schema, *args, **kw):
        result, used, notes = super().__call__(prompt, schema, *args, **kw)
        if schema is E.PLAN:
            result.update(artifact_kind='python', artifact_filename='inventory_app.py', runtime=SPEC,
                          acceptance_criteria=['shows the inventory and keeps quantities the Owner changes'])
        return result, used, notes


@unittest.skipUnless(REAL, 'AppContainer backend not available on this machine')
class PlanToRunnerTests(unittest.TestCase):
    setUp, tearDown, engine = TE.EngineTests.setUp, TE.EngineTests.tearDown, TE.EngineTests.engine

    def test_contract_flows_from_plan_to_producer_to_verification_to_runner(self):
        script = PlannedWebApp([APP], ['PASS'])
        eng = self.engine(script)
        pid = self.store.new_project('작은 매장 재고 웹앱; 바꾼 수량은 다음에도 남아 있어야 함')
        eng.attach_inputs(pid, [str(FIXTURE / 'inventory.csv')])
        p = eng.run(pid)
        self.assertEqual(p['state'], 'OWNER_REVIEW', p.get('pause_reason'))
        build = next(pr for s, _, pr in script.prompts if s is E.BUILD)
        self.assertIn('"compatible_from": 1', build)                           # the producer received the contract
        self.assertIn('{marker}', build)
        v = self.store.verifications(pid)[-1]
        steps = {s['name']: s for s in v['checks']['runtime']['steps']}
        self.assertTrue(steps['data: restored into a fresh copy and read back after restart']['ok'])   # executed, isolated
        self.assertTrue(all(m['backend'] == 'appcontainer' for m in v['checks']['runtime']['isolation']))
        # The runner honours the same contract: save in one run, restore in the next.
        app, httpd = web.serve(self.tmp / 'ws', 0, launcher=lambda *a: None,
                               engine_factory=lambda: E.Engine(Store(self.tmp / 'ws' / 'axbranch.sqlite3'),
                                                               workspace=self.tmp / 'ws', vault=self.tmp / 'v',
                                                               gai_db=self.tmp / 'x', llm=None))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            r = web.project_action(app, self.store, pid, 'result', {}, 'web')
            self.assertTrue(r['data_kept'])
            body = b'item=%EC%9E%90%EB%8F%99%EC%A0%80%EC%9E%A5&qty=8'          # "자동저장"
            urllib.request.urlopen(urllib.request.Request(r['url'] + 'update', data=body, method='POST'), timeout=15).read()
            web.project_action(app, self.store, pid, 'result-stop', {}, 'web')
            snap = userdata.current(self.tmp / 'ws' / 'projects' / pid)
            self.assertEqual((snap['data_schema'], snap['contract']['formats']), (1, ['.json']))
            again = web.project_action(app, self.store, pid, 'result', {}, 'web')
            self.assertIn('자동저장', urllib.request.urlopen(again['url'], timeout=15).read().decode('utf-8'))
        finally:
            app.owner_runs.stop_all()
            httpd.shutdown()
            httpd.server_close()


if __name__ == '__main__':
    unittest.main()
