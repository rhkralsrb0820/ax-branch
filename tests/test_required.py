"""H2: available vs required attachments, enforced at planning, execution/rework, acceptance and removal."""
import shutil
import tempfile
import unittest
from pathlib import Path

from axbranch import actions, departments as D, engine as E
from axbranch.state import Rejected, Store
from tests.test_departments import DepartmentScript

REAL = D.ROOT
RESEARCH_ONLY = [{'name': 'analyse', 'agent_role': 'Research analyst', 'instructions': 'find the numbers',
                  'provider': 'codex', 'web': False, 'department': 'research', 'why': 'research owns the analysis'},
                 {'name': 'build', 'agent_role': 'Report writer', 'instructions': 'write it', 'provider': 'claude',
                  'web': False, 'department': '', 'why': 'temporary agent'}]


class RequiredTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='axb-required-'))
        shutil.copytree(REAL, self.tmp / 'departments')
        for f in (self.tmp / 'departments').glob('*/lifecycle.json'):
            f.unlink()
        D.ROOT = self.tmp / 'departments'
        self.store = Store(self.tmp / 'ws' / 'axbranch.sqlite3')
        self.specs = D.catalog()[0]

    def tearDown(self):
        D.ROOT = REAL
        self.store.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def engine(self, script):
        return E.Engine(self.store, workspace=self.tmp / 'ws', vault=self.tmp / 'v', gai_db=self.tmp / 'x', llm=script)

    def project(self, required=(), available=()):
        pid = self.store.new_project('팀별 문의 우선순위 도구')
        for d in available:
            D.attach(self.store, pid, d, self.specs)
        for d in required:
            D.attach(self.store, pid, d, self.specs, mode='required')
        return pid

    def test_legacy_attachment_is_available_and_modes_are_recorded(self):
        pid = self.store.new_project('legacy')
        self.store.event(pid, 'department_attached', department='research', version=self.specs['research']['version'],
                         spec=self.specs['research'], spec_sha256=D.spec_digest(self.specs['research']))
        self.assertEqual(D.attached(self.store, pid)[0]['mode'], 'available')
        D.set_mode(self.store, pid, 'research', 'required')
        self.assertEqual(D.attached(self.store, pid)[0]['mode'], 'required')
        self.assertEqual([e['detail']['mode'] for e in self.store.events(pid, {'department_mode'})], ['required'])

    def test_removal_needs_explicit_recorded_intent(self):
        pid = self.project(required=['research'])
        with self.assertRaises(Rejected):
            D.detach(self.store, pid, 'research')
        with self.assertRaises(Rejected):
            D.set_mode(self.store, pid, 'research', 'available', reason=' ')
        D.set_mode(self.store, pid, 'research', 'available', reason='goal no longer needs data analysis')
        D.detach(self.store, pid, 'research')
        self.assertEqual(D.attached(self.store, pid), [])
        self.assertEqual(self.store.events(pid, {'department_mode'})[-1]['detail']['reason'],
                         'goal no longer needs data analysis')

    def test_plan_without_the_required_department_is_blocked_before_any_agent_call(self):
        pid = self.project(required=['operations'], available=['research'])
        script = DepartmentScript(pipeline=RESEARCH_ONLY)
        result = self.engine(script).run(pid)
        self.assertEqual(result['state'], 'PAUSED')
        self.assertIn("required department 'operations' has no stage", result['pause_reason'])
        self.assertFalse([s for s, _ in script.contexts if s in (E.WORK, E.BUILD)])
        planned = next(c for s, c in script.contexts if s is E.PLAN)
        self.assertIn('required_rule', planned)
        self.assertEqual({d['id']: d['mode'] for d in planned['attached_departments']},
                         {'research': 'available', 'operations': 'required'})

    def test_renamed_role_temporary_agent_does_not_fulfil_a_requirement(self):
        pid = self.project(required=['operations'], available=['research'])
        role = self.specs['operations']['agent']['role']
        script = DepartmentScript(pipeline=[RESEARCH_ONLY[0], dict(RESEARCH_ONLY[1], agent_role=role)])
        result = self.engine(script).run(pid)
        self.assertEqual(result['state'], 'PAUSED')
        self.assertIn('operations', result['pause_reason'])

    def test_fulfilled_required_departments_reach_owner_review(self):
        pid = self.project(required=['research', 'operations'])
        result = self.engine(DepartmentScript()).run(pid)
        self.assertEqual(result['state'], 'OWNER_REVIEW', result.get('pause_reason'))
        p = self.store.project(pid)
        self.assertEqual(D.required_unfulfilled(self.store, pid, p['plan'], p['iteration']), [])
        self.assertFalse(self.store.events(pid, {'required_unmet'}))

    def test_requirement_added_after_staffing_applies_at_execution(self):
        pid = self.project(available=['research', 'operations'])
        script = DepartmentScript(pipeline=RESEARCH_ONLY)
        eng = self.engine(script)
        eng.run(pid, stop_at='EXECUTING')
        D.set_mode(self.store, pid, 'operations', 'required')
        result = eng.run(pid)
        self.assertEqual(result['state'], 'PAUSED')
        self.assertIn("required department 'operations'", result['pause_reason'])
        self.assertFalse([s for s, _ in script.contexts if s in (E.WORK, E.BUILD)])

    def test_stale_work_or_unmet_criteria_never_fulfil_at_acceptance(self):
        pid = self.project(required=['research'], available=['operations'])
        result = self.engine(DepartmentScript()).run(pid)
        self.assertEqual(result['state'], 'OWNER_REVIEW', result.get('pause_reason'))
        p = self.store.project(pid)
        self.store.update(pid, plan_version=p['plan_version'] + 1)          # a new plan version: old notes are stale
        self.assertIn('no valid recorded work', D.required_unfulfilled(self.store, pid, p['plan'], p['iteration'])[0])
        self.store.update(pid, plan_version=p['plan_version'])
        results = self.store.events(pid, {'department_acceptance'})[-1]['detail']['results']
        self.store.event(pid, 'department_acceptance', iteration=p['iteration'],
                         results=[dict(r, status='unverifiable') if r['department'] == 'research' else r for r in results])
        self.assertIn('not all met', D.required_unfulfilled(self.store, pid, p['plan'], p['iteration'])[0])

    def test_unavailable_department_cannot_be_or_stay_required(self):
        pid = self.project(available=['research'])
        D.set_lifecycle('research', 'quarantined', 'bad citation found')
        with self.assertRaises(Rejected):
            D.set_mode(self.store, pid, 'research', 'required')
        D.set_lifecycle('research', 'verified', 'two tasks', ['e/1.md', 'e/2.md'])
        D.set_mode(self.store, pid, 'research', 'required')
        D.set_lifecycle('research', 'retired', 'replaced')
        self.assertIn('unavailable', D.required_problems(self.store, pid, {'pipeline': RESEARCH_ONLY})[0])

    def test_start_records_the_owner_required_choice(self):
        pid = actions.start(self.store, None, '문의 보고서', ['research', 'operations'], self.specs, [], 'web',
                            required=['operations'])
        self.assertEqual({d['id']: d['mode'] for d in D.attached(self.store, pid)},
                         {'research': 'available', 'operations': 'required'})


if __name__ == '__main__':
    unittest.main()
