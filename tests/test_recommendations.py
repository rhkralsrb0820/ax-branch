"""H3 recommendations are bounded planning data, never automatic attachment or authority."""
import copy
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from axbranch import departments as D, engine as E
from axbranch.state import Store, Rejected
from tests.test_engine import Script, GOOD


class RecommendationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='axb-recommend-'))
        self.store = Store(self.tmp / 'ws' / 'axbranch.sqlite3')
        self.specs = D.catalog()[0]
        self.pid = self.store.new_project('make a concise sourced product proposal')

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def suggest(self, dep='research'):
        D.record_recommendations(self.store, self.pid, [{'id': dep, 'reason': 'Compare supplied evidence for this Goal'}])
        return D.recommendations(self.store, self.pid)[-1]['id']

    def test_only_eligible_distinct_unattached_recommendations_are_recorded(self):
        D.attach(self.store, self.pid, 'research', self.specs)
        proposals = [{'id': 'research', 'reason': 'already attached'}, {'id': [], 'reason': 'malformed'},
                     {'id': 'unknown', 'reason': 'unknown'}, {'id': 'operations', 'reason': ''},
                     {'id': 'product-planning', 'reason': 'turn the supplied findings into MVP scope'},
                     {'id': 'product-planning', 'reason': 'duplicate'}]
        D.record_recommendations(self.store, self.pid, proposals)
        D.record_recommendations(self.store, self.pid, proposals)
        rows = D.recommendations(self.store, self.pid)
        self.assertEqual([r['department'] for r in rows], ['product-planning'])
        self.assertEqual([d['id'] for d in D.attached(self.store, self.pid)], ['research'])
        self.assertEqual(rows[0]['lifecycle'], 'legacy')

    def test_gap_is_shown_and_owner_vs_recommended_connections_are_distinguished(self):
        from axbranch import web
        D.attach(self.store, self.pid, 'operations', self.specs)                 # the Owner connected it directly
        D.record_recommendations(self.store, self.pid, [{'id': 'research', 'reason': 'compare sources',
                                                         'gap': 'no attached department checks sources'}])
        rec = D.recommendations(self.store, self.pid)[-1]
        self.assertEqual(rec['gap'], 'no attached department checks sources')
        D.decide_recommendation(self.store, self.pid, rec['id'], 'accepted')
        self.assertEqual({d['id']: d['via'] for d in web._attached_view(self.store, self.pid)},
                         {'operations': 'owner', 'research': 'ceo_recommendation'})

    def test_max_three_and_empty_without_any_model_call(self):
        specs = {}
        for n in range(5):
            spec = copy.deepcopy(self.specs['research'])
            spec['id'] = f'fixture{n}'
            specs[spec['id']] = spec
        with mock.patch.object(D, 'catalog', return_value=(specs, {})):
            D.record_recommendations(self.store, self.pid, [])
            self.assertEqual(D.recommendations(self.store, self.pid), [])
            D.record_recommendations(self.store, self.pid, [{'id': k, 'reason': 'fixture'} for k in specs])
            self.assertEqual(len(D.recommendations(self.store, self.pid)), 3)

    def test_explicit_acceptance_is_atomic_idempotent_and_preserves_required_mode(self):
        D.attach(self.store, self.pid, 'operations', self.specs, mode='required')
        recommendation = self.suggest()
        self.assertTrue(D.decide_recommendation(self.store, self.pid, recommendation, 'accepted'))
        self.assertFalse(D.decide_recommendation(self.store, self.pid, recommendation, 'accepted'))
        self.assertEqual({d['id']: d['mode'] for d in D.attached(self.store, self.pid)},
                         {'operations': 'required', 'research': 'available'})
        self.assertEqual(self.store.project(self.pid)['state'], 'CREATED')
        self.assertFalse(self.store.events(self.pid, {'call_start', 'permission_granted'}))
        with self.assertRaises(Rejected):
            D.decide_recommendation(self.store, self.pid, recommendation, 'dismissed')

    def test_dismissal_and_cross_project_ids_never_attach(self):
        rec = self.suggest()
        other = self.store.new_project('another project')
        with self.assertRaises(Rejected):
            D.decide_recommendation(self.store, other, rec, 'accepted')
        D.decide_recommendation(self.store, self.pid, rec, 'dismissed')
        self.assertFalse(D.attached(self.store, self.pid))

    def test_changed_scope_quarantine_spec_change_and_active_work_refuse_acceptance(self):
        rec = self.suggest()
        with mock.patch.object(D, 'blocked', return_value='quarantined'):
            with self.assertRaises(Rejected):
                D.decide_recommendation(self.store, self.pid, rec, 'accepted')
        specs = copy.deepcopy(self.specs)
        specs['research']['version'] = '99.0.0'
        with mock.patch.object(D, 'catalog', return_value=(specs, {})):
            with self.assertRaises(Rejected):
                D.decide_recommendation(self.store, self.pid, rec, 'accepted')
        self.store.update(self.pid, state='EXECUTING')
        with self.assertRaises(Rejected):
            D.decide_recommendation(self.store, self.pid, rec, 'accepted')
        self.store.update(self.pid, state='PAUSED', plan_version=2)
        with self.assertRaises(Rejected):
            D.decide_recommendation(self.store, self.pid, rec, 'accepted')
        self.assertFalse(D.attached(self.store, self.pid))

    def test_failed_attachment_rolls_back_decision(self):
        rec = self.suggest()
        with mock.patch.object(D, 'attach', side_effect=Rejected('fixture refusal')):
            with self.assertRaises(Rejected):
                D.decide_recommendation(self.store, self.pid, rec, 'accepted')
        self.assertFalse(self.store.events(self.pid, {'department_recommendation_decision'}))

    def test_existing_planning_call_records_a_recommendation_without_new_calls(self):
        class RecommendingScript(Script):
            def __call__(script, prompt, schema, *args, **kw):
                out, used, notes = super().__call__(prompt, schema, *args, **kw)
                if schema is E.PLAN:
                    out['recommended_departments'] = [{'id': 'operations', 'reason': 'check the supplied quantities'}]
                return out, used, notes
        engine = E.Engine(self.store, workspace=self.tmp / 'ws', vault=self.tmp / 'v', gai_db=self.tmp / 'x',
                          llm=RecommendingScript([GOOD], ['PASS']))
        self.assertIn('recommendable_departments', engine._department_context(self.pid))
        result = engine.run(self.pid, stop_at='STAFFING')
        self.assertEqual(result['state'], 'STAFFING')
        self.assertEqual(len(self.store.events(self.pid, {'call'})), 1)
        self.assertEqual(D.recommendations(self.store, self.pid)[0]['department'], 'operations')
        self.assertEqual(D.attached(self.store, self.pid), [])


if __name__ == '__main__':
    unittest.main()
