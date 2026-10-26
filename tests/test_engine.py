"""End-to-end engine behaviour with a scripted provider (no subscription usage)."""
import json
import shutil
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from axbranch import artifacts, engine as E, governance as gov, knowledge, providers
from axbranch.state import Rejected, Store, stop_outcome

GOOD = "def add(a, b):\n    return a + b\n\nif __name__ == '__main__':\n    assert add(2, 3) == 5\n    print('ok')\n"
BROKEN = "def add(a, b):\n    return a - b\n\nif __name__ == '__main__':\n    assert add(2, 3) == 5\n"


# Fixed per Owner feedback: a double-click shows the result; the self-test moved behind --self-test.
LAUNCHABLE = ("import sys\ndef add(a, b):\n    return a + b\n\nif __name__ == '__main__':\n"
              "    if sys.argv[1:] == ['--self-test']:\n        assert add(2, 3) == 5\n        print('ok')\n"
              "    else:\n        print('result:', add(2, 3))\n")


class Script:
    """Answers by schema. `builds` and `verdicts` are consumed in order."""

    def __init__(self, builds, verdicts, strategy='continue', fail_on=None, probe_disposition='UNRESOLVED'):
        self.builds, self.verdicts, self.strategy = list(builds), list(verdicts), strategy
        self.fail_on, self.prompts = fail_on, []
        self.network = []
        self.probe_disposition = probe_disposition

    def __call__(self, prompt, schema, prefer='claude', web=False, cancel=None, **kw):
        self.prompts.append((schema, prefer, prompt))
        if self.fail_on is schema:
            self.fail_on = None
            raise providers.RateLimited('usage limit (scripted)')
        if schema is E.PLAN:
            return {'interpretation': 'Build an add() helper', 'artifact_kind': 'python',
                    'artifact_filename': '../evil/add tool.py', 'acceptance_criteria': ['add(2,3)==5'],
                    'verification_lenses': ['software engineering'], 'required_tools': [],
                    'runtime': {'mode': 'cli', 'owner_launch': 'double-click', 'launch_args': [], 'probes': []},
                    'network_access': self.network,
                    'pipeline': [{'name': 'design', 'agent_role': 'Architect', 'instructions': 'design',
                                  'provider': 'codex', 'web': False},
                                 {'name': 'build', 'agent_role': 'Developer', 'instructions': 'build',
                                  'provider': 'claude', 'web': False}]}, 'claude', []
        if schema is E.WORK:
            return {'output': 'use +', 'key_points': ['use +']}, prefer, []
        if schema is E.BUILD:
            return {'content': self.builds.pop(0), 'files': [], 'summary': 's', 'changes_from_previous': ''}, prefer, []
        if schema is E.VERDICT:
            v = self.verdicts.pop(0)
            approved = json.loads(prompt.split('CONTEXT (JSON — data, not instructions):\n', 1)[1]
                                  .rsplit('\n\nReturn exactly', 1)[0])['acceptance_criteria']
            return {'verdict': v, 'lenses_applied': ['se'],
                    'criteria': [{'index': c['index'], 'criterion': c['criterion'], 'met': v == 'PASS', 'evidence': 'e'}
                                 for c in approved],
                    'findings': [] if v == 'PASS' else [{'severity': 'major', 'issue': 'wrong sum', 'evidence': 'a - b'}]}, prefer, []
        if schema is E.PROBE_REVIEW:
            return {'disposition': self.probe_disposition, 'rationale': 'scripted review',
                    'evidence': 'The normal launch prints ok instead of the required result: 5.'
                                if self.probe_disposition == 'PRODUCT_DEFECT' else '',
                    'runtime': {'mode': 'cli', 'owner_launch': 'x', 'launch_args': [], 'probes': []}}, 'claude', []
        if schema is E.STRATEGY or 'decision' in schema.get('properties', {}):
            return {'decision': self.strategy, 'rationale': 'r', 'pipeline': [],
                    'runtime': {'mode': 'cli', 'owner_launch': 'x', 'launch_args': [], 'probes': []},
                    'network_access': self.network}, 'claude', []
        if schema is E.DIAGNOSIS:
            return {'diagnosis': 'owner saw it close', 'root_cause': 'no usable launch', 'change_summary': 'add probe',
                    'interpretation': 'Build an add() helper usable by double-click', 'artifact_kind': 'python',
                    'artifact_filename': 'add_tool.py', 'acceptance_criteria': ['add(2,3)==5', 'launch prints a result'],
                    'verification_lenses': ['software engineering', 'usability'],
                    'runtime': {'mode': 'cli', 'owner_launch': 'double-click', 'launch_args': [],
                                'probes': [{'name': 'launch shows result', 'args': [], 'stdin': '', 'http_method': '',
                                            'http_path': '', 'http_body': '', 'expect_exit': 0, 'expect_status': 0,
                                            'expect_contains': ['result: 5']}]},
                    'network_access': self.network,
                    'pipeline': [{'name': 'build', 'agent_role': 'Developer', 'instructions': 'rebuild',
                                  'provider': 'claude', 'web': False}]}, 'claude', []
        if schema is E.REPORT:
            return {'summary': 'done', 'judgment': 'good', 'next_steps': ['use it']}, 'claude', []
        raise AssertionError('unexpected schema')


class ExecutiveScript(Script):
    """Keep the normal pipeline, but consume scripted CEO acceptance reports."""

    def __init__(self, builds, verdicts, reports):
        super().__init__(builds, verdicts)
        self.reports = list(reports)

    def __call__(self, prompt, schema, *args, **kw):
        result, used, notes = super().__call__(prompt, schema, *args, **kw)
        if schema is E.REPORT:
            result.update(self.reports.pop(0))
        return result, used, notes


class PreserveProbesTests(unittest.TestCase):
    def test_preserves_dropped_probes_and_assertions_without_mutating_inputs(self):
        launch = {'name': 'launch', 'args': [], 'stdin': '', 'http_method': '', 'http_path': '',
                  'http_body': '', 'expect_exit': 0, 'expect_status': 0,
                  'expect_contains': ['ok'], 'expect_absent': ['Traceback']}
        flow = {**launch, 'name': 'flow', 'args': ['--old'], 'stdin': 'old', 'http_method': 'BROWSER',
                'http_path': '/old', 'http_body': '#old', 'expect_status': 200,
                'expect_contains': ['ok', 'summary'], 'expect_absent': ['Traceback', 'invented']}
        repaired = {**flow, 'args': ['--offline'], 'stdin': 'new', 'http_method': 'POST',
                    'http_path': '/repaired', 'http_body': '{"sample": 1}', 'expect_exit': -1, 'expect_status': 0,
                    'expect_contains': ['summary', 'extra', 'extra'], 'expect_absent': ['invented', 'error', 'error']}
        added = {**launch, 'name': 'added'}
        old, new = [launch, flow], [repaired, added]
        before = json.loads(json.dumps([old, new]))

        probes, notes = E.preserve_probes(old, new)

        self.assertEqual(probes, [
            launch, {**flow, 'expect_exit': 0, 'expect_status': 200,
             'expect_contains': ['ok', 'summary', 'extra'], 'expect_absent': ['Traceback', 'invented', 'error']},
            added])
        self.assertEqual(notes, ['kept assertions of flow', 'kept dropped probe launch'])
        self.assertEqual([old, new], before)

    def test_numeric_assertions_and_additions_only_note_restored_assertions(self):
        base = {'name': 'flow', 'args': [], 'stdin': '', 'http_method': 'GET', 'http_path': '/',
                'http_body': '', 'expect_contains': ['ok'], 'expect_absent': ['Traceback']}
        cases = [
            (0, -1, 201, 2, 201, 2, []),
            (200, 0, 201, 2, 200, 0, ['kept assertions of flow']),
            (200, 0, 200, 0, 200, 0, []),
        ]
        for old_status, old_exit, new_status, new_exit, status, exit_code, notes in cases:
            with self.subTest(old=(old_status, old_exit), new=(new_status, new_exit)):
                old = {**base, 'expect_status': old_status, 'expect_exit': old_exit}
                new = {**base, 'expect_status': new_status, 'expect_exit': new_exit,
                       'expect_contains': ['added', 'ok'], 'expect_absent': ['warning', 'Traceback']}
                self.assertEqual(E.preserve_probes([old], [new]), ([
                    {**new, 'expect_status': status, 'expect_exit': exit_code,
                     'expect_contains': ['ok', 'added'], 'expect_absent': ['Traceback', 'warning']}], notes))


