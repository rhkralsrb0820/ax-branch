"""Owner data kept across runs and code versions (userdata.py + owner_runs.py), on the real AppContainer backend with
the fixed developer test app in tests/fixtures/owner_data_app (NOT AI-produced; see its README)."""
import hashlib
import json
import os
import shutil
import socket
import sqlite3
import tempfile
import threading
import time
import unittest
import urllib.parse
import urllib.request
from pathlib import Path

from axbranch import engine as E, isolation as I, owner_runs, runtime, userdata, web
from axbranch.state import Rejected, Store

REAL = os.name == 'nt' and I.available()[0]
FIXTURE = Path(__file__).parent / 'fixtures' / 'owner_data_app'
SPEC = {'mode': 'web', 'owner_launch': 'double-click inventory_app.py', 'launch_args': ['--port', '{port}'], 'probes': []}


def page(url):
    return urllib.request.urlopen(url, timeout=15).read().decode('utf-8')


def update(url, item, qty):
    body = urllib.parse.urlencode({'item': item, 'qty': qty}).encode()
    urllib.request.urlopen(urllib.request.Request(url + 'update', data=body, method='POST'), timeout=15).read()


class DataContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='axb-userdata-'))
        self.run = self.tmp / 'run'
        (self.run / 'data' / 'sub').mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_only_contract_files_are_saved(self):
        d = self.run / 'data'
        (d / 'items.json').write_text('[1]', encoding='utf-8')
        (d / 'sub' / 'notes.txt').write_text('메모', encoding='utf-8')
        for bad in ('tool.exe', 'script.py', 'run.bat', 'api_token.txt', '.env', 'lib.dll'):
            (d / bad).write_text('x', encoding='utf-8')
        (self.run / 'outside.json').write_text('{}', encoding='utf-8')          # outside ./data
        files, skipped = userdata.collect(self.run)
        self.assertEqual(files, [('data/items.json', 'json'), ('data/sub/notes.txt', 'text')])
        self.assertTrue(any('credential' in s for s in skipped))
        snap = userdata.snapshot(self.tmp / 'proj', self.run, {'iteration': 1, 'sha256': 'a'}, 'test')
        self.assertEqual([f['path'] for f in snap['files']], ['data/items.json', 'data/sub/notes.txt'])

    def test_live_sqlite_uses_the_backup_api_and_bad_files_never_replace_good_data(self):
        db = self.run / 'data' / 'shop.db'
        con = sqlite3.connect(db)
        con.execute('PRAGMA journal_mode=WAL')
        con.execute('CREATE TABLE t(x)')
        con.execute('INSERT INTO t VALUES (1)')
        con.commit()                                   # the "program" keeps the connection open (a live database)
        first = userdata.snapshot(self.tmp / 'proj', self.run, {'iteration': 1, 'sha256': 'a'}, 'live')
        copy = sqlite3.connect(Path(first['folder']) / 'files' / 'data' / 'shop.db')
        self.assertEqual(copy.execute('SELECT x FROM t').fetchall(), [(1,)])
        copy.close()
        con.close()
        (self.run / 'data' / 'broken.json').write_text('{"half": ', encoding='utf-8')   # caught mid-write
        with self.assertRaises(userdata.SaveFailed):
            userdata.snapshot(self.tmp / 'proj', self.run, {'iteration': 1, 'sha256': 'a'}, 'bad')
        self.assertEqual(userdata.current(self.tmp / 'proj')['snapshot'], first['snapshot'])   # last good kept
        self.assertFalse(list((self.tmp / 'proj' / 'userdata').glob('.staging-*')))

    def test_damaged_pointer_or_snapshot_falls_back_and_restore_stays_in_data(self):
        (self.run / 'data' / 'a.json').write_text('[1]', encoding='utf-8')
        one = userdata.snapshot(self.tmp / 'proj', self.run, {'iteration': 1, 'sha256': 'a'}, 's1')
        (self.run / 'data' / 'a.json').write_text('[2]', encoding='utf-8')
        two = userdata.snapshot(self.tmp / 'proj', self.run, {'iteration': 1, 'sha256': 'a'}, 's2')
        (Path(two['folder']) / 'files' / 'data' / 'a.json').write_text('[999]', encoding='utf-8')   # damaged
        self.assertEqual(userdata.current(self.tmp / 'proj')['snapshot'], one['snapshot'])
        tampered = dict(one, files=[{'path': '../evil.json', 'sha256': one['files'][0]['sha256']}])
        with self.assertRaises(userdata.SaveFailed):
            userdata.restore(tampered, self.tmp / 'new-run')

    def test_old_code_versions_keep_their_last_snapshot(self):
        (self.run / 'data' / 'a.json').write_text('[0]', encoding='utf-8')
        old = userdata.snapshot(self.tmp / 'proj', self.run, {'iteration': 1, 'sha256': 'v1'}, 'v1 data')
        for n in range(1, userdata.KEEP + 3):
            (self.run / 'data' / 'a.json').write_text(f'[{n}]', encoding='utf-8')
            userdata.snapshot(self.tmp / 'proj', self.run, {'iteration': 3, 'sha256': 'v3'}, 'v3 data')
        self.assertTrue(Path(old['folder']).exists())


