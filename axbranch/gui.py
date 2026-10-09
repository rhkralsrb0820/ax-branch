"""Minimal Owner window. The engine runs in worker threads with their own SQLite
connection; this window only reads the database on a timer, so it never blocks
and always shows the persisted truth."""
import gc
import os
import re
from pathlib import Path
import threading
import time
import tkinter as tk
from tkinter import font as tkfont, messagebox, scrolledtext, ttk

from . import WORKSPACE, __version__, live, supervisor
from .engine import open_engine
from .state import Busy, Store

FONT = ('Malgun Gothic', 10)
COLUMNS = {'engine': ('엔진', 70), 'task': ('현재 작업', 170), 'status': ('상태', 230), 'last': ('마지막 활동', 90),
           'why': ('고용 이유', 220), 'result': ('결과', 260)}


class App(tk.Tk):
    def __init__(self, workspace=WORKSPACE, engine_factory=None, goal=None, resume=None):
        """engine_factory: callable returning a fresh Engine (own SQLite connection) — tests
        inject one; goal: pre-filled and submitted once the window is up (`--goal`)."""
        super().__init__()
        self.workspace = workspace
        self.engine_factory = engine_factory or (lambda: open_engine(workspace))
        self.injected = engine_factory is not None
        self.title(f'AX Branch {__version__} — 淸月 AI CEO')
        self.geometry('1180x760')
        self.store = Store(workspace / 'axbranch.sqlite3')
        self.running = {}            # pid -> cancel Event
        self.selected = None
        self._notice = ['']           # set by worker threads, shown by the Tk thread
        self._last_supervision = 0.0

        top = ttk.Frame(self, padding=8); top.pack(fill='x')
        ttk.Label(top, text='Goal', font=('Malgun Gothic', 11, 'bold')).pack(anchor='w')
        self.goal = tk.Text(top, height=3, font=FONT, wrap='word'); self.goal.pack(fill='x')
        ttk.Button(top, text='淸月 CEO에게 맡기기', command=self.start).pack(anchor='e', pady=4)

        body = ttk.PanedWindow(self, orient='horizontal'); body.pack(fill='both', expand=True, padx=8)
        # Project list: short title + one colored status dot (a Listbox can only color whole rows).
        holder = ttk.Frame(body, width=LIST_WIDTH)       # starting width of the list pane (~280 px)
        holder.pack_propagate(False)
        self.list = tk.Text(holder, font=LIST_FONT, width=1, wrap='none', cursor='arrow',
                            spacing1=4, spacing3=4, padx=LIST_PAD, state='disabled')
        self.list.pack(fill='both', expand=True)
        for tag, color in INDICATOR_COLORS.items():
            self.list.tag_configure(tag, foreground=color)
        self.list.tag_configure('selected', background='#d6e8ff')
        self.list.bind('<Button-1>', self.select)
        # Widths change -> titles are re-fitted; hover shows the full title.
        self.list.bind('<Configure>', lambda _e: self.refresh_list(force=True))
        self.list.bind('<Motion>', self._tip)
        self.list.bind('<Leave>', lambda _e: self._tip(None))
        body.add(holder, weight=0)                        # the main area takes any extra width; divider draggable
        self.ids, self._rows, self._titles, self._tipwin = [], None, [], None
        self._labels = {}
        right = ttk.PanedWindow(body, orient='vertical')
        body.add(right, weight=1)
        self.right = right
        self.owner_box = ttk.LabelFrame(right, text='Owner 결정 — AX Branch가 기다리고 있습니다', padding=6)
        self.owner_note = ttk.Label(self.owner_box, font=FONT, wraplength=820, justify='left')
        self.owner_note.pack(anchor='w')
        self.works_row = ttk.Frame(self.owner_box)
        self.run_button = ttk.Button(self.works_row, text='결과 실행', command=self.run_result)
        self.run_button.pack(side='left', padx=(0, 12))
        self.works = tk.StringVar(value='unknown')
        ttk.Label(self.works_row, text='실행해 보니:', font=FONT).pack(side='left')
        for label, value in (('작동함', 'yes'), ('작동하지 않음', 'no'), ('아직 확인 안 함', 'unknown')):
            ttk.Radiobutton(self.works_row, text=label, value=value, variable=self.works).pack(side='left', padx=4)
        self.feedback = tk.Text(self.owner_box, height=4, font=FONT, wrap='word')
        self.decide_row = ttk.Frame(self.owner_box)
        for text, cmd in (('수정 요청 / 계속', self.owner_send), ('완료', self.owner_finish), ('중단', self.stop)):
            ttk.Button(self.decide_row, text=text, command=cmd).pack(side='left', padx=3)
        self.approve_row = ttk.Frame(self.owner_box)
        for text, cmd in (('외부 연결 승인', lambda: self.network(True)), ('외부 연결 거절', lambda: self.network(False))):
            ttk.Button(self.approve_row, text=text, command=cmd).pack(side='left', padx=3)
        self._owner_mode = None
        # Live execution view: project -> 淸月 CEO -> hired agents -> verification -> Owner review, read
        # from local state (supervisor status, heartbeat/activity files, SQLite) every refresh; no AI call.
        self.live = tk.Text(right, font=FONT, wrap='word', state='disabled', height=8)
        right.add(self.live, weight=0)
        self.agents = ttk.Treeview(right, columns=tuple(COLUMNS), show='tree headings', height=8, selectmode='browse')
        self.agents.heading('#0', text='Agent')
        self.agents.column('#0', width=230, stretch=False)
        for col, (title, width) in COLUMNS.items():
            self.agents.heading(col, text=title)
            self.agents.column(col, width=width, stretch=col in ('why', 'result'))
        self.agents.bind('<<TreeviewSelect>>', lambda _e: self.show())
        right.add(self.agents, weight=1)
        tabs = ttk.Notebook(right)
        right.add(tabs, weight=2)
        self.records = scrolledtext.ScrolledText(tabs, font=FONT, wrap='word', state='disabled')
        self.timeline = scrolledtext.ScrolledText(tabs, font=FONT, wrap='word', state='disabled')
        self.detail = scrolledtext.ScrolledText(tabs, font=FONT, wrap='word', state='disabled')
        for widget, title in ((self.records, 'Agent 기록'), (self.timeline, '타임라인'), (self.detail, '프로젝트')):
            tabs.add(widget, text=title)

        bar = ttk.Frame(self, padding=8); bar.pack(fill='x')
        for text, cmd in (('리뷰 / 피드백…', self.review_dialog), ('외부 연결 승인', lambda: self.network(True)),
                          ('외부 연결 거절', lambda: self.network(False)),
                          ('계속 실행 / 재개', self.resume), ('중단', self.stop), ('프로젝트 종료…', self.finish),
                          ('폴더 열기', self.open_folder)):
            ttk.Button(bar, text=text, command=cmd).pack(side='left', padx=3)
        self.status = ttk.Label(bar, text=''); self.status.pack(side='right')
        self.protocol('WM_DELETE_WINDOW', self.quit_app)
        self.refresh()
        if goal:
            self.goal.insert('1.0', goal)
            self.after(500, self.start)
        elif resume:                     # same as selecting the project and pressing 계속 실행 / 재개
            self.selected = resume
            self.after(500, self.resume)

    # ---- project workers
    def _launch(self, pid):
        """A run is its own background process, so closing this window never stops it; the window only
        reads its state. (In-window threads are kept for injected test engines.)"""
        if self.injected:
            return self._launch_thread(pid)
        if supervisor.status(self.workspace, self.store, pid)['status'] == 'ACTIVE':
            return                                       # already running somewhere: never a second worker
        supervisor.launch_detached(self.workspace, pid)

    def _launch_thread(self, pid):
        if pid in self.running:
            return
        cancel = threading.Event()
        self.running[pid] = cancel
        # The worker must not reference the window: if it outlived the window and dropped the last
        # reference, Tk would be torn down on the wrong thread and abort the process.
        factory, running, notice = self.engine_factory, self.running, self._notice

        def work():
            engine = None
            try:
                engine = factory()
                engine.run(pid, cancel)
            except Busy as e:           # e.g. a CLI or Codex session is running it; nothing changed
                notice[0] = str(e)
            except Exception as e:      # never die silently in a windowed app
                notice[0] = f'{type(e).__name__}: {e}'
            finally:
                if engine is not None:
                    engine.store.close()
                running.pop(pid, None)
        threading.Thread(target=work, daemon=True).start()

    def start(self):
        goal = self.goal.get('1.0', 'end').strip()
        if not goal:
            return
        self.selected = self.store.new_project(goal)
        self._owner_action('new')
        self.goal.delete('1.0', 'end')
        self._launch(self.selected)

    def resume(self):
        if not self.selected:
            return
        p = self.store.project(self.selected)
        if p['state'] == 'PAUSED':
            if p['resume_state'] in ('OWNER_REVIEW', 'PENDING_CLOSE', 'ARCHIVE_PENDING_APPROVAL'):
                self.store.resume(self.selected)          # back to waiting for the Owner: no engine work, no worker
                self._owner_action('resume')
                return
            extra = 3 if 'not lowered' in (p['pause_reason'] or '') else 0
            self.store.resume(self.selected, extra)
        self._owner_action('resume')
        self._launch(self.selected)

    def stop(self):
        """Owner stop: end the worker's whole process tree and PAUSE (checkpointed; the supervisor never
        auto-resumes an Owner stop). 계속 실행 / 재개 continues from the same state."""
        if not self.selected:
            return
        if self.selected in self.running:
            self.running[self.selected].set()
            return
        rec = supervisor.status(self.workspace, self.store, self.selected)
        if rec.get('worker_pid') and supervisor._held(self.workspace, self.selected):
            supervisor.stop_worker(rec['worker_pid'], pid=self.selected)    # also one waiting for a provider slot
        p = self.store.project(self.selected)
        reason = f'{supervisor.OWNER_STOP} (window). Resume continues from here.'
        if p['state'] == 'PAUSED':
            self.store.update(self.selected, pause_reason=reason)          # an Owner stop, not a failure
        elif p['state'] != 'CLOSED':                       # incl. a project waiting for the Owner (0.1.23: no-op)
            self.store.pause(self.selected, reason)
        self._owner_action('stop')

    def review_dialog(self):
        """Two separate questions: does it work? / what do you want next (plain language) or finish."""
        if not self.selected:
            return
        win = tk.Toplevel(self); win.title('AX Branch — Owner review'); win.grab_set()
        ttk.Label(win, text='1. 실행해 보니 제대로 작동하나요?', font=FONT, padding=(10, 8, 10, 2)).pack(anchor='w')
        works = tk.StringVar(value='unknown')
        for label, value in (('작동함', 'yes'), ('작동하지 않음', 'no'), ('아직 확인 안 함', 'unknown')):
            ttk.Radiobutton(win, text=label, value=value, variable=works).pack(anchor='w', padx=24)
        ttk.Label(win, text='2. 바꾸거나 더하고 싶은 점이 있나요? 자유롭게 적어 주세요 (없으면 비워 두세요).\n'
                            '   작동하지 않으면 어떻게 실행했고 무엇이 보였는지도 적어 주세요.',
                  font=FONT, padding=(10, 10, 10, 2)).pack(anchor='w')
        box = tk.Text(win, height=7, width=72, font=FONT, wrap='word'); box.pack(padx=10, fill='both', expand=True)
        win.feedback_text = box                      # reachable by tests
        row = ttk.Frame(win, padding=8); row.pack(fill='x')

        def send(finish=False):
            answer = {'yes': True, 'no': False}.get(works.get())
            if self.review(answer, box.get('1.0', 'end').strip(), finish):
                win.destroy()
                # Closed dialogs leave Tk objects in reference cycles; collect them HERE, on the Tk thread.
                # Left to chance, the cyclic GC may run on an engine worker thread and abort Python
                # ("Tcl_AsyncDelete: async handler deleted by the wrong thread").
                gc.collect()
        ttk.Button(row, text='보내기', command=send).pack(side='right', padx=3)
        ttk.Button(row, text='마무리(프로젝트 끝내기)', command=lambda: send(True)).pack(side='right', padx=3)

    def network(self, approve):
        if not self.selected:
            return
        engine = self.engine_factory()
        try:
            engine.decide_network(self.selected, approve)
            self._owner_action('approve')
        except Exception as e:
            messagebox.showwarning('AX Branch', str(e))
            return
        finally:
            engine.store.close()
        self.resume()

    def _owner_panel(self, p, status):
        """Show the decision panel only while this project waits for the Owner; never require a CLI."""
        reason = p['pause_reason'] or ''
        if status != 'WAITING_FOR_OWNER' or p['state'] in ('ARCHIVE_PENDING_APPROVAL',):
            mode = None
        elif 'approval needed' in reason:
            mode = 'approval'
        elif p['state'] == 'OWNER_REVIEW':
            mode = 'review'
        else:
            mode = 'decision'
        if mode != self._owner_mode:
            for w in (self.works_row, self.feedback, self.decide_row, self.approve_row):
                w.pack_forget()
            if self._owner_mode is not None:
                self.right.forget(self.owner_box)
            if mode is not None:
                self.right.insert(0, self.owner_box, weight=0)
                if mode == 'approval':
                    self.approve_row.pack(anchor='w', pady=4)
                else:
                    if mode == 'review':
                        self.works_row.pack(anchor='w', pady=(4, 0))
                    self.feedback.pack(fill='x', pady=4)
                    self.decide_row.pack(anchor='w')
            self._owner_mode = mode
        if mode == 'review':
            label = self._result_label(p['id'])
            if self.run_button.cget('text') != label:
                self.run_button.config(text=label)
            note = (f'결과가 검증을 통과했습니다. [{label}]로 검증된 결과를 바로 확인하고 의견을 적어 주세요. '
                    '수정이 필요하면 [수정 요청 / 계속], 끝내려면 [완료].')
        elif mode == 'decision':
            note = (f'{reason[:220] or p["state"]}\n원하는 방향을 자연어로 적고 [수정 요청 / 계속]을 누르면 淸月 CEO가 분석해 같은 프로젝트에서 '
                    '다시 계획·작업·검증합니다. 비워 두고 누르면 같은 방향으로 3라운드 더 진행합니다. 끝내려면 [완료].')
        elif mode == 'approval':
            note = reason[:400]
        else:
            note = ''
        if self.owner_note.cget('text') != note:
            self.owner_note.config(text=note)

    def _result_label(self, pid):
        key = (pid, self.store.project(pid)['iteration'])
        if key not in self._labels:                        # once per project version, not every refresh
            engine = self.engine_factory()
            try:
                self._labels[key] = '결과 보기' if engine.result_info(pid)[0] == 'view' else '결과 실행'
            except Exception:
                return '결과 실행'
            finally:
                engine.store.close()
        return self._labels[key]

    def run_result(self):
        """[결과 보기] / [결과 실행]: the verified result in one click (no CLI, no Explorer, no editor)."""
        if not self.selected:
            return
        engine = self.engine_factory()
        try:
            how, path = engine.open_result(self.selected, show_text=self.show_text)
            self._notice[0] = f"{'열었음' if how == 'view' else '실행함'}: {path.name} (검증된 버전)"
        except Exception as e:
            messagebox.showwarning('AX Branch', str(e))
        finally:
            engine.store.close()

    def show_text(self, title, text, path):
        """A report inside AX Branch (read-only), with the program run one click away when there is one."""
        win = tk.Toplevel(self)
        win.title(f'AX Branch — {title}')
        win.geometry('900x700')
        view = scrolledtext.ScrolledText(win, font=FONT, wrap='word')
        view.insert('1.0', text)
        view.config(state='disabled')
        row = ttk.Frame(win, padding=6)
        row.pack(fill='x', side='bottom')
        pid = self.selected
        if any(Path(path).parent.glob('*.py')):
            ttk.Button(row, text='프로그램 실행', command=lambda: self._run_program(pid)).pack(side='left')
        ttk.Button(row, text='닫기', command=win.destroy).pack(side='right')
        view.pack(fill='both', expand=True)
        win.view = view
        self._viewer = win

    def _run_program(self, pid):
        engine = self.engine_factory()
        try:
            engine.launch_verified(pid)
        except Exception as e:
            messagebox.showwarning('AX Branch', str(e))
        finally:
            engine.store.close()

    def owner_send(self):
        text = self.feedback.get('1.0', 'end').strip()
        works = {'yes': True, 'no': False}.get(self.works.get()) if self._owner_mode == 'review' else None
        if self._owner_mode == 'review' and works is None and not text:
            messagebox.showinfo('AX Branch', '바꾸고 싶은 점을 적거나, 작동 여부를 선택해 주세요.')
            return
        if self.review(works, text):
            self.feedback.delete('1.0', 'end')
            self.works.set('unknown')

    def owner_finish(self):
        if self.review(finish=True):
            self.finish()

    def review(self, works=None, text='', finish=False):
        """Record the Owner's review; anything that needs work reopens the same project and rebuilds it."""
        if not self.selected:
            return False
        engine = self.engine_factory()
        try:
            p = engine.owner_review(self.selected, works, text, finish)
            self._owner_action('review')
        except Exception as e:
            messagebox.showwarning('AX Branch', str(e))
            return False
        finally:
            engine.store.close()
        if p['state'] not in ('OWNER_REVIEW', 'PENDING_CLOSE', 'PAUSED', 'CLOSED', 'ARCHIVE_PENDING_APPROVAL'):
            self._launch(self.selected)                  # REWORK / resumed: the same project runs again
        return True

    def finish(self):
        if not self.selected:
            return
        engine = self.engine_factory()
        try:
            p = engine.close(self.selected)            # CEO asks before anything happens
        except Exception as e:
            messagebox.showwarning('AX Branch', str(e)); engine.store.close(); return
        win = tk.Toplevel(self); win.title('淸月 AI CEO'); win.grab_set()
        ttk.Label(win, text='프로젝트를 마칩니다. 이 프로젝트의 지식을 저장할까요?', font=FONT, padding=10).pack()
        sat = tk.IntVar(value=90)
        row = ttk.Frame(win, padding=6); row.pack()
        ttk.Label(row, text='만족도(%)').pack(side='left')
        ttk.Spinbox(row, from_=0, to=100, textvariable=sat, width=5).pack(side='left')
        ttk.Label(row, text='  이유(선택)').pack(side='left')
        why = tk.StringVar()
        ttk.Entry(row, textvariable=why, width=48).pack(side='left')

        def choose(choice):
            confirm = False
            if choice == 'discard':
                confirm = messagebox.askyesno('확인', '저장하지 않고 닫으면 이 프로젝트의 지식과 Agent 컨텍스트가 '
                                              '영구히 버려집니다. 계속할까요?', parent=win)
                if not confirm:
                    return
            try:
                if choice != 'discard':
                    engine.note_satisfaction(p['id'], why.get())
                engine.close(p['id'], choice, confirm, sat.get())
                engine.store.event(p['id'], 'owner_action', action=f'close_{choice}', channel='app')
            except Exception as e:
                messagebox.showerror('AX Branch', str(e), parent=win)
            win.destroy(); engine.store.close(); gc.collect()   # Tk cycles freed on the Tk thread
        for text, choice in (('A. SAVE & CLOSE', 'save'), ('B. PAUSE', 'pause'), ('C. CLOSE WITHOUT SAVE', 'discard')):
            ttk.Button(win, text=text, command=lambda c=choice: choose(c)).pack(fill='x', padx=12, pady=3)

    def open_folder(self):
        target = self.workspace / 'projects' / self.selected if self.selected else self.workspace
        if target.exists():
            os.startfile(target)

    # ---- display
    def select(self, event=None):
        line = int(self.list.index(f'@{event.x},{event.y}').split('.')[0]) - 1 if event else -1
        if 0 <= line < len(self.ids):
            self.selected = self.ids[line]
            self._rows = None                             # redraw the highlight
            self.refresh_list()
            self.show()
        return 'break'

    def refresh_list(self, force=False):
        """Titles with a status dot. The exact internal state stays in the project view on the right."""
        projects = self.store.projects()
        watch = supervisor.candidates(self.store)
        labels = {p['id']: supervisor.status(self.workspace, self.store, p['id'])['status'] for p in projects}
        if self.selected is None and watch:                  # open on the work in progress
            self.selected = next((pid for pid in watch if labels[pid] == 'ACTIVE'), watch[0])
        rows = [(p['id'], project_title(self.store.project(p['id'])), indicator(p['state'], labels[p['id']]))
                for p in projects]
        if rows == self._rows and not force:
            return
        self._rows, self.ids, self._titles = rows, [r[0] for r in rows], [r[1] for r in rows]
        width = self.list.winfo_width() if self.list.winfo_width() > 1 else LIST_WIDTH
        font = tkfont.Font(font=self.list.cget('font'))
        # The dot sits on a right-aligned tab at the right edge; the title gets everything left of it.
        edge = max(60, width - 2 * LIST_PAD - 6)
        room = edge - font.measure('  ●') - 4
        self.list.config(state='normal', tabs=(edge, 'right'))
        self.list.delete('1.0', 'end')
        for pid, title, (tag, mark) in rows:
            start = self.list.index('end-1c')
            self.list.insert('end', f'{fit(title, room, font.measure)}\t')
            self.list.insert('end', mark, tag)
            self.list.insert('end', '\n')
            if pid == self.selected:
                self.list.tag_add('selected', start, f'{start} lineend+1c')
        self.list.config(state='disabled')

    def _tip(self, event):
        """Hover: the full project title in a small tooltip."""
        line = int(self.list.index(f'@{event.x},{event.y}').split('.')[0]) - 1 if event else -1
        text = self._titles[line] if 0 <= line < len(self._titles) else None
        if self._tipwin is not None and (text is None or self._tipwin.text != text):
            self._tipwin.destroy()
            self._tipwin = None
        if text and self._tipwin is None:
            tip = tk.Toplevel(self)
            tip.wm_overrideredirect(True)
            tip.text = text
            tk.Label(tip, text=text, font=FONT, background='#ffffe0', relief='solid', borderwidth=1, padx=4).pack()
            tip.wm_geometry(f'+{event.x_root + 14}+{event.y_root + 12}')
            self._tipwin = tip

    def refresh(self):
        self.refresh_list()
        self.show()
        self.status.config(text=self._notice[0] or f'실행 중 {len(self.running)}건')
        if time.monotonic() - self._last_supervision > 30:
            self._last_supervision = time.monotonic()
            self.supervise()
        self._tick = self.after(1500, self.refresh)

    def supervise(self):
        """The window is the supervisor while it is open: stalled or failed work is detected and recovered
        here (bounded), so the Owner never has to diagnose a run in a terminal."""
        from . import supervisor
        engine = self.engine_factory()
        try:
            for pid in supervisor.candidates(engine.store):
                if pid in self.running and supervisor.status(self.workspace, engine.store, pid)['status'] == 'ACTIVE':
                    continue
                supervisor.supervise(engine, pid, launch=self._launch,
                                     stop=lambda p, w: supervisor.stop_worker(w, self.running, p))
        except Exception as e:                       # supervision must never take the window down
            self._notice[0] = f'supervisor: {type(e).__name__}: {e}'
        finally:
            engine.store.close()

    def _owner_action(self, action):
        if self.selected:
            self.store.event(self.selected, 'owner_action', action=action, channel='app')

    def show(self):
        if not self.selected:
            return
        h = self.store.handoff(self.selected)
        p = self.store.project(self.selected)
        lines = [f"[{h['project_id']}] {h['state']}" + (f"  ⏸ {h['pause_reason']}" if h['pause_reason'] else ''),
                 f"Goal: {h['goal']}", f"다음: {h['next_action']}"]
        lines.append('')
        view = live.view(self.workspace, self.store, self.selected)
        self._owner_panel(p, dict(view['header'])['상태'].split(' — ')[0])
        _put(self.live, '\n'.join(f'{k}: {v}' for k, v in view['header'] if k not in ('목표', '다음 작업'))
             + f"\n다음: {dict(view['header'])['다음 작업']}")
        rows = {r['key']: r for r in view['pipeline']}
        if list(self.agents.get_children()) != list(rows):
            self.agents.delete(*self.agents.get_children())
            for key in rows:
                self.agents.insert('', 'end', iid=key)
        for key, r in rows.items():
            self.agents.item(key, text=f"{r['mark']} {r['title']}",
                             values=(r['engine'], r['task'], r['detail'], r['last'], r['why'], r['result']))
        chosen = self.agents.selection()
        _put(self.records, live.records(self.store, self.selected, chosen[0]) if chosen
             else 'Agent를 선택하면 그 Agent의 주장 · 근거 · 반론 · 결정 · 검증 기록이 표시됩니다.')
        _put(self.timeline, '\n'.join(f"[{t['at']}] {t['actor']}  {t['text']}" for t in reversed(view['timeline'])))
        if h['interpretation']:
            lines += ['■ CEO 해석', h['interpretation'], '', '■ 수용 기준', *[f'  - {c}' for c in h['acceptance_criteria']], '',
                      '■ 파이프라인', *[f"  {i + 1}. {s['name']} — {s['agent_role']} ({s['provider']}{', web' if s['web'] else ''})"
                                       for i, s in enumerate(h['pipeline'])], '']
        for v in self.store.verifications(self.selected):
            rt = v['checks'].get('runtime')
            lines.append(f"■ 검증 {v['iteration']}회차: {v['verdict']} ({v['provider']}) · 결정적 검사 "
                         f"{'통과' if v['checks']['ok'] else '실패'}"
                         + (f" · 실행 검증({rt['mode']}) {'통과' if rt['ok'] else '실패'}" if rt else ''))
            if rt:
                lines += [f"  실행 {'OK ' if s['ok'] else 'FAIL'} {s['name']}" + (f" — {', '.join(s['problems'])}" if s.get('problems') else '')
                          for s in rt.get('steps', [])]
            lines += [f"  [{f['severity']}] {f['issue']}" for f in v['result']['findings']]
        for f in self.store.feedback(self.selected):
            lines.append(f"■ Owner 피드백 {f['iteration']}회차 ({f['verdict']}): {f['text']}")
        for ap in self.store.approvals(self.selected):
            lines.append(f"■ 외부 연결 {ap['subject']} — {ap['purpose']}: {ap['status']}")
        if p['report']:
            r = p['report']
            lines += ['', '■ 淸月 AI CEO 보고', r['summary'], '', f"판단: {r['judgment']}", f"산출물: {r['artifact']}",
                      *([f"테스트 방법: {r['how_to_test']}"] if r.get('how_to_test') else []),
                      *[f'  - {s}' for s in r['next_steps']]]
        if p['archive_note']:
            lines += ['', f"Obsidian 저장: {p['archive_note']}"]
        _put(self.detail, '\n'.join(lines))

    def destroy(self):
        if getattr(self, '_tick', None):
            self.after_cancel(self._tick)       # no refresh callback firing into a destroyed window
        self.store.close()
        super().destroy()
        gc.collect()                            # same reason: never let a worker thread free Tk objects

    def quit_app(self):
        # Background workers keep running after the window closes; only in-window (test) threads stop.
        if self.running and not messagebox.askyesno('AX Branch', '실행 중인 프로젝트가 있습니다. 중단하고 닫을까요? '
                                                    '(상태는 저장되어 다음에 재개할 수 있습니다)'):
            return
        for cancel in self.running.values():
            cancel.set()
        self.destroy()