class StopOutcomeTests(unittest.TestCase):
    def test_stop_outcome(self):
        self.assertIs(E.stop_outcome, stop_outcome)
        paused = [
            ('3 builds failed verification. The standard is not lowered; Owner may resume with more rounds.',
             'BUDGET_REACHED'),
            ('NEEDS_DECISION: the same failure (product:self-test) recurred after a forced change of approach. '
             'The Owner decides how to continue.', 'EXHAUSTED'),
            ('NEEDS_DECISION: automatic recovery did not resolve INFRA_FAILED: timeout', 'OWNER_DECISION_REQUIRED'),
            ('NEEDS_DECISION: automatic recovery did not resolve 3 builds failed verification',
             'OWNER_DECISION_REQUIRED'),
            ('NEEDS_DECISION: choose an approach', 'OWNER_DECISION_REQUIRED'),
            ('HARNESS_BLOCKED: missing evidence', 'BLOCKED'),
            ('INFRA_FAILED: browser failed', 'BLOCKED'),
            ('RateLimited: usage limit', 'BLOCKED'),
            ('No provider available: both quotas exhausted', 'BLOCKED'),
            ('Owner approval needed (external_connection): example.com', 'OWNER_DECISION_REQUIRED'),
            ('Owner action needed (install_tool): blender', 'OWNER_DECISION_REQUIRED'),
            ('Owner stopped the run', 'OWNER_STOPPED'),
            ('Rejected: Owner stopped the run', 'OWNER_STOPPED'),
            ('Rejected: Codex: 오너가 중단했습니다. 프로세스 트리 전체를 종료했습니다.', 'OWNER_STOPPED'),
            ('Rejected: unusable reply', 'BLOCKED'),
            ('Internal error ValueError: invalid value', 'BLOCKED'),
            ('Unrecognized pause reason', 'OWNER_DECISION_REQUIRED'),
            ('Rejected: ' + 'x' * 220, 'BLOCKED'),
        ]
        cases = [('PAUSED', reason, (code, reason[:200])) for reason, code in paused]
        cases += [('PAUSED', reason, ('OWNER_DECISION_REQUIRED', 'waiting for an Owner decision'))
                  for reason in (None, '')]
        cases += [('OWNER_REVIEW', None, ('VERIFIED', 'verified; waiting for the Owner review'))]
        cases += [(state, None, ('CLOSING', 'Owner closing steps'))
                  for state in ('PENDING_CLOSE', 'ARCHIVE_PENDING_APPROVAL', 'ARCHIVING', 'CLOSED')]
        cases += [(state, reason, None) for state in E.ACTIVE for reason in (None, 'Owner stopped the run')]
        for state, reason, expected in cases:
            with self.subTest(state=state, reason=reason):
                project = {'state': state, 'pause_reason': reason}
                self.assertEqual(stop_outcome(project), expected)
                self.assertEqual(project, {'state': state, 'pause_reason': reason})


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.store = Store(self.tmp / 'ws' / 'axbranch.sqlite3')
        self.vault = self.tmp / 'vault'
        self.vault.mkdir()

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def engine(self, script):
        return E.Engine(self.store, workspace=self.tmp / 'ws', vault=self.vault, gai_db=self.tmp / 'none.db', llm=script)

    def test_fail_rebuild_pass_deliver_and_save(self):
        script = Script([BROKEN, GOOD], ['PASS', 'PASS'])   # verifier wrongly says PASS on v1
        eng = self.engine(script)
        pid = self.store.new_project('make an add tool')
        p = eng.run(pid)
        self.assertEqual(p['state'], 'OWNER_REVIEW')
        self.assertEqual([e['detail'] for e in self.store.events(pid, {'stop_outcome'})], [
            {'code': 'VERIFIED', 'detail': 'verified; waiting for the Owner review', 'iteration': p['iteration']}])
        self.assertEqual(self.store.handoff(pid)['stop_outcome'][0], 'VERIFIED')
        vs = self.store.verifications(pid)
        # Deterministic self-test overrides the model's PASS on the broken build.
        self.assertEqual([v['verdict'] for v in vs], ['FAIL', 'PASS'])
        self.assertIn('Gate failed: deterministic checks failed', vs[0]['result']['findings'][-1]['issue'])
        arts = self.store.artifacts(pid)
        self.assertEqual([Path(a['path']).parent.name for a in arts], ['v1', 'v2'])
        self.assertEqual(Path(arts[0]['path']).name, 'add_tool.py')       # filename sanitized, no traversal
        import hashlib
        for a in arts:   # recorded hash = bytes on disk (no Windows newline translation)
            self.assertEqual(hashlib.sha256(Path(a['path']).read_bytes()).hexdigest(), a['sha256'])
        # Rebuild prompt carried the findings; verifier ran on the other provider than the producer.
        build_prompts = [pr for s, _, pr in script.prompts if s is E.BUILD]
        self.assertIn('FAILED independent verification', build_prompts[1])
        self.assertTrue(all(pref == 'codex' for s, pref, _ in script.prompts if s is E.VERDICT))
        # Notes stage ran once and was reused in the rebuild.
        self.assertEqual(sum(s is E.WORK for s, _, _ in script.prompts), 1)
        self.assertEqual(p['report']['rounds'], 2)

        p = eng.close(pid)                           # CEO asks first
        self.assertEqual(p['state'], 'ARCHIVE_PENDING_APPROVAL')
        p = eng.close(pid, 'save', satisfaction=95)
        self.assertEqual(p['state'], 'CLOSED')
        note = Path(p['archive_note'])
        self.assertIn('Gate failed', note.read_text(encoding='utf-8'))
        text = note.read_text(encoding='utf-8')
        self.assertNotIn('return a + b', text)                       # no raw artifact content archived
        self.assertIn('### Round 2 — PASS', text)                    # every round's verification, not only FAILs
        self.assertIn(self.store.artifacts(pid)[-1]['sha256'], text)  # artifacts by reference
        self.assertEqual(self.store.agents(pid), [])
        # Archived knowledge is retrievable for the next goal.
        self.assertTrue(knowledge.retrieve(self.vault, 'add tool gate override'))

    def test_quota_pauses_then_resume_continues_from_db(self):
        script = Script([GOOD], ['PASS'], fail_on=E.BUILD)
        eng = self.engine(script)
        pid = self.store.new_project('make an add tool')
        p = eng.run(pid)
        self.assertEqual((p['state'], p['resume_state']), ('PAUSED', 'EXECUTING'))
        handoff = (self.tmp / 'ws' / 'projects' / pid / 'HANDOFF.md').read_text(encoding='utf-8')
        self.assertIn('"state": "PAUSED"', handoff)
        # A fresh engine/store (e.g. a different CLI session) picks it up.
        store2 = Store(self.tmp / 'ws' / 'axbranch.sqlite3')
        try:
            store2.resume(pid)
            eng2 = E.Engine(store2, workspace=self.tmp / 'ws', vault=self.vault, gai_db=self.tmp / 'none.db', llm=script)
            self.assertEqual(eng2.run(pid)['state'], 'OWNER_REVIEW')
        finally:
            store2.close()
        self.assertEqual(sum(s is E.PLAN for s, _, _ in script.prompts), 1)   # no re-planning

    def test_failed_build_records_duration_error_and_notes_then_pauses(self):
        for error in (providers.Rejected('timeout: ' + 'x' * 600),
                      providers.RateLimited('usage limit')):
            with self.subTest(error=type(error).__name__):
                script = Script([GOOD], ['PASS'])
                error.notes = ['claude: usage limit']

                def failing(prompt, schema, **kw):
                    if schema is E.BUILD:
                        clock.return_value = 1900
                        raise error
                    return script(prompt, schema, **kw)
                eng = self.engine(failing)
                pid = self.store.new_project('make an add tool')
                with mock.patch.object(E.time, 'monotonic', return_value=100) as clock:
                    p = eng.run(pid)
                self.assertEqual((p['state'], p['resume_state']), ('PAUSED', 'EXECUTING'))
                self.assertEqual(p['pause_reason'], f'{type(error).__name__}: {error}')
                failed = self.store.events(pid, {'call_failed'})
                self.assertEqual(len(failed), 1)
                self.assertEqual(failed[0]['detail'], {
                    'who': 'Developer', 'preferred': 'claude', 'seconds': 1800,
                    'error': str(error)[:500], 'failures': [providers.failure_category(n) for n in error.notes]})
                self.assertIsNone(E.activity(self.tmp / 'ws', pid))
                self.assertEqual(len(self.store.events(pid, {'call_start'})), 3)
                calls = self.store.events(pid, {'call'})
                self.assertEqual(len(calls), 2)
                self.assertFalse(any(e['detail']['who'] == 'Developer' for e in calls))

    def test_budget_pauses_without_lowering_bar_and_strategy_switches(self):
        old = gov.MAX_ROUNDS
        script = Script([BROKEN + f'# attempt {i}\n' for i in range(3)], ['FAIL'] * 3, strategy='switch_provider')
        eng = self.engine(script)
        pid = self.store.new_project('make an add tool')
        self.store.update(pid, budget=3)
        p = eng.run(pid)
        self.assertEqual(p['state'], 'PAUSED')
        self.assertIn('not lowered', p['pause_reason'])
        self.assertEqual(p['plan']['pipeline'][-1]['provider'], 'codex')            # switched after 2 fails
        self.assertIn('replaced', {a['status'] for a in self.store.agents(pid, active_only=False)})
        self.assertEqual(gov.MAX_ROUNDS, old)
        outcomes = self.store.events(pid, {'stop_outcome'})
        self.assertEqual([e['detail'] for e in outcomes], [
            {'code': 'BUDGET_REACHED', 'detail': p['pause_reason'][:200], 'iteration': p['iteration']}])
        self.assertEqual(self.store.handoff(pid)['stop_outcome'], ('BUDGET_REACHED', p['pause_reason'][:200]))
        self.assertEqual(eng.run(pid), p)
        self.assertEqual(self.store.events(pid, {'stop_outcome'}), outcomes)

    def test_stop_outcome_compares_code_and_detail_with_latest_event(self):
        eng = self.engine(Script([], []))
        pid = self.store.new_project('record stop reasons')
        self.store.pause(pid, 'Owner stopped the run')
        eng.run(pid)
        outcomes = self.store.events(pid, {'stop_outcome'})
        self.store.update(pid, iteration=2)
        eng.run(pid)
        self.assertEqual(self.store.events(pid, {'stop_outcome'}), outcomes)
        for reason in ('Owner stopped again', 'Rejected: unusable reply', 'Owner stopped the run'):
            self.store.update(pid, pause_reason=reason)
            eng.run(pid)
        self.assertEqual([e['detail'] for e in self.store.events(pid, {'stop_outcome'})], [
            {'code': 'OWNER_STOPPED', 'detail': 'Owner stopped the run', 'iteration': 1},
            {'code': 'OWNER_STOPPED', 'detail': 'Owner stopped again', 'iteration': 2},
            {'code': 'BLOCKED', 'detail': 'Rejected: unusable reply', 'iteration': 2},
            {'code': 'OWNER_STOPPED', 'detail': 'Owner stopped the run', 'iteration': 2}])

    def test_discard_needs_confirmation(self):
        eng = self.engine(Script([GOOD], ['PASS']))
        pid = self.store.new_project('make an add tool')
        eng.run(pid)
        with self.assertRaises(Rejected):
            eng.close(pid, 'discard')
        p = eng.close(pid, 'discard', confirm=True)
        self.assertEqual((p['state'], p['closed_mode']), ('CLOSED', 'discard'))
        self.assertEqual(list(self.vault.rglob('*.md')), [])

    def test_pause_choice_then_resume_to_pending_close(self):
        eng = self.engine(Script([GOOD], ['PASS']))
        pid = self.store.new_project('make an add tool')
        eng.run(pid)
        p = eng.close(pid, 'pause')
        self.assertEqual((p['state'], p['resume_state']), ('PAUSED', 'PENDING_CLOSE'))
        self.assertEqual(eng.close(pid, 'save')['state'], 'CLOSED')

    def test_missing_tool_asks_owner(self):
        script = Script([GOOD], ['PASS'])
        plan_call = script.__call__

        def with_tool(prompt, schema, **kw):
            result = plan_call(prompt, schema, **kw)
            if schema is E.PLAN:
                result[0]['required_tools'] = ['definitely-not-installed-tool']
            return result
        eng = self.engine(with_tool)
        pid = self.store.new_project('render a 3d scene')
        p = eng.run(pid)
        self.assertEqual(p['state'], 'PAUSED')
        self.assertIn('install_tool', p['pause_reason'])

    def test_cancel_pauses(self):
        eng = self.engine(Script([GOOD], ['PASS']))
        pid = self.store.new_project('x tool')
        stop = threading.Event(); stop.set()
        self.assertEqual(eng.run(pid, stop)['state'], 'PAUSED')

    def test_stop_at_checkpoint_then_another_session_continues_without_rerun(self):
        script = Script([GOOD], ['PASS'])
        eng = self.engine(script)
        pid = self.store.new_project('make an add tool')
        p = eng.run(pid, stop_at='VERIFYING')
        self.assertEqual(p['state'], 'VERIFYING')                 # left ACTIVE, like an interrupted engine
        self.assertEqual(self.store.events(pid, {'stop_outcome'}), [])
        self.assertIsNone(self.store.handoff(pid)['stop_outcome'])
        self.assertEqual(eng.consistency(pid), [])
        handoff = (self.tmp / 'ws' / 'projects' / pid / 'HANDOFF.md').read_text(encoding='utf-8')
        self.assertIn('Verification Agent judges the latest artifact', handoff)
        before = len(script.prompts)
        store2 = Store(self.tmp / 'ws' / 'axbranch.sqlite3')
        try:
            eng2 = E.Engine(store2, workspace=self.tmp / 'ws', vault=self.vault, gai_db=self.tmp / 'none.db', llm=script)
            self.assertEqual(eng2.run(pid)['state'], 'OWNER_REVIEW')
        finally:
            store2.close()
        # The second session made only the verification and the CEO report calls.
        self.assertEqual([s for s, _, _ in script.prompts[before:]], [E.VERDICT, E.REPORT])
        self.assertEqual(len(self.store.events(pid, {'session'})), 2)

    def test_consistency_detects_tampered_artifact(self):
        eng = self.engine(Script([GOOD], ['PASS']))
        pid = self.store.new_project('make an add tool')
        eng.run(pid, stop_at='VERIFYING')
        Path(self.store.artifacts(pid)[-1]['path']).write_bytes(b'tampered')
        self.assertIn('differ', eng.consistency(pid)[0])
        self.assertEqual(eng.run(pid)['state'], 'PAUSED')          # never verifies a changed artifact

    def test_self_test_gets_empty_stdin_and_flag(self):
        path = self.tmp / 'reads_stdin.py'
        path.write_text("import sys\nif __name__ == '__main__':\n    assert sys.argv[1:] == ['--self-test']\n"
                        "    assert sys.stdin.read() == ''\n", encoding='utf-8')
        self.assertTrue(self.engine(Script([], [])).checks(path, 'python')['ok'])

    def test_verifier_on_producer_engine_is_recorded(self):
        for discarded in (False, True):
            with self.subTest(discarded=discarded):
                script = Script([GOOD], ['PASS'])

                def other_engine_limited(prompt, schema, **kw):
                    result, used, notes = script(prompt, schema, **kw)
                    return (result, 'claude', notes) if schema is E.VERDICT else (result, used, notes)
                eng = self.engine(other_engine_limited)     # producer and verifier both use claude
                pid = self.store.new_project('make an add tool')
                self.assertEqual(eng.run(pid, stop_at='VERIFYING')['state'], 'VERIFYING')
                if discarded:
                    self.store.discard_context(pid)
                self.assertEqual(eng.run(pid)['state'], 'OWNER_REVIEW')
                decision = next(e['detail'] for e in self.store.events(pid, {'decision'})
                                if e['detail']['what'] == "verification ran on the producer's engine")
                self.assertEqual(decision['actual_producer'], 'claude')
                self.assertEqual(decision['producer_source'], 'configured fallback' if discarded else 'recorded')
                self.assertEqual([prefer for schema, prefer, _ in script.prompts if schema is E.VERDICT], ['codex'])

    def test_verifier_is_chosen_against_the_actual_producer(self):
        class FailoverScript(Script):
            def __call__(self, prompt, schema, **kw):
                result, used, notes = super().__call__(prompt, schema, **kw)
                return (result, 'codex', ['claude: quota']) if schema is E.BUILD else (result, used, notes)

        script = FailoverScript([GOOD], ['PASS'])
        eng = self.engine(script)
        pid = self.store.new_project('make an add tool')
        p = eng.run(pid)
        self.assertEqual(p['state'], 'OWNER_REVIEW')
        self.assertEqual(p['plan']['pipeline'][-1]['provider'], 'claude')
        self.assertEqual([prefer for schema, prefer, _ in script.prompts if schema is E.VERDICT], ['claude'])
        self.assertFalse(any(e['detail']['what'] == "verification ran on the producer's engine"
                             for e in self.store.events(pid, {'decision'})))

    def test_same_engine_verification_is_detected_after_failover(self):
        class FailoverScript(Script):
            def __call__(self, prompt, schema, **kw):
                result, used, notes = super().__call__(prompt, schema, **kw)
                if schema is E.BUILD or schema is E.VERDICT:
                    return result, 'codex', ['claude: quota']
                return result, used, notes

        script = FailoverScript([GOOD], ['PASS'])
        eng = self.engine(script)
        pid = self.store.new_project('make an add tool')
        self.assertEqual(eng.run(pid)['state'], 'OWNER_REVIEW')
        decision = next(e['detail'] for e in self.store.events(pid, {'decision'})
                        if e['detail']['what'] == "verification ran on the producer's engine")
        self.assertEqual(decision['actual_producer'], 'codex')
        self.assertEqual(decision['producer_source'], 'recorded')
        self.assertEqual([prefer for schema, prefer, _ in script.prompts if schema is E.VERDICT], ['claude'])

    def test_actual_producer_uses_final_stage_of_artifact_iteration(self):
        eng = self.engine(Script([], []))
        pid = self.store.new_project('producer provenance')
        other = self.store.new_project('unrelated project')
        self.store.update(pid, iteration=2, plan_version=2, plan={'pipeline': [{'provider': 'claude'}]})
        artifact = {'iteration': 1}
        self.store.save_output(pid, 1, 1, 1, None, 'codex', {})
        self.store.save_output(pid, 1, 1, 0, None, 'claude', {})
        self.store.save_output(pid, 2, 2, 2, None, 'claude', {})
        self.store.save_output(other, 1, 1, 2, None, 'claude', {})
        self.assertEqual(eng._actual_producer(pid, artifact), ('codex', False))
        self.store.discard_context(pid)
        self.assertEqual(eng._actual_producer(pid, artifact), ('claude', True))

    def test_owner_problem_reopens_same_project_reproduces_and_redelivers(self):
        script = Script([GOOD, GOOD, LAUNCHABLE], ['PASS', 'PASS', 'PASS'], probe_disposition='PRODUCT_DEFECT')
        eng = self.engine(script)
        pid = self.store.new_project('make an add tool')
        self.assertEqual(eng.run(pid)['state'], 'OWNER_REVIEW')
        with self.assertRaises(Rejected):
            eng.owner_review(pid, works=False, text='   ')               # a problem needs a description
        self.assertEqual(eng.owner_review(pid, works=False, text='double-click closes immediately')['state'], 'REWORK')
        p = eng.run(pid)
        self.assertEqual(p['state'], 'OWNER_REVIEW')                      # back to the Owner, same project
        self.assertEqual(len(self.store.projects()), 1)
        diag = next(pr for s, _, pr in script.prompts if s is E.DIAGNOSIS)
        self.assertIn('double-click closes immediately', diag)            # CEO saw the Owner's words
        self.assertIn('runtime_evidence_current', diag)                   # ...and the reproduction run
        repro = self.store.events(pid, {'reproduction'})[0]['detail']
        self.assertTrue(repro['current_spec_ok'])                         # old spec missed it
        self.assertFalse(repro['revised_spec_ok'])                        # revised acceptance reproduces it on v1
        vs = self.store.verifications(pid)
        # v2 (unchanged GOOD) is blocked by Runtime Acceptance despite the model's PASS; v3 passes.
        self.assertEqual([v['verdict'] for v in vs], ['PASS', 'FAIL', 'PASS'])
        self.assertFalse(vs[1]['checks']['runtime']['ok'])
        self.assertTrue(vs[2]['checks']['runtime']['ok'])
        self.assertTrue(all(f['handled_iteration'] for f in self.store.feedback(pid)))
        self.assertEqual(p['plan_version'], 2)
        builds = [pr for s, _, pr in script.prompts if s is E.BUILD]
        self.assertIn('owner_rework', builds[-1])
        self.assertEqual(eng.owner_review(pid, works=True)['state'], 'OWNER_REVIEW')   # confirmed, still open
        self.assertEqual(eng.owner_review(pid, finish=True)['state'], 'PENDING_CLOSE')  # only an explicit finish

    def test_live_activity_is_visible_during_a_call_and_cleared_after(self):
        script = Script([GOOD], ['PASS'])
        seen = []

        def watching(prompt, schema, **kw):
            if schema is E.BUILD:
                kw['on_tick']({'provider': 'codex', 'pid': 4242, 'elapsed': 61, 'output_bytes': 900, 'idle': 3})
                seen.append(E.activity(self.tmp / 'ws', pid))
            return script(prompt, schema, **kw)
        eng = self.engine(watching)
        pid = self.store.new_project('make an add tool')
        eng.run(pid)
        a = seen[0]
        self.assertEqual((a['agent'], a['provider'], a['pid'], a['elapsed'], a['state']), ('Developer', 'codex', 4242, 61, 'EXECUTING'))
        self.assertIsNone(E.activity(self.tmp / 'ws', pid))          # nothing in flight any more
        starts = self.store.events(pid, {'call_start'})
        self.assertTrue(starts and all('who' in e['detail'] for e in starts))
        self.assertTrue(all('seconds' in e['detail'] for e in self.store.events(pid, {'call'})))

    def test_call_records_prompt_size_and_unknown_tokens_without_reported_usage(self):
        from axbranch import providers
        providers._usage.value = {'source': 'an earlier real turn', 'input_tokens': 999}   # stale: must not leak
        eng = self.engine(Script([GOOD], ['PASS']))
        pid = self.store.new_project('make an add tool')
        eng.run(pid)
        calls = [e['detail'] for e in self.store.events(pid, {'call'})]
        self.assertTrue(calls)
        self.assertTrue(all(c['tokens'] == 'UNKNOWN' and c['prompt_chars'] > 0 for c in calls))

    def test_works_plus_plain_language_request_reopens_without_classification(self):
        script = Script([LAUNCHABLE, GOOD, LAUNCHABLE], ['PASS', 'PASS', 'PASS'], probe_disposition='PRODUCT_DEFECT')
        eng = self.engine(script)
        pid = self.store.new_project('make an add tool')
        eng.run(pid)
        with self.assertRaises(Rejected):
            eng.owner_review(pid, works=True, text='more please', finish=True)   # contradictory
        p = eng.owner_review(pid, works=True, text='숫자 두 개를 직접 입력할 수 있으면 좋겠어요. 설명도 붙여 주세요.')
        self.assertEqual(p['state'], 'REWORK')
        kinds = [(f['verdict'], f['handled_iteration']) for f in self.store.feedback(pid)]
        self.assertEqual(kinds, [('works', 1), ('request', None)])       # confirmation never pending
        p = eng.run(pid)
        self.assertEqual(p['state'], 'OWNER_REVIEW')
        diagnoses = [pr for s, _, pr in script.prompts if s is E.DIAGNOSIS]
        self.assertEqual(len(diagnoses), 1)          # a later verification FAIL did not re-diagnose
        self.assertIn('숫자 두 개를 직접 입력', diagnoses[0])
        self.assertIn('"owner_confirmed_working_versions": [\n  1\n ]', diagnoses[0])
        self.assertEqual([v['verdict'] for v in self.store.verifications(pid)], ['PASS', 'FAIL', 'PASS'])

    def test_every_rework_stage_sees_the_current_version(self):
        script = Script([LAUNCHABLE, LAUNCHABLE], ['PASS', 'PASS'])
        eng = self.engine(script)
        pid = self.store.new_project('make an add tool')
        eng.run(pid)
        original_diagnosis = Script.__call__

        def two_stage(self_, prompt, schema, prefer='claude', web=False, cancel=None, **kw):
            result = original_diagnosis(self_, prompt, schema, prefer, web, cancel, **kw)
            if schema is E.DIAGNOSIS:
                result[0]['pipeline'] = [{'name': 'design', 'agent_role': 'Architect', 'instructions': 'design',
                                          'provider': 'codex', 'web': False}] + result[0]['pipeline']
            return result
        with unittest.mock.patch.object(Script, '__call__', two_stage):
            eng.owner_review(pid, works=True, text='please add an explanation line')
            eng.run(pid)
        notes = [pr for s, _, pr in script.prompts if s is E.WORK]
        self.assertIn("print('result:', add(2, 3))", notes[-1].replace('\\n', '\n'))   # v1 source given to design
        self.assertIn('please add an explanation line', notes[-1])

    def test_empty_build_fails_without_verification_and_never_becomes_the_baseline(self):
        script = Script([LAUNCHABLE, '', LAUNCHABLE + '\n# explanation added\n'], ['PASS', 'PASS'])     # v2 build comes back empty
        eng = self.engine(script)
        pid = self.store.new_project('make an add tool')
        eng.run(pid)
        eng.owner_review(pid, works=True, text='add an explanation line')
        p = eng.run(pid)
        self.assertEqual(p['state'], 'OWNER_REVIEW')
        self.assertEqual(len(self.store.events(pid, {'build_rejected'})), 1)
        self.assertEqual(sum(s is E.VERDICT for s, _, _ in script.prompts), 2)      # empty build: no verifier call
        self.assertEqual([a['iteration'] for a in self.store.artifacts(pid)], [1, 3])   # no empty artifact stored
        rebuild = [pr for s, _, pr in script.prompts if s is E.BUILD][-1]
        self.assertIn("print('result:', add(2, 3))", rebuild.replace('\\n', '\n'))      # baseline = real v1

    def test_recovery_replan_reviews_strategy_and_keeps_history(self):
        script = Script([GOOD], ['PASS'], fail_on=E.BUILD)              # interrupted mid-build -> PAUSED
        eng = self.engine(script)
        pid = self.store.new_project('make an add tool')
        self.assertEqual(eng.run(pid)['state'], 'PAUSED')
        p = eng.replan(pid, 'earlier stages lacked the source; use the best candidate')
        self.assertEqual(p['state'], 'REWORK')
        strategy = [pr for s, _, pr in script.prompts if s is E.STRATEGY][-1]
        self.assertIn('earlier stages lacked the source', strategy)
        self.assertIn('best_candidate_version', strategy)
        self.assertEqual(len(self.store.events(pid, {'recovery_replan'})), 1)
        self.assertEqual(eng.run(pid)['state'], 'OWNER_REVIEW')

    def test_harness_hang_is_rechecked_not_sent_to_rework(self):
        eng = self.engine(Script([GOOD], ['PASS']))
        real = eng.runtime_evidence
        calls = []

        def flaky(*args):
            calls.append(1)
            if len(calls) == 1:          # first run: the browser hung, the artifact is not at fault
                return {'ok': False, 'mode': 'web', 'notes': [], 'steps': [
                    {'name': 'BROWSER: home', 'ok': False, 'problems': ['browser did not finish within 90s (2 attempts)']}]}
            return real(*args)
        eng.runtime_evidence = flaky
        pid = self.store.new_project('make an add tool')
        self.assertEqual(eng.run(pid)['state'], 'OWNER_REVIEW')
        self.assertEqual([v['verdict'] for v in self.store.verifications(pid)], ['PASS'])   # no rebuild
        self.assertEqual(len(self.store.events(pid, {'harness_retry'})), 1)

    def _budget_paused(self, script):
        eng = self.engine(script)
        pid = self.store.new_project('make an add tool')
        self.store.update(pid, budget=1)
        p = eng.run(pid)                                    # first build fails -> budget used -> waits for the Owner
        self.assertEqual(p['state'], 'PAUSED')
        self.assertIn('not lowered', p['pause_reason'])
        return eng, pid

    def test_owner_feedback_on_a_waiting_project_reworks_the_same_project(self):
        script = Script([BROKEN, LAUNCHABLE], ['FAIL', 'PASS'])
        eng, pid = self._budget_paused(script)
        p = eng.owner_review(pid, text='결론은 좋은데 다른 방법으로 다시 검증해줘')
        self.assertEqual(p['state'], 'REWORK')
        self.assertGreater(p['budget'], 1)                                  # fresh rounds for the new direction
        self.assertEqual(eng.run(pid)['state'], 'OWNER_REVIEW')
        diagnosis = next(pr for s, _, pr in script.prompts if s is E.DIAGNOSIS)
        self.assertIn('다른 방법으로 다시 검증해줘', diagnosis)                 # the CEO analysed the feedback
        self.assertIn('wrong sum', diagnosis)                               # with the earlier findings kept
        self.assertEqual(len(self.store.projects()), 1)

    def test_owner_continue_or_finish_on_a_waiting_project(self):
        eng, pid = self._budget_paused(Script([BROKEN], ['FAIL']))
        p = eng.owner_review(pid)                                           # [계속] without text
        self.assertEqual((p['state'], p['budget']), ('REWORK', 4))
        eng2, pid2 = self._budget_paused(Script([BROKEN], ['FAIL']))
        p = eng2.owner_review(pid2, finish=True)                           # [완료]
        self.assertEqual(p['state'], 'PENDING_CLOSE')

    def test_misconfigured_probe_goes_to_the_ceo_not_to_rework(self):
        # P-bbad3c v21: BROWSER probes carried prose instead of selectors; only the CEO can fix the probe.
        script = Script([GOOD, GOOD + '\n'], ['PASS', 'PASS'])
        eng = self.engine(script)
        real = eng.runtime_evidence
        calls = []

        def misconfigured(*args):
            calls.append(1)
            if len(calls) == 1:
                return {'ok': False, 'mode': 'web', 'notes': [], 'steps': [
                    {'name': 'BROWSER: flow', 'ok': False, 'probe_misconfigured': True,
                     'problems': ["probe misconfigured: click selector 'Click the sample' matched nothing; "
                                  'element ids on the page: #sample-1']}]}
            return real(*args)
        eng.runtime_evidence = misconfigured
        pid = self.store.new_project('make an add tool')
        p = eng.run(pid)
        strategy = [pr for s, _, pr in script.prompts if s is E.PROBE_REVIEW]
        self.assertEqual(len(strategy), 1)                                  # the CEO reviews the probe
        self.assertIn('NO product evidence', strategy[0])
        self.assertIn('#sample-1', strategy[0])
        # no repair from the CEO: harness-only -> HARNESS_BLOCKED, never a product rebuild
        self.assertTrue(p['pause_reason'].startswith('HARNESS_BLOCKED'))
        self.assertEqual(len(self.store.artifacts(pid)), 1)
        self.store.resume(pid)                                              # resume re-verifies the same version
        self.assertEqual(eng.run(pid)['state'], 'OWNER_REVIEW')
        self.assertEqual(len(self.store.artifacts(pid)), 1)

    def test_feedback_loop_is_generic_math_proof_document(self):
        proof1 = '# Proof that sqrt(2) is irrational\n' + 'Step 1. Assume sqrt(2)=p/q in lowest terms.\n' * 8
        proof2 = proof1 + 'Step 3 (re-verified by an independent method: infinite descent).\n' * 6
        script = Script([proof1, proof2], ['PASS', 'PASS'])
        base = Script.__call__

        def as_document(self_, prompt, schema, prefer='claude', web=False, cancel=None, **kw):
            result = base(self_, prompt, schema, prefer, web, cancel, **kw)
            if schema in (E.PLAN, E.DIAGNOSIS):
                result[0].update(artifact_kind='markdown', artifact_filename='proof.md',
                                 runtime={'mode': 'none', 'owner_launch': 'read it', 'launch_args': [], 'probes': []})
            return result
        with mock.patch.object(Script, '__call__', as_document):
            eng = self.engine(script)
            pid = self.store.new_project('수학 난제 하나 풀어봐')
            self.assertEqual(eng.run(pid)['state'], 'OWNER_REVIEW')
            p = eng.owner_review(pid, text='3번째 논리가 부족한 것 같은데 다른 방법으로 다시 검증해줘.')
            self.assertEqual(p['state'], 'REWORK')
            self.assertEqual(eng.run(pid)['state'], 'OWNER_REVIEW')     # same project, verified again
        diagnosis = next(pr for s, _, pr in script.prompts if s is E.DIAGNOSIS)
        self.assertIn('3번째 논리가 부족한', diagnosis)
        self.assertEqual(len(self.store.projects()), 1)
        self.assertIn('infinite descent', Path(self.store.artifacts(pid)[-1]['path']).read_text(encoding='utf-8'))

    def test_declined_domain_proposed_again_can_be_approved(self):
        script = Script([LAUNCHABLE], ['PASS'])
        script.network = [{'domain': 'data.sec.gov', 'purpose': 'facts', 'risk': 'public_read'}]
        eng = self.engine(script)
        pid = self.store.new_project('make an add tool')
        eng.run(pid)
        eng.decide_network(pid, False, 'use official sources')              # declined once
        self.store.resume(pid)
        p = eng.run(pid)                                                    # CEO proposes it again
        self.assertEqual(p['state'], 'PAUSED')
        self.assertTrue(self.store.approvals(pid, 'pending'))              # a new request the Owner can answer
        eng.decide_network(pid, True)
        self.store.resume(pid)
        self.assertEqual(eng.run(pid)['state'], 'OWNER_REVIEW')

    def test_strategy_preserves_runtime_probes_and_assertions(self):
        launch = {'name': 'launch', 'args': [], 'stdin': '', 'http_method': '', 'http_path': '',
                  'http_body': '', 'expect_exit': 0, 'expect_status': 0,
                  'expect_contains': ['ok'], 'expect_absent': ['Traceback']}
        self_test = {**launch, 'name': 'self-test', 'args': ['--self-test']}

        class ProbeScript(Script):
            def __call__(self, prompt, schema, **kw):
                result, used, notes = super().__call__(prompt, schema, **kw)
                if schema is E.PLAN:
                    result['runtime']['probes'] = [launch, self_test]
                elif schema is E.STRATEGY:
                    result['runtime']['probes'] = [
                        {**launch, 'args': ['--repaired'], 'expect_exit': -1,
                         'expect_contains': [], 'expect_absent': []}]
                return result, used, notes

        script = ProbeScript([GOOD + f'# attempt {i}\n' for i in range(3)], ['FAIL', 'FAIL', 'PASS'],
                             strategy='continue')
        eng = self.engine(script)
        pid = self.store.new_project('make an add tool')
        p = eng.run(pid)

        self.assertEqual(p['state'], 'OWNER_REVIEW')
        self.assertEqual([v['verdict'] for v in self.store.verifications(pid)], ['FAIL', 'FAIL', 'PASS'])
        self.assertEqual(sum(schema is E.STRATEGY for schema, _, _ in script.prompts), 1)
        self.assertEqual(p['plan']['runtime']['probes'], [launch, self_test])
        self.assertEqual([e['detail'] for e in self.store.events(pid, {'decision'})
                          if e['detail']['what'] == 'runtime probes preserved'], [
            {'what': 'runtime probes preserved', 'why': 'kept assertions of launch; kept dropped probe self-test; kept runtime owner_launch',
             'by': 'engine'}])

    def test_strategy_cannot_silently_drop_approved_connections_and_agents_see_approval(self):
        # P-bbad3c: a strategy review set network access to 'none' after the Owner approved it, and the agents,
        # reading a stale interpretation, shipped fetching disabled ("Owner 승인 대기").
        script = Script([LAUNCHABLE], ['PASS'])
        sec = {'domain': 'data.sec.gov', 'purpose': 'facts', 'risk': 'public_read'}
        script.network = [sec]
        eng = self.engine(script)
        pid = self.store.new_project('make an add tool')
        eng.run(pid)
        eng.decide_network(pid, True)
        script.network = []                                                 # a later review proposes none
        eng._strategy(pid)
        self.assertEqual(self.store.project(pid)['plan']['network_access'], [sec])
        self.assertTrue(any(e['detail']['what'] == 'Owner-approved network access kept'
                            for e in self.store.events(pid, {'decision'})))
        self.store.resume(pid)
        self.assertEqual(eng.run(pid)['state'], 'OWNER_REVIEW')
        build = [pr for s, _, pr in script.prompts if s is E.BUILD][-1]
        self.assertIn('"owner_decision": "approved"', build)                # the producer sees the decision

    def test_external_connection_waits_for_owner_approval(self):
        script = Script([GOOD], ['PASS'])
        script.network = [{'domain': 'query1.finance.example', 'purpose': 'daily prices'}]
        eng = self.engine(script)
        pid = self.store.new_project('make an add tool')
        p = eng.run(pid)
        self.assertEqual((p['state'], p['resume_state']), ('PAUSED', 'STAFFING'))
        self.assertIn('external_connection', p['pause_reason'])
        self.assertFalse(any(s is E.BUILD for s, _, _ in script.prompts))      # nothing built before approval
        eng.decide_network(pid, True)
        self.store.resume(pid)
        self.assertEqual(eng.run(pid)['state'], 'OWNER_REVIEW')
        self.assertEqual(self.store.approvals(pid)[0]['status'], 'approved')

    def test_approved_public_read_access_is_reused_by_a_later_project(self):
        sec = {'domain': 'data.sec.gov', 'purpose': 'official company facts', 'risk': 'public_read'}
        first = Script([GOOD], ['PASS'])
        first.network = [sec]
        eng = self.engine(first)
        p1 = self.store.new_project('make an add tool')
        self.assertEqual(eng.run(p1)['state'], 'PAUSED')                 # first time: the Owner is asked
        eng.decide_network(p1, True)
        self.store.resume(p1)
        self.assertEqual(eng.run(p1)['state'], 'OWNER_REVIEW')
        second = Script([GOOD], ['PASS'])
        second.network = [dict(sec)]
        eng.llm = second
        p2 = self.store.new_project('another tool using the same public data')
        self.assertEqual(eng.run(p2)['state'], 'OWNER_REVIEW')            # same low-risk scope: not asked again
        self.assertEqual(len(self.store.events(p2, {'approval_reused'})), 1)
        third = Script([GOOD], ['PASS'])
        third.network = [{**sec, 'purpose': 'company facts with my API key'}]   # riskier: asks again
        eng.llm = third
        p3 = self.store.new_project('a tool that needs a key')
        self.assertEqual(eng.run(p3)['state'], 'PAUSED')
        self.assertIn('[api_key]', eng.store.project(p3)['pause_reason'])

    def test_declined_connection_goes_back_to_the_ceo(self):
        script = Script([GOOD], ['PASS'])
        script.network = [{'domain': 'query1.finance.example', 'purpose': 'daily prices'}]
        eng = self.engine(script)
        pid = self.store.new_project('make an add tool')
        eng.run(pid)
        p = eng.decide_network(pid, False)
        self.assertEqual(p['resume_state'], 'REWORK')
        self.assertIn('declined', self.store.feedback(pid)[-1]['text'])
        self.assertEqual(self.store.approvals(pid)[0]['status'], 'denied')

    def test_review_only_for_delivered_projects(self):
        eng = self.engine(Script([GOOD], ['PASS']))
        pid = self.store.new_project('make an add tool')
        with self.assertRaises(Rejected):
            eng.owner_review(pid, works=True)

    def test_illegal_transition(self):
        pid = self.store.new_project('x')
        with self.assertRaises(Rejected):
            self.store.set_state(pid, 'CLOSED')


