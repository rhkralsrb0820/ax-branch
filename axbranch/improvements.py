"""Improvement candidates for AX Branch's own operating rules, registered from repeated failures (evidence only).

CANDIDATE -> EVAL_READY -> EVALUATING -> COMPARED -> APPLIED -> ROLLED_BACK; REJECTED any time before APPLIED.
- A candidate is registered only when the engine recorded a repeated failure signature (same failure code twice).
- Its proposed rule is the forced strategy change after which that project later PASSED (model-written, unverified).
- An evaluation runs the source goals in fresh projects, baseline vs. variant, with experience retrieval disabled.
- Only an APPLIED rule reaches the CEO (planning and strategy), as reference text that fixed governance outranks.
  Applying needs a recorded comparison in which the variant did not do worse AND the Owner.
This is retrieval of approved operating notes, never model training; no quality gain is claimed by applying one."""
import hashlib
import json
import time
from pathlib import Path

from .state import ACTIVE, Rejected

STATES = ('CANDIDATE', 'EVAL_READY', 'EVALUATING', 'COMPARED', 'APPLIED', 'ROLLED_BACK', 'REJECTED')
LABEL = {'CANDIDATE': '후보', 'EVAL_READY': '평가 준비됨', 'EVALUATING': '평가 실행 중', 'COMPARED': '비교 완료',
         'APPLIED': '적용됨', 'ROLLED_BACK': '되돌림', 'REJECTED': '거절됨'}
MAX_CASES = 2
NOTE = ('Owner-approved operating notes from earlier repeated failures. Reference only: the fixed governance, the '
        'acceptance criteria and verification outrank them; they never authorize skipping a check or an approval.')


def _db(store):
    store.db.execute('CREATE TABLE IF NOT EXISTS improvements(id TEXT PRIMARY KEY, signature TEXT UNIQUE NOT NULL, '
                     'state TEXT NOT NULL, data TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL)')
    return store.db


def all_(store):
    return [{'id': r['id'], 'signature': r['signature'], 'state': r['state'], 'label': LABEL[r['state']],
             'created': r['created'], 'updated': r['updated'], **json.loads(r['data'])}
            for r in _db(store).execute('SELECT * FROM improvements ORDER BY updated DESC')]


def get(store, cid):
    found = [c for c in all_(store) if c['id'] == cid]
    if not found:
        raise Rejected(f'개선 후보가 없습니다: {cid}')
    return found[0]


def _save(store, c, state, what, by):
    data = {k: v for k, v in c.items() if k not in ('id', 'signature', 'state', 'label', 'created', 'updated')}
    data['history'] = data.get('history', []) + [{'at': time.time(), 'from': c['state'], 'to': state, 'what': what, 'by': by}]
    with store.tx():
        _db(store).execute('UPDATE improvements SET state=?, data=?, updated=? WHERE id=?',
                           (state, json.dumps(data, ensure_ascii=False), time.time(), c['id']))
    return get(store, c['id'])


def evaluation_projects(store):
    """Projects created to evaluate a candidate: kept with all their records, listed under the candidate instead of
    the Owner's work list."""
    return {r[0] for r in store.db.execute("SELECT DISTINCT project_id FROM events WHERE kind='improvement_policy'")}


def with_states(store, candidates):
    for c in candidates:
        for p in (c.get('eval') or {}).get('projects', []):
            proj = store.project(p['project'])
            vs = store.verifications(p['project'])
            p.update(state=proj['state'], last_verdict=vs[-1]['verdict'] if vs else None)
    return candidates


def _policy(store, pid):
    found = store.events(pid, {'improvement_policy'})
    return found[-1]['detail'] if found else None


