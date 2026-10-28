"""Completion reserves protect verification/acceptance without erasing usage on restart."""
import tempfile
import unittest
from pathlib import Path

from axbranch import budgets
from axbranch.state import Rejected, Store


def call(who, tokens, *, kind='call', start=None, usage_complete=False):
    detail = {'who': who, 'tokens': {'source': 'codex turn.completed',
                                    'input_tokens': tokens, 'output_tokens': 0}}
    if start is not None:
        detail['call_start_id'] = start
    if usage_complete:
        detail['usage_complete'] = True
    return {'kind': kind, 'detail': detail}


class CompletionBudgetTests(unittest.TestCase):
    def test_production_cannot_spend_the_verification_and_acceptance_reserve(self):
        events = [call('CEO', 14906), call('Researcher', 15000)]
        result = budgets.assess_budget(events, {'max_reported_tokens': 70000, 'max_calls': 12},
                                       'production')
        self.assertFalse(result['allowed'])
        self.assertGreater(result['remaining'], result['current_tokens'])
        self.assertEqual(result['reason'], 'completion_tokens')
        self.assertEqual([row['phase'] for row in result['downstream']], ['verification', 'acceptance'])
        # More budget permits the SAME work without weakening verification or erasing calls.
        bigger = budgets.assess_budget(events, {'max_reported_tokens': 100000, 'max_calls': 12},
                                       'production')
        self.assertTrue(bigger['allowed'])
        self.assertEqual(bigger['reported_tokens'], result['reported_tokens'])

    def test_first_pass_can_progress_to_acceptance_at_exact_estimated_capacity(self):
        total = budgets.completion_reserve([], 'planning')['reserve_tokens']
        settings = {'max_reported_tokens': total, 'max_calls': 4}
        events = []
        for phase, who in [('planning', 'CEO'), ('production', 'Maker'),
                           ('verification', 'Verification'), ('acceptance', 'CEO')]:
            check = budgets.assess_budget(events, settings, phase)
            self.assertTrue(check['allowed'], (phase, check))
            events.append(call(who, check['current_tokens']))
        self.assertEqual(budgets.ledger_usage(events)['reported_tokens'], total)

    def test_verifier_keeps_acceptance_but_acceptance_does_not_reserve_it_twice(self):
        before = budgets.completion_reserve([], 'verification')
        final = budgets.completion_reserve([], 'acceptance')
        self.assertEqual(before['reserve_calls'], 2)
        self.assertEqual(final['reserve_calls'], 1)
        self.assertEqual(before['reserve_tokens'] - final['reserve_tokens'], 20080)

    def test_known_pipeline_reserves_every_remaining_producer(self):
        planned = budgets.completion_reserve([], 'planning', pending_workers=4)
        current = budgets.completion_reserve([], 'production', pending_workers=3)
        self.assertEqual(planned['reserve_calls'], 7)
        self.assertEqual(current['reserve_calls'], 6)
        self.assertEqual(planned['reserve_tokens'] - current['reserve_tokens'], 14906)

    def test_call_ceiling_is_reserved_as_well_as_tokens(self):
        check = budgets.assess_budget([], {'max_reported_tokens': 250000, 'max_calls': 2}, 'production')
        self.assertFalse(check['allowed'])
        self.assertEqual(check['reason'], 'completion_calls')

    def test_larger_worker_call_raises_other_workers_reserves(self):
        events = [call('Researcher', 40000)]
        self.assertEqual(budgets.completion_reserve(events, 'production')['current_tokens'], 40000)
        self.assertEqual(budgets.call_reserve(events, 'verify'), 20080)

    def test_unknown_failed_or_interrupted_usage_blocks_new_calls(self):
        for events in ([{'kind': 'call_failed', 'detail': {'who': 'CEO'}}],
                       [{'kind': 'call', 'detail': {'who': 'Maker', 'tokens': 'UNKNOWN'}}],
                       [{'id': 5, 'kind': 'call_start', 'detail': {'who': 'CEO'}}]):
            with self.subTest(events=events):
                check = budgets.assess_budget(events, {'max_reported_tokens': 250000, 'max_calls': 20}, 'planning')
                self.assertFalse(check['allowed'])
                self.assertIsNone(check['reported_tokens'])
                self.assertEqual(check['reason'], 'unknown_usage')

    def test_explicit_terminal_pair_does_not_mask_an_earlier_interrupted_call(self):
        events = [{'id': 1, 'kind': 'call_start', 'detail': {}},
                  {'id': 2, 'kind': 'call_start', 'detail': {}}, call('CEO', 9000, start=2)]
        result = budgets.ledger_usage(events)
        self.assertIsNone(result['reported_tokens'])
        self.assertEqual(result['interrupted_calls'], 1)
        self.assertEqual(result['known_tokens'], 9000)
        self.assertEqual(result['started_calls'], 2)

    def test_failed_reported_usage_and_legacy_calls_are_counted(self):
        events = [{'id': 1, 'kind': 'call_start', 'detail': {}},
                  call('CEO', 1200, kind='call_failed', start=1, usage_complete=True), call('Maker', 2300)]
        result = budgets.ledger_usage(events)
        self.assertEqual(result['reported_tokens'], 3500)
        self.assertEqual(result['failed_calls'], 1)
        self.assertEqual(result['started_calls'], 2)
        events.append(call('CEO', 1200, kind='call_failed', start=1))
        self.assertIsNone(budgets.ledger_usage(events)['reported_tokens'])

    def test_partial_failure_usage_cannot_be_treated_as_complete_and_legacy_calls_count(self):
        partial = [call('CEO', 1200, kind='call_failed')]
        self.assertIsNone(budgets.ledger_usage(partial)['reported_tokens'])
        mixed = [call('Maker', 2300), {'id': 8, 'kind': 'call_start', 'detail': {}}]
        self.assertEqual(budgets.ledger_usage(mixed)['started_calls'], 2)
        mixed.append(call('CEO', 1200, start=8))
        self.assertEqual(budgets.ledger_usage(mixed)['started_calls'], 2)
        self.assertEqual(budgets.ledger_usage(mixed)['reported_tokens'], 3500)

    def test_provider_cache_semantics_and_invalid_usage(self):
        codex = {'tokens': {'source': 'codex turn.completed', 'input_tokens': 100,
                            'cached_input_tokens': 90, 'output_tokens': 20, 'reasoning_output_tokens': 15}}
        self.assertEqual(budgets.usage_tokens(codex), 120)
        claude = {'tokens': {'source': 'claude result', 'input_tokens': 100,
                             'cache_creation_input_tokens': 40, 'cache_read_input_tokens': 50, 'output_tokens': 20}}
        self.assertEqual(budgets.usage_tokens(claude), 210)
        for invalid in (-1, True, '3', float('nan'), float('inf')):
            claude['tokens']['cache_read_input_tokens'] = invalid
            self.assertIsNone(budgets.usage_tokens(claude))

    def test_restart_preserves_configuration_and_complete_ledger(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'state.sqlite3'
            store = Store(path)
            pid = store.new_project('budget persistence test')
            budgets.configure(store, pid, max_reported_tokens=150000, profile='product_planning')
            start = store.event(pid, 'call_start', who='CEO')
            store.event(pid, 'call', who='CEO', call_start_id=start,
                        tokens={'source': 'codex turn.completed', 'input_tokens': 10000, 'output_tokens': 2000})
            store.close()
            store = Store(path)
            try:
                self.assertEqual(budgets.ledger_usage(store.events(pid))['reported_tokens'], 12000)
                self.assertEqual(store.events(pid, {'execution_budget'})[0]['detail']['profile'], 'product_planning')
                with self.assertRaises(Rejected):
                    budgets.configure(store, pid, max_reported_tokens=250000)
            finally:
                store.close()

    def test_invalid_phase_and_counts_are_not_silently_under_reserved(self):
        with self.assertRaises(ValueError):
            budgets.completion_reserve([], 'unknown')
        for count in (-1, True, 1.5):
            with self.assertRaises(ValueError):
                budgets.completion_reserve([], 'production', count)


if __name__ == '__main__':
    unittest.main()
