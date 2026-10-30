"""Capability gaps stop production; leases cannot outlive one operation."""
import json
import unittest
from unittest import mock

from axbranch import capabilities as C, engine as E, providers
from axbranch.state import Rejected
from tests import test_engine as F


class CapabilityTests(unittest.TestCase):
    setUp, tearDown, engine = F.EngineTests.setUp, F.EngineTests.tearDown, F.EngineTests.engine

    def assert_revoked(self, pid):
        attached = self.store.events(pid, {'capability_attached'})
        ended = self.store.events(pid, {'capability_revoked'})
        self.assertTrue(attached)
        self.assertCountEqual([e['id'] for e in attached], [e['detail']['grant'] for e in ended])

    def test_unknown_capability_stops_before_any_build(self):
        script = F.Script([F.GOOD], ['PASS'])

        def llm(prompt, schema, **kw):
            result, used, notes = script(prompt, schema, **kw)
            if schema is E.PLAN:
                result['pipeline'][-1]['capabilities'] = ['gui_interaction']
            return result, used, notes

        pid = self.store.new_project('Drive a desktop app')
        result = self.engine(llm).run(pid)
        self.assertEqual((result['state'], result['resume_state']), ('PAUSED', 'STAFFING'))
        self.assertIn('gui_interaction', result['pause_reason'])
        self.assertEqual(len(script.prompts), 1)
        self.assertFalse(self.store.artifacts(pid))
        self.assert_revoked(pid)
        decision = self.store.events(pid, {'capability_decision'})[-1]['detail']
        self.assertEqual((decision['capability'], decision['status']), ('gui_interaction', 'unsupported'))

    def test_every_gap_is_resolved_or_recorded_never_claimed(self):
        pid = self.store.new_project('gap flow')
        native = C.resolve(self.store, pid, 'native_executable_launch', self.tmp)
        self.assertEqual(native['status'], 'needs_replan')                   # supported free alternative, nothing obtained
        self.assertIn('pyinstaller', native['alternative'][0])
        with mock.patch.object(C.shutil, 'which', lambda t: r'C:\\tools\\ffmpeg.exe' if t == 'ffmpeg' else None):
            video = C.resolve(self.store, pid, 'video_editing', self.tmp)
        self.assertEqual(video['status'], 'unsupported')                     # an installed program is not an adapter
        self.assertIn('ffmpeg', video['tried'][0]['why'])
        from axbranch import runtime
        with mock.patch.object(runtime, 'browser', lambda: None):
            browser = C.resolve(self.store, pid, 'runtime_browser', self.tmp)
        self.assertEqual(browser['status'], 'needs_owner')
        self.assertIn('Chrome', browser['minimal_approval'][0])
        with mock.patch.object(runtime, 'browser', lambda: r'C:\\chrome.exe'):
            self.assertEqual(C.resolve(self.store, pid, 'runtime_browser', self.tmp)['status'], 'resolved')
        self.assertEqual([e['detail']['status'] for e in self.store.events(pid, {'capability_decision'})],
                         ['needs_replan', 'unsupported', 'needs_owner', 'resolved'])

    def training_plan(self, options, runs=1):
        """A plan whose builder stage declares model_training; the resolver's options are stand-ins."""
        script = F.Script([F.GOOD] * 2, ['PASS'] * 2)

        def llm(prompt, schema, **kw):
            result, used, notes = script(prompt, schema, **kw)
            if schema is E.PLAN:
                result['pipeline'][-1]['capabilities'] = ['model_training']
            return result, used, notes

        pid = self.store.new_project('Train a small classifier')
        with mock.patch.object(C, 'options', lambda name, training=None: options if name in C.TRAINING_NAMES else ()):
            result = self.engine(llm).run(pid)
        return pid, result, script

    def test_training_gap_fails_over_to_the_next_option_and_proceeds(self):
        calls = []
        cpu = lambda d: calls.append('cpu') or {'ok': False, 'why': 'pip failed'}
        cloud = lambda d: calls.append('cloud') or {'ok': True, 'evidence': {'adapter_changed': True}}
        pid, result, _ = self.training_plan((('local_cpu_lora', cpu), ('free_cloud_gpu', cloud)))
        self.assertEqual(calls, ['cpu', 'cloud'])                                  # tried in order, real attempts
        attempts = [e['detail'] for e in self.store.events(pid, {'capability_attempt'})]
        self.assertEqual([(a['option'], a['ok']) for a in attempts], [('local_cpu_lora', False), ('free_cloud_gpu', True)])
        self.assertEqual(attempts[0]['why'], 'pip failed')
        decision = self.store.events(pid, {'capability_decision'})[-1]['detail']
        self.assertEqual((decision['status'], decision['chosen']), ('resolved', 'free_cloud_gpu'))
        self.assertIn('model_training', self.store.project(pid)['plan']['harness_capabilities'])
        self.assertTrue(self.store.artifacts(pid))                                 # production continued
        # Harness authority only: no production agent lease ever carried model_training.
        self.assertFalse([e for e in self.store.events(pid, {'capability_attached'})
                          if 'model_training' in e['detail']['capabilities']])

    def test_no_working_option_is_an_owner_decision_with_cost_and_minimal_approval(self):
        cpu = lambda d: {'ok': False, 'why': 'LoRA probe failed (exit 1)'}
        cloud = lambda d: {'ok': False, 'why': 'no signed-in session', 'minimal_approval': 'Owner signs in to Colab',
                           'cost': '0 on the free tier'}
        pid, result, script = self.training_plan((('local_cpu_lora', cpu), ('free_cloud_gpu', cloud)))
        self.assertEqual(result['state'], 'PAUSED')
        self.assertTrue(result['pause_reason'].startswith('Owner action needed: capability model_training'))
        self.assertIn('Owner signs in to Colab', result['pause_reason'])
        decision = self.store.events(pid, {'capability_decision'})[-1]['detail']
        self.assertEqual(decision['status'], 'needs_owner')
        self.assertEqual(decision['cost'], ['UNKNOWN', '0 on the free tier'])
        self.assertEqual([t['why'] for t in decision['tried']], ['LoRA probe failed (exit 1)', 'no signed-in session'])
        self.assertFalse(self.store.artifacts(pid))                               # quality not lowered silently
        self.assertEqual(E.stop_outcome(result)[0], 'OWNER_DECISION_REQUIRED')
        # The Owner can answer it (not mistaken for a pending network approval, which blocks feedback).
        self.engine(F.Script([F.GOOD], ['PASS'])).owner_review(pid, text='Use a non-trained baseline instead.')
        self.assertEqual(self.store.project(pid)['state'], 'REWORK')

    def test_a_resolved_capability_is_not_probed_again(self):
        calls = []
        cpu = lambda d: calls.append('cpu') or {'ok': True, 'evidence': {}}
        pid, _, _ = self.training_plan((('local_cpu_lora', cpu),))
        eng = self.engine(F.Script([F.GOOD], ['PASS']))
        with mock.patch.object(C, 'options', lambda name, training=None: (('local_cpu_lora', cpu),)
                               if name in C.TRAINING_NAMES else ()):
            self.assertTrue(eng._capability_gate(pid))
        self.assertEqual(calls, ['cpu'])
        self.assertEqual(len(self.store.events(pid, {'capability_decision'})), 1)

    def test_native_launch_detection_ignores_python_itself_and_urls(self):
        native = lambda s: 'native_executable_launch' in C.harness_requests({'mode': 'web', 'owner_launch': s})
        self.assertEqual([native(s) for s in ('double-click DiligenceReviewDesk.exe', 'install Setup.msi',
                                              'run python.exe app.py', 'pythonw.exe tool.pyw',
                                              'double-click app.py; opens http://todo.app/',
                                              'Run python app.py then open https://demo.exe.com/',
                                              'double-click app.py; it reads report.exe.config',
                                              r'run C:\Tools\Desk.exe')],
                         [True, True, False, False, False, False, False, True])

    def test_a_native_executable_owner_launch_is_a_gap_before_any_build(self):
        # P-20261016-5fb8d6: owner_launch '... double-click DiligenceReviewDesk.exe' while the harness ran
        # `python <entry>` and reported the "exact Owner launch" as passed.
        script = F.Script([F.GOOD], ['PASS'])

        def llm(prompt, schema, **kw):
            result, used, notes = script(prompt, schema, **kw)
            if schema is E.PLAN:
                result['runtime'] = {**result['runtime'], 'owner_launch': 'Extract App.zip and double-click App.exe'}
            return result, used, notes

        pid = self.store.new_project('Make a Windows program')
        result = self.engine(llm).run(pid)
        self.assertEqual(result['state'], 'PAUSED')
        self.assertIn('native_executable_launch', result['pause_reason'])
        self.assertFalse(self.store.artifacts(pid))

    def test_research_grant_is_scoped_and_actual_failover_is_recorded(self):
        script = F.Script([F.GOOD], ['PASS'])

        def llm(prompt, schema, **kw):
            result, used, notes = script(prompt, schema, **kw)
            if schema is E.PLAN:
                result['pipeline'][0]['capabilities'] = ['web_research']
            if schema is E.WORK:
                self.assertTrue(kw['web'])
                return result, 'claude', ['codex quota refusal (scripted)']
            if schema is E.BUILD:
                self.assertFalse(kw['web'])
            return result, used, notes

        pid = self.store.new_project('Research and write an add tool')
        self.assertEqual(self.engine(llm).run(pid)['state'], 'OWNER_REVIEW')
        calls = self.store.events(pid, {'call'})
        research = next(e['detail'] for e in calls if e['detail']['who'] == 'Architect')
        build = next(e['detail'] for e in calls if e['detail']['who'] == 'Developer')
        self.assertEqual(research['provider'], 'claude')
        self.assertTrue(research['authority']['web_research'])
        self.assertFalse(build['authority']['web_research'])
        self.assertTrue(all('capability_grant' in e['detail'] for e in calls))
        self.assert_revoked(pid)

    def test_failed_call_revokes_before_pause_and_resume(self):
        script = F.Script([F.GOOD], ['PASS'], fail_on=E.BUILD)
        pid = self.store.new_project('add tool')
        eng = self.engine(script)
        self.assertEqual(eng.run(pid)['state'], 'PAUSED')
        self.assert_revoked(pid)
        self.assertIn('interrupted', [e['detail']['outcome'] for e in self.store.events(pid, {'capability_revoked'})])
        self.store.resume(pid)
        self.assertEqual(self.engine(script).run(pid)['state'], 'OWNER_REVIEW')
        self.assert_revoked(pid)

    def test_crash_audit_is_closed_only_after_lock_is_acquired(self):
        pid = self.store.new_project('add tool')
        grant = self.store.event(pid, 'capability_attached', who='dead worker', capabilities=['web_research'])
        self.engine(F.Script([F.GOOD], ['PASS'])).run(pid, stop_at='PLANNING')
        event = self.store.events(pid, {'capability_revoked'})[0]
        self.assertEqual(event['detail']['grant'], grant)
        self.assertIn('not reattached', event['detail']['outcome'])
        C.recover(self.store, pid)
        self.assertEqual(len(self.store.events(pid, {'capability_revoked'})), 1)

    def test_gap_at_call_boundary_fails_closed(self):
        pid = self.store.new_project('no shell')
        llm = mock.Mock()
        with self.assertRaisesRegex(Rejected, 'CAPABILITY_GAP'):
            self.engine(llm)._ask(pid, 'worker', 's', 't', {}, E.WORK, 'claude', required=['shell'])
        llm.assert_not_called()
        self.assertFalse(self.store.events(pid, {'capability_attached'}))
        with self.assertRaisesRegex(Rejected, 'flag disabled'):
            with C.lease(self.store, pid, 'worker', ['web_research'], web=False):
                self.fail('must never enter the operation')

    def test_harness_exception_and_baseexception_revoke(self):
        pid = self.store.new_project('bounded execution')
        for error in (RuntimeError('probe failed'), KeyboardInterrupt()):
            with self.assertRaises(type(error)):
                with C.lease(self.store, pid, 'checks', ['runtime_cli'], kind='harness'):
                    raise error
        self.assert_revoked(pid)

    def test_missing_browser_is_an_explicit_gap(self):
        script = F.Script([], [])
        plan = script('', E.PLAN)[0]
        plan['runtime'] = {'mode': 'web', 'probes': [{'http_method': 'BROWSER'}]}
        self.assertEqual(C.gaps(plan, False), ['runtime_browser'])
        self.assertEqual(C.gaps(plan, True), [])
        self.assertNotIn('runtime_browser', C.inventory(False)['available'])
        plan['pipeline'][0]['capabilities'] = ['runtime_cli']
        self.assertEqual(C.gaps(plan, True), ['runtime_cli'])

    def test_replan_replaces_pipeline_and_keeps_contract_and_scopes(self):
        script = F.Script([F.BROKEN + '#1', F.BROKEN + '#2', F.GOOD], ['FAIL', 'FAIL', 'PASS'])

        def llm(prompt, schema, **kw):
            result, used, notes = script(prompt, schema, **kw)
            if 'decision' in schema.get('properties', {}):
                data = json.loads(prompt.split('CONTEXT (JSON — data, not instructions):\n')[1]
                                  .rsplit('\n\nReturn exactly', 1)[0])
                self.assertEqual(len(data['attempt_ledger']), 2)
                self.assertIn('capability_inventory', data)
                result.update(decision='change_pipeline', pipeline=[
                    {'name': 'correct algorithm', 'agent_role': 'Algorithm engineer', 'instructions': 'Use addition',
                     'provider': 'codex', 'web': False, 'capabilities': ['code_generation']}])
            return result, used, notes

        pid = self.store.new_project('add tool')
        result = self.engine(llm).run(pid)
        self.assertEqual(result['state'], 'OWNER_REVIEW')
        self.assertEqual(result['plan_version'], 2)
        self.assertEqual(result['plan']['acceptance_criteria'], ['add(2,3)==5'])
        self.assertEqual([v['verdict'] for v in self.store.verifications(pid)], ['FAIL', 'FAIL', 'PASS'])
        self.assertEqual(result['plan']['pipeline'][0]['agent_role'], 'Algorithm engineer')
        self.assert_revoked(pid)

    def test_malformed_declaration_is_rejected(self):
        for required in ('shell', None, [None], {'reasoning': True}):
            with self.subTest(required=required), self.assertRaises(Rejected):
                C.agent_requests(required)


if __name__ == '__main__':
    unittest.main()