def observe(store, pid):
    """After a run stops: register repeated failure signatures, attach a resolution, finish an evaluation. Idempotent."""
    policy = _policy(store, pid)
    if policy:                                    # an evaluation project never registers evidence of its own
        return _maybe_compare(store, policy['candidate'])
    events = store.events(pid, {'decision'})
    passes = [v for v in store.verifications(pid) if v['verdict'] == 'PASS' and v['checks'].get('ok')]
    for i, e in enumerate(events):
        if e['detail'].get('what') != 'repeated failure signature':
            continue
        sig = e['detail']['why']
        cid = 'I-' + hashlib.sha256(sig.encode('utf-8')).hexdigest()[:8]
        with store.tx():
            _db(store).execute('INSERT OR IGNORE INTO improvements VALUES(?,?,?,?,?,?)',
                               (cid, sig, 'CANDIDATE', json.dumps({'evidence': [], 'history': []}), time.time(), time.time()))
        c = get(store, cid)
        changed = False
        if not any(x['event'] == e['id'] and x['project'] == pid for x in c['evidence']):
            c['evidence'].append({'project': pid, 'event': e['id'], 'at': e['at']})
            changed = True
        strategy = next((s for s in reversed(events[:i]) if s['detail'].get('what', '').startswith('strategy:')), None)
        passed = next((v for v in passes if v['created'] > e['at']), None)
        if strategy and passed and not c.get('proposal'):
            c['proposal'] = {'rule': f"반복 실패 '{sig}'가 나타나면 검토할 방법: {strategy['detail'].get('why', '')[:600]}",
                             'source': {'project': pid, 'strategy_event': strategy['id'], 'pass_verification': passed['id']},
                             'origin': 'strategy change recorded before a later PASS (model-written, unverified)'}
            changed = True
        if changed:
            _save(store, c, c['state'], 'evidence recorded', 'engine')


def prepare_eval(store, cid, by='owner'):
    c = get(store, cid)
    if c['state'] != 'CANDIDATE':
        raise Rejected(f"'{LABEL[c['state']]}' 상태에서는 평가를 준비할 수 없습니다.")
    if not c.get('proposal'):
        raise Rejected('이 실패를 해결한 기록이 아직 없어 비교할 개선안이 없습니다. 같은 실패가 해결되면 자동으로 개선안이 붙습니다.')
    from .actions import TASK_BUDGETS
    sources = list(dict.fromkeys(x['project'] for x in c['evidence']))[:MAX_CASES]
    per = TASK_BUDGETS['general']['max_reported_tokens']
    c['eval'] = {'cases': [{'source': s, 'goal': store.project(s)['goal']} for s in sources],
                 'arms': ['baseline', 'variant'], 'experience': 'disabled in every evaluation project',
                 'max_tokens_per_project': per, 'max_tokens_total': per * 2 * len(sources),
                 'pass_rule': 'variant passes at least as often as baseline and the signature does not recur more often'}
    return _save(store, c, 'EVAL_READY', 'evaluation prepared', by)


def start_eval(store, engine_factory, specs, cid, launch, approved=False, by='owner'):
    """Owner-approved: create baseline/variant projects per case and launch them (real model calls)."""
    c = get(store, cid)
    if c['state'] != 'EVAL_READY':
        raise Rejected('평가 준비가 끝난 후보만 실행할 수 있습니다.')
    if not approved:
        raise Rejected(f"평가 실행은 실제 모델을 호출합니다 (최대 {c['eval']['max_tokens_total']:,} 토큰). Owner 승인이 필요합니다.")
    from . import actions, departments
    projects = []
    for case in c['eval']['cases']:
        src = case['source']
        deps = [d['id'] for d in departments.attached(store, src)]
        engine = engine_factory()
        try:
            folder = engine.workspace / 'projects' / src / 'inputs'
            files = [str(f) for f in folder.iterdir() if f.is_file()] if folder.is_dir() else []
        finally:
            engine.store.close()
        for arm in c['eval']['arms']:
            pid = actions.start(store, engine_factory, case['goal'], [d for d in deps if d in specs], specs, files,
                                'improvement-eval')
            engine = engine_factory()
            try:
                engine.configure_experience(pid, enabled=False)
            finally:
                engine.store.close()
            store.event(pid, 'improvement_policy', candidate=cid, arm=arm, source=src)
            projects.append({'source': src, 'arm': arm, 'project': pid})
    c['eval']['projects'] = projects
    c = _save(store, c, 'EVALUATING', 'evaluation started (Owner-approved)', by)
    for p in projects:
        launch(p['project'])
    return c


def _outcome(store, pid, sig):
    from .engine import failure_code
    p, vs = store.project(pid), store.verifications(pid)
    return {'project': pid, 'state': p['state'],
            'passed': bool(vs and vs[-1]['verdict'] == 'PASS' and vs[-1]['checks'].get('ok')),
            'recurred': sum(1 for v in vs if v['verdict'] == 'FAIL' and failure_code(v) == sig)}


