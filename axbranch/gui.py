"""Minimal Owner window. The engine runs in worker threads with their own SQLite
connection; this window only reads the database on a timer, so it never blocks
and always shows the persisted truth."""
import os
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext, simpledialog, ttk

from . import WORKSPACE, __version__
from .engine import activity, open_engine
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
        for text, cmd in (('작동함', lambda: self.review('works')), ('문제 있음…', lambda: self.review('problem')),
                          ('수정 요청…', lambda: self.review('change')),
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

    def review(self, verdict, text=None):
        """Owner's verdict on a delivered artifact. Problem/change reopen the same project and rebuild it."""
        if not self.selected:
            return
        if verdict != 'works' and text is None:
            prompt = ('무엇이 작동하지 않나요? 어떻게 실행했고 무엇이 보였는지 적어 주세요.' if verdict == 'problem'
                      else '무엇을 바꾸고 싶은지 적어 주세요.')
            text = simpledialog.askstring('AX Branch — Owner review', prompt, parent=self)
            if not text:
                return
        engine = self.engine_factory()
        try:
            p = engine.owner_review(self.selected, verdict, text or '')
        except Exception as e:
            messagebox.showwarning('AX Branch', str(e))
            return
        finally:
            engine.store.close()
        if p['state'] == 'REWORK':
            self._launch(self.selected)

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
            win.destroy(); engine.store.close()
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
        self._tick = self.after(1500, self.refresh)

    def show(self):
        if not self.selected:
            return
        h = self.store.handoff(self.selected)
        p = self.store.project(self.selected)
        lines = [f"[{h['project_id']}] {h['state']}" + (f"  ⏸ {h['pause_reason']}" if h['pause_reason'] else ''),
                 f"Goal: {h['goal']}", f"다음: {h['next_action']}"]
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

