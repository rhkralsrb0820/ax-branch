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


def _clock(at):
    return time.strftime('%H:%M:%S', time.localtime(at))


def _output(store, pid, project, index):
    """Latest recorded output of pipeline stage `index` in the current plan (None if not produced)."""
    row = store.output(pid, index, project.get('plan_version'))
    return row['output'] if row else None


def _stage_result(store, pid, project, index, count):
    out = _output(store, pid, project, index) or {}
    if index == count - 1:                       # the producer: what it delivered
        edits = out.get('edits') or []
        return (f'{len(edits)} edits · ' if edits else '') + str(out.get('summary') or '')[:100]
    return str((out.get('key_points') or [out.get('output') or ''])[0])[:100]


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

    def row(title, engine='-', mark='○', detail='', key=None, why='', task=''):
        # Agent card fields (key/why/task/result/last) come from the plan and recorded events only.
        result = dict(mark=mark, title=title, engine=engine, detail=detail, key=key or title, why=why, task=task,
                      result='', last='')
        pipeline.append(result)
        return result

    decisions = [e for e in events if e['kind'] == 'decision' and e['detail'].get('by') != 'engine']
    decision = decisions[-1]['detail'] if decisions else {}
    ceo = row('淸月 CEO', _engine(decision.get('by')), '✓' if decisions else '○', decision.get('what', ''),
              key='ceo', why='Owner의 목표를 해석하고 Agent와 파이프라인을 결정', task=decision.get('what', ''))
    if decisions:
        ceo['last'] = _clock(decisions[-1]['at'])
        ceo['result'] = f"plan v{project.get('plan_version') or '-'}"
    plan = project.get('plan') or {}
    stages = plan.get('pipeline', [])
    running_detail = f'{status} · {elapsed} / {timeout} · 마지막 활동 {activity}'
    calls = [e for e in current if e['kind'] in ('call_start', 'call', 'call_failed')]
    for index, stage in enumerate(stages):
        role = stage.get('agent_role', '')
        item = row(role, _engine(stage.get('provider')), key=f'stage:{index}', why=stage.get('why') or stage.get('name', ''),
                   task=stage.get('name', ''))
        history = [e for e in calls if e['detail'].get('who') == role]
        if not history:
            continue
        latest = history[-1]
        d = latest['detail']
        item['last'] = activity if active and rec.get('agent') == role else _clock(latest['at'])
        if latest['kind'] == 'call':
            item.update(mark='✓', engine=_engine(d.get('provider')),
                        detail='Completed · ' + _duration(d.get('seconds')))
            item['result'] = _stage_result(store, pid, project, index, len(stages)) or item['detail']
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
    item = row('Verification Agent', key='verification', why='산출물을 독립적으로 검증 (만든 Agent와 분리)',
               task='수용 기준 · 결정적 검사 · 실행 검증')
    if verified:
        d = verified[-1]
        verdict = d.get('verdict', '')
        item.update(mark='✓' if verdict == 'PASS' else '✗', engine=_engine(d.get('provider')),
                    detail=verdict + ' · ' + _engine(d.get('provider')), result=verdict)
    elif calls and calls[-1]['kind'] == 'call_start' and calls[-1]['detail'].get('who') == 'Verification' and active:
        item.update(mark='●', engine=_engine(calls[-1]['detail'].get('preferred')), detail=running_detail)
    item = row('Runtime Acceptance (LOCAL)', 'Local', key='runtime', why='실제로 실행해 Owner 사용 경로를 확인 (AI 아님)',
               task='실행 검증')
    if active and rec['stage'] == 'VERIFYING' and runtime:
        item.update(mark='●', detail=detail)
    elif verified:
        verifications = store.verifications(pid)
        checks = verifications[-1]['checks'].get('runtime') if verifications else None
        if checks is not None:
            steps = checks.get('steps', [])
            passed = sum(bool(step.get('ok')) for step in steps)
            item.update(mark='✓' if checks.get('ok') else '✗', detail=f'{passed} / {len(steps)} checks passed')
            item['result'] = item['detail']
    item = row('OWNER_REVIEW', key='owner', why='Owner가 결과를 확인하고 피드백 또는 마무리', task='Owner 확인')
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


