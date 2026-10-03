"""End-to-end engine behaviour with a scripted provider (no subscription usage)."""
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


class Script:
    """Answers by schema. `builds` and `verdicts` are consumed in order."""

    def __init__(self, builds, verdicts, strategy='continue', fail_on=None):
        self.builds, self.verdicts, self.strategy = list(builds), list(verdicts), strategy
        self.fail_on, self.prompts = fail_on, []

    def __call__(self, prompt, schema, prefer='claude', web=False, cancel=None):
        self.prompts.append((schema, prefer, prompt))
        if self.fail_on is schema:
            self.fail_on = None
            raise providers.RateLimited('usage limit (scripted)')
        if schema is E.PLAN:
            return {'interpretation': 'Build an add() helper', 'artifact_kind': 'python',
                    'artifact_filename': '../evil/add tool.py', 'acceptance_criteria': ['add(2,3)==5'],
                    'verification_lenses': ['software engineering'], 'required_tools': [],
                    'pipeline': [{'name': 'design', 'agent_role': 'Architect', 'instructions': 'design',
                                  'provider': 'codex', 'web': False},
                                 {'name': 'build', 'agent_role': 'Developer', 'instructions': 'build',
                                  'provider': 'claude', 'web': False}]}, 'claude', []
        if schema is E.WORK:
            return {'output': 'use +', 'key_points': ['use +']}, prefer, []
        if schema is E.BUILD:
            return {'content': self.builds.pop(0), 'summary': 's', 'changes_from_previous': ''}, prefer, []
        if schema is E.VERDICT:
            v = self.verdicts.pop(0)
            return {'verdict': v, 'lenses_applied': ['se'], 'criteria': [{'criterion': 'add', 'met': v == 'PASS', 'evidence': 'e'}],
                    'findings': [] if v == 'PASS' else [{'severity': 'major', 'issue': 'wrong sum', 'evidence': 'a - b'}]}, prefer, []
        if schema is E.STRATEGY:
            return {'decision': self.strategy, 'rationale': 'r', 'pipeline': []}, 'claude', []
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
        self.assertEqual(p['state'], 'PENDING_CLOSE')
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
            self.assertEqual(eng2.run(pid)['state'], 'PENDING_CLOSE')
        finally:
            store2.close()
        self.assertEqual(sum(s is E.PLAN for s, _, _ in script.prompts), 1)   # no re-planning

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
            self.assertEqual(eng2.run(pid)['state'], 'PENDING_CLOSE')
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

    def test_self_test_gets_empty_stdin_and_no_args(self):
        path = self.tmp / 'reads_stdin.py'
        path.write_text("import sys\nif __name__ == '__main__':\n    assert sys.argv[1:] == []\n"
                        "    assert sys.stdin.read() == ''\n", encoding='utf-8')
        self.assertTrue(self.engine(Script([], [])).checks(path, 'python')['ok'])

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