def _maybe_compare(store, cid):
    c = get(store, cid)
    if c['state'] != 'EVALUATING' or any(store.project(p['project'])['state'] in ACTIVE for p in c['eval']['projects']):
        return c
    arms = {}
    for p in c['eval']['projects']:
        arms.setdefault(p['arm'], []).append(_outcome(store, p['project'], c['signature']))
    total = {a: {'passed': sum(o['passed'] for o in os_), 'n': len(os_), 'recurred': sum(o['recurred'] for o in os_),
                 'projects': os_} for a, os_ in arms.items()}
    b, v = total['baseline'], total['variant']
    c['comparison'] = {**total, 'not_worse': v['passed'] >= b['passed'] and v['recurred'] <= b['recurred'],
                       'better': v['passed'] > b['passed'] or v['recurred'] < b['recurred'],
                       'limits': f"{b['n']}건씩의 작은 비교이며 통계적 효과 검증이 아닙니다."}
    return _save(store, c, 'COMPARED', 'comparison recorded', 'engine')


def approve(store, cid, by='owner'):
    c = get(store, cid)
    if c['state'] != 'COMPARED':
        raise Rejected('비교 결과가 기록된 후보만 적용할 수 있습니다. 검증되지 않은 후보는 운영 규칙에 넣지 않습니다.')
    if not c['comparison']['not_worse']:
        raise Rejected('개선안이 기준보다 나빴습니다. 적용하지 않습니다 (거절하거나 다른 해결 기록을 기다리세요).')
    return _save(store, c, 'APPLIED', 'applied to CEO planning/strategy context', by)


def rollback(store, cid, by='owner'):
    c = get(store, cid)
    if c['state'] != 'APPLIED':
        raise Rejected('적용된 후보만 되돌릴 수 있습니다.')
    return _save(store, c, 'ROLLED_BACK', 'removed from CEO context', by)


def reject(store, cid, why='', by='owner'):
    c = get(store, cid)
    if c['state'] in ('APPLIED', 'REJECTED', 'EVALUATING'):
        raise Rejected(f"'{LABEL[c['state']]}' 상태는 거절할 수 없습니다" + (' (적용된 것은 되돌리기를 사용하세요).' if c['state'] == 'APPLIED' else '.'))
    return _save(store, c, 'REJECTED', f'rejected: {why[:300]}', by)


def for_project(store, pid):
    """The rules this project's CEO sees: APPLIED ones, adjusted by an evaluation arm (baseline omits, variant adds)."""
    policy = _policy(store, pid) or {}
    rules = [c for c in all_(store) if (c['state'] == 'APPLIED' and not (policy.get('arm') == 'baseline' and
                                                                          policy.get('candidate') == c['id']))
             or (policy.get('arm') == 'variant' and policy.get('candidate') == c['id'])]
    return [{'id': c['id'], 'signature': c['signature'], 'rule': c['proposal']['rule']} for c in rules if c.get('proposal')]


def _base_model(run):
    """The base model a run declares (metrics.json or a PEFT adapter_config.json it wrote), else UNKNOWN."""
    if isinstance(run.get('metrics'), dict):
        for k in ('base_model', 'model', 'model_name'):
            if isinstance(run['metrics'].get(k), str):
                return run['metrics'][k]
    for f in run.get('files', []):
        if f['path'].endswith('adapter_config.json'):
            try:
                return json.loads((Path(run['dir']) / f['path']).read_text(encoding='utf-8')).get('base_model_name_or_path') or 'UNKNOWN'
            except (OSError, ValueError, KeyError):
                pass
    return 'UNKNOWN'


