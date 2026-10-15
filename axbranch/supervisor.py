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
                2nd time the same signature is seen    -> CEO re-plan, then resume (a project that died in
                                                          VERIFYING is only re-verified: nothing to re-plan)
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
MAX_RECOVERIES = 5        # per project since the Owner's last action, all signatures together
OWNER_STOP = 'Owner stopped'
RECOVERING_STALE = 300    # s: a RECOVERING marker older than this was left by a crashed supervisor
OWNER_STATES = ('OWNER_REVIEW', 'PENDING_CLOSE', 'ARCHIVE_PENDING_APPROVAL')
PROVIDER_RETRY_GAP = 900  # s between automatic retries after a stated provider reset time
_RESETS = re.compile(r'resets (\d{1,2})(?::(\d{2}))?\s*([ap]m)', re.I)
_TRY_AT = re.compile(r'try again at (\w{3})\w* (\d{1,2})\w*, (\d{4}) (\d{1,2}):(\d{2})\s*([AP]M)', re.I)


def provider_reset_at(reason, paused_at):
    """Epoch time of the EARLIEST reset the provider refusals in `reason` state (one free provider is enough),
    or None if none is stated. 'resets 12:10am' is the next such local time after the pause; 'try again at
    Oct 9th, 2026 12:15 AM' is absolute. Local time: the CLIs print the user's zone."""
    import datetime as dt
    base = dt.datetime.fromtimestamp(paused_at)
    times = []
    for h, m, ap in _RESETS.findall(reason or ''):
        hour = int(h) % 12 + (12 if ap.lower() == 'pm' else 0)
        at = base.replace(hour=hour, minute=int(m or 0), second=0, microsecond=0)
        times.append(at if at > base else at + dt.timedelta(days=1))
    for mon, day, year, h, m, ap in _TRY_AT.findall(reason or ''):
        try:
            at = dt.datetime.strptime(f'{mon} {day} {year} {h}:{m} {ap.upper()}', '%b %d %Y %I:%M %p')
        except ValueError:
            continue
        times.append(at)
    return min(times).timestamp() if times else None


def awake():
    """Seconds of machine time that exclude sleep/hibernation, comparable across processes. A heartbeat
    that went quiet because the PC slept is not a hung worker (P-bbad3c 10-08: asleep 03:27-19:11, then the
    wall-clock age said 'no heartbeat for 56643 s' and recovery killed the live v30 verification)."""
    import os
    if os.name != 'nt':
        return time.monotonic()                   # CLOCK_MONOTONIC stops during suspend
    import ctypes
    value = ctypes.c_ulonglong()
    ctypes.windll.kernel32.QueryUnbiasedInterruptTime(ctypes.byref(value))
    return value.value / 1e7


