"""Runtime Acceptance Verification: run the artifact the way the Owner will, and record evidence.

Source review and unit tests are not enough (owner acceptance 2026-10-04: a program that passed
both closed 0.3 s after a double-click, and offered no page to connect to). The CEO's plan declares
how the Owner launches the artifact and which probes exercise its primary flow; this module runs
them under containment (sandbox) and returns evidence. PASS needs every probe to hold.

Modes
  none  documents and pure libraries: nothing to launch.
  cli   each probe = `python <entry> *args` with stdin; exit code and output checked.
  web   start `python <entry> *launch_args` ('{port}' -> a free local port), wait for the port,
        run HTTP probes, require the server to survive them and still answer afterwards.
  gui   start it and require it to stay up; the window itself is not exercised (recorded).
"""
import http.client
import re
import socket
import time

from . import sandbox

INT = {'type': 'integer'}
STR = {'type': 'string'}
_ARR = lambda item: {'type': 'array', 'items': item}


def _obj(**props):
    return {'type': 'object', 'additionalProperties': False, 'properties': props, 'required': list(props)}


PROBE = _obj(name=STR, args=_ARR(STR), stdin=STR, http_method={'type': 'string', 'enum': ['', 'GET', 'POST', 'BROWSER']},
             http_path=STR, http_body=STR, expect_exit=INT, expect_status=INT, expect_contains=_ARR(STR))
SPEC = _obj(mode={'type': 'string', 'enum': ['none', 'cli', 'web', 'gui']}, owner_launch=STR,
            launch_args=_ARR(STR), probes=_ARR(PROBE))

# Plans made before 0.1.8 carry no spec: judge them by the Owner's realistic launch (double-click).
DEFAULT = {'mode': 'cli', 'owner_launch': 'double-click the file (python <file>, no arguments)',
           'launch_args': [], 'probes': []}

START_TIMEOUT, PROBE_TIMEOUT, CLI_TIMEOUT, GUI_ALIVE, BROWSER_TIMEOUT = 25, 15, 60, 6, 90
EDGE_PATHS = (r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
              r'C:\Program Files\Microsoft\Edge\Application\msedge.exe')


def browser():
    """A local headless browser that executes page JavaScript (Edge ships with Windows), or None."""
    import os
    import shutil
    return next((p for p in EDGE_PATHS if os.path.isfile(p)), None) or shutil.which('msedge') or shutil.which('chrome')


def normalize(spec):
    """Enforce the launch contract deterministically (a prompt rule alone was not enough: a live
    plan asked for a web app with launch_args=[], which would bind a fixed port and open the
    Owner's browser during verification). Returns (spec, notes)."""
    spec = dict(spec or DEFAULT)
    notes = []
    if spec.get('mode') == 'web':
        args = list(spec.get('launch_args') or [])
        if '{port}' not in args:
            args = ['--port', '{port}', '--no-browser']
            notes.append('launch_args set to --port {port} --no-browser (web contract)')
        elif '--no-browser' not in args:
            args.append('--no-browser')
            notes.append('--no-browser added (web contract)')
        spec['launch_args'] = args
        spec['probes'] = [{**p, 'http_method': p.get('http_method') or 'GET'} for p in spec.get('probes', [])]
    return spec, notes


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def _contains(text, needles):
    missing = [n for n in needles if n not in text]
    return missing


