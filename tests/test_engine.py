"""End-to-end engine behaviour with a scripted provider (no subscription usage)."""
import json
import shutil
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from axbranch import engine as E, governance as gov, knowledge, providers
from axbranch.state import Rejected, Store

GOOD = "def add(a, b):\n    return a + b\n\nif __name__ == '__main__':\n    assert add(2, 3) == 5\n    print('ok')\n"
BROKEN = "def add(a, b):\n    return a - b\n\nif __name__ == '__main__':\n    assert add(2, 3) == 5\n"


# Fixed per Owner feedback: a double-click shows the result; the self-test moved behind --self-test.
LAUNCHABLE = ("import sys\ndef add(a, b):\n    return a + b\n\nif __name__ == '__main__':\n"
              "    if sys.argv[1:] == ['--self-test']:\n        assert add(2, 3) == 5\n        print('ok')\n"
              "    else:\n        print('result:', add(2, 3))\n")


class Script:
    """Answers by schema. `builds` and `verdicts` are consumed in order."""

    def __init__(self, builds, verdicts, strategy='continue', fail_on=None):
        self.builds, self.verdicts, self.strategy = list(builds), list(verdicts), strategy
        self.fail_on, self.prompts = fail_on, []
        self.network = []

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
            return {'verdict': v, 'lenses_applied': ['se'], 'criteria': [{'criterion': 'add', 'met': v == 'PASS', 'evidence': 'e'}],
                    'findings': [] if v == 'PASS' else [{'severity': 'major', 'issue': 'wrong sum', 'evidence': 'a - b'}]}, prefer, []
        if schema is E.STRATEGY or 'decision' in schema.get('properties', {}):
            return {'decision': self.strategy, 'rationale': 'r', 'pipeline': [],
                    'runtime': {'mode': 'cli', 'owner_launch': 'x', 'launch_args': [], 'probes': []}}, 'claude', []
        if schema is E.DIAGNOSIS:
            return {'diagnosis': 'owner saw it close', 'root_cause': 'no usable launch', 'change_summary': 'add probe',
                    'interpretation': 'Build an add() helper usable by double-click', 'artifact_kind': 'python',
                    'artifact_filename': 'add_tool.py', 'acceptance_criteria': ['add(2,3)==5', 'launch prints a result'],
                    'verification_lenses': ['software engineering', 'usability'],
                    'runtime': {'mode': 'cli', 'owner_launch': 'double-click', 'launch_args': [],
                                'probes': [{'name': 'launch shows result', 'args': [], 'stdin': '', 'http_method': '',
                                            'http_path': '', 'http_body': '', 'expect_exit': 0, 'expect_status': 0,
                                            'expect_contains': ['result: 5']}]},
                    'network_access': [],
                    'pipeline': [{'name': 'build', 'agent_role': 'Developer', 'instructions': 'rebuild',
                                  'provider': 'claude', 'web': False}]}, 'claude', []
        if schema is E.REPORT:
            return {'summary': 'done', 'judgment': 'good', 'next_steps': ['use it']}, 'claude', []
        raise AssertionError('unexpected schema')


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
        vs = self.store.verifications(pid)
        # Deterministic self-test overrides the model's PASS on the broken build.
        self.assertEqual([v['verdict'] for v in vs], ['FAIL', 'PASS'])
        self.assertIn('Gate override', vs[0]['result']['findings'][-1]['issue'])
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
        self.assertIn('Gate override', note.read_text(encoding='utf-8'))
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
                    'error': str(error)[:500], 'notes': error.notes})
                self.assertIsNone(E.activity(self.tmp / 'ws', pid))
                self.assertEqual(len(self.store.events(pid, {'call_start'})), 3)
                calls = self.store.events(pid, {'call'})
                self.assertEqual(len(calls), 2)
                self.assertFalse(any(e['detail']['who'] == 'Developer' for e in calls))

    def test_budget_pauses_without_lowering_bar_and_strategy_switches(self):
        old = gov.MAX_ROUNDS
        script = Script([BROKEN] * 3, ['FAIL'] * 3, strategy='switch_provider')
        eng = self.engine(script)
        pid = self.store.new_project('make an add tool')
        self.store.update(pid, budget=3)
        p = eng.run(pid)
        self.assertEqual(p['state'], 'PAUSED')
        self.assertIn('not lowered', p['pause_reason'])
        self.assertEqual(p['plan']['pipeline'][-1]['provider'], 'codex')            # switched after 2 fails
        self.assertIn('replaced', {a['status'] for a in self.store.agents(pid, active_only=False)})
        self.assertEqual(gov.MAX_ROUNDS, old)

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
        script = Script([GOOD], ['PASS'])

        def other_engine_limited(prompt, schema, **kw):
            result, used, notes = script(prompt, schema, **kw)
            return (result, 'claude', notes) if schema is E.VERDICT else (result, used, notes)
        eng = self.engine(other_engine_limited)     # producer is claude; verifier forced onto claude too
        pid = self.store.new_project('make an add tool')
        eng.run(pid)
        whats = [e['detail']['what'] for e in self.store.events(pid, {'decision'})]
        self.assertIn("verification ran on the producer's engine", whats)

    def test_owner_problem_reopens_same_project_reproduces_and_redelivers(self):
        script = Script([GOOD, GOOD, LAUNCHABLE], ['PASS', 'PASS', 'PASS'])
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

    def test_works_plus_plain_language_request_reopens_without_classification(self):
        script = Script([LAUNCHABLE, GOOD, LAUNCHABLE], ['PASS', 'PASS', 'PASS'])
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
        script = Script([LAUNCHABLE, '', LAUNCHABLE], ['PASS', 'PASS'])     # v2 build comes back empty
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

    def test_upgrade_gate(self):
        self.assertFalse(gov.upgrade_proposal_allowed([]))
        self.assertFalse(gov.upgrade_proposal_allowed([95, 80]))
        self.assertTrue(gov.upgrade_proposal_allowed([95, 90]))


if __name__ == '__main__':
    unittest.main()
