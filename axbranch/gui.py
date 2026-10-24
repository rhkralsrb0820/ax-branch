"""Minimal Owner window. The engine runs in worker threads with their own SQLite
connection; this window only reads the database on a timer, so it never blocks
and always shows the persisted truth."""
import gc
import json
import os
import re
from pathlib import Path
import threading
import time
import tkinter as tk
from tkinter import font as tkfont, messagebox, scrolledtext, ttk

from . import WORKSPACE, __version__, departments, library, live, supervisor
from .library import project_title
from .engine import open_engine
from .state import Busy, Store
from .home import Home, draw_pipeline, configure_theme, RoundedPanel, StatusOrb, ORB_LABELS, orb_state

FONT = ('Malgun Gothic', 10)
COLUMNS = {'engine': ('엔진', 70), 'task': ('현재 작업', 170), 'status': ('상태', 230), 'last': ('마지막 활동', 90),
           'why': ('고용 이유', 220), 'result': ('결과', 260)}


class RecordText(scrolledtext.ScrolledText):
    """Keep Text's API and keyboard scrolling, replace the classic OS scrollbar."""
    def __init__(self, parent, **kwargs):
        super().__init__(parent, padx=16, pady=14, borderwidth=0, highlightthickness=0, **kwargs)
        self.frame.configure(borderwidth=0, highlightthickness=0, relief='flat', background='white')
        self.vbar.destroy()
        self.vbar = ttk.Scrollbar(self.frame, orient='vertical', command=self.yview)
        self.vbar.pack(side='right', fill='y')
        self.configure(yscrollcommand=self.vbar.set)


