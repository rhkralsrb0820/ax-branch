"""Outcome Attribution v1 rules (observational), on temporary stores only."""
import json
import shutil
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from axbranch import attribution as A
from axbranch.state import Store

MISCONFIGURED = {'name': 'pick', 'ok': False, 'probe_misconfigured': True, 'problems': ["invalid selector 'a[[b'"]}
ANY_STATUS = {'name': 'add log', 'ok': False, 'status': 201, 'problems': ['status 201, expected -1']}
CRASH = {'name': 'launch', 'ok': False, 'exit': 1, 'problems': ['crashed (exit 1)'],
         'output_tail': 'Traceback (most recent call last):\n  boom'}
MISMATCH = {'name': 'page', 'ok': False, 'problems': ["rendered page lacks ['합계']"]}


def checks(*steps, exit_code=0):
    return {'ok': not steps and exit_code == 0, 'exit_code': exit_code, 'output': 'ok',
            'runtime': {'ok': not steps, 'steps': list(steps)}}


def fail(findings=(), criteria=()):
    return {'verdict': 'FAIL', 'findings': list(findings), 'criteria': list(criteria)}


class AttributionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.store = Store(self.tmp / 'ax.sqlite3')
        self.pid = self.store.new_project('make a tool')
        self.store.update(self.pid, plan={'acceptance_criteria': ['works']})
        self.agent = self.store.add_agent(self.pid, 'Developer', 'claude')
        self.art = self.store.add_artifact(self.pid, 1, self.tmp / 'a.py', 'sha', 'python', self.agent)

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def verify(self, verdict, chk, result=None, provider='claude', artifact=None):
        vid = self.store.add_verification(self.pid, self.art if artifact is None else artifact, 1, verdict,
                                          result or fail(), chk, provider)
        return next(v for v in self.store.verifications(self.pid) if v['id'] == vid)

    def classes(self, a):
        return {(c['class'], c['role'], c['status']) for c in a['causes']}

    def test_invalid_check_is_harness_and_rules_out_product(self):
        for step in (MISCONFIGURED, ANY_STATUS):
            with self.subTest(step=step['name']):
                a = A.verification_causes(self.store, self.pid, self.verify('FAIL', checks(step)))
                self.assertEqual((a['primary'], a['primary_status']), ('HARNESS', 'VERIFIED'))
                self.assertIn(('PRODUCT', 'RULED_OUT', 'VERIFIED'), self.classes(a))

    def test_crash_is_product_with_the_producer_responsible(self):
        a = A.verification_causes(self.store, self.pid, self.verify('FAIL', checks(CRASH)))
        self.assertEqual((a['primary'], a['primary_status']), ('PRODUCT', 'VERIFIED'))
        primary = a['causes'][0]
        self.assertEqual((primary['agent_role'], primary['provider'], primary['artifact']), ('Developer', 'claude', self.art))
        selftest = A.verification_causes(self.store, self.pid, self.verify('FAIL', checks(exit_code=1)))
        self.assertEqual(selftest['primary'], 'PRODUCT')

    def test_model_judgment_alone_never_becomes_verified(self):
        verdict = fail([{'severity': 'major', 'kind': 'product', 'criterion': 0, 'issue': 'wrong total'}],
                       [{'index': 0, 'met': False}])
        a = A.verification_causes(self.store, self.pid, self.verify('FAIL', checks(), verdict))
        self.assertEqual((a['primary'], a['primary_status']), ('UNKNOWN', 'UNKNOWN'))
        self.assertIn(('PRODUCT', 'CONTRIBUTING', 'ESTIMATED'), self.classes(a))

    def test_ambiguous_mismatch_stays_unknown(self):
        a = A.verification_causes(self.store, self.pid, self.verify('FAIL', checks(MISMATCH)))
        self.assertEqual(a['primary'], 'UNKNOWN')
        self.assertFalse([c for c in a['causes'] if c['status'] == 'VERIFIED' and c['role'] != 'RULED_OUT'])

    def repair(self, fail, art=None):
        """An accepted harness repair, opened for `fail` (as engine._probe_review records it)."""
        pending = self.store.event(self.pid, 'probe_review_pending', artifact=art or self.art, verification=fail['id'])
        self.store.event(self.pid, 'probe_review', pending=pending, artifact=art or self.art,
                         disposition='HARNESS_REPAIR', repaired=True)

    def test_a_missing_deliverable_is_never_verified_agent_blame(self):
        # P-bbad3c v15-v20: empty answers came from transport/timeout limits, not the agent; the record cannot tell.
        self.store.event(self.pid, 'build_rejected', agent='Developer', provider='codex', reason='empty deliverable')
        first = self.verify('FAIL', {'ok': False, 'output': 'empty deliverable'}, provider='engine', artifact='')
        a = A.verification_causes(self.store, self.pid, first)
        self.assertEqual((a['primary'], a['primary_status']), ('UNKNOWN', 'UNKNOWN'))
        self.assertIn(('AGENT', 'CONTRIBUTING', 'ESTIMATED'), self.classes(a))
        self.assertIn(('PRODUCT', 'RULED_OUT', 'VERIFIED'), self.classes(a))
        # replay later: a newer rejection (other provider/reason) must not lend its evidence to the earlier FAIL
        self.store.event(self.pid, 'build_rejected', agent='Writer', provider='claude', reason='edits do not apply')
        self.verify('FAIL', {'ok': False}, provider='engine', artifact='')
        agent = next(c for c in A.history(self.store, self.pid)[first['id']]['causes'] if c['class'] == 'AGENT')
        self.assertEqual((agent['provider'], agent['agent_role']), ('codex', 'Developer'))
        self.assertIn('empty deliverable', agent['evidence'][0])

    def test_pause_reasons(self):
        cases = {'RateLimited: No provider available: codex: usage limit reached': ('PROVIDER', 'VERIFIED'),
                 'Rejected: Claude Code: 시간 초과(900초). 프로세스 트리 전체를 종료했습니다.': ('UNKNOWN', 'UNKNOWN'),
                 'Owner stopped the run': ('OWNER_CONSTRAINT', 'VERIFIED'),
                 'Owner approval needed (external_connection): the program would contact x': ('GOVERNANCE', 'VERIFIED'),
                 '6 builds failed verification. The standard is not lowered; Owner may resume': ('GOVERNANCE', 'VERIFIED'),
                 'Rejected: Claude: 사용 가능한 메모리가 300 MB로 부족해 실행하지 않았습니다': ('INFRA', 'VERIFIED'),
                 'Internal error KeyError: x (traceback: log)': ('ENGINE', 'VERIFIED'),
                 'NEEDS_DECISION: the same failure recurred': ('UNKNOWN', 'UNKNOWN')}
        for reason, expected in cases.items():
            with self.subTest(reason=reason):
                a = A.pause_causes(self.store, self.pid, reason)
                self.assertEqual((a['primary'], a['primary_status']), expected)
        quota = A.pause_causes(self.store, self.pid, 'RateLimited: No provider available: codex: usage limit reached')
        self.assertEqual(quota['causes'][0]['provider_state'], 'QUOTA_EXHAUSTED')
        timeout = A.pause_causes(self.store, self.pid, 'Rejected: Codex: timed out')
        self.assertIn(('PROVIDER', 'CONTRIBUTING', 'ESTIMATED'), self.classes(timeout))     # a candidate, not a verdict

    def test_history_separates_the_fail_from_the_unnecessary_rebuild_and_credits_validated_repairs(self):
        first = self.verify('FAIL', checks(ANY_STATUS))
        art2 = self.store.add_artifact(self.pid, 2, self.tmp / 'b.py', 'sha2', 'python', self.agent)
        h = A.history(self.store, self.pid)
        self.assertEqual(h[first['id']]['primary'], 'HARNESS')                    # the FAIL keeps its own cause
        self.assertEqual(h[art2]['primary'], 'ENGINE')                            # the rebuild is the engine's
        self.store.add_feedback(self.pid, 2, 'problem', 'it does not work')       # Owner asked: not an engine breach
        art3 = self.store.add_artifact(self.pid, 3, self.tmp / 'c.py', 'sha3', 'python', self.agent)
        self.assertNotIn(art3, A.history(self.store, self.pid))
        # same artifact: ambiguous FAIL, accepted harness repair, then PASS -> HARNESS VERIFIED
        amb = self.verify('FAIL', checks(MISMATCH), artifact=art3)
        self.repair(amb, art3)
        self.verify('PASS', checks(), {'verdict': 'PASS', 'findings': [], 'criteria': []}, artifact=art3)
        self.assertEqual(A.history(self.store, self.pid)[amb['id']]['primary_status'], 'VERIFIED')

    def test_a_repair_explains_only_its_own_fail_and_never_overrides_verified_infra(self):
        infra = self.verify('FAIL', checks({'name': 'ui', 'ok': False, 'problems': ['no headless browser found']}))
        other = self.verify('FAIL', checks(MISMATCH))           # ambiguous, but no repair was opened for it
        amb = self.verify('FAIL', checks(MISMATCH))
        self.repair(amb)
        self.repair(infra)                                       # even a repair opened for it: INFRA stays
        passed = self.verify('PASS', checks(), {'verdict': 'PASS', 'findings': [], 'criteria': []})
        self.assertEqual(A.repaired_fails(self.store, self.pid, passed), [amb['id']])
        h = A.history(self.store, self.pid)
        self.assertEqual((h[infra['id']]['primary'], h[other['id']]['primary'], h[amb['id']]['primary']),
                         ('INFRA', 'UNKNOWN', 'HARNESS'))

    def test_responsibility_names_the_provider_that_actually_produced(self):
        self.store.save_output(self.pid, 1, 1, 0, self.agent, 'codex', {'content': 'x'})     # failover: claude -> codex
        a = A.verification_causes(self.store, self.pid, self.verify('FAIL', checks(CRASH)))
        self.assertEqual((a['causes'][0]['agent_role'], a['causes'][0]['provider']), ('Developer', 'codex'))

    def test_ceo_self_assessment_is_not_a_source_and_replay_writes_nothing(self):
        v = self.verify('FAIL', checks(MISMATCH))
        before = A.verification_causes(self.store, self.pid, v)
        self.store.event(self.pid, 'decision_trace', who='CEO', proposed='rework', reason='product is broken',
                         evidence=['I am sure'], retrievals=[], knowledge_use=[])
        plan = self.store.project(self.pid)['plan']
        self.store.update(self.pid, plan={**plan, 'ceo_directive': {'gap_class': 'PRODUCT_DEFECT'}})
        self.assertEqual(A.verification_causes(self.store, self.pid, v), before)
        counts = [self.store.db.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] for t in ('events', 'verifications')]
        A.history(self.store, self.pid)
        self.assertEqual([self.store.db.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
                          for t in ('events', 'verifications')], counts)


