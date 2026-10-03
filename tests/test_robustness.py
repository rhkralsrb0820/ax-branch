"""Failures that must never strand a project: internal errors, and mixed code versions on one DB."""
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from axbranch import engine as E
from axbranch.state import SCHEMA_VERSION, Rejected, Store
from tests.test_engine import GOOD, Script


class RobustnessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db = self.tmp / 'ws' / 'axbranch.sqlite3'

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_internal_error_pauses_with_traceback_instead_of_stranding(self):
        store = Store(self.db)
        script = Script([GOOD], ['PASS'])

        def buggy(prompt, schema, **kw):
            if schema is E.BUILD:
                raise KeyError('simulated bug')
            return script(prompt, schema, **kw)
        try:
            eng = E.Engine(store, workspace=self.tmp / 'ws', vault=self.tmp / 'v', gai_db=self.tmp / 'x.db', llm=buggy)
            pid = store.new_project('make an add tool')
            p = eng.run(pid)
            self.assertEqual((p['state'], p['resume_state']), ('PAUSED', 'EXECUTING'))
            self.assertIn('Internal error KeyError', p['pause_reason'])
            self.assertIn('simulated bug', (self.tmp / 'ws' / 'logs' / 'engine-errors.log').read_text(encoding='utf-8'))
            store.resume(pid)                           # once fixed, the Owner resumes and it continues
            eng.llm = script
            self.assertEqual(eng.run(pid)['state'], 'PENDING_CLOSE')
        finally:
            store.close()

    def test_old_database_is_upgraded_and_marked(self):
        Store(self.db).close()
        con = sqlite3.connect(self.db)                  # simulate a 0.1.4 database: no marker, no column
        con.execute('PRAGMA user_version=0')
        con.execute('ALTER TABLE artifacts DROP COLUMN manifest')
        con.commit(); con.close()
        Store(self.db).close()
        con = sqlite3.connect(self.db)
        self.assertEqual(con.execute('PRAGMA user_version').fetchone()[0], SCHEMA_VERSION)
        self.assertIn('manifest', [r[1] for r in con.execute('PRAGMA table_info(artifacts)')])
        con.close()

    def test_older_code_refuses_newer_database(self):
        Store(self.db).close()
        con = sqlite3.connect(self.db)
        con.execute(f'PRAGMA user_version={SCHEMA_VERSION + 1}')
        con.commit(); con.close()
        with self.assertRaises(Rejected) as ctx:
            Store(self.db)
        self.assertIn('Update AX Branch', str(ctx.exception))


if __name__ == '__main__':
    unittest.main()
