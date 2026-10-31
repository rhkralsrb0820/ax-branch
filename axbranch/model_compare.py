"""Before/after-training comparison of a verified TEXT-CLASSIFICATION result (the only supported task).

Supported scope (stated, not implied wider):
- a verified bundle with a successful training run (engine._training_run) and a `predict.py` following CONTRACT;
- evaluation data: the run's ./outputs/data/test.csv with a `text` column and a `label` or `category` column;
  training-side data for the leakage check: ./outputs/data/train.csv (+ dev.csv when present).
Everything that decides the outcome is fixed at preparation and recorded (spec + its hash): result version, model
identities (file hashes from `predict.py --describe`), evaluation inputs and answers (hashes), source / split files,
metrics, the decision rule and the limits. Answers stay with AX Branch (comparisons/<id>/answers.jsonl); the predictor
only ever receives ids and texts. Both arms run in the existing isolated runner (AppContainer, no network, the
pinned training stack read-only), are checked for missing / duplicate / unknown ids and malformed lines, and are
scored by THIS module's code - never by numbers a model reports. One arm failing or an input/model changing after
preparation leaves the comparison incomplete. An effect is "confirmed in this evaluation" only when the run is
complete, the trained arm is better by the rule, no train/eval text overlap was found and the predictor is not a
fixed test fixture; it is never a general quality claim. Applying a model to later work is NOT connected here."""
import csv
import hashlib
import io
import json
import shutil
import tempfile
import time
import uuid
from pathlib import Path

from . import artifacts, isolation, sandbox, training
from .state import Busy, Rejected, run_lock

SUPPORTED = ('text classification only: CSV with a text column and a label/category column; the result provides '
             'predict.py (--describe, --model baseline|trained --input --output)')
CONTRACT = ('For a trained classification result, ship predict.py in the bundle: `python predict.py --describe` prints '
            'one JSON object {"baseline": {"name": str, "files": [bundle-relative paths]}, "trained": {"name": str, '
            '"base_model": str, "files": [...]}}; `python predict.py --model baseline|trained --input X --output Y` '
            'reads JSON lines {"id","text"} from X and writes one JSON line {"id","label"} per input to Y, using only '
            'the files it described (./outputs from training). It never trains, downloads or reads labels.')