class AttributionHookTests(unittest.TestCase):
    """The observational hooks: one append-only attribution per outcome subject; nothing in the run depends on it."""
    def setUp(self):
        AttributionTests.setUp(self)

    def tearDown(self):
        AttributionTests.tearDown(self)

    verify = AttributionTests.verify

    def current(self, subject):
        return [a['detail'] for a in self.store.attributions(self.pid) if a['detail']['subject'] == subject]

    def test_a_fail_gets_exactly_one_attribution_linked_to_its_outcomes(self):
        self.store.trace_action(self.pid, 'verify', 'verify:x:0', artifact=self.art)
        v = self.verify('FAIL', checks(ANY_STATUS))
        (a,) = self.current(v['id'])
        self.assertEqual((a['primary'], a['primary_status'], a['rules_version']), ('HARNESS', 'VERIFIED', A.RULES_VERSION))
        outcome = [o['id'] for o in self.store.events(self.pid, {'outcome_trace'}) if o['detail'].get('verification') == v['id']]
        self.assertEqual(a['outcomes'], outcome)
        self.assertEqual(len([e for e in self.store.events(self.pid, {'attribution_trace'})
                              if e['detail']['subject'] == v['id']]), 1)
        self.assertEqual(self.current('nothing'), [])
        passed = self.verify('PASS', checks(), {'verdict': 'PASS', 'findings': [], 'criteria': []})
        self.assertEqual(self.current(passed['id']), [])                  # a PASS has no failure cause

    def test_validated_repair_supersedes_without_rewriting_history(self):
        amb = self.verify('FAIL', checks(MISMATCH))
        first = self.current(amb['id'])[0]
        self.assertEqual(first['primary'], 'UNKNOWN')
        AttributionTests.repair(self, amb)
        self.verify('PASS', checks(), {'verdict': 'PASS', 'findings': [], 'criteria': []})
        self.verify('PASS', checks(), {'verdict': 'PASS', 'findings': [], 'criteria': []})     # no second supersede
        history = [e for e in self.store.events(self.pid, {'attribution_trace'}) if e['detail']['subject'] == amb['id']]
        self.assertEqual([h['detail']['primary'] for h in history], ['UNKNOWN', 'HARNESS'])
        self.assertEqual(history[1]['detail']['supersedes'], history[0]['id'])
        self.assertEqual([c['primary'] for c in self.current(amb['id'])], ['HARNESS'])

    def test_pause_and_unnecessary_rebuild_are_attributed(self):
        self.store.pause(self.pid, 'RateLimited: No provider available: codex: usage limit reached')
        pause = [a['detail'] for a in self.store.attributions(self.pid) if a['detail']['subject'].startswith('pause:')]
        self.assertEqual((pause[0]['primary'], pause[0]['causes'][0]['provider_state']), ('PROVIDER', 'QUOTA_EXHAUSTED'))
        fail = self.verify('FAIL', checks(ANY_STATUS))
        art2 = self.store.add_artifact(self.pid, 2, self.tmp / 'b.py', 'sha2', 'python', self.agent)
        self.assertEqual(self.current(art2)[0]['primary'], 'ENGINE')
        self.assertEqual(self.current(fail['id'])[0]['primary'], 'HARNESS')    # the FAIL keeps its own cause

    def test_crashing_rebuild_and_repair_rules_are_recorded_not_raised(self):
        fail = self.verify('FAIL', checks(ANY_STATUS))
        with mock.patch.object(A, 'engine_breach', side_effect=RuntimeError('breach bug')):
            art2 = self.store.add_artifact(self.pid, 2, self.tmp / 'b.py', 'sha2', 'python', self.agent)
        self.assertIn(art2, [a['id'] for a in self.store.artifacts(self.pid)])
        AttributionTests.repair(self, fail)
        with mock.patch.object(A, 'repaired_fails', side_effect=RuntimeError('repair bug')):
            passed = self.verify('PASS', checks(), {'verdict': 'PASS', 'findings': [], 'criteria': []})
        self.assertEqual(passed['verdict'], 'PASS')
        for subject, bug in ((art2, 'breach bug'), (passed['id'], 'repair bug')):
            (a,) = self.current(subject)
            self.assertEqual((a['primary'], a['error']), ('UNKNOWN', f'RuntimeError: {bug}'))
        self.assertEqual(self.current(fail['id'])[0]['primary'], 'HARNESS')     # untouched by the failed repair rule

    def test_a_crashing_rule_changes_nothing_in_the_run(self):
        from tests import test_engine as F
        from axbranch import engine as E

        def run(break_rules):
            store = Store(self.tmp / f'run-{break_rules}.sqlite3')
            try:
                eng = E.Engine(store, workspace=self.tmp / f'ws-{break_rules}', vault=self.tmp / 'vault',
                               gai_db=self.tmp / 'none.db', llm=F.Script([F.BROKEN, F.GOOD], ['FAIL', 'PASS']))
                (self.tmp / 'vault').mkdir(exist_ok=True)
                with mock.patch.object(A, 'verification_causes', side_effect=RuntimeError('rule bug')) if break_rules \
                        else mock.patch.object(A, 'RULES_VERSION', A.RULES_VERSION):
                    pid = store.new_project('make an add tool')
                    p = eng.run(pid)
                return ((p['state'], p['iteration'], p['budget']),
                        [(v['iteration'], v['verdict']) for v in store.verifications(pid)],
                        [e['detail']['to'] for e in store.events(pid, {'state'})],
                        [a['detail'] for a in store.events(pid, {'attribution_trace'})])
            finally:
                store.close()
        normal, broken = run(False), run(True)
        self.assertEqual(normal[:3], broken[:3])                                   # same run, verdicts, states
        self.assertEqual([(a['primary'], 'error' in a) for a in broken[3]], [('UNKNOWN', True)])
        self.assertNotIn('error', normal[3][0])


if __name__ == '__main__':
    unittest.main()
