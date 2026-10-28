"""Owner task profiles and cumulative budget read models; isolated SQLite, no model/provider/browser."""
import tempfile
import unittest
from pathlib import Path

from axbranch import actions, budgets, web
from axbranch.state import Store


class TaskBudgetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmp.name)
        self.store = Store(self.workspace / 'axbranch.sqlite3')
        self.launched = []
        self.app = web.App(workspace=self.workspace, engine_factory=self.no_engine,
                           launcher=lambda _, pid: self.launched.append(pid))

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    @staticmethod
    def no_engine():
        raise AssertionError('Budget selection must not open an engine or provider')

    def create(self, profile='general', request='budget-request-001'):
        return web.create_project(self.app, self.store,
                                  {'goal': '분석 결과 만들기', 'task_type': profile, 'request_id': request}, 'web')['id']

    def test_each_profile_is_fixed_once_and_survives_a_new_store(self):
        for index, (profile, limit) in enumerate((('general', 250000), ('product_planning', 150000),
                                                ('csv_analysis', 250000), ('web_app', 250000))):
            pid = self.create(profile, f'budget-request-{index:03d}')
            with self.subTest(profile=profile):
                reopened = Store(self.workspace / 'axbranch.sqlite3')
                try:
                    settings = reopened.events(pid, {'execution_budget'})
                    self.assertEqual(len(settings), 1)
                    rec = settings[0]['detail']
                    self.assertEqual((rec['profile'], rec['max_reported_tokens']), (profile, limit))
                    self.assertEqual((rec['max_calls'], rec['max_seconds'], rec['max_prompt_chars']), (20, 3600, 200000))
                    self.assertFalse(rec['local_documents'])
                finally:
                    reopened.close()
        self.assertEqual(len(self.launched), 4)

    def test_task_profile_time_is_spent_call_time_not_calendar_time(self):
        pid = self.create('csv_analysis', 'budget-time-001')
        rec = self.store.events(pid, {'execution_budget'})[-1]
        self.assertEqual(rec['detail']['time_basis'], 'call_seconds')
        events = self.store.events(pid)
        tomorrow = rec['at'] + 86400                       # an Owner revision the next day
        self.assertEqual(budgets.seconds_left(events, rec['detail'], rec['at'], tomorrow), 3600)
        self.store.event(pid, 'call', who='CEO', seconds=3500, tokens={'source': 'codex', 'input_tokens': 1, 'output_tokens': 1})
        self.assertEqual(budgets.seconds_left(self.store.events(pid), rec['detail'], rec['at'], tomorrow), 100)
        wall = {**rec['detail'], 'time_basis': 'wall_clock'}   # experiments keep elapsed-time semantics
        self.assertLess(budgets.seconds_left(events, wall, rec['at'], tomorrow), 0)

    def test_response_loss_retry_cannot_replace_a_created_projects_allowance(self):
        pid = self.create('product_planning')
        self.assertEqual(self.create('web_app'), pid)
        self.assertEqual(self.launched, [pid])
        self.assertEqual(len(self.store.events(pid, {'execution_budget'})), 1)
        self.assertEqual(self.store.events(pid, {'execution_budget'})[0]['detail']['max_reported_tokens'], 150000)

    def test_bad_profile_is_rejected_before_creation_or_launch(self):
        for profile in ('unlimited', None, {}, 250000):
            with self.subTest(profile=profile), self.assertRaises(actions.StartRejected):
                self.create(profile)
        self.assertEqual(self.store.projects(), [])
        self.assertEqual(self.launched, [])

    def test_legacy_and_explicit_experiment_budgets_are_not_replaced_by_reading(self):
        legacy = self.store.new_project('기존 프로젝트')
        experimental = self.store.new_project('사전 등록 실험')
        budgets.configure(self.store, experimental, max_reported_tokens=60000, local_documents=True)
        before = self.store.events(experimental)
        self.assertFalse(web._execution_budget(self.store, self.store.project(legacy))['configured'])
        report = web._execution_budget(self.store, self.store.project(experimental))
        self.assertEqual((report['label'], report['max_reported_tokens']), ('개별 설정', 60000))
        self.assertEqual(self.store.events(experimental), before)

    def test_resume_keeps_project_usage_and_unknown_call_is_not_zero(self):
        pid = self.create()
        self.store.event(pid, 'call', who='CEO', tokens={'input_tokens': 100, 'output_tokens': 20})
        self.store.pause(pid, 'Execution budget reserve')
        actions.resume(self.store, pid, 'web')
        report = web._execution_budget(self.store, self.store.project(pid))
        self.assertEqual((report['reported_tokens'], report['remaining_tokens']), (120, 249880))
        self.assertEqual(len(self.store.events(pid, {'execution_budget'})), 1)
        self.store.event(pid, 'call_start', who='Developer')
        report = web._execution_budget(self.store, self.store.project(pid))
        self.assertIsNone(report['reported_tokens'])
        self.assertIsNone(report['remaining_tokens'])
        self.assertEqual(report['known_tokens'], 120)

    def test_acceptance_pending_requires_current_pass_and_current_acceptance_stop(self):
        pid = self.create()
        self.store.update(pid, iteration=1)
        artifact = self.store.add_artifact(pid, 1, self.workspace / 'report.md', 'fixture', 'markdown', None)
        self.store.add_verification(pid, artifact, 1, 'PASS', {'findings': []}, {'ok': True}, 'codex')
        self.store.event(pid, 'budget_reserve_stop', phase='acceptance', iteration=1, reserve=14906, remaining=1000)
        self.store.pause(pid, 'Execution budget reserve')
        current = web._execution_budget(self.store, self.store.project(pid))
        self.assertTrue(current['verification_passed'])
        self.assertTrue(current['acceptance_pending'])
        self.store.update(pid, iteration=2)
        after_revision = web._execution_budget(self.store, self.store.project(pid))
        self.assertFalse(after_revision['verification_passed'])
        self.assertFalse(after_revision['acceptance_pending'])
        self.store.update(pid, iteration=1)
        self.store.event(pid, 'budget_reserve_stop', phase='production', iteration=1, reserve=50000, remaining=1000)
        self.assertFalse(web._execution_budget(self.store, self.store.project(pid))['acceptance_pending'])


if __name__ == '__main__':
    unittest.main()