# User-facing status, mapped from the internal state / supervisor status (the DB state is never changed).
INDICATOR_COLORS = {'working': '#2e9e44', 'owner': '#e8870e', 'waiting': '#2f74d0', 'error': '#d0342c', 'done': '#8a8a8a'}


def indicator(state, status):
    """(color tag, mark): 작업 중 green · Owner 확인/승인 필요 orange · 대기/일시정지 blue · 오류/복구 필요 red · 완료 gray ✓."""
    if state == 'CLOSED' or status == 'COMPLETED':
        return 'done', '✓'
    if status == 'WAITING_FOR_OWNER':
        return 'owner', '●'
    if status in ('STALLED', 'FAILED'):
        return ('waiting', '●') if state == 'CREATED' else ('error', '●')    # not started yet is not an error
    if status in ('ACTIVE', 'RECOVERING'):
        return 'working', '●'
    return 'waiting', '●'                                 # PAUSED, WAITING_FOR_PROVIDER


_ASK = re.compile(r'\s*(?:을|를)?\s*(?:만들어\s*(?:줘|봐|주세요|주십시오)|해\s*(?:줘|봐|주세요)|부탁(?:해|합니다)?)[.!?\s]*$')


LIST_WIDTH, LIST_PAD, LIST_FONT = 280, 8, ('Malgun Gothic', 11)


def project_title(p):
    """The CEO's title from planning; for older projects a short title derived from the goal (the goal is unchanged)."""
    title = ((p.get('plan') or {}).get('title') or '').strip()
    if not title:
        goal = re.sub(r'^\s*\[[^\]]*\]\s*', '', p['goal'].splitlines()[0] if p['goal'] else '')
        title = _ASK.sub('', re.split(r'[:.(]', goal, 1)[0]).strip() or goal.strip()
    return title


def fit(text, room, measure):
    """text on one line within `room` pixels; '…' only when it does not fit."""
    if measure(text) <= room:
        return text
    while text and measure(text + '…') > room:
        text = text[:-1]
    return text.rstrip() + '…'


def _put(widget, text):
    """Replace a read-only text widget's content only when it changed, keeping the Owner's scroll position."""
    if text != widget.get('1.0', 'end-1c'):
        top = widget.yview()[0]
        widget.config(state='normal'); widget.delete('1.0', 'end')
        widget.insert('1.0', text); widget.config(state='disabled')
        widget.yview_moveto(top)


def main(goal=None, resume=None):
    App(goal=goal, resume=resume).mainloop()

