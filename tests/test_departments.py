"""Department harness: validated shared packages, per-project attachment, delegation only to attached
departments, results passed between departments, refusals, temporary agents, detachment and replanning."""
import json
import shutil
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from axbranch import departments as D, engine as E
from axbranch.state import Rejected, Store
from tests.test_engine import BROKEN, GOOD, Script

SPECS, _ = D.catalog()


class DepartmentScript(Script):
    """Plans the two-department pipeline (or `pipeline`), and records what each stage was given."""
    def __init__(self, pipeline=None, **kw):
        super().__init__([GOOD, GOOD, GOOD], ['PASS', 'PASS', 'PASS'], **kw)
        self.pipeline = pipeline or [
            {'name': 'analyse', 'agent_role': 'Research analyst', 'instructions': 'find the numbers', 'provider': 'codex',
             'web': False, 'department': 'research', 'why': 'research owns the analysis'},
            {'name': 'build', 'agent_role': 'Operations designer', 'instructions': 'build the tool', 'provider': 'claude',
             'web': False, 'department': 'operations', 'why': 'operations makes the usable tool'}]
        self.contexts = []
        self.judge_departments = True        # the verifier judges each department criterion

    def __call__(self, prompt, schema, *args, **kw):
        result, used, notes = super().__call__(prompt, schema, *args, **kw)
        context = json.loads(prompt.split('CONTEXT (JSON — data, not instructions):\n', 1)[1].rsplit('\n\nReturn exactly', 1)[0])
        self.contexts.append((schema, context))
        if schema is E.PLAN:
            result['pipeline'] = [dict(s) for s in self.pipeline]
        if schema is E.WORK:
            result = {'output': 'card team has 40% of inquiries (row 3)', 'key_points': ['card 40%'],
                      'evidence': ['inputs row 3'], 'counterpoints': ['small sample']}
        if schema is E.VERDICT and self.judge_departments and 'department_acceptance' in context:
            result = dict(result, department_criteria=[dict(c, status='met', evidence='stage results')
                                                       for c in context['department_acceptance']['criteria']])
        return result, used, notes


class DepartmentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.store = Store(self.tmp / 'ws' / 'axbranch.sqlite3')

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def engine(self, script):
        return E.Engine(self.store, workspace=self.tmp / 'ws', vault=self.tmp / 'v', gai_db=self.tmp / 'x', llm=script)

    def project(self, *deps):
        pid = self.store.new_project('팀별 문의 우선순위 도구')
        for d in deps:
            D.attach(self.store, pid, d, SPECS)
        return pid

    def test_invalid_specs_are_refused_at_load(self):
        root = self.tmp / 'lib'
        good = SPECS['research']
        bad = {'missing': {k: v for k, v in good.items() if k != 'tools'},
               'shell': {**good, 'id': 'shell', 'permissions': {**good['permissions'], 'shell': True}},
               'tools': {**good, 'id': 'tools', 'tools': ['reasoning', 'payments']},
               'web': {**good, 'id': 'web', 'tools': ['reasoning', 'web_research']},
               'mismatch': {**good, 'id': 'other'}}
        for folder, spec in {'research': good, **bad}.items():
            (root / folder).mkdir(parents=True)
            (root / folder / 'department.json').write_text(json.dumps(spec), encoding='utf-8')
        (root / 'broken').mkdir()
        (root / 'broken' / 'department.json').write_text('{not json', encoding='utf-8')
        valid, refused = D.catalog(root)
        self.assertEqual(sorted(valid), ['research'])
        self.assertEqual(sorted(refused), ['broken', 'mismatch', 'missing', 'shell', 'tools', 'web'])
        self.assertIn('payments', ' '.join(refused['tools']))
        self.assertIn('shell', ' '.join(refused['shell']))
        self.assertEqual(sorted(SPECS), ['operations', 'research'])           # the shipped packages are valid

    def test_attach_is_persistent_per_project_without_duplicates(self):
        a, b = self.project('research'), self.project()
        with self.assertRaises(Rejected):
            D.attach(self.store, a, 'research', SPECS)                         # no duplicate connection
        with self.assertRaises(Rejected):
            D.attach(self.store, a, 'payments', SPECS)                         # not in the library
        D.attach(self.store, a, 'operations', SPECS)
        self.store.close()
        self.store = Store(self.tmp / 'ws' / 'axbranch.sqlite3')               # reopened: attachment restored
        self.assertEqual([d['id'] for d in D.attached(self.store, a)], ['research', 'operations'])
        self.assertEqual(D.attached(self.store, b), [])                        # never mixed between projects
        D.detach(self.store, a, 'research')
        self.assertEqual([d['id'] for d in D.attached(self.store, a)], ['operations'])
        with self.assertRaises(Rejected):
            D.detach(self.store, a, 'research')
        self.assertEqual(len(self.store.events(a, {'department_attached'})), 2)   # audit kept

    def test_ceo_delegates_to_attached_departments_and_results_flow_forward(self):
        script = DepartmentScript()
        pid = self.project('research', 'operations')
        p = self.engine(script).run(pid)
        self.assertEqual(p['state'], 'OWNER_REVIEW', p['pause_reason'])
        plan_ctx = next(c for s, c in script.contexts if s is E.PLAN)
        self.assertEqual([d['id'] for d in plan_ctx['attached_departments']], ['research', 'operations'])
        self.assertNotIn('standing_instructions', json.dumps(plan_ctx))        # summaries, not prompts
        work_ctx = next(c for s, c in script.contexts if s is E.WORK)
        self.assertEqual(work_ctx['department']['id'], 'research')             # only its own department
        build_ctx = next(c for s, c in script.contexts if s is E.BUILD)
        self.assertEqual(build_ctx['department']['id'], 'operations')
        self.assertEqual(build_ctx['previous_stages'][0]['output'], 'card team has 40% of inquiries (row 3)')
        self.assertNotIn('attached_departments', build_ctx)
        delegations = [e['detail'] for e in self.store.events(pid, {'department_delegation'})]
        self.assertEqual([(d['stage'], d['department']) for d in delegations], [('analyse', 'research'), ('build', 'operations')])
        result = self.store.events(pid, {'department_result'})[0]['detail']
        self.assertEqual((result['department'], result['evidence'], result['limits']), ('research', 1, ['small sample']))
        self.assertTrue(any(s is E.VERDICT for s, _ in script.contexts))       # independent verification kept

    def test_a_reused_department_result_is_shown_as_done_after_a_rework(self):
        # E2E P-20261024-5dd942: after a rework only operations rebuilt; research looked "not started" (○).
        from axbranch import live
        script = DepartmentScript()
        script.builds, script.verdicts = [BROKEN, GOOD, GOOD], ['FAIL', 'PASS', 'PASS']   # a real change after FAIL
        pid = self.project('research', 'operations')
        p = self.engine(script).run(pid)
        self.assertEqual(p['state'], 'OWNER_REVIEW', p['pause_reason'])
        self.assertEqual(sum(s is E.WORK for s, _ in script.contexts), 1)        # research ran once, then reused
        rows = {r['key']: r for r in live.view(self.tmp / 'ws', self.store, pid)['pipeline']}
        self.assertEqual((rows['stage:0']['mark'], rows['stage:0']['title']), ('✓', '[리서치] Research analyst'))
        self.assertIn('재사용', rows['stage:0']['detail'])

    def test_unattached_department_or_overreach_is_refused_before_any_work(self):
        cases = [(('research',), {}, 'not attached'),
                 (('research', 'operations'), {'capabilities': ['web_research'], 'web': True}, 'web'),
                 (('research', 'operations'), {'capabilities': ['code_generation']}, 'beyond')]
        for deps, change, word in cases:
            with self.subTest(word=word):
                pipeline = [dict(DepartmentScript().pipeline[0], **change), DepartmentScript().pipeline[1]]
                script = DepartmentScript(pipeline)
                pid = self.project(*deps)
                p = self.engine(script).run(pid)
                self.assertEqual(p['state'], 'PAUSED')
                self.assertIn('delegation refused', p['pause_reason'])
                self.assertIn(word, self.store.events(pid, {'delegation_refused'})[-1]['detail']['reason'])
                self.assertFalse(any(s in (E.WORK, E.BUILD) for s, _ in script.contexts))
                self.assertFalse(self.store.artifacts(pid))

    def test_no_fitting_department_is_a_recorded_temporary_agent(self):
        pipeline = [dict(DepartmentScript().pipeline[0]),
                    dict(DepartmentScript().pipeline[1], department='', agent_role='Interim builder',
                         why='no attached department builds tools')]
        pid = self.project('research')
        p = self.engine(DepartmentScript(pipeline)).run(pid)
        self.assertEqual(p['state'], 'OWNER_REVIEW', p['pause_reason'])
        temp = self.store.events(pid, {'temporary_agent'})[0]['detail']
        self.assertEqual((temp['stage'], temp['why'], temp['attached']), ('build', 'no attached department builds tools', ['research']))

    def test_temporary_agent_cannot_bypass_attachment_tools_or_network(self):
        # Only research (reasoning, no network) attached: a temporary agent may not take operations' role,
        # declare tools no attached department grants, or research the web.
        cases = [({'agent_role': 'Operations designer'}, "'operations'"),
                 ({'capabilities': ['code_generation']}, 'no attached department provides'),
                 ({'capabilities': ['web_research'], 'web': True}, 'web')]
        for change, word in cases:
            with self.subTest(word=word):
                first = dict(DepartmentScript().pipeline[0], department='', **{'agent_role': 'Interim analyst', **change})
                script = DepartmentScript([first, dict(DepartmentScript().pipeline[1], department='')])
                pid = self.project('research')
                p = self.engine(script).run(pid)
                self.assertEqual(p['state'], 'PAUSED')
                self.assertIn(word, self.store.events(pid, {'delegation_refused'})[-1]['detail']['reason'])
                self.assertFalse(any(s in (E.WORK, E.BUILD) for s, _ in script.contexts))
                self.assertFalse(self.store.events(pid, {'temporary_agent'}))
        # Allowed: the final stage keeps the engine's build contract; the record names its tools.
        last = dict(DepartmentScript().pipeline[1], department='', agent_role='Interim builder',
                    capabilities=['code_generation'])
        pid = self.project('research')
        p = self.engine(DepartmentScript([DepartmentScript().pipeline[0], last])).run(pid)
        self.assertEqual(p['state'], 'OWNER_REVIEW', p['pause_reason'])
        temp = self.store.events(pid, {'temporary_agent'})[0]['detail']
        self.assertEqual((temp['tools'], temp['web']), (['code_generation', 'reasoning'], False))
        # Nothing attached: the pre-department rules apply unchanged (no department policy).
        self.assertIsNone(D.check_stage({'name': 'x', 'agent_role': 'Operations designer', 'web': True,
                                         'capabilities': ['web_research']}, {}, SPECS))

    def test_detached_department_gets_no_new_work_and_replanning_resumes(self):
        pid = self.project('research', 'operations')
        eng = self.engine(DepartmentScript())
        eng.run(pid, stop_at='EXECUTING')                                       # planned and staffed
        D.detach(self.store, pid, 'operations')
        p = eng.run(pid)
        self.assertEqual(p['state'], 'PAUSED')
        self.assertIn('not attached', p['pause_reason'] + str(self.store.events(pid, {'delegation_refused'})))
        self.assertFalse(self.store.artifacts(pid))
        self.assertEqual(len(self.store.events(pid, {'department_attached'})), 2)   # history kept
        # The Owner answers; 淸月 re-plans with what is attached (bounded by the usual round budget).
        replan = DepartmentScript([dict(DepartmentScript().pipeline[0]),
                                   dict(DepartmentScript().pipeline[1], department='', why='operations was removed')])
        eng = self.engine(replan)
        eng.owner_review(pid, text='운영 부서를 뺐으니 남은 부서로 다시 계획해 줘')
        p = eng.run(pid)
        self.assertNotIn('delegation refused', p['pause_reason'] or '')
        self.assertTrue(self.store.events(pid, {'temporary_agent'}))


    def test_cli_attaches_refuses_duplicates_and_detaches(self):
        # The packaged exe's mouse-free path (axbranch department <id> list|attach|detach): same rules as the window.
        import contextlib, io
        from unittest import mock
        from axbranch import __main__ as cli
        pid = self.project()
        def run(*args):
            out = io.StringIO()
            with mock.patch.object(cli, 'open_engine', lambda **kw: self.engine(DepartmentScript())),                     contextlib.redirect_stdout(out):
                return cli.main(['department', pid, *args]), out.getvalue().strip()
        self.assertEqual(run('attach', 'research'), (None, 'research'))
        code, text = run('attach', 'research')
        self.assertEqual(code, 1)
        self.assertIn('이미 연결된 부서', text)
        self.assertEqual(run('attach', 'operations')[1], 'research, operations')
        self.assertEqual(run('detach', 'research')[1], 'operations')
        self.assertEqual(run('list')[1], 'operations')
        self.assertEqual(len(self.store.events(pid, {'department_attached'})), 2)

    def test_contract_failure_is_not_handed_on_and_gets_one_bounded_rework(self):
        bad = {'output': '', 'key_points': [], 'evidence': [], 'counterpoints': []}
        good = {'output': 'card team has 40% of inquiries (row 3)', 'key_points': ['card 40%'],
                'evidence': ['inputs row 3'], 'counterpoints': []}
        for replies, final_state in (([bad, good], 'OWNER_REVIEW'), ([bad, bad, good], 'PAUSED')):
            with self.subTest(replies=len(replies)):
                script = DepartmentScript()
                queue = list(replies)
                original = DepartmentScript.__call__

                def call(prompt, schema, *a, _q=queue, **kw):
                    result, used, notes = original(script, prompt, schema, *a, **kw)
                    return (dict(_q.pop(0)) if schema is E.WORK else result), used, notes
                script.__call__ = call
                pid = self.project('research', 'operations')
                p = self.engine(call).run(pid)
                self.assertEqual(p['state'], final_state, p['pause_reason'])
                checks = [e['detail'] for e in self.store.events(pid, {'department_contract'})]
                self.assertEqual(checks[0]['status'], 'fail')
                self.assertIn('결과(output)가 비어 있음', checks[0]['problems'])
                works = [c for s_, c in script.contexts if s_ is E.WORK]
                self.assertIn('contract_feedback', works[1])                       # the problems go back to it
                builds = [c for s_, c in script.contexts if s_ is E.BUILD]
                if final_state == 'PAUSED':
                    self.assertEqual(len(works), 2)                                 # bounded: no third attempt
                    self.assertEqual(builds, [])                                    # nothing handed on
                    self.assertIn('department contract failed', p['pause_reason'])
                    self.engine(call).run(pid)                                      # a resume does not retry it
                    self.assertEqual(len([c for s_, c in script.contexts if s_ is E.WORK]), 2)
                else:
                    self.assertEqual(checks[-1]['status'], 'format_ok')
                    self.assertIn('independent verification', checks[-1]['note'])
                    self.assertEqual(builds[0]['previous_stages'][0]['output'], good['output'])

    def test_contract_checks_foreign_references_inputs_and_legacy_specs(self):
        spec = SPECS['research']
        self.assertIn("다른 프로젝트 참조: ['P-20990101-abcdef']",
                      D.check_output(spec, {'output': 'see P-20990101-abcdef for the numbers', 'key_points': ['k'],
                                            'evidence': ['e']}, 'P-20261024-000000'))
        self.assertEqual(D.check_output(spec, {'output': 'own project P-20261024-000000 row 3 says 40%',
                                               'key_points': ['k'], 'evidence': ['e']}, 'P-20261024-000000'), [])
        self.assertEqual(D.check_output(spec, {'output': 'row 3 of the input: P-20990101-abcdef FAIL', 'key_points': ['k'],
                                               'evidence': ['e']}, 'P-20261024-000000', {'P-20990101-abcdef'}), [])
        self.assertIn('근거 부족 (0개 < 1개)', D.check_output(spec, {'output': 'x' * 30, 'key_points': ['k'], 'evidence': []}, 'P'))
        needs = dict(spec, contract={'version': 1, 'output': {}, 'input': {'require': ['owner_inputs']}})
        self.assertEqual(D.check_input(needs, False, True), ['필수 입력 없음: owner_inputs'])
        legacy = {k: v for k, v in spec.items() if k != 'contract'}
        self.assertEqual(D.validate(legacy, 'research'), [])                            # old specs still load
        self.assertEqual(D.check_output(legacy, {'output': 'short'}, 'P'), [])           # universal checks only
        self.assertTrue(D.validate(dict(spec, contract={'version': 1, 'output': {'require': ['nope']}}), 'research'))
        pid = self.project('research', 'operations')                                     # a failing input check
        with unittest.mock.patch.dict(SPECS['research'], contract=needs['contract']):
            with unittest.mock.patch.object(D, 'catalog', return_value=(SPECS, {})):
                p = self.engine(DepartmentScript()).run(pid)
        self.assertEqual(p['state'], 'PAUSED')
        self.assertIn('필수 입력 없음: owner_inputs', p['pause_reason'])

    def test_reused_results_are_recorded_with_a_reason(self):
        script = DepartmentScript()
        script.builds, script.verdicts = [BROKEN, GOOD, GOOD], ['FAIL', 'PASS', 'PASS']
        pid = self.project('research', 'operations')
        self.engine(script).run(pid)
        reused = [e['detail'] for e in self.store.events(pid, {'stage_reused'})]
        self.assertTrue(reused and reused[0]['stage'] == 'analyse' and 'contract' in reused[0]['why'])

    def test_department_acceptance_is_judged_separately_and_never_passes_unmet(self):
        crit = SPECS['research']['acceptance_criteria'] + SPECS['operations']['acceptance_criteria']
        for label, judged, final in (('all met', 'met', 'OWNER_REVIEW'), ('missing', None, None),
                                     ('unmet', 'unmet', None), ('conflict', 'conflict', None)):
            with self.subTest(label):
                script = DepartmentScript()
                script.judge_departments = False
                original = DepartmentScript.__call__

                def call(prompt, schema, *a, _j=judged, **kw):
                    result, used, notes = original(script, prompt, schema, *a, **kw)
                    if schema is E.VERDICT and _j:
                        ctx = script.contexts[-1][1]
                        result = dict(result, department_criteria=[
                            dict(c, status=_j, evidence='artifact section 2') for c in ctx['department_acceptance']['criteria']])
                    return result, used, notes
                pid = self.project('research', 'operations')
                p = self.engine(call).run(pid)
                ctx = next(c for s_, c in script.contexts if s_ is E.VERDICT)
                self.assertEqual(len(ctx['department_acceptance']['criteria']), len(crit))   # sent to the verifier
                first = self.store.verifications(pid)[0]
                acc = self.store.events(pid, {'department_acceptance'})[0]['detail']['results']
                if final:
                    self.assertEqual((first['verdict'], p['state']), ('PASS', final))
                    self.assertTrue(all(a['status'] == 'met' for a in acc))
                else:
                    self.assertEqual(first['verdict'], 'FAIL')                       # a verifier PASS is not enough
                    self.assertIn('Department acceptance', ' '.join(f['issue'] for f in first['result']['findings']))
                    self.assertEqual({a['status'] for a in acc}, {judged or 'unverifiable'})
                if judged == 'conflict':
                    self.assertTrue(self.store.events(pid, {'criteria_conflict'}))
                    self.assertIn('re-plan', self.store.events(pid, {'criteria_conflict'})[0]['detail']['decision'])

    def test_replan_reuses_unchanged_stages_and_reruns_dependents_with_reasons(self):
        three = [dict(DepartmentScript().pipeline[0]),
                 dict(DepartmentScript().pipeline[0], name='summarise', instructions='summarise the numbers'),
                 dict(DepartmentScript().pipeline[1])]
        for label, change, owner_rework, ran, reused, discarded in (
                ('second changed', {1: 'summarise differently'}, None, ['summarise'], ['analyse'], ['summarise']),
                ('first changed', {0: 'find other numbers'}, None, ['analyse', 'summarise'], [], ['analyse', 'summarise']),
                ('owner feedback', {}, '더 짧게', ['analyse', 'summarise'], [], ['analyse', 'summarise'])):
            with self.subTest(label):
                script = DepartmentScript([dict(x) for x in three])
                pid = self.project('research', 'operations')
                eng = self.engine(script)
                self.assertEqual(eng.run(pid)['state'], 'OWNER_REVIEW')
                p = self.store.project(pid)
                plan = dict(p['plan'], pipeline=[dict(st) for st in p['plan']['pipeline']])
                for i, text in change.items():
                    plan['pipeline'][i]['instructions'] = text
                if owner_rework:
                    plan['owner_rework'] = owner_rework
                self.store.update(pid, plan=plan, plan_version=p['plan_version'] + 1)
                for state in ('REWORK', 'STAFFING'):
                    self.store.set_state(pid, state)
                before = len(script.contexts)
                self.engine(script).run(pid)
                works = [c['stage'] for s_, c in script.contexts[before:] if s_ is E.WORK]
                self.assertEqual(works, ran)
                pv = p['plan_version'] + 1
                rs = [e['detail'] for e in self.store.events(pid, {'stage_reused'}) if e['detail'].get('from_plan_version')]
                ds = [e['detail'] for e in self.store.events(pid, {'stage_discarded'})]
                self.assertEqual([r['stage'] for r in rs if r['plan_version'] == pv], reused)
                self.assertEqual([d['stage'] for d in ds if d['plan_version'] == pv], discarded)
                whys = {d['stage']: d['why'] for d in ds if d['plan_version'] == pv}
                if label == 'first changed':
                    self.assertIn('definition changed', whys['analyse'])
                    self.assertIn('earlier stage re-ran', whys['summarise'])          # dependents re-run
                if label == 'owner feedback':
                    self.assertIn('Owner feedback', whys['analyse'])

    def test_ids_that_are_values_in_the_projects_own_input_are_not_foreign(self):
        # E2E P-20261025-1d2aec: the research result cited project ids from the attached CSV's project column.
        data = self.tmp / 'history.csv'
        data.write_text('project,verdict\nP-20990101-abcdef,FAIL\n', encoding='utf-8')
        script = DepartmentScript()
        original = DepartmentScript.__call__

        def call(prompt, schema, *a, **kw):
            result, used, notes = original(script, prompt, schema, *a, **kw)
            if schema is E.WORK:
                result = dict(result, output='P-20990101-abcdef failed once (input row 2), 1 of 1 rows')
            return result, used, notes
        pid = self.project('research', 'operations')
        eng = self.engine(call)
        eng.attach_inputs(pid, [str(data)])
        p = eng.run(pid)
        self.assertEqual(p['state'], 'OWNER_REVIEW', p['pause_reason'])
        self.assertEqual(self.store.events(pid, {'department_contract'})[0]['detail']['status'], 'format_ok')

if __name__ == '__main__':
    unittest.main()
