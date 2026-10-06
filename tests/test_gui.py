"""Owner window end to end: goal -> build/verify loop -> report shown -> SAVE & CLOSE,
driven through the real Tk widgets (scripted provider, temp workspace)."""
import shutil
import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path
from tkinter import ttk

from axbranch import engine as E
from axbranch.gui import App
from axbranch.state import Store
from tests.test_engine import BROKEN, GOOD, LAUNCHABLE, Script


def _buttons(widget):
    for child in widget.winfo_children():
        if isinstance(child, (ttk.Button, tk.Button)):
            yield child
        yield from _buttons(child)


def _radios(widget):
    for child in widget.winfo_children():
        if isinstance(child, ttk.Radiobutton):
            yield child
        yield from _radios(child)


def _press(widget, text):
    button = next(b for b in _buttons(widget) if b.cget('text') == text)
    button.invoke()


class GuiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.ws, self.vault = self.tmp / 'ws', self.tmp / 'vault'
        self.vault.mkdir()
        self.script = Script([BROKEN, GOOD], ['FAIL', 'PASS'])
        ws, vault, gai, script = self.ws, self.vault, self.tmp / 'none.db', self.script

        def factory():          # captures plain values only: a worker thread must never hold the window
            return E.Engine(Store(ws / 'axbranch.sqlite3'), workspace=ws, vault=vault, gai_db=gai, llm=script)
        try:
            self.app = App(workspace=self.ws, engine_factory=factory)
        except tk.TclError as e:
            if 'display' not in str(e).lower():      # only a missing display is a reason to skip
                raise
            self.skipTest(f'no display: {e}')
        self.app.withdraw()

    def tearDown(self):
        self.app.destroy()           # App.destroy collects Tk cycles on this (the Tk) thread
        shutil.rmtree(self.tmp, ignore_errors=True)

    def pump_until(self, condition, seconds=30):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.app.update()
            if condition():
                return
            time.sleep(0.05)
        pid = self.app.selected
        self.fail('GUI did not reach the expected state: ' + repr((self.app._notice[0], self.app.running,
                  pid and self.app.store.project(pid)['state'], pid and self.app.store.project(pid)['pause_reason'])))

    def test_goal_to_verified_report_to_save_and_close(self):
        self.app.goal.insert('1.0', 'make an add tool')
        _press(self.app, '淸月 CEO에게 맡기기')
        pid = self.app.selected
        self.pump_until(lambda: self.app.store.project(pid)['state'] == 'OWNER_REVIEW' and not self.app.running)
        self.pump_until(lambda: '淸月 AI CEO 보고' in self.app.detail.get('1.0', 'end'))
        shown = self.app.detail.get('1.0', 'end')
        self.assertIn('검증 1회차: FAIL', shown)
        self.assertIn('검증 2회차: PASS', shown)
        # Live view, from local state only: agent cards, records on click, timeline.
        cards = {k: self.app.agents.item(k, 'text') for k in self.app.agents.get_children()}
        self.assertEqual(cards['owner'], '● OWNER_REVIEW')
        self.assertEqual(cards['verification'], '✓ Verification Agent')
        self.assertTrue(cards['ceo'].startswith('✓ 淸月 CEO'))
        self.assertIn('stage:0', cards)
        self.app.agents.selection_set('verification')
        self.pump_until(lambda: '검증 2회차: PASS' in self.app.records.get('1.0', 'end'))
        timeline = self.app.timeline.get('1.0', 'end')
        self.assertIn('hired', timeline)
        self.assertIn('Assigned engine', timeline)

        _press(self.app, '리뷰 / 피드백…')                 # Q1 works? Q2 what next? -> finish
        dialog = next(w for w in self.app.winfo_children() if isinstance(w, tk.Toplevel))
        next(r for r in _radios(dialog) if r.cget('text') == '작동함').invoke()
        _press(dialog, '마무리(프로젝트 끝내기)')
        self.assertEqual(self.app.store.project(pid)['state'], 'PENDING_CLOSE')
        self.assertEqual([f['verdict'] for f in self.app.store.feedback(pid)], ['works', 'finish'])
        _press(self.app, '프로젝트 종료…')
        dialog = next(w for w in self.app.winfo_children() if isinstance(w, tk.Toplevel))
        _press(dialog, 'A. SAVE & CLOSE')
        self.pump_until(lambda: self.app.store.project(pid)['state'] == 'CLOSED')
        note = Path(self.app.store.project(pid)['archive_note'])
        self.assertTrue(note.is_file())
        self.pump_until(lambda: 'Obsidian 저장' in self.app.detail.get('1.0', 'end'))

    def test_problem_report_reopens_same_project_and_redelivers(self):
        self.script.builds, self.script.verdicts = [GOOD, LAUNCHABLE], ['PASS', 'PASS']
        self.app.goal.insert('1.0', 'make an add tool')
        _press(self.app, '淸月 CEO에게 맡기기')
        pid = self.app.selected
        self.pump_until(lambda: self.app.store.project(pid)['state'] == 'OWNER_REVIEW' and not self.app.running)
        _press(self.app, '리뷰 / 피드백…')
        dialog = next(w for w in self.app.winfo_children() if isinstance(w, tk.Toplevel))
        next(r for r in _radios(dialog) if r.cget('text') == '작동하지 않음').invoke()
        dialog.feedback_text.insert('1.0', 'double-click closes immediately')
        _press(dialog, '보내기')
        self.pump_until(lambda: self.app.store.project(pid)['state'] == 'OWNER_REVIEW' and not self.app.running
                        and len(self.app.store.artifacts(pid)) == 2)
        self.assertEqual(self.app.store.projects()[0]['id'], pid)            # same project, not a new one
        self.pump_until(lambda: 'Owner 피드백 1회차 (problem): double-click closes immediately'
                        in self.app.detail.get('1.0', 'end'))

    def test_busy_project_is_reported_not_run(self):
        pid = self.app.store.new_project('make an add tool')
        self.app.selected = pid
        engine = self.app.engine_factory()
        with engine.lock(pid):                     # another session holds the project
            _press(self.app, '계속 실행 / 재개')
            self.pump_until(lambda: 'Already running' in self.app.status.cget('text'))
        engine.store.close()
        self.assertEqual(self.app.store.project(pid)['state'], 'CREATED')


if __name__ == '__main__':
    unittest.main()