ARMS = ('baseline', 'trained')
LIMITS = {'seconds_per_arm': 900, 'describe_seconds': 120, 'max_samples': 5000}
RULE = {'primary': 'macro_f1', 'min_delta': 0.01,
        'text': 'trained better if macro-F1 is higher by at least 0.01; worse if lower by at least 0.01; otherwise same'}


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _canon(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()


def _norm(text):
    return ' '.join(str(text).lower().split())


def _folder(engine, pid, cid):
    return engine.workspace / 'projects' / pid / 'comparisons' / cid


def read_labelled(path):
    """[(text, label)] from a CSV with `text` and `label` (or `category`) columns."""
    rows = list(csv.DictReader(io.StringIO(Path(path).read_text(encoding='utf-8-sig'))))
    if not rows:
        raise Rejected(f'평가 자료가 비어 있습니다: {Path(path).name}')
    label = next((c for c in ('label', 'category') if c in rows[0]), None)
    if 'text' not in rows[0] or label is None:
        raise Rejected(f'지원하지 않는 자료 형식입니다({Path(path).name}): text 열과 label 또는 category 열이 필요합니다.')
    return [(r['text'], r[label]) for r in rows], label


def _source(engine, pid):
    artifact = engine._verified(pid)
    trained = engine._trained(artifact)
    if trained is None:
        raise Rejected('이 결과물에는 성공한 학습 실행 기록이 없어 학습 전후를 비교할 수 없습니다.')
    if 'predict.py' not in {rel for rel, _, _ in artifacts.files_of(artifact)}:
        raise Rejected('이 결과물에는 비교용 예측 명령(predict.py)이 없습니다. 같은 프로젝트에 "학습 전후 비교용 '
                       'predict.py를 추가해 달라"고 수정 요청을 보내면 비교할 수 있습니다. 생성된 결과물은 직접 고치지 않습니다.')
    return artifact, trained


def _run(engine, artifact, trained, args, timeout, input_file=None):
    """One predictor call in the existing isolated runner. Returns (exit, output, predictions text or None, seconds)."""
    with tempfile.TemporaryDirectory(prefix='axb-compare-', ignore_cleanup_errors=True) as cwd:
        target = Path(cwd)
        artifacts.materialize(artifact, target)
        engine._copy_inputs(artifact['path'], target)
        shutil.copytree(trained, target / 'outputs', dirs_exist_ok=True)
        if input_file:
            shutil.copyfile(input_file, target / 'eval_inputs.jsonl')
        manifest = isolation.Manifest(purpose='before/after training comparison', artifact_sha256=artifact['sha256'],
                                      lifetime_seconds=timeout)
        started = time.monotonic()
        code, out = sandbox.run([str(training.env_python()[1]), '-E', '-s', '-B', '-X', 'utf8', 'predict.py', *args],
                                cwd, timeout, isolate=manifest)
        seconds = round(time.monotonic() - started, 2)
        pred = target / 'predictions.jsonl'
        return code, out, pred.read_text(encoding='utf-8', errors='replace') if pred.is_file() else None, seconds


def _model_files(artifact, trained, files):
    """{path: sha256} for files a predictor described; ./outputs/... come from the training run, others from the bundle."""
    bundle = {rel: sha for rel, _, sha in artifacts.files_of(artifact)}
    out = {}
    for f in files:
        rel = Path(str(f)).as_posix()
        if rel.startswith('outputs/') and (Path(trained) / rel[len('outputs/'):]).is_file():
            out[rel] = _sha(Path(trained) / rel[len('outputs/'):])
        elif rel in bundle:
            out[rel] = bundle[rel]
        else:
            raise Rejected(f'예측 명령이 밝힌 모델 파일이 없습니다: {rel}')
    return out


def prepare(engine, pid, by='owner'):
    """Fix and record everything the comparison depends on. Runs only `predict.py --describe` (isolated)."""
    artifact, trained = _source(engine, pid)
    trained = Path(trained)
    if isolation.training_runtime() is None:
        raise Rejected(training.MISSING_ENV.format(path=training.env_python()[0]))
    eval_path = trained / 'data' / 'test.csv'
    if not eval_path.is_file():
        raise Rejected('학습 출력에 평가 자료(outputs/data/test.csv)가 없습니다. 지원 범위: ' + SUPPORTED)
    rows, label_col = read_labelled(eval_path)
    if len(rows) > LIMITS['max_samples']:
        raise Rejected(f"평가 자료가 {len(rows)}건으로 한도({LIMITS['max_samples']}건)를 넘습니다.")
    code, out, _, _ = _run(engine, artifact, trained, ['--describe'], LIMITS['describe_seconds'])
    try:
        described = json.loads([ln for ln in out.strip().splitlines() if ln.startswith('{')][-1])
        arms = {a: {'name': str(described[a]['name']), 'base_model': str(described[a].get('base_model', '')),
                    'files': _model_files(artifact, trained, described[a]['files'])} for a in ARMS}
    except Rejected:
        raise
    except Exception:
        raise Rejected(f'predict.py --describe가 계약대로 응답하지 않았습니다(종료 코드 {code}): {out[-300:]}') from None
    if arms['baseline']['files'] == arms['trained']['files']:
        raise Rejected('기준 모델과 학습 모델의 파일이 같습니다. 비교할 수 없습니다.')
    train_side = [p for p in (trained / 'data' / 'train.csv', trained / 'data' / 'dev.csv') if p.is_file()]
    seen = {_norm(t) for p in train_side for t, _ in read_labelled(p)[0]} if train_side else None
    texts = [_norm(t) for t, _ in rows]
    leakage = ({'checked': False, 'overlap': None, 'note': '학습 자료를 찾지 못해 학습·평가 자료 중복을 확인할 수 없습니다.'}
               if seen is None else
               {'checked': True, 'overlap': sum(1 for t in texts if t in seen),
                'note': '정규화한 문장(소문자·공백 정리)이 학습/개발 자료와 같은 평가 샘플 수'})
    leakage['eval_internal_duplicates'] = len(texts) - len(set(texts))
    cid = 'C-' + time.strftime('%Y%m%d') + '-' + uuid.uuid4().hex[:6]
    folder = _folder(engine, pid, cid)
    folder.mkdir(parents=True)
    ids = [f'e{i:05d}' for i in range(len(rows))]
    (folder / 'inputs.jsonl').write_text(''.join(json.dumps({'id': i, 'text': t}, ensure_ascii=False) + '\n'
                                                 for i, (t, _) in zip(ids, rows)), encoding='utf-8')
    (folder / 'answers.jsonl').write_text(''.join(json.dumps({'id': i, 'label': y}, ensure_ascii=False) + '\n'
                                                  for i, (_, y) in zip(ids, rows)), encoding='utf-8')
    extra = {name: _sha(trained / name) for name in ('split.json', 'data/raw/SOURCE.json') if (trained / name).is_file()}
    spec = {'cid': cid, 'project': pid, 'task': 'text classification', 'supported': SUPPORTED,
            'artifact': {'id': artifact['id'], 'version': artifact['iteration'], 'sha256': artifact['sha256']},
            'training_dir': str(trained), 'arms': arms, 'fixture': bool(described.get('fixture')),
            'evaluation': {'source': 'outputs/data/test.csv', 'source_sha256': _sha(eval_path), 'label_column': label_col,
                           'samples': len(rows), 'labels': sorted({y for _, y in rows}),
                           'inputs_sha256': _sha(folder / 'inputs.jsonl'), 'answers_sha256': _sha(folder / 'answers.jsonl'),
                           'split_and_source_files': extra,
                           'training_side': [str(p.relative_to(trained).as_posix()) for p in train_side]},
            'leakage': leakage, 'metrics': ['accuracy', 'macro_f1', 'errors', 'seconds'], 'rule': RULE, 'limits': LIMITS,
            'prepared_by': by, 'prepared_at': time.time()}
    (folder / 'spec.json').write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding='utf-8')
    engine.store.event(pid, 'comparison_prepared', cid=cid, spec=spec, spec_sha256=_canon(spec))
    return view(engine, pid, cid)


