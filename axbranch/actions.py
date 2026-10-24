"""Owner actions shared by the Tk window and the local web UI: one implementation of start / resume / stop /
network decision / review / close / result, all through the existing store, engine and supervisor. A screen
never runs its own approval, execution or verification logic."""
from . import departments, supervisor
from .state import Rejected

OWNER_WAIT = ('OWNER_REVIEW', 'PENDING_CLOSE', 'ARCHIVE_PENDING_APPROVAL')


def launch(workspace, store, pid, launcher=None):
    """Start the project's background worker unless one already runs. Returns True when started."""
    if supervisor.status(workspace, store, pid)['status'] == 'ACTIVE':
        return False                                   # already running somewhere: never a second worker
    (launcher or supervisor.launch_detached)(workspace, pid)
    return True


def start(store, engine_factory, goal, dep_ids, specs, files, channel, request_id=None):
    """A new project from the goal box: inputs checked first (a bad file never leaves a half project), then the
    project, its departments (function connections only) and its inputs. Returns the project id.
    request_id: the same id again returns the project it already created (a reload or double submit)."""
    goal = (goal or '').strip()
    if not goal:
        raise Rejected('목표를 입력해 주세요.')
    if request_id:
        existing = created_by(store, request_id)
        if existing:
            return existing
    if files:
        from .artifacts import validate_inputs
        validate_inputs(files)
    unknown = [d for d in dep_ids if d not in specs]
    if unknown:
        raise Rejected(f'라이브러리에 없는 부서: {unknown}')
    pid = store.new_project(goal)
    store.event(pid, 'owner_action', action='new', channel=channel, **({'request_id': request_id} if request_id else {}))
    for dep_id in dict.fromkeys(dep_ids):
        departments.attach(store, pid, dep_id, specs)
    if files:
        engine = engine_factory()
        try:
            engine.attach_inputs(pid, files)
        except (ValueError, OSError) as e:      # e.g. a file changed after it was checked: do not run without it
            err = Rejected(f'첨부 실패 — 프로젝트를 실행하지 않았습니다: {e}')
            err.pid = pid
            raise err
        finally:
            engine.store.close()
    return pid


def created_by(store, request_id):
    for p in store.projects():
        for e in store.events(p['id'], {'owner_action'}):
            if e['detail'].get('action') == 'new' and e['detail'].get('request_id') == request_id:
                return p['id']
    return None


def resume(store, pid, channel):
    """Returns True when the project needs its worker (False: it only went back to waiting for the Owner)."""
    p = store.project(pid)
    if p['state'] == 'PAUSED':
        if p['resume_state'] in OWNER_WAIT:
            store.resume(pid)                          # back to waiting for the Owner: no engine work, no worker
            store.event(pid, 'owner_action', action='resume', channel=channel)
            return False
        extra = 3 if 'not lowered' in (p['pause_reason'] or '') else 0
        store.resume(pid, extra)
    store.event(pid, 'owner_action', action='resume', channel=channel)
    return p['state'] not in ('CLOSED',) + OWNER_WAIT


def stop(workspace, store, pid, channel, via='window'):
    """Owner stop: end the worker's process tree and PAUSE (checkpointed; never auto-resumed)."""
    rec = supervisor.status(workspace, store, pid)
    if rec.get('worker_pid') and supervisor._held(workspace, pid):
        supervisor.stop_worker(rec['worker_pid'], pid=pid)
    p = store.project(pid)
    reason = f'{supervisor.OWNER_STOP} ({via}). Resume continues from here.'
    if p['state'] == 'PAUSED':
        store.update(pid, pause_reason=reason)         # an Owner stop, not a failure
    elif p['state'] != 'CLOSED':
        store.pause(pid, reason)
    store.event(pid, 'owner_action', action='stop', channel=channel)


def decide_network(engine_factory, pid, approve, channel, note=''):
    engine = engine_factory()
    try:
        engine.decide_network(pid, approve, note=note)
        engine.store.event(pid, 'owner_action', action='approve', channel=channel)
    finally:
        engine.store.close()


def review(engine_factory, pid, works, text, finish, channel):
    """Record the Owner's review. Returns (project, needs_worker)."""
    engine = engine_factory()
    try:
        p = engine.owner_review(pid, works, text, finish)
        engine.store.event(pid, 'owner_action', action='review', channel=channel)
    finally:
        engine.store.close()
    return p, p['state'] not in OWNER_WAIT + ('PAUSED', 'CLOSED')


def close(engine_factory, pid, choice, channel, satisfaction=None, why='', confirm=False):
    """Finish a project: the CEO asks first (choice None); then save / pause / discard (discard needs confirm)."""
    engine = engine_factory()
    try:
        p = engine.close(pid)
        if choice is None:
            return p
        if choice != 'discard':
            engine.note_satisfaction(pid, why)
        p = engine.close(pid, choice, confirm, satisfaction)
        engine.store.event(pid, 'owner_action', action=f'close_{choice}', channel=channel)
        return p
    finally:
        engine.store.close()


def owner_mode(p, status):
    """Which Owner decision a project waits for: 'approval' / 'review' / 'decision' / None, and its note."""
    reason = p['pause_reason'] or ''
    if status != 'WAITING_FOR_OWNER' or p['state'] == 'ARCHIVE_PENDING_APPROVAL':
        return None, ''
    if 'approval needed' in reason:
        return 'approval', reason[:400]
    if p['state'] == 'OWNER_REVIEW':
        return 'review', ''
    return 'decision', reason[:220] or p['state']
