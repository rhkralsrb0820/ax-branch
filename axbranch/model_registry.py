"""Reusable trained models: register a project's trained TEXT CLASSIFIER, connect it to departments / projects, and
let 淸月 use it in later work through the existing isolated runner. Text classification only (model_compare.CONTRACT).

States are separate facts, never implied by each other:
- registered: a package (predict.py + ONLY the model files predict.py --describe names for the trained arm) copied
  into workspace/models/<id>/files with hashes, source project / version, base model, environment pins, task, contract;
- runnable: a real isolated smoke run of the package produced well-formed predictions (recorded);
- evaluated: a complete before/after comparison (model_compare) of the same source version exists (its effect shown);
- approved for use: the Owner approved it; only approved, runnable, intact packages are used.
A connection never gives access to the source project's inputs or Owner data: a use run gets the package and the
CURRENT project's own input file only. A failed use is recorded and stops the work; no other model is substituted.
Connections are append-only events, so an earlier model selection can be restored; results and data are kept."""
import csv
import hashlib
import io
import json
import shutil
import tempfile
import time
import uuid
from pathlib import Path

from . import artifacts, isolation, model_compare, sandbox, training
from .state import Rejected

TASK = 'text classification'
SUPPORTED = ('text classification only: input = a CSV Owner input of the current project with a text column; output = '
             'one predicted label per row (predict.py --model trained)')
PROBE = ['my card has not arrived', 'please refund my payment', 'hello']
RUN_SECONDS = 900


def _db(store):
    store.db.execute('CREATE TABLE IF NOT EXISTS models(id TEXT PRIMARY KEY, data TEXT NOT NULL, created REAL NOT NULL, '
                     'updated REAL NOT NULL)')
    return store.db


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def package_dir(workspace, mid):
    return Path(workspace) / 'models' / mid / 'files'


def get(store, mid):
    row = _db(store).execute('SELECT * FROM models WHERE id=?', (mid,)).fetchone()
    if row is None:
        raise Rejected(f'등록된 모델이 없습니다: {mid}')
    return {'id': mid, 'created': row['created'], 'updated': row['updated'], **json.loads(row['data'])}


def all_(store):
    return [get(store, r['id']) for r in _db(store).execute('SELECT id FROM models ORDER BY created DESC')]


def _save(store, m, what, by):
    data = {k: v for k, v in m.items() if k not in ('id', 'created', 'updated')}
    data['history'] = data.get('history', []) + [{'at': time.time(), 'what': what, 'by': by}]
    with store.tx():
        _db(store).execute('UPDATE models SET data=?, updated=? WHERE id=?', (json.dumps(data, ensure_ascii=False), time.time(), m['id']))
    return get(store, m['id'])


def _labels(trained):
    path = Path(trained) / 'data' / 'test.csv'
    try:
        return sorted({y for _, y in model_compare.read_labelled(path)[0]}) if path.is_file() else []
    except Rejected:
        return []


