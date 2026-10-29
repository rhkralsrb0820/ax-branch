"""Owner-opened web/server results: the verified program runs in its own AppContainer and the Owner's browser reaches
it only through the per-run channel (isolation.ServerChannel). Owned by the AX Branch web server process.

- one run per project (opening again returns the running one); explicit stop; a hard lifetime; dead runs reaped
- a fresh copy of the VERIFIED version in a run folder under the temp directory; no Owner workspace grant
- no network capability (external and host loopback denied by the OS); child processes denied (a built .exe gets its
  bootloader child only); clean environment; Job Object limits and kill-on-close, so if AX Branch itself dies the
  program dies with it
- the result page is served on its own port: a different browser origin from AX Branch (whose API needs the session
  token embedded only in AX Branch's own page and refuses foreign Origins), opened with noopener
- unsupported launches are refused with the reason; there is no unisolated fallback

Limits (measured, not assumed away): any process of the same Windows user can connect to the relay port while the
run is open; data the program writes lives in the run folder and is exported to projects/<id>/run/v<N> on stop, each
open starts again from the verified version; WebSockets/HTTPS/multi-port programs are untested."""
import shutil
import tempfile
import threading
import time
from pathlib import Path

from . import artifacts, isolation, runtime, sandbox
from .state import Rejected

LIFETIME = 4 * 3600          # seconds an Owner-opened result may stay up; then it is stopped and cleaned
START_TIMEOUT = 25
PREFIX = 'axb-owner-web-'


class OwnerRuns:
    def __init__(self):
        self.runs, self.lock = {}, threading.Lock()
        sweep()

    def start(self, engine, pid):
        """URL of the project's running result, starting it if needed."""
        with self.lock:
            self._reap_locked()
            run = self.runs.get(pid)
            if run:
                return self._view(pid, run, reused=True)
            run = _launch(engine, pid)
            self.runs[pid] = run
            engine.store.event(pid, 'owner_web_run_start', version=run['version'], url=run['url'], run_id=run['run_id'],
                               artifact_sha256=run['sha256'], isolation=run['manifest'],
                               limits={'lifetime_seconds': LIFETIME, 'network': 'none', 'child_processes': run['children']})
            return self._view(pid, run, reused=False)

    def stop(self, store, pid, reason='owner'):
        with self.lock:
            run = self.runs.pop(pid, None)
        if run is None:
            return {'running': False}
        exported = _finish(run)
        store.event(pid, 'owner_web_run_stop', run_id=run['run_id'], reason=reason, exported=exported,
                    seconds=round(time.time() - run['started']))
        return {'running': False, 'exported': exported}

    def status(self, pid):
        with self.lock:
            self._reap_locked()
            run = self.runs.get(pid)
            return self._view(pid, run, reused=True) if run else {'running': False}

    def stop_all(self, store_factory=None):
        with self.lock:
            runs, self.runs = dict(self.runs), {}
        for run in runs.values():
            _finish(run)

    def _reap_locked(self):
        for pid, run in list(self.runs.items()):
            expired = time.time() - run['started'] > LIFETIME
            if expired or not run['proc'].alive():
                self.runs.pop(pid)
                run['reaped'] = 'lifetime reached' if expired else 'program exited'
                _finish(run)

    @staticmethod
    def _view(pid, run, reused):
        return {'running': True, 'url': run['url'], 'version': run['version'], 'started': run['started'],
                'lifetime_seconds': LIFETIME, 'reused': reused,
                'protection': 'AppContainer · 네트워크 차단 · 실행 전용 폴더만 접근 · 별도 출처(포트)'}


