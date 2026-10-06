"""SQLite runtime state: the Source of Truth for every project.

Chat transcripts are never consulted. Anything a fresh engine (Claude, Codex or a
human) needs to continue a project is in these tables, and handoff() renders it.
"""
import json
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from . import __version__, governance as gov

TRANSITIONS = {
    'CREATED': {'PLANNING'},
    'PLANNING': {'STAFFING'},
    'STAFFING': {'EXECUTING'},
    'EXECUTING': {'VERIFYING', 'REWORK'},     # REWORK: the producer delivered nothing (no verification needed)
    'VERIFYING': {'REWORK', 'OWNER_REVIEW'},
    'REWORK': {'STAFFING'},
    # The Owner tries the verified artifact: works -> PENDING_CLOSE; problem / change -> REWORK (same project).
    'OWNER_REVIEW': {'PENDING_CLOSE', 'REWORK', 'ARCHIVE_PENDING_APPROVAL'},
    'PENDING_CLOSE': {'ARCHIVE_PENDING_APPROVAL', 'REWORK'},
    'ARCHIVE_PENDING_APPROVAL': {'ARCHIVING', 'CLOSED'},
    'ARCHIVING': {'CLOSED'},
    'CLOSED': set(),
}
STATES = (*TRANSITIONS, 'PAUSED')
ACTIVE = {'CREATED', 'PLANNING', 'STAFFING', 'EXECUTING', 'VERIFYING', 'REWORK'}
NEXT = {
    'CREATED': 'CEO interprets the goal',
    'PLANNING': 'CEO interprets the goal and designs the pipeline',
    'STAFFING': 'CEO hires the temporary specialist agents the pipeline needs',
    'EXECUTING': 'Production agents run the pipeline stages and build the artifact',
    'VERIFYING': 'Verification Agent judges the latest artifact',
    'REWORK': 'Rebuild: CEO diagnoses Owner feedback (if any), production agents rebuild from findings',
    'OWNER_REVIEW': 'Owner tests the verified artifact and reports: works / problem / change request',
    'PAUSED': 'Owner decides: resume (python -m axbranch resume <id>)',
    'PENDING_CLOSE': 'Owner accepted the result; says when the project is finished (or reports a problem)',
    'ARCHIVE_PENDING_APPROVAL': 'Owner chooses SAVE & CLOSE, PAUSE or CLOSE WITHOUT SAVE',
    'ARCHIVING': 'Write and verify the Obsidian archive',
    'CLOSED': 'Nothing; project closed',
}

SCHEMA = '''
CREATE TABLE IF NOT EXISTS projects(
  id TEXT PRIMARY KEY, goal TEXT NOT NULL, state TEXT NOT NULL, resume_state TEXT, pause_reason TEXT,
  plan TEXT, plan_version INTEGER NOT NULL DEFAULT 0, iteration INTEGER NOT NULL DEFAULT 1,
  budget INTEGER NOT NULL, report TEXT, closed_mode TEXT, archive_note TEXT, satisfaction INTEGER,
  created REAL NOT NULL, updated REAL NOT NULL);
CREATE TABLE IF NOT EXISTS agents(
  id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), role TEXT NOT NULL,
  provider TEXT NOT NULL, status TEXT NOT NULL, created REAL NOT NULL, ended REAL);
CREATE TABLE IF NOT EXISTS stage_outputs(
  project_id TEXT NOT NULL REFERENCES projects(id), iteration INTEGER NOT NULL, plan_version INTEGER NOT NULL,
  stage INTEGER NOT NULL, agent_id TEXT, provider TEXT, output TEXT NOT NULL, created REAL NOT NULL,
  PRIMARY KEY(project_id, iteration, plan_version, stage));
CREATE TABLE IF NOT EXISTS artifacts(
  id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), iteration INTEGER NOT NULL,
  path TEXT NOT NULL, sha256 TEXT NOT NULL, kind TEXT NOT NULL, agent_id TEXT, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS verifications(
  id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), artifact_id TEXT NOT NULL,
  iteration INTEGER NOT NULL, verdict TEXT NOT NULL, result TEXT NOT NULL, checks TEXT NOT NULL,
  provider TEXT, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS owner_feedback(
  id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL REFERENCES projects(id),
  iteration INTEGER NOT NULL, verdict TEXT NOT NULL, text TEXT NOT NULL, created REAL NOT NULL,
  handled_iteration INTEGER);
CREATE TABLE IF NOT EXISTS approvals(
  id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL REFERENCES projects(id),
  action TEXT NOT NULL, subject TEXT NOT NULL, purpose TEXT NOT NULL, status TEXT NOT NULL,
  created REAL NOT NULL, decided REAL);
CREATE TABLE IF NOT EXISTS events(
  id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL, at REAL NOT NULL, kind TEXT NOT NULL,
  detail TEXT NOT NULL);
'''
_JSON = ('plan', 'report')
SCHEMA_VERSION = 4   # 1 = 0.1.0-0.1.4 (no marker), 2 = artifacts.manifest (0.1.5), 3 = owner_feedback (0.1.8),
                     # 4 = approvals (0.1.9)


