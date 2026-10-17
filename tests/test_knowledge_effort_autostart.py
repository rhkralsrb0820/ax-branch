"""0.2 prep: readable archive + lesson retrieval, per-project Owner Effort, D-AUTO-1 scheduler/notification."""
import shutil
import tempfile
import unittest
from pathlib import Path

from axbranch import autostart, engine as E, knowledge, metrics
from axbranch.state import Store
from tests.test_engine import BROKEN, GOOD, Script


class ArchiveRetrievalEffortTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.store = Store(self.tmp / 'ws' / 'axbranch.sqlite3')
        self.vault = self.tmp / 'vault'
        self.vault.mkdir()
        self.eng = E.Engine(self.store, workspace=self.tmp / 'ws', vault=self.vault, gai_db=self.tmp / 'none.db',
                            llm=Script([BROKEN, GOOD], ['FAIL', 'PASS']))

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def closed_project(self):
        pid = self.store.new_project('make an add tool for invoices')
        self.eng.run(pid)
        self.eng.close(pid)
        self.eng.note_satisfaction(pid, 'UI 가독성과 보고서 구조가 부족')
        return pid, self.eng.close(pid, 'save', satisfaction=60)

    def test_readable_archive_keeps_every_original_record_and_is_retrieved_for_planning(self):
        pid, p = self.closed_project()
        text = Path(p['archive_note']).read_text(encoding='utf-8')
        for heading in knowledge.SECTIONS:
            self.assertIn(heading, text)
        self.assertLess(text.index('## 요약'), text.index('## Evidence (원본 기록)'))
        self.assertIn('60/100 — UI 가독성과 보고서 구조가 부족', text)
        self.assertIn('[major] wrong sum', text)                                  # original findings kept
        effort = self.store.events(pid, {'owner_effort'})[-1]['detail']
        self.assertEqual((effort['verification_rounds'], effort['satisfaction'], effort['owner_review_minutes']),
                         (2, 60, 'UNKNOWN'))
        # A new project's planning context gets the lessons, traceable to note and project.
        script = Script([GOOD], ['PASS'])
        eng2 = E.Engine(self.store, workspace=self.tmp / 'ws', vault=self.vault, gai_db=self.tmp / 'none.db', llm=script)
        eng2.run(self.store.new_project('invoices add tool, second version'), stop_at='STAFFING')
        plan_prompt = next(prompt for schema, _, prompt in script.prompts if schema is E.PLAN)
        self.assertIn(f'"project": "{pid}"', plan_prompt)
        self.assertIn('재사용 지식 (Reusable Knowledge)', plan_prompt)
        self.assertIn('Evidence (원본 기록)', plan_prompt)

    def test_restructure_existing_archive_keeps_content_and_backs_up(self):
        pid, p = self.closed_project()
        renamed = Path(p['archive_note']).with_name('Owner named it.md')    # the Owner renamed the note
        Path(p['archive_note']).rename(renamed)
        note, _ = self.eng.rearchive(pid)
        self.assertEqual(Path(note), renamed)
        self.assertEqual(self.store.project(pid)['archive_note'], str(renamed))
        backup = Path(self.store.events(pid, {'archive_restructured'})[-1]['detail']['backup'])
        self.assertTrue(backup.is_file())
        self.assertEqual(len(list(self.vault.rglob('*.md'))), 1)            # no duplicate note in the vault

    def test_effort_before_owner_action_records_is_unknown_not_guessed(self):
        pid = self.store.new_project('old project')
        self.store.db.execute('UPDATE projects SET created=0 WHERE id=?', (pid,))
        self.store.event(pid, 'owner_action', action='resume', channel='developer_cli')
        effort = metrics.project_effort(self.store, pid)
        self.assertIn('UNKNOWN', str(effort['owner_interventions']))
        self.assertIn('UNKNOWN', str(effort['manual_recovery']))


class AutostartTests(unittest.TestCase):
    def test_memory_line_records_free_memory_and_never_breaks_a_pass(self):
        from unittest import mock
        line = autostart.memory_line()
        self.assertRegex(line, r'^free=\d+MB( commit_free=\d+MB/\d+MB)?( top=\S+)?$')
        with mock.patch.object(autostart.subprocess, 'run', side_effect=OSError('no tasklist')):
            self.assertTrue(autostart.memory_line().startswith('memory=unknown'))

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.store = Store(self.tmp / 'ws' / 'axbranch.sqlite3')
        self.eng = E.Engine(self.store, workspace=self.tmp / 'ws', vault=self.tmp / 'vault', gai_db=self.tmp / 'x.db',
                            llm=Script([GOOD], ['PASS']))

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_task_is_single_instance_every_5_minutes_and_at_logon(self):
        xml = autostart.task_xml('C:/py/pythonw.exe', '-X utf8 -m axbranch supervise', 'C:/ax & b', 'PC\\me')
        for part in ('<MultipleInstancesPolicy>IgnoreNew', '<Interval>PT5M', '<LogonTrigger>',
                     '-m axbranch supervise', 'C:/ax &amp; b', '<RunLevel>LeastPrivilege'):
            self.assertIn(part, xml)

    def test_owner_is_notified_once_per_waiting_state(self):
        pid = self.store.new_project('make an add tool')
        self.eng.run(pid)                                                    # -> OWNER_REVIEW
        shown = []
        show = lambda title, text: shown.append(text) or True
        self.assertEqual(autostart.notify_waiting(self.eng, show), [pid])
        self.assertEqual(autostart.notify_waiting(self.eng, show), [])       # same state: not again
        self.assertIn('[결과 실행]', shown[0])
        self.store.pause(pid, 'NEEDS_DECISION: test')                        # a new waiting state
        self.assertEqual(autostart.notify_waiting(self.eng, show), [pid])
        self.assertEqual(len(shown), 2)
        self.store.update(pid, state='PENDING_CLOSE', pause_reason=None)    # the Owner chose finish: no toast
        self.assertEqual(autostart.notify_waiting(self.eng, show), [])
        other = self.store.new_project('second')
        self.store.pause(other, 'NEEDS_DECISION: x')
        self.assertEqual(autostart.notify_waiting(self.eng, lambda t, x: False), [])   # toast failed
        self.assertEqual(autostart.notify_waiting(self.eng, show), [other])           # tried again


if __name__ == '__main__':
    unittest.main()
