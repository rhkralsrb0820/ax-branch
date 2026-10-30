"""Local web UI for AX Branch: a loopback-only HTTP server over the SAME store, engine, supervisor and Owner
actions as the window and the CLI (axbranch.actions). It adds no engine and edits no table directly.

Security (local only, no hosting):
- binds 127.0.0.1 only;
- every /api call needs the per-start session token (embedded in the page this server serves; another site
  cannot read it) in the X-AXB-Token header, a Host of this server (DNS rebinding) and, when sent, an Origin of
  this server. A custom header forces a CORS preflight, which is never granted;
- no endpoint runs a command; actions are the named Owner actions only.
Viewing never resumes work: GET endpoints only read, and this server runs no supervision loop.

    python -m axbranch web [--port 8765]     start (prints the address; opens no browser)
    python -m axbranch web --stop            stop the server started from this workspace"""
import base64
import json
import os
import re
import secrets
import shutil
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from . import WORKSPACE, __version__, actions, budgets, departments, home, improvements, knowledge, live, supervisor
from .state import Rejected, Store, run_lock

ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
STATIC = ROOT / 'axbranch' / 'webui' if (ROOT / 'axbranch' / 'webui').is_dir() else Path(__file__).with_name('webui')
DEVROOM = ROOT / 'docs' / 'devroom' / 'status.json'
MAX_BODY = 30 * 2**20
PID_RE = re.compile(r'P-\d{8}-[0-9a-f]{6}')
TYPES = {'.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8'}


