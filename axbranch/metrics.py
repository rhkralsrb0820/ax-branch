"""Owner Effort — AX Branch's primary product KPI — computed only from recorded state.

MEASURED   counted from SQLite events/rows; exact.
ESTIMATED  derived with a stated rule; may be wrong.
UNKNOWN    not recorded anywhere; never guessed or converted into "time saved".
"""
import json


def _sessions(db, where, args):
    """Who started each engine session, attributed by the CLI environment the process ran in."""
    out = {'owner_or_app': 0, 'claude_code_operator': 0, 'codex_session': 0}
    for (detail,) in db.execute(f"SELECT detail FROM events WHERE kind='session' {where}", args):
        env = json.loads(detail).get('env') or []
        if any(k.startswith('CODEX_SESSION') or k.startswith('CODEX_THREAD') for k in env):
            out['codex_session'] += 1
        elif 'CLAUDECODE' in env:
            out['claude_code_operator'] += 1
        else:
            out['owner_or_app'] += 1
    return out


def _owner_escapes(db, where, args):
    out = {'total': 0, 'by_channel': {'cli': 0, 'developer_cli': 0}, 'by_action': {},
           'in_app_actions': 0, 'excluded_development': 0}
    for (detail,) in db.execute(f"SELECT detail FROM events WHERE kind='owner_action' {where}", args):
        action = json.loads(detail)
        channel = action.get('channel')
        if channel in out['by_channel']:
            # Replans count once here, never again from their recovery_replan events.
            out['total'] += 1
            out['by_channel'][channel] += 1
            name = action['action']
            out['by_action'][name] = out['by_action'].get(name, 0) + 1
        elif channel == 'app':
            out['in_app_actions'] += 1
        elif channel == 'dev':
            out['excluded_development'] += 1
    return out


def effort(store, pid=None):
    db = store.db
    where, args = ('AND project_id=?', (pid,)) if pid else ('', ())
    count = lambda sql: db.execute(sql + ' ' + where, args).fetchone()[0]
    feedback = {v: n for v, n in db.execute(f'SELECT verdict, COUNT(*) FROM owner_feedback WHERE 1=1 {where} '
                                            'GROUP BY verdict', args)}
    events = lambda kind: count(f"SELECT COUNT(*) FROM events WHERE kind='{kind}'")
    # Owner resumes only. Before 2026-10-14 the supervisor's automatic resumes were also labelled 'Owner resumed';
    # those are recognised (history is not rewritten) by the provider_retry/recovery event right before them.
    # A supervisor recovery/provider_retry starts an automatic episode that lasts until its resume (or an Owner
    # action): the re-plan and resume inside it are the supervisor's, whatever the old label said, e.g.
    # recovery -> state(PAUSED, checkpoint) -> recovery_replan(Owner/operator) -> state(Owner resumed).
    rows = db.execute(f"SELECT project_id, id, kind, detail FROM events WHERE kind IN ('state', 'provider_retry', "
                      f"'recovery', 'recovery_replan', 'owner_action') {where} ORDER BY project_id, id", args).fetchall()
    resumes = replans = 0
    project, automatic = None, False
    for pid_, _, kind, detail in rows:
        if pid_ != project:
            project, automatic = pid_, False
        action = json.loads(detail).get('action') if kind == 'recovery' else None
        if kind == 'provider_retry' or action in ('resume', 'replan+resume'):
            automatic = True          # only these supervisor steps resume the project themselves
        elif action == 'needs_owner_decision':
            automatic = False         # the supervisor gave up: whatever resumes next is the Owner
        # (waiting_for_stop resumes nothing and leaves the episode as it was)
        elif kind == 'owner_action':
            automatic = False
        elif kind == 'recovery_replan':
            replans += not automatic and '"by": "Supervisor"' not in detail
        elif kind == 'state' and ('Owner resumed' in detail or 'Supervisor resumed' in detail):
            resumes += 'Owner resumed' in detail and not automatic
            automatic = False                                  # the episode ends with its resume
    projects = 1 if pid else db.execute('SELECT COUNT(*) FROM projects').fetchone()[0]
    owner_instructions = projects + feedback.get('problem', 0) + feedback.get('request', 0)
    calls = events('call')
    # A FAIL on an empty / missing deliverable is AX Branch's own pipeline failure, not a product defect caught.
    from . import artifacts
    empty = {a['id'] for a in (dict(r) for r in db.execute(f'SELECT * FROM artifacts WHERE 1=1 {where}', args))
             if artifacts.is_empty(a)}
    fail_rows = [r[0] for r in db.execute(f"SELECT artifact_id FROM verifications WHERE verdict='FAIL' {where}", args)]
    pipeline_failures = sum(1 for a in fail_rows if a == '' or a in empty)
    fails = len(fail_rows) - pipeline_failures
    passes = count("SELECT COUNT(*) FROM verifications WHERE verdict='PASS'")
    escaped = feedback.get('problem', 0)
    return {
        'scope': pid or 'all projects',
        'MEASURED': {
            'owner_instructions (goals + problem reports + change requests)': owner_instructions,
            'owner_confirmations (works / finish)': feedback.get('works', 0) + feedback.get('finish', 0),
            'owner_approval_decisions': events('approval_decided'),
            'owner_resumes': resumes,
            'manual_recovery_replans': replans,
            'owner_escapes': _owner_escapes(db, where, args),
            'automatic_recoveries': events('recovery'),
            'engine_sessions_started_by': _sessions(db, where, args),
            'ai_agent_turns_run_by_ax_branch': calls,
            'ai_turns_per_owner_instruction': round(calls / owner_instructions, 1) if owner_instructions else None,
            'automatic_provider_switches (no Owner relay)': events('provider_handoff'),
            'defects_caught_before_owner (verification FAIL on a real build)': fails,
            'ax_branch_pipeline_failures (empty / no deliverable)': pipeline_failures,
            'verified_deliveries (PASS)': passes,
            'problems_found_by_owner_after_PASS': escaped,
        },
        'ESTIMATED': {
            'manual_ai_relays_avoided': {
                'value': events('provider_handoff') + calls,
                'rule': 'each AX Branch agent turn and provider switch is a prompt/handoff the Owner would otherwise '
                        'have typed or relayed when driving the AI directly; assumes one prompt per turn',
            },
        },
        'UNKNOWN': [
            'Owner minutes spent reviewing, testing or writing feedback (not recorded)',
            'time the same result would take with direct Claude/ChatGPT/Gemini use (no baseline measured)',
            'business value of the delivered artifacts',
        ],
    }