@unittest.skipUnless(REAL, 'AppContainer backend not available on this machine')
class OwnerDataFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='axb-owner-data-'))
        self.ws = self.tmp / 'ws'
        self.store = Store(self.ws / 'axbranch.sqlite3')
        self.app, self.httpd = web.serve(self.ws, 0, launcher=lambda *a: None, engine_factory=self.engine)
        self.app.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self._interval = userdata.SAVE_INTERVAL

    def tearDown(self):
        userdata.SAVE_INTERVAL = self._interval
        self.app.owner_runs.stop_all()
        self.httpd.shutdown()
        self.httpd.server_close()
        self.store.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def engine(self):
        return E.Engine(Store(self.ws / 'axbranch.sqlite3'), workspace=self.ws, vault=self.tmp / 'v',
                        gai_db=self.tmp / 'x', llm=None)

    def project(self, name='매장'):
        pid = self.store.new_project(f'synthetic inventory {name}')
        plan = {'artifact_filename': 'inventory_app.py', 'artifact_kind': 'python', 'acceptance_criteria': ['x'],
                'runtime': SPEC, 'pipeline': []}
        self.store.update(pid, plan=plan)
        eng = self.engine()
        eng.attach_inputs(pid, [str(FIXTURE / 'inventory.csv')])
        eng.store.close()
        return pid

    def version(self, pid, fixture):
        it = len(self.store.artifacts(pid)) + 1
        folder = self.ws / 'projects' / pid / 'artifacts' / f'v{it}'
        folder.mkdir(parents=True)
        path = folder / 'inventory_app.py'
        shutil.copyfile(FIXTURE / fixture, path)
        self.store.update(pid, iteration=it)
        aid = self.store.add_artifact(pid, it, path, hashlib.sha256(path.read_bytes()).hexdigest(), 'python', None)
        self.store.add_verification(pid, aid, it, 'PASS', {'verdict': 'PASS', 'findings': []}, {'ok': True}, 'codex')
        return path

    def act(self, pid, action, **body):
        return web.project_action(self.app, self.store, pid, action, body, 'web')

    def test_use_save_stop_reopen_and_keep_data_on_a_revised_version(self):
        pid = self.project()
        v1 = self.version(pid, 'v1_inventory_app.py')
        r = self.act(pid, 'result')
        self.assertIsNone(r['restored'])
        update(r['url'], '빨대', 40)                                           # the Owner enters data
        saved = self.act(pid, 'result-save')
        self.assertEqual(saved['last_saved']['data_version'], 1)
        self.act(pid, 'result-stop')
        status = self.app.project(self.store, pid)['owner_web_run']
        self.assertFalse(status['running'])
        self.assertEqual(status['last_saved']['code_iteration'], 1)
        again = self.act(pid, 'result')                                       # reopen: data restored
        self.assertEqual(again['restored']['data_version'], 1)
        self.assertIn('>40<', page(again['url']).replace(' ', ''))
        self.act(pid, 'result-stop')
        self.version(pid, 'v2_inventory_app.py')                               # fixed revised code version
        r2 = self.act(pid, 'result')
        html = page(r2['url'])
        self.assertIn('수정 버전 v2', html)
        self.assertIn('>40<', html.replace(' ', ''))                            # data kept on the new version
        self.assertEqual((r2['version'], r2['restored']['code_iteration']), (2, 1))
        update(r2['url'], '종이컵', 99)
        self.act(pid, 'result-stop')
        snap = userdata.current(self.ws / 'projects' / pid)
        self.assertEqual((snap['code_version']['iteration'], snap['data_version']), (2, 2))   # unchanged stops add none
        self.assertEqual(hashlib.sha256(v1.read_bytes()).hexdigest(),          # the verified artifact is untouched
                         hashlib.sha256((FIXTURE / 'v1_inventory_app.py').read_bytes()).hexdigest())

    def test_periodic_save_survives_an_abnormal_ax_branch_end(self):
        userdata.SAVE_INTERVAL = 1
        pid = self.project()
        self.version(pid, 'v1_inventory_app.py')
        r = self.act(pid, 'result')
        update(r['url'], '냅킨', 7)
        deadline = time.time() + 15
        while time.time() < deadline and not self.app.owner_runs.runs[pid].get('last_saved'):
            time.sleep(0.5)
        run = self.app.owner_runs.runs.pop(pid)                                # AX Branch "dies": no stop, no final save
        run['stopped'].set()
        run['proc'].stop()
        run['proc'].cleanup()
        fresh = owner_runs.OwnerRuns(self.app.store)                           # a restarted AX Branch
        self.app.owner_runs = fresh
        back = self.act(pid, 'result')
        self.assertEqual(back['restored']['snapshot'], run['last_saved']['snapshot'])
        self.assertIn('>7<', page(back['url']).replace(' ', ''))

    def test_a_failed_save_keeps_the_last_good_data_and_says_so(self):
        pid = self.project()
        self.version(pid, 'v1_inventory_app.py')
        r = self.act(pid, 'result')
        update(r['url'], '뚜껑', 11)
        good = self.act(pid, 'result-save')['last_saved']['snapshot']
        (self.app.owner_runs.runs[pid]['cwd'] / 'data' / 'inventory.json').write_text('[{"item": ', encoding='utf-8')
        with self.assertRaises(Rejected) as failed:
            self.act(pid, 'result-save')
        self.assertIn('마지막 정상 데이터', str(failed.exception))
        self.assertEqual(userdata.current(self.ws / 'projects' / pid)['snapshot'], good)
        self.assertTrue(self.app.owner_runs.status(pid)['save_error'])
        self.assertTrue(self.store.events(pid, {'owner_data_save_failed'}))

    def test_incompatible_revision_never_overwrites_data_and_offers_choices(self):
        pid = self.project()
        self.version(pid, 'v1_inventory_app.py')
        r = self.act(pid, 'result')
        update(r['url'], '빨대', 40)
        self.act(pid, 'result-stop')
        before = userdata.current(self.ws / 'projects' / pid)
        self.version(pid, 'v3_incompatible_inventory_app.py')
        answer = self.act(pid, 'result')
        self.assertTrue(answer['incompatible'])
        self.assertEqual([o['choice'] for o in answer['options']], ['previous', 'empty'])
        self.assertEqual(userdata.current(self.ws / 'projects' / pid)['snapshot'], before['snapshot'])
        self.assertNotIn(pid, self.app.owner_runs.runs)
        prev = self.act(pid, 'result', choice='previous')                     # the older version with the data
        self.assertEqual(prev['version'], 1)
        self.assertIn('>40<', page(prev['url']).replace(' ', ''))
        self.act(pid, 'result-stop')
        empty = self.act(pid, 'result', choice='empty')                       # the new version, empty data
        self.assertEqual((empty['version'], empty['restored']), (2, None))
        self.act(pid, 'result-stop')
        self.assertTrue(Path(before['folder']).exists())                       # the v1 data is still kept

    def test_projects_never_share_data(self):
        a, b = self.project('A'), self.project('B')
        self.version(a, 'v1_inventory_app.py')
        self.version(b, 'v1_inventory_app.py')
        ra = self.act(a, 'result')
        update(ra['url'], 'A전용', 1)
        self.act(a, 'result-stop')
        rb = self.act(b, 'result')
        self.assertIsNone(rb['restored'])
        self.assertNotIn('A전용', page(rb['url']))

    def test_port_conflict_retry_announced_port_and_reserved_port(self):
        pid = self.project()
        self.version(pid, 'v1_inventory_app.py')
        busy = socket.socket()
        busy.bind(('127.0.0.1', 0))
        busy.listen(1)
        busy_port = busy.getsockname()[1]
        real_free = runtime.free_port
        ports = iter([busy_port])
        runtime.free_port = lambda: next(ports, None) or real_free()           # first attempt gets a busy port
        try:
            r = self.act(pid, 'result')
        finally:
            runtime.free_port = real_free
            busy.close()
        self.assertIn('매장 재고 현황', page(r['url']))                        # served after retrying on a free port
        self.assertNotEqual(self.app.owner_runs.runs[pid]['program_port'], busy_port)
        self.act(pid, 'result-stop')


if __name__ == '__main__':
    unittest.main()