def records(store, pid, key):
    """The explicit collaboration record of one agent card: claims, evidence, counterpoints, decisions and
    verification as RECORDED — never hidden reasoning (none is stored)."""
    project = store.project(pid)
    plan = project.get('plan') or {}
    stages = plan.get('pipeline', [])
    out = []

    def section(title, items):
        items = [str(i) for i in items if i]
        if items:
            out.append(f'■ {title}')
            out.extend(f'  - {i}' for i in items)

    if key == 'ceo':
        out.append('淸月 AI CEO — 해석 (Interpretation)')
        out.append(str(plan.get('interpretation') or '-'))
        section('수용 기준 (Acceptance criteria)', plan.get('acceptance_criteria') or [])
        section('결정 (Decision · 근거)', [f"[{_clock(e['at'])}] {e['detail'].get('what', '')} — {str(e['detail'].get('why', ''))[:300]}"
                                        for e in store.events(pid, {'decision'})[-15:]])
        section('고용한 Agent (Why hired)', [f"{s.get('agent_role')} ({_engine(s.get('provider'))}): {s.get('why') or s.get('name')}"
                                            for s in stages])
    elif key.startswith('stage:'):
        index = int(key.split(':')[1])
        stage = stages[index] if index < len(stages) else {}
        o = _output(store, pid, project, index)
        out.append(f"{stage.get('agent_role', '-')} · {_engine(stage.get('provider'))}")
        out.append(f"고용 이유 (Why hired): {stage.get('why') or '-'}")
        out.append(f"지시 (Task): {stage.get('instructions', '-')}")
        if o is None:
            out.append('아직 기록된 결과가 없습니다.')
        elif index == len(stages) - 1:
            out.append('')
            out.append(f"■ 산출물 요약 (Claim): {o.get('summary') or '-'}")
            out.append(f"■ 이전 버전 대비 변경: {o.get('changes_from_previous') or '-'}")
            if o.get('edits'):
                out.append(f"■ 수정(edit) {len(o['edits'])}건")
        else:
            out.append('')
            out.append('■ 주장 / 작업 결과 (Claim)')
            out.append(str(o.get('output') or '-')[:4000])
            section('핵심 (Key points)', o.get('key_points') or [])
            section('근거 (Evidence)', o.get('evidence') or [])
            section('반론 · 위험 (Counterargument)', o.get('counterpoints') or [])
    elif key == 'verification':
        for v in store.verifications(pid)[-2:]:
            r = v['result']
            out.append(f"■ 검증 {v['iteration']}회차: {v['verdict']} ({_engine(v['provider'])}) · 결정적 검사 "
                       f"{'통과' if v['checks'].get('ok') else '실패'}")
            out.extend(f"  {'✓' if c.get('met') else '✗'} {c.get('criterion')} — {str(c.get('evidence', ''))[:300]}"
                       for c in r.get('criteria', []))
            out.extend(f"  [{f.get('severity')}] {f.get('issue')} — 근거: {str(f.get('evidence', ''))[:300]}"
                       for f in r.get('findings', []))
    elif key == 'runtime':
        verifications = store.verifications(pid)
        rt = verifications[-1]['checks'].get('runtime') if verifications else None
        if not rt:
            out.append('아직 실행 검증 기록이 없습니다.')
        else:
            out.append(f"■ 실행 검증 ({rt.get('mode')}): {'통과' if rt.get('ok') else '실패'}")
            out.extend(f"  {'OK  ' if s.get('ok') else 'FAIL'} {s.get('name')}"
                       + (f" — {', '.join(s['problems'])}" if s.get('problems') else '') for s in rt.get('steps', []))
    elif key == 'owner':
        section('Owner 피드백', [f"{f['iteration']}회차 ({f['verdict']}): {f['text']}" for f in store.feedback(pid)])
        section('외부 연결 승인', [f"{a['subject']}: {a['status']}" for a in store.approvals(pid)])
    return '\n'.join(out) or '기록 없음'


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