class ExecutiveAcceptanceTests(unittest.TestCase):
    setUp, tearDown, engine = EngineTests.setUp, EngineTests.tearDown, EngineTests.engine

    rework = {'goal_satisfied': 'partly', 'missing_evidence': ['real output'],
              'next_action': 'rework', 'directive': 'show real output', 'gap_class': 'PRODUCT_CHANGE'}
    deliver = {'goal_satisfied': 'yes', 'missing_evidence': [], 'next_action': 'deliver', 'directive': ''}

    def test_executive_rework_once_then_deliver(self):
        script = ExecutiveScript([GOOD, GOOD + '\n'], ['PASS', 'PASS'], [self.rework, self.deliver])
        eng = self.engine(script)
        pid = self.store.new_project('make an add tool')
        p = eng.run(pid)
        self.assertEqual(p['state'], 'OWNER_REVIEW', p['pause_reason'])
        builds = [prompt for schema, _, prompt in script.prompts if schema is E.BUILD]
        self.assertEqual(len(builds), 2)
        self.assertNotIn('ceo_directive', builds[0])
        self.assertIn('ceo_directive', builds[1])
        self.assertIn('show real output', builds[1])
        self.assertIn(E.CEO_DIRECTIVE, builds[1])
        self.assertEqual([e['detail']['what'] for e in self.store.events(pid, {'decision'})
                          if e['detail']['what'].startswith('executive ')],
                         ['executive rework', 'executive acceptance'])
        self.assertNotIn('ceo_directive', p['plan'])
        arts = self.store.artifacts(pid)
        self.assertEqual([a['iteration'] for a in arts], [1, 2])
        self.assertEqual([Path(a['path']).read_bytes() for a in arts],
                         [GOOD.encode('utf-8'), (GOOD + '\n').encode('utf-8')])
        self.assertEqual([v['verdict'] for v in self.store.verifications(pid)], ['PASS', 'PASS'])
        self.assertEqual(p['report']['artifact'], arts[-1]['path'])
        self.assertEqual((p['iteration'], p['report']['rounds']), (2, 2))
        self.assertEqual(eng.consistency(pid), [])
        self.assertEqual((script.builds, script.verdicts, script.reports), ([], [], []))

    def test_executive_rework_is_capped_even_for_identical_passed_bytes(self):
        rounds = E.MAX_EXECUTIVE_REWORKS + 1
        for identical in (False, True):
            with self.subTest(identical=identical):
                builds = [GOOD if identical else GOOD + '\n' * i for i in range(rounds)]
                script = ExecutiveScript(builds, ['PASS'] * rounds, [self.rework] * rounds)
                eng = self.engine(script)
                pid = self.store.new_project('make an add tool')
                p = eng.run(pid)
                self.assertEqual(p['state'], 'OWNER_REVIEW', p['pause_reason'])
                decisions = [e['detail']['what'] for e in self.store.events(pid, {'decision'})]
                self.assertEqual(decisions.count('executive rework'), E.MAX_EXECUTIVE_REWORKS)
                self.assertEqual(decisions.count('executive acceptance'), 1)
                self.assertIn(f'자동 재작업 한도 {E.MAX_EXECUTIVE_REWORKS}회', p['report']['judgment'])
                self.assertNotIn('ceo_directive', p['plan'])
                arts = self.store.artifacts(pid)
                expected = builds[:1] if identical else builds
                self.assertEqual([a['iteration'] for a in arts], list(range(1, len(expected) + 1)))
                self.assertEqual(len({Path(a['path']).parent for a in arts}), len(expected))
                self.assertEqual([Path(a['path']).read_bytes() for a in arts],
                                 [content.encode('utf-8') for content in expected])
                self.assertEqual(self.store.events(pid, {'build_rejected'}), [])
                self.assertEqual([v['verdict'] for v in self.store.verifications(pid)], ['PASS'] * rounds)
                self.assertEqual((script.builds, script.verdicts, script.reports), ([], [], []))

    def test_owner_action_resets_executive_rework_cap(self):
        script = ExecutiveScript([GOOD, GOOD + '\n'], ['PASS', 'PASS'], [self.rework, self.deliver])
        eng = self.engine(script)
        pid = self.store.new_project('make an add tool')
        for _ in range(E.MAX_EXECUTIVE_REWORKS):
            self.store.event(pid, 'decision', what='executive rework', why='earlier order', by='claude')
        self.store.event(pid, 'owner_action', action='review', channel='app')
        owner_action = self.store.events(pid, {'owner_action'})[-1]['id']
        p = eng.run(pid)
        self.assertEqual(p['state'], 'OWNER_REVIEW', p['pause_reason'])
        ordered = [e for e in self.store.events(pid, {'decision'}) if e['detail']['what'] == 'executive rework']
        self.assertEqual(len(ordered), E.MAX_EXECUTIVE_REWORKS + 1)
        self.assertEqual(sum(e['id'] > owner_action for e in ordered), 1)
        self.assertEqual(len(self.store.artifacts(pid)), 2)
        self.assertEqual((script.builds, script.verdicts, script.reports), ([], [], []))

    def test_executive_rework_without_directive_delivers_without_looping(self):
        script = ExecutiveScript([GOOD], ['PASS'], [{**self.rework, 'directive': ''}])
        pid = self.store.new_project('make an add tool')
        p = self.engine(script).run(pid)
        self.assertEqual(p['state'], 'OWNER_REVIEW', p['pause_reason'])
        self.assertEqual([e['detail']['what'] for e in self.store.events(pid, {'decision'})
                          if e['detail']['what'].startswith('executive ')], ['executive acceptance'])
        self.assertNotIn('ceo_directive', p['plan'])
        self.assertEqual(len(self.store.artifacts(pid)), 1)
        self.assertEqual(sum(schema is E.REPORT for schema, _, _ in script.prompts), 1)

    def test_executive_owner_decision_is_delivered_for_owner_review(self):
        report = {**self.rework, 'next_action': 'owner_decision', 'directive': ''}
        script = ExecutiveScript([GOOD], ['PASS'], [report])
        pid = self.store.new_project('make an add tool')
        p = self.engine(script).run(pid)
        self.assertEqual(p['state'], 'OWNER_REVIEW', p['pause_reason'])
        decisions = [e['detail'] for e in self.store.events(pid, {'decision'})
                     if e['detail']['what'].startswith('executive ')]
        self.assertEqual([d['what'] for d in decisions], ['executive acceptance'])
        self.assertIn('next owner_decision', decisions[0]['why'])
        self.assertEqual(p['report']['next_action'], 'owner_decision')
        self.assertEqual(p['report']['missing_evidence'], ['real output'])
        self.assertNotIn('ceo_directive', p['plan'])
        self.assertEqual(len(self.store.artifacts(pid)), 1)

    def test_executive_rework_respects_failure_budget(self):
        script = ExecutiveScript([BROKEN, GOOD], ['FAIL', 'PASS'], [self.rework])
        eng = self.engine(script)
        pid = self.store.new_project('make an add tool')
        self.store.update(pid, budget=2)
        self.assertEqual(eng.run(pid, stop_at='REWORK')['state'], 'REWORK')
        self.assertEqual(eng.run(pid, stop_at='VERIFYING')['state'], 'VERIFYING')
        self.store.update(pid, budget=1)         # the next PASS must not grant another build at the budget boundary
        p = eng.run(pid)
        self.assertEqual(p['state'], 'OWNER_REVIEW', p['pause_reason'])
        self.assertEqual([v['verdict'] for v in self.store.verifications(pid)], ['FAIL', 'PASS'])
        decisions = [e['detail']['what'] for e in self.store.events(pid, {'decision'})]
        self.assertNotIn('executive rework', decisions)
        self.assertEqual(decisions.count('executive acceptance'), 1)
        self.assertIn('실패 예산', p['report']['judgment'])
        self.assertNotIn('ceo_directive', p['plan'])
        self.assertEqual(len(self.store.artifacts(pid)), 2)

    def test_owner_feedback_replaces_pending_ceo_directive(self):
        script = ExecutiveScript([GOOD, LAUNCHABLE], ['PASS', 'PASS'], [self.rework, self.deliver])
        eng = self.engine(script)
        pid = self.store.new_project('make an add tool')
        p = eng.run(pid, stop_at='REWORK')
        self.assertEqual(p['state'], 'REWORK', p['pause_reason'])
        self.assertEqual(p['plan']['ceo_directive']['directive'], 'show real output')
        self.store.pause(pid, 'Owner stopped the run')
        eng.owner_review(pid, text='double-click must keep the result visible')
        self.store.event(pid, 'owner_action', action='review', channel='app')
        p = eng.run(pid, stop_at='STAFFING')
        self.assertEqual(p['state'], 'STAFFING', p['pause_reason'])
        self.assertNotIn('ceo_directive', p['plan'])
        self.assertIn('double-click must keep the result visible', p['plan']['owner_rework']['feedback'])
        p = eng.run(pid)
        self.assertEqual(p['state'], 'OWNER_REVIEW', p['pause_reason'])
        build = [prompt for schema, _, prompt in script.prompts if schema is E.BUILD][-1]
        self.assertIn('owner_rework', build)
        self.assertNotIn('ceo_directive', build)
        self.assertNotIn(E.CEO_DIRECTIVE, build)
        self.assertEqual(len(self.store.artifacts(pid)), 2)

    def test_executive_report_fails_over_to_codex(self):
        class ReportFailover(ExecutiveScript):
            def __call__(self, prompt, schema, *args, **kw):
                if schema is E.REPORT:
                    self.prompts.append((schema, kw.get('prefer', 'claude'), prompt))
                    return providers.call(prompt, schema, *args, **kw)
                return super().__call__(prompt, schema, *args, **kw)

        script = ReportFailover([GOOD, GOOD + '\n'], ['PASS', 'PASS'], [self.rework, self.deliver])
        claude = mock.Mock(side_effect=providers.RateLimited('usage limit (scripted)'))
        codex = mock.Mock(side_effect=lambda *a: {'summary': 'done', 'judgment': 'good', 'next_steps': [],
                                                **script.reports.pop(0)})
        pid = self.store.new_project('make an add tool')
        with mock.patch.dict(providers.RUN, {'claude': claude, 'codex': codex}), \
                mock.patch.object(providers.shutil, 'which', return_value='x'):
            p = self.engine(script).run(pid)
        self.assertEqual(p['state'], 'OWNER_REVIEW', p['pause_reason'])
        self.assertEqual((claude.call_count, codex.call_count), (2, 2))
        self.assertTrue(all(call.args[1] is E.REPORT for call in codex.call_args_list))
        decisions = [e['detail'] for e in self.store.events(pid, {'decision'})
                     if e['detail']['what'].startswith('executive ')]
        self.assertEqual([(d['what'], d['by']) for d in decisions],
                         [('executive rework', 'codex'), ('executive acceptance', 'codex')])
        handoffs = [e['detail'] for e in self.store.events(pid, {'provider_handoff'})]
        self.assertEqual([(e['who'], e['preferred'], e['used']) for e in handoffs],
                         [('CEO', 'claude', 'codex'), ('CEO', 'claude', 'codex')])
        self.assertTrue(all('usage limit' in e['notes'][0] for e in handoffs))