def check(spec, entry_path, python, cwd):
    """Run the spec against the artifact copied in cwd. Returns an evidence dict with 'ok'."""
    spec, corrections = normalize(spec)
    mode = spec.get('mode', 'cli')
    base = [python, '-E', '-s', '-X', 'utf8', entry_path]
    ev = {'mode': mode, 'owner_launch': spec.get('owner_launch', ''), 'steps': [], 'notes': corrections,
          'launch_args': spec.get('launch_args', [])}
    if mode == 'none':
        ev.update(ok=True, notes=corrections + ['no runtime surface declared (document or library)'])
        return ev
    if mode == 'cli':
        launch = {'name': 'owner launch', 'args': spec.get('launch_args', []), 'stdin': '', 'expect_exit': -1,
                  'expect_contains': []}
        for probe in [launch, *spec.get('probes', [])]:
            started = time.monotonic()
            code, out = sandbox.run(base + list(probe['args']), cwd, CLI_TIMEOUT, probe.get('stdin', ''))
            step = {'name': probe['name'], 'args': probe['args'], 'exit': code,
                    'seconds': round(time.monotonic() - started, 2), 'output_tail': out[-1200:]}
            problems = []
            if code is None:
                problems.append(f'did not finish within {CLI_TIMEOUT}s')
            elif probe.get('expect_exit', -1) >= 0 and code != probe['expect_exit']:
                problems.append(f"exit {code}, expected {probe['expect_exit']}")
            elif probe.get('expect_exit', -1) < 0 and code not in (0,) and 'Traceback' in out:
                problems.append(f'crashed (exit {code})')
            missing = _contains(out, probe.get('expect_contains', []))
            if missing:
                problems.append(f'output lacks {missing}')
            step.update(ok=not problems, problems=problems)
            ev['steps'].append(step)
        ev['ok'] = all(s['ok'] for s in ev['steps'])
        return ev
    port = free_port()
    args = [a.replace('{port}', str(port)) for a in spec.get('launch_args', [])]
    proc = sandbox.start(base + args, cwd)
    try:
        if mode == 'gui':
            code = proc.wait(GUI_ALIVE)
            ok = code is None
            ev['steps'].append({'name': 'owner launch (window)', 'args': args, 'ok': ok,
                                'problems': [] if ok else [f'exited after <{GUI_ALIVE}s with code {code}'],
                                'output_tail': proc.output()[-1200:]})
            ev['notes'].append('window content was not exercised; only startup and survival were checked')
            ev['ok'] = ok
            return ev
        ev['port'] = port
        up, waited = _wait_port(proc, port)
        ev['steps'].append({'name': 'server start', 'args': args, 'ok': up, 'seconds': waited,
                            'problems': [] if up else [('process exited with code %s before listening' % proc.proc.poll())
                                                       if not proc.alive() else f'port {port} not listening after {START_TIMEOUT}s']})
        if up:
            probes = spec.get('probes', [])
            for probe in probes:
                ev['steps'].append(_rendered(port, probe) if probe.get('http_method') == 'BROWSER' else _http(port, probe))
            first_http = next((pr for pr in probes if pr.get('http_method') != 'BROWSER'), None)
            if first_http:   # still serving after the flow, and the first page still answers
                again = _http(port, {**first_http, 'name': f"{first_http['name']} (again after flow)"})
                ev['steps'].append(again)
            alive = proc.alive()
            ev['steps'].append({'name': 'server survived', 'ok': alive,
                                'problems': [] if alive else [f'server process exited with code {proc.proc.poll()}']})
        ev['server_output_tail'] = proc.output()[-1500:]
    finally:
        proc.stop()
        proc.cleanup()
    if ev['steps'][0]['ok']:
        # The verification launch above uses --port/--no-browser. The Owner double-clicks: no arguments,
        # fixed port, browser. Check exactly that too (browser neutralized by the clean environment).
        ev['steps'].append(_exact_owner_launch(base, cwd, spec))
    ev['ok'] = all(s['ok'] for s in ev['steps'])
    return ev


_URL = re.compile(r'https?://(?:127\.0\.0\.1|localhost):(\d+)')