class App(tk.Tk):
    def __init__(self, workspace=WORKSPACE, engine_factory=None, goal=None, resume=None, open_id=None):
        """engine_factory: callable returning a fresh Engine (own SQLite connection) — tests
        inject one; goal: pre-filled and submitted once the window is up (`--goal`)."""
        super().__init__()
        configure_theme(self)
        self.workspace = workspace
        self.engine_factory = engine_factory or (lambda: open_engine(workspace))
        self.injected = engine_factory is not None
        self.title(f'AX Branch {__version__} — 淸月 AI CEO')
        # Fit the screen (1920x1080 at 100% gave a 1180x760 window whose agent table showed only its header).
        # Leave room for the Windows taskbar (at 88% of 1080 the bottom button bar sat under it).
        w, h = min(1440, int(self.winfo_screenwidth() * .9)), min(880, int(self.winfo_screenheight() * .82))
        self.geometry(f'{w}x{h}+{(self.winfo_screenwidth() - w) // 2}+{max(0, (self.winfo_screenheight() - h) // 2 - 30)}')
        self.minsize(1000, 740)
        self.store = Store(workspace / 'axbranch.sqlite3')
        self.running = {}            # pid -> cancel Event
        self.selected = None
        self.home_mode = True
        self._notice = ['']           # set by worker threads, shown by the Tk thread
        self._last_supervision = 0.0

        shell = ttk.Frame(self, padding=16); shell.pack(fill='both', expand=True)
        holder = ttk.Frame(shell, width=224, style='Sidebar.TFrame')
        holder.pack(side='left', fill='y', padx=(0, 18))
        holder.pack_propagate(False)
        ttk.Label(holder, text='◒  AX Branch', style='Brand.TLabel').pack(anchor='w', padx=18, pady=(22, 4))
        ttk.Label(holder, text='청월 AI 워크스페이스', style='Side.TLabel').pack(anchor='w', padx=18, pady=(0, 30))
        main = ttk.Frame(shell); main.pack(side='left', fill='both', expand=True)
        header = ttk.Frame(main); header.pack(fill='x', pady=(4, 16))
        self.page_title = ttk.Label(header, text='워크스페이스  /  청월 홈', style='Page.TLabel')
        self.page_title.pack(side='left')
        ttk.Button(header, text='+ 새 업무', command=self.go_home).pack(side='right', padx=(12, 0))
        ttk.Label(header, text=f'로컬 워크스페이스   ·   v{__version__}', style='Muted.TLabel').pack(side='right')
        self.settings_path = workspace / 'settings.json'
        try:
            saved = json.loads(self.settings_path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            saved = {}
        self.motion_off = tk.BooleanVar(value=bool(saved.get('motion_off')))
        ttk.Checkbutton(header, text='모션 끄기', variable=self.motion_off, command=self._save_motion).pack(side='right', padx=12)
        panel = RoundedPanel(main)
        panel.pack(fill='x', pady=(0, 16))
        self.composer = panel
        top = panel.content
        orb_box = ttk.Frame(top, style='Card.TFrame'); orb_box.pack(side='left', padx=(0, 20))
        self.orb = StatusOrb(orb_box); self.orb.pack()
        self.orb_label = ttk.Label(orb_box, text=ORB_LABELS['idle'], style='Card.TLabel'); self.orb_label.pack()
        composer_content = ttk.Frame(top, style='Card.TFrame')
        composer_content.pack(side='left', fill='both', expand=True)
        top = composer_content
        ttk.Label(top, text='청월에게 어떤 일을 맡길까요?', style='CardTitle.TLabel').pack(anchor='w')
        self.goal = tk.Text(top, height=2, font=('Malgun Gothic', 12), wrap='word', relief='flat', bg='#f6f7fb', fg='#202636', padx=12, pady=10, highlightthickness=1, highlightbackground='#e5e8f0', highlightcolor='#7964db'); self.goal.pack(fill='x')
        goal_row = ttk.Frame(top, style='Card.TFrame'); goal_row.pack(fill='x', pady=4)
        ttk.Button(goal_row, text='淸月 CEO에게 맡기기', style='Primary.TButton', command=self.start).pack(side='right')
        ttk.Button(goal_row, text='파일 첨부', command=self.attach).pack(side='right', padx=6)
        ttk.Button(goal_row, text='부서 첨부', command=self.department_menu).pack(side='right')
        self.pending_departments = []          # department ids for the next goal (attached when it starts)
        self.composer_chips = ttk.Frame(goal_row, style='Card.TFrame'); self.composer_chips.pack(side='left')
        self.attached = []           # Owner input files for the next Goal (copied read-only when it starts)
        self.attached_label = ttk.Label(goal_row, text='', style='Card.TLabel'); self.attached_label.pack(side='right')

        body = ttk.PanedWindow(main, orient='horizontal'); body.pack(fill='both', expand=True)
        # Project list: short title + one colored status dot (a Listbox can only color whole rows).
        self.nav_buttons = {}
        for label, symbol in (('청월 홈', '⌂'), ('AI 동향', '◈'), ('AI 취업', '▤')):
            button = ttk.Button(holder, text=f'{symbol}   {label}', style='Selected.Nav.TButton' if label == '청월 홈' else 'Nav.TButton', command=lambda name=label: self.go_home(name))
            button.pack(fill='x', padx=10, pady=4)
            self.nav_buttons[label] = button
        ttk.Separator(holder).pack(fill='x', padx=16, pady=20)
        ttk.Label(holder, text='나의 프로젝트', style='Side.TLabel').pack(anchor='w', padx=18, pady=(0, 12))
        self.list = tk.Text(holder, font=LIST_FONT, width=1, wrap='none', cursor='arrow',
                            spacing1=8, spacing3=8, padx=LIST_PAD, state='disabled', relief='flat', borderwidth=0, bg='#eae6f5', fg='#56516b', highlightthickness=0)
        self.list.pack(fill='both', expand=True)
        for tag, color in INDICATOR_COLORS.items():
            self.list.tag_configure(tag, foreground=color)
        self.list.tag_configure('selected', background='#d7ceeb')
        self.list.bind('<Button-1>', self.select)
        # Widths change -> titles are re-fitted; hover shows the full title.
        self.list.bind('<Configure>', lambda _e: self.refresh_list(force=True))
        self.list.bind('<Motion>', self._tip)
        self.list.bind('<Leave>', lambda _e: self._tip(None))
        ttk.Button(holder, text='▣   결과물 라이브러리', style='Nav.TButton', command=self.library_window).pack(side='bottom', fill='x', padx=12, pady=16, before=self.list)
        self.department_specs, self.department_refused = departments.catalog()
        library_box = ttk.Frame(holder, style='Sidebar.TFrame')
        library_box.pack(side='bottom', fill='x', padx=12, before=self.list)
        ttk.Label(library_box, text='부서 라이브러리 · 끌어서 연결', style='Side.TLabel').pack(anchor='w', padx=6, pady=(8, 4))
        self.library_chips = {}
        for dep_id, spec in self.department_specs.items():
            chip = self._chip(library_box, spec, drag=True)
            chip.pack(anchor='w', padx=6, pady=3)
            self.library_chips[dep_id] = chip
        if self.department_refused:
            ttk.Label(library_box, text=f'명세 오류로 제외: {", ".join(self.department_refused)}', style='Side.TLabel',
                      wraplength=190).pack(anchor='w', padx=6)
        self.ids, self._rows, self._titles, self._tipwin = [], None, [], None
        self._labels = {}
        view = ttk.Frame(body)              # project view: status banner + panes
        self.banner = tk.Label(view, font=('Malgun Gothic', 11, 'bold'), anchor='w', justify='left', padx=10, pady=6)
        self.banner.pack(fill='x')
        self.project_departments = ttk.Frame(view)
        self.project_departments.pack(fill='x', pady=(4, 2))
        self._departments_shown = None
        # Wrap to the current width: fixed wraplengths cut the banner and the Owner note in narrow windows.
        view.bind('<Configure>', lambda e: (self.banner.config(wraplength=max(300, e.width - 24)),
                                            self.owner_note.config(wraplength=max(300, e.width - 40))))
        right = ttk.PanedWindow(view, orient='vertical')
        right.pack(fill='both', expand=True)
        body.add(view, weight=1)
        self.view = view
        self.right = right
        self.body = body
        self.home = Home(body, workspace)
        self.owner_box = ttk.LabelFrame(view, text='결과 확인 및 피드백', padding=16)
        self.owner_note = ttk.Label(self.owner_box, font=FONT, wraplength=820, justify='left')
        self.owner_note.pack(anchor='w')
        self.works_row = ttk.Frame(self.owner_box)
        self.run_button = ttk.Button(self.works_row, text='결과 실행', command=self.run_result)
        self.run_button.pack(side='left', padx=(0, 12))
        self.works = tk.StringVar(value='unknown')
        ttk.Label(self.works_row, text='실행해 보니:', font=FONT).pack(side='left')
        for label, value in (('작동함', 'yes'), ('작동하지 않음', 'no'), ('아직 확인 안 함', 'unknown')):
            ttk.Radiobutton(self.works_row, text=label, value=value, variable=self.works).pack(side='left', padx=4)
        self.feedback = tk.Text(self.owner_box, height=2, font=FONT, wrap='word', bg='#f5f3fa', padx=12, pady=10)
        self.decide_row = ttk.Frame(self.owner_box)
        for text, cmd in (('수정 요청 / 계속', self.owner_send), ('완료', self.owner_finish), ('중단', self.stop)):
            ttk.Button(self.decide_row, text=text, command=cmd).pack(side='left', padx=3)
        self.approve_row = ttk.Frame(self.owner_box)
        for text, cmd in (('외부 연결 승인', lambda: self.network(True)), ('외부 연결 거절', lambda: self.network(False))):
            ttk.Button(self.approve_row, text=text, command=cmd).pack(side='left', padx=3)
        self._owner_mode = None
        # Live execution view: project -> 淸月 CEO -> hired agents -> verification -> Owner review, read
        # from local state (supervisor status, heartbeat/activity files, SQLite) every refresh; no AI call.
        self.live = tk.Text(right, font=FONT, wrap='word', state='disabled', height=3, padx=14, pady=8, fg='#68718a')
        right.add(self.live, weight=0)
        graph = ttk.Frame(right)
        self.pipeline = tk.Canvas(graph, height=105, background='#ffffff', highlightthickness=0)
        self.pipeline.pack(fill='x')
        scroll = ttk.Scrollbar(graph, orient='horizontal', command=self.pipeline.xview)
        scroll.pack(fill='x')
        self.pipeline.configure(xscrollcommand=scroll.set)
        right.add(graph, weight=0)
        self._pipeline_signature = None
        # Agents and their records side by side: stacked, they shared the leftover height and the table collapsed.
        lower = ttk.PanedWindow(right, orient='horizontal')
        right.add(lower, weight=1)
        agent_box = ttk.Frame(lower, style='Card.TFrame')
        self.agents = ttk.Treeview(agent_box, columns=tuple(COLUMNS), show='tree headings', height=8, selectmode='browse')
        agent_box.rowconfigure(0, weight=1)
        agent_box.columnconfigure(0, weight=1)
        self.agents.grid(row=0, column=0, sticky='nsew')
        yscroll = ttk.Scrollbar(agent_box, orient='vertical', command=self.agents.yview)
        yscroll.grid(row=0, column=1, sticky='ns')
        xscroll = ttk.Scrollbar(agent_box, orient='horizontal', command=self.agents.xview)
        xscroll.grid(row=1, column=0, sticky='ew')
        self.agents.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.agents.heading('#0', text='Agent')
        self.agents.column('#0', width=230, stretch=False)
        for col, (title, width) in COLUMNS.items():
            self.agents.heading(col, text=title)
            self.agents.column(col, width=width, stretch=col in ('why', 'result'))
        self.agents['displaycolumns'] = ('engine', 'task', 'status')     # the rest is in Agent 기록
        self.agents.bind('<<TreeviewSelect>>', lambda _e: self.show())
        lower.add(agent_box, weight=1)
        tabs = ttk.Notebook(lower)
        lower.add(tabs, weight=1)
        self.records = RecordText(tabs, font=FONT, wrap='word', state='disabled')
        self.timeline = RecordText(tabs, font=FONT, wrap='word', state='disabled')
        self.detail = RecordText(tabs, font=FONT, wrap='word', state='disabled')
        for widget, title in ((self.records, 'Agent 기록'), (self.timeline, '타임라인'), (self.detail, '프로젝트')):
            tabs.add(widget, text=title)

        bar = ttk.Frame(main, padding=(0, 10)); bar.pack(fill='x', side='bottom', before=body)   # never clipped
        actions = ttk.Menubutton(bar, text='프로젝트 관리 ▾')
        actions.pack(side='left')
        menu = tk.Menu(actions, tearoff=False)
        actions.configure(menu=menu)
        for text, cmd in (('Library', self.library_window), ('리뷰 / 피드백…', self.review_dialog),
                          ('외부 연결 승인', lambda: self.network(True)),
                          ('외부 연결 거절', lambda: self.network(False)),
                          ('계속 실행 / 재개', self.resume), ('중단', self.stop), ('프로젝트 종료…', self.finish),
                          ('폴더 열기', self.open_folder)):
            menu.add_command(label=text, command=cmd)
        self.status = ttk.Label(bar, text=''); self.status.pack(side='right')
        self.protocol('WM_DELETE_WINDOW', self.quit_app)
        body.forget(view)
        body.add(self.home, weight=1)
        self.refresh()
        if goal:
            self.goal.insert('1.0', goal)
            self.after(500, self.start)
        elif resume:                     # same as selecting the project and pressing 계속 실행 / 재개
            self.selected = resume
            self.open_project()
            self.after(500, self.resume)
        elif open_id:                    # only shows that project's view; never runs or resumes it
            self.selected = open_id
            self.open_project()

    # ---- project workers
    def _launch(self, pid):
        """A run is its own background process, so closing this window never stops it; the window only
        reads its state. (In-window threads are kept for injected test engines.)"""
        if pid == self.selected:
            self.open_project()       # one path for start / resume / develop / rework: the project the Owner acts on
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

    def attach(self):
        from tkinter import filedialog
        files = filedialog.askopenfilenames(title='Goal에 사용할 파일 (데이터로만 사용, 지시로 따르지 않음)')
        self.attached = list(dict.fromkeys([*self.attached, *files]))
        self.attached_label.config(text=f"첨부 {len(self.attached)}개: " + ', '.join(Path(f).name for f in self.attached)[:80]
                                   if self.attached else '')

    def start(self):
        goal = self.goal.get('1.0', 'end').strip()
        if not goal:
            return
        if self.attached:      # check the files before a project exists, so a bad file never leaves a half project
            from .artifacts import validate_inputs
            try:
                validate_inputs(self.attached)
            except ValueError as e:
                messagebox.showerror('AX Branch', str(e))
                return
        self.selected = self.store.new_project(goal)
        self._owner_action('new')
        for dep_id in self.pending_departments:      # function connections only; Owner approvals are unchanged
            departments.attach(self.store, self.selected, dep_id, self.department_specs)
        self.pending_departments = []
        self._render_composer_departments()
        if self.attached:
            engine = self.engine_factory()
            try:
                engine.attach_inputs(self.selected, self.attached)
            except (ValueError, OSError) as e:      # e.g. a file changed after it was checked: do not run without it
                messagebox.showerror('AX Branch', f'첨부 실패 — 프로젝트를 실행하지 않았습니다: {e}')
                return
            finally:
                engine.store.close()
            self.attached = []
            self.attached_label.config(text='')
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
                self.owner_box.pack_forget()
            if mode is not None:
                # Packed above the panes, never inside them: a pane was squeezed until its buttons vanished.
                self.owner_box.pack(fill='x', before=self.right, padx=0, pady=(0, 4))
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

    # ---- Artifact Library: what was made, its current version, and Develop
    def library_window(self):
        """Completed artifacts by type. Each shows its current version; its versions (one per project in its
        lineage) are listed under it. Actions: 보기/실행, Develop (a goal only), 관련 프로젝트."""
        win = tk.Toplevel(self)
        win.title('AX Branch — Library')
        win.geometry('860x520')
        tree = ttk.Treeview(win, columns=('version', 'status', 'updated'), show='tree headings', selectmode='browse')
        tree.heading('#0', text='결과물')
        tree.column('#0', width=420)
        for col, text, width in (('version', '버전', 80), ('status', '검증', 70), ('updated', '업데이트', 140)):
            tree.heading(col, text=text)
            tree.column(col, width=width, stretch=False)
        rows = {}
        items = library.entries(self.store)
        for kind in library.TYPES:
            group = [e for e in items if e['type'] == kind]
            if not group:
                continue
            parent = tree.insert('', 'end', text=f'{kind} ({len(group)})', open=True)
            for e in group:
                node = tree.insert(parent, 'end', text=e['title'], values=(
                    f"v{e['version']}", e['verification'], time.strftime('%Y-%m-%d %H:%M', time.localtime(e['updated']))))
                rows[node] = (e, e['project'])
                for v in reversed(e['versions']):
                    child = tree.insert(node, 'end', text=f"v{v['version']} ← {v['project']}  {v['goal'][:50]}",
                                        values=(f"v{v['version']}", '', ''))
                    rows[child] = (e, v['project'])
        row = ttk.Frame(win, padding=6)
        row.pack(fill='x', side='bottom')
        act = ttk.Button(row, text='보기', command=lambda: self._library_open(rows.get(tree.focus())))
        act.pack(side='left', padx=3)
        ttk.Button(row, text='Develop', command=lambda: self._develop_dialog(rows.get(tree.focus()), win)).pack(side='left', padx=3)
        ttk.Button(row, text='관련 프로젝트', command=lambda: self._library_project(rows.get(tree.focus()), win)).pack(side='left', padx=3)
        ttk.Label(row, text='결과물을 고르고 보기/실행하거나, Develop으로 새 목표를 이어서 맡기세요.', font=FONT).pack(side='left', padx=12)

        def relabel(_e=None):
            picked = rows.get(tree.focus())
            act.config(text='실행' if picked and picked[0]['type'] == 'Apps' else '보기')
        tree.bind('<<TreeviewSelect>>', relabel)
        tree.pack(fill='both', expand=True, padx=6, pady=6)
        win.tree, win.rows = tree, rows
        self._library = win
        return win

    def _library_open(self, picked):
        if not picked:
            return
        engine = self.engine_factory()
        try:
            engine.open_result(picked[1], show_text=self.show_text)
        except Exception as e:
            messagebox.showwarning('AX Branch', str(e))
        finally:
            engine.store.close()

    def _library_project(self, picked, win):
        if picked:
            self.selected = picked[1]
            self._rows = None
            self.refresh_list()
            self.open_project()
            win.destroy()

    def _develop_dialog(self, picked, win):
        """Develop: the Owner gives only the new goal; 淸月 CEO takes it from there (knowledge, agents, engines,
        verification). The new project starts from the selected artifact's current version."""
        if not picked:
            messagebox.showinfo('AX Branch', 'Develop할 결과물을 고르세요.', parent=win)
            return
        entry, base = picked                              # the version row the Owner picked (default: current)
        version = next((v['version'] for v in entry['versions'] if v['project'] == base), entry['version'])
        dlg = tk.Toplevel(win)
        dlg.title(f"Develop — {entry['title']} v{version}")
        ttk.Label(dlg, text=f"'{entry['title']}' v{version}을 바탕으로 이어서 할 일을 적어 주세요.",
                  font=FONT, padding=(10, 8)).pack(anchor='w')
        goal = tk.Text(dlg, height=5, width=70, font=FONT, wrap='word')
        goal.pack(padx=10, fill='x')

        def start():
            text = goal.get('1.0', 'end').strip()
            if not text:
                return
            pid = self.develop(base, text)
            if pid:
                dlg.destroy()
                win.destroy()
        ttk.Button(dlg, text='淸月 CEO에게 맡기기', command=start).pack(anchor='e', padx=10, pady=8)
        dlg.goal, dlg.start = goal, start
        self._develop = dlg

    def develop(self, base_pid, goal):
        engine = self.engine_factory()
        try:
            pid = engine.develop(base_pid, goal)
        except Exception as e:
            messagebox.showwarning('AX Branch', str(e))
            return None
        finally:
            engine.store.close()
        self.store.event(pid, 'owner_action', action='develop', channel='app')
        self.selected = pid
        self._rows = None
        self._launch(pid)
        return pid

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

    # ---- departments: library chips, drag/drop or [프로젝트에 추가], attached chips (persisted as project events)
    def _chip(self, parent, spec, drag=False, remove=None):
        frame = tk.Frame(parent, bg='#ddd5f3', padx=8, pady=3, cursor='hand2' if drag else 'arrow')
        label = tk.Label(frame, text=f"▣ {spec['name']}", bg='#ddd5f3', fg='#3f3863', font=('Malgun Gothic', 9, 'bold'))
        label.pack(side='left')
        if remove is not None:
            tk.Button(frame, text='✕', bd=0, bg='#ddd5f3', fg='#6b6290', activebackground='#cfc5ec',
                      command=remove, cursor='hand2').pack(side='left', padx=(6, 0))
        if drag:
            for w in (frame, label):
                w.bind('<ButtonPress-1>', lambda e, d=spec['id']: setattr(self, '_drag', (d, e.x_root, e.y_root)))
                w.bind('<ButtonRelease-1>', lambda e: self._drop(e.x_root, e.y_root))
        frame.department = spec['id']
        return frame

    def _drop(self, x, y):
        """Release of a library chip: dropped on the composer -> pending for the next goal; on the project view ->
        attached to that project; a click without moving opens the department's details."""
        dep_id, x0, y0 = getattr(self, '_drag', (None, x, y))
        self._drag = None
        if dep_id is None:
            return
        if abs(x - x0) < 6 and abs(y - y0) < 6:
            return self.department_detail(dep_id)
        target = self.winfo_containing(x, y)
        while target is not None and target not in (self.composer, self.view):
            target = target.master
        if target is self.composer:
            self.add_department(dep_id, to_project=False)
        elif target is self.view and not self.home_mode:
            self.add_department(dep_id, to_project=True)
        else:   # missed, or the spot is covered by another window (the hit test then finds no AX Branch widget)
            messagebox.showinfo('AX Branch', f"연결되지 않았습니다: {self.department_specs[dep_id]['name']}\n"
                                '놓은 곳이 프로젝트 화면이나 목표 입력창이 아니었습니다(다른 창에 가려졌을 수 있음). '
                                '부서를 클릭해 상세 화면의 [프로젝트에 추가]를 사용하세요.')

    def department_menu(self):
        menu = tk.Menu(self, tearoff=False)
        for dep_id, spec in self.department_specs.items():
            menu.add_command(label=f"{spec['name']} — {', '.join(spec['provides'][:2])}",
                             command=lambda d=dep_id: self.add_department(d, to_project=False))
        menu.tk_popup(self.winfo_pointerx(), self.winfo_pointery())

    def add_department(self, dep_id, to_project):
        if to_project:
            if not self.selected:
                return
            try:
                departments.attach(self.store, self.selected, dep_id, self.department_specs)
            except departments.Rejected as e:
                messagebox.showinfo('AX Branch', str(e))
            self._departments_shown = None
            self.show()
        elif dep_id in self.pending_departments:
            messagebox.showinfo('AX Branch', f"이미 첨부한 부서입니다: {self.department_specs[dep_id]['name']}")
        else:
            self.pending_departments.append(dep_id)
            self._render_composer_departments()

    def remove_department(self, dep_id, from_project):
        if from_project and self.selected:
            departments.detach(self.store, self.selected, dep_id)
            self._notice[0] = '부서 해제: 다음 위임부터 적용 (실행 중인 단계는 끝까지 진행, 기록은 보존)'
            self._departments_shown = None
            self.show()
        else:
            self.pending_departments.remove(dep_id)
            self._render_composer_departments()

    def _render_composer_departments(self):
        for w in self.composer_chips.winfo_children():
            w.destroy()
        for dep_id in self.pending_departments:
            self._chip(self.composer_chips, self.department_specs[dep_id],
                       remove=lambda d=dep_id: self.remove_department(d, False)).pack(side='left', padx=(0, 6))

    def _render_project_departments(self):
        ids = [d['id'] for d in departments.attached(self.store, self.selected)] if self.selected else []
        if ids == self._departments_shown:
            return
        self._departments_shown = ids
        for w in self.project_departments.winfo_children():
            w.destroy()
        ttk.Label(self.project_departments, text='연결된 부서' if ids else
                  '연결된 부서 없음 · 라이브러리에서 끌어 놓으면 연결됩니다 (기능 연결일 뿐, 결제·게시 등 승인은 그대로)',
                  style='Muted.TLabel').pack(side='left', padx=(2, 10))
        for dep_id in ids:
            spec = self.department_specs.get(dep_id) or {'id': dep_id, 'name': f'{dep_id} (라이브러리에 없음)'}
            self._chip(self.project_departments, spec,
                       remove=lambda d=dep_id: self.remove_department(d, True)).pack(side='left', padx=(0, 6))

    def department_detail(self, dep_id):
        spec = self.department_specs[dep_id]
        win = tk.Toplevel(self); win.title(f"부서 — {spec['name']}")
        text = scrolledtext.ScrolledText(win, width=70, height=18, font=FONT, wrap='word')
        text.pack(fill='both', expand=True, padx=10, pady=10)
        perm = spec['permissions']
        text.insert('1.0', '\n'.join([
            f"{spec['name']}  (id {spec['id']}, v{spec['version']})", '', f"역할: {spec['role']}",
            f"제공 기능: {', '.join(spec['provides'])}", f"담당 에이전트: {spec['agent']['role']}",
            f"사용 도구: {', '.join(spec['tools'])}", f"입력: {', '.join(spec['inputs'])}",
            f"결과: {', '.join(spec['outputs'])}", f"참조 자료: {', '.join(spec['knowledge'])}",
            f"권한: 읽기 {perm['read']} · 쓰기 {perm['write']} · 네트워크 {'예' if perm['network'] else '아니오'} · shell 아니오",
            '검수 기준:', *[f'  - {c}' for c in spec['acceptance_criteria']], '',
            '연결은 기능 연결입니다. 결제·credential·외부 게시·고객 연락 등은 별도 Owner 승인이 필요합니다.']))
        text.configure(state='disabled')
        row = ttk.Frame(win, padding=8); row.pack(fill='x')
        ttk.Button(row, text='프로젝트에 추가', command=lambda: (self.add_department(dep_id, not self.home_mode),
                                                         win.destroy())).pack(side='right')
        win.department = dep_id                     # reachable by tests

    # ---- display
    def go_home(self, category='청월 홈'):
        for name, button in self.nav_buttons.items():
            button.configure(style='Selected.Nav.TButton' if name == category else 'Nav.TButton')
        self.composer.pack(fill='x', pady=(0, 16), before=self.body)
        self.page_title.config(text='워크스페이스  /  ' + category)
        self.home_mode = True
        if str(self.view) in self.body.panes():
            self.body.forget(self.view)
            self.body.add(self.home, weight=1)
        self.home.render(None if category == '청월 홈' else category)
        self.home.update_state(self.store.projects())

    def open_project(self):
        for button in self.nav_buttons.values():
            button.configure(style='Nav.TButton')
        self.composer.pack_forget()
        self.page_title.config(text='워크스페이스  /  실행 파이프라인')
        self.home_mode = False
        if str(self.home) in self.body.panes():
            self.body.forget(self.home)
            self.body.add(self.view, weight=1)
        self.show()

    def select_pipeline(self, key):
        if self.agents.exists(key):
            self.agents.selection_set(key)
            self.agents.see(key)
            self.show()

    def select(self, event=None):
        line = int(self.list.index(f'@{event.x},{event.y}').split('.')[0]) - 1 if event else -1
        if 0 <= line < len(self.ids):
            self.selected = self.ids[line]
            self._rows = None                             # redraw the highlight
            self.refresh_list()
            self.open_project()
        return 'break'

    def refresh_list(self, force=False):
        """Titles with a status dot. The exact internal state stays in the project view on the right."""
        projects = self.store.projects()
        watch = supervisor.candidates(self.store)
        labels = {p['id']: supervisor.status(self.workspace, self.store, p['id'])['status'] for p in projects}
        self._statuses = labels
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
        self._update_orb()
        self.show()
        self.status.config(text=self._notice[0] or f'실행 중 {len(self.running)}건')
        if time.monotonic() - self._last_supervision > 30:
            self._last_supervision = time.monotonic()
            self.supervise()
        if getattr(self, '_tick', None):         # one refresh loop only: a direct refresh() call never adds a second
            self.after_cancel(self._tick)
        self._tick = self.after(1500, self.refresh)

    def _save_motion(self):
        try:
            self.settings_path.parent.mkdir(parents=True, exist_ok=True)
            self.settings_path.write_text(json.dumps({'motion_off': self.motion_off.get()}), encoding='utf-8')
        except OSError:
            pass                                       # the setting still applies for this session
        self._update_orb()

    def _update_orb(self):
        statuses = getattr(self, '_statuses', {})
        state = orb_state([(p['state'], statuses.get(p['id'], ''),
                            self.store.project(p['id'])['pause_reason'] if p['state'] == 'PAUSED' else None)
                           for p in self.store.projects()])
        self.orb.set_state(state, motion=not self.motion_off.get())
        if self.orb_label.cget('text') != ORB_LABELS[state]:
            self.orb_label.config(text=ORB_LABELS[state])

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
        self.home.update_state(self.store.projects())
        if self.home_mode:
            return
        if not self.selected:
            return
        h = self.store.handoff(self.selected)
        p = self.store.project(self.selected)
        lines = [f"[{h['project_id']}] {h['state']}" + (f"  ⏸ {h['pause_reason']}" if h['pause_reason'] else ''),
                 f"Goal: {h['goal']}", f"다음: {h['next_action']}"]
        lines.append('')
        view = live.view(self.workspace, self.store, self.selected)
        self._render_project_departments()
        status = dict(view['header'])['상태'].split(' — ')[0]
        text, color = banner(p['state'], status, p['pause_reason'] or '')
        if self.banner.cget('text') != text:
            self.banner.config(text=text, bg=color)
        self._owner_panel(p, status)
        header = dict(view['header'])
        _put(self.live, f"{project_title(p)}\n현재 작업  {header.get('현재 작업', '기록 확인')}\n"
             '에이전트를 선택하면 작업 내용과 검증 근거를 볼 수 있습니다.')
        rows = {r['key']: r for r in view['pipeline']}
        signature = repr(view['pipeline'])
        if signature != self._pipeline_signature:
            self._pipeline_signature = signature
            draw_pipeline(self.pipeline, view['pipeline'], self.select_pipeline)
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


def banner(state, status, reason=''):
    """(text, background) for the project view: what the project is doing, and WHEN Owner input takes effect.
    Never claims that input is applied while a run is in progress (feedback is not queued during a run)."""
    if state == 'CLOSED' or status == 'COMPLETED':
        return '완료 · 종료된 프로젝트입니다. 기록과 결과만 볼 수 있습니다.', '#e5e8ec'
    if status == 'WAITING_FOR_OWNER':
        if 'approval needed' in reason:
            return '승인 대기 · [외부 연결 승인/거절]을 누르는 즉시 결정이 기록되고, 이어서 실행할 수 있습니다.', '#ffe3b3'
        if state == 'OWNER_REVIEW':
            return '검토 대기 · 검증을 통과한 결과가 도착했습니다. [결과 실행]으로 확인하고, 의견은 보낼 때 반영됩니다.', '#d4f0e4'
        return '결정 대기 · 프로젝트가 멈춰 Owner를 기다립니다. 적은 방향은 [수정 요청 / 계속]을 누를 때 반영됩니다.', '#ffe3b3'
    if status in ('STALLED', 'FAILED') and state != 'CREATED':
        return '오류 · 실행이 멈췄습니다. 아래 상태와 타임라인에서 원인을 확인한 뒤 [계속 실행 / 재개]하세요.', '#ffd6d1'
    if status in ('ACTIVE', 'RECOVERING'):
        return ('작업 중 · 지금은 피드백이 반영되지 않습니다. 결과가 검토 단계에 도착하면 입력하거나, '
                '[중단] 후 입력하세요.', '#d7e6ff')
    if state == 'PAUSED':
        return f'일시중지 · {reason[:140] or "재개를 기다립니다"}', '#fff1cc'
    return '대기 · 아직 실행되지 않았습니다.', '#eef1f5'


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


LIST_WIDTH, LIST_PAD, LIST_FONT = 224, 16, ('Malgun Gothic', 10)


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


def main(goal=None, resume=None, open_id=None):
    App(goal=goal, resume=resume, open_id=open_id).mainloop()

