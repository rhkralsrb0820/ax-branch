"""Owner window end to end: goal -> build/verify loop -> report shown -> SAVE & CLOSE,
driven through the real Tk widgets (scripted provider, temp workspace)."""
import shutil
import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest import mock
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

    def test_attached_file_goes_with_the_goal_as_a_read_only_input(self):
        data = self.tmp / 'sales.csv'
        data.write_text('item,amount\napple,10\n', encoding='utf-8')
        from unittest import mock
        with mock.patch('tkinter.filedialog.askopenfilenames', return_value=(str(data),)):
            _press(self.app, '파일 첨부')
        self.assertIn('sales.csv', self.app.attached_label.cget('text'))
        self.app.goal.insert('1.0', 'make an add tool')
        _press(self.app, '淸月 CEO에게 맡기기')
        pid = self.app.selected
        self.pump_until(lambda: not self.app.running)
        files = [r['name'] for e in self.app.store.events(pid, {'owner_inputs'}) for r in e['detail']['files']]
        self.assertEqual((files, self.app.attached), (['sales.csv'], []))
        self.assertTrue((self.ws / 'projects' / pid / 'inputs' / 'sales.csv').is_file())

    def test_a_failed_attachment_never_starts_a_project(self):
        from unittest import mock
        with mock.patch('tkinter.filedialog.askopenfilenames', return_value=(str(self.tmp / 'missing.csv'),)):
            _press(self.app, '파일 첨부')
        self.app.goal.insert('1.0', 'make an add tool')
        with mock.patch('tkinter.messagebox.showerror') as shown:
            _press(self.app, '淸月 CEO에게 맡기기')
        self.assertTrue(shown.called)
        self.assertEqual((self.app.store.projects(), self.app.running), ([], {}))

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

    def test_waiting_project_shows_owner_panel_and_feedback_reworks_it(self):
        self.script.builds, self.script.verdicts = [BROKEN, LAUNCHABLE], ['FAIL', 'PASS']
        pid = self.app.store.new_project('make an add tool')
        self.app.store.update(pid, budget=1)
        self.app.selected = pid
        self.app._launch(pid)
        self.pump_until(lambda: self.app.store.project(pid)['state'] == 'PAUSED' and not self.app.running)
        self.pump_until(lambda: self.app._owner_mode == 'decision')         # panel shown, no CLI needed
        self.assertIn('[수정 요청 / 계속]', self.app.owner_note.cget('text'))
        self.app.feedback.insert('1.0', '다른 방법으로 다시 만들어줘')
        _press(self.app.owner_box, '수정 요청 / 계속')
        self.pump_until(lambda: self.app.store.project(pid)['state'] == 'OWNER_REVIEW' and not self.app.running)
        self.assertEqual(len(self.app.store.projects()), 1)                   # the same project
        self.assertEqual([f['text'] for f in self.app.store.feedback(pid)], ['다른 방법으로 다시 만들어줘'])
        self.pump_until(lambda: self.app._owner_mode == 'review')             # works? + feedback + 완료
        with mock.patch.object(E.Engine, 'launch_verified', return_value=(Path('add_tool.py'), None)) as run:
            _press(self.app.owner_box, '결과 실행')                         # a program without a report: run it
        self.assertEqual(run.call_args.args[0], pid)                         # no CLI / Explorer needed
        self.assertIn('[결과 실행]', self.app.owner_note.cget('text'))

    def test_status_banner_distinguishes_states_and_never_claims_live_feedback(self):
        from axbranch.gui import banner
        texts = {key: banner(*key)[0] for key in [
            ('EXECUTING', 'ACTIVE', ''), ('PAUSED', 'WAITING_FOR_OWNER', 'Owner approval needed (external_connection): x'),
            ('OWNER_REVIEW', 'WAITING_FOR_OWNER', ''), ('PAUSED', 'WAITING_FOR_OWNER', 'NEEDS_DECISION: budget'),
            ('EXECUTING', 'STALLED', ''), ('PAUSED', 'WAITING_FOR_PROVIDER', 'RateLimited: quota'), ('CLOSED', 'COMPLETED', '')]}
        heads = [t.split(' · ')[0] for t in texts.values()]
        self.assertEqual(heads, ['작업 중', '승인 대기', '검토 대기', '결정 대기', '오류', '일시중지', '완료'])
        self.assertIn('반영되지 않습니다', texts[('EXECUTING', 'ACTIVE', '')])       # no false "applied" claim
        self.assertEqual(len({banner(*k)[1] for k in texts}), 6)                    # distinct colours (both waits share)
        # The default window keeps the agent table usable without dragging dividers (it showed only its header).
        pid = self.app.store.new_project('make an add tool')
        self.app.selected = pid
        self.app.open_project()
        self.app.deiconify()                               # a withdrawn window is never laid out
        self.app.geometry('1180x760')                      # the old default, where the table showed only its header
        for _ in range(5):
            self.app.update()
        try:
            self.assertGreater(self.app.agents.winfo_height(), 100)
        finally:
            self.app.withdraw()

    def test_project_list_shows_short_title_and_status_dot_not_internal_state(self):
        from axbranch.gui import indicator, project_title
        pid = self.app.store.new_project('주식 분석 프로그램 만들어봐')
        self.app.refresh_list()
        line = self.app.list.get('1.0', '1.end')
        self.assertEqual(line, '주식 분석 프로그램\t●')                     # no goal text, no 'CREATED'
        self.assertIn('waiting', self.app.list.tag_names('1.end-1c'))      # created, not started: blue
        self.assertEqual(self.app.store.project(pid)['goal'], '주식 분석 프로그램 만들어봐')   # goal unchanged
        self.assertEqual(project_title({'goal': 'x', 'plan': {'title': '리만 가설 연구'}}), '리만 가설 연구')
        cases = {('EXECUTING', 'ACTIVE'): 'working', ('OWNER_REVIEW', 'WAITING_FOR_OWNER'): 'owner',
                 ('PAUSED', 'WAITING_FOR_PROVIDER'): 'waiting', ('EXECUTING', 'STALLED'): 'error',
                 ('PAUSED', 'FAILED'): 'error', ('CLOSED', 'COMPLETED'): 'done'}
        for (state, status), tag in cases.items():
            self.assertEqual(indicator(state, status)[0], tag, (state, status))
        self.app.selected = None
        self.app.select(type('E', (), {'x': 1, 'y': 1})())                # a click on the first line
        self.assertEqual(self.app.selected, pid)

    def test_long_title_is_cut_only_when_needed_and_shown_whole_on_hover(self):
        from axbranch.gui import LIST_WIDTH, fit
        measure = len                                                       # 1 px per character
        self.assertEqual(fit('short', 10, measure), 'short')                # fits: untouched
        self.assertEqual(fit('a much longer project title', 10, measure), 'a much lo…')
        self.assertEqual(self.app.list.master.cget('width'), LIST_WIDTH)    # ~280 px list pane
        long = '섭씨/화씨/켈빈 온도를 서로 변환하는 Python 함수와 CLI'
        self.app.store.new_project(long)
        self.app.refresh_list(force=True)
        self.assertNotIn('\n', self.app.list.get('1.0', '1.end'))          # one line per project
        event = type('E', (), {'x': 1, 'y': 1, 'x_root': 10, 'y_root': 10})()
        self.app._tip(event)
        self.assertEqual(self.app._tipwin.text, long)                       # the full title on hover
        self.app._tip(None)
        self.assertIsNone(self.app._tipwin)

    def test_stop_pauses_a_project_waiting_for_the_owner_and_resume_restores_it(self):
        # 0.1.23: [중단] on a PENDING_CLOSE / OWNER_REVIEW project did nothing.
        from axbranch import supervisor
        for waiting in ('PENDING_CLOSE', 'OWNER_REVIEW'):
            with self.subTest(waiting=waiting):
                pid = self.app.store.new_project('waiting project')
                self.app.store.update(pid, state=waiting)
                self.app.selected = pid
                _press(self.app, '중단')
                p = self.app.store.project(pid)
                self.assertEqual((p['state'], p['resume_state']), ('PAUSED', waiting))
                self.assertIn(supervisor.OWNER_STOP, p['pause_reason'])
                engine = self.app.engine_factory()
                launch = mock.Mock()
                self.assertIsNone(supervisor.supervise(engine, pid, launch=launch, stop=mock.Mock()))
                engine.store.close()
                launch.assert_not_called()                                   # never auto-resumed
                self.assertEqual(self.app.store.project(pid)['state'], 'PAUSED')
                with mock.patch.object(supervisor, 'launch_detached') as worker:
                    _press(self.app, '계속 실행 / 재개')                      # the Owner resumes explicitly
                worker.assert_not_called()                                   # nothing to run: no worker
                self.assertEqual(self.app.store.project(pid)['state'], waiting)
        closed = self.app.store.new_project('closed project')
        self.app.store.update(closed, state='CLOSED')
        self.app.selected = closed
        _press(self.app, '중단')
        self.assertEqual(self.app.store.project(closed)['state'], 'CLOSED')   # unchanged

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
