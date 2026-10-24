"""Owner window end to end: goal -> build/verify loop -> report shown -> SAVE & CLOSE,
driven through the real Tk widgets (scripted provider, temp workspace)."""
import json
import shutil
import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest import mock
from tkinter import ttk

from axbranch import engine as E, live
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
    button = next((b for b in _buttons(widget) if b.cget('text') == text), None)
    if button is not None:
        button.invoke()
        return
    # The redesigned command bar groups project actions in a real menu.
    def menus(parent):
        for child in parent.winfo_children():
            if isinstance(child, tk.Menu):
                yield child
            yield from menus(child)
    for menu in menus(widget):
        for index in range((menu.index('end') or 0) + 1):
            if menu.type(index) == 'command' and menu.entrycget(index, 'label') == text:
                menu.invoke(index)
                return
    raise AssertionError(f'No UI action labelled {text}')


class GuiTests(unittest.TestCase):
    def test_dashboard_composer_folds_and_restores_without_executing(self):
        self.app.update_idletasks()
        self.assertEqual(self.app.composer.winfo_manager(), 'pack')
        pid = self.app.store.new_project('layout check')
        self.app.selected = pid
        self.app.open_project()
        self.app.update_idletasks()
        self.assertEqual(self.app.composer.winfo_manager(), '')
        self.assertFalse(self.app.running)
        self.app.go_home()
        self.app.update_idletasks()
        self.assertEqual(self.app.composer.winfo_manager(), 'pack')
        self.assertEqual(self.app.store.project(pid)['state'], 'CREATED')

    def test_orb_motion_follows_real_state_and_stops_when_idle_or_turned_off(self):
        from axbranch.home import orb_state
        self.assertEqual(orb_state([]), 'idle')
        self.assertEqual(orb_state([('EXECUTING', 'ACTIVE', None), ('OWNER_REVIEW', 'WAITING_FOR_OWNER', None)]), 'delegating')
        self.assertEqual(orb_state([('PLANNING', 'ACTIVE', None)]), 'planning')
        self.assertEqual(orb_state([('VERIFYING', 'ACTIVE', None)]), 'verifying')
        self.assertEqual(orb_state([('REWORK', 'ACTIVE', None)]), 'rework')
        self.assertEqual(orb_state([('OWNER_REVIEW', 'WAITING_FOR_OWNER', None)]), 'done')        # result to review
        self.assertEqual(orb_state([('PAUSED', 'WAITING_FOR_OWNER', 'Owner approval needed')]), 'waiting')
        self.assertEqual(orb_state([('PAUSED', 'PAUSED', 'Rejected: 오너가 중단했습니다')]), 'paused')
        self.assertEqual(orb_state([('PAUSED', 'WAITING_FOR_PROVIDER', 'RateLimited: quota')]), 'limit')
        self.assertEqual(orb_state([('PAUSED', 'WAITING_FOR_PROVIDER', None)]), 'limit')
        self.assertEqual(orb_state([('EXECUTING', 'STALLED', None)]), 'error')
        self.assertEqual(orb_state([('CREATED', 'STALLED', None)]), 'idle')         # never started is not an error
        orb = self.app.orb
        self.app.update()

        def settle():                              # let any transition finish, then one frame
            orb._settle_until, orb._impulse, orb._burst = 0, 0, 0
            orb._cancel()
            orb._tick()
        orb.set_state('idle'); settle()
        self.assertIsNone(orb._job)                                                 # idle: no loop at all
        orb.set_state('verifying')
        self.assertIsNotNone(orb._job)
        for stopped in ('waiting', 'paused', 'limit', 'error'):
            orb.set_state(stopped); settle()
            self.assertIsNone(orb._job, stopped)                                    # stopped states: still
        orb.set_state('planning', motion=False); settle()
        self.assertIsNone(orb._job)                                                 # motion off: still frame
        # With no project running, the window's own refresh leaves the orb idle and the loop stopped.
        self.app.refresh(); settle()
        self.assertEqual((orb.state, orb._job), ('idle', None))
        self.assertEqual(self.app.orb_label.cget('text'), '대기')
        self.assertIn('다음:', self.app.orb_caption.cget('text'))                  # readable state + next action
        # The goal box reacts (focus/typing) only while no real work is shown; a submitted goal hands over.
        self.app._goal_input('focus')
        self.assertEqual(self.app.orb.state, 'focus')
        self.app.goal.insert('1.0', 'x'); self.app._goal_input('typing')
        self.assertEqual((self.app.orb.state, self.app.orb_label.cget('text')), ('typing', '목표 입력 중'))
        self.app.goal.delete('1.0', 'end'); self.app._goal_input(None)
        self.assertEqual(self.app.orb.state, 'idle')
        self.app.motion_off.set(True)
        self.app.low_power.set(True)
        self.app._save_motion()
        saved = json.loads((self.ws / 'settings.json').read_text(encoding='utf-8'))
        self.assertEqual((saved['motion_off'], saved['low_power'], orb.low_power), (True, True, True))

    def test_orb_completion_once_and_delegation_links_from_real_events(self):
        from axbranch import departments
        pid = self.app.store.new_project('orb events')
        departments.attach(self.app.store, pid, 'research', self.app.department_specs)
        self.app.store.event(pid, 'department_delegation', stage='a', department='research', version='1.0.0',
                             agent_role='Research analyst', why='')
        self.app._statuses = {pid: 'ACTIVE'}
        with mock.patch.object(self.app.store, 'projects', return_value=[{'id': pid, 'state': 'EXECUTING'}]):
            self.app._update_orb()
        self.assertEqual(self.app.orb.state, 'delegating')
        self.assertEqual([n for n, _ in self.app.orb.departments], ['리서치'])
        self.assertIn('리서치', self.app.orb_caption.cget('text'))
        self.app._statuses = {pid: 'WAITING_FOR_OWNER'}
        with mock.patch.object(self.app.store, 'projects', return_value=[{'id': pid, 'state': 'OWNER_REVIEW'}]), \
                mock.patch.object(self.app.orb, 'complete') as complete:
            self.app._update_orb()
            self.app._update_orb()                                                 # once, not every refresh
        self.assertEqual(complete.call_count, 1)
        self.assertEqual(self.app.orb.state, 'done')

    def test_departments_attach_by_drop_or_button_persist_and_detach(self):
        from axbranch import departments
        from axbranch.gui import App as Window
        pid = self.app.store.new_project('department wiring')
        self.app.selected = pid
        self.app.open_project()
        # Drag a library chip and release it over the project's department row. The screen hit test is given
        # (another application's window on the Owner's desktop would make the real one environment-dependent).
        self.app._drag = ('research', 10, 10)
        with mock.patch.object(self.app, 'winfo_containing', return_value=self.app.project_departments):
            self.app._drop(200, 200)
        self.assertEqual([d['id'] for d in departments.attached(self.app.store, pid)], ['research'])
        # A drop the hit test cannot place (outside, or covered by another window) connects nothing and says so.
        self.app._drag = ('operations', 10, 10)
        with mock.patch.object(self.app, 'winfo_containing', return_value=None), \
                mock.patch('axbranch.gui.messagebox.showinfo') as info:
            self.app._drop(200, 200)
        self.assertIn('연결되지 않았습니다', info.call_args.args[1])
        self.assertIn('프로젝트에 추가', info.call_args.args[1])
        self.assertEqual([d['id'] for d in departments.attached(self.app.store, pid)], ['research'])
        with mock.patch('axbranch.gui.messagebox.showinfo') as info:            # duplicate refused, said once
            self.app.add_department('research', to_project=True)
        self.assertIn('이미 연결된 부서', info.call_args.args[1])
        self.app.department_detail('operations')                                 # details -> [프로젝트에 추가]
        detail = next(w for w in self.app.winfo_children() if getattr(w, 'department', None) == 'operations')
        _press(detail, '프로젝트에 추가')
        self.app.update()
        chips = [w.department for w in self.app.project_departments.winfo_children() if hasattr(w, 'department')]
        self.assertEqual(chips, ['research', 'operations'])
        # Reopened app: the connection is restored from the project's own records, not recreated.
        with mock.patch.object(Window, 'supervise', lambda self: None):     # reopening must not run anything
            again = Window(workspace=self.ws, engine_factory=lambda: None)
        try:
            again.withdraw()
            again.selected = pid
            again.open_project()
            again.update()
            self.assertEqual([w.department for w in again.project_departments.winfo_children()
                              if hasattr(w, 'department')], ['research', 'operations'])
        finally:
            again.destroy()
        self.app.remove_department('research', from_project=True)
        self.assertIn('다음 위임부터', self.app._notice[0])
        self.assertEqual([d['id'] for d in departments.attached(self.app.store, pid)], ['operations'])

    def test_open_flag_shows_a_project_without_running_it(self):
        from axbranch.gui import App as Window
        pid = self.app.store.new_project('open only')
        with mock.patch.object(Window, 'supervise', lambda self: None), \
                mock.patch.object(Window, '_launch', side_effect=AssertionError('must not run')):
            again = Window(workspace=self.ws, engine_factory=lambda: None, open_id=pid)
        try:
            again.withdraw()
            again.update()
            self.assertEqual((again.selected, again.home_mode), (pid, False))
            self.assertEqual(again.store.project(pid)['state'], 'CREATED')
        finally:
            again.destroy()

    def test_pending_departments_attach_when_the_goal_starts_and_pipeline_names_them(self):
        from axbranch import departments
        self.app.add_department('research', to_project=False)
        with mock.patch('axbranch.gui.messagebox.showinfo'):
            self.app.add_department('research', to_project=False)              # no duplicate chip
        self.assertEqual(self.app.pending_departments, ['research'])
        self.app.goal.insert('1.0', 'make an add tool')
        self.app.start()
        pid = self.app.selected
        self.assertEqual([d['id'] for d in departments.attached(self.app.store, pid)], ['research'])
        self.assertEqual(self.app.pending_departments, [])
        self.pump_until(lambda: self.app.store.project(pid)['state'] in ('OWNER_REVIEW', 'PAUSED') and not self.app.running)
        # The scripted plan names no department although one is attached: shown as a temporary agent.
        rows = live.view(self.ws, self.app.store, pid)['pipeline']
        self.assertTrue(any(r['title'].startswith('[임시 에이전트]') for r in rows), [r['title'] for r in rows])

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
