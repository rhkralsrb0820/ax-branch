"""Minimal Owner window. The engine runs in worker threads with their own SQLite
connection; this window only reads the database on a timer, so it never blocks
and always shows the persisted truth."""
import gc
import os
import threading
import time
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

from . import WORKSPACE, __version__
from .engine import activity, liveness, open_engine
from .state import Busy, Store

FONT = ('Malgun Gothic', 10)


class App(tk.Tk):
    def __init__(self, workspace=WORKSPACE, engine_factory=None, goal=None, resume=None):
        """engine_factory: callable returning a fresh Engine (own SQLite connection) — tests
        inject one; goal: pre-filled and submitted once the window is up (`--goal`)."""
        super().__init__()
        self.workspace = workspace
        self.engine_factory = engine_factory or (lambda: open_engine(workspace))
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
        self.list = tk.Listbox(body, font=FONT, width=48, activestyle='none')
        self.list.bind('<<ListboxSelect>>', self.select)
        body.add(self.list, weight=1)
        self.detail = scrolledtext.ScrolledText(body, font=FONT, wrap='word', state='disabled')
        body.add(self.detail, weight=3)

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

    # ---- engine threads
    def _launch(self, pid):
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
            if p['resume_state'] in ('PENDING_CLOSE', 'ARCHIVE_PENDING_APPROVAL'):
                self.store.resume(self.selected)
                return
            extra = 3 if 'not lowered' in (p['pause_reason'] or '') else 0
            self.store.resume(self.selected, extra)
        self._launch(self.selected)

    def stop(self):
        if self.selected in self.running:
            self.running[self.selected].set()

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
        if p['state'] == 'REWORK':
            self._launch(self.selected)
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

        def choose(choice):
            confirm = False
            if choice == 'discard':
                confirm = messagebox.askyesno('확인', '저장하지 않고 닫으면 이 프로젝트의 지식과 Agent 컨텍스트가 '
                                              '영구히 버려집니다. 계속할까요?', parent=win)
                if not confirm:
                    return
            try:
                engine.close(p['id'], choice, confirm, sat.get())
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
    def select(self, _event=None):
        sel = self.list.curselection()
        if sel:
            self.selected = self.ids[sel[0]]
            self.show()

    def refresh(self):
        projects = self.store.projects()
        self.ids = [p['id'] for p in projects]
        rows = [f"{'▶ ' if p['id'] in self.running else '  '}{p['state']:<12} {p['goal'][:40]}" for p in projects]
        if rows != list(self.list.get(0, 'end')):
            self.list.delete(0, 'end')
            for i, row in enumerate(rows):
                self.list.insert('end', row)
                if self.ids[i] == self.selected:
                    self.list.selection_set(i)
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
        label, detail = liveness(self.workspace, self.store, self.selected)
        lines.append(f"상태: [{label}] {detail}")
        a = activity(self.workspace, self.selected)
        if a:
            lines.append(f"▶ 진행 중: {a['agent']} · {a.get('provider')} (CLI pid {a.get('pid', '-')}) · 경과 {a.get('elapsed', 0)}초 · "
                         f"출력 {a.get('output_bytes', 0)}B · 마지막 출력 {a.get('idle', 0)}초 전"
                         + (' (Claude는 완료 시에만 출력)' if a.get('provider') == 'claude' else ''))
        lines.append('')
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
        lines += ['', '■ 기록'] + [f"  {e['kind']}: {_brief(e['detail'])}" for e in self.store.events(self.selected)[-25:]]
        text = '\n'.join(lines)
        if text != self.detail.get('1.0', 'end-1c'):
            self.detail.config(state='normal'); self.detail.delete('1.0', 'end')
            self.detail.insert('1.0', text); self.detail.config(state='disabled')

    def destroy(self):
        if getattr(self, '_tick', None):
            self.after_cancel(self._tick)       # no refresh callback firing into a destroyed window
        self.store.close()
        super().destroy()
        gc.collect()                            # same reason: never let a worker thread free Tk objects

    def quit_app(self):
        if self.running and not messagebox.askyesno('AX Branch', '실행 중인 프로젝트가 있습니다. 중단하고 닫을까요? '
                                                    '(상태는 저장되어 다음에 재개할 수 있습니다)'):
            return
        for cancel in self.running.values():
            cancel.set()
        self.destroy()


def _brief(detail):
    return ', '.join(f'{k}={str(v)[:80]}' for k, v in detail.items())


def main(goal=None, resume=None):
    App(goal=goal, resume=resume).mainloop()

