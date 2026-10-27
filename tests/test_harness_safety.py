"""Harness safety and recovery with temporary stores and scripted agents only."""
import json
import unittest
from unittest import mock

from axbranch import engine as E, runtime
from axbranch.state import Store, Rejected, stop_outcome
from tests import test_engine as fixtures
from tests.test_engine import Script, GOOD

PROBE = {'name': 'save', 'args': ['--save', 'item'], 'stdin': 'required input',
         'http_method': 'POST', 'http_path': '/save', 'http_body': '{"item": 1}',
         'expect_exit': 0, 'expect_status': 201, 'expect_contains': ['saved'], 'expect_absent': ['error']}
SPEC = {'mode': 'cli', 'owner_launch': 'normal launch', 'launch_args': ['--bad'], 'probes': [PROBE]}
BAD = {'ok': False, 'mode': 'cli', 'steps': [
    {'name': 'save', 'ok': False, 'problems': ['output lacks saved'], 'exit': 0}], 'notes': []}
OK = {'ok': True, 'mode': 'cli', 'steps': [], 'notes': []}


class ReviewScript(Script):
    def __init__(self, disposition='UNRESOLVED', proposed=None, equivalent=False, fail_on=None):
        super().__init__([GOOD, GOOD], ['PASS'] * 20, fail_on=fail_on)
        self.disposition, self.proposed, self.equivalent = disposition, proposed, equivalent
        self.harness_blocker = False

    def __call__(self, prompt, schema, *args, **kw):
        if schema is E.PROBE_EQUIVALENCE:
            self.prompts.append((schema, kw.get('prefer'), prompt))
            return {'equivalent': self.equivalent, 'evidence': 'Source and approved normal launch were compared.'}, 'codex', []
        result, used, notes = super().__call__(prompt, schema, *args, **kw)
        if schema is E.PROBE_REVIEW:
            context = json.JSONDecoder().raw_decode(prompt[prompt.index('\n{\n') + 1:])[0]
            result.update(disposition=self.disposition, evidence='Concrete source evidence for this scripted case.',
                          runtime=self.proposed if self.proposed is not None else context['runtime'])
        if schema is E.VERDICT and self.harness_blocker:
            result['criteria'] = []
            result['findings'] = [{'kind': 'harness', 'severity': 'major', 'criterion': 0,
                                   'issue': 'incomplete evidence', 'evidence': 'no criterion judgment'}]
        return result, used, notes


