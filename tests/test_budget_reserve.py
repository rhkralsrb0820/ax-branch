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

    def test_engine_pauses_before_the_verifier_with_a_readable_reason(self):
        eng, pid = self.project()
        with mock.patch.object(providers, 'last_usage', return_value=usage(15000)):
            p = eng.run(pid)
        self.assertEqual(p['state'], 'PAUSED')
        self.assertIn('예산 여유가 부족해 호출을 시작하지 않았습니다', p['pause_reason'])
        self.assertEqual([e['detail']['who'] for e in self.store.events(pid, {'call'})], ['CEO', 'Architect', 'Developer'])
        self.assertEqual(self.store.events(pid, {'budget_reserve_stop'})[-1]['detail']['who'], 'Verification')


if __name__ == '__main__':
    unittest.main()