def training_runs(store, limit=20):
    """Real training runs of generated results (engine._training_run), split into run / result / evaluation / applied.
    The metrics are the training script's own dev-split numbers; the independent check is the verification verdict."""
    out = []
    rows = store.db.execute("SELECT project_id, at, detail FROM events WHERE kind='training_run' ORDER BY id DESC LIMIT ?", (limit,))
    for pid, at, detail in rows.fetchall():
        run = json.loads(detail)
        verdicts = [v for v in store.verifications(pid) if v['artifact_id'] == run.get('artifact')]
        project = store.project(pid)
        delivered = bool(verdicts and verdicts[-1]['verdict'] == 'PASS' and project['state'] in ('OWNER_REVIEW', 'PENDING_CLOSE', 'CLOSED'))
        inputs = [f for e in store.events(pid, {'owner_inputs'}) for f in e['detail'].get('files', [])]
        uses = [e['detail'] for e in store.events(pid, {'trained_output_used'}) if e['detail'].get('artifact') == run.get('artifact')]
        count = lambda *kinds: sum(1 for u in uses if u.get('use') in kinds)
        out.append({
            'project': pid, 'at': at, 'artifact': run.get('artifact'),
            'run': {'status': '재사용(이미 끝난 학습)' if run.get('reused') else ('완료' if run.get('ok') else '실패'),
                    'why': run.get('why', ''), 'seconds': run.get('seconds'), 'time_limit': run.get('time_limit'),
                    'pins': run.get('pins', [])},
            'inputs': [{'name': f.get('name') or f.get('path'), 'sha256': (f.get('sha256') or '')[:12]} for f in inputs][:10],
            'base_model': _base_model(run),
            'result': {'files': len(run.get('files', [])),
                       'adapter_files': [f['path'] for f in run.get('files', []) if 'adapter' in f['path'].lower()][:10]},
            'evaluation': {'self_reported_metrics': run.get('metrics'),
                           'independent_verification': verdicts[-1]['verdict'] if verdicts else '미검증'},
            # Three separate facts: files handed over, outputs actually given to a running program, effect measured.
            'delivered': ('Owner에게 결과 파일과 프로그램 전달됨 (모델 적용 완료를 뜻하지 않음)' if delivered else '전달 전'),
            'used': {'verification_runs': count('verification'), 'owner_runs': count('owner_run', 'owner_web_run'),
                     'note': '실행할 때 학습 출력을 프로그램 폴더(./outputs)에 제공한 횟수. 프로그램이 실제로 불러 썼는지는 검증 통과 여부로만 판단'},
            'effect': '미확인 — 학습하지 않은 기준과 비교한 평가가 없습니다 (학습 스크립트 자체 지표는 효과 확인이 아님)',
        })
    return out


def learning_paths(store):
    """What each learning path really does on this PC, from recorded state (no claimed effect)."""
    from . import training
    rows = store.db.execute("SELECT project_id, detail FROM events WHERE kind IN ('capability_decision') ORDER BY id DESC LIMIT 10").fetchall()
    venv, vpy = training.env_python()
    marker = venv / 'AXB_INSTALLED'
    runs = store.db.execute("SELECT detail FROM events WHERE kind='training_run'").fetchall()
    run_ok = sum(1 for (d,) in runs if json.loads(d).get('ok'))
    experience = store.db.execute("SELECT COUNT(*) FROM events WHERE kind='department_experience'").fetchone()[0]
    searches = store.db.execute("SELECT COUNT(*) FROM events WHERE kind='experience_search'").fetchone()[0]
    applied = [c['id'] for c in all_(store) if c['state'] == 'APPLIED']
    return [
        {'id': 'experience', 'name': '경험 검색 (RAG 방식)', 'status': '사용 중',
         'detail': f'경험 기록 {experience}건 · 검색 {searches}회. 모델 가중치는 바꾸지 않습니다.',
         'effect': '품질 개선 효과 미검증 (A/B 보류)'},
        {'id': 'rules', 'name': '승인된 개선 규칙', 'status': '사용 중' if applied else '적용된 규칙 없음',
         'detail': f"적용 {len(applied)}개{': ' + ', '.join(applied) if applied else ''}. 반복 실패 → 비교 평가 → Owner 승인 후에만 청월에게 전달.",
         'effect': '후보별 소규모 비교 결과만 있음'},
        {'id': 'lora', 'name': 'LoRA 학습 (생성 결과물용)',
         'status': '환경 설치됨' if vpy.is_file() and marker.is_file() else '환경 미설치',
         'detail': ('결과물이 모델 학습을 요구하면 무료 대안을 순서대로 실제 시도합니다: 로컬 CPU 소형 LoRA → 무료 클라우드 GPU(Owner 로그인 필요). '
                    f"최근 결정 {len(rows)}건: " + '; '.join(
                        f"{r['project_id']} {json.loads(r['detail']).get('status')}" for r in rows[:5]) if rows else
                    '결과물이 모델 학습을 요구하면 무료 대안(로컬 CPU 소형 LoRA → 무료 클라우드 GPU, Owner 로그인 필요)을 실제로 시도합니다. 아직 시도 기록 없음.'),
         'runs': f'학습 실행 기록 {len(runs)}건 (성공 {run_ok}건) — 아래 학습 기록 표',
         'effect': 'AX Branch 자신의 청월·제작 모델은 학습하지 않습니다'},
        {'id': 'finetune', 'name': 'AX Branch 모델 Fine-tuning', 'status': '미지원',
         'detail': '구독 CLI 모델은 가중치를 바꿀 수 없고, 유료 학습 API는 비용·인증 승인 대상입니다. 대안: 경험 검색과 승인된 개선 규칙.',
         'effect': '-'},
    ]
