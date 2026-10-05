"""Execution supervisor: the Owner must never be the watchdog.

Everything here is deterministic (lock, heartbeat file, live activity file, SQLite events) — no LLM.

status()     -> one record with project / stage / agent / provider / worker pid / call start, elapsed,
                timeout / last heartbeat / last meaningful activity / artifact version / verification
                round / recovery count / failure signature / next action, and a label:
                ACTIVE · WAITING_FOR_OWNER · WAITING_FOR_PROVIDER · STALLED · RECOVERING · FAILED ·
                PAUSED · COMPLETED.
supervise()  -> bounded automatic recovery for one project:
                1st time a failure signature is seen   -> resume from the checkpoint (completed work is
                                                          never redone: the engine continues from SQLite)
                2nd time the same signature is seen    -> CEO re-plan, then resume
                3rd time                               -> PAUSED, needs an Owner decision
                Total recoveries per project are capped.

Who runs it: the Owner window, on its refresh timer (one mechanism, no extra shells); without the
window, `axbranch supervise --watch` does the same until nothing is left to supervise.
"""
import json
import re
import time
from pathlib import Path

from . import providers
from .state import ACTIVE, NEXT, Busy, run_lock

HEARTBEAT_STALE = 600     # s without any engine heartbeat between provider calls -> stalled
OUTPUT_STALE = 900        # s without CLI output while a provider call is in flight -> stalled
TIMEOUT_GRACE = 300       # a call past its own timeout by this much means the timeout did not fire
MAX_RECOVERIES = 5        # per project, all signatures together
RECOVERING_STALE = 300    # s: a RECOVERING marker older than this was left by a crashed supervisor
OWNER_STATES = ('OWNER_REVIEW', 'PENDING_CLOSE', 'ARCHIVE_PENDING_APPROVAL')


