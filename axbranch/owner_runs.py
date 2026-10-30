"""Owner-opened web/server results: the verified program runs in its own AppContainer and the Owner's browser reaches
it only through the per-run channel (isolation.ServerChannel). Owned by the AX Branch web server process.

- one run per project (opening again returns the running one); explicit stop; a hard lifetime; exited runs reaped
- a fresh copy of the chosen VERIFIED version in a run folder under the temp directory; no Owner workspace grant
- Owner data (userdata.py contract: ./data/) is restored into the run from the project's last good snapshot, saved
  every userdata.SAVE_INTERVAL seconds while open, on [지금 저장], on stop, on program exit and on lifetime end
- a snapshot from another code version is restored only if that version starts and serves its main page with it;
  otherwise nothing is saved, the data and older versions stay, and the Owner chooses (previous version / empty data)
- no network capability; child processes denied (a built .exe keeps its bootloader child only); clean environment;
  Job Object kill-on-close, so if AX Branch itself dies the program dies with it (the last periodic save remains)
- the result page is served on its own port: a different browser origin from AX Branch, opened with noopener
- the port: the program gets a free port; if it announces another one, that one is used; a bind failure retries on a
  new free port; the AX Branch port is refused
- unsupported launches are refused with the reason and the next possible action; no unisolated fallback

Limits: any process of the same Windows user can connect to the relay port while the run is open; WebSockets/HTTPS/
multi-port programs are untested; data outside ./data/ is not kept between runs."""
import re
import shutil
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import artifacts, isolation, runtime, sandbox, userdata
from .state import Rejected

LIFETIME = 4 * 3600          # seconds an Owner-opened result may stay up; then it is saved, stopped and cleaned
START_TIMEOUT = 25
PORT_ATTEMPTS = 3
PREFIX = 'axb-owner-web-'
_URL = re.compile(r'https?://(?:127\.0\.0\.1|localhost):(\d{2,5})')
_BIND_FAILED = re.compile(r'10048|address already in use|only one usage of each socket address', re.I)


