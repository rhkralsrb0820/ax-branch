"""Right-hand development pane: what Claude Code, Codex and AX Branch workers are ACTUALLY doing.

    devteam\\devview.cmd        (opens this pane on the right half of the screen)

It is an observability surface, not a control surface: nothing here needs input. It reads only local
state — the Windows process table and CPU times, devteam/live/ (written by delegate.py) and the
AX Branch SQLite/activity files — and never calls an LLM. delegate.py opens it automatically when it
hands a task to Codex and no pane is open.
"""
import ctypes
import json
import os
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LIVE = REPO / 'devteam' / 'live'
PANE_PID = LIVE / 'pane.pid'
REFRESH = 3            # s
CPU_ACTIVE = 0.15      # CPU seconds per refresh above which a process counts as ACTIVE

k32 = ctypes.WinDLL('kernel32', use_last_error=True) if os.name == 'nt' else None


class _Entry(ctypes.Structure):
    _fields_ = [('dwSize', wintypes.DWORD), ('cntUsage', wintypes.DWORD), ('th32ProcessID', wintypes.DWORD),
                ('th32DefaultHeapID', ctypes.c_void_p), ('th32ModuleID', wintypes.DWORD),
                ('cntThreads', wintypes.DWORD), ('th32ParentProcessID', wintypes.DWORD),
                ('pcPriClassBase', ctypes.c_long), ('dwFlags', wintypes.DWORD), ('szExeFile', ctypes.c_wchar * 260)]


def processes():
    """{pid: (parent pid, exe name lower-case)} from one Toolhelp snapshot."""
    k32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
    snap = k32.CreateToolhelp32Snapshot(2, 0)
    entry, table = _Entry(), {}
    entry.dwSize = ctypes.sizeof(_Entry)
    try:
        ok = k32.Process32FirstW(ctypes.c_void_p(snap), ctypes.byref(entry))
        while ok:
            table[entry.th32ProcessID] = (entry.th32ParentProcessID, entry.szExeFile.lower())
            ok = k32.Process32NextW(ctypes.c_void_p(snap), ctypes.byref(entry))
    finally:
        k32.CloseHandle(ctypes.c_void_p(snap))
    return table


def _open(pid):
    k32.OpenProcess.restype = ctypes.c_void_p
    return k32.OpenProcess(0x1000, False, pid)          # PROCESS_QUERY_LIMITED_INFORMATION


def alive(pid):
    h = _open(int(pid or 0))
    if not h:
        return False
    code = wintypes.DWORD()
    try:
        return bool(k32.GetExitCodeProcess(ctypes.c_void_p(h), ctypes.byref(code))) and code.value == 259
    finally:
        k32.CloseHandle(ctypes.c_void_p(h))


def cpu_seconds(pid):
    h = _open(pid)
    if not h:
        return 0.0
    times = [wintypes.FILETIME() for _ in range(4)]
    try:
        k32.GetProcessTimes(ctypes.c_void_p(h), *[ctypes.byref(t) for t in times])
    finally:
        k32.CloseHandle(ctypes.c_void_p(h))
    return sum((t.dwHighDateTime << 32 | t.dwLowDateTime) for t in times[2:]) / 1e7


def _tree(table, roots):
    """roots plus all their descendants."""
    found, frontier = set(roots), list(roots)
    while frontier:
        parent = frontier.pop()
        for pid, (ppid, _) in table.items():
            if ppid == parent and pid not in found:
                found.add(pid); frontier.append(pid)
    return found


def _ancestors(table, pid):
    seen = []
    while pid in table and pid not in seen and len(seen) < 64:
        seen.append(pid); pid = table[pid][0]
    return seen[1:]


def ensure_pane():
    """Open the pane in its own console window unless one is already open (never two)."""
    LIVE.mkdir(parents=True, exist_ok=True)
    try:
        if alive(int(PANE_PID.read_text())):
            return
    except (OSError, ValueError):
        pass
    subprocess.Popen([sys.executable, '-X', 'utf8', str(Path(__file__))], cwd=str(REPO),
                     creationflags=subprocess.CREATE_NEW_CONSOLE)


def _dock_right():
    """Put this console on the right half of the work area (Claude Code stays on the left)."""
    hwnd = k32.GetConsoleWindow()
    rect = wintypes.RECT()
    if hwnd and ctypes.windll.user32.SystemParametersInfoW(0x30, 0, ctypes.byref(rect), 0):    # SPI_GETWORKAREA
        half = (rect.right - rect.left) // 2
        ctypes.windll.user32.MoveWindow(hwnd, rect.left + half, rect.top, half, rect.bottom - rect.top, True)