def _read(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def _held(workspace, pid):
    try:
        with run_lock(Path(workspace) / 'projects' / pid / 'run.lock'):
            return False
    except Busy:
        return True


def signature(text):
    """A stable failure signature: the reason with numbers, paths and ids removed."""
    text = re.sub(r'[A-Za-z]:\\[^\s)]+|/[\w./-]+', '<path>', text or '')
    text = re.sub(r'\d+', 'N', text)
    return re.sub(r'\s+', ' ', text).strip()[:120]


def status(workspace, store, pid, now=None):
    now = now or time.time()
    p = store.project(pid)
    folder = Path(workspace) / 'projects' / pid
    beat, act = _read(folder / 'HEARTBEAT.json'), _read(folder / 'ACTIVITY.json')
    events = store.events(pid)
    recoveries = [e for e in events if e['kind'] == 'recovery']
    last_event = events[-1]['at'] if events else p['updated']
    beat_at = beat['at'] if beat else None
    act_at = (folder / 'ACTIVITY.json').stat().st_mtime if act else None
    meaningful = max(x for x in (last_event, beat_at,
                                 (act_at - (act.get('idle') or 0)) if act else None) if x is not None)
    rec = {
        'project': pid, 'stage': p['state'], 'resume_state': p['resume_state'],
        'agent': act and act.get('agent'), 'provider': act and act.get('provider'),
        'worker_pid': (beat or {}).get('os_pid'), 'provider_pid': act and act.get('pid'),
        'call_started': act and act.get('started_at'), 'call_elapsed': act and act.get('elapsed'),
        'call_timeout': providers.TIMEOUT, 'last_heartbeat_age': round(now - beat_at) if beat_at else None,
        'last_meaningful_activity_age': round(now - meaningful),
        'artifact_version': p['iteration'], 'verification_round': len(store.verifications(pid)),
        'recovery_count': len(recoveries),
        'failure_signature': recoveries[-1]['detail'].get('signature') if recoveries else None,
        'next_action': NEXT[p['resume_state'] if p['state'] == 'PAUSED' else p['state']],
    }
    rec['status'], rec['reason'] = _classify(p, rec, act, beat, folder, workspace, now)
    return rec


def _classify(p, rec, act, beat, folder, workspace, now):
    state, reason = p['state'], p['pause_reason'] or ''
    if state == 'CLOSED':
        return 'COMPLETED', 'closed'
    if state in OWNER_STATES:
        return 'WAITING_FOR_OWNER', f'{state}: the Owner reviews / decides'
    if state == 'PAUSED':
        if 'approval needed' in reason or 'NEEDS_DECISION' in reason or 'not lowered' in reason:
            return 'WAITING_FOR_OWNER', reason[:200]
        if 'RateLimited' in reason or 'No provider available' in reason:
            return 'WAITING_FOR_PROVIDER', reason[:200]
        if reason.startswith(('Rejected', 'Internal error')):
            return 'FAILED', reason[:200]
        return 'PAUSED', reason[:200]
    marker = folder / 'RECOVERING'
    if marker.exists():
        if now - marker.stat().st_mtime < RECOVERING_STALE:
            return 'RECOVERING', marker.read_text(encoding='utf-8')[:200]
        marker.unlink(missing_ok=True)         # left by a crashed supervisor: never let it block recovery
    if not _held(workspace, p['id']):
        return 'STALLED', f'{state} but no engine session is running it (process gone)'
    if act:
        if act.get('waiting'):
            return 'WAITING_FOR_PROVIDER', act['waiting']
        if (act.get('elapsed') or 0) > providers.TIMEOUT + TIMEOUT_GRACE:
            return 'STALLED', f"provider call at {act['elapsed']} s, past its {providers.TIMEOUT} s timeout"
        if (act.get('idle') or 0) > OUTPUT_STALE:
            return 'STALLED', f"no provider output for {act['idle']} s"
        return 'ACTIVE', f"{act.get('agent')} on {act.get('provider')}: {act.get('elapsed')} s / {providers.TIMEOUT} s"
    if rec['last_heartbeat_age'] is not None and rec['last_heartbeat_age'] > HEARTBEAT_STALE:
        return 'STALLED', f"no engine heartbeat for {rec['last_heartbeat_age']} s ({(beat or {}).get('detail')})"
    return 'ACTIVE', f"engine working: {(beat or {}).get('detail') or state}"


def supervise(engine, pid, launch, stop):
    """One supervision decision for one project. launch(pid) starts an engine session in the
    background; stop(pid, worker_pid) ends a hung one. Returns the action taken (or None)."""
    store, workspace = engine.store, engine.workspace
    rec = status(workspace, store, pid)
    if rec['status'] not in ('STALLED', 'FAILED'):
        return None
    p = store.project(pid)
    sig = signature(f"{rec['status']}:{rec['stage']}:{rec['reason']}")
    seen = [e for e in store.events(pid, {'recovery'}) if e['detail'].get('signature') == sig]
    total = rec['recovery_count']
    folder = Path(workspace) / 'projects' / pid
    if total >= MAX_RECOVERIES or len(seen) >= 2:
        if p['state'] != 'PAUSED':
            stop(pid, rec['worker_pid'])
            _settle(engine, pid)
        reason = (f"NEEDS_DECISION: automatic recovery did not resolve '{sig}' "
                  f"({len(seen)} same-signature attempts, {total} total). The Owner decides how to continue.")
        if store.project(pid)['state'] == 'PAUSED':
            store.update(pid, pause_reason=reason)      # pause() is a no-op on an already paused project
        else:
            store.pause(pid, reason)
        store.event(pid, 'recovery', signature=sig, action='needs_owner_decision', attempt=len(seen) + 1)
        return 'needs_owner_decision'
    (folder / 'RECOVERING').write_text(f"{rec['status']}: {rec['reason']} -> recovering", encoding='utf-8')
    try:
        if rec['status'] == 'STALLED' and _held(workspace, pid):
            stop(pid, rec['worker_pid'])             # hung worker: end its whole tree first
        _settle(engine, pid)
        if _held(workspace, pid):
            # The old worker has not let go yet: launching now would start a second session.
            store.event(pid, 'recovery', signature=sig, action='waiting_for_stop', attempt=len(seen) + 1)
            return 'waiting_for_stop'
        action = 'resume'
        if seen:                                     # same failure again: change the approach, not retry
            action = 'replan+resume'
            if store.project(pid)['state'] not in ('PAUSED', 'REWORK'):
                store.pause(pid, f'recovery checkpoint before re-plan ({sig})')
            engine.replan(pid, f'Automatic recovery: the failure "{sig}" happened again after a resume. '
                               'Change the approach so it does not recur; keep all completed, still-valid work.')
        p = store.project(pid)
        if p['state'] == 'PAUSED':
            store.resume(pid)
        store.event(pid, 'recovery', signature=sig, action=action, attempt=len(seen) + 1, reason=rec['reason'])
        launch(pid)
        return action
    finally:
        (folder / 'RECOVERING').unlink(missing_ok=True)


def _settle(engine, pid, seconds=30):
    """Wait (bounded) until the stopped session has released the project lock."""
    end = time.monotonic() + seconds
    while _held(engine.workspace, pid) and time.monotonic() < end:
        time.sleep(0.5)


def candidates(store):
    """Projects worth a supervision look: active or failed-paused ones."""
    return [p['id'] for p in store.projects() if p['state'] in ACTIVE or p['state'] == 'PAUSED']


def stop_worker(worker_pid, cancel_events=None, pid=None):
    """End a hung session: a thread of this process gets its cancel event set (the provider loop and
    whole-tree kill do the rest); another process has its whole tree terminated."""
    import os
    import subprocess
    if worker_pid in (None, os.getpid()):
        event = (cancel_events or {}).get(pid)
        if event is not None:
            event.set()
        return
    if os.name == 'nt':
        subprocess.run(['taskkill', '/PID', str(worker_pid), '/T', '/F'], capture_output=True)
    else:
        import signal
        try:
            os.killpg(os.getpgid(worker_pid), signal.SIGKILL)
        except OSError:
            pass


def launch_detached(workspace, pid):
    """Start `axbranch run <pid>` as its own background process (no console, survives this one)."""
    import os
    import subprocess
    import sys
    log = (Path(workspace) / 'projects' / pid / 'supervised-run.log').open('ab')
    flags = 0x00000008 | 0x00000200 | 0x08000000 if os.name == 'nt' else 0   # DETACHED | NEW_GROUP | NO_WINDOW
    subprocess.Popen([sys.executable, '-X', 'utf8', '-m', 'axbranch', 'run', pid], stdout=log, stderr=log,
                     stdin=subprocess.DEVNULL, creationflags=flags, cwd=str(Path(__file__).resolve().parents[1]))


def channel():
    """Where an Owner action came from. Development of AX Branch itself (AXB_DEV=1) is not an Owner
    escape; an Owner forced into a developer CLI (Claude Code / Codex env) is."""
    import os
    if os.environ.get('AXB_DEV') == '1':
        return 'dev'
    if any(k.startswith(('CLAUDECODE', 'CODEX_SESSION', 'CODEX_THREAD')) for k in os.environ):
        return 'developer_cli'
    return 'cli'