def _spec(engine, pid, cid):
    found = [e['detail'] for e in engine.store.events(pid, {'comparison_prepared'}) if e['detail']['cid'] == cid]
    if not found:
        raise Rejected(f'비교 준비 기록이 없습니다: {cid}')
    return found[-1]


def changes(engine, pid, d):
    """What changed since preparation (empty = nothing)."""
    spec, problems = d['spec'], []
    if _canon(spec) != d['spec_sha256']:
        problems.append('비교 명세 기록이 바뀜')
    artifact = next((a for a in engine.store.artifacts(pid) if a['id'] == spec['artifact']['id']), None)
    if artifact is None or artifact['sha256'] != spec['artifact']['sha256'] or artifacts.problems(artifact):
        problems.append('결과물 버전이 바뀜')
    folder = _folder(engine, pid, spec['cid'])
    for name, key in (('inputs.jsonl', 'inputs_sha256'), ('answers.jsonl', 'answers_sha256')):
        if not (folder / name).is_file() or _sha(folder / name) != spec['evaluation'][key]:
            problems.append(f'평가 {"입력" if name.startswith("inputs") else "정답"}이 바뀜')
    trained = Path(spec['training_dir'])
    if not (trained / 'data' / 'test.csv').is_file() or _sha(trained / 'data' / 'test.csv') != spec['evaluation']['source_sha256']:
        problems.append('평가 자료 원본이 바뀜')
    if artifact is not None and not problems:
        for arm, info in spec['arms'].items():
            try:
                if _model_files(artifact, trained, list(info['files'])) != info['files']:
                    problems.append(f'{arm} 모델 파일이 바뀜')
            except Rejected:
                problems.append(f'{arm} 모델 파일이 없어짐')
    return problems