class OwnerRuns:
    def __init__(self, store_factory=None):
        self.runs, self.lock, self.store_factory = {}, threading.Lock(), store_factory
        sweep()

    # ---- Owner actions
    def start(self, engine, pid, choice=None):
        """The project's running result (starting it if needed), or an 'incompatible data' answer with options."""
        with self.lock:
            self._reap_locked()
            run = self.runs.get(pid)
            if run:
                return self._view(run, reused=True)
            project_dir = engine.workspace / 'projects' / pid
            contract = data_contract(engine.store.project(pid))
            snap = None if choice == 'empty' or contract is None else (userdata.current(project_dir)
                                                                        or _inherited(engine, pid, choice))
            artifact = _choose_artifact(engine, pid, snap if choice == 'previous' else None)
            other_code = snap and snap['code_version'].get('sha256') != artifact['sha256']
            schema = snap.get('data_schema') if snap else None
            declared_incompatible = bool(other_code and isinstance(schema, int) and
                                         not contract['compatible_from'] <= schema <= contract['schema_version'])
            run = None if declared_incompatible else _launch(engine, pid, artifact, snap, contract)
            if other_code and (declared_incompatible or not _serves(run)):
                if run:
                    _kill(run)
                why = (f"이 결과 버전(v{artifact['iteration']})은 데이터 형식 {contract['compatible_from']}~{contract['schema_version']}만 "
                       f"읽을 수 있는데, 마지막 저장 데이터는 형식 {schema}입니다(v{snap['code_version'].get('iteration')}, {snap['saved_at']})."
                       if declared_incompatible else
                       f"이 결과 버전(v{artifact['iteration']})이 마지막 저장 데이터(v{snap['code_version'].get('iteration')}에서 "
                       f"{snap['saved_at']} 저장)로 시작하지 못했습니다.")
                engine.store.event(pid, 'owner_web_data_incompatible', version=artifact['iteration'],
                                   snapshot=snap['snapshot'], snapshot_code=snap['code_version'], reason=why)
                origin = snap.get('inherited_from')
                previous = ([] if origin else
                            [{'choice': 'previous', 'label': f"이전 버전 v{snap['code_version'].get('iteration')}로 데이터와 함께 열기"}])
                return {'running': False, 'incompatible': True, 'reason': why, 'snapshot': snap['snapshot'],
                        'origin_project': origin,
                        'options': previous + [{'choice': 'empty', 'label': f"새 버전 v{artifact['iteration']}을 빈 데이터로 열기 (저장된 데이터는 그대로 보존)"}]}
            run['choice'] = choice
            if choice == 'previous' and run['contract'] and isinstance(schema, int):
                # The previous version writes ITS data format, not the latest plan's: keep the restored schema.
                run['contract'] = {**run['contract'], 'schema_version': schema}
            self.runs[pid] = run
            engine.store.event(pid, 'owner_web_run_start', version=run['version'], url=run['url'], run_id=run['run_id'],
                               artifact_sha256=run['code_version']['sha256'], isolation=run['manifest'], choice=choice,
                               restored=run['restored'] and {k: run['restored'][k] for k in ('snapshot', 'saved_at', 'data_version')},
                               port=run['program_port'], limits={'lifetime_seconds': LIFETIME, 'network': 'none',
                                                                 'child_processes': run['children']})
            run['saver'] = threading.Thread(target=self._periodic, args=(pid, run), daemon=True)
            run['saver'].start()
            return self._view(run, reused=False)

    def save(self, pid, reason='owner'):
        with self.lock:
            run = self.runs.get(pid)
        if run is None:
            raise Rejected('실행 중인 결과가 없습니다. 먼저 [결과 열기]를 누르세요.')
        self._save(pid, run, reason, only_if_changed=False)
        return self._view(run, reused=True)

    def stop(self, store, pid, reason='owner'):
        with self.lock:
            run = self.runs.pop(pid, None)
        if run is None:
            return {'running': False, **self.saved(pid, store_dir=None)}
        self._finish(pid, run, reason)
        return {'running': False, 'last_saved': run.get('last_saved'), 'save_error': run.get('save_error')}

    def status(self, pid, project_dir=None):
        with self.lock:
            self._reap_locked()
            run = self.runs.get(pid)
        if run:
            return self._view(run, reused=True)
        return {'running': False, **(self.saved(pid, project_dir) if project_dir else {})}

    @staticmethod
    def saved(pid, store_dir):
        snap = userdata.current(store_dir) if store_dir else None
        return {'last_saved': snap and {k: snap[k] for k in ('snapshot', 'saved_at', 'data_version', 'reason')}
                | {'code_iteration': snap['code_version'].get('iteration'), 'files': len(snap['files'])}}

    def stop_all(self):
        with self.lock:
            runs, self.runs = dict(self.runs), {}
        for pid, run in runs.items():
            self._finish(pid, run, 'AX Branch stopped')

    # ---- internals
    def _event(self, pid, kind, **detail):
        if self.store_factory is None:
            return
        store = self.store_factory()
        try:
            store.event(pid, kind, **detail)
        finally:
            store.close()

    def _save(self, pid, run, reason, only_if_changed):
        if run['contract'] is None:            # no declared data contract: nothing is kept by guesswork
            if not only_if_changed:
                raise Rejected('이 결과에는 데이터 저장 명세가 없어 저장하지 않습니다. 같은 프로젝트에 "입력한 데이터를 저장하게 해 달라"고 '
                               '수정 요청을 보내면 저장·복원되는 버전이 만들어집니다.')
            return None
        with run['save_lock']:
            try:
                snap = userdata.snapshot(run['project_dir'], run['cwd'], run['code_version'], reason,
                                         only_if_changed=only_if_changed, contract=run['contract'])
            except userdata.SaveFailed as e:
                run['save_error'] = {'at': time.strftime('%Y-%m-%d %H:%M:%S'), 'reason': str(e)[:300]}
                self._event(pid, 'owner_data_save_failed', run_id=run['run_id'], reason=str(e)[:500], trigger=reason,
                            kept=run.get('last_saved') or run['restored'] and run['restored']['snapshot'])
                if not only_if_changed:
                    raise Rejected(f'저장하지 못했습니다: {e}. 마지막 정상 데이터는 그대로 남아 있습니다.') from e
                return None
            if snap:
                run['last_saved'] = {k: snap[k] for k in ('snapshot', 'saved_at', 'data_version', 'reason')} | {'files': len(snap['files'])}
                run['save_error'] = None
                self._event(pid, 'owner_data_saved', run_id=run['run_id'], snapshot=snap['snapshot'], trigger=reason,
                            code_version=snap['code_version'], files=[f['path'] for f in snap['files']],
                            skipped=snap['skipped'][:20])
            return snap

    def _periodic(self, pid, run):
        while not run['stopped'].wait(userdata.SAVE_INTERVAL):
            if run['proc'].alive():
                self._save(pid, run, 'periodic', only_if_changed=True)

    def _finish(self, pid, run, reason):
        """Stop the whole tree first (files are then at rest), save, export nothing else, remove the run folder."""
        run['stopped'].set()
        run['proc'].stop()
        try:
            self._save(pid, run, f'stop: {reason}', only_if_changed=True)
        except Rejected:
            pass
        run['proc'].cleanup()
        shutil.rmtree(run['cwd'], ignore_errors=True)
        self._event(pid, 'owner_web_run_stop', run_id=run['run_id'], reason=reason,
                    seconds=round(time.time() - run['started']), last_saved=run.get('last_saved'),
                    save_error=run.get('save_error'))

    def _reap_locked(self):
        for pid, run in list(self.runs.items()):
            expired = time.time() - run['started'] > LIFETIME
            if expired or not run['proc'].alive():
                self.runs.pop(pid)
                self._finish(pid, run, 'lifetime reached' if expired else 'program exited')

    @staticmethod
    def _view(run, reused):
        return {'running': True, 'url': run['url'], 'version': run['version'], 'started': run['started'],
                'data_kept': run['contract'] is not None,
                'lifetime_seconds': LIFETIME, 'reused': reused, 'choice': run.get('choice'),
                'restored': run['restored'] and {k: run['restored'][k] for k in ('snapshot', 'saved_at', 'data_version')}
                | {'code_iteration': run['restored']['code_version'].get('iteration'), 'files': len(run['restored']['files']),
                   'from_project': run['restored'].get('inherited_from')},
                'last_saved': run.get('last_saved'), 'save_error': run.get('save_error'),
                'save_interval_seconds': userdata.SAVE_INTERVAL,
                'protection': 'AppContainer · 네트워크 차단 · 실행 전용 폴더만 접근 · 별도 출처(포트)'}


