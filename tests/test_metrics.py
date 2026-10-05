"""Owner Effort KPI: counts come from recorded state; pipeline failures are not credited as caught defects."""
import shutil
import tempfile
import unittest
from pathlib import Path

from axbranch import engine as E
from axbranch.metrics import effort
from axbranch.state import Store
from tests.test_engine import BROKEN, LAUNCHABLE, Script


class MetricsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.store = Store(self.tmp / 'ws' / 'axbranch.sqlite3')

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

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