class PreservationTests(unittest.TestCase):
    def test_exact_status_and_assertions_survive_even_validated_input_repair(self):
        for equivalent in (False, True):
            for status in (202, 200, 0, -1, 401):
                proposed = {**PROBE, 'expect_status': status, 'expect_exit': -1,
                            'expect_contains': [], 'expect_absent': []}
                kept, _ = E.preserve_probes([PROBE], [proposed], equivalent=equivalent)
                self.assertEqual(kept, [PROBE])
        kept, _ = E.preserve_probes([{**PROBE, 'expect_status': -1}], [{**PROBE, 'expect_status': 0}])
        self.assertEqual(kept[0]['expect_status'], 0)

    def test_method_path_args_inputs_and_click_sequence_cannot_change(self):
        for field, value in [('http_method', 'GET'), ('http_path', '/health'), ('args', []),
                             ('stdin', ''), ('http_body', '')]:
            with self.subTest(field=field):
                kept, _ = E.preserve_probes([PROBE], [{**PROBE, field: value}])
                self.assertEqual(kept, [PROBE])
        hostile = {**PROBE, 'http_method': 'DELETE', 'http_headers': ['Origin: http://evil.example'], 'expect_status': 403}
        for headers in ([], ['Origin: http://127.0.0.1']):             # the hostile Origin is the check itself
            kept, _ = E.preserve_probes([hostile], [{**hostile, 'http_headers': headers}])
            self.assertEqual(kept, [hostile])
        click = {**PROBE, 'http_method': 'BROWSER', 'http_body': '#input||#save||#confirm'}
        for body in ('#input', '#confirm||#save||#input', ''):
            kept, _ = E.preserve_probes([click], [{**click, 'http_body': body}])
            self.assertEqual(kept, [click])
        second = {**PROBE, 'name': 'read', 'http_method': 'GET'}
        kept, _ = E.preserve_probes([PROBE, second], [second, PROBE])
        self.assertEqual(kept, [PROBE, second])

    def test_duplicate_names_cannot_replace_a_different_required_action(self):
        other = {**PROBE, 'http_path': '/another-required-target'}
        for before, proposed in (([PROBE, other], [PROBE]), ([PROBE], [PROBE, other])):
            with self.assertRaises(Rejected):
                E.preserve_probes(before, proposed)

    def test_invalid_http_target_is_a_harness_configuration_error(self):
        with mock.patch.object(runtime.http.client, 'HTTPConnection') as connection:
            connection.return_value.request.side_effect = runtime.http.client.InvalidURL('control character in path')
            step = runtime._http(12345, PROBE)
        self.assertFalse(step['ok'])
        self.assertEqual(runtime.classify_step(step), 'harness')

    def test_strategy_cannot_change_mode_or_launch_contract(self):
        kept, _ = E.preserve_runtime(SPEC, {**SPEC, 'mode': 'none', 'launch_args': ['--self-test']})
        self.assertEqual(kept, SPEC)

    def test_cli_crash_uses_exit_and_stderr_when_explicit_exit_assertion_fails(self):
        base = mock.Mock()
        base.record.return_value = {}
        proc = base.start.return_value
        proc.wait.return_value = 1
        proc.streams.return_value = ('', 'Traceback (most recent call last): ValueError')
        step = runtime._cli(base, {**PROBE, 'expect_contains': [], 'expect_absent': []})
        self.assertIn('exit 1, expected 0', step['problems'])
        self.assertEqual(runtime.classify_step(step), 'product')

    def test_uncertain_browser_evidence_and_crashes(self):
        for step in ({'probe_misconfigured': True, 'problems': ['matched nothing'],
                      'clicks': [{'problem': 'missing'}]},
                     {'harness_error': True, 'problems': ['no visible-text report']},
                     {'harness_error': True, 'problems': ['requests did not settle']},
                     {'problems': ['browser did not finish within 90s (2 attempts)']}):
            self.assertEqual(runtime.classify_step({'ok': False, **step}), 'ambiguous')
        self.assertEqual(runtime.classify_step({'ok': False, 'probe_misconfigured': True,
                        'clicks': [{'problem': 'invalid'}], 'problems': ['invalid selector']}), 'harness')
        for extra in ({}, {'harness_error': True}, {'probe_misconfigured': True}):
            self.assertEqual(runtime.classify_step({'ok': False, 'exit': 1,
                'stderr_tail': 'Traceback (most recent call last): ValueError',
                'problems': ['exit 1, expected 0'], **extra}), 'product')
        self.assertEqual(runtime.classify_step({'ok': False, 'exit': -11, 'problems': []}), 'product')
        self.assertEqual(runtime.classify_step({'ok': False, 'exit': 2,
                         'problems': ['exit 2, expected 0']}), 'ambiguous')