RECOVERY_ACTIONS = ('resume', 'resume_point', 'replan', 'run', 'stop')


def project_effort(store, pid):
    """Owner Effort for one project, stored with its archive. Every value is counted from recorded events;
    what the records cannot show is UNKNOWN, never estimated.
    owner_interventions  Owner actions (app, CLI, developer CLI; AX Branch development excluded)
    rework_rounds        transitions into REWORK
    verification_rounds  verification records
    manual_recovery      resume/replan/run/stop done outside the app (a person recovering the run)
    owner_escape         Owner actions that needed a CLI / developer session instead of the app
    elapsed              creation -> close (wall clock); agent_active = sum of agent call durations"""
    import time
    p = store.project(pid)
    events = store.events(pid)
    first = store.db.execute("SELECT MIN(at) FROM events WHERE kind='owner_action'").fetchone()[0]
    partial = first is None or p['created'] < first
    since = time.strftime('%Y-%m-%d %H:%M', time.localtime(first)) if first else None
    owner = [e['detail'] for e in events if e['kind'] == 'owner_action' and e['detail'].get('channel') != 'dev']
    manual = [a for a in owner if a.get('action') in RECOVERY_ACTIONS and a.get('channel') != 'app']
    escape = [a for a in owner if a.get('channel') in ('cli', 'developer_cli')]
    closed = [e['at'] for e in events if e['kind'] == 'state' and e['detail'].get('to') == 'CLOSED']
    end = closed[-1] if closed else time.time()
    counted = lambda n: n if not partial else (f'{n} (기록: {since} 이후; 그 이전 UNKNOWN)' if since else 'UNKNOWN')
    return {
        'owner_interventions': counted(len(owner)),
        'owner_feedback_rounds': len(store.feedback(pid)),
        'rework_rounds': sum(e['kind'] == 'state' and e['detail'].get('to') == 'REWORK' for e in events),
        'verification_rounds': len(store.verifications(pid)),
        'manual_recovery': counted(len(manual)),
        'owner_escape': counted(len(escape)),
        'automatic_recoveries': sum(e['kind'] == 'recovery' for e in events),
        'elapsed_hours': round((end - p['created']) / 3600, 1),
        'agent_active_minutes': round(sum(e['detail'].get('seconds') or 0 for e in events if e['kind'] == 'call') / 60),
        'satisfaction': p['satisfaction'] if p['satisfaction'] is not None else 'UNKNOWN',
        'owner_review_minutes': 'UNKNOWN',
    }


def provider_record(store):
    """Measured history per execution engine on this PC, for the CEO's engine choices (experience ->
    better routing, without training). Final builds are judged by their verification outcome."""
    db = store.db
    rec = {}
    for name in ('claude', 'codex'):
        secs = sorted(json.loads(d).get('seconds') for (d,) in db.execute(
            "SELECT detail FROM events WHERE kind='call' AND detail LIKE ?", (f'%"provider": "{name}"%',))
            if json.loads(d).get('seconds') is not None)
        builds = db.execute(
            "SELECT v.verdict FROM verifications v JOIN artifacts a ON a.id = v.artifact_id "
            "JOIN agents g ON g.id = a.agent_id WHERE COALESCE("
            "(SELECT s.provider FROM stage_outputs s WHERE s.project_id = a.project_id "
            "AND s.iteration = a.iteration ORDER BY s.stage DESC LIMIT 1), g.provider) = ?",
            (name,)).fetchall()
        empty = db.execute("SELECT COUNT(*) FROM events WHERE kind='build_rejected' AND detail LIKE ?",
                           (f'%"provider": "{name}"%',)).fetchone()[0]
        label = 'Claude Code' if name == 'claude' else 'Codex'
        timeouts = db.execute("SELECT COUNT(*) FROM events WHERE kind='state' AND detail LIKE ? AND detail LIKE ?",
                              (f'%{label}:%', '%초과%')).fetchone()[0]
        quota = db.execute("SELECT COUNT(*) FROM events WHERE kind='provider_handoff' AND detail LIKE ?",
                           (f'%"preferred": "{name}"%',)).fetchone()[0]
        rec[name] = {'turns_with_duration': len(secs),
                     'median_turn_seconds': secs[len(secs) // 2] if secs else None,
                     'longest_turn_seconds': secs[-1] if secs else None,
                     'final_builds_verified': len(builds),
                     'final_builds_passed': sum(v == 'PASS' for (v,) in builds),
                     'empty_final_builds_rejected': empty,
                     'timeouts': timeouts,
                     'usage_limit_switches_away': quota}
    return rec