def data_contract(project):
    """The project's declared Owner-data contract (plan runtime.data, normalized), or None: an older plan without
    one is never restored or saved by guesswork."""
    spec, _ = runtime.normalize((project['plan'] or {}).get('runtime'))
    data = spec.get('data') or {}
    return data if data.get('needed') and not data.get('invalid') else None


def _inherited(engine, pid, choice):
    """A project continued from the library ('이어서 개발') starts from the nearest ancestor's last good data. Read-only:
    the copy is restored into this run and later saved under THIS project; the ancestor's snapshots never change."""
    if choice == 'previous':
        return None                              # 'previous' means this project's own earlier version
    from . import library
    for ancestor in reversed(library.ancestry(library._links(engine.store), pid)[:-1]):
        snap = userdata.current(engine.workspace / 'projects' / ancestor)
        if snap:
            return {**snap, 'inherited_from': ancestor}
    return None


def _choose_artifact(engine, pid, snap):
    """The latest verified version, or (choice 'previous') the verified version the snapshot was saved with."""
    if snap is None:
        return engine._verified(pid)
    passed = {v['artifact_id'] for v in engine.store.verifications(pid) if v['verdict'] == 'PASS'}
    for a in reversed(engine.store.artifacts(pid)):
        if a['id'] in passed and a['sha256'] == snap['code_version'].get('sha256'):
            return a
    raise Rejected('저장 데이터를 만든 이전 버전을 찾지 못했습니다(검증된 버전이 아니거나 삭제됨). 새 버전을 빈 데이터로 여세요.')