def register(engine, pid, by='owner'):
    """Copy predict.py and the trained arm's described files into a package. Registration is not approval."""
    artifact, trained = model_compare._source(engine, pid)
    if isolation.training_runtime() is None:
        raise Rejected(training.MISSING_ENV.format(path=training.env_python()[0]))
    code, out, _, _ = model_compare._run(engine, artifact, trained, ['--describe'], model_compare.LIMITS['describe_seconds'])
    try:
        described = json.loads([ln for ln in out.strip().splitlines() if ln.startswith('{')][-1])
        info = described['trained']
        files = model_compare._model_files(artifact, trained, info['files'])
    except Rejected:
        raise
    except Exception:
        raise Rejected(f'predict.py --describe가 계약대로 응답하지 않았습니다(종료 코드 {code}).') from None
    source_files = {rel: path for rel, path, _ in artifacts.files_of(artifact)}
    mid = 'M-' + time.strftime('%Y%m%d') + '-' + uuid.uuid4().hex[:6]
    pkg = package_dir(engine.workspace, mid)
    pkg.mkdir(parents=True)
    shutil.copyfile(source_files['predict.py'], pkg / 'predict.py')
    for rel in files:
        dest = pkg / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        src = Path(trained) / rel[len('outputs/'):] if rel.startswith('outputs/') else source_files[rel]
        shutil.copyfile(src, dest)
    hashes = {'predict.py': _sha(pkg / 'predict.py'), **{rel: _sha(pkg / rel) for rel in files}}
    if any(hashes[rel] != sha for rel, sha in files.items()):
        shutil.rmtree(pkg.parent, ignore_errors=True)
        raise Rejected('복사한 모델 파일의 해시가 원본과 다릅니다. 등록하지 않았습니다.')
    data = {'name': str(info.get('name', '')), 'base_model': str(info.get('base_model', '') or 'UNKNOWN'), 'task': TASK,
            'fixture': bool(described.get('fixture')),
            'source': {'project': pid, 'artifact': artifact['id'], 'version': artifact['iteration'], 'sha256': artifact['sha256'],
                       'training_dir': str(trained)},
            'files': hashes, 'package_sha256': model_compare._canon(hashes), 'labels': _labels(trained),
            'environment': {'training_stack_pins': list(training.PINS), 'runner': 'AppContainer, no network, read-only stack'},
            'contract': {'input': 'JSON lines {"id","text"} built from the text column of a CSV',
                         'output': 'JSON lines {"id","label"}, one per input', 'command': 'predict.py --model trained'},
            'supported': SUPPORTED, 'limits': f'{TASK} only; labels limited to the registered label set when known',
            'runnable': None, 'approved': None, 'departments': [], 'history': []}
    with engine.store.tx():
        _db(engine.store).execute('INSERT INTO models VALUES(?,?,?,?)', (mid, json.dumps(data, ensure_ascii=False), time.time(), time.time()))
    engine.store.event(pid, 'model_registered', model=mid, package_sha256=data['package_sha256'])
    return _save(engine.store, get(engine.store, mid), 'registered (not approved, not evaluated)', by)


def package_problems(workspace, m):
    pkg = package_dir(workspace, m['id'])
    out = []
    for rel, sha in m['files'].items():
        if not (pkg / rel).is_file():
            out.append(f'모델 파일 없음: {rel}')
        elif _sha(pkg / rel) != sha:
            out.append(f'모델 파일이 등록 후 바뀜: {rel}')
    extra = [p.relative_to(pkg).as_posix() for p in pkg.rglob('*') if p.is_file() and p.relative_to(pkg).as_posix() not in m['files']]
    out += [f'등록되지 않은 파일: {rel}' for rel in extra]
    return out


def _run_package(workspace, m, rows, timeout=RUN_SECONDS):
    """predict.py of the package on [(id, text)] in the isolated runner. Returns (exit, output, predictions text, seconds)."""
    with tempfile.TemporaryDirectory(prefix='axb-model-', ignore_cleanup_errors=True) as cwd:
        target = Path(cwd)
        shutil.copytree(package_dir(workspace, m['id']), target, dirs_exist_ok=True)
        (target / 'eval_inputs.jsonl').write_text(''.join(json.dumps({'id': i, 'text': t}, ensure_ascii=False) + '\n'
                                                          for i, t in rows), encoding='utf-8')
        manifest = isolation.Manifest(purpose=f"registered model {m['id']}", artifact_sha256=m['package_sha256'],
                                      lifetime_seconds=timeout)
        started = time.monotonic()
        code, out = sandbox.run([str(training.env_python()[1]), '-E', '-s', '-B', '-X', 'utf8', 'predict.py', '--model', 'trained',
                                 '--input', 'eval_inputs.jsonl', '--output', 'predictions.jsonl'], cwd, timeout, isolate=manifest)
        pred = target / 'predictions.jsonl'
        return code, out, pred.read_text(encoding='utf-8', errors='replace') if pred.is_file() else None, round(time.monotonic() - started, 2)


def _ready(workspace, m):
    problems = package_problems(workspace, m)
    if isolation.training_runtime() is None:
        problems.append('실행 환경(고정 학습 환경)이 없음')
    return problems


def _predict(workspace, m, rows):
    """(predictions {id: label}, problems, seconds)."""
    code, out, pred, seconds = _run_package(workspace, m, rows)
    got, problems = model_compare.check_predictions(pred, [i for i, _ in rows])
    if code != 0:
        problems.insert(0, '시간 한도 초과' if code is None else f'예측 명령 종료 코드 {code}')
    if m['labels']:
        unknown = sorted({y for y in got.values() if y not in m['labels']})
        if unknown:
            problems.append(f"등록된 라벨이 아닌 예측 {len(unknown)}종: {', '.join(unknown[:5])}")
    return got, problems, seconds