def _exact_owner_launch(base, cwd, spec):
    step = {'name': 'exact Owner launch (no arguments)', 'args': []}
    proc = sandbox.start(base, cwd)
    try:
        port, started = None, time.monotonic()
        hinted = _URL.search(spec.get('owner_launch', ''))
        while time.monotonic() - started < START_TIMEOUT and proc.alive():
            found = _URL.search(proc.output())
            if found:
                port = int(found.group(1))
                break
            time.sleep(0.25)
        if port is None and hinted and proc.alive():
            port = int(hinted.group(1))          # not announced: use the port the Owner was told
        if port is None:
            step.update(ok=False, problems=['process exited before serving' if not proc.alive()
                                            else 'no local URL announced and none in the Owner instructions'],
                        output_tail=proc.output()[-800:])
            return step
        up, waited = _wait_port(proc, port)
        step.update(port=port, seconds=waited)
        if not up:
            step.update(ok=False, problems=[f'nothing listening on {port}'], output_tail=proc.output()[-800:])
            return step
        probes = [pr for pr in spec.get('probes', []) if pr.get('http_method') != 'BROWSER'] or [
            {'name': 'page', 'http_method': 'GET', 'http_path': '/', 'expect_status': 200, 'expect_contains': []}]
        first = _http(port, {**probes[0], 'name': 'first page'})
        step.update(ok=first['ok'] and proc.alive(), problems=first['problems'] + ([] if proc.alive() else ['server exited']),
                    status=first.get('status'))
        return step
    finally:
        proc.stop()
        proc.cleanup()


def _wait_port(proc, port):
    started = time.monotonic()
    while time.monotonic() - started < START_TIMEOUT:
        if not proc.alive():
            return False, round(time.monotonic() - started, 2)
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=1):
                return True, round(time.monotonic() - started, 2)
        except OSError:
            time.sleep(0.25)
    return False, START_TIMEOUT


def _rendered(port, probe):
    """BROWSER probe: load the page in a real headless browser (scripts run, the page's own API calls
    happen) and check the RENDERED text — script source is stripped so code text cannot fake a match."""
    import os
    import tempfile
    path = probe.get('http_path') or '/'
    step = {'name': probe['name'], 'request': f'BROWSER {path}'}
    exe = browser()
    if exe is None:
        step.update(ok=False, problems=['no headless browser available on this PC (Edge/Chrome)'])
        return step
    profile = tempfile.mkdtemp(prefix='axb-browser-')
    proc = sandbox.start([exe, '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
                          '--disable-logging', '--log-level=3',
                          f'--user-data-dir={profile}', '--virtual-time-budget=10000', '--dump-dom',
                          f'http://127.0.0.1:{port}{path}'], profile, env=dict(os.environ), caps=False)
    try:
        if proc.wait(BROWSER_TIMEOUT) is None:
            step.update(ok=False, problems=[f'browser did not finish within {BROWSER_TIMEOUT}s'])
            return step
        dom = proc.output()
    finally:
        proc.stop()
        proc.cleanup()
    text = re.sub(r'<script\b.*?</script>', ' ', dom, flags=re.S | re.I)
    text = re.sub(r'<style\b.*?</style>', ' ', text, flags=re.S | re.I)
    missing = _contains(text, probe.get('expect_contains', []))
    step.update(ok=not missing, problems=[f'rendered page lacks {missing}'] if missing else [],
                rendered_tail=re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', text))[-800:])
    return step


def _http(port, probe):
    method = probe.get('http_method') or 'GET'
    body = probe.get('http_body') or None
    headers = {}
    if body is not None:
        headers['Content-Type'] = 'application/json' if body.lstrip().startswith(('{', '[')) else 'application/x-www-form-urlencoded'
    step = {'name': probe['name'], 'request': f"{method} {probe.get('http_path') or '/'}"}
    problems = []
    try:
        con = http.client.HTTPConnection('127.0.0.1', port, timeout=PROBE_TIMEOUT)
        con.request(method, probe.get('http_path') or '/', body=body.encode('utf-8') if body else None, headers=headers)
        resp = con.getresponse()
        text = resp.read(200_000).decode('utf-8', errors='replace')
        con.close()
        step.update(status=resp.status, body_tail=text[:800])
        if probe.get('expect_status', 0) and resp.status != probe['expect_status']:
            problems.append(f"status {resp.status}, expected {probe['expect_status']}")
        missing = _contains(text, probe.get('expect_contains', []))
        if missing:
            problems.append(f'response lacks {missing}')
    except (ConnectionResetError, ConnectionAbortedError, http.client.RemoteDisconnected, BrokenPipeError) as e:
        problems.append(f'connection lost: {type(e).__name__}: {e}')
    except (OSError, http.client.HTTPException) as e:
        problems.append(f'request failed: {type(e).__name__}: {e}')
    step.update(ok=not problems, problems=problems)
    return step