def _launch(engine, pid):
    project = engine.store.project(pid)
    plan = project['plan'] or {}
    spec = plan.get('runtime') or {}
    mode = spec.get('mode', 'cli')
    if mode not in ('web', 'server'):
        raise Rejected(f'이 결과는 웹·서버형이 아닙니다(실행 방식 {mode!r}). [결과 실행]을 사용하세요.')
    artifact = engine._verified(pid)
    changed = artifacts.problems(artifact)
    if changed:
        raise Rejected(f"검증된 버전이 디스크에서 바뀌었습니다: {'; '.join(changed)}")
    if engine._trained(artifact) is not None:
        raise Rejected('학습된 모델이 필요한 결과는 격리 실행기가 지원하지 않습니다. 실행하지 않았습니다.')
    if not any('{port}' in str(a) for a in spec.get('launch_args', [])):
        raise Rejected('이 프로그램은 검증된 포트 지정 실행 방식({port})이 없어 격리된 채 열 수 없습니다. 실행하지 않았습니다.')
    exe = engine._dist_exe(artifact)
    if exe is None and (plan.get('native_build') or {}).get('tool') == 'pyinstaller':
        raise Rejected('검증된 .exe가 없거나 바뀌었습니다. 소스로 대신 실행하지 않습니다.')
    cwd = Path(tempfile.mkdtemp(prefix=PREFIX))
    try:
        artifacts.materialize(artifact, cwd)
        engine._copy_inputs(artifact['path'], cwd)
        entry = (plan['artifact_filename'] if artifact['kind'] == 'bundle' else Path(artifact['path']).name)
        port = runtime.free_port()
        args = [a.replace('{port}', str(port)) for a in spec.get('launch_args', [])]
        if exe is not None:
            shutil.copyfile(exe, cwd / exe.name)
            argv = [str(cwd / exe.name), *args]
        else:
            python = engine._python()
            if not python:
                raise Rejected('결과를 실행할 Python을 찾지 못했습니다.')
            argv = [python, '-E', '-s', '-B', '-X', 'utf8', entry, *args]
        manifest = isolation.Manifest(purpose='Owner web result', artifact_sha256=artifact['sha256'], serve=True,
                                      lifetime_seconds=LIFETIME, child_processes=exe is not None,
                                      max_processes=3 if exe is not None else 8)
        proc = sandbox.start(argv, str(cwd), isolate=manifest)
    except (isolation.IsolationUnavailable, OSError) as exc:
        shutil.rmtree(cwd, ignore_errors=True)
        raise Rejected(f'격리된 결과 실행을 시작하지 못했습니다: {exc}. 격리 없이 실행하지 않습니다.') from exc
    except BaseException:
        shutil.rmtree(cwd, ignore_errors=True)
        raise
    deadline = time.time() + START_TIMEOUT
    while time.time() < deadline:
        if not proc.alive():
            break
        if proc.channel.ready(port):
            relay = proc.reach(port)
            run_dir = engine.workspace / 'projects' / pid / 'run' / f"v{artifact['iteration']}"
            return {'proc': proc, 'cwd': cwd, 'port': port, 'url': f'http://127.0.0.1:{relay}/', 'started': time.time(),
                    'version': artifact['iteration'], 'sha256': artifact['sha256'], 'run_id': manifest.run_id,
                    'manifest': manifest.record(), 'children': exe is not None, 'export_to': run_dir}
        time.sleep(0.3)
    tail = proc.output()[-600:]
    proc.stop()
    proc.cleanup()
    shutil.rmtree(cwd, ignore_errors=True)
    raise Rejected(f'결과 프로그램이 {START_TIMEOUT}초 안에 준비되지 않았습니다. 정리했습니다. 출력: {tail}')


def _finish(run):
    """Stop the whole tree, export bounded regular outputs, remove the run folder (and with it every grant)."""
    from .engine import Engine
    run['proc'].stop()
    run['proc'].cleanup()
    exported = []
    try:
        run['export_to'].mkdir(parents=True, exist_ok=True)
        exported = Engine._owner_output_files(run['cwd'], run['export_to'])
    except (OSError, Rejected) as exc:
        exported = [f'export skipped: {exc}'[:200]]
    shutil.rmtree(run['cwd'], ignore_errors=True)
    return exported


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