class HarnessSafetyTests(unittest.TestCase):
    setUp, tearDown, engine = fixtures.EngineTests.setUp, fixtures.EngineTests.tearDown, fixtures.EngineTests.engine

    def prepared(self, script=None):
        script = script or ReviewScript()
        eng = self.engine(script)
        pid = self.store.new_project('save an item through the normal interface')
        eng.run(pid, stop_at='VERIFYING')
        p = self.store.project(pid)
        p['plan']['runtime'] = json.loads(json.dumps(SPEC))
        self.store.update(pid, plan=p['plan'])
        eng.checks = mock.Mock(side_effect=self.isolated_check({'ok': True, 'output': '', 'ran': ['self-test']}))
        eng.runtime_evidence = mock.Mock(return_value=BAD)
        return eng, pid, script

    def isolated_check(self, result):
        """A mocked check that still requires the engine to ask for OS isolation of generated code."""
        def check(*args, isolate):
            self.assertIs(isolate, True)
            return dict(result)       # a fresh dict per call, like a real check
        return check

    def test_product_failure_cannot_hide_behind_harness_blocker(self):
        for selftest in (False, True):
            with self.subTest(selftest=selftest):
                script = ReviewScript()
                script.harness_blocker = True
                eng, pid, _ = self.prepared(script)
                if selftest:
                    eng.checks.side_effect = self.isolated_check({'ok': False, 'output': 'assert failed'})
                else:
                    eng.runtime_evidence.return_value = {**BAD, 'steps': [
                        {'name': 'save', 'ok': False, 'status': 500, 'problems': ['server error']}]}
                p = eng.run(pid, stop_at='REWORK')
                self.assertEqual(p['state'], 'REWORK', p['pause_reason'])
                self.assertEqual(len(eng._product_failures(pid)), 1)
                self.assertEqual(self.store.events(pid, {'probe_review_pending'}), [])
                self.assertTrue(any(f.get('kind') == 'product' for f in self.store.verifications(pid)[-1]['result']['findings']))

    PRODUCT_500 = {'name': 'save', 'ok': False, 'status': 500, 'problems': ['server error']}
    PROSE_ACTION = {'name': 'clean windows scenario', 'ok': False, 'probe_misconfigured': True,
                    'problems': ["browser action 'Independent clean-copy scenario: copy the release' is not a CSS selector"]}

    def test_unexecutable_check_is_reviewed_even_when_the_product_also_failed(self):
        # P-20261016-5fb8d6 v7-v22: a product failure skipped probe review, the contract preserved the prose
        # browser action, and it failed every round until "the same failure" stopped the project.
        eng, pid, _ = self.prepared(ReviewScript('UNRESOLVED'))
        eng.runtime_evidence.return_value = {**BAD, 'steps': [self.PRODUCT_500, self.PROSE_ACTION]}
        p = eng.run(pid)
        pending = self.store.events(pid, {'probe_review_pending'})[0]['detail']
        self.assertEqual(([s['name'] for s in pending['steps']], pending['product_failed']), (['clean windows scenario'], True))
        self.assertEqual(p['state'], 'PAUSED')
        self.assertIn('cannot be executed here', p['pause_reason'])
        self.assertIn('clean windows scenario', p['pause_reason'])            # the decision names the check
        v = self.store.verifications(pid)[-1]
        self.assertEqual(E.failure_code(v), 'product:save')                     # the repeat signature ignores it

    def test_a_failing_self_test_keeps_one_signature_with_or_without_an_invalid_probe(self):
        base = {'provider': 'claude', 'verdict': 'FAIL', 'result': {'findings': [], 'criteria': []}}
        bad = {'name': 'bad-selector', 'ok': False, 'probe_misconfigured': True, 'problems': ["'a[[' is not a CSS selector"]}
        with_probe = {**base, 'checks': {'ok': False, 'exit_code': 1, 'output': 'AssertionError',
                                         'runtime': {'ok': False, 'steps': [bad]}}}
        without = {**base, 'checks': {'ok': False, 'exit_code': 1, 'output': 'AssertionError',
                                      'runtime': {'ok': True, 'steps': []}}}
        self.assertEqual((E.failure_code(with_probe), E.failure_code(without)),
                         ('product:deterministic checks', 'product:deterministic checks'))
        harness_only = {**base, 'checks': {'ok': True, 'exit_code': 0, 'output': 'PASS', 'runtime': {'ok': False, 'steps': [bad]}}}
        self.assertEqual(E.failure_code(harness_only), 'non-product:bad-selector')

    def test_reproduction_by_unexecutable_checks_only_is_not_a_reproduction(self):
        script = ReviewScript('UNRESOLVED')
        eng, pid, _ = self.prepared(script)
        eng.runtime_evidence.side_effect = [OK]
        self.assertEqual(eng.run(pid)['state'], 'OWNER_REVIEW')
        eng.owner_review(pid, works=False, text='the local service is unreachable when I launch it')
        eng.runtime_evidence.side_effect = [OK, {**BAD, 'steps': [self.PROSE_ACTION]}] + [OK] * 10
        eng.run(pid, stop_at='STAFFING')
        repro = self.store.events(pid, {'reproduction'})[-1]['detail']
        self.assertEqual((repro['revised_spec_ok'], repro['reproduced'], repro['unexecutable']),
                         (False, False, ['clean windows scenario']))
        rework = self.store.project(pid)['plan']['owner_rework']
        self.assertFalse(rework['reproduced_on_previous_version'])

    def test_launch_only_repair_reverifies_same_artifact_and_persists_decision(self):
        proposed = {**SPEC, 'launch_args': []}
        eng, pid, script = self.prepared(ReviewScript('HARNESS_REPAIR', proposed, equivalent=True))
        before = self.store.artifacts(pid)
        eng.runtime_evidence.side_effect = [BAD, OK]
        p = eng.run(pid)
        self.assertEqual(p['state'], 'OWNER_REVIEW', p['pause_reason'])
        self.assertEqual(self.store.artifacts(pid), before)
        self.assertEqual(p['iteration'], before[0]['iteration'])
        review = self.store.events(pid, {'probe_review'})[0]['detail']
        self.assertEqual(review['disposition'], 'HARNESS_REPAIR')
        self.assertEqual(review['before']['probes'], review['after']['probes'])
        self.assertNotEqual(review['before']['launch_args'], review['after']['launch_args'])
        self.assertTrue(review['equivalence']['equivalent'])
        self.assertEqual(len(eng._product_failures(pid)), 0)
        self.assertEqual([v['verdict'] for v in self.store.verifications(pid)], ['FAIL', 'PASS'])
        self.assertEqual(sum(s is E.BUILD for s, _, _ in script.prompts), 1)

    def test_rejected_equivalence_keeps_spec_and_blocks_without_rebuild(self):
        eng, pid, _ = self.prepared(ReviewScript('HARNESS_REPAIR', {**SPEC, 'launch_args': ['--self-test']}))
        p = eng.run(pid)
        self.assertEqual(p['plan']['runtime'], SPEC)
        self.assertEqual(self.store.events(pid, {'probe_review'})[0]['detail']['disposition'], 'UNRESOLVED')
        self.assertEqual((p['state'], p['resume_state'], p['iteration']), ('PAUSED', 'VERIFYING', 1))

    def test_unchanged_probes_never_imply_product_defect(self):
        eng, pid, _ = self.prepared()
        p = eng.run(pid)
        self.assertEqual(stop_outcome(p)[0], 'BLOCKED')
        self.assertEqual(len(eng._product_failures(pid)), 0)
        self.assertEqual(len(self.store.artifacts(pid)), 1)

    def test_explicit_product_disposition_condemns_identical_bytes(self):
        eng, pid, _ = self.prepared(ReviewScript('PRODUCT_DEFECT'))
        self.store.update(pid, budget=2)
        eng.run(pid, stop_at='REWORK')
        self.assertEqual(self.store.events(pid, {'probe_review'})[0]['detail']['disposition'], 'PRODUCT_DEFECT')
        self.assertEqual(len(eng._product_failures(pid)), 1)
        eng.run(pid)
        self.assertIn('identical to v1', self.store.events(pid, {'build_rejected'})[-1]['detail']['reason'])
        self.assertEqual(len(self.store.artifacts(pid)), 1)

    def test_known_harness_error_cannot_be_reclassified_into_rebuild(self):
        eng, pid, _ = self.prepared(ReviewScript('PRODUCT_DEFECT'))
        eng.runtime_evidence.return_value = {**BAD, 'steps': [
            {'name': 'save', 'ok': False, 'probe_misconfigured': True, 'problems': ['invalid selector']}]}
        p = eng.run(pid)
        self.assertEqual((p['state'], p['resume_state'], p['iteration']), ('PAUSED', 'VERIFYING', 1))
        self.assertEqual(eng._product_failures(pid), [])

    def test_pending_review_resumes_without_duplicate_verification(self):
        eng, pid, script = self.prepared(ReviewScript('HARNESS_REPAIR', {**SPEC, 'launch_args': []},
                                                     equivalent=True, fail_on=E.PROBE_REVIEW))
        eng.runtime_evidence.side_effect = [BAD, OK]
        p = eng.run(pid)
        self.assertEqual(p['state'], 'PAUSED')
        self.assertEqual(len(self.store.verifications(pid)), 1)
        self.assertEqual(len(self.store.events(pid, {'probe_review_pending'})), 1)
        self.assertEqual(self.store.events(pid, {'probe_review'}), [])
        db = self.tmp / 'ws' / 'axbranch.sqlite3'
        self.store.close()
        self.store = Store(db)
        eng.store = self.store
        self.store.resume(pid)
        p = eng.run(pid)
        self.assertEqual(p['state'], 'OWNER_REVIEW', p['pause_reason'])
        self.assertEqual(eng.runtime_evidence.call_count, 2)
        self.assertEqual(len(self.store.events(pid, {'probe_review_pending'})), 1)
        self.assertEqual(len(self.store.artifacts(pid)), 1)

    def test_completed_decision_survives_interruption_before_routing(self):
        for disposition in ('PRODUCT_DEFECT', 'HARNESS_REPAIR', 'UNRESOLVED'):
            with self.subTest(disposition=disposition):
                eng, pid, script = self.prepared(ReviewScript(disposition, {**SPEC, 'launch_args': []}, True))
                event = self.store.event
                def interrupt(project, kind, **detail):
                    if kind == 'probe_review_applied':
                        raise KeyboardInterrupt('interrupt routing transaction')
                    return event(project, kind, **detail)
                with mock.patch.object(self.store, 'event', side_effect=interrupt):
                    with self.assertRaises(KeyboardInterrupt):
                        eng._verifying(pid)
                self.assertEqual(self.store.project(pid)['state'], 'VERIFYING')
                self.assertEqual(len(self.store.events(pid, {'probe_review'})), 1)
                self.assertEqual(self.store.events(pid, {'probe_review_applied'}), [])
                calls = len(script.prompts)
                eng._verifying(pid)
                self.assertEqual(len(script.prompts), calls)
                self.assertEqual(len(self.store.events(pid, {'probe_review_applied'})), 1)
                state = self.store.project(pid)['state']
                self.assertEqual(state, {'PRODUCT_DEFECT': 'REWORK', 'HARNESS_REPAIR': 'VERIFYING',
                                         'UNRESOLVED': 'PAUSED'}[disposition])
                self.assertEqual(len(self.store.verifications(pid)), 1)

    def test_plan_and_review_completion_are_atomic(self):
        eng, pid, _ = self.prepared(ReviewScript('HARNESS_REPAIR', {**SPEC, 'launch_args': []}, True))
        event = self.store.event
        def interrupt(project, kind, **detail):
            if kind == 'probe_review':
                raise KeyboardInterrupt('interrupt completion transaction')
            return event(project, kind, **detail)
        with mock.patch.object(self.store, 'event', side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt):
                eng._verifying(pid)
        self.assertEqual(self.store.project(pid)['plan']['runtime'], SPEC)
        self.assertEqual(self.store.events(pid, {'probe_review'}), [])
        self.assertEqual(len(self.store.events(pid, {'probe_review_pending'})), 1)
        eng._verifying(pid)
        self.assertEqual(self.store.project(pid)['plan']['runtime']['launch_args'], [])
        self.assertEqual(len(self.store.verifications(pid)), 1)

    def test_harness_rechecks_do_not_spend_budget_or_trigger_product_recurrence(self):
        eng, pid, script = self.prepared()
        self.store.update(pid, budget=1)
        before = self.store.artifacts(pid)
        for i in range(8):
            if i:
                self.store.resume(pid)
            p = eng.run(pid)
            self.assertEqual(stop_outcome(p)[0], 'BLOCKED')
            self.assertEqual(eng._product_failures(pid), [])
            self.assertIsNone(eng._repeated_failure(pid))
            self.assertEqual(p['iteration'], 1)
        self.assertEqual(self.store.artifacts(pid), before)
        self.assertEqual(len(self.store.verifications(pid)), 8)
        self.assertEqual(sum(s is E.PROBE_REVIEW for s, _, _ in script.prompts), 1)
        self.store.resume(pid)
        eng.runtime_evidence.return_value = {**BAD, 'steps': [
            {'name': 'save', 'ok': False, 'status': 500, 'problems': ['server error']}]}
        self.store.update(pid, budget=2)
        p = eng.run(pid, stop_at='REWORK')
        self.assertEqual(p['state'], 'REWORK', p['pause_reason'])
        self.assertEqual(len(eng._product_failures(pid)), 1)
        self.assertIsNone(eng._repeated_failure(pid))

    def test_after_fail_refuses_harness_only_rebuild_even_if_called_directly(self):
        eng, pid, _ = self.prepared()
        eng.run(pid)
        self.store.resume(pid)
        eng._after_fail(pid, self.store.project(pid))
        p = self.store.project(pid)
        self.assertEqual((p['state'], p['resume_state'], p['iteration']), ('PAUSED', 'VERIFYING', 1))

    def test_legacy_rework_recovery_cannot_rebuild_a_harness_failure(self):
        eng, pid, _ = self.prepared()
        eng.run(pid)
        self.store.update(pid, state='REWORK')
        p = eng.run(pid)
        self.assertEqual((p['state'], p['resume_state'], p['iteration']), ('PAUSED', 'VERIFYING', 1))
        self.assertEqual(len(self.store.artifacts(pid)), 1)

    def test_product_build_count_deduplicates_rechecks(self):
        eng, pid, _ = self.prepared(ReviewScript('PRODUCT_DEFECT'))
        eng.run(pid, stop_at='REWORK')
        v = self.store.verifications(pid)[-1]
        self.store.add_verification(pid, v['artifact_id'], v['iteration'], 'FAIL', v['result'], v['checks'], v['provider'])
        self.assertEqual(len(eng._product_failures(pid)), 1)
        self.assertIsNone(eng._repeated_failure(pid))

    def test_ineffective_repair_stops_after_one_review_without_rebuild(self):
        eng, pid, script = self.prepared(ReviewScript('HARNESS_REPAIR', {**SPEC, 'launch_args': []}, True))
        p = eng.run(pid)
        self.assertEqual(stop_outcome(p)[0], 'BLOCKED')
        self.assertEqual(len(self.store.verifications(pid)), 2)
        self.assertEqual(len(self.store.artifacts(pid)), 1)
        self.assertEqual(eng._product_failures(pid), [])
        self.assertEqual(sum(s is E.PROBE_REVIEW for s, _, _ in script.prompts), 1)


if __name__ == '__main__':
    unittest.main()
