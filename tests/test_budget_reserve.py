"""Budget control before a call: a call starts only if the remaining budget covers the role's largest measured call."""
import unittest
from unittest import mock

from axbranch import providers
from axbranch.state import Rejected
from tests import test_engine as TE
from tests.test_engine import GOOD, Script


def usage(n, source='codex turn.completed'):
    return {'source': source, 'input_tokens': n, 'output_tokens': 0}


class BudgetReserveTests(unittest.TestCase):
    setUp, tearDown, engine = TE.EngineTests.setUp, TE.EngineTests.tearDown, TE.EngineTests.engine

    def project(self, cap=60000):
        pid = self.store.new_project('budget fixture')
        eng = self.engine(Script([GOOD], ['PASS']))
        eng.configure_budget(pid, max_calls=12, max_seconds=1200, max_prompt_chars=100000, max_reported_tokens=cap)
        return eng, pid

    def test_enough_budget_starts_the_call(self):
        eng, pid = self.project()
        self.assertFalse(eng._budget_guard(pid, 'prompt', 'Verification').is_set())

    def test_insufficient_remaining_budget_refuses_and_project_maximum_raises_the_reserve(self):
        eng, pid = self.project()
        self.store.event(pid, 'call', who='CEO', tokens=usage(45000))
        with self.assertRaises(Rejected) as stop:
            eng._budget_guard(pid, 'prompt', 'Verification')                       # 15,000 left < 20,080
        self.assertIn('remaining 15,000', str(stop.exception))
        rec = self.store.events(pid, {'budget_reserve_stop'})[-1]['detail']
        self.assertEqual((rec['used'], rec['reserve'], rec['remaining'], rec['cap']), (45000, 20080, 15000, 60000))
        with self.assertRaises(Rejected):
            eng._budget_guard(pid, 'prompt', 'Developer')                          # 15,000 left < 15,636
        eng2, pid2 = self.project()
        self.store.event(pid2, 'call', who='Verification', tokens=usage(35000))    # a larger call seen in THIS project
        self.assertEqual(eng2._call_reserve(self.store.events(pid2), 'Verification'), ('verify', 35000))
        with self.assertRaises(Rejected):
            eng2._budget_guard(pid2, 'prompt', 'Verification')                     # 25,000 left < 35,000

    def test_unknown_usage_stops(self):
        eng, pid = self.project()
        self.store.event(pid, 'call', who='CEO', tokens='UNKNOWN')
        with self.assertRaises(Rejected) as stop:
            eng._budget_guard(pid, 'prompt', 'CEO')
        self.assertIn('Execution budget reached', str(stop.exception))

    def test_engine_does_not_start_production_it_cannot_finish(self):
        eng, pid = self.project(cap=95000)
        with mock.patch.object(providers, 'last_usage', return_value=usage(20000)):
            p = eng.run(pid)
        self.assertEqual(p['state'], 'PAUSED')
        self.assertIn('예산 여유가 부족해 호출을 시작하지 않았습니다', p['pause_reason'])
        self.assertEqual([e['detail']['who'] for e in self.store.events(pid, {'call'})], ['CEO', 'Architect'])
        stop = self.store.events(pid, {'budget_reserve_stop'})[-1]['detail']
        self.assertEqual((stop['who'], stop['phase']), ('Developer', 'production'))
        self.assertEqual([s['phase'] for s in stop['downstream']], ['verification', 'acceptance'])
        # this build + verification + acceptance; the 20,000-token calls seen in THIS project raised the worker and CEO
        # reserves above their recorded defaults (15,636 / 14,906)
        self.assertEqual(stop['reserve'], 20000 + 20080 + 20000)


    def test_ab_preflight_walks_the_first_pass_under_the_reserve_rule(self):
        from axbranch import product_experiment as X
        old = X.reserve_feasibility(60000)                             # the 2026-10-26 approval
        self.assertFalse(old['best_case']['fits'])                     # cannot even start under the completion reserve
        self.assertIn('call 1 (ceo)', old['best_case']['stopped_at'])
        proposal = X.reserve_feasibility(X.BUDGET['max_reported_tokens'])
        self.assertTrue(proposal['best_case']['fits'] and proposal['worst_case']['fits'])

    def test_a_real_ab_run_needs_the_owner_approval_flag(self):
        import tempfile
        from pathlib import Path
        from axbranch import product_experiment as X
        root = Path(tempfile.mkdtemp()) / 'ab'
        with self.assertRaises(Rejected):
            X.run_compact(root)                                        # real providers, no approval: refused
        self.assertFalse(root.exists())                                # nothing was registered or started

if __name__ == '__main__':
    unittest.main()
