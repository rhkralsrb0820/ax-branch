"""Owner Effort KPI: counts come from recorded state; pipeline failures are not credited as caught defects."""
import shutil
import tempfile
import unittest
from pathlib import Path

from axbranch import engine as E
from axbranch.metrics import effort, provider_record
from axbranch.state import Store
from tests.test_engine import BROKEN, LAUNCHABLE, Script


class MetricsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.store = Store(self.tmp / 'ws' / 'axbranch.sqlite3')

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_owner_escapes_by_channel_and_action(self):
        pid = self.store.new_project('owner actions')
        for action, channel in [('run', 'cli'), ('review', 'developer_cli'), ('run', 'cli'),
                                ('review', 'app'), ('run', 'dev')]:
            self.store.event(pid, 'owner_action', action=action, channel=channel)
        self.assertEqual(effort(self.store, pid)['MEASURED']['owner_escapes'], {
            'total': 3, 'by_channel': {'cli': 2, 'developer_cli': 1},
            'by_action': {'run': 2, 'review': 1}, 'in_app_actions': 1, 'excluded_development': 1,
        })

    def test_recoveries_counted_separately(self):
        pid = self.store.new_project('recoveries')
        for channel in ('cli', 'developer_cli', 'app', 'dev'):
            self.store.event(pid, 'owner_action', action='replan', channel=channel)
            self.store.event(pid, 'recovery_replan', reason='manual recovery')
        for action in ('resume', 'replan+resume', 'needs_owner_decision'):
            self.store.event(pid, 'recovery', action=action)
        # A recovery_replan without an owner_action is not evidence of an Owner escape.
        self.store.event(pid, 'recovery_replan', reason='automatic recovery')
        m = effort(self.store, pid)['MEASURED']
        self.assertEqual(m['owner_escapes'], {
            'total': 2, 'by_channel': {'cli': 1, 'developer_cli': 1},
            'by_action': {'replan': 2}, 'in_app_actions': 1, 'excluded_development': 1,
        })
        # the last re-plan comes after the supervisor gave up (needs_owner_decision) and has no Supervisor label:
        # outside an automatic episode, so it is the Owner's
        self.assertEqual(m['manual_recovery_replans'], 5)
        self.assertEqual(m['automatic_recoveries'], 3)

    def test_effort_project_scope(self):
        pid = self.store.new_project('first project')
        other = self.store.new_project('second project')
        for action, channel in [('run', 'developer_cli'), ('review', 'app'), ('replan', 'dev')]:
            self.store.event(other, 'owner_action', action=action, channel=channel)
        self.store.event(other, 'recovery', action='resume')
        scoped = effort(self.store, pid)
        self.assertEqual(set(scoped), {'scope', 'MEASURED', 'ESTIMATED', 'UNKNOWN'})
        self.assertEqual(scoped['scope'], pid)
        self.assertEqual(scoped['MEASURED']['owner_escapes'], {
            'total': 0, 'by_channel': {'cli': 0, 'developer_cli': 0},
            'by_action': {}, 'in_app_actions': 0, 'excluded_development': 0,
        })
        self.assertEqual(scoped['MEASURED']['automatic_recoveries'], 0)
        self.store.event(pid, 'owner_action', action='review', channel='cli')
        self.store.event(pid, 'recovery', action='resume')
        scoped = effort(self.store, pid)['MEASURED']
        self.assertEqual(scoped['owner_escapes']['total'], 1)
        self.assertEqual(scoped['automatic_recoveries'], 1)
        combined = effort(self.store)['MEASURED']
        self.assertEqual(combined['owner_escapes'], {
            'total': 2, 'by_channel': {'cli': 1, 'developer_cli': 1},
            'by_action': {'run': 1, 'review': 1}, 'in_app_actions': 1, 'excluded_development': 1,
        })
        self.assertEqual(combined['automatic_recoveries'], 2)

    def test_provider_record_attributes_pass_to_actual_producer(self):
        pid = self.store.new_project('producer provenance')
        other = self.store.new_project('unrelated project')
        agent = self.store.add_agent(pid, 'Developer', 'claude')
        artifact = self.store.add_artifact(pid, 1, self.tmp / 'build.py', 'sha', 'python', agent)
        self.store.save_output(pid, 1, 1, 1, agent, 'codex', {})
        self.store.save_output(pid, 1, 1, 0, agent, 'claude', {})
        self.store.save_output(pid, 2, 2, 2, agent, 'claude', {})
        self.store.save_output(other, 1, 1, 2, None, 'claude', {})
        self.store.add_verification(pid, artifact, 1, 'PASS', {}, {}, 'claude')

        recorded = provider_record(self.store)
        self.assertEqual(recorded['codex']['final_builds_verified'], 1)
        self.assertEqual(recorded['codex']['final_builds_passed'], 1)
        self.assertEqual(recorded['claude']['final_builds_verified'], 0)
        self.assertEqual(recorded['claude']['final_builds_passed'], 0)

        self.store.discard_context(pid)
        fallback = provider_record(self.store)
        self.assertEqual(fallback['claude']['final_builds_verified'], 1)
        self.assertEqual(fallback['claude']['final_builds_passed'], 1)
        self.assertEqual(fallback['codex']['final_builds_verified'], 0)
        self.assertEqual(fallback['codex']['final_builds_passed'], 0)

    def test_effort_counts(self):
        script = Script([BROKEN, LAUNCHABLE, '', LAUNCHABLE], ['PASS', 'PASS', 'PASS'])
        eng = E.Engine(self.store, workspace=self.tmp / 'ws', vault=self.tmp / 'v', gai_db=self.tmp / 'x', llm=script)
        pid = self.store.new_project('make an add tool')
        eng.run(pid)                                       # v1 BROKEN fails its self-test -> v2 passes
        eng.owner_review(pid, works=True, text='show a short explanation too')
        eng.run(pid)                                       # v3 empty -> v4 passes
        m = effort(self.store, pid)['MEASURED']
        self.assertEqual(m['owner_instructions (goals + problem reports + change requests)'], 2)
        self.assertEqual(m['owner_confirmations (works / finish)'], 1)
        self.assertEqual(m['defects_caught_before_owner (verification FAIL on a real build)'], 1)
        self.assertEqual(m['ax_branch_pipeline_failures (empty / no deliverable)'], 1)
        self.assertEqual(m['verified_deliveries (PASS)'], 2)
        self.assertEqual(m['problems_found_by_owner_after_PASS'], 0)
        self.assertGreater(m['ai_agent_turns_run_by_ax_branch'], m['owner_instructions (goals + problem reports + change requests)'])
        self.assertIn('UNKNOWN', effort(self.store))


if __name__ == '__main__':
    unittest.main()
