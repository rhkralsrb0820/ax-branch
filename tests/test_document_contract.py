"""Product Planning document contract: found early, fixed in production, never mistaken for content verification."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from axbranch import departments as D, engine as E
from axbranch.state import Store
from tests.test_departments import DepartmentScript
from tests.test_product_planning import document

STAGE = [dict(name='plan', agent_role='Product planner', instructions='Write the proposal', department='product-planning',
              provider='claude', web=False, why='planning owns the decision')]


def with_plan(change):
    """document() with its product_plan changed by `change(plan)`."""
    text = document()
    head, block = text.split('```json\n', 1)
    data = json.loads(block.split('\n```', 1)[0])
    change(data['product_plan'])
    return head + '```json\n' + json.dumps(data) + '\n```'


class PlanScript(DepartmentScript):
    def __call__(self, prompt, schema, *args, **kw):
        result, used, notes = super().__call__(prompt, schema, *args, **kw)
        if schema is E.PLAN:
            result.update(artifact_kind='markdown', artifact_filename='plan.md')
        return result, used, notes


class DocumentContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='axb-doc-contract-'))
        self.store = Store(self.tmp / 'ws' / 'axbranch.sqlite3')
        self.specs = D.catalog()[0]
        self.spec = self.specs['product-planning']

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_project(self, builds, verdicts=('PASS', 'PASS', 'PASS')):
        script = PlanScript(pipeline=STAGE)
        script.builds, script.verdicts = list(builds), list(verdicts)
        pid = self.store.new_project('product planning cost scenario')
        D.attach(self.store, pid, 'product-planning', self.specs)
        eng = E.Engine(self.store, workspace=self.tmp / 'ws', vault=self.tmp / 'v', gai_db=self.tmp / 'x', llm=script)
        return pid, eng.run(pid), script

    def test_missing_and_empty_required_lists_are_named(self):
        missing = with_plan(lambda p: p.pop('excluded'))
        empty = with_plan(lambda p: p.update(excluded=[], experiments=[]))
        self.assertIn('product_plan.excluded 목록이 필요합니다', D.check_document(self.spec, missing))
        problems = D.check_document(self.spec, empty)
        self.assertIn('product_plan.excluded 목록이 필요합니다', problems)
        self.assertIn('product_plan.experiments 목록이 필요합니다', problems)

    def test_unsupported_claims_are_not_filled_in(self):
        verified_without_source = with_plan(lambda p: p['claims'].__setitem__(
            0, {'statement': 'Tutors pay 30,000 KRW', 'status': 'VERIFIED', 'evidence': []}))
        honest_unknown = with_plan(lambda p: p['claims'].__setitem__(
            0, {'statement': 'Willingness to pay', 'status': 'UNKNOWN', 'evidence': []}))
        self.assertIn('확인 사실에 근거 참조가 없습니다', D.check_document(self.spec, verified_without_source))
        self.assertEqual(D.check_document(self.spec, honest_unknown), [])      # UNKNOWN is legitimate, nothing added

    def test_contract_failure_skips_the_verifier_and_the_producer_fixes_it(self):
        bad = with_plan(lambda p: p.update(excluded=[], experiments=[]))
        pid, p, script = self.run_project([bad, document()])
        self.assertEqual(p['state'], 'OWNER_REVIEW', p.get('pause_reason'))
        first, second = self.store.verifications(pid)
        self.assertEqual((first['verdict'], first['provider']), ('FAIL', 'engine'))
        self.assertTrue(any('excluded' in f['issue'] for f in first['result']['findings']))
        self.assertEqual(second['verdict'], 'PASS')
        self.assertEqual(sum(s is E.VERDICT for s, _ in script.contexts), 1)       # only the valid document
        self.assertEqual(len(self.store.events(pid, {'verification_call_skipped'})), 1)
        builds = [c for s, c in script.contexts if s is E.BUILD]
        self.assertIn('product_plan_rules', builds[0]['required_document']['contracts'][0])
        rework = json.dumps(builds[1].get('verification_findings'), ensure_ascii=False)
        self.assertIn('product_plan.excluded', rework)                            # the exact problem reached the producer

    def test_a_valid_format_is_not_a_content_verdict(self):
        pid, p, script = self.run_project([document(), document()], verdicts=['FAIL', 'FAIL', 'FAIL'])
        v = self.store.verifications(pid)[0]
        self.assertEqual((v['verdict'], v['provider']), ('FAIL', 'codex'))        # the independent verifier decided
        self.assertTrue(any(s is E.VERDICT for s, _ in script.contexts))
        self.assertFalse(self.store.events(pid, {'verification_call_skipped'}))


if __name__ == '__main__':
    unittest.main()
