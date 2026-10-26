"""H1: department registry lifecycle — recorded transitions, fail-closed reads, quarantine enforced at runtime."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from axbranch import departments as D, engine as E
from axbranch.state import Rejected, Store
from tests.test_departments import DepartmentScript

REAL = D.ROOT


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='axb-lifecycle-'))
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

    def test_legacy_is_usable_and_a_broken_record_fails_closed(self):
        self.assertEqual(D.lifecycle('research')['status'], 'legacy')
        self.assertIsNone(D.blocked('research'))
        (D.ROOT / 'research' / 'lifecycle.json').write_text('{not json', encoding='utf-8')
        self.assertEqual(D.lifecycle('research')['status'], 'quarantined')
        (D.ROOT / 'research' / 'lifecycle.json').write_text('{"status": "trusted"}', encoding='utf-8')
        self.assertIn('quarantined', D.blocked('research'))

    def test_transitions_are_recorded_and_verified_needs_independent_evidence(self):
        before = D.spec_digest(D.catalog()[0]['research'])
        with self.assertRaises(Rejected):
            D.set_lifecycle('research', 'verified', 'one good run', ['docs/evidence/a.md'])
        with self.assertRaises(Rejected):
            D.set_lifecycle('research', 'quarantined', '  ')
        with self.assertRaises(Rejected):
            D.set_lifecycle('research', 'trusted', 'x')
        D.set_lifecycle('research', 'verified', 'two independent tasks', ['docs/evidence/a.md', 'docs/evidence/b.md'])
        state = D.set_lifecycle('research', 'quarantined', 'bad citation found')
        self.assertEqual([h['to'] for h in state['history']], ['verified', 'quarantined'])
        self.assertEqual(state['history'][-1]['spec_sha256'], before)
        self.assertEqual(D.spec_digest(D.catalog()[0]['research']), before)      # status never changes the package

    def test_quarantine_blocks_new_attachment_and_delegation_but_keeps_history(self):
        pid = self.store.new_project('팀별 문의 우선순위 도구')
        for d in ('research', 'operations'):
            D.attach(self.store, pid, d, self.specs)
        D.set_lifecycle('research', 'quarantined', 'bad citation found')
        other = self.store.new_project('another')
        with self.assertRaises(Rejected):
            D.attach(self.store, other, 'research', self.specs)
        script = DepartmentScript()
        result = self.engine(script).run(pid)
        self.assertEqual(result['state'], 'PAUSED')
        self.assertIn('quarantined', result['pause_reason'])
        self.assertFalse([s for s, _ in script.contexts if s in (E.WORK, E.BUILD)])
        self.assertEqual(D.resolve(self.store, pid, self.specs)['research']['version'], self.specs['research']['version'])
        self.assertTrue(self.store.events(pid, {'department_attached'}))

    def test_quarantine_landing_after_staffing_is_caught_before_the_call(self):
        pid = self.store.new_project('팀별 문의 우선순위 도구')
        for d in ('research', 'operations'):
            D.attach(self.store, pid, d, self.specs)
        script = DepartmentScript()
        eng = self.engine(script)
        eng.run(pid, stop_at='EXECUTING')
        D.set_lifecycle('research', 'retired', 'replaced')
        result = eng.run(pid)
        self.assertEqual(result['state'], 'PAUSED')
        self.assertIn('retired', result['pause_reason'])
        self.assertFalse([s for s, _ in script.contexts if s in (E.WORK, E.BUILD)])

    def test_no_temporary_agent_or_role_bypass(self):
        attached = {d: self.specs[d] for d in ('research', 'operations')}
        D.set_lifecycle('research', 'quarantined', 'x')
        borrow_role = dict(name='a', agent_role=self.specs['research']['agent']['role'], department='',
                           capabilities=[], web=False)
        self.assertIn('not usable', D.check_stage(borrow_role, attached, self.specs))
        D.set_lifecycle('operations', 'candidate', 'new version under evaluation')
        anon = dict(name='b', agent_role='Helper', department='', capabilities=[], web=False)
        self.assertIn('no attached department is usable', D.check_stage(anon, attached, self.specs))
        self.assertIn('candidate', D.check_stage(dict(anon, department='operations'), attached, self.specs))


if __name__ == '__main__':
    unittest.main()