def check_runnable(engine, mid, by='owner'):
    m = get(engine.store, mid)
    problems = _ready(engine.workspace, m)
    seconds = 0
    if not problems:
        _, problems, seconds = _predict(engine.workspace, m, [(f'p{i}', t) for i, t in enumerate(PROBE)])
    m['runnable'] = {'ok': not problems, 'problems': problems, 'at': time.time(), 'seconds': seconds,
                     'probe': 'three fixed synthetic texts; checks the contract only, not quality'}
    return _save(engine.store, m, 'runnable check ' + ('passed' if not problems else 'failed'), by)


def approve(store, workspace, mid, by='owner'):
    m = get(store, mid)
    if not (m.get('runnable') or {}).get('ok'):
        raise Rejected('실행 가능 확인을 통과한 모델만 사용 승인할 수 있습니다.')
    problems = package_problems(workspace, m)
    if problems:
        raise Rejected('모델 파일이 등록 상태와 다릅니다: ' + '; '.join(problems))
    m['approved'] = {'at': time.time(), 'by': by, 'package_sha256': m['package_sha256'],
                     'evaluation_at_approval': evaluation(store, m)['label']}
    return _save(store, m, 'approved for use', by)


def revoke(store, mid, by='owner'):
    m = get(store, mid)
    m['approved'] = None
    return _save(store, m, 'approval withdrawn', by)


def link_department(store, mid, dep, specs, link=True, by='owner'):
    m = get(store, mid)
    if dep not in specs:
        raise Rejected(f'라이브러리에 없는 부서: {dep}')
    m['departments'] = sorted(set(m['departments']) | {dep}) if link else [d for d in m['departments'] if d != dep]
    return _save(store, m, f"{'linked to' if link else 'unlinked from'} department {dep}", by)


def attach(store, pid, mid, by='owner'):
    m = get(store, mid)
    store.project(pid)
    store.event(pid, 'model_attached', model=mid, package_sha256=m['package_sha256'], by=by)


def detach(store, pid, mid, by='owner'):
    store.event(pid, 'model_detached', model=mid, by=by)


def attached(store, pid):
    """{model id: package hash} attached directly, replayed from this project's own events."""
    current = {}
    for e in store.events(pid, {'model_attached', 'model_detached'}):
        if e['kind'] == 'model_attached':
            current[e['detail']['model']] = e['detail']['package_sha256']
        else:
            current.pop(e['detail']['model'], None)
    return current


def available(store, pid):
    """[(model, via)] usable in this project: attached directly, or linked to a department attached to it."""
    from . import departments
    direct = attached(store, pid)
    deps = {d['id'] for d in departments.attached(store, pid)}
    out = []
    for m in all_(store):
        if m['id'] in direct:
            out.append((m, 'project'))
        elif set(m['departments']) & deps:
            out.append((m, 'department:' + ','.join(sorted(set(m['departments']) & deps))))
    return out


def evaluation(store, m):
    """The latest complete before/after comparison of the model's source version, read from model_compare records."""
    pid = m['source']['project']
    specs = {e['detail']['cid']: e['detail']['spec'] for e in store.events(pid, {'comparison_prepared'})
             if e['detail']['spec']['artifact']['id'] == m['source']['artifact']}
    results = [e['detail'] for e in store.events(pid, {'comparison_result'}) if e['detail']['cid'] in specs
               and e['detail']['status'] == 'complete']
    if not results:
        return {'done': False, 'label': '평가 전 — 학습 전후 비교 기록 없음'}
    r = results[-1]
    from .improvements import EFFECT
    return {'done': True, 'cid': r['cid'], 'effect': r['effect'], 'label': f"{EFFECT[r['effect']]} · {r['cid']}"}


def context(store, pid):
    """For 淸月's planning: models it MAY use in this project, with their scope and evidence; nothing when none."""
    rows = [{'model': m['id'], 'name': m['name'], 'task': m['task'], 'labels': m['labels'][:100], 'via': via,
             'approved': bool(m['approved']), 'runnable': bool((m.get('runnable') or {}).get('ok')),
             'evaluation': evaluation(store, m)['label'], 'supported': m['supported']} for m, via in available(store, pid)]
    if not rows:
        return {}
    return {'available_models': rows,
            'model_rule': ('model_uses: list {model, input, why} only for an APPROVED model whose task fits the goal, with '
                           'input = the name of one of THIS project\'s owner_inputs (a CSV with a text column). The engine runs '
                           'it isolated before production and gives every later stage and check the predictions at '
                           './model_outputs/<model>/<input>.predictions.csv (columns text,label). Never claim its quality '
                           'beyond its recorded evaluation; [] when no listed model fits.')}