class Rejected(Exception):
    pass


class Busy(Rejected):
    """Another session (GUI thread, CLI, Codex...) is running this project right now."""


@contextmanager
def run_lock(path, wait=0.0):
    """Exclusive, non-blocking OS lock on `path`. The OS drops it when the holder exits or
    crashes, so a dead session never leaves a stale lock. Two threads of one process conflict
    too (each takes its own handle). `wait`: seconds to keep retrying — a liveness probe holds the
    lock for microseconds, and a starting session must not mistake that for another session."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    f = open(path, 'a+b')
    deadline = time.monotonic() + wait if wait else None
    while True:
        try:
            f.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except OSError:
            if deadline and time.monotonic() < deadline:
                time.sleep(0.05)
                continue
            f.close()
            raise Busy(f'Already running in another session (lock {path}). Not started; nothing changed.') from None
    try:
        yield
    finally:
        try:
            f.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        finally:
            f.close()


def _new_id(prefix):
    return f'{prefix}-{time.strftime("%Y%m%d")}-{uuid.uuid4().hex[:6]}'


class Store:
    def __init__(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=30, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA foreign_keys=ON')
        found = self.db.execute('PRAGMA user_version').fetchone()[0]
        if found > SCHEMA_VERSION:
            # A newer AX Branch already upgraded this database. Running older code on it is
            # exactly what stranded a project in 0.1.4, so stop before touching anything.
            self.db.close()
            raise Rejected(f'This workspace database uses schema v{found}; this AX Branch understands up to '
                           f'v{SCHEMA_VERSION}. Update AX Branch (rebuild/reinstall) before using it.')
        self.db.executescript(SCHEMA)
        if 'manifest' not in {r['name'] for r in self.db.execute('PRAGMA table_info(artifacts)')}:
            self.db.execute('ALTER TABLE artifacts ADD COLUMN manifest TEXT')   # 0.1.5: multi-file bundles
        if found < SCHEMA_VERSION:
            self.db.execute(f'PRAGMA user_version={SCHEMA_VERSION}')

    def close(self):
        self.db.close()

    @contextmanager
    def tx(self):
        if self.db.in_transaction:      # nested: the outer transaction owns commit
            yield
            return
        self.db.execute('BEGIN IMMEDIATE')
        try:
            yield
            self.db.execute('COMMIT')
        except BaseException:
            self.db.execute('ROLLBACK')
            raise

    # ---- projects
    def new_project(self, goal):
        goal = (goal or '').strip()
        if not goal:
            raise Rejected('Goal is empty.')
        pid, now = _new_id('P'), time.time()
        with self.tx():
            self.db.execute('INSERT INTO projects(id,goal,state,budget,created,updated) VALUES(?,?,?,?,?,?)',
                            (pid, goal, 'CREATED', gov.MAX_ROUNDS, now, now))
            self.event(pid, 'created', goal=goal)
        return pid

    def project(self, pid):
        row = self.db.execute('SELECT * FROM projects WHERE id=?', (pid,)).fetchone()
        if row is None:
            raise Rejected(f'No project {pid}.')
        p = dict(row)
        for key in _JSON:
            p[key] = json.loads(p[key]) if p[key] else None
        return p

    def projects(self):
        return [dict(r) for r in self.db.execute(
            'SELECT id,goal,state,iteration,updated FROM projects ORDER BY created DESC')]

    def update(self, pid, **fields):
        for key in _JSON:
            if key in fields and fields[key] is not None:
                fields[key] = json.dumps(fields[key], ensure_ascii=False)
        fields['updated'] = time.time()
        cols = ','.join(f'{k}=?' for k in fields)
        self.db.execute(f'UPDATE projects SET {cols} WHERE id=?', (*fields.values(), pid))

    def set_state(self, pid, state, reason=''):
        current = self.project(pid)['state']
        allowed = TRANSITIONS.get(current, set())
        if current == 'PAUSED':
            allowed = {self.project(pid)['resume_state']}
        if state not in allowed:
            raise Rejected(f'Illegal transition {current} -> {state}.')
        with self.tx():
            self.update(pid, state=state, **({'resume_state': None, 'pause_reason': None} if current == 'PAUSED' else {}))
            self.event(pid, 'state', frm=current, to=state, reason=reason)

    def pause(self, pid, reason, resume_state=None):
        p = self.project(pid)
        if p['state'] in ('CLOSED', 'PAUSED'):
            return
        with self.tx():
            self.update(pid, state='PAUSED', resume_state=resume_state or p['state'], pause_reason=reason)
            self.event(pid, 'state', frm=p['state'], to='PAUSED', reason=reason)

    def resume(self, pid, extra_rounds=0):
        p = self.project(pid)
        if p['state'] != 'PAUSED':
            raise Rejected(f'Project is {p["state"]}, not PAUSED.')
        with self.tx():
            if extra_rounds:
                self.update(pid, budget=p['budget'] + extra_rounds)
            self.set_state(pid, p['resume_state'], reason=f'Owner resumed (+{extra_rounds} rounds)')

    # ---- agents (temporary specialists; CEO and Verification are permanent and not rows)
    def add_agent(self, pid, role, provider):
        aid = _new_id('A')
        self.db.execute('INSERT INTO agents(id,project_id,role,provider,status,created) VALUES(?,?,?,?,?,?)',
                        (aid, pid, role, provider, 'active', time.time()))
        self.event(pid, 'agent_hired', agent=aid, role=role, provider=provider)
        return aid

    def agents(self, pid, active_only=True):
        sql = 'SELECT * FROM agents WHERE project_id=?' + (" AND status='active'" if active_only else '')
        return [dict(r) for r in self.db.execute(sql + ' ORDER BY created', (pid,))]

    def end_agents(self, pid, status, role=None):
        sql = "UPDATE agents SET status=?, ended=? WHERE project_id=? AND status='active'"
        args = [status, time.time(), pid]
        if role is not None:
            sql += ' AND role=?'
            args.append(role)
        self.db.execute(sql, args)
        self.event(pid, 'agents_' + status, role=role)

    # ---- work products
    def save_output(self, pid, iteration, plan_version, stage, agent_id, provider, output):
        self.db.execute('INSERT INTO stage_outputs(project_id,iteration,plan_version,stage,agent_id,provider,output,created) '
                        'VALUES(?,?,?,?,?,?,?,?)',
                        (pid, iteration, plan_version, stage, agent_id, provider,
                         json.dumps(output, ensure_ascii=False), time.time()))

    def output(self, pid, stage, plan_version, iteration=None):
        sql = 'SELECT * FROM stage_outputs WHERE project_id=? AND stage=? AND plan_version=?'
        args = [pid, stage, plan_version]
        if iteration is not None:
            sql += ' AND iteration=?'
            args.append(iteration)
        row = self.db.execute(sql + ' ORDER BY iteration DESC LIMIT 1', args).fetchone()
        return None if row is None else {**dict(row), 'output': json.loads(row['output'])}

    def add_artifact(self, pid, iteration, path, sha, kind, agent_id, manifest=None):
        aid = _new_id('F')
        self.db.execute('INSERT INTO artifacts(id,project_id,iteration,path,sha256,kind,agent_id,created,manifest) '
                        'VALUES(?,?,?,?,?,?,?,?,?)', (aid, pid, iteration, str(path), sha, kind, agent_id, time.time(),
                                                      manifest and json.dumps(manifest, ensure_ascii=False)))
        return aid

    def artifacts(self, pid):
        return [dict(r) for r in self.db.execute('SELECT * FROM artifacts WHERE project_id=? ORDER BY created', (pid,))]

    def add_verification(self, pid, artifact_id, iteration, verdict, result, checks, provider):
        vid = _new_id('V')
        self.db.execute('INSERT INTO verifications(id,project_id,artifact_id,iteration,verdict,result,checks,provider,created) '
                        'VALUES(?,?,?,?,?,?,?,?,?)',
                        (vid, pid, artifact_id, iteration, verdict, json.dumps(result, ensure_ascii=False),
                         json.dumps(checks, ensure_ascii=False), provider, time.time()))
        self.event(pid, 'verification', verdict=verdict, iteration=iteration, provider=provider)
        return vid

    def verifications(self, pid):
        return [{**dict(r), 'result': json.loads(r['result']), 'checks': json.loads(r['checks'])}
                for r in self.db.execute('SELECT * FROM verifications WHERE project_id=? ORDER BY created', (pid,))]

    def event(self, pid, kind, **detail):
        self.db.execute('INSERT INTO events(project_id,at,kind,detail) VALUES(?,?,?,?)',
                        (pid, time.time(), kind, json.dumps(detail, ensure_ascii=False)))

    def events(self, pid, kinds=None):
        rows = [{**dict(r), 'detail': json.loads(r['detail'])}
                for r in self.db.execute('SELECT * FROM events WHERE project_id=? ORDER BY id', (pid,))]
        return [r for r in rows if kinds is None or r['kind'] in kinds]

    # ---- Owner review
    def add_feedback(self, pid, iteration, verdict, text, handled=None):
        """verdict: works (runtime confirmed) | problem (does not work) | request (natural-language change,
        feature or improvement) | finish. Only problem/request are rework input; the others are stored
        handled so they can never trigger a diagnosis later."""
        self.db.execute('INSERT INTO owner_feedback(project_id,iteration,verdict,text,created,handled_iteration) '
                        'VALUES(?,?,?,?,?,?)', (pid, iteration, verdict, text, time.time(), handled))
        self.event(pid, 'owner_feedback', verdict=verdict, iteration=iteration, text=text[:2000])

    def feedback(self, pid, pending_only=False):
        sql = 'SELECT * FROM owner_feedback WHERE project_id=?' + (' AND handled_iteration IS NULL' if pending_only else '')
        return [dict(r) for r in self.db.execute(sql + ' ORDER BY id', (pid,))]

    def mark_feedback_handled(self, pid, iteration):
        self.db.execute('UPDATE owner_feedback SET handled_iteration=? WHERE project_id=? AND handled_iteration IS NULL',
                        (iteration, pid))

    # ---- Owner approvals (governance)
    def request_approval(self, pid, action, subject, purpose):
        known = self.db.execute('SELECT status FROM approvals WHERE project_id=? AND action=? AND subject=? '
                                'ORDER BY id DESC LIMIT 1', (pid, action, subject)).fetchone()
        if known is None or known['status'] == 'denied':
            # A decline answers THAT request. If a later plan proposes the same connection again, it is a new
            # request the Owner must see — otherwise the project waits for an approval nobody can give.
            self.db.execute('INSERT INTO approvals(project_id,action,subject,purpose,status,created) VALUES(?,?,?,?,?,?)',
                            (pid, action, subject, purpose, 'pending', time.time()))
            self.event(pid, 'approval_requested', action=action, subject=subject, purpose=purpose)
            return 'pending'
        return known['status']

    def decide_approval(self, pid, action, subject, approve):
        status = 'approved' if approve else 'denied'
        changed = self.db.execute("UPDATE approvals SET status=?, decided=? WHERE project_id=? AND action=? AND subject=? "
                                  "AND status='pending'", (status, time.time(), pid, action, subject)).rowcount
        if changed:
            self.event(pid, 'approval_decided', action=action, subject=subject, status=status, by='Owner')
        return changed

    def approvals(self, pid, status=None):
        sql = 'SELECT * FROM approvals WHERE project_id=?' + (' AND status=?' if status else '')
        return [dict(r) for r in self.db.execute(sql + ' ORDER BY id', (pid, status) if status else (pid,))]

    def discard_context(self, pid):
        """Agent working context (stage outputs). Artifacts and verdicts stay as the audit record."""
        self.db.execute('DELETE FROM stage_outputs WHERE project_id=?', (pid,))

    # ---- structured handoff for any engine
    def handoff(self, pid):
        p = self.project(pid)
        plan = p['plan'] or {}
        last = (self.verifications(pid) or [None])[-1]
        outputs = [dict(r) for r in self.db.execute(
            'SELECT iteration,plan_version,stage,provider,output FROM stage_outputs WHERE project_id=? ORDER BY iteration,stage', (pid,))]
        return {
            'ax_branch_version': __version__,
            'generated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
            'project_id': pid, 'goal': p['goal'], 'state': p['state'],
            'resume_state': p['resume_state'], 'pause_reason': p['pause_reason'],
            'next_action': NEXT[p['resume_state'] if p['state'] == 'PAUSED' else p['state']],
            'iteration': p['iteration'], 'plan_version': p['plan_version'], 'round_budget': p['budget'],
            'interpretation': plan.get('interpretation'),
            'acceptance_criteria': plan.get('acceptance_criteria'),
            'pipeline': plan.get('pipeline'),
            'active_agents': [{k: a[k] for k in ('id', 'role', 'provider')} for a in self.agents(pid)],
            'completed_stages': [{'iteration': o['iteration'], 'plan_version': o['plan_version'], 'stage': o['stage'],
                                  'provider': o['provider'],
                                  'key_points': json.loads(o['output']).get('key_points') or json.loads(o['output']).get('summary')}
                                 for o in outputs],
            'artifacts': [{k: a[k] for k in ('iteration', 'path', 'sha256', 'kind')} for a in self.artifacts(pid)],
            'last_verification': last and {'iteration': last['iteration'], 'verdict': last['verdict'],
                                           'findings': last['result'].get('findings'), 'checks_ok': last['checks'].get('ok')},
            'decisions': [e['detail'] for e in self.events(pid, {'decision'})],
            'provider_handoffs': [e['detail'] for e in self.events(pid, {'provider_handoff'})],
            'ceo_report': p['report'],
            'owner_feedback': [{k: f[k] for k in ('iteration', 'verdict', 'text', 'handled_iteration')}
                               for f in self.feedback(pid)],
            'runtime_spec': plan.get('runtime'),
            'owner_confirmed_working_versions': sorted({f['iteration'] for f in self.feedback(pid) if f['verdict'] == 'works'}),
            'approvals': [{k: a[k] for k in ('action', 'subject', 'purpose', 'status')} for a in self.approvals(pid)],
            'constraints': gov.SUMMARY,
            'continue_with': f'python -m axbranch run {pid}   (from the ax-branch folder; any engine)',
        }