def check_predictions(text, ids):
    """(predicted {id: label}, problems). Missing, duplicate, unknown ids and malformed lines are problems."""
    got, problems, dup, unknown, bad = {}, [], 0, 0, 0
    wanted = set(ids)
    for line in (text or '').splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            i, y = row['id'], row['label']
            if not isinstance(i, str) or not isinstance(y, str):
                raise TypeError
        except (ValueError, KeyError, TypeError):
            bad += 1
            continue
        if i not in wanted:
            unknown += 1
        elif i in got:
            dup += 1
        else:
            got[i] = y
    missing = len(wanted) - len(got)
    for n, what in ((missing, '누락'), (dup, '중복'), (unknown, '알 수 없는 ID'), (bad, '잘못된 형식')):
        if n:
            problems.append(f'예측 {what} {n}건')
    if text is None:
        problems.insert(0, '예측 파일이 없음')
    return got, problems


def score(answers, predicted):
    """accuracy, macro-F1 (over labels seen in answers or predictions) and error count - this module's code only."""
    labels = sorted(set(answers.values()) | set(predicted.values()))
    correct = sum(1 for i, y in answers.items() if predicted.get(i) == y)
    f1s = []
    for c in labels:
        tp = sum(1 for i, y in answers.items() if y == c and predicted.get(i) == c)
        fp = sum(1 for i, y in answers.items() if y != c and predicted.get(i) == c)
        fn = sum(1 for i, y in answers.items() if y == c and predicted.get(i) != c)
        f1s.append(0.0 if tp == 0 else 2 * tp / (2 * tp + fp + fn))
    return {'accuracy': round(correct / len(answers), 4), 'macro_f1': round(sum(f1s) / len(f1s), 4),
            'errors': len(answers) - correct, 'samples': len(answers)}