def use(engine, pid, mid, input_name, plan_version, by='engine'):
    """Run an available, approved model on one of THIS project's inputs; record the outcome either way."""
    store = engine.store
    rec = {'model': mid, 'input': input_name, 'plan_version': plan_version, 'by': by}
    try:
        found = {m['id']: (m, via) for m, via in available(store, pid)}
        if mid not in found:
            raise Rejected(f'이 프로젝트에 연결되지 않은 모델입니다: {mid}')
        m, via = found[mid]
        rec.update(package_sha256=m['package_sha256'], via=via, contract=m['contract'])
        if not m['approved'] or m['approved'].get('package_sha256') != m['package_sha256']:
            raise Rejected(f'{mid}은 사용 승인되지 않은 모델입니다.')
        if via == 'project' and attached(store, pid)[mid] != m['package_sha256']:
            raise Rejected(f'{mid}의 패키지가 연결 당시와 다릅니다.')
        problems = _ready(engine.workspace, m)
        if problems:
            raise Rejected('; '.join(problems))
        record = next((r for r in engine._input_records(pid) if r['name'] == input_name), None)
        path = engine.workspace / 'projects' / pid / 'inputs' / input_name
        if record is None or not path.is_file() or _sha(path) != record['sha256']:
            raise Rejected(f'이 프로젝트의 입력 파일이 아니거나 기록과 다릅니다: {input_name}')
        try:
            table = list(csv.DictReader(io.StringIO(path.read_text(encoding='utf-8-sig'))))
        except (UnicodeDecodeError, csv.Error) as e:
            raise Rejected(f'입력 형식 불일치: {input_name} ({e})') from None
        if not table or 'text' not in table[0]:
            raise Rejected(f'입력 형식 불일치: {input_name}에 text 열이 필요합니다 ({SUPPORTED}).')
        rows = [(f'r{i:05d}', r['text']) for i, r in enumerate(table)]
        rec['input_sha256'] = record['sha256']
        got, problems, seconds = _predict(engine.workspace, m, rows)
        if problems:
            raise Rejected('모델 실행 결과가 계약과 다릅니다: ' + '; '.join(problems))
        out = engine.workspace / 'projects' / pid / 'model_outputs' / mid / f'{input_name}.predictions.csv'
        out.parent.mkdir(parents=True, exist_ok=True)
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator='\n')
        w.writerow(['text', 'label'])
        w.writerows((t, got[i]) for i, t in rows)
        out.write_text(buf.getvalue(), encoding='utf-8')
        rec.update(status='ok', output=str(out), output_sha256=_sha(out), rows=len(rows), seconds=seconds,
                   source_project=m['source']['project'], source_version=m['source']['version'])
        store.event(pid, 'model_use', **rec)
        return rec
    except Rejected as e:
        rec.update(status='failed', reason=str(e)[:500])
        store.event(pid, 'model_use', **rec)
        raise


def uses(store, mid=None):
    rows = store.db.execute("SELECT project_id, at, detail FROM events WHERE kind='model_use' ORDER BY id DESC LIMIT 200").fetchall()
    out = [{'project': p, 'at': at, **json.loads(d)} for p, at, d in rows]
    return [u for u in out if mid is None or u['model'] == mid]


def view(store, workspace):
    """Owner screen rows: states kept apart, connections, evaluation evidence and real use records."""
    projects = {}
    for pid, in store.db.execute("SELECT DISTINCT project_id FROM events WHERE kind IN ('model_attached','model_detached')"):
        for mid, sha in attached(store, pid).items():
            projects.setdefault(mid, []).append(pid)
    history = {}
    for pid, at, kind, d in store.db.execute("SELECT project_id, at, kind, detail FROM events WHERE kind IN "
                                             "('model_attached','model_detached') ORDER BY id"):
        history.setdefault(json.loads(d)['model'], []).append({'project': pid, 'at': at, 'what': kind})
    out = []
    for m in all_(store):
        u = uses(store, m['id'])
        out.append({**m, 'evaluation': evaluation(store, m), 'package_problems': package_problems(workspace, m),
                    'projects': projects.get(m['id'], []), 'connections': history.get(m['id'], [])[-20:],
                    'uses': u[:20], 'used_ok': sum(1 for x in u if x['status'] == 'ok'),
                    'used_failed': sum(1 for x in u if x['status'] != 'ok')})
    return out