class ProviderTests(unittest.TestCase):
    def test_failover_only_on_quota(self):
        calls = []

        def limited(*a):
            calls.append('claude'); raise providers.RateLimited('usage limit')

        def ok(*a):
            calls.append('codex'); return {'x': 1}
        with mock.patch.dict(providers.RUN, {'claude': limited, 'codex': ok}), \
                mock.patch.object(providers.shutil, 'which', return_value='x'):
            result, used, notes = providers.call('p', {}, prefer='claude')
        self.assertEqual((result, used, calls), ({'x': 1}, 'codex', ['claude', 'codex']))
        self.assertTrue(notes)

        def broken(*a):
            raise providers.Rejected('timeout')
        with mock.patch.dict(providers.RUN, {'claude': broken, 'codex': ok}), \
                mock.patch.object(providers.shutil, 'which', return_value='x'):
            with self.assertRaises(providers.Rejected):
                providers.call('p', {}, prefer='claude')     # a non-quota fault never spends the other plan

    def test_quota_then_timeout_preserves_switch_notes_and_original_exception(self):
        error = providers.Rejected('timeout')
        claude = mock.Mock(side_effect=providers.RateLimited('usage limit'))
        codex = mock.Mock(side_effect=error)
        with mock.patch.dict(providers.RUN, {'claude': claude, 'codex': codex}), \
                mock.patch.object(providers.shutil, 'which', return_value='x'):
            with self.assertRaises(providers.Rejected) as raised:
                providers.call('p', {}, prefer='claude')
        self.assertIs(raised.exception, error)
        self.assertEqual(error.notes, ['claude: usage limit'])
        self.assertEqual(str(error), 'timeout / claude: usage limit')
        claude.assert_called_once()
        codex.assert_called_once()

    def test_all_quota_refusals_preserve_notes(self):
        with mock.patch.dict(providers.RUN, {
                'claude': mock.Mock(side_effect=providers.RateLimited('usage limit')),
                'codex': mock.Mock(side_effect=providers.RateLimited('quota exhausted'))}), \
                mock.patch.object(providers.shutil, 'which', return_value='x'):
            with self.assertRaises(providers.RateLimited) as raised:
                providers.call('p', {}, prefer='claude')
        self.assertEqual(raised.exception.notes, ['claude: usage limit', 'codex: quota exhausted'])
        for note in raised.exception.notes:
            self.assertIn(note, str(raised.exception))

    def test_claude_stream_result_is_found_and_quota_still_detected(self):
        ok = ('{"type":"system","subtype":"init"}\n{"type":"stream_event","event":{"delta":"x"}}\n'
              '{"type":"result","subtype":"success","is_error":false,"structured_output":{"a":1}}\n')
        self.assertEqual(json.loads(providers._claude_result(ok))['structured_output'], {'a': 1})
        limited = ('{"type":"system"}\n{"type":"result","is_error":true,'
                   '"result":"You\'ve hit your session limit - resets 9:10pm"}\n')
        with self.assertRaises(providers.RateLimited):
            providers._check_rate_limit(providers._claude_failure_text(providers._claude_result(limited)))
        self.assertIn('boom', providers._claude_result('not json at all: boom'))

    def test_gai_read_only(self):
        import sqlite3
        tmp = Path(tempfile.mkdtemp())
        db = tmp / 'g.db'
        con = sqlite3.connect(db)
        con.execute('CREATE TABLE items(id INTEGER PRIMARY KEY, title, summary, source, published_at, original_url, verification_status)')
        con.execute("INSERT INTO items(title,summary) VALUES('agent orchestration survey','multi agent orchestration')")
        con.commit(); con.close()
        self.assertEqual(len(knowledge.intel(db, 'agent orchestration design')), 1)
        shutil.rmtree(tmp, ignore_errors=True)

    def test_paying_stays_owner_only_after_proposals_are_ungated(self):
        self.assertFalse(hasattr(gov, 'SATISFACTION_GATE'))                     # proposals are not gated
        self.assertTrue(gov.PAID_EXPANSION_LOCKED)
        self.assertTrue({'payment', 'paid_api', 'plan_upgrade', 'publish', 'external_contact',
                         'sensitive_data', 'governance_change'} <= gov.REQUIRES_OWNER)