def _launch(engine, pid, artifact, snap, contract=None):
    project = engine.store.project(pid)
    plan = project['plan'] or {}
    spec = plan.get('runtime') or {}
    mode = spec.get('mode', 'cli')
    if mode not in ('web', 'server'):
        raise Rejected(f'이 결과는 웹·서버형이 아닙니다(실행 방식 {mode!r}). [결과 실행]을 사용하세요.')
    changed = artifacts.problems(artifact)
    if changed:
        raise Rejected(f"검증된 버전이 디스크에서 바뀌었습니다: {'; '.join(changed)}. 같은 프로젝트에 수정 요청을 보내 새 버전을 만드세요.")
    if engine._trained(artifact) is not None:
        raise Rejected('학습된 모델이 필요한 결과는 격리 실행기가 지원하지 않습니다. 실행하지 않았습니다.')
    if not any('{port}' in str(a) for a in spec.get('launch_args', [])):
        raise Rejected('이 프로그램은 포트를 지정해 실행하는 방식({port})이 없어 격리된 채 열 수 없습니다. '
                       '같은 프로젝트에 "--port 옵션을 지원해 달라"고 수정 요청을 보내면 열 수 있게 됩니다.')
    exe = engine._dist_exe(artifact) if artifact['id'] == engine._verified(pid)['id'] else None
    if exe is None and (plan.get('native_build') or {}).get('tool') == 'pyinstaller':
        raise Rejected('검증된 .exe가 없거나 바뀌었습니다. 소스로 대신 실행하지 않습니다.')
    python = None if exe else engine._python()
    if not exe and not python:
        raise Rejected('결과를 실행할 Python을 찾지 못했습니다.')
    entry = plan['artifact_filename'] if artifact['kind'] == 'bundle' else Path(artifact['path']).name
    last_output = ''
    for _ in range(PORT_ATTEMPTS):
        cwd = Path(tempfile.mkdtemp(prefix=PREFIX))
        try:
            artifacts.materialize(artifact, cwd)
            engine._copy_inputs(artifact['path'], cwd)
            restored = userdata.restore(snap, cwd) if snap else []
            port = runtime.free_port()
            args = [a.replace('{port}', str(port)) for a in spec.get('launch_args', [])]
            if exe is not None:
                shutil.copyfile(exe, cwd / exe.name)
                argv = [str(cwd / exe.name), *args]
            else:
                argv = [python, '-E', '-s', '-B', '-X', 'utf8', entry, *args]
            manifest = isolation.Manifest(purpose='Owner web result', artifact_sha256=artifact['sha256'], serve=True,
                                          lifetime_seconds=LIFETIME, child_processes=exe is not None,
                                          max_processes=3 if exe is not None else 8)
            proc = sandbox.start(argv, str(cwd), isolate=manifest)
        except userdata.SaveFailed as exc:
            shutil.rmtree(cwd, ignore_errors=True)
            raise Rejected(f'저장 데이터를 복원하지 못했습니다: {exc}. 실행하지 않았습니다(데이터는 그대로 보존).') from exc
        except (isolation.IsolationUnavailable, OSError) as exc:
            shutil.rmtree(cwd, ignore_errors=True)
            raise Rejected(f'격리된 결과 실행을 시작하지 못했습니다: {exc}. 격리 없이 실행하지 않습니다.') from exc
        live = _wait_ready(proc, port)
        if live:
            relay = proc.reach(live)
            return {'proc': proc, 'cwd': cwd, 'program_port': live, 'url': f'http://127.0.0.1:{relay}/',
                    'started': time.time(), 'version': artifact['iteration'], 'run_id': manifest.run_id,
                    'code_version': {'iteration': artifact['iteration'], 'sha256': artifact['sha256'], 'artifact': artifact['id']},
                    'manifest': manifest.record(), 'children': exe is not None, 'restored': snap and dict(snap),
                    'restored_files': restored, 'project_dir': engine.workspace / 'projects' / pid,
                    'save_lock': threading.Lock(), 'stopped': threading.Event(), 'last_saved': None, 'save_error': None,
                    'contract': contract}
        last_output = proc.output()[-600:]
        proc.stop()
        proc.cleanup()
        shutil.rmtree(cwd, ignore_errors=True)
        announced = [int(p) for p in _URL.findall(last_output)]
        if any(p in runtime.RESERVED_PORTS for p in announced):
            raise Rejected('이 프로그램이 AX Branch 전용 포트(8765)를 쓰려고 했습니다. 같은 프로젝트에 "기본 포트를 바꿔 달라"고 '
                           f'수정 요청을 보내세요. 출력: {last_output[-300:]}')
        if not _BIND_FAILED.search(last_output):
            break                                   # not a port problem: retrying would not help
    raise Rejected(f'결과 프로그램이 {START_TIMEOUT}초 안에 준비되지 않아 정리했습니다. 출력: {last_output[-400:]}')


def _wait_ready(proc, port):
    """The container port that serves: the one we passed, or the one the program announced (never a reserved one)."""
    deadline = time.time() + START_TIMEOUT
    while time.time() < deadline:
        if not proc.alive():
            return None
        if proc.channel.ready(port):
            return port
        for announced in {int(p) for p in _URL.findall(proc.output())} - {port}:
            if announced not in runtime.RESERVED_PORTS and proc.channel.ready(announced):
                return announced
        time.sleep(0.3)
    return None


def _serves(run):
    """Compatibility of restored data with this code version: the program still runs and its main page answers
    without a server error."""
    time.sleep(1)
    if not run['proc'].alive():
        return False
    try:
        with urllib.request.urlopen(run['url'], timeout=10) as r:
            return r.status < 500
    except urllib.error.HTTPError as e:
        return e.code < 500
    except OSError:
        return False


def _kill(run):
    run['stopped'].set()
    run['proc'].stop()
    run['proc'].cleanup()
    shutil.rmtree(run['cwd'], ignore_errors=True)


def sweep(max_age=LIFETIME):
    """Remove run folders left by an AX Branch that died (its Job already killed the programs)."""
    temp = Path(tempfile.gettempdir())
    now = time.time()
    for folder in temp.glob(PREFIX + '*'):
        try:
            if now - folder.stat().st_mtime > max_age:
                shutil.rmtree(folder, ignore_errors=True)
        except OSError:
            pass
