"""End-to-end engine behaviour with a scripted provider (no subscription usage)."""
import json
import shutil
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from axbranch import artifacts, engine as E, governance as gov, knowledge, providers
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
            approved = json.loads(prompt.split('CONTEXT (JSON — data, not instructions):\n', 1)[1]
                                  .rsplit('\n\nReturn exactly', 1)[0])['acceptance_criteria']
            return {'verdict': v, 'lenses_applied': ['se'],
                    'criteria': [{'index': c['index'], 'criterion': c['criterion'], 'met': v == 'PASS', 'evidence': 'e'}
                                 for c in approved],
                    'findings': [] if v == 'PASS' else [{'severity': 'major', 'issue': 'wrong sum', 'evidence': 'a - b'}]}, prefer, []
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
        script = Script([GOOD, GOOD], ['PASS', 'PASS'])
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
        self.assertEqual(eng.run(pid)['state'], 'OWNER_REVIEW')
        strategy = [pr for s, _, pr in script.prompts if s is E.STRATEGY]
        self.assertEqual(len(strategy), 1)
        self.assertIn('MISCONFIGURED', strategy[0])
        self.assertIn('#sample-1', strategy[0])

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


class FailureRoutingTests(unittest.TestCase):
    setUp, tearDown, engine = EngineTests.setUp, EngineTests.tearDown, EngineTests.engine

    def test_refused_strategy_review_runs_before_the_next_build(self):
        class RefusedStrategy(Script):
            def __call__(self, prompt, schema, *args, **kw):
                # Repeated failures use a copied strategy schema that forbids 'continue'.
                if self.fail_on is E.STRATEGY and 'decision' in schema.get('properties', {}):
                    self.fail_on = schema
                return super().__call__(prompt, schema, *args, **kw)

        script = RefusedStrategy([BROKEN, BROKEN, GOOD], ['FAIL', 'FAIL', 'PASS'],
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
        script = Script([BROKEN, BROKEN, GOOD], ['FAIL', 'FAIL', 'PASS'], strategy='switch_provider')
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
        # 10-08: a recovery re-plan from VERIFYING rebuilt into the built v31 -> IntegrityError twice.
        script = HarnessScript([GOOD, GOOD], ['FAIL', 'PASS'])
        eng = self.engine(script)
        pid = self.store.new_project('make an add tool')
        built = eng.run(pid)['iteration']
        eng.replan(pid, 'operator re-plan')           # PAUSED(VERIFYING) -> REWORK, iteration unchanged
        p = eng.run(pid)
        self.assertEqual(p['state'], 'OWNER_REVIEW', p['pause_reason'])
        self.assertEqual([a['iteration'] for a in self.store.artifacts(pid)], [built, built + 1])

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
        path, _ = eng.launch_verified(pid, popen=popen)
        args, kwargs = popen.call_args
        self.assertEqual(args[0][-1], Path(verified['path']).name)       # the Owner's launch: no arguments
        self.assertEqual(args[0][:2], ['cmd', '/k'])                      # a CLI result stays on screen
        self.assertEqual(Path(kwargs['cwd']), self.tmp / 'ws' / 'projects' / pid / 'run' / f"v{verified['iteration']}")
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
        eng = self.engine(HarnessScript([GOOD, GOOD], ['FAIL', 'PASS']))
        pid = self.store.new_project('make an add tool')
        eng.run(pid)                                   # v1 built, HARNESS_BLOCKED
        v1 = self.store.artifacts(pid)[0]
        eng.replan(pid, 'operator re-plan')            # rebuild -> v2
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