def _read(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def since_owner(events, kinds):
    """Events of these kinds after the Owner's last action: an explicit Owner decision (resume, review,
    approve, …) starts a fresh automatic-recovery budget; supervisor-launched workers are not Owner actions."""
    last = max((i for i, e in enumerate(events) if e['kind'] == 'owner_action'), default=-1)
    return [e for e in events[last + 1:] if e['kind'] in kinds]


def _held(workspace, pid):
    path = Path(workspace) / 'projects' / pid / 'run.lock'
    if not path.exists():                     # never ran here; a display probe must not create files
        return False
    try:
        with run_lock(path):
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
    recoveries = since_owner(events, {'recovery'})
    last_event = events[-1]['at'] if events else p['updated']
    beat_at = beat['at'] if beat else None
    beat_age = (awake() - beat['awake']) if beat and 'awake' in beat else (now - beat_at if beat_at else None)
    try:
        act_at = (folder / 'ACTIVITY.json').stat().st_mtime if act else None
    except FileNotFoundError:             # the engine finished the call after _read()
        act, act_at = None, None
    meaningful = max(x for x in (last_event, beat_at,
                                 (act_at - (act.get('idle') or 0)) if act else None) if x is not None)
    rec = {
        'project': pid, 'stage': p['state'], 'resume_state': p['resume_state'],
        'agent': act and act.get('agent'), 'provider': act and act.get('provider'),
        'worker_pid': (beat or {}).get('os_pid'), 'provider_pid': act and act.get('pid'),
        'call_started': act and act.get('started_at'), 'call_elapsed': act and act.get('elapsed'),
        'call_timeout': providers.TIMEOUT, 'last_heartbeat_age': round(beat_age) if beat_age is not None else None,
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
        if any(k in reason for k in ('approval needed', 'NEEDS_DECISION', 'not lowered', 'HARNESS_BLOCKED')):
            return 'WAITING_FOR_OWNER', reason[:200]
        if 'RateLimited' in reason or 'No provider available' in reason:
            return 'WAITING_FOR_PROVIDER', reason[:200]
        if OWNER_STOP in reason or '오너가 중단' in reason:
            return 'PAUSED', reason[:200]                  # the Owner stopped it: never auto-resumed
        if reason.startswith(('Rejected', 'Internal error', 'recovery checkpoint', 'INFRA_FAILED')):   # incl. a failed re-plan
            return 'FAILED', reason[:200]
        return 'PAUSED', reason[:200]
    if not _held(workspace, p['id']):
        marker = folder / 'RECOVERING'
        try:      # a recovery launched a worker that has not taken the lock yet: not a second death
            if now - marker.stat().st_mtime < RECOVERING_STALE:
                return 'RECOVERING', marker.read_text(encoding='utf-8')[:200]
        except FileNotFoundError:
            pass  # older markers were left by a crashed supervisor: never block recovery
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
    background; stop(pid, worker_pid) ends a hung one. Returns the action taken (or None).
    One supervisor at a time per project (window + CLI): the other pass backs off."""
    guard = run_lock(Path(engine.workspace) / 'projects' / pid / 'supervise.lock')
    try:
        guard.__enter__()
    except Busy:
        return None
    try:
        return _supervise(engine, pid, launch, stop)
    finally:
        guard.__exit__(None, None, None)


def _supervise(engine, pid, launch, stop):
    store, workspace = engine.store, engine.workspace
    rec = status(workspace, store, pid)
    if rec['status'] == 'WAITING_FOR_PROVIDER':
        return _provider_retry(engine, pid, launch)
    if rec['status'] not in ('STALLED', 'FAILED'):
        return None
    p = store.project(pid)
    sig = signature(f"{rec['status']}:{rec['stage']}:{rec['reason']}")
    seen = [e for e in since_owner(store.events(pid), {'recovery'}) if e['detail'].get('signature') == sig]
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
    marker = folder / 'RECOVERING'
    try:
        if time.time() - marker.stat().st_mtime >= RECOVERING_STALE:
            marker.unlink(missing_ok=True)        # left by a crashed supervisor: never blocks recovery
    except FileNotFoundError:
        pass
    try:                                          # exclusive: a second supervisor (window + CLI) backs off
        with marker.open('x', encoding='utf-8') as f:
            f.write(f"{rec['status']}: {rec['reason']} -> recovering")
    except FileExistsError:
        return None
    launched = False
    try:
        if rec['status'] == 'STALLED' and _held(workspace, pid):
            stop(pid, rec['worker_pid'])             # hung worker: end its whole tree first
        _settle(engine, pid)
        if _held(workspace, pid):
            # The old worker has not let go yet: launching now would start a second session.
            store.event(pid, 'recovery', signature=sig, action='waiting_for_stop', attempt=len(seen) + 1)
            return 'waiting_for_stop'
        stage = p['resume_state'] if p['state'] == 'PAUSED' else p['state']
        # Same failure again: change the approach — except in VERIFYING, which resumes by re-verifying the
        # built version (10-08: a re-plan there rebuilt into the verified iteration and crashed twice).
        action = 'replan+resume' if seen and stage != 'VERIFYING' else 'resume'
        # Recorded BEFORE acting, so an attempt that itself fails (e.g. the re-plan raises) still counts.
        store.event(pid, 'recovery', signature=sig, action=action, attempt=len(seen) + 1, reason=rec['reason'])
        if action == 'replan+resume':
            if store.project(pid)['state'] not in ('PAUSED', 'REWORK'):
                store.pause(pid, f'recovery checkpoint before re-plan ({sig})')
            engine.replan(pid, f'Automatic recovery: the failure "{sig}" happened again after a resume. '
                               'Change the approach so it does not recur; keep all completed, still-valid work.',
                          by='Supervisor')
        p = store.project(pid)
        if p['state'] == 'PAUSED':
            store.resume(pid, by='Supervisor')
        launch(pid)
        launched = True
        return action
    finally:
        if not launched:   # after a launch the marker stays until the new worker starts (engine._run removes
            marker.unlink(missing_ok=True)   # it), so a second supervisor pass meanwhile sees RECOVERING


def _provider_retry(engine, pid, launch, now=None):
    """A project paused because every provider refused for quota resumes from its checkpoint once the
    stated reset time has passed (10-08: reset 00:10 passed and the project sat in WAITING_FOR_PROVIDER, since
    nothing ever re-checked). Not a failure recovery: no re-plan, no recovery count. At most one retry per
    PROVIDER_RETRY_GAP; a refusal again just pauses again with the new reset time."""
    store, now = engine.store, now or time.time()
    p = store.project(pid)
    if p['state'] != 'PAUSED' or not p['pause_reason'] or 'RateLimited' not in p['pause_reason']:
        return None                                     # a live call waiting for a slot, or not a quota pause
    paused = [e for e in store.events(pid, {'state'}) if e['detail'].get('to') == 'PAUSED']
    reset = provider_reset_at(p['pause_reason'], paused[-1]['at'] if paused else now)
    retries = [e for e in store.events(pid, {'provider_retry'}) if now - e['at'] < PROVIDER_RETRY_GAP]
    if reset is None or now < reset or retries:
        return None
    folder = Path(engine.workspace) / 'projects' / pid
    try:
        with (folder / 'RECOVERING').open('x', encoding='utf-8') as f:     # the worker removes it when it starts
            f.write('provider reset passed -> resuming from the checkpoint')
    except FileExistsError:
        return None
    store.event(pid, 'provider_retry', reset_at=reset, resume_state=p['resume_state'])
    store.resume(pid, by='Supervisor')
    launch(pid)
    return 'provider_retry'


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
    folder = Path(workspace) / 'projects' / pid
    folder.mkdir(parents=True, exist_ok=True)
    flags = 0x00000008 | 0x00000200 | 0x08000000 if os.name == 'nt' else 0   # DETACHED | NEW_GROUP | NO_WINDOW
    frozen = getattr(sys, 'frozen', False)                 # AXBranch.exe dispatches `run` to the CLI
    cmd = [sys.executable, 'run', pid] if frozen else [sys.executable, '-X', 'utf8', '-m', 'axbranch', 'run', pid]
    with (folder / 'supervised-run.log').open('ab') as log:
        kwargs = dict(stdout=log, stderr=log, stdin=subprocess.DEVNULL, env={**os.environ, 'AXB_SUPERVISED': '1'},
                      cwd=None if frozen else str(Path(__file__).resolve().parents[1]))
        try:     # leave the launcher's job (a scheduled pass ends right after this) when the job allows it
            subprocess.Popen(cmd, creationflags=flags | (0x01000000 if os.name == 'nt' else 0), **kwargs)
        except OSError:
            subprocess.Popen(cmd, creationflags=flags, **kwargs)


def channel():
    """Where an Owner action came from. Development of AX Branch itself (AXB_DEV=1) is not an Owner
    escape; an Owner forced into a developer CLI (Claude Code / Codex env) is."""
    import os
    if os.environ.get('AXB_DEV') == '1':
        return 'dev'
    if any(k.startswith(('CLAUDECODE', 'CODEX_SESSION', 'CODEX_THREAD')) for k in os.environ):
        return 'developer_cli'
    return 'cli'
