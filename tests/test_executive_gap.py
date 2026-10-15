"""Gap-aware executive lifecycle; all projects live in temporary workspaces."""
import json
import unittest
from pathlib import Path
from unittest import mock

from axbranch import engine as E
from tests import test_engine as F


class ExecutiveGapTests(unittest.TestCase):
    setUp, tearDown = F.EngineTests.setUp, F.EngineTests.tearDown

    def engine(self, script):
        eng = F.EngineTests.engine(self, script)
        eng.checks = mock.Mock(return_value={'ok': True, 'ran': ['self-test'], 'exit_code': 0, 'output': 'ok'})
        eng.runtime_evidence = mock.Mock(return_value={'ok': True, 'mode': 'cli', 'steps': [], 'notes': []})
        return eng

    def report(self, gap, **extra):
        return {'goal_satisfied': 'partly', 'missing_evidence': ['real use'], 'next_action': 'rework',
                'directive': 'Close the classified gap', 'gap_class': gap, **extra}

    def run_case(self, gap, builds=None, reports=None):
        script = F.ExecutiveScript(builds or [F.GOOD], ['PASS', 'PASS'],
                                  reports or [self.report(gap), F.ExecutiveAcceptanceTests.deliver])
        eng = self.engine(script)
        pid = self.store.new_project('make an add tool')
        result = eng.run(pid)
        self.assertEqual(result['state'], 'OWNER_REVIEW', result['pause_reason'])
        return pid, eng, script

    def test_nonproduct_gaps_reverify_same_artifact_without_production_or_budget(self):
        for gap in ('EVIDENCE_GAP', 'HARNESS_DEFECT', 'AMBIGUOUS'):
            with self.subTest(gap=gap):
                pid, eng, script = self.run_case(gap)
                self.assertEqual(len(self.store.artifacts(pid)), 1)
                self.assertEqual(self.store.project(pid)['iteration'], 1)
                self.assertEqual(len({v['artifact_id'] for v in self.store.verifications(pid)}), 1)
                self.assertEqual(len(self.store.verifications(pid)), 2)
                self.assertEqual(sum(s is E.BUILD for s, _, _ in script.prompts), 1)
                self.assertEqual(eng._product_failures(pid), [])
                self.assertFalse(any(e['detail'].get('to') == 'REWORK' for e in self.store.events(pid, {'state'})))

    def test_product_classes_rebuild(self):
        for gap in ('PRODUCT_CHANGE', 'PRODUCT_DEFECT'):
            with self.subTest(gap=gap):
                pid, _, _ = self.run_case(gap, [F.GOOD, F.GOOD + '\n'])
                self.assertEqual([a['iteration'] for a in self.store.artifacts(pid)], [1, 2])

    def test_unknown_class_is_evidence_collection(self):
        pid, _, _ = self.run_case('invented')
        self.assertEqual(len(self.store.artifacts(pid)), 1)

    def test_outside_authority_uses_owner_path(self):
        pid, _, script = self.run_case('OUTSIDE_AUTHORITY', reports=[self.report('OUTSIDE_AUTHORITY')])
        self.assertEqual(self.store.project(pid)['report']['next_action'], 'owner_decision')
        self.assertEqual(sum(s is E.BUILD for s, _, _ in script.prompts), 1)
        self.assertFalse(self.store.events(pid, {'same_artifact_route'}))

    def test_additive_verification_keeps_acceptance_intent(self):
        probe = {'name': 'original', 'args': ['--keep'], 'stdin': 'required', 'http_method': 'POST',
                 'http_path': '/create', 'http_body': '{}', 'expect_status': 201, 'expect_exit': 0,
                 'expect_contains': ['saved'], 'expect_absent': []}
        class WithProbe(F.ExecutiveScript):
            def __call__(self, prompt, schema, *args, **kw):
                result, used, notes = super().__call__(prompt, schema, *args, **kw)
                if schema is E.PLAN:
                    result['runtime']['probes'] = [probe]
                return result, used, notes
        spec = {'mode': 'none', 'owner_launch': 'weakened', 'launch_args': ['--wrong'],
                'probes': [{**probe, 'args': [], 'http_path': '/easier', 'expect_status': 202,
                            'expect_contains': []}, {**probe, 'name': 'extra'}]}
        script = WithProbe([F.GOOD], ['PASS', 'PASS'], [self.report('EVIDENCE_GAP', runtime=spec),
                                                       F.ExecutiveAcceptanceTests.deliver])
        pid = self.store.new_project('make an add tool')
        result = self.engine(script).run(pid)
        self.assertEqual(result['state'], 'OWNER_REVIEW', result['pause_reason'])
        runtime = result['plan']['runtime']
        self.assertEqual(runtime['mode'], 'cli')
        self.assertEqual(runtime['launch_args'], [])
        self.assertEqual(runtime['probes'][0]['args'], ['--keep'])
        self.assertEqual(runtime['probes'][0]['http_path'], '/create')
        self.assertEqual(runtime['probes'][0]['expect_status'], 201)
        self.assertEqual(runtime['probes'][0]['expect_contains'], ['saved'])
        self.assertEqual(len(runtime['probes']), 2)
        self.assertEqual(result['plan']['acceptance_criteria'], ['add(2,3)==5'])

    def test_deterministic_product_failure_overrides_nonproduct_report(self):
        script = F.ExecutiveScript([F.GOOD], ['PASS'], [self.report('EVIDENCE_GAP')])
        eng = self.engine(script)
        pid = self.store.new_project('make an add tool')
        for fn in (eng._created, eng._planning, eng._staffing, eng._executing):
            fn(pid)
        art = self.store.artifacts(pid)[0]
        verdict = {'verdict': 'PASS', 'criteria': [], 'findings': []}
        self.store.add_verification(pid, art['id'], 1, 'PASS', verdict,
            {'ok': False, 'exit_code': 1, 'output': 'AssertionError', 'ran': ['self-test']}, 'codex')
        eng._deliver(pid, art, F.GOOD, verdict)
        result = self.store.project(pid)
        self.assertEqual(result['state'], 'REWORK')
        self.assertEqual(result['plan']['ceo_directive']['gap_class'], 'PRODUCT_DEFECT')
        self.assertEqual(result['iteration'], 2)

    def test_new_product_evidence_replaces_stale_no_product_directive(self):
        eng = self.engine(F.Script([F.GOOD], []))
        pid = self.store.new_project('make an add tool')
        for fn in (eng._created, eng._planning, eng._staffing, eng._executing):
            fn(pid)
        art = self.store.artifacts(pid)[0]
        self.store.add_verification(pid, art['id'], 1, 'FAIL', {'criteria': [], 'findings': []},
            {'ok': False, 'exit_code': 1, 'output': 'AssertionError', 'ran': ['self-test']}, 'codex')
        p = self.store.project(pid)
        p['plan']['ceo_directive'] = {'gap_class': 'EVIDENCE_GAP', 'after_version': 1, 'directive': 'Do not change the product'}
        self.store.update(pid, plan=p['plan'], state='REWORK', iteration=2)
        eng._rework(pid)
        p = self.store.project(pid)
        self.assertEqual(p['state'], 'STAFFING')
        self.assertEqual(p['plan']['ceo_directive']['gap_class'], 'PRODUCT_DEFECT')
        self.assertIn('Repair', p['plan']['ceo_directive']['directive'])
        self.assertEqual(p['plan']['ceo_directive']['prior_directive'], 'Do not change the product')

    def test_verifier_product_failure_after_evidence_gap_rebuilds_once(self):
        for evidence in ('finding', 'unmet_criterion'):
            with self.subTest(evidence=evidence):
                class ProductFailure(F.ExecutiveScript):
                    def __call__(self, prompt, schema, *args, **kw):
                        result, used, notes = super().__call__(prompt, schema, *args, **kw)
                        if schema is E.VERDICT and result['verdict'] == 'FAIL':
                            if evidence == 'finding':
                                result['criteria'][0]['met'] = True
                                result['findings'][0].update(kind='product', criterion=0)
                            else:
                                result['findings'] = []
                        return result, used, notes

                script = ProductFailure([F.GOOD, F.GOOD + '\n# product repaired\n'],
                    ['PASS', 'FAIL', 'PASS'],
                    [self.report('EVIDENCE_GAP'), F.ExecutiveAcceptanceTests.deliver])
                eng = self.engine(script)
                pid = self.store.new_project('make an add tool')
                for fn in (eng._created, eng._planning, eng._staffing, eng._executing,
                           eng._verifying):
                    fn(pid)
                self.assertEqual(self.store.project(pid)['state'], 'VERIFYING')
                self.assertEqual(eng._product_failures(pid), [])
                eng._verifying(pid)
                failed = self.store.verifications(pid)[-1]
                self.assertFalse(eng._deterministic_product(failed))
                self.assertEqual([v['id'] for v in eng._product_failures(pid)], [failed['id']])
                self.assertEqual(self.store.project(pid)['state'], 'REWORK')
                eng._rework(pid)
                p = self.store.project(pid)
                self.assertEqual(p['state'], 'STAFFING')  # fail promptly instead of entering the old loop
                self.assertEqual(p['plan']['ceo_directive']['gap_class'], 'PRODUCT_DEFECT')
                result = eng.run(pid)
                self.assertEqual(result['state'], 'OWNER_REVIEW', result['pause_reason'])
                arts = self.store.artifacts(pid)
                self.assertEqual([a['iteration'] for a in arts], [1, 2])
                vs = self.store.verifications(pid)
                self.assertEqual([v['verdict'] for v in vs], ['PASS', 'FAIL', 'PASS'])
                self.assertEqual([v['artifact_id'] for v in vs], [arts[0]['id'], arts[0]['id'], arts[1]['id']])
                self.assertEqual(sum(s is E.BUILD for s, _, _ in script.prompts), 2)
                self.assertEqual([v['id'] for v in eng._product_failures(pid)], [failed['id']])
                self.assertEqual(len(self.store.events(pid, {'same_artifact_route'})), 1)
                self.assertEqual(result['plan']['acceptance_criteria'], ['add(2,3)==5'])
                self.assertEqual((script.builds, script.verdicts, script.reports), ([], [], []))

    def test_intentional_no_change_is_reverified_not_failed(self):
        class NoChange(F.ExecutiveScript):
            def __call__(self, prompt, schema, *args, **kw):
                result, used, notes = super().__call__(prompt, schema, *args, **kw)
                if schema is E.BUILD and not result['content']:
                    result.update(outcome='NO_CHANGE', no_change_evidence='Existing add implementation meets the requested behavior; observe it.')
                return result, used, notes
        script = NoChange([F.GOOD, ''], ['PASS', 'PASS'], [self.report('PRODUCT_CHANGE'), F.ExecutiveAcceptanceTests.deliver])
        eng = self.engine(script)
        pid = self.store.new_project('make an add tool')
        result = eng.run(pid)
        self.assertEqual(result['state'], 'OWNER_REVIEW', result['pause_reason'])
        self.assertEqual(len(self.store.artifacts(pid)), 1)
        self.assertEqual(eng._product_failures(pid), [])
        self.assertTrue(self.store.events(pid, {'intentional_no_change'}))
        self.assertEqual([v['verdict'] for v in self.store.verifications(pid)], ['PASS', 'PASS'])

    def test_intentional_no_change_with_only_harness_evidence_does_not_fail_product(self):
        script = F.Script([F.GOOD], [])
        eng = self.engine(script)
        pid = self.store.new_project('make an add tool')
        for fn in (eng._created, eng._planning, eng._staffing, eng._executing):
            fn(pid)
        art = self.store.artifacts(pid)[0]
        self.store.add_verification(pid, art['id'], 1, 'FAIL', {'criteria': [], 'findings': []},
            {'ok': False, 'exit_code': 0, 'output': 'RUNTIME ACCEPTANCE FAILED: missing recording',
             'runtime': {'steps': [{'ok': False, 'problems': ['browser did not finish']}] }}, 'codex')
        self.store.update(pid, state='EXECUTING', iteration=2)
        final = self.store.project(pid)['plan']['pipeline'][-1]
        eng._no_deliverable(pid, final, 'claude', {'outcome': 'NO_CHANGE', 'no_change_evidence': 'Only the browser recording failed'})
        self.assertEqual(self.store.project(pid)['state'], 'VERIFYING')
        self.assertEqual(eng._product_failures(pid), [])
        self.assertEqual(len(self.store.verifications(pid)), 1)

    def test_empty_output_or_unsubstantiated_no_change_still_fails(self):
        for outcome, evidence in (('CHANGED', ''), ('NO_CHANGE', ''), ('NO_CHANGE', 'No baseline exists')):
            with self.subTest(outcome=outcome, evidence=evidence):
                class Empty(F.Script):
                    def __call__(self, prompt, schema, *args, **kw):
                        result, used, notes = super().__call__(prompt, schema, *args, **kw)
                        if schema is E.BUILD:
                            result.update(outcome=outcome, no_change_evidence=evidence)
                        return result, used, notes
                eng = self.engine(Empty([''], []))
                pid = self.store.new_project('make an add tool')
                self.store.update(pid, budget=1)
                self.assertEqual(eng.run(pid)['state'], 'PAUSED')
                self.assertEqual(len(eng._product_failures(pid)), 1)
                self.assertEqual(self.store.verifications(pid)[0]['verdict'], 'FAIL')

    def test_identical_passed_bytes_do_not_commit_new_version(self):
        pid, eng, _ = self.run_case('PRODUCT_CHANGE', [F.GOOD, F.GOOD])
        arts = self.store.artifacts(pid)
        self.assertEqual(len(arts), 1)
        self.assertEqual(self.store.project(pid)['iteration'], 1)
        self.assertFalse((Path(arts[0]['path']).parent.parent / 'v2').exists())
        self.assertEqual(eng._product_failures(pid), [])
        self.assertEqual(len(self.store.verifications(pid)), 2)

    def test_identical_passed_bundle_is_not_versioned(self):
        class Bundle(F.ExecutiveScript):
            def __call__(self, prompt, schema, *args, **kw):
                result, used, notes = super().__call__(prompt, schema, *args, **kw)
                if schema is E.PLAN:
                    result.update(artifact_kind='bundle', artifact_filename='app.py')
                if schema is E.BUILD:
                    result['files'] = [{'path': 'app.py', 'content': result['content']}]
                    result['content'] = ''
                return result, used, notes
        script = Bundle([F.GOOD, F.GOOD], ['PASS', 'PASS'], [self.report('PRODUCT_CHANGE'), F.ExecutiveAcceptanceTests.deliver])
        eng = self.engine(script)
        pid = self.store.new_project('make an add tool')
        result = eng.run(pid)
        self.assertEqual(result['state'], 'OWNER_REVIEW', result['pause_reason'])
        self.assertEqual(len(self.store.artifacts(pid)), 1)
        self.assertEqual(eng.consistency(pid), [])

    def test_older_latest_pass_is_reused_and_remains_the_feedback_baseline(self):
        script = F.ExecutiveScript([F.GOOD, F.BROKEN, F.GOOD], ['PASS', 'FAIL', 'PASS'],
                                  [self.report('PRODUCT_CHANGE'), F.ExecutiveAcceptanceTests.deliver])
        eng = self.engine(script)
        pid = self.store.new_project('make an add tool')
        result = eng.run(pid)
        self.assertEqual(result['state'], 'OWNER_REVIEW', result['pause_reason'])
        arts = self.store.artifacts(pid)
        self.assertEqual([a['iteration'] for a in arts], [1, 2])
        self.assertEqual(result['iteration'], 1)
        self.assertEqual(self.store.verifications(pid)[-1]['artifact_id'], arts[0]['id'])
        self.assertEqual(eng._baselines(pid)[0]['id'], arts[0]['id'])
        self.assertEqual(len(eng._product_failures(pid)), 1)
        eng.owner_review(pid, text='Recheck this working version')
        original = script.__call__
        def diagnose(*args, **kw):
            answer, used, notes = original(*args, **kw)
            if args[1] is E.DIAGNOSIS:
                answer['evidence_class'] = 'NO_PRODUCT_EVIDENCE'
            return answer, used, notes
        eng.llm = diagnose
        eng._owner_rework(pid)
        self.assertEqual(self.store.project(pid)['state'], 'VERIFYING')
        self.assertEqual(self.store.project(pid)['iteration'], 1)

    def test_empty_build_after_pass_does_not_become_no_change(self):
        script = F.ExecutiveScript([F.GOOD, ''], ['PASS'], [self.report('PRODUCT_CHANGE')])
        eng = self.engine(script)
        pid = self.store.new_project('make an add tool')
        self.store.update(pid, budget=1)
        result = eng.run(pid)
        self.assertEqual(result['state'], 'PAUSED')
        self.assertEqual(len(eng._product_failures(pid)), 1)
        self.assertEqual(self.store.verifications(pid)[-1]['verdict'], 'FAIL')
        self.assertFalse(self.store.events(pid, {'intentional_no_change'}))

    def test_same_artifact_route_survives_interruption(self):
        script = F.ExecutiveScript([F.GOOD], ['PASS', 'PASS'], [self.report('EVIDENCE_GAP'), F.ExecutiveAcceptanceTests.deliver])
        eng = self.engine(script)
        pid = self.store.new_project('make an add tool')
        for fn in (eng._created, eng._planning, eng._staffing, eng._executing, eng._verifying):
            fn(pid)
        self.assertEqual(self.store.project(pid)['state'], 'VERIFYING')
        self.assertEqual(len(self.store.verifications(pid)), 1)
        resumed = self.engine(script)
        self.assertEqual(resumed.run(pid)['state'], 'OWNER_REVIEW')
        self.assertEqual(len(self.store.verifications(pid)), 2)
        self.assertEqual(len(self.store.artifacts(pid)), 1)

    def test_nonproduct_rechecks_ignore_product_budget_but_obey_executive_cap(self):
        rounds = E.MAX_EXECUTIVE_REWORKS + 1
        script = F.ExecutiveScript([F.GOOD], ['PASS'] * rounds, [self.report('EVIDENCE_GAP')] * rounds)
        eng = self.engine(script)
        pid = self.store.new_project('make an add tool')
        self.store.update(pid, budget=0)
        result = eng.run(pid)
        self.assertEqual(result['state'], 'OWNER_REVIEW', result['pause_reason'])
        self.assertEqual(len(self.store.verifications(pid)), rounds)
        self.assertEqual(result['report']['goal_satisfied'], 'partly')
        self.assertEqual(result['report']['missing_evidence'], ['real use'])
        self.assertEqual(len(self.store.artifacts(pid)), 1)

    def test_legacy_executive_rework_is_not_implicitly_a_product_order(self):
        pid, eng, _ = self.run_case('OUTSIDE_AUTHORITY', reports=[self.report('OUTSIDE_AUTHORITY')])
        p = self.store.project(pid)
        p['plan']['ceo_directive'] = {'after_version': 1, 'directive': 'collect more evidence', 'gap_class': 'legacy-unknown'}
        self.store.update(pid, plan=p['plan'], state='REWORK', iteration=2)
        eng._rework(pid)
        self.assertEqual(self.store.project(pid)['state'], 'VERIFYING')
        self.assertEqual(self.store.project(pid)['iteration'], 1)


if __name__ == '__main__':
    unittest.main()