def _age(seconds):
    seconds = int(seconds)
    return f'{seconds // 60}m {seconds % 60:02d}s' if seconds >= 60 else f'{seconds}s'


class Board:
    def __init__(self):
        self.cpu = {}

    def _active(self, pids):
        """CPU used by these processes since the previous refresh (real work, not 'process exists')."""
        used = 0.0
        for pid in pids:
            now = cpu_seconds(pid)
            used += max(0.0, now - self.cpu.get(pid, now))
            self.cpu[pid] = now
        return used

    def projects(self):
        """AX Branch project workers with a live or stalled run, from local state only."""
        from axbranch import WORKSPACE, supervisor
        from axbranch.state import Store
        store = Store(WORKSPACE / 'axbranch.sqlite3')
        try:
            return [supervisor.status(WORKSPACE, store, pid) for pid in supervisor.candidates(store)]
        finally:
            store.close()

    def render(self):
        table = processes()
        workers = self.projects()
        provider_trees = _tree(table, [r['worker_pid'] for r in workers if r.get('worker_pid')])
        # Claude Code CLI = claude.exe not started by an AX Branch worker (those are project providers).
        dev_claude = [pid for pid, (_, exe) in table.items() if exe == 'claude.exe' and pid not in provider_trees
                      and not any(table.get(a, (0, ''))[1] == 'python.exe' for a in _ancestors(table, pid))]
        claude_cpu = self._active(dev_claude)
        out = [f"AX Branch development view · {time.strftime('%H:%M:%S')} · local state only, no AI calls", '']
        out.append(f"CLAUDE CODE (dev CLI, left)   {'ACTIVE' if claude_cpu > CPU_ACTIVE else 'IDLE'}"
                   f"   ({len(dev_claude)} process(es), CPU {claude_cpu:.2f}s / {REFRESH}s)")
        try:
            job = json.loads((LIVE / 'codex.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            job = None
        if job and job.get('state') == 'codex' and alive(job.get('pid')):
            cpu = self._active(_tree(table, [job['pid']]))
            out.append(f"CODEX CLI (dev, this pane)    ACTIVE   task {job['task']} · {_age(time.time() - job['started'])}"
                       f" · CPU {cpu:.2f}s / {REFRESH}s")
        elif job and job.get('state') == 'host tests':
            out.append(f"CODEX CLI (dev, this pane)    IDLE     LOCAL — host running acceptance tests for {job['task']}")
        else:
            last = f"   last: {job['task']} → {job.get('result')}" if job and job.get('result') else ''
            out.append(f'CODEX CLI (dev, this pane)    IDLE{last}')
        out.append('')
        out.append('AX BRANCH PROJECT WORKERS (provider calls made by projects, not development):')
        for r in workers or []:
            line = f"  {r['project']}  [{r['status']}] {r['stage']}"
            if r['status'] == 'ACTIVE' and r.get('call_elapsed') is not None:
                line += (f" · {r['agent']} on {r['provider']} (pid {r.get('provider_pid')}) · "
                         f"{_age(r['call_elapsed'])} / {_age(r['call_timeout'])}")
            else:
                line += f" · {r['reason'][:90]}"
            out.append(line)
        if not workers:
            out.append('  none running')
        out += ['', '─' * 78, 'CODEX OUTPUT (devteam/live/codex.log):', '']
        try:
            lines = (LIVE / 'codex.log').read_text(encoding='utf-8', errors='replace').splitlines()
        except OSError:
            lines = ['(no Codex task yet)']
        out += [line[:160] for line in lines[-40:]]
        return '\n'.join(out)


def main():
    LIVE.mkdir(parents=True, exist_ok=True)
    PANE_PID.write_text(str(os.getpid()))
    os.system('')                      # enable ANSI clear-screen on Windows consoles
    ctypes.windll.kernel32.SetConsoleTitleW('CODEX CLI — AX Branch development (observe only)')
    _dock_right()
    sys.path.append(str(REPO))
    board = Board()
    while True:
        try:
            text = board.render()
        except Exception as e:         # an observability pane must never die on a bad read
            text = f'devview: {type(e).__name__}: {e}'
        sys.stdout.write('\x1b[2J\x1b[H' + text + '\n')
        sys.stdout.flush()
        time.sleep(REFRESH)


if __name__ == '__main__':
    main()
