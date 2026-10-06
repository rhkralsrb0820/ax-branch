"""Local visibility from scripted SQLite state and real supervisor locks."""
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from axbranch import live
from axbranch.state import Store, run_lock


class LiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.ws = Path(self.temp.name)
        self.store = Store(self.ws / 'axbranch.sqlite3')
        self.addCleanup(self.store.close)
        self.pid = self.store.new_project('A visible execution ' * 10)
        self.folder = self.ws / 'projects' / self.pid
        self.folder.mkdir(parents=True)
        self.store.update(self.pid, plan={'pipeline': [
            {'agent_role': 'Builder', 'provider': 'codex'}]})
        for state in ('PLANNING', 'STAFFING', 'EXECUTING'):
            self.store.set_state(self.pid, state)
        self.beat('call Builder (codex)')

    def beat(self, detail):
        (self.folder / 'HEARTBEAT.json').write_text(json.dumps({
            'at': time.time(), 'os_pid': os.getpid(), 'detail': detail,
            'state': self.store.project(self.pid)['state']}), encoding='utf-8')

    def start(self):
        self.store.event(self.pid, 'call_start', who='Builder', preferred='codex')
        (self.folder / 'ACTIVITY.json').write_text(json.dumps({
            'agent': 'Builder', 'provider': 'codex', 'pid': 12345,
            'elapsed': 751, 'idle': 2, 'started_at': time.time() - 751}), encoding='utf-8')

    def view(self):
        return live.view(self.ws, self.store, self.pid)

    def row(self, view, title):
        return next(row for row in view['pipeline'] if row['title'] == title)

    def verify(self, verdict='FAIL', ok=False):
        self.store.add_verification(self.pid, '', 1, verdict, {}, {
            'runtime': {'ok': ok, 'steps': [{'ok': True}, {'ok': ok}]}}, 'claude')

    def test_agent_card_why_and_explicit_records(self):
        self.store.update(self.pid, plan_version=1, plan={'interpretation': 'build it', 'pipeline': [
            {'agent_role': 'Analyst', 'provider': 'claude', 'name': 'analysis', 'why': 'knows the domain',
             'instructions': 'analyse'},
            {'agent_role': 'Builder', 'provider': 'codex', 'name': 'build', 'why': 'writes the code',
             'instructions': 'build'}]})
        self.store.save_output(self.pid, 1, 1, 0, None, 'claude', {
            'output': 'Use the official API', 'key_points': ['official source'],
            'evidence': ['documented, free'], 'counterpoints': ['rate limits: cached for 10 min']})
        self.store.event(self.pid, 'call', who='Analyst', provider='claude', seconds=266)
        v = self.view()
        card = next(r for r in v['pipeline'] if r['key'] == 'stage:0')
        self.assertEqual((card['mark'], card['why'], card['result']), ('✓', 'knows the domain', 'official source'))
        text = live.records(self.store, self.pid, 'stage:0')
        for part in ('고용 이유 (Why hired): knows the domain', 'Use the official API', '근거 (Evidence)',
                     'documented, free', '반론 · 위험 (Counterargument)', 'rate limits: cached for 10 min'):
            self.assertIn(part, text)
        self.assertIn('Analyst (Claude): knows the domain', live.records(self.store, self.pid, 'ceo'))

    def test_active_call(self):
        self.start()
        with run_lock(self.folder / 'run.lock'):
            v = self.view()
        h = dict(v['header'])
        self.assertEqual(self.row(v, 'Builder')['mark'], '●')
        self.assertEqual(h['에이전트 / 역할'], 'Builder')
        self.assertEqual(h['엔진'], 'Codex')
        self.assertEqual(h['provider pid'], '12345')
        self.assertEqual(h['현재 작업'], 'Builder on Codex')
        self.assertTrue(h['경과 / 제한'].startswith('12m 31s / '))
        self.assertLessEqual(len(h['목표']), 120)
        self.assertEqual([k for k, _ in v['header']], [
            '프로젝트', '목표', '단계', '상태', '에이전트 / 역할', '엔진', 'worker pid',
            'provider pid', '현재 작업', '경과 / 제한', '마지막 활동', '산출물', '복구 횟수', '다음 작업'])
        self.assertTrue(all(isinstance(value, str) for _, value in v['header']))

    def test_stale_execution_is_interrupted(self):
        self.start()
        v = self.view()
        h = dict(v['header'])
        self.assertNotIn('●', [r['mark'] for r in v['pipeline']])
        self.assertEqual(self.row(v, 'Builder')['detail'], 'interrupted — STALLED')
        self.assertEqual(self.row(v, 'Builder')['mark'], '!')
        self.assertEqual(h['에이전트 / 역할'], '마지막: Builder')
        self.assertEqual(h['provider pid'], '-')
        self.assertEqual(h['경과 / 제한'], '-')
        self.assertTrue(h['현재 작업'].startswith('없음'))

    def test_call_finishes_during_status_refresh(self):
        self.start()
        self.store.set_state(self.pid, 'VERIFYING')
        self.beat('runtime: checking launch')
        read = live.supervisor._read

        def finish_after_read(path):
            data = read(path)
            if path.name == 'ACTIVITY.json':
                path.unlink()
            return data

        with run_lock(self.folder / 'run.lock'):
            with mock.patch('axbranch.supervisor._read', side_effect=finish_after_read):
                v = self.view()
        h = dict(v['header'])
        self.assertTrue(h['상태'].startswith('ACTIVE'))
        self.assertEqual(h['provider pid'], '-')
        self.assertEqual(h['경과 / 제한'], '-')
        self.assertEqual(h['현재 작업'], 'LOCAL — Runtime acceptance: checking launch')
        self.assertIn('━ 파이프라인 ━', live.render(v))

    def test_hiring_and_completed_duration(self):
        self.store.add_agent(self.pid, 'Builder', 'codex')
        self.store.event(self.pid, 'call_start', who='Builder', preferred='codex')
        self.store.event(self.pid, 'call', who='Builder', seconds=266, provider='codex')
        v = self.view()
        text = live.render(v)
        self.assertIn('→ hired Builder', text)
        self.assertIn('Assigned engine: Codex', text)
        self.assertIn('Completed · 4m 26s', text)
        self.assertEqual(self.row(v, 'Builder')['mark'], '✓')
        self.assertLess(text.index('started · Codex'), text.index('completed · 4m 26s'))

    def test_failed_verification_and_rejected_build(self):
        self.store.event(self.pid, 'call', who='Builder', seconds=59, provider='codex')
        self.store.event(self.pid, 'build_rejected', reason='empty build')
        self.verify()
        v = self.view()
        self.assertEqual(self.row(v, 'Builder')['mark'], '✗')
        self.assertEqual(self.row(v, 'Builder')['detail'], 'no deliverable: empty build')
        self.assertEqual(self.row(v, 'Verification Agent')['mark'], '✗')
        self.assertEqual(self.row(v, 'Verification Agent')['detail'], 'FAIL · Claude')
        self.assertEqual(self.row(v, 'Runtime Acceptance (LOCAL)')['mark'], '✗')
        self.assertEqual(self.row(v, 'Runtime Acceptance (LOCAL)')['detail'], '1 / 2 checks passed')

    def test_owner_review(self):
        self.store.set_state(self.pid, 'VERIFYING')
        self.store.set_state(self.pid, 'OWNER_REVIEW')
        self.assertEqual(self.row(self.view(), 'OWNER_REVIEW')['mark'], '●')
        self.store.set_state(self.pid, 'PENDING_CLOSE')
        self.assertEqual(self.row(self.view(), 'OWNER_REVIEW')['mark'], '✓')

    def test_active_runtime_without_provider_call(self):
        self.store.set_state(self.pid, 'VERIFYING')
        self.beat('runtime: checking launch')
        with run_lock(self.folder / 'run.lock'):
            v = self.view()
        h = dict(v['header'])
        self.assertEqual(h['현재 작업'], 'LOCAL — Runtime acceptance: checking launch')
        self.assertEqual(h['경과 / 제한'], '-')
        self.assertEqual(h['provider pid'], '-')
        self.assertEqual(self.row(v, 'Runtime Acceptance (LOCAL)')['mark'], '●')
        self.assertEqual(self.row(self.view(), 'Runtime Acceptance (LOCAL)')['mark'], '○')

    def test_no_llm_or_state_changes(self):
        self.start()
        before = self.store.events(self.pid)
        files = {p.name: p.read_bytes() for p in self.folder.iterdir()}
        with mock.patch('axbranch.providers.call', side_effect=AssertionError('LLM forbidden')):
            with run_lock(self.folder / 'run.lock'):
                self.assertIn('AI 호출 없음', live.render(self.view()))
        self.assertEqual(self.store.events(self.pid), before)
        for name, contents in files.items():
            self.assertEqual((self.folder / name).read_bytes(), contents)

    def test_new_round_excludes_old_results_but_keeps_ceo_decision(self):
        self.store.event(self.pid, 'decision', by='claude', what='plan v1')
        self.store.event(self.pid, 'decision', by='engine', what='internal')
        self.store.event(self.pid, 'call', who='Builder', provider='codex', seconds=60)
        self.store.event(self.pid, 'build_rejected', reason='old rejection')
        self.verify()
        self.store.set_state(self.pid, 'REWORK')
        self.store.set_state(self.pid, 'STAFFING')
        v = self.view()
        self.assertEqual(self.row(v, '淸月 CEO')['detail'], 'plan v1')
        for title in ('Builder', 'Verification Agent', 'Runtime Acceptance (LOCAL)'):
            self.assertEqual(self.row(v, title)['mark'], '○')

    def test_retry_failure_and_verification_call(self):
        self.start()
        self.store.event(self.pid, 'call_failed', who='Builder', error='x' * 100)
        self.assertEqual(self.row(self.view(), 'Builder')['detail'], 'x' * 80)
        self.assertEqual(self.row(self.view(), 'Builder')['mark'], '✗')
        self.store.event(self.pid, 'call_start', who='Verification', preferred='claude')
        with run_lock(self.folder / 'run.lock'):
            self.assertEqual(self.row(self.view(), 'Verification Agent')['mark'], '●')
        self.assertEqual(self.row(self.view(), 'Verification Agent')['mark'], '○')
        self.verify('PASS', True)
        self.assertEqual(self.row(self.view(), 'Verification Agent')['mark'], '✓')
        self.assertEqual(self.row(self.view(), 'Runtime Acceptance (LOCAL)')['mark'], '✓')

    def test_missing_event_keys_and_timeline_limit(self):
        kinds = ('decision', 'agent_hired', 'call_start', 'call', 'call_failed', 'provider_handoff',
                 'state', 'verification', 'build_rejected', 'edits_applied', 'recovery',
                 'recovery_replan', 'approval_requested', 'approval_decided', 'approval_reused',
                 'permission_granted', 'owner_feedback', 'owner_action', 'session')
        for kind in kinds:
            self.store.event(self.pid, kind)
        self.assertIsInstance(live.render(self.view()), str)
        for i in range(35):
            self.store.event(self.pid, 'custom', number=i, long='x' * 200)
        rows = self.view()['timeline']
        self.assertEqual(len(rows), 30)
        self.assertTrue(rows[0]['text'].startswith('number=5,'))
        self.assertTrue(rows[-1]['text'].startswith('number=34,'))
        self.assertTrue(all(len(r['text']) <= 100 for r in rows))
        expected = time.strftime('%H:%M:%S', time.localtime(self.store.events(self.pid)[-1]['at']))
        self.assertEqual(rows[-1]['at'], expected)

    def test_recovery_and_engine_names(self):
        self.store.event(self.pid, 'recovery', action='resume', attempt=1)
        self.store.event(self.pid, 'recovery_replan')
        self.store.event(self.pid, 'call', who='Builder', seconds=7, provider='custom')
        v = self.view()
        self.assertEqual(dict(v['header'])['복구 횟수'], '1')
        self.assertEqual(self.row(v, 'Builder')['engine'], 'custom')
        text = live.render(v)
        self.assertIn('recovery: resume (attempt 1)', text)
        self.assertIn('recovery re-plan', text)
        self.assertIn('Completed · 7s', text)


if __name__ == '__main__':
    unittest.main()