def run(engine, pid, cid, approved=False, by='owner'):
    """Owner-approved: run both arms (resuming finished ones), score, record one result. Never twice at once."""
    d = _spec(engine, pid, cid)
    spec = d['spec']
    done = [e['detail'] for e in engine.store.events(pid, {'comparison_result'}) if e['detail']['cid'] == cid]
    if done:
        return view(engine, pid, cid)
    if not approved:
        raise Rejected('비교 실행은 Owner 승인이 필요합니다 (로컬 CPU, 비용 없음, 모델 호출 없음).')
    folder = _folder(engine, pid, cid)
    try:
        with run_lock(folder / 'run.lock'):
            engine.store.event(pid, 'comparison_started', cid=cid, by=by)
            problems = changes(engine, pid, d)
            if problems:
                engine.store.event(pid, 'comparison_result', cid=cid, status='invalid', problems=problems,
                                   effect='not_checked', note='준비 이후 입력·모델이 바뀌어 비교하지 않았습니다. 다시 준비하세요.')
                return view(engine, pid, cid)
            answers = {r['id']: r['label'] for r in map(json.loads, (folder / 'answers.jsonl').read_text(encoding='utf-8').splitlines())}
            ids = list(answers)
            artifact = next(a for a in engine.store.artifacts(pid) if a['id'] == spec['artifact']['id'])
            arms = {e['detail']['arm']: e['detail'] for e in engine.store.events(pid, {'comparison_arm'})
                    if e['detail']['cid'] == cid and e['detail']['spec_sha256'] == d['spec_sha256']}
            for arm in ARMS:
                if arm in arms:
                    continue                                    # resumed: this arm already finished
                code, out, pred, seconds = _run(engine, artifact, Path(spec['training_dir']),
                                                ['--model', arm, '--input', 'eval_inputs.jsonl', '--output', 'predictions.jsonl'],
                                                spec['limits']['seconds_per_arm'], input_file=folder / 'inputs.jsonl')
                got, issues = check_predictions(pred, ids)
                if code != 0:
                    issues.insert(0, '시간 한도 초과' if code is None else f'예측 명령 종료 코드 {code}')
                rec = {'cid': cid, 'arm': arm, 'spec_sha256': d['spec_sha256'], 'seconds': seconds,
                       'status': 'failed' if issues else 'ok', 'problems': issues, 'output_tail': out[-800:],
                       **({'metrics': {**score(answers, got), 'seconds': seconds}} if not issues else {})}
                engine.store.event(pid, 'comparison_arm', **rec)
                arms[arm] = rec
            failed = [f"{a}: {'; '.join(r['problems'])}" for a, r in arms.items() if r['status'] != 'ok']
            if failed:
                engine.store.event(pid, 'comparison_result', cid=cid, status='incomplete', problems=failed, effect='not_checked',
                                   note='한쪽 이상이 실패했거나 결과가 불완전해 비교를 완료하지 않았습니다.')
                return view(engine, pid, cid)
            b, t = arms['baseline']['metrics'], arms['trained']['metrics']
            delta = round(t[RULE['primary']] - b[RULE['primary']], 4)
            verdict = 'trained_better' if delta >= RULE['min_delta'] else 'trained_worse' if delta <= -RULE['min_delta'] else 'same'
            leak = spec['leakage']
            if spec['fixture']:
                effect, why = 'function_check_only', '고정 시험 모델로 실행 경로만 확인했습니다. 실제 학습 효과가 아닙니다.'
            elif not leak['checked'] or leak['overlap']:
                effect, why = 'not_verified', ('학습·평가 자료 중복을 확인할 수 없어 효과를 판정하지 않습니다.' if not leak['checked'] else
                                               f"평가 샘플 {leak['overlap']}건이 학습 자료와 겹쳐 효과를 판정하지 않습니다.")
            elif verdict == 'trained_better':
                effect, why = 'confirmed_in_this_evaluation', '이 평가 자료·조건에서만 확인된 결과입니다. 일반적인 품질 향상을 뜻하지 않습니다.'
            else:
                effect, why = 'not_confirmed', '이 평가에서 학습 모델이 기준보다 낫지 않았습니다.'
            engine.store.event(pid, 'comparison_result', cid=cid, status='complete', verdict=verdict, delta=delta,
                               baseline=b, trained=t, effect=effect, note=why)
            return view(engine, pid, cid)
    except Busy:
        raise Rejected('이 비교는 이미 실행 중입니다. 끝나면 결과가 표시됩니다.') from None


def view(engine, pid, cid, running=False):
    d = _spec(engine, pid, cid)
    arms = {e['detail']['arm']: e['detail'] for e in engine.store.events(pid, {'comparison_arm'}) if e['detail']['cid'] == cid}
    result = next((e['detail'] for e in reversed(engine.store.events(pid, {'comparison_result'})) if e['detail']['cid'] == cid), None)
    started = [e for e in engine.store.events(pid, {'comparison_started'}) if e['detail']['cid'] == cid]
    if result:
        state = {'complete': '비교 완료', 'incomplete': '비교 미완료', 'invalid': '무효(준비 후 변경)'}[result['status']]
    elif running:
        state = '실행 중'
    elif started:
        state = '중단됨 · 재개 가능 (끝난 쪽은 다시 실행하지 않음)'
    else:
        state = '준비됨 · 실행 전'
    errors = [e['detail']['error'] for e in engine.store.events(pid, {'comparison_error'}) if e['detail']['cid'] == cid]
    return {'cid': cid, 'project': pid, 'state': state, 'spec': d['spec'], 'spec_sha256': d['spec_sha256'],
            'arms': arms, 'result': result, 'resumable': bool(started and not result and not running),
            'running': running, 'last_error': errors[-1] if errors and not result else None}


def project_comparisons(engine, pid, running=()):
    return [view(engine, pid, e['detail']['cid'], running=e['detail']['cid'] in running)
            for e in engine.store.events(pid, {'comparison_prepared'})]
