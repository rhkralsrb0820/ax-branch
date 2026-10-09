"""D-AUTO-1: supervision without the window and without an LLM.

A Windows Task Scheduler entry (at logon + every 5 minutes, one instance at a time) runs the existing
deterministic pass `axbranch supervise` and exits. That pass applies the same recovery rules as the window
(supervisor.supervise: stage-correct resume, bounded attempts, no duplicate worker, NEEDS_DECISION) and then
tells the Owner once, with a Windows notification, when a project starts waiting for them (OWNER_REVIEW or
a decision). Registered and removed only by the Owner (`axbranch autostart on|off`).
"""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

TASK = 'AX Branch Supervisor'
INTERVAL_MINUTES = 5
_NO_WINDOW = 0x08000000


def _action():
    """(command, arguments, working directory) of one headless supervision pass."""
    if getattr(sys, 'frozen', False):
        return sys.executable, 'supervise', str(Path(sys.executable).parent)
    exe = Path(sys.executable)
    pythonw = exe.with_name('pythonw.exe')
    return str(pythonw if pythonw.is_file() else exe), '-X utf8 -m axbranch supervise', str(Path(__file__).resolve().parents[1])


def task_xml(command, arguments, workdir, user):
    esc = lambda s: str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>AX Branch: deterministic supervision pass (no AI). Recovers dead or stalled project
workers by the AX Branch recovery rules and notifies the Owner when a project waits for them.</Description></RegistrationInfo>
  <Triggers>
    <LogonTrigger><Enabled>true</Enabled><UserId>{esc(user)}</UserId></LogonTrigger>
    <TimeTrigger><Repetition><Interval>PT{INTERVAL_MINUTES}M</Interval><StopAtDurationEnd>false</StopAtDurationEnd></Repetition>
      <StartBoundary>2026-01-01T00:00:00</StartBoundary><Enabled>true</Enabled></TimeTrigger>
  </Triggers>
  <Principals><Principal id="Author"><UserId>{esc(user)}</UserId><LogonType>InteractiveToken</LogonType>
    <RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries><StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable><ExecutionTimeLimit>PT10M</ExecutionTimeLimit>
    <Enabled>true</Enabled><Hidden>false</Hidden><WakeToRun>false</WakeToRun>
  </Settings>
  <Actions Context="Author"><Exec><Command>{esc(command)}</Command><Arguments>{esc(arguments)}</Arguments>
    <WorkingDirectory>{esc(workdir)}</WorkingDirectory></Exec></Actions>
</Task>
"""


def _schtasks(*args):
    r = subprocess.run(['schtasks', *args], capture_output=True, text=True, errors='replace',
                       creationflags=_NO_WINDOW if os.name == 'nt' else 0)
    return r.returncode, (r.stdout + r.stderr).strip()


def register(name=TASK, action=None):
    """Create or replace the scheduled task (current user, no elevation)."""
    command, arguments, workdir = action or _action()
    user = f"{os.environ.get('USERDOMAIN', '')}\\{os.environ.get('USERNAME', '')}".lstrip('\\')
    with tempfile.TemporaryDirectory() as tmp:
        xml = Path(tmp) / 'task.xml'
        xml.write_text(task_xml(command, arguments, workdir, user), encoding='utf-16')
        code, out = _schtasks('/Create', '/TN', name, '/XML', str(xml), '/F')
    if code:
        raise RuntimeError(f'schtasks /Create failed: {out}')
    return out


def unregister(name=TASK):
    code, out = _schtasks('/Delete', '/TN', name, '/F')
    return out if code == 0 else f'not registered ({out})'


def status(name=TASK):
    code, out = _schtasks('/Query', '/TN', name, '/V', '/FO', 'LIST')
    return out if code == 0 else 'not registered'


def notify(title, text):
    """A Windows notification (built-in toast through PowerShell; no extra software). True if shown."""
    if os.name != 'nt':
        return False
    script = (
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null;"
        "$t = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent("
        "[Windows.UI.Notifications.ToastTemplateType]::ToastText02);"
        "$x = $t.GetElementsByTagName('text');"
        "$x.Item(0).AppendChild($t.CreateTextNode($env:AXB_TITLE)) > $null;"
        "$x.Item(1).AppendChild($t.CreateTextNode($env:AXB_TEXT)) > $null;"
        "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("
        "'{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe')"
        ".Show([Windows.UI.Notifications.ToastNotification]::new($t))")
    try:
        r = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', script], timeout=30,
                           capture_output=True, env={**os.environ, 'AXB_TITLE': title, 'AXB_TEXT': text},
                           creationflags=_NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0


def notify_waiting(engine, show=notify):
    """Tell the Owner once per waiting state (state + version + reason) that a project waits for them."""
    from . import supervisor
    store, sent = engine.store, []
    for p in (store.project(row['id']) for row in store.projects()):
        rec = supervisor.status(engine.workspace, store, p['id'])
        if rec['status'] != 'WAITING_FOR_OWNER' or p['state'] in ('PENDING_CLOSE', 'ARCHIVE_PENDING_APPROVAL'):
            continue                      # closing steps the Owner already chose are not news
        # One waiting episode = the transition into the current state (a later identical pause is a new one).
        entered = max((e['id'] for e in store.events(p['id'], {'state'})), default=0)
        key = f"{p['state']}|v{p['iteration']}|state-event {entered}"
        if any(e['detail'].get('key') == key and e['detail'].get('shown') for e in store.events(p['id'], {'owner_notified'})):
            continue
        what = ('검증된 결과가 준비됐습니다. AX Branch에서 [결과 실행] 후 의견을 남겨 주세요.'
                if p['state'] == 'OWNER_REVIEW' else 'Owner 결정이 필요합니다: ' + (p['pause_reason'] or p['state'])[:120])
        shown = show(f"AX Branch — {p['goal'][:40]}", what)
        store.event(p['id'], 'owner_notified', key=key, shown=shown)
        if shown:                                         # a failed toast is tried again on the next pass
            sent.append(p['id'])
    return sent


def log_pass(workspace, line):
    """One line per headless pass, so a pass that ran (and what it did) is visible without a window."""
    path = Path(workspace) / 'logs' / 'supervisor.log'
    path.parent.mkdir(parents=True, exist_ok=True)
    # ponytail: append-only, ~100 B per 5 min (~10 MB/yr); rotate if it ever matters
    with path.open('a', encoding='utf-8') as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} pid={os.getpid()} {line}\n")
