"""Local web UI server: loopback only, token/Host/Origin checks, the same Owner actions as the window,
no duplicate project on a repeated submit, reading never launches work, Owner memos survive status updates."""
import json
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from axbranch import web
from axbranch.state import Store


class WebTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.ws = self.tmp / 'ws'
        self.ws.mkdir()
        Store(self.ws / 'axbranch.sqlite3').close()
        self.devroom = self.tmp / 'status.json'
        self.devroom.write_text(json.dumps({'version': 'x', 'items': []}), encoding='utf-8')
        self.launched = []
        self.app, self.httpd = web.serve(self.ws, 0, launcher=lambda ws, pid: self.launched.append(pid),
                                         engine_factory=self._no_engine, devroom=self.devroom)
        self.port = self.app.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _no_engine(self):
        raise AssertionError('no engine (model) may be opened in these tests')

    def call(self, path, body=None, headers=None, token=True):
        h = {'Host': f'127.0.0.1:{self.port}'}
        if token:
            h['X-AXB-Token'] = self.app.token
        h.update(headers or {})
        data = None if body is None else json.dumps(body).encode()
        if data is not None:
            h['Content-Type'] = 'application/json'
        req = urllib.request.Request(f'http://127.0.0.1:{self.port}{path}', data=data, headers=h,
                                     method='POST' if data is not None else 'GET')
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read() or b'{}') if 'json' in r.headers.get('Content-Type', '') else r.read()
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b'{}')

    def test_binds_loopback_and_rejects_foreign_pages(self):
        self.assertEqual(self.httpd.server_address[0], '127.0.0.1')
        self.assertEqual(self.call('/api/overview', token=False)[0], 403)                   # no token
        self.assertEqual(self.call('/api/overview', headers={'X-AXB-Token': 'guess'})[0], 403)
        self.assertEqual(self.call('/api/overview', headers={'Origin': 'https://evil.example'})[0], 403)
        self.assertEqual(self.call('/api/overview', headers={'Host': 'evil.example:80'})[0], 403)   # DNS rebinding
        code, _ = self.call('/api/projects', {'goal': 'x', 'request_id': 'abcdefgh1'}, headers={'Origin': 'http://evil.example'})
        self.assertEqual(code, 403)
        req = urllib.request.Request(f'http://127.0.0.1:{self.port}/api/projects', method='OPTIONS',
                                     headers={'Origin': 'https://evil.example', 'Access-Control-Request-Method': 'POST'})
        with self.assertRaises(urllib.error.HTTPError) as cm:                                 # no CORS preflight grant
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(cm.exception.code, 403)
        self.assertEqual(self.launched, [])
        code, page = self.call('/', token=False)
        self.assertEqual(code, 200)
        self.assertIn(self.app.token.encode(), page)                                          # only our own page has it

    def test_sidebar_uses_saved_title_without_rewriting_original_goal(self):
        broken_goal = '泥⑤???寃 검증?? CSV'
        store = self.app.store()
        try:
            pid = store.new_project(broken_goal)
            store.update(pid, plan={'title': '검증 실패 원인 메모'})
            before = store.project(pid)
            _, overview = self.call('/api/overview')
            row = next(p for p in overview['projects'] if p['id'] == pid)
            self.assertEqual(row['title'], '검증 실패 원인 메모')
            self.assertEqual(store.project(pid), before)
            self.assertEqual(row['goal'], broken_goal)
            self.assertEqual(self.launched, [])
        finally:
            store.close()

    def test_create_is_idempotent_and_launches_once(self):
        body = {'goal': '팀별 문의 집계', 'departments': ['research'], 'request_id': 'req-0001-abcd'}
        code, first = self.call('/api/projects', body)
        self.assertEqual((code, first['created']), (200, True))
        code, again = self.call('/api/projects', body)                                       # reload / double submit
        self.assertEqual((again['id'], again['created']), (first['id'], False))
        self.assertEqual(self.launched, [first['id']])
        s = Store(self.ws / 'axbranch.sqlite3')
        try:
            self.assertEqual(len(s.projects()), 1)
            self.assertEqual([e['detail']['channel'] for e in s.events(first['id'], {'owner_action'})], ['web'])
        finally:
            s.close()
        self.assertEqual(self.call('/api/projects', {'goal': 'x'})[0], 400)                   # request id required
        self.assertEqual(self.call('/api/projects', {'goal': ' ', 'request_id': 'req-0002-abcd'})[0], 400)

    def test_reading_never_launches_or_opens_an_engine(self):
        _, p = self.call('/api/projects', {'goal': 'g', 'request_id': 'req-0003-abcd'})
        self.launched.clear()
        for path in ('/api/overview', f"/api/project/{p['id']}", f"/api/project/{p['id']}/records?key=ceo",
                     '/api/feeds', '/api/devroom'):
            code, _ = self.call(path)
            self.assertEqual(code, 200, path)
        self.assertEqual(self.launched, [])

    def test_departments_attach_detach_persist_and_refuse_duplicates(self):
        _, p = self.call('/api/projects', {'goal': 'g', 'request_id': 'req-0004-abcd'})
        url = f"/api/project/{p['id']}/department"
        self.assertEqual([d['id'] for d in self.call(url, {'action': 'attach', 'id': 'research'})[1]['attached']], ['research'])
        code, err = self.call(url, {'action': 'attach', 'id': 'research'})
        self.assertEqual(code, 400)
        self.assertIn('이미 연결된 부서', err['error'])
        self.call(url, {'action': 'attach', 'id': 'operations'})
        self.call(url, {'action': 'detach', 'id': 'research'})
        _, view = self.call(f"/api/project/{p['id']}")                                       # read back from the store
        self.assertEqual([d['id'] for d in view['attached']], ['operations'])
        self.assertEqual(self.call(url, {'action': 'attach', 'id': 'payments'})[0], 400)

    def test_stop_and_resume_use_the_shared_actions(self):
        _, p = self.call('/api/projects', {'goal': 'g', 'request_id': 'req-0005-abcd'})
        self.launched.clear()
        self.assertEqual(self.call(f"/api/project/{p['id']}/stop", {})[0], 200)
        s = Store(self.ws / 'axbranch.sqlite3')
        try:
            self.assertEqual(s.project(p['id'])['state'], 'PAUSED')
        finally:
            s.close()
        self.call(f"/api/project/{p['id']}/resume", {})
        self.assertEqual(self.launched, [p['id']])

    def test_devroom_notes_survive_status_updates_and_settings_persist(self):
        notes = [{'id': '1', 'text': '드래그가 느림', 'at': 1}]
        self.assertEqual(self.call('/api/devroom/notes', {'notes': notes})[1]['notes'][0]['text'], '드래그가 느림')
        self.devroom.write_text(json.dumps({'version': 'y', 'items': []}), encoding='utf-8')    # a status update
        _, data = self.call('/api/devroom')
        self.assertEqual((data['status']['version'], data['notes'][0]['text']), ('y', '드래그가 느림'))
        self.call('/api/settings', {'motion_off': True, 'low_power': True})
        self.assertEqual(json.loads((self.ws / 'settings.json').read_text(encoding='utf-8')),
                         {'motion_off': True, 'low_power': True})

    def test_the_shipped_devroom_record_is_well_formed(self):
        status = json.loads(web.DEVROOM.read_text(encoding='utf-8'))
        for key in ('version', 'branch', 'commit', 'updated_at', 'now', 'current_work', 'next', 'owner_todo', 'recent', 'areas', 'items', 'issues', 'changelog'):
            self.assertIn(key, status)
        impl, verify = {'계획', '개발 중', '구현 완료', '보류'}, {'미검증', '자동 테스트 확인', '실제 E2E 확인', 'Owner 확인'}
        for item in status['items']:
            self.assertIn(item['impl'], impl, item['id'])
            self.assertIn(item['verify'], verify, item['id'])
        self.assertNotRegex(json.dumps(status, ensure_ascii=False), r'\d+\s*%\s*완성')       # no unfounded completion %
        self.assertTrue({p['source'] for p in status['next']} <= {'owner', 'dev'})
        self.assertLessEqual(len(status['recent']), 3)
        cats = {'현재 문제', 'Owner 확인', '해결·과거 기록'}
        for i in status['issues']:                                                   # every card answers who/what/when
            self.assertIn(i['category'], cats, i['id'])
            self.assertIn(i['owner'], {'개발 담당', 'Owner'}, i['id'])
            for k in ('title', 'impact', 'status', 'priority', 'next', 'checked', 'history'):
                self.assertTrue(i.get(k), (i['id'], k))
        self.assertEqual(len({i['id'] for i in status['issues']}), len(status['issues']))   # one record per problem


    def test_a_running_worker_is_never_started_twice(self):
        from unittest import mock
        from axbranch import actions
        _, p = self.call('/api/projects', {'goal': 'g', 'request_id': 'req-0006-abcd'})
        self.launched.clear()
        with mock.patch('axbranch.supervisor.status', return_value={'status': 'ACTIVE'}):
            s = Store(self.ws / 'axbranch.sqlite3')
            try:
                self.assertFalse(actions.launch(self.ws, s, p['id'], lambda ws, pid: self.launched.append(pid)))
            finally:
                s.close()
            self.call(f"/api/project/{p['id']}/resume", {})                          # reconnect + resume
        self.assertEqual(self.launched, [])

    def test_library_and_develop_use_the_engine_once_per_request(self):
        made = []

        class FakeEngine:                       # stands in for engine.develop (no model in these tests)
            def __init__(self, ws):
                self.store = Store(ws / 'axbranch.sqlite3')

            def develop(self, base, goal):
                pid = self.store.new_project(goal)
                made.append((base, goal, pid))
                return pid
        self.app.engine_factory = lambda: FakeEngine(self.ws)
        _, base = self.call('/api/projects', {'goal': 'base', 'request_id': 'req-0007-abcd'})
        code, lib = self.call('/api/library')
        self.assertEqual(code, 200)
        self.assertIn('types', lib)
        self.launched.clear()
        body = {'base': base['id'], 'goal': '검색 기능 추가', 'request_id': 'dev-0001-abcd'}
        code, first = self.call('/api/develop', body)
        self.assertEqual((code, first['created']), (200, True))
        _, again = self.call('/api/develop', body)                                   # reload / double click
        self.assertEqual((again['id'], again['created']), (first['id'], False))
        self.assertEqual(len(made), 1)
        self.assertEqual(self.launched, [first['id']])
        self.assertEqual(self.call('/api/develop', {'base': base['id'], 'goal': ' ', 'request_id': 'dev-0002-abcd'})[0], 400)

if __name__ == '__main__':
    unittest.main()
