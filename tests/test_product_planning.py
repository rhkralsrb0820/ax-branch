"""Isolated, scripted tests only. These documents are fixtures, never autonomous-run evidence."""
import copy
import json
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from axbranch import artifacts, departments as D, engine as E, knowledge, kindex
from axbranch.state import Rejected, Store
from tests.test_departments import DepartmentScript


def document():
    plan = {'scenarios': [dict(name=name, price=100, unit_cost=40, quantity=10, fixed_cost=120,
                              revenue=1000, profit=480, break_even_units=2) for name in ('downside', 'base', 'upside')],
            'claims': [{'statement': 'Fixture assumption only', 'status': 'ESTIMATED', 'evidence': ['synthetic.csv row 1']}],
            'mvp': ['one local report'], 'excluded': ['customer contact'],
            'experiments': [{'metric': 'verified evidence count', 'threshold': '>=1', 'method': 'inspect input references'}],
            'market_validation': {'willingness_to_pay': 'UNKNOWN', 'revenue': 'UNKNOWN'}}
    headings = D.catalog()[0]['product-planning']['contract']['document_sections']
    return '\n'.join(f'## {h}\nScripted test fixture; not market evidence.' for h in headings) + '\n```json\n' + json.dumps({'product_plan': plan}) + '\n```'


class ProductPlanningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='axb-product-test-'))
        self.store = Store(self.tmp / 'ws' / 'axbranch.sqlite3')
        self.specs = D.catalog()[0]

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_arithmetic_and_unverified_commercial_claims_are_enforced(self):
        spec, text = self.specs['product-planning'], document()
        self.assertEqual(D.check_document(spec, text), [])
        for changed in (text.replace('"profit": 480', '"profit": 999'),
                        text.replace('"break_even_units": 2', '"break_even_units": 3'),
                        text.replace('"willingness_to_pay": "UNKNOWN"', '"willingness_to_pay": "VERIFIED"'),
                        text.replace('"quantity": 10', '"quantity": true'),
                        text.replace('"status": "ESTIMATED"', '"status": "VERIFIED"').replace('["synthetic.csv row 1"]', '[]'),
                        text.replace('## MVP와 제외', '## omitted')):
            with self.subTest(changed=changed[-100:]):
                self.assertTrue(D.check_document(spec, changed))

    def test_malformed_scenario_names_are_rejected_without_crashing(self):
        for name in ([], {}, None, 12):
            with self.subTest(name=name):
                text = document().replace('"name": "base"', '"name": ' + json.dumps(name))
                self.assertTrue(D.check_document(self.specs['product-planning'], text))

    def test_attached_snapshot_does_not_silently_upgrade(self):
        pid = self.store.new_project('product planning cost scenario')
        D.attach(self.store, pid, 'product-planning', self.specs)
        changed = copy.deepcopy(self.specs)
        changed['product-planning']['version'] = '2.0.0'
        changed['product-planning']['permissions']['network'] = True
        pinned = D.resolve(self.store, pid, changed)['product-planning']
        self.assertEqual(pinned['version'], self.specs['product-planning']['version'])
        self.assertFalse(pinned['permissions']['network'])
        legacy = self.store.new_project('legacy')
        self.store.event(legacy, 'department_attached', department='product-planning', version='0.1.0')
        with self.assertRaises(Rejected):
            D.resolve(self.store, legacy, self.specs)

    def test_temporary_agent_cannot_union_department_privileges(self):
        specs = {'a': {'tools': ['web_research'], 'permissions': {'network': True}},
                 'b': {'tools': ['code_generation'], 'permissions': {'network': False}}}
        stage = dict(name='mixed', department='', capabilities=['web_research', 'code_generation'], web=True)
        self.assertIn('combines', D.check_stage(stage, specs))

    def test_scripted_engine_delegates_checks_verifies_and_records(self):
        class ProductScript(DepartmentScript):
            def __call__(script, prompt, schema, **kw):
                result, used, notes = super().__call__(prompt, schema, **kw)
                if schema is E.PLAN:
                    result.update(artifact_kind='markdown', artifact_filename='plan.md')
                return result, used, notes
        stages = [dict(name='research', agent_role='Research analyst', instructions='Analyse supplied data only',
                       department='research', provider='codex', web=False, why='reuse supplied-data research'),
                  dict(name='plan', agent_role='Product planner', instructions='Decide from previous findings',
                       department='product-planning', provider='claude', web=False, why='planning owns the decision')]
        script = ProductScript(pipeline=stages)
        script.builds = [document()]
        pid = self.store.new_project('product planning cost scenario PRIVATE-DO-NOT-COPY')
        for dep in ('research', 'product-planning'):
            D.attach(self.store, pid, dep, self.specs)
        eng = E.Engine(self.store, workspace=self.tmp / 'ws', vault=self.tmp / 'vault', gai_db=self.tmp / 'none', llm=script)
        result = eng.run(pid)
        self.assertEqual(result['state'], 'OWNER_REVIEW', result.get('pause_reason'))
        self.assertTrue(self.store.events(pid, {'department_document_contract'}))
        self.assertEqual(self.store.verifications(pid)[-1]['verdict'], 'PASS')
        records = self.store.events(pid, {'department_experience'})
        self.assertTrue(records)
        self.assertNotIn('PRIVATE-DO-NOT-COPY', json.dumps(records))
        self.assertTrue(all(e['detail']['improvement'] == 'UNKNOWN' for e in records))
        self.assertEqual(knowledge.department_experience(self.store, 'product planning cost scenario', 'other',
                         [{'id': 'product-planning', 'version': self.specs['product-planning']['version']}]), [])  # scripted != subscription execution
        # The same required headings and JSON block reach planning, production and verification.
        want = D.document_contracts({'product-planning': self.specs['product-planning']})
        plan_ctx = next(c for s, c in script.contexts if s is E.PLAN)
        planned = {d['id']: d for d in plan_ctx['attached_departments']}
        self.assertEqual(planned['product-planning']['document_contract']['headings'], want[0]['headings'])
        self.assertNotIn('document_contract', planned['research'])
        for schema in (E.BUILD, E.VERDICT):
            ctx = next(c for s, c in script.contexts if s is schema)
            self.assertEqual(ctx['required_document']['contracts'], want, schema)
        self.assertTrue(all(h[3:] in document() for h in want[0]['headings']))   # what check_document enforces

    def test_preflight_refuses_a_non_document_plan_before_any_agent_call(self):
        class CodeScript(DepartmentScript):
            def __call__(script, prompt, schema, **kw):
                result, used, notes = super().__call__(prompt, schema, **kw)
                if schema is E.PLAN:
                    result.update(artifact_kind='python', artifact_filename='plan.py')
                return result, used, notes
        stages = [dict(name='plan', agent_role='Product planner', instructions='Decide', department='product-planning',
                       provider='claude', web=False, why='planning owns the decision')]
        script = CodeScript(pipeline=stages)
        pid = self.store.new_project('product planning cost scenario')
        D.attach(self.store, pid, 'product-planning', self.specs)
        eng = E.Engine(self.store, workspace=self.tmp / 'ws', vault=self.tmp / 'vault', gai_db=self.tmp / 'none', llm=script)
        result = eng.run(pid)
        self.assertEqual(result['state'], 'PAUSED')
        self.assertIn('markdown document', result['pause_reason'])
        self.assertFalse([s for s, _ in script.contexts if s in (E.WORK, E.BUILD, E.VERDICT)])
        self.assertEqual(D.preflight({'artifact_kind': 'markdown', 'pipeline': stages}, self.specs), [])
        self.assertEqual(D.preflight({'artifact_kind': 'python', 'pipeline': [dict(stages[0], department='research')]},
                                     self.specs), [])

    def test_source_criterion_is_conditional_in_1_0_1(self):
        spec = self.specs['product-planning']
        self.assertEqual(spec['version'], '1.0.1')
        self.assertIn('제공되지 않았으면 제공된 것이 없다고 명시한다', spec['acceptance_criteria'][-1])
        self.assertIn('## 고객과 문제', spec['agent']['instructions'])

    def source(self):
        pid = self.store.new_project('product planning cost scenario')
        D.attach(self.store, pid, 'product-planning', self.specs)
        self.store.event(pid, 'session', execution_mode='subscription_cli')  # synthetic metadata for filter unit tests
        self.store.event(pid, 'department_delegation', department='product-planning', version='1.0.0', iteration=1)
        path = self.tmp / 'fixture.md'
        path.write_bytes(document().encode('utf-8'))
        aid = self.store.add_artifact(pid, 1, path, artifacts.sha(path.read_bytes()), 'markdown', None)
        self.store.add_verification(pid, aid, 1, 'PASS', {'verdict': 'PASS', 'findings': []}, {'ok': True}, 'codex')
        knowledge.record_department_experience(self.store, pid)
        return pid

    def test_scoped_retrieval_is_bounded_and_has_no_evaluation_leakage(self):
        source = self.source()
        allowed = [{'id': 'product-planning', 'version': '1.0.0'}]
        args = (self.store, 'product planning cost scenario', 'requester', allowed)
        self.assertEqual(len(knowledge.department_experience(*args, source_projects=[source])), 1)
        self.assertEqual(knowledge.department_experience(*args, source_projects=[]), [])
        self.assertEqual(knowledge.department_experience(*args, before=1), [])
        self.assertEqual(knowledge.department_experience(*args, chars=1), [])
        self.assertEqual(knowledge.department_experience(*args, limit=0), [])
        self.assertEqual(knowledge.department_experience(self.store, 'product planning', 'x',
                         [{'id': 'product-planning', 'version': '1.0.0', 'spec_sha256': 'wrong'}]), [])
        self.assertEqual(knowledge.department_experience(self.store, 'product planning', 'x', []), [])
        self.assertEqual(knowledge.department_experience(self.store, 'unrelated gardening', 'x', allowed), [])
        self.assertEqual(knowledge.record_department_experience(self.store, source), [])
        self.store.update(source, closed_mode='discard')
        self.assertEqual(knowledge.department_experience(*args), [])

    def test_budget_scope_and_missing_usage_stop_further_calls(self):
        pid = self.store.new_project('bounded fixture')
        eng = E.Engine(self.store, workspace=self.tmp / 'ws')
        eng.configure_budget(pid, max_calls=1, max_seconds=60, max_prompt_chars=10, max_reported_tokens=20)
        self.assertFalse(eng._budget_guard(pid, 'short').is_set())
        with self.assertRaises(Rejected):
            eng._budget_guard(pid, 'too many characters')
        self.store.event(pid, 'call_start', who='fixture')
        with self.assertRaises(Rejected):
            eng._budget_guard(pid, 'short')
        with self.assertRaises(Rejected):
            eng.configure_budget(pid)
        with self.assertRaises(Rejected):
            eng.configure_experience(pid)
        self.assertIsNone(knowledge.reported_tokens([{'kind': 'call', 'detail': {'tokens': 'UNKNOWN'}}]))
        self.assertEqual(knowledge.reported_tokens([{'kind': 'call', 'detail': {'tokens': {
            'source': 'codex turn.completed', 'input_tokens': 10, 'cached_input_tokens': 5,
            'output_tokens': 4, 'reasoning_output_tokens': 2}}}]), 14)

    def test_restart_keeps_budget_and_never_duplicates_experience(self):
        # A stopped or reconnected project is resumed by a NEW engine process: limits and experience must come from
        # the stored events, not from memory of the first process.
        pid = self.store.new_project('restart fixture')
        D.attach(self.store, pid, 'research', self.specs)
        eng = E.Engine(self.store, workspace=self.tmp / 'ws')
        eng.configure_budget(pid, max_calls=2, max_seconds=600, max_prompt_chars=1000, max_reported_tokens=500)
        self.store.event(pid, 'call_start', who='fixture')
        self.store.event(pid, 'call', who='fixture', tokens={'source': 'fixture', 'input_tokens': 1, 'output_tokens': 1})
        self.store.event(pid, 'call_start', who='fixture')
        self.store.event(pid, 'call', who='fixture', tokens={'source': 'fixture', 'input_tokens': 1, 'output_tokens': 1})
        self.store.close()
        self.store = Store(self.tmp / 'ws' / 'axbranch.sqlite3')                     # restart: fresh store + engine
        again = E.Engine(self.store, workspace=self.tmp / 'ws')
        with self.assertRaises(Rejected):                                          # the 2-call limit still holds
            again._budget_guard(pid, 'short')
        with self.assertRaises(Rejected):                                          # and cannot be re-opened
            again.configure_budget(pid, max_calls=50)
        self.store.pause(pid, 'Owner stop fixture')
        first = knowledge.record_department_experience(self.store, pid)
        self.assertTrue(first)                                                     # the stop itself is recorded
        second = knowledge.record_department_experience(self.store, pid)           # e.g. a second resume pass
        self.assertEqual(second, [])
        self.assertEqual(len(self.store.events(pid, {'department_experience'})), len(first))

    def test_experience_level_comes_from_recorded_provenance_not_the_verdict(self):
        ok = {'verdict': 'PASS', 'checks': {'ok': True}}
        prov = lambda producer, verifier, source='recorded': {**ok, 'checks': {'ok': True, 'verifier_provenance': {
            'producer': producer, 'verifier': verifier, 'producer_source': source}}}
        self.assertEqual(knowledge.verification_level(prov('claude', 'codex')), 'CROSS_PROVIDER_PASS')
        self.assertEqual(knowledge.verification_level(prov('claude', 'claude')), 'SAME_PROVIDER_ROLE_SEPARATED_PASS')
        self.assertEqual(knowledge.verification_level(ok), 'PASS_PROVENANCE_UNKNOWN')            # older record
        self.assertEqual(knowledge.verification_level(prov('claude', 'codex', 'configured fallback')),
                         'PASS_PROVENANCE_UNKNOWN')                                              # producer not recorded
        self.assertIsNone(knowledge.verification_level({'verdict': 'FAIL', 'checks': {'ok': False}}))
        # Through the engine: the verification stores provenance and the card carries it.
        script = DepartmentScript()
        pid = self.store.new_project('provenance fixture')
        for dep in ('research', 'operations'):
            D.attach(self.store, pid, dep, self.specs)
        eng = E.Engine(self.store, workspace=self.tmp / 'ws', vault=self.tmp / 'v', gai_db=self.tmp / 'x', llm=script)
        self.assertEqual(eng.run(pid)['state'], 'OWNER_REVIEW')
        v = self.store.verifications(pid)[-1]
        self.assertEqual(set(v['checks']['verifier_provenance']), {'producer', 'verifier', 'producer_source'})
        card = self.store.events(pid, {'department_experience'})[-1]['detail']
        self.assertEqual(card['verification_level'], knowledge.verification_level(v))
        self.assertNotEqual(card['verification_level'], 'INDEPENDENT_PASS')

    def _compact_llm(self, providers_by_stage):
        """Scripted model for the compact experiment: department pipeline, fixed usage per call, rubric scores."""
        from axbranch import providers as P
        pipeline = [dict(DepartmentScript().pipeline[0], provider=providers_by_stage[0]),
                    dict(DepartmentScript().pipeline[1], provider=providers_by_stage[1])]
        script = DepartmentScript(pipeline)
        from tests.test_engine import GOOD
        script.builds, script.verdicts = [GOOD] * 9, ['PASS'] * 9   # three projects share this scripted model
        prompts = []

        def llm(prompt, schema, *a, **kw):
            P._usage.value = {'source': 'fixture', 'input_tokens': 100, 'output_tokens': 50}
            if 'scores' in schema.get('properties', {}):
                prompts.append(prompt)
                score = {'score': 1, 'evidence': ['artifact line 1']}
                return {'scores': {k: dict(score) for k in kindex.PRODUCT_RUBRIC}, 'limitations': ['fixture']}, kw.get('prefer', 'codex'), []
            result, used, notes = script(prompt, schema, *a, **kw)
            if schema is E.BUILD:                      # a substantive markdown proposal (fixture, not market evidence)
                result = dict(result, content='# Scripted proposal\n\n' + '\n'.join(
                    f'## Section {n}\nScripted fixture text for section {n}; synthetic input row {n}.' for n in range(1, 9)),
                    files=[], edits=[])
            if schema is E.PLAN:                       # the compact tasks ask for one markdown proposal
                result = dict(result, artifact_kind='markdown', artifact_filename='proposal.md', required_tools=[],
                              network_access=[], runtime={'mode': 'none', 'probes': []})
            return result, used, notes
        return llm, prompts

    def test_compact_run_is_blind_independent_and_reports_every_budget(self):
        from axbranch import product_experiment as X
        llm, prompts = self._compact_llm(['claude', 'claude'])
        report = X.run_compact(self.tmp / 'compact', llm=llm)
        self.assertEqual(report['status'], 'COMPLETED', report.get('error'))
        prereg = json.loads((self.tmp / 'compact' / 'PRE_REGISTERED.json').read_text(encoding='utf-8'))
        self.assertIn('NOT confirmed minimums', prereg['estimate_note'])
        self.assertIn('NOT re-verified', prereg['textual_revision'])
        self.assertEqual((prereg['budget_production_per_project']['max_reported_tokens'],
                          prereg['budget_evaluation_per_result']['max_reported_tokens'], prereg['experiment_max_reported_tokens']),
                         (60000, 25000, 230000))
        for label in ('B-control', 'B-experience'):
            ev = report['evaluations'][label]
            self.assertEqual((ev['evaluator'], ev['independent']), ('codex', True))
            self.assertNotEqual(ev['evaluation_project'], report['runs'][label]['project'])   # its own budget
        self.assertEqual(len(prompts), 2)
        for prompt in prompts:                                                         # blind, no retrieval
            for leak in ('B-experience', 'B-control', 'department_experience', 'experience_search', 'prior_knowledge'):
                self.assertNotIn(leak, prompt)
        self.assertEqual(report['usage_total_reported_tokens'],
                         sum(m['reported_total_tokens'] for m in report['usage_by_project'].values()))
        self.assertIn('comparison', report)

    def test_compact_run_stops_when_no_independent_evaluator_exists(self):
        from axbranch import product_experiment as X
        llm, prompts = self._compact_llm(['codex', 'claude'])                          # both providers produced
        report = X.run_compact(self.tmp / 'compact', llm=llm)
        self.assertEqual(report['status'], 'STOPPED')
        self.assertIn('independent evaluation impossible', report['error'])
        self.assertEqual(prompts, [])
        with self.assertRaises(Rejected):
            X.run_compact(self.tmp / 'compact', llm=llm)                              # never reuses a root

    def test_compact_run_refuses_to_start_when_the_estimate_cannot_fit(self):
        from unittest import mock
        from axbranch import product_experiment as X
        heavy = dict(X.MEASURED_CALL_TOKENS, verify=(50000, 60000))
        with mock.patch.object(X, 'MEASURED_CALL_TOKENS', heavy):
            report = X.run_compact(self.tmp / 'too-big', llm=lambda *a, **k: self.fail('no model call may happen'))
        self.assertEqual((report['status'], report['model_calls']), ('NOT_STARTED_INFEASIBLE', 0))
        self.assertTrue((self.tmp / 'too-big' / 'PRE_REGISTERED.json').exists())

    def test_comparison_rejects_leakage_and_never_promotes_small_sample(self):
        control = {'execution_mode': 'subscription_cli', 'artifact_sha256': 'a' * 64, 'verification_ref': 'V-fixture',
                   'task_sha256': 'b' * 64, 'input_sha256': 'c' * 64, 'department_specs': {'product': 'fixed'},
                   'metrics': {'token_usage_complete': True, 'agent_turns_completed': 1, 'provider_seconds': 1},
                   'budget': {'calls': 12}, 'rubric_sha256': kindex.product_rubric_hash(), 'independent_evaluator': True,
                   'scores': {k: {'score': 1, 'evidence': ['fixture source']} for k in kindex.PRODUCT_RUBRIC}}
        treatment = copy.deepcopy(control)
        treatment['scores']['cost_accuracy']['score'] = 2
        comparison = kindex.compare_product_evaluations(control, treatment)
        self.assertEqual(comparison['local_score_delta'], 1)
        self.assertEqual(comparison['quality_improvement'], 'UNPROVEN')
        self.assertEqual(comparison['recommendation'], 'HOLD')
        self.assertFalse(comparison['department_update_applied'])
        treatment['input_sha256'] = 'different data'
        self.assertFalse(kindex.compare_product_evaluations(control, treatment)['comparison_valid'])
        treatment['input_sha256'] = control['input_sha256']
        treatment['execution_mode'] = 'scripted'
        self.assertFalse(kindex.compare_product_evaluations(control, treatment)['comparison_valid'])


if __name__ == '__main__':
    unittest.main()