class App:
    """State shared by the handler threads. engine_factory / launcher are injectable for tests."""
    def __init__(self, workspace=WORKSPACE, port=8765, engine_factory=None, launcher=None, devroom=DEVROOM,
                 test_mode=False):
        self.workspace, self.port, self.devroom, self.test_mode = Path(workspace), port, Path(devroom), test_mode
        self.db = self.workspace / 'axbranch.sqlite3'
        self.engine_factory = engine_factory or self._open_engine
        self.launcher = launcher
        self.token = secrets.token_urlsafe(24)
        self.specs, self.refused = departments.catalog()
        self.lock = threading.Lock()                 # serialises project creation (idempotency)
        self.reports = []                            # test mode: in-browser self-test / perf reports
        self.started = time.time()
        from .owner_runs import OwnerRuns
        self.owner_runs = OwnerRuns(self.store)      # Owner-opened web/server results (isolated, one per project)

    def _open_engine(self):
        from .engine import open_engine
        return open_engine(self.workspace)

    def store(self):
        return Store(self.db)

    # ---- read models ----
    def overview(self, store):
        statuses, rows = {}, []
        for p in store.projects():
            # The summary rows omit plan, including the CEO's saved display title.
            # Use the same full record as the project page; never rewrite the original goal.
            p = store.project(p['id'])
            rec = supervisor.status(self.workspace, store, p['id'])
            statuses[p['id']] = rec['status']
            reason = store.project(p['id'])['pause_reason'] if p['state'] == 'PAUSED' else None
            tag, mark = _indicator(p['state'], rec['status'])
            rows.append({'id': p['id'], 'title': _title(p), 'goal': p['goal'][:300], 'state': p['state'],
                         'status': rec['status'], 'reason': (reason or '')[:300], 'indicator': tag, 'mark': mark})
        orb = home.orb_state([(r['state'], r['status'], r['reason'] or None) for r in rows])
        delegated = []
        running = next((r['id'] for r in rows if r['status'] in ('ACTIVE', 'RECOVERING')), None)
        if running:
            for e in store.events(running, {'department_delegation', 'temporary_agent'}):
                spec = self.specs.get(e['detail'].get('department', ''))
                name = spec['name'] if spec else '임시 에이전트'
                if name not in delegated:
                    delegated.append(name)
        return {'version': __version__, 'projects': rows, 'orb': orb, 'delegated': delegated,
                'groups': [{'label': l, 'count': n, 'color': c} for l, n, c in home.state_groups(store.projects())],
                'departments': [dict(departments.summary(s), knowledge=s['knowledge'], lifecycle=departments.lifecycle(s['id']))
                                for s in self.specs.values()],
                'refused': sorted(self.refused), 'settings': self.settings(), 'test_mode': self.test_mode,
                'task_budgets': [dict(v, id=k, **actions.TASK_LIMITS) for k, v in actions.TASK_BUDGETS.items()],
                'orb_text': _orb_text()}

    def project(self, store, pid):
        p = store.project(pid)
        rec = supervisor.status(self.workspace, store, pid)
        text, color = _banner(p['state'], rec['status'], p['pause_reason'] or '')
        mode, note = actions.owner_mode(p, rec['status'])
        view = live.view(self.workspace, store, pid)
        return {'id': pid, 'title': _title(p), 'goal': p['goal'], 'state': p['state'], 'status': rec['status'],
                'pause_reason': p['pause_reason'], 'iteration': p['iteration'], 'banner': {'text': text, 'color': color},
                'owner': {'mode': mode, 'note': note}, 'attached': _attached_view(store, pid),
                'capabilities': [e['detail'] for e in store.events(pid, {'capability_decision'})][-5:],
                'pipeline': view['pipeline'], 'header': view['header'], 'timeline': view['timeline'][-80:],
                'verifications': [{'iteration': v['iteration'], 'verdict': v['verdict'], 'provider': v['provider'],
                                   'created': v['created']} for v in store.verifications(pid)],
                'contract': [e['detail'] for e in store.events(pid, {'department_contract'})][-10:],
                'acceptance': ([e['detail'] for e in store.events(pid, {'department_acceptance'})] or [{}])[-1],
                'required_unmet': ([e['detail'] for e in store.events(pid, {'required_unmet', 'delegation_refused'})] or [{}])[-1],
                'conflicts': [e['detail'] for e in store.events(pid, {'criteria_conflict'})][-5:],
                'document_contract': [e['detail'] for e in store.events(pid, {'department_document_contract'})][-10:],
                'experience': knowledge.experience_view(store, pid),
                'recommendations': departments.recommendations(store, pid),
                'execution_budget': _execution_budget(store, p),
                'owner_web_run': self.owner_runs.status(pid, self.workspace / 'projects' / pid),
                'improvements': _improvements_view(store, pid)}

    def settings(self):
        try:
            return json.loads((self.workspace / 'settings.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return {}

    def feeds(self):
        try:
            data = json.loads((self.workspace / 'home-feeds.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            data = {}
        return {cat: dict(data.get(cat, {}), source=source) for cat, source in home.FEEDS.items()}

    # ---- Owner development room (AX Branch's OWN development status; not user projects) ----
    def devroom_data(self):
        try:
            status = json.loads(self.devroom.read_text(encoding='utf-8'))
        except (OSError, ValueError) as e:
            status = {'error': f'현황 기록을 읽지 못했습니다: {type(e).__name__}'}
        return {'status': status, 'notes': self.notes(), 'running': {'version': __version__, 'code': _code_id()}}

    def notes(self):
        try:
            return json.loads((self.workspace / 'devroom-notes.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return []


def _title(p):
    from .library import project_title
    return project_title(p)


def _execution_budget(store, project):
    """Read-only Owner view of the cumulative ledger. A past PASS must not imply the current revision passed."""
    events = store.events(project['id'])
    configured = [e['detail'] for e in events if e['kind'] == 'execution_budget']
    usage = budgets.ledger_usage(events)
    if not configured:
        return {'configured': False, **usage}
    limit = configured[-1]
    stop = next((e['detail'] for e in reversed(events) if e['kind'] == 'budget_reserve_stop'), None)
    is_budget_pause = project['state'] == 'PAUSED' and 'budget' in (project['pause_reason'] or '').lower()
    current_verification = next((v for v in reversed(store.verifications(project['id']))
                                 if v['iteration'] == project['iteration']), None)
    artifacts_now = {a['id'] for a in store.artifacts(project['id']) if a['iteration'] == project['iteration']}
    current_pass = bool(current_verification and current_verification['artifact_id'] in artifacts_now
                        and current_verification['verdict'] == 'PASS' and current_verification['checks'].get('ok'))
    acceptance_wait = bool(is_budget_pause and stop and stop.get('phase') == 'acceptance' and current_pass
                           and stop.get('iteration') == project['iteration'])
    profile = limit.get('profile')
    return {'configured': True, **usage, **{k: limit[k] for k in (
                'max_reported_tokens', 'max_calls', 'max_seconds', 'max_prompt_chars')},
            'profile': profile, 'label': actions.TASK_BUDGETS.get(profile, {}).get('label', '개별 설정'),
            'remaining_tokens': (max(0, limit['max_reported_tokens'] - usage['reported_tokens'])
                                 if usage['reported_tokens'] is not None else None),
            'paused': is_budget_pause, 'stop': stop if is_budget_pause else None,
            'verification_passed': current_pass, 'acceptance_pending': acceptance_wait}


def _banner(state, status, reason):
    from .gui import banner
    return banner(state, status, reason)


def _indicator(state, status):
    from .gui import indicator
    return indicator(state, status)


def _orb_text():
    from .orb import TEXT
    return TEXT


def _code_id():
    """The code this server runs: a git commit in a source checkout, or the packaged build."""
    head = ROOT / '.git' / 'HEAD'
    try:
        ref = head.read_text(encoding='utf-8').strip()
        if ref.startswith('ref: '):
            ref = (ROOT / '.git' / ref[5:]).read_text(encoding='utf-8').strip()
        return ref[:12]
    except OSError:
        return 'packaged build' if getattr(sys, 'frozen', False) else 'UNKNOWN'


class Handler(BaseHTTPRequestHandler):
    app: App = None
    server_version = 'AXBranchWeb'

    def log_message(self, fmt, *args):            # quiet: no request log on the console
        pass

    # ---- helpers ----
    def _send(self, code, body, ctype='application/json; charset=utf-8'):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False, default=str).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self' data:; "
                                                    "style-src 'self' 'unsafe-inline'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(data)

    def _host_ok(self):
        return self.headers.get('Host', '') in (f'127.0.0.1:{self.app.port}', f'localhost:{self.app.port}')

    def _api_ok(self):
        origin = self.headers.get('Origin')
        if origin is not None and origin not in (f'http://127.0.0.1:{self.app.port}', f'http://localhost:{self.app.port}'):
            return False
        return self._host_ok() and secrets.compare_digest(self.headers.get('X-AXB-Token', ''), self.app.token)

    def _body(self):
        n = int(self.headers.get('Content-Length') or 0)
        if n > MAX_BODY:
            raise Rejected('요청이 너무 큽니다.')
        raw = self.rfile.read(n) if n else b'{}'
        data = json.loads(raw or b'{}')
        if not isinstance(data, dict):
            raise Rejected('JSON 객체가 필요합니다.')
        return data

    def do_OPTIONS(self):                         # no CORS: a cross-origin preflight is refused
        self._send(403, {'error': 'forbidden'})

    def do_GET(self):
        if not self._host_ok():
            return self._send(403, {'error': 'forbidden host'})
        path = urlsplit(self.path).path
        if path == '/' or path == '/index.html':
            page = (STATIC / 'index.html').read_text(encoding='utf-8').replace('__AXB_TOKEN__', self.app.token)
            return self._send(200, page.encode('utf-8'), TYPES['.html'])
        if path in ('/app.js', '/app.css', '/orb.js', '/devroom.js') or (path == '/selftest.js' and self.app.test_mode):
            f = STATIC / path[1:]
            return self._send(200, f.read_bytes(), TYPES[f.suffix])
        if not path.startswith('/api/'):
            return self._send(404, {'error': 'not found'})
        if not self._api_ok():
            return self._send(403, {'error': 'forbidden'})
        self._api('GET', path, parse_qs(urlsplit(self.path).query), {})

    def do_POST(self):
        if not self._host_ok() or not self.path.startswith('/api/') or not self._api_ok():
            return self._send(403, {'error': 'forbidden'})
        try:
            body = self._body()
        except (ValueError, Rejected) as e:
            return self._send(400, {'error': str(e)})
        self._api('POST', urlsplit(self.path).path, {}, body)

    def _api(self, method, path, query, body):
        store = self.app.store()
        try:
            result = route(self.app, store, method, path, query, body)
            self._send(200, result)
        except actions.StartRejected as e:
            self._send(400, {'error': str(e), 'submission': 'rejected_before_creation', 'request_id': e.request_id})
        except (Rejected, ValueError, KeyError) as e:
            self._send(400, {'error': str(e)})
        except Exception as e:                     # never a traceback page; the message only
            self._send(500, {'error': f'{type(e).__name__}: {e}'})
        finally:
            store.close()


def route(app, store, method, path, query, body):
    parts = path.strip('/').split('/')[1:]          # after 'api'
    if method == 'GET':
        if parts == ['overview']:
            return app.overview(store)
        if parts == ['submission']:
            request_id = (query.get('request_id') or [''])[0]
            if not re.fullmatch(r'[\w-]{8,64}', request_id):
                raise Rejected('올바른 request_id가 필요합니다.')
            with app.lock:                         # wait for a creation currently committing
                pid = actions.created_by(store, request_id)
            return {'id': pid}
        if parts == ['feeds']:
            return app.feeds()
        if parts == ['devroom']:
            return app.devroom_data()
        if parts == ['test', 'signals'] and app.test_mode:      # out-of-process harness -> page (test server only)
            try:
                return json.loads((app.workspace / 'test-signals.json').read_text(encoding='utf-8'))
            except (OSError, ValueError):
                return {}
        if parts == ['test', 'fixture'] and app.test_mode and os.environ.get('AXB_TEST_FIXTURE'):
            f = Path(os.environ['AXB_TEST_FIXTURE'])
            return {'name': f.name, 'text': f.read_text(encoding='utf-8-sig')}
        if parts == ['improvements']:
            return {'candidates': improvements.all_(store), 'learning': improvements.learning_paths(store)}
        if parts == ['library']:
            from . import library
            return {'types': list(library.TYPES), 'entries': library.entries(store)}
        if len(parts) == 2 and parts[0] == 'project' and PID_RE.fullmatch(parts[1]):
            return app.project(store, parts[1])
        if len(parts) == 3 and parts[0] == 'project' and parts[2] == 'records' and PID_RE.fullmatch(parts[1]):
            key = (query.get('key') or [''])[0]
            return {'records': live.records(store, parts[1], key)}
        raise KeyError('unknown endpoint')
    channel = 'web'
    if parts == ['projects']:
        return create_project(app, store, body, channel)
    if parts == ['develop']:
        request_id, base = str(body.get('request_id') or ''), str(body.get('base') or '')
        if not re.fullmatch(r'[\w-]{8,64}', request_id) or not PID_RE.fullmatch(base):
            raise Rejected('base 프로젝트와 request_id가 필요합니다.')
        with app.lock:
            existing = actions.created_by(store, request_id, 'develop')
            if existing:
                return {'id': existing, 'created': False}
            pid = actions.develop(app.engine_factory, store, base, str(body.get('goal', '')), channel, request_id)
        actions.launch(app.workspace, store, pid, app.launcher)
        return {'id': pid, 'created': True}
    if parts == ['settings']:
        current = app.settings()
        current.update({k: bool(body[k]) for k in ('motion_off', 'low_power') if k in body})
        app.workspace.mkdir(parents=True, exist_ok=True)
        (app.workspace / 'settings.json').write_text(json.dumps(current), encoding='utf-8')
        return current
    if parts == ['feeds', 'refresh']:                # the Owner asked: public feeds, no AI call
        data = app.feeds()
        for category, result in home.fetch_feeds().items():   # same cache as the window; a failed source keeps old items
            if result['error']:
                old = data.get(category, {})
                result['items'], result['fetched'] = old.get('items', []), old.get('fetched')
            data[category] = result
        (app.workspace / 'home-feeds.json').write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        return data
    if parts == ['devroom', 'notes']:
        notes = body.get('notes')
        if not isinstance(notes, list) or len(notes) > 500:
            raise Rejected('notes must be a list')
        clean = [{'id': str(n.get('id', ''))[:40], 'item': str(n.get('item', ''))[:80], 'text': str(n.get('text', ''))[:4000],
                  'at': n.get('at')} for n in notes if isinstance(n, dict)]
        (app.workspace / 'devroom-notes.json').write_text(json.dumps(clean, ensure_ascii=False, indent=1), encoding='utf-8')
        return {'notes': clean}
    if parts == ['shutdown']:
        app.owner_runs.stop_all()
        threading.Thread(target=app.httpd.shutdown, daemon=True).start()
        return {'ok': True}
    if parts and parts[0] == 'test' and app.test_mode:   # in-browser self-test / perf reports (test server only)
        app.reports.append({'kind': parts[1] if len(parts) > 1 else '', **body})
        with (app.workspace / 'test-reports.jsonl').open('a', encoding='utf-8') as f:   # for out-of-process harnesses
            f.write(json.dumps(app.reports[-1], ensure_ascii=False) + '\n')
        return {'ok': True}
    if len(parts) == 3 and parts[0] == 'project' and PID_RE.fullmatch(parts[1]):
        return project_action(app, store, parts[1], parts[2], body, channel)
    if len(parts) == 3 and parts[0] == 'improvement' and re.fullmatch(r'I-[0-9a-f]{8}', parts[1]):
        return improvement_action(app, store, parts[1], parts[2], body)
    raise KeyError('unknown endpoint')


def create_project(app, store, body, channel):
    request_id = str(body.get('request_id') or '')
    if not re.fullmatch(r'[\w-]{8,64}', request_id):
        raise Rejected('request_id가 필요합니다 (새로고침·중복 제출 방지).')
    files, tmp = [], None
    try:
        with app.lock:                               # one creation at a time: the same request_id never twice
            existing = actions.created_by(store, request_id)
            if existing:
                return {'id': existing, 'created': False}
            try:
                if body.get('files'):
                    tmp = Path(tempfile.mkdtemp(prefix='axb-web-upload-'))
                    for f in body['files'][:20]:
                        name = Path(str(f.get('name', ''))).name
                        if not name or name.startswith('.'):
                            raise Rejected('파일 이름이 올바르지 않습니다.')
                        (tmp / name).write_bytes(base64.b64decode(f.get('data', ''), validate=True))
                        files.append(str(tmp / name))
            except (Rejected, ValueError, OSError) as e:
                raise actions.StartRejected(str(e), request_id) from e
            pid = actions.start(store, app.engine_factory, body.get('goal', ''), list(body.get('departments') or []),
                                app.specs, files, channel, request_id=request_id, required=list(body.get('required') or []),
                                task_type=body.get('task_type', 'general'))
        actions.launch(app.workspace, store, pid, app.launcher)
        return {'id': pid, 'created': True}
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)   # attach_inputs copied them into the project


def improvement_action(app, store, cid, action, body):
    with app.lock:                                   # one transition at a time (a double click never starts two evaluations)
        if action == 'prepare':
            return improvements.prepare_eval(store, cid)
        if action == 'evaluate':
            return improvements.start_eval(store, app.engine_factory, app.specs, cid,
                                           lambda pid: actions.launch(app.workspace, store, pid, app.launcher),
                                           approved=body.get('approve') is True)
        if action == 'approve':
            return improvements.approve(store, cid)
        if action == 'rollback':
            return improvements.rollback(store, cid)
        if action == 'reject':
            return improvements.reject(store, cid, str(body.get('why', '')))
    raise KeyError('unknown action')


def _attached_view(store, pid):
    """Attached departments with who connected them: the Owner directly, or the Owner accepting a CEO recommendation."""
    accepted = {e['detail']['department'] for e in store.events(pid, {'department_recommendation_decision'})
                if e['detail'].get('decision') == 'accepted'}
    return [dict(d, via='ceo_recommendation' if d['id'] in accepted else 'owner') for d in departments.attached(store, pid)]


def _improvements_view(store, pid):
    used = store.events(pid, {'improvements_used'})
    policy = store.events(pid, {'improvement_policy'})
    return {'used': [e['detail'] for e in used][-4:], 'evaluation': policy[-1]['detail'] if policy else None}


def project_action(app, store, pid, action, body, channel):
    if action == 'recommendation':
        with run_lock(app.workspace / 'projects' / pid / 'run.lock'):
            changed = departments.decide_recommendation(store, pid, body.get('id'), body.get('decision'))
        return {'changed': changed, 'recommendations': departments.recommendations(store, pid),
                'attached': departments.attached(store, pid)}
    store.project(pid)                               # unknown project -> error
    if action == 'department':
        dep = str(body.get('id', ''))
        if body.get('action') == 'attach':
            departments.attach(store, pid, dep, app.specs)
        elif body.get('action') == 'detach':
            departments.detach(store, pid, dep)
        elif body.get('action') in ('require', 'optional'):
            departments.set_mode(store, pid, dep, 'required' if body['action'] == 'require' else 'available',
                                 str(body.get('reason', '')), channel=channel)
        else:
            raise Rejected('action must be attach, detach, require or optional')
        return {'attached': departments.attached(store, pid)}
    if action == 'resume':
        if actions.resume(store, pid, channel):
            actions.launch(app.workspace, store, pid, app.launcher)
        return {'ok': True}
    if action == 'stop':
        actions.stop(app.workspace, store, pid, channel, via='web')
        return {'ok': True}
    if action == 'network':
        actions.decide_network(app.engine_factory, pid, bool(body.get('approve')), channel, str(body.get('note', ''))[:2000])
        if actions.resume(store, pid, channel):
            actions.launch(app.workspace, store, pid, app.launcher)
        return {'ok': True}
    if action == 'review':
        works = {'yes': True, 'no': False}.get(body.get('works'))
        _, needs = actions.review(app.engine_factory, pid, works, str(body.get('text', ''))[:8000],
                                  bool(body.get('finish')), channel,
                                  actor='owner_delegated_test' if app.test_mode else 'owner')
        if needs:
            actions.launch(app.workspace, store, pid, app.launcher)
        return {'ok': True}
    if action == 'close':
        choice = body.get('choice')
        if choice not in (None, 'save', 'pause', 'discard'):
            raise Rejected('choice must be save, pause or discard')
        p = actions.close(app.engine_factory, pid, choice, channel, body.get('satisfaction'), str(body.get('why', ''))[:500],
                          bool(body.get('confirm')))
        return {'state': p['state']}
    if action == 'result':
        shown = {}
        engine = app.engine_factory()
        try:
            mode = ((engine.store.project(pid)['plan'] or {}).get('runtime') or {}).get('mode', 'cli')
            if mode in ('web', 'server') and engine.result_info(pid)[0] == 'run':
                choice = body.get('choice')
                if choice not in (None, 'previous', 'empty'):
                    raise Rejected('choice must be previous or empty')
                return {'how': 'web', **app.owner_runs.start(engine, pid, choice)}
            how, path = engine.open_result(pid, show_text=lambda title, text, p: shown.update(title=title, text=text[:200000]))
        finally:
            engine.store.close()
        return {'how': how, 'path': str(path), **shown}
    if action == 'result-stop':
        return app.owner_runs.stop(store, pid, reason='owner')
    if action == 'result-save':
        return app.owner_runs.save(pid, reason='owner')
    raise KeyError('unknown action')


def serve(workspace=WORKSPACE, port=8765, **kw):
    app = App(workspace, port, **kw)
    httpd = ThreadingHTTPServer(('127.0.0.1', port), type('H', (Handler,), {'app': app}))
    httpd.daemon_threads = True
    app.httpd = httpd
    info = Path(workspace) / 'web-server.json'
    Path(workspace).mkdir(parents=True, exist_ok=True)
    info.write_text(json.dumps({'pid': os.getpid(), 'port': port, 'token': app.token, 'started': app.started}),
                    encoding='utf-8')
    return app, httpd


def stop_running(workspace=WORKSPACE):
    """Ask the server started from this workspace to shut down (its token is in the workspace, never in the page
    of another site). Returns a message."""
    import urllib.request
    info = Path(workspace) / 'web-server.json'
    try:
        data = json.loads(info.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return '실행 중인 웹 서버 기록이 없습니다.'
    req = urllib.request.Request(f"http://127.0.0.1:{data['port']}/api/shutdown", data=b'{}', method='POST',
                                 headers={'X-AXB-Token': data['token'], 'Content-Type': 'application/json'})
    try:
        urllib.request.urlopen(req, timeout=5).read()
    except OSError as e:
        return f'서버에 연결하지 못했습니다 ({e}). 이미 종료되었을 수 있습니다.'
    info.unlink(missing_ok=True)
    return '웹 서버를 종료했습니다.'


def main(port=8765, test_mode=False):
    app, httpd = serve(port=port, test_mode=test_mode)
    print(f'AX Branch web UI: http://127.0.0.1:{port}/  (stop: Ctrl+C or `python -m axbranch web --stop`)', flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        app.owner_runs.stop_all()
        httpd.server_close()
        (WORKSPACE / 'web-server.json').unlink(missing_ok=True)
