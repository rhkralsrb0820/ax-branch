"""Local execution display. Liveness belongs to supervisor, never to the UI."""
import json
import time
from pathlib import Path

from . import supervisor


def _engine(value):
    return {'claude': 'Claude', 'codex': 'Codex', 'engine': 'Local',
            'local': 'Local', None: '-'}.get(value, value)


def _duration(value):
    if value is None:
        return '-'
    seconds = max(0, int(value))
    return f'{seconds // 60}m {seconds % 60:02d}s' if seconds >= 60 else f'{seconds}s'


def _brief(detail):
    return ', '.join(f'{k}={v}' for k, v in detail.items())[:100]


def view(workspace, store, pid):
    """Build a display from persisted events and the supervisor's current status."""
    rec = supervisor.status(workspace, store, pid)
    project = store.project(pid)
    events = store.events(pid)
    status = rec['status']
    active = status == 'ACTIVE'
    live = active and rec.get('call_elapsed') is not None
    agent = rec.get('agent') or '-'
    engine = _engine(rec.get('provider'))
    elapsed = _duration(rec.get('call_elapsed'))
    timeout = _duration(rec.get('call_timeout'))
    age = rec.get('last_meaningful_activity_age')
    activity = f'{age}초 전' if age is not None else '-'
    try:
        beat = json.loads((Path(workspace) / 'projects' / pid / 'HEARTBEAT.json').read_text(encoding='utf-8'))
        detail = str(beat.get('detail') or '') if isinstance(beat, dict) else ''
    except (OSError, ValueError):
        detail = ''
    runtime = detail.startswith('runtime:')
    task = f'없음 ({status})'
    if live:
        task = f'{agent} on {engine}'
    elif active:
        task = 'LOCAL — Runtime acceptance: ' + detail[len('runtime:'):].strip() if runtime else detail
    header = [
        ('프로젝트', pid), ('목표', project['goal'][:120]), ('단계', rec['stage']),
        ('상태', status + ' — ' + rec['reason']),
        ('에이전트 / 역할', agent if live else '마지막: ' + agent),
        ('엔진', engine if live or engine == '-' else '마지막: ' + engine),
        ('worker pid', rec.get('worker_pid')), ('provider pid', rec.get('provider_pid') if live else '-'),
        ('현재 작업', task), ('경과 / 제한', f'{elapsed} / {timeout}' if live else '-'),
        ('마지막 활동', activity), ('산출물', f"v{rec['artifact_version']}"),
        ('복구 횟수', rec['recovery_count']), ('다음 작업', rec['next_action']),
    ]
    header = [(label, '-' if value is None else str(value)) for label, value in header]
    boundary = max((i + 1 for i, e in enumerate(events)
                    if e['kind'] == 'state' and e['detail'].get('to') == 'STAFFING'), default=0)
    current = events[boundary:]
    pipeline = []

    def row(title, engine='-', mark='○', detail=''):
        result = dict(mark=mark, title=title, engine=engine, detail=detail)
        pipeline.append(result)
        return result

    decisions = [e['detail'] for e in events if e['kind'] == 'decision' and e['detail'].get('by') != 'engine']
    decision = decisions[-1] if decisions else {}
    row('淸月 CEO', _engine(decision.get('by')), '✓' if decisions else '○', decision.get('what', ''))
    stages = (project.get('plan') or {}).get('pipeline', [])
    running_detail = f'{status} · {elapsed} / {timeout} · 마지막 활동 {activity}'
    calls = [e for e in current if e['kind'] in ('call_start', 'call', 'call_failed')]
    for stage in stages:
        role = stage.get('agent_role', '')
        item = row(role, _engine(stage.get('provider')))
        history = [e for e in calls if e['detail'].get('who') == role]
        if not history:
            continue
        latest = history[-1]
        d = latest['detail']
        if latest['kind'] == 'call':
            item.update(mark='✓', engine=_engine(d.get('provider')),
                        detail='Completed · ' + _duration(d.get('seconds')))
        elif latest['kind'] == 'call_failed':
            item.update(mark='✗', detail=str(d.get('error', ''))[:80])
        else:
            running = active and rec.get('agent') == role        # the stage the supervisor sees running
            item.update(mark='●' if running else '!',
                        detail=running_detail if running else 'interrupted — ' + status)
    rejected = [e['detail'] for e in current if e['kind'] == 'build_rejected']
    if stages and rejected:
        pipeline[-1].update(mark='✗', detail='no deliverable: ' + str(rejected[-1].get('reason', '')))

    verified = [e['detail'] for e in current if e['kind'] == 'verification']
    item = row('Verification Agent')
    if verified:
        d = verified[-1]
        verdict = d.get('verdict', '')
        item.update(mark='✓' if verdict == 'PASS' else '✗', engine=_engine(d.get('provider')),
                    detail=verdict + ' · ' + _engine(d.get('provider')))
    elif calls and calls[-1]['kind'] == 'call_start' and calls[-1]['detail'].get('who') == 'Verification' and active:
        item.update(mark='●', engine=_engine(calls[-1]['detail'].get('preferred')), detail=running_detail)
    item = row('Runtime Acceptance (LOCAL)', 'Local')
    if active and rec['stage'] == 'VERIFYING' and runtime:
        item.update(mark='●', detail=detail)
    elif verified:
        verifications = store.verifications(pid)
        checks = verifications[-1]['checks'].get('runtime') if verifications else None
        if checks is not None:
            steps = checks.get('steps', [])
            passed = sum(bool(step.get('ok')) for step in steps)
            item.update(mark='✓' if checks.get('ok') else '✗', detail=f'{passed} / {len(steps)} checks passed')
    item = row('OWNER_REVIEW')
    if project['state'] == 'OWNER_REVIEW':
        item.update(mark='●', detail='Owner 확인 대기')
    elif project['state'] in ('PENDING_CLOSE', 'ARCHIVE_PENDING_APPROVAL', 'ARCHIVING', 'CLOSED'):
        item['mark'] = '✓'

    timeline = []
    for event in events[-30:]:
        kind, d = event['kind'], event['detail']
        actor, text = kind, _brief(d)
        who = str(d.get('who', '-'))
        if kind == 'decision':
            actor, text = ('ENGINE' if d.get('by') == 'engine' else '淸月 CEO'), '→ ' + str(d.get('what', ''))
        elif kind == 'agent_hired':
            actor, text = '淸月 CEO', '→ hired ' + str(d.get('role', ''))
        elif kind == 'call_start':
            actor, text = who, 'started · ' + _engine(d.get('preferred'))
        elif kind == 'call':
            actor, text = who, 'completed · ' + _duration(d.get('seconds')) + ' · ' + _engine(d.get('provider'))
        elif kind == 'call_failed':
            actor, text = who, 'failed: ' + str(d.get('error', ''))[:80]
        elif kind == 'provider_handoff':
            actor, text = who, f"engine switched {d.get('preferred', '-')} → {d.get('used', '-')}"
        elif kind == 'state':
            actor, text = 'STATE', f"{d.get('frm', '-')} → {d.get('to', '-')}"
            if d.get('reason'):
                text += ' (' + str(d['reason'])[:80] + ')'
        elif kind == 'verification':
            actor, text = 'Verification Agent', f"{d.get('verdict', '')} (round {d.get('iteration', '-')}, {_engine(d.get('provider'))})"
        elif kind == 'build_rejected':
            actor, text = 'LOCAL', 'build rejected: ' + str(d.get('reason', ''))
        elif kind == 'edits_applied':
            actor, text = 'LOCAL', f"{d.get('count', '-')} edits applied to v{d.get('base_version', '-')}"
        elif kind == 'recovery':
            actor, text = 'SUPERVISOR', f"recovery: {d.get('action', '')} (attempt {d.get('attempt', '-')})"
        elif kind == 'recovery_replan':
            actor, text = '淸月 CEO', 'recovery re-plan'
        elif kind == 'approval_requested':
            actor, text = 'GATE', 'approval asked: ' + str(d.get('subject', ''))
        elif kind == 'approval_decided':
            actor, text = 'OWNER', f"{d.get('subject', '')} {d.get('status', '')}"
        elif kind in ('approval_reused', 'permission_granted'):
            actor, text = 'GATE', kind + ': ' + _brief(d)
        elif kind == 'owner_feedback':
            actor, text = 'OWNER', str(d.get('text', ''))[:80]
        elif kind == 'owner_action':
            actor, text = 'OWNER', f"{d.get('action', '')} via {d.get('channel', '')}"
        elif kind == 'session':
            actor, text = 'LOCAL', f"engine session started (pid {d.get('os_pid', '-')})"
        at = time.strftime('%H:%M:%S', time.localtime(event['at']))
        timeline.append(dict(at=at, actor=actor, text=text))
        if kind == 'agent_hired':
            timeline.append(dict(at=at, actor=actor, text='Assigned engine: ' + _engine(d.get('provider'))))
    return dict(header=header, pipeline=pipeline, timeline=timeline)


def render(v):
    """Plain text suitable for a Tk Text widget, with oldest events first."""
    lines = ['━ 실행 현황 (로컬 상태 · AI 호출 없음) ━']
    lines.extend(f'{label}: {value}' for label, value in v['header'])
    lines.append('━ 파이프라인 ━')
    for row in v['pipeline']:
        lines.append(f"{row['mark']} {row['title']}")
        parts = ([f"Engine: {row['engine']}"] if row['engine'] else [])
        if row['detail']:
            parts.append(row['detail'])
        if parts:
            lines.append('    ' + ' · '.join(parts))
    lines.append('━ 타임라인 ━')
    lines.extend(f"[{row['at']}] {row['actor']} {row['text']}" for row in v['timeline'])
    return '\n'.join(lines)
