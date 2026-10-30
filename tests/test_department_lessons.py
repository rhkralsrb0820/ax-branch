"""Lesson candidates are fixed mappings of recorded events (no model text, no claimed effect)."""
import unittest

from axbranch import knowledge


def ev(i, kind, **detail):
    return {'id': i, 'kind': kind, 'detail': detail}


class LessonTests(unittest.TestCase):
    def test_only_matching_department_version_and_stage_events_become_candidates(self):
        delegations = [ev(1, 'delegation', plan_version=2, stage=1)]
        events = [ev(2, 'department_contract', department='research', status='fail', plan_version=2),
                  ev(3, 'department_contract', department='research', status='fail', plan_version=1),   # other version
                  ev(4, 'department_contract', department='ops', status='fail', plan_version=2),        # other department
                  ev(5, 'stage_reused', stage=1, plan_version=2),
                  ev(6, 'budget_reserve_stop')]
        got = {c['code']: c for c in knowledge.department_lessons(events, 'research', delegations)}
        self.assertEqual(got['contract_format']['evidence_events'], [2])
        self.assertEqual(got['unchanged_stage']['evidence_events'], [5])
        self.assertEqual(got['completion_budget']['scope'], 'project')
        self.assertTrue(all(c['status'] == 'CANDIDATE' and c['causal_effect'] == 'UNKNOWN' for c in got.values()))
        self.assertEqual(knowledge.department_lessons([], 'research', delegations), [])


if __name__ == '__main__':
    unittest.main()