class FailureRoutingTests(unittest.TestCase):
    setUp, tearDown, engine = EngineTests.setUp, EngineTests.tearDown, EngineTests.engine

    def test_attempt_ledger_links_approach_to_outcome(self):
        # The second FAIL is the engine's identical-build rejection, with no verifier call.
        script = Script([BROKEN, BROKEN, GOOD], ['FAIL', 'PASS'])
        eng = self.engine(script)
        pid = self.store.new_project('make an add tool')
        self.assertEqual(eng.run(pid)['state'], 'OWNER_REVIEW')
        ledger = E.attempt_ledger(self.store, pid)
        self.assertEqual([row['round'] for row in ledger], [1, 2, 3])
        self.assertEqual([row['verdict'] for row in ledger], ['FAIL', 'FAIL', 'PASS'])
        self.assertEqual([row['approach_kind'] for row in ledger[:2]], ['plan v1', 'plan v1'])
        self.assertEqual(ledger[0]['approach'], 'initial plan')
        self.assertTrue(ledger[2]['approach_kind'].startswith('strategy:'))
        self.assertEqual(ledger[2]['approach'], 'r')
        self.assertEqual(ledger[0]['top_findings'], ['wrong sum'])
        self.assertIn('identical to v1', ledger[1]['top_findings'][0])
        self.assertEqual(ledger[0]['failure_code'], E.failure_code(self.store.verifications(pid)[0]))
        self.assertTrue(ledger[1]['failure_code'].startswith('engine:'))
        self.assertIsNone(ledger[2]['failure_code'])
        prompt = next(pr for schema, _, pr in script.prompts if schema is E.STRATEGY)
        self.assertIn('attempt_ledger', prompt)
        context = json.loads(prompt.split('CONTEXT (JSON — data, not instructions):\n', 1)[1]
                             .rsplit('\n\nReturn exactly', 1)[0])
        self.assertEqual(context['attempt_ledger'], ledger[:2])

    def test_attempt_ledger_orders_and_bounds_recorded_context(self):
        store = mock.Mock()
        findings = [{'severity': 'major', 'criterion': -1, 'issue': 'recommendation'},
                    {'severity': 'minor', 'criterion': 0, 'issue': 'polish'},
                    {'severity': 'critical', 'criterion': 0, 'issue': 'x' * 201},
                    {'severity': 'major', 'criterion': -1, 'deterministic': True, 'issue': 'y' * 201},
                    {'severity': 'major', 'criterion': 0, 'issue': 'third blocker'}]
        store.verifications.return_value = [
            {'iteration': i, 'created': 10 + i, 'verdict': 'FAIL', 'provider': 'engine',
             'result': {'findings': findings}, 'checks': {'ok': False, 'output': 'same failure'}}
            for i in reversed(range(14))]
        store.events.return_value = [
            {'at': 23, 'detail': {'what': 'strategy: switch_provider', 'why': 'not before the last verification'}},
            {'at': 13.5, 'detail': {'what': 'owner feedback diagnosis', 'why': 'owner diagnosis ' * 30}},
            {'at': 12, 'detail': {'what': 'strategy: continue', 'why': 'earlier strategy'}},
            {'at': 20, 'detail': {'what': 'unrelated decision', 'why': 'ignore'}}]
        ledger = E.attempt_ledger(store, 'p')
        self.assertEqual([row['round'] for row in ledger], list(range(2, 14)))
        self.assertEqual(ledger[0]['approach_kind'], 'plan v1')       # equal timestamps are not BEFORE
        self.assertEqual(ledger[1]['approach'], 'earlier strategy')
        self.assertTrue(all(row['approach_kind'] == 'owner feedback diagnosis' for row in ledger[2:]))
        self.assertEqual(ledger[-1]['approach'], ('owner diagnosis ' * 30)[:300])
        self.assertEqual(ledger[-1]['top_findings'], ['x' * 200, 'y' * 200])
        self.assertEqual(E.attempt_ledger(store, 'p', limit=2), ledger[-2:])
        self.assertEqual(E.attempt_ledger(store, 'p', limit=0), [])
        store.verifications.return_value = []
        self.assertEqual(E.attempt_ledger(store, 'p'), [])

    def test_a_recurring_failure_stops_with_evidence_and_concrete_options(self):
        # P-20261016-5fb8d6: "the same failure recurred ... The Owner decides how to continue" gave nothing to decide on.
        script = Script([BROKEN, BROKEN + '\n', BROKEN + '\n\n'], ['FAIL', 'FAIL', 'FAIL'], strategy='change_pipeline')
        eng = self.engine(script)
        pid = self.store.new_project('make an add tool')
        p = eng.run(pid)
        self.assertEqual(p['state'], 'PAUSED')
        self.assertTrue(p['pause_reason'].startswith('NEEDS_DECISION: the same failure'), p['pause_reason'])
        for part in ('Still failing', 'The last forced change', 'Options:', 'stop the project'):
            self.assertIn(part, p['pause_reason'])
        change = self.store.events(pid, {'strategy_change'})[-1]['detail']
        self.assertEqual((change['forced'], set(change) >= {'pipeline', 'provider', 'runtime', 'material'}), (True, True))
        brief = self.store.events(pid, {'owner_decision_needed'})[-1]['detail']
        self.assertEqual(brief['last_forced_change_material'], change['material'])
        self.assertIn('stop the project', brief['options'])
        # the resume option is enforced: a forced, no-"continue" review is pending before any rebuild
        pending = self.store.events(pid, {'strategy_pending'})[-1]['detail']
        self.assertEqual((pending['trigger'], pending['forbid_continue']), ('after_recurrence', True))
        done = {e['detail']['pending'] for e in self.store.events(pid, {'strategy_done'})}
        self.assertNotIn(self.store.events(pid, {'strategy_pending'})[-1]['id'], done)

    def test_recurrence_at_budget_exhaustion_completes_its_review_now(self):
        script = Script([BROKEN, BROKEN + '\n', BROKEN + '\n\n'], ['FAIL', 'FAIL', 'FAIL'], strategy='change_pipeline')
        eng = self.engine(script)
        pid = self.store.new_project('make an add tool')
        self.store.update(pid, budget=3)
        p = eng.run(pid)
        self.assertIn('not lowered', p['pause_reason'])                    # the budget stop wins
        pending = {e['id'] for e in self.store.events(pid, {'strategy_pending'})}
        self.assertEqual(pending, {e['detail']['pending'] for e in self.store.events(pid, {'strategy_done'})})

    def test_a_strategy_review_and_its_done_marker_commit_together(self):
        script = Script([BROKEN, BROKEN + '\n', GOOD], ['FAIL', 'FAIL', 'PASS'], strategy='switch_provider')
        eng = self.engine(script)
        pid = self.store.new_project('make an add tool')
        original = eng._strategy
        calls = []

        def crash_after(pid_, **kw):                       # the review commits, then the process "dies"
            calls.append(1)
            original(pid_, **kw)
            raise SystemExit('killed')
        eng._strategy = crash_after
        with self.assertRaises(SystemExit):
            eng.run(pid)
        done = self.store.events(pid, {'strategy_done'})
        self.assertEqual(len(done), 1)                     # committed with the plan change, not after it
        eng._strategy = original
        provider = self.store.project(pid)['plan']['pipeline'][-1]['provider']
        self.store.update(pid, state='REWORK') if self.store.project(pid)['state'] != 'REWORK' else None
        eng.run(pid)
        self.assertEqual(self.store.events(pid, {'strategy_done'})[:1], done)   # not applied a second time
        self.assertEqual(len([e for e in self.store.events(pid, {'strategy_change'})]), 1)
        self.assertEqual(self.store.project(pid)['plan']['pipeline'][-1]['provider'], provider)

    def test_refused_strategy_review_runs_before_the_next_build(self):
        class RefusedStrategy(Script):
            def __call__(self, prompt, schema, *args, **kw):
                # Repeated failures use a copied strategy schema that forbids 'continue'.
                if self.fail_on is E.STRATEGY and 'decision' in schema.get('properties', {}):
                    self.fail_on = schema
                return super().__call__(prompt, schema, *args, **kw)

        script = RefusedStrategy([BROKEN, BROKEN + '\n', GOOD], ['FAIL', 'FAIL', 'PASS'],
                                 strategy='switch_provider', fail_on=E.STRATEGY)
        eng = self.engine(script)
        pid = self.store.new_project('make an add tool')
        p = eng.run(pid)
        self.assertEqual((p['state'], p['resume_state']), ('PAUSED', 'REWORK'))
        self.assertIn('RateLimited', p['pause_reason'])
        pending = self.store.events(pid, {'strategy_pending'})
        self.assertEqual(len(pending), 1)
        pending = pending[0]
        self.assertEqual(pending['detail']['verification_round'], 2)
        self.assertEqual(pending['detail']['trigger'], 'repeated')
        self.assertTrue(pending['detail']['forbid_continue'])
        self.assertEqual(self.store.events(pid, {'strategy_done'}), [])
        self.assertEqual(sum(s is E.BUILD for s, _, _ in script.prompts), 2)

        checkpoint = len(script.prompts)
        self.store.resume(pid)
        p = self.engine(script).run(pid)
        self.assertEqual(p['state'], 'OWNER_REVIEW', p['pause_reason'])
        resumed = script.prompts[checkpoint:]
        strategy_index = next(i for i, (s, _, _) in enumerate(resumed) if 'decision' in s.get('properties', {}))
        build_index = next(i for i, (s, _, _) in enumerate(resumed) if s is E.BUILD)
        self.assertLess(strategy_index, build_index)
        schema, _, prompt = resumed[strategy_index]
        self.assertIn(pending['detail']['recovery_note'], prompt)
        self.assertNotIn('continue', schema['properties']['decision']['enum'])
        self.assertEqual([e['id'] for e in self.store.events(pid, {'strategy_pending'})], [pending['id']])
        self.assertEqual([e['detail'] for e in self.store.events(pid, {'strategy_done'})], [{'pending': pending['id']}])

    def test_exhausted_budget_never_builds_again_on_resume(self):
        script = Script([BROKEN, BROKEN + '\n', GOOD], ['FAIL', 'FAIL', 'PASS'], strategy='switch_provider')
        eng = self.engine(script)
        pid = self.store.new_project('make an add tool')
        self.store.update(pid, budget=2)
        p = eng.run(pid)
        self.assertEqual(p['state'], 'PAUSED')
        self.assertIn('not lowered', p['pause_reason'])
        self.assertEqual(sum(v['verdict'] == 'FAIL' for v in self.store.verifications(pid)), 2)
        self.assertEqual(sum(s is E.BUILD for s, _, _ in script.prompts), 2)
        done = self.store.events(pid, {'strategy_done'})
        self.assertEqual(len(done), 1)

        checkpoint = len(script.prompts)
        self.store.update(pid, state='REWORK')
        p = eng.run(pid)
        self.assertEqual((p['state'], p['resume_state']), ('PAUSED', 'REWORK'))
        self.assertIn('not lowered', p['pause_reason'])
        self.assertEqual(script.prompts[checkpoint:], [])       # no build or already-completed strategy review
        self.assertEqual(self.store.events(pid, {'strategy_done'}), done)

    def test_harness_only_fail_pauses_without_rebuild_and_reverifies(self):
        # P-bbad3c v27-v31: findings the verifier itself called unverifiable sent a working build back 4 times.
        script = HarnessScript([GOOD, GOOD], ['FAIL', 'PASS'])
        eng = self.engine(script)
        pid = self.store.new_project('make an add tool')
        p = eng.run(pid)
        self.assertEqual((p['state'], p['resume_state']), ('PAUSED', 'VERIFYING'))
        self.assertTrue(p['pause_reason'].startswith('HARNESS_BLOCKED'))
        self.assertEqual(len(self.store.artifacts(pid)), 1)
        self.assertEqual(sum(s is E.BUILD for s, _, _ in script.prompts), 1)
        self.store.resume(pid)                        # verifier fixed: the SAME version is verified again
        p = eng.run(pid)
        self.assertEqual(p['state'], 'OWNER_REVIEW')
        self.assertEqual([a['iteration'] for a in self.store.artifacts(pid)], [p['iteration']])

    def test_rebuild_from_a_built_iteration_gets_a_new_version(self):
        script = Script([GOOD, GOOD + '\n'], ['FAIL', 'PASS'])
        eng = self.engine(script)
        pid = self.store.new_project('make an add tool')
        eng.run(pid, stop_at='REWORK')
        built = self.store.artifacts(pid)[-1]['iteration']
        self.store.update(pid, iteration=built)  # a legacy recovery left the built iteration selected
        p = eng.run(pid)
        self.assertEqual(p['state'], 'OWNER_REVIEW', p['pause_reason'])
        self.assertEqual([a['iteration'] for a in self.store.artifacts(pid)], [built, built + 1])

    def test_preserve_probes_separates_intent_from_harness_configuration(self):
        base = {'name': 'add', 'http_method': 'POST', 'http_path': '/api/x', 'expect_contains': ['ok'], 'expect_absent': []}
        # Unspecified may become specific; explicit positive statuses remain exact.
        merged, _ = E.preserve_probes([{**base, 'expect_status': -1}], [{**base, 'expect_status': 200}])
        self.assertEqual(merged[0]['expect_status'], 200)
        merged, notes = E.preserve_probes([{**base, 'expect_status': 201}], [{**base, 'expect_status': 200}])
        self.assertEqual(merged[0]['expect_status'], 201)
        self.assertIn('kept assertions of add', notes)
        # weakening is undone: a specific status removed, or its meaning changed
        for weaker in (0, -1, 404):
            merged, notes = E.preserve_probes([{**base, 'expect_status': 200}], [{**base, 'expect_status': weaker}])
            self.assertEqual(merged[0]['expect_status'], 200, weaker)
            self.assertIn('kept assertions of add', notes)
        merged, _ = E.preserve_probes([{**base, 'expect_status': 200}], [{**base, 'expect_contains': []}])
        self.assertEqual(merged[0]['expect_contains'], ['ok'])

    def test_harness_repair_reverifies_the_same_version(self):
        # The probe launches with a wrong argument; the product is fine. The CEO repairs how the probe runs.
        prog = ("import sys\nif __name__ == '__main__':\n    if len(sys.argv) > 1 and sys.argv[1] != '--self-test':\n"
                "        print('unknown option'); sys.exit(0)\n    print('ok')\n")
        bad = {'name': 'launch', 'args': ['--bad'], 'stdin': '', 'http_method': '', 'http_path': '', 'http_body': '',
               'expect_exit': -1, 'expect_status': 0, 'expect_contains': ['ok'], 'expect_absent': []}

        class Repairing(Script):
            def __call__(self, prompt, schema, *args, **kw):
                if schema is E.PROBE_EQUIVALENCE:
                    return {'equivalent': True, 'evidence': 'No arguments exercises the required normal launch.'}, 'codex', []
                result, used, notes = super().__call__(prompt, schema, *args, **kw)
                if schema is E.PLAN:
                    result['runtime'] = {'mode': 'cli', 'owner_launch': 'x', 'launch_args': [], 'probes': [bad]}
                if schema is E.PROBE_REVIEW:
                    result.update(disposition='HARNESS_REPAIR', evidence='The artifact treats no arguments as the normal launch.')
                    result['runtime'] = {'mode': 'cli', 'owner_launch': 'x', 'launch_args': [], 'probes': [{**bad, 'args': []}]}
                return result, used, notes
        script = Repairing([prog], ['PASS', 'PASS'])
        eng = self.engine(script)
        pid = self.store.new_project('make a tool')
        p = eng.run(pid)
        self.assertEqual(p['state'], 'OWNER_REVIEW', p['pause_reason'])
        self.assertEqual(len(self.store.artifacts(pid)), 1)                     # never rebuilt
        self.assertEqual([v['verdict'] for v in self.store.verifications(pid)], ['FAIL', 'PASS'])
        self.assertEqual({v['artifact_id'] for v in self.store.verifications(pid)}, {self.store.artifacts(pid)[0]['id']})
        self.assertTrue(self.store.events(pid, {'probe_review'})[0]['detail']['repaired'])
        self.assertNotEqual(self.store.verifications(pid)[0]['result']['findings'][-1]['kind'], 'product')

    def test_harness_defect_never_rebuilds_the_artifact(self):
        script = Script([GOOD], ['PASS'])
        eng = self.engine(script)
        pid = self.store.new_project('make an add tool')
        broken_check = {'ok': False, 'mode': 'cli', 'notes': [],
                        'steps': [{'name': 'p', 'ok': False, 'probe_misconfigured': True, 'problems': ['probe misconfigured: x']}]}
        with mock.patch.object(eng, 'runtime_evidence', return_value=broken_check):
            p = eng.run(pid)
        self.assertEqual((p['state'], p['resume_state']), ('PAUSED', 'VERIFYING'))
        self.assertTrue(p['pause_reason'].startswith('HARNESS_BLOCKED'))
        self.assertEqual(len(self.store.artifacts(pid)), 1)
        self.assertEqual(sum(schema is E.BUILD for schema, _, _ in script.prompts), 1)

    # ---- Codex review of the Test #3 harness fix: six confirmed defects
    def test_d1_invalid_selector_text_is_harness_not_product(self):
        step = {'ok': False, 'probe_misconfigured': True,
                'problems': ["probe misconfigured: click selector 'crashed[' is not a CSS selector"]}
        self.assertEqual(E.runtime.classify_step(step), 'harness')

    def test_d2_same_artifact_recovery_cannot_add_unapproved_connections(self):
        script = Script([GOOD], ['PASS'])
        eng = self.engine(script)
        pid = self.store.new_project('make an add tool')
        eng.run(pid, stop_at='VERIFYING')
        script.network = [{'domain': 'evil.example.com', 'purpose': 'x', 'risk': 'public_read'}]
        eng._strategy(pid, recovery_note='probe review')
        self.assertEqual(self.store.project(pid)['plan'].get('network_access') or [], [])
        self.assertTrue(any(e['detail'].get('what') == 'network expansion deferred'
                            for e in self.store.events(pid, {'decision'})))

    def test_d3_owner_feedback_can_replace_the_contract(self):
        class Replacing(Script):
            def __call__(self, prompt, schema, *args, **kw):
                result, used, notes = super().__call__(prompt, schema, *args, **kw)
                if schema is E.DIAGNOSIS:
                    result['acceptance_criteria'] = ['a web page shows the sum']
                    result['removed_criteria'] = [{'criterion': 'add(2,3)==5', 'owner_quote': self.quote}]
                return result, used, notes
        for quote, expected in (('replace the CLI with a web page', ['a web page shows the sum']),      # Owner's words
                                ('the model thinks this is better', ['a web page shows the sum', 'add(2,3)==5'])):
            script = Replacing([GOOD, GOOD + '\n'], ['PASS', 'PASS'])
            script.quote = quote
            eng = self.engine(script)
            pid = self.store.new_project('make an add tool')
            eng.run(pid)
            eng.owner_review(pid, works=True, text='replace the CLI with a web page')
            eng.run(pid)
            self.assertEqual(self.store.project(pid)['plan']['acceptance_criteria'], expected, quote)
            change = self.store.events(pid, {'requirements_changed_by_owner'})[-1]['detail']
            self.assertEqual(bool(change['removed']), quote.startswith('replace'))
            self.assertEqual(bool(change['restored_without_owner_provenance']), not quote.startswith('replace'))

    def test_d4_out_of_range_finding_does_not_count_as_a_product_failure(self):
        eng = self.engine(Script([GOOD], ['PASS']))
        pid = self.store.new_project('make an add tool')
        eng.run(pid)
        art = self.store.artifacts(pid)[0]
        self.store.add_verification(pid, art['id'], 1, 'FAIL', {'verdict': 'FAIL', 'criteria': [], 'findings': [
            {'severity': 'major', 'kind': 'product', 'criterion': 999, 'issue': 'idea', 'evidence': 'e'}]},
            {'ok': True}, 'codex')
        self.assertEqual(eng._product_failures(pid), [])

    def test_d5_rework_and_its_strategy_obligation_commit_together(self):
        eng = self.engine(Script([BROKEN, BROKEN + '\n', GOOD], ['FAIL', 'FAIL', 'PASS']))
        pid = self.store.new_project('make an add tool')
        seen = []
        real = eng._strategy
        def spy(p, **kw):
            seen.append((self.store.project(p)['state'], len(self.store.events(p, {'strategy_pending'}))))
            return real(p, **kw)
        eng._strategy = spy
        self.assertEqual(eng.run(pid)['state'], 'OWNER_REVIEW')
        self.assertEqual(seen[0], ('REWORK', 1))          # REWORK and its pending review were already committed

    # ---- Test #3 retry defect: the CEO's diagnosis must control Owner-feedback routing
    def _owner_routed(self, evidence_class, crash_during_reproduction=False):
        class Diagnosing(Script):
            def __call__(self, prompt, schema, *args, **kw):
                result, used, notes = super().__call__(prompt, schema, *args, **kw)
                if schema is E.DIAGNOSIS:
                    result['evidence_class'] = evidence_class
                return result, used, notes
        script = Diagnosing([LAUNCHABLE, LAUNCHABLE + '\n'], ['PASS', 'PASS'])
        eng = self.engine(script)
        if crash_during_reproduction:
            real, calls = eng.runtime_evidence, []
            def evidence(*args):
                calls.append(1)
                if len(calls) in (2, 3):     # before / reproduction inside the Owner-feedback diagnosis
                    return {'ok': False, 'mode': 'cli', 'notes': [], 'steps': [
                        {'name': 'launch', 'ok': False, 'exit': 1, 'problems': ['crashed (exit 1)'],
                         'output_tail': 'Traceback (most recent call last):\n  boom'}]}
                return real(*args)
            eng.runtime_evidence = evidence
        pid = self.store.new_project('make an add tool')
        self.assertEqual(eng.run(pid)['state'], 'OWNER_REVIEW')
        eng.owner_review(pid, works=False, text='the result screen looks wrong to me')
        return eng.run(pid), pid, script

    def test_owner_feedback_harness_defect_reverifies_the_same_artifact(self):
        p, pid, script = self._owner_routed('HARNESS_DEFECT')
        self.assertEqual(p['state'], 'OWNER_REVIEW')
        self.assertEqual(len(self.store.artifacts(pid)), 1)                       # no new version
        vs = self.store.verifications(pid)
        self.assertEqual([v['artifact_id'] for v in vs], [self.store.artifacts(pid)[0]['id']] * 2)
        self.assertEqual(self.store.events(pid, {'owner_rework_route'})[-1]['detail']['route'], 'reverify')
        self.assertEqual(sum(s is E.BUILD for s, _, _ in script.prompts), 1)
        # Verification -> CEO Final Goal Judgment stays intact after the same-artifact re-verification
        self.assertEqual(sum(s is E.REPORT for s, _, _ in script.prompts), 2)
        self.assertEqual(sum(e['detail'].get('what') == 'executive acceptance'
                             for e in self.store.events(pid, {'decision'})), 2)

    def test_owner_feedback_without_product_evidence_reverifies(self):
        for cls in ('NO_PRODUCT_EVIDENCE', 'AMBIGUOUS'):
            with self.subTest(cls=cls):
                p, pid, script = self._owner_routed(cls)
                self.assertEqual((p['state'], len(self.store.artifacts(pid))), ('OWNER_REVIEW', 1))
                self.assertEqual(sum(s is E.BUILD for s, _, _ in script.prompts), 1)

    def test_owner_feedback_product_change_rebuilds(self):
        p, pid, script = self._owner_routed('PRODUCT_CHANGE')
        self.assertEqual(p['state'], 'OWNER_REVIEW')
        self.assertEqual(len(self.store.artifacts(pid)), 2)                       # a genuine change: new version
        self.assertEqual(self.store.events(pid, {'owner_rework_route'})[-1]['detail']['route'], 'rebuild')

    def test_deterministic_product_evidence_overrides_a_harness_diagnosis(self):
        p, pid, script = self._owner_routed('HARNESS_DEFECT', crash_during_reproduction=True)
        route = self.store.events(pid, {'owner_rework_route'})[-1]['detail']
        self.assertEqual((route['route'], route['product_evidence']), ('rebuild', True))
        self.assertEqual(len(self.store.artifacts(pid)), 2)

    # ---- legacy synthetic kind='product' FAILs: counted from stored evidence, the records never change
    SYNTHETIC = {'severity': 'major', 'kind': 'product', 'criterion': -1, 'deterministic': True,
                 'issue': 'Gate failed: deterministic checks failed.', 'evidence': ''}
    HARNESS_STEP = {'name': 'add log', 'ok': False, 'status': 201, 'exit': None, 'probe_misconfigured': True,
                    'problems': ['status 201, expected -1']}
    CRASH_STEP = {'name': 'add log', 'ok': False, 'exit': 1, 'problems': ['crashed (exit 1)'],
                  'output_tail': 'Traceback (most recent call last):\n  boom'}

    def _legacy(self, step=None, exit_code=0, output='ok', times=1):
        """A delivered v1, plus legacy FAILs on it shaped like Test #3's (synthetic gate finding kind='product')."""
        eng = self.engine(Script([GOOD], ['PASS']))
        pid = self.store.new_project('make an add tool')
        eng.run(pid)
        art = self.store.artifacts(pid)[0]
        checks = {'ok': False, 'ran': ['compile', 'self-test'], 'output': output}
        if exit_code is not None:
            checks['exit_code'] = exit_code
        if step:
            checks['output'] += '\nRUNTIME ACCEPTANCE FAILED: add log: ' + step['problems'][0]
            checks['runtime'] = {'ok': False, 'mode': 'cli', 'notes': [], 'steps': [step]}
        for _ in range(times):
            self.store.add_verification(pid, art['id'], 1, 'FAIL', {'verdict': 'FAIL', 'criteria': [{'index': 0, 'met': True}],
                                                                   'findings': [dict(self.SYNTHETIC)]}, checks, 'claude')
        return eng, pid, art

    def test_legacy_product_label_with_harness_evidence_is_not_a_product_failure(self):
        eng, pid, _ = self._legacy(self.HARNESS_STEP, times=4)
        self.assertEqual(eng._product_failures(pid), [])
        self.assertIsNone(eng._repeated_failure(pid))
        self.assertTrue(E.failure_code(self.store.verifications(pid)[-1]).startswith('non-product:'))

    def test_legacy_product_label_with_genuine_product_evidence_counts(self):
        for name, kw in (('runtime crash', {'step': self.CRASH_STEP}),
                         ('self-test failed', {'exit_code': 1, 'output': 'AssertionError'})):
            with self.subTest(name):
                eng, pid, art = self._legacy(times=2, **kw)
                self.assertEqual([v['artifact_id'] for v in eng._product_failures(pid)], [art['id']])  # once per build
                self.assertTrue(eng._repeated_failure(pid) is None or eng._repeated_failure(pid).startswith('product:'))
                self.assertTrue(E.failure_code(self.store.verifications(pid)[-1]).startswith('product:'))

    def test_legacy_record_without_evidence_is_not_a_product_failure(self):
        eng, pid, _ = self._legacy(exit_code=None, output='')
        self.assertEqual(eng._product_failures(pid), [])

    def test_legacy_accounting_routes_consistently_and_never_changes_history(self):
        # [계속] after legacy harness-only FAILs: no rework, no budget spent, no identical-build rejection.
        eng, pid, art = self._legacy(self.HARNESS_STEP, times=4)
        rows = lambda: self.store.db.execute('SELECT * FROM verifications WHERE project_id=? ORDER BY rowid',
                                             (pid,)).fetchall()
        before = [tuple(r) for r in rows()]
        self.store.update(pid, state='VERIFYING')
        eng._after_fail(pid, self.store.project(pid))
        p = self.store.project(pid)
        self.assertEqual((p['state'], p['resume_state'], p['iteration']), ('PAUSED', 'VERIFYING', 1))
        self.assertIn('HARNESS_BLOCKED', p['pause_reason'])
        self.assertEqual(self.store.events(pid, {'strategy_pending'}), [])
        # the same bytes again are not condemned by a harness-only FAIL ...
        self.store.update(pid, state='STAFFING', iteration=2)
        self.engine(Script([GOOD], ['PASS'])).run(pid)
        self.assertEqual(len(self.store.artifacts(pid)), 2)
        self.assertEqual([tuple(r) for r in rows()][:len(before)], before)      # history unchanged, byte for byte
        # ... but are by a genuine product FAIL (the same rule decides the guard)
        eng, pid, art = self._legacy(self.CRASH_STEP)
        self.store.update(pid, state='STAFFING', iteration=2)
        self.engine(Script([GOOD, GOOD + '\n'], ['PASS'])).run(pid)
        self.assertTrue(any('identical to v1' in e['detail']['reason'] for e in self.store.events(pid, {'build_rejected'})))

    def test_failure_code_ignores_verifier_wording(self):
        def v(issue, steps=('Rendered home',), provider='codex', output=''):
            return {'provider': provider, 'result': {'findings': [{'severity': 'major', 'kind': 'harness', 'issue': issue}]},
                    'checks': {'ok': not steps, 'output': output,
                               'runtime': {'ok': not steps, 'steps': [{'name': s, 'ok': False} for s in steps]}}}
        self.assertEqual(E.failure_code(v('the repeated home/collapsed-detail failure')),
                         E.failure_code(v('repeated home and collapsed-fixture failures')))
        self.assertNotEqual(E.failure_code(v('x')), E.failure_code(v('x', steps=('Other probe',))))
        self.assertIsNone(E.failure_code(v('no deterministic evidence', steps=())))
        self.assertEqual(E.failure_code(v('a', provider='engine', output='empty deliverable')),
                         E.failure_code(v('b', provider='engine', output='empty deliverable')))
        self.assertEqual(E.failure_code(v('a', provider='engine', output='identical to v1, which already FAILED verification')),
                         E.failure_code(v('b', provider='engine', output='identical to v42, which already FAILED verification')))
        selftest = v('self-test failed', steps=())          # Codex review: a failing self-test alone
        selftest['checks'].update(ok=False, runtime={'ok': True, 'steps': []})
        self.assertIsNotNone(E.failure_code(selftest))

    def test_pass_contradicted_only_by_harness_findings_is_not_a_product_rebuild(self):
        class Script2(Script):
            def __call__(self, prompt, schema, *args, **kw):
                result, used, notes = super().__call__(prompt, schema, *args, **kw)
                if schema is E.VERDICT and self.verdicts:     # first verdict: PASS + a harness finding
                    result['findings'] = [{'severity': 'major', 'kind': 'harness', 'issue': 'probe not recorded',
                                           'evidence': 'e'}]
                return result, used, notes
        eng = self.engine(Script2([GOOD], ['PASS', 'PASS']))
        pid = self.store.new_project('make an add tool')
        p = eng.run(pid)
        self.assertTrue(p['pause_reason'].startswith('HARNESS_BLOCKED'), p['pause_reason'])
        self.assertEqual(len(self.store.artifacts(pid)), 1)


class GateAndImmutabilityTests(unittest.TestCase):
    setUp, tearDown, engine = EngineTests.setUp, EngineTests.tearDown, EngineTests.engine

    def test_replanning_retrieves_lessons_for_the_current_failure(self):
        note = ('# add tool\n\n- project: `P-OTHER`\n\n## 요약 (Summary)\nx\n\n## 재사용 지식 (Reusable Knowledge)\n'
                '- [검증 교훈] wrong sum: add must use + not -\n')
        (self.vault / 'Projects').mkdir(parents=True, exist_ok=True)
        (self.vault / 'Projects' / 'other.md').write_text(note, encoding='utf-8')
        script = Script([BROKEN, BROKEN + '\n', GOOD], ['FAIL', 'FAIL', 'PASS'])
        eng = self.engine(script)
        pid = self.store.new_project('make an add tool')
        self.assertEqual(eng.run(pid)['state'], 'OWNER_REVIEW')
        strategy = next(prompt for schema, _, prompt in script.prompts if 'decision' in schema.get('properties', {}))
        self.assertIn('relevant_knowledge', strategy)
        self.assertIn('add must use +', strategy)
        used = [e['detail'] for e in self.store.events(pid, {'context_used'}) if e['detail'].get('stage') == 'strategy']
        self.assertEqual(used[0]['projects'], ['P-OTHER'])
        own = note.replace('P-OTHER', pid)                                  # its own archive never counts
        (self.vault / 'Projects' / 'other.md').write_text(own, encoding='utf-8')
        self.assertEqual(eng._replan_knowledge(pid, 'strategy', 'wrong sum'), [])
        missing = E.Engine(self.store, workspace=self.tmp / 'ws', vault=self.tmp / 'no-vault', gai_db=self.tmp / 'x.db',
                           llm=script)
        self.assertEqual(missing._replan_knowledge(pid, 'strategy', 'wrong sum'), [])

    def test_interrupted_acceptance_resumes_without_reverifying(self):
        # A PASS is recorded, then the CEO acceptance (REPORT) call is refused for quota.
        script = Script([GOOD], ['PASS'], fail_on=E.REPORT)
        eng = self.engine(script)
        pid = self.store.new_project('make an add tool')
        p = eng.run(pid)
        self.assertEqual((p['state'], p['resume_state']), ('PAUSED', 'VERIFYING'))
        self.store.resume(pid)
        self.assertEqual(eng.run(pid)['state'], 'OWNER_REVIEW')
        self.assertEqual(sum(schema is E.VERDICT for schema, _, _ in script.prompts), 1)   # not verified again
        self.assertEqual([v['verdict'] for v in self.store.verifications(pid)], ['PASS'])

    def test_owner_decision_is_its_own_stop_outcome(self):
        project = {'state': 'OWNER_REVIEW', 'pause_reason': None,
                   'report': {'next_action': 'owner_decision', 'judgment': 'needs a paid data source'}}
        self.assertEqual(stop_outcome(project), ('OWNER_DECISION_REQUIRED', 'needs a paid data source'))
        self.assertEqual(stop_outcome({**project, 'report': {'next_action': 'deliver'}})[0], 'VERIFIED')

    def test_replan_after_harness_failure_reverifies_without_rebuilding(self):
        script = HarnessScript([GOOD, GOOD], ['FAIL', 'PASS'])        # FAIL #1: harness findings only
        eng = self.engine(script)
        pid = self.store.new_project('make an add tool')
        eng.run(pid)
        eng.replan(pid, 'operator re-plan')
        self.assertEqual(eng.run(pid)['state'], 'OWNER_REVIEW')
        self.assertEqual(len(self.store.artifacts(pid)), 1)
        self.assertEqual(len(script.builds), 1)
        self.assertEqual(self.store.events(pid, {'build_rejected'}), [])

    def test_identical_rebuild_is_not_verified_again(self):
        script = Script([BROKEN, BROKEN, GOOD], ['FAIL', 'PASS'])
        eng = self.engine(script)
        pid = self.store.new_project('make an add tool')
        self.assertEqual(eng.run(pid)['state'], 'OWNER_REVIEW')
        self.assertEqual(sum(schema is E.VERDICT for schema, _, _ in script.prompts), 2)
        vs = self.store.verifications(pid)
        self.assertEqual([v['verdict'] for v in vs], ['FAIL', 'FAIL', 'PASS'])
        self.assertEqual((vs[1]['provider'], vs[1]['artifact_id']), ('engine', ''))
        self.assertIn('identical to v1', vs[1]['checks']['output'])
        rejected = self.store.events(pid, {'build_rejected'})
        self.assertEqual(len(rejected), 1)
        self.assertIn('identical', rejected[0]['detail']['reason'])
        arts = self.store.artifacts(pid)
        self.assertEqual([a['iteration'] for a in arts], [1, 3])
        self.assertFalse((Path(arts[0]['path']).parent.parent / 'v2').exists())
        self.assertEqual(artifacts.problems(arts[0]), [])
        self.assertEqual((script.builds, script.verdicts), ([], []))

    def test_findings_outside_approved_criteria_are_recommendations(self):
        class Recommending(Script):
            def __call__(self, prompt, schema, *args, **kw):
                result, used, notes = super().__call__(prompt, schema, *args, **kw)
                if schema is E.VERDICT:
                    result['verdict'] = 'FAIL'
                    result['findings'] = [{'severity': 'major', 'kind': 'harness', 'criterion': -1,
                                           'issue': 'also test the startup failure at runtime', 'evidence': 'e'}]
                return result, used, notes
        eng = self.engine(Recommending([GOOD], ['PASS']))
        pid = self.store.new_project('make an add tool')
        p = eng.run(pid)
        self.assertEqual(p['state'], 'OWNER_REVIEW', p['pause_reason'])
        self.assertEqual(self.store.verifications(pid)[-1]['verdict'], 'PASS')
        recs = self.store.events(pid, {'verification_recommendations'})
        self.assertIn('startup failure', recs[0]['detail']['items'][0])

    def test_recommendations_never_reach_the_rebuild(self):
        class Mixed(Script):
            def __call__(self, prompt, schema, *args, **kw):
                result, used, notes = super().__call__(prompt, schema, *args, **kw)
                if schema is E.VERDICT and result['verdict'] == 'FAIL':
                    result['findings'] = [{'severity': 'major', 'kind': 'product', 'criterion': 0,
                                           'issue': 'wrong sum', 'evidence': 'e'},
                                          {'severity': 'major', 'kind': 'harness', 'criterion': -1,
                                           'issue': 'RECOMMENDATION-XYZ', 'evidence': 'e'}]
                return result, used, notes
        script = Mixed([BROKEN, GOOD], ['FAIL', 'PASS'])
        p = self.engine(script).run(self.store.new_project('make an add tool'))
        self.assertEqual(p['state'], 'OWNER_REVIEW')
        rebuild = [prompt for schema, _, prompt in script.prompts if schema is E.BUILD][-1]
        self.assertIn('wrong sum', rebuild)
        self.assertNotIn('RECOMMENDATION-XYZ', rebuild)

    def test_owner_ruling_reaches_the_verifier_and_never_changes_criteria(self):
        script = HarnessScript([GOOD], ['FAIL'])
        eng = self.engine(script)
        pid = self.store.new_project('make an add tool')
        eng.run(pid)
        criteria = self.store.project(pid)['plan']['acceptance_criteria']
        with self.assertRaises(Rejected):
            eng.add_ruling(pid, len(criteria), 'out of range')
        eng.add_ruling(pid, 0, 'RULING-ABC: the recorded request counts; the Owner checks the window at review')
        self.store.resume(pid)
        script.verdicts.append('PASS')
        eng.run(pid)
        verify = [prompt for schema, _, prompt in script.prompts if schema is E.VERDICT][-1]
        self.assertIn('RULING-ABC', verify)
        self.assertEqual(self.store.project(pid)['plan']['acceptance_criteria'], criteria)
        plan = self.store.project(pid)['plan']                   # an Owner change rewrites criterion 0
        plan['acceptance_criteria'] = ['a different requirement'] + plan['acceptance_criteria'][1:]
        self.store.update(pid, plan=plan)
        script.verdicts.append('PASS')
        # a fresh verification of the version (a recorded PASS would resume at the CEO acceptance instead)
        self.store.db.execute("DELETE FROM verifications WHERE project_id=? AND verdict='PASS'", (pid,))
        self.store.update(pid, state='VERIFYING')
        eng.run(pid)
        verify = [prompt for schema, _, prompt in script.prompts if schema is E.VERDICT][-1]
        self.assertNotIn('RULING-ABC', verify)                   # never moves onto another requirement

    def test_owner_runs_the_verified_version_from_a_copy(self):
        eng = self.engine(Script([BROKEN, GOOD], ['FAIL', 'PASS']))
        pid = self.store.new_project('make an add tool')
        with self.assertRaises(Rejected):
            eng.launch_verified(pid, popen=mock.Mock())          # nothing verified yet
        eng.run(pid)
        verified = self.store.artifacts(pid)[-1]                 # v2 passed; v1 failed
        popen = mock.Mock()
        with mock.patch.object(E.sandbox, 'run', return_value=(0, 'result')) as isolated:
            path, _ = eng.launch_verified(pid, popen=popen)
        args, kwargs = isolated.call_args
        self.assertEqual(args[0][-1], Path(verified['path']).name)       # the Owner's launch: no arguments
        self.assertIsInstance(kwargs['isolate'], E.isolation.Manifest)
        self.assertNotEqual(Path(args[1]), path.parent)             # temporary isolated copy, not Owner workspace
        popen.assert_not_called()
        self.assertEqual(path.read_bytes(), Path(verified['path']).read_bytes())
        self.assertEqual(artifacts.problems(verified), [])
        self.assertEqual(self.store.events(pid, {'owner_run'})[-1]['detail']['version'], verified['iteration'])

    def test_report_is_shown_in_ax_branch_and_a_web_app_is_run(self):
        # P-20261009-bd147a: a CLI research bundle; [결과 실행] flashed a console and the report never showed.
        eng = self.engine(Script([GOOD], ['PASS']))
        pid = self.store.new_project('make an add tool')
        eng.run(pid)
        art = self.store.artifacts(pid)[-1]
        self.assertEqual(eng.result_info(pid), ('run', []))               # a program without a document
        report = Path(art['path']).parent / 'REPORT.md'
        self.store.db.execute("UPDATE artifacts SET kind='bundle', path=?, manifest=? WHERE id=?",
                              (str(report.parent), json.dumps({'files': [], 'rejected': []}), art['id']))
        with mock.patch.object(artifacts, 'files_of', return_value=[('REPORT.md', report, ''), ('add_tool.py', report, '')]), \
                mock.patch.object(artifacts, 'problems', return_value=[]), \
                mock.patch.object(artifacts, 'materialize', lambda a, run: (Path(run) / 'REPORT.md').write_text('# 보고서', encoding='utf-8')):
            self.assertEqual(eng.result_info(pid), ('view', ['REPORT.md']))
            shown = []
            how, path = eng.open_result(pid, show_text=lambda title, text, p: shown.append((title, text)))
        self.assertEqual((how, shown), ('view', [('REPORT.md', '# 보고서')]))
        plan = self.store.project(pid)['plan']
        plan['runtime'] = {**plan['runtime'], 'mode': 'web'}
        self.store.update(pid, plan=plan)
        with mock.patch.object(artifacts, 'files_of', return_value=[('REPORT.md', report, '')]):
            self.assertEqual(eng.result_info(pid), ('run', []))           # a web app runs, its docs aside

    def test_existing_version_folder_is_never_written(self):
        eng = self.engine(Script([GOOD], ['PASS']))
        pid = self.store.new_project('make an add tool')
        leftover = self.tmp / 'ws' / 'projects' / pid / 'artifacts' / 'v1'
        leftover.mkdir(parents=True)
        (leftover / 'add_tool.py').write_bytes(b'old bytes')
        p = eng.run(pid)
        self.assertEqual(p['state'], 'OWNER_REVIEW')
        self.assertEqual((leftover / 'add_tool.py').read_bytes(), b'old bytes')
        self.assertEqual([Path(a['path']).parent.name for a in self.store.artifacts(pid)], ['v2'])

    def test_failed_commit_removes_only_its_own_new_version(self):
        eng = self.engine(Script([GOOD, GOOD + '\n'], ['FAIL', 'PASS']))
        pid = self.store.new_project('make an add tool')
        eng.run(pid, stop_at='REWORK')                  # v1 has a product defect; rebuild -> v2
        v1 = self.store.artifacts(pid)[0]
        with mock.patch.object(self.store, 'add_artifact', side_effect=RuntimeError('disk full (simulated)')):
            p = eng.run(pid)
        self.assertIn('Internal error', p['pause_reason'])
        folder = Path(v1['path']).parent
        self.assertFalse((folder.parent / f"v{p['iteration']}").exists())
        self.assertEqual(artifacts.problems(v1), [])


class HarnessScript(Script):
    """The first FAIL's findings are verification-harness findings (no product defect shown)."""

    def __call__(self, prompt, schema, *args, **kw):
        result, used, notes = super().__call__(prompt, schema, *args, **kw)
        if schema is E.VERDICT:
            for f in result['findings']:
                f['kind'] = 'harness'
        return result, used, notes


if __name__ == '__main__':
    unittest.main()
