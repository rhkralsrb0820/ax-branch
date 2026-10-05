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
import http.server
import json
import re
import socket
import threading
import time

from . import sandbox

INT = {'type': 'integer'}
STR = {'type': 'string'}
_ARR = lambda item: {'type': 'array', 'items': item}


def _obj(**props):
    return {'type': 'object', 'additionalProperties': False, 'properties': props, 'required': list(props)}


PROBE = _obj(name=STR, args=_ARR(STR), stdin=STR, http_method={'type': 'string', 'enum': ['', 'GET', 'POST', 'BROWSER']},
             http_path=STR, http_body=STR, expect_exit=INT, expect_status=INT, expect_contains=_ARR(STR),
             expect_absent=_ARR(STR))
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


def _present(text, probe):
    """Problems from expect_absent: text that must NOT appear (e.g. a fabricated value or a traceback).
    'Must contain' alone could not tell '103 104' apart from the fabricated '103104' (2026-10-05)."""
    found = [n for n in probe.get('expect_absent', []) if n and n in text]
    return [f'must not contain {found}'] if found else []


def _contains(text, needles):
    missing = [n for n in needles if n not in text]
    return missing


def check(spec, entry_path, python, cwd, on_step=None):
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
            problems += _present(out, probe)
            step.update(ok=not problems, problems=problems)
            ev['steps'].append(step)
            if on_step:
                on_step(f"runtime: {step['name']}")
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
                if on_step:
                    on_step(f"runtime: {probe['name']}")
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


def _click_proxy(port, path, selectors):
    """Forward the app through loopback, injecting clicks only into the requested HTML page."""
    # Escape '<' so a selector can never terminate the injected script element.
    encoded = json.dumps(selectors).replace('<', r'\u003c')
    script = ('''<script>document.addEventListener('DOMContentLoaded', async () => {
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
for (const selector of SELECTORS) {
    const deadline = performance.now() + 5000;
    let element;
    while (!(element = document.querySelector(selector)) && performance.now() < deadline)
        await sleep(50);
    if (!element) return;
    element.click();
    await sleep(300);
}
});</script>'''.replace('SELECTORS', encoded)).encode('ascii')

    class Proxy(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def forward(self):
            con = http.client.HTTPConnection('127.0.0.1', port, timeout=PROBE_TIMEOUT)
            try:
                # Preserve method, query, headers and body, including chunked request framing.
                con.putrequest(self.command, self.path, skip_host=True, skip_accept_encoding=True)
                upstream = f'127.0.0.1:{port}'
                for key, value in self.headers.items():
                    # The app must see its own address: apps that guard Host/Origin (anti DNS rebinding)
                    # rejected every proxied request (found live on the stock analyzer).
                    if key.lower() == 'host':
                        value = upstream
                    elif key.lower() in ('origin', 'referer'):
                        value = re.sub(r'^(https?://)[^/]+', lambda m: m.group(1) + upstream, value)
                    con.putheader(key, value)
                con.endheaders()
                if self.headers.get('Transfer-Encoding', '').lower() == 'chunked':
                    while True:
                        line = self.rfile.readline()
                        con.send(line)
                        size = int(line.split(b';', 1)[0], 16)
                        if not size:
                            while True:
                                line = self.rfile.readline()
                                con.send(line)
                                if line in (b'\r\n', b''):
                                    break
                            break
                        con.send(self.rfile.read(size + 2))
                elif self.headers.get('Content-Length'):
                    con.send(self.rfile.read(int(self.headers['Content-Length'])))
                response = con.getresponse()
                body = response.read()
                content_type = response.getheader('Content-Type', '').lower()
                inject = (self.command == 'GET' and self.path == path
                          and ('text/html' in content_type or (not content_type
                               and re.search(br'<(?:html|body)\b', body, flags=re.I))))
                if inject:
                    import gzip
                    import zlib
                    encoding = response.getheader('Content-Encoding', '').lower()
                    if encoding == 'gzip':
                        body = gzip.decompress(body)
                    elif encoding == 'deflate':
                        body = zlib.decompress(body)
                    elif encoding not in ('', 'identity'):
                        inject = False
                    if inject:
                        body = re.sub(b'</body\\s*>', lambda m: script + m.group(), body, count=1, flags=re.I)
                        if encoding == 'gzip':
                            body = gzip.compress(body)
                        elif encoding == 'deflate':
                            body = zlib.compress(body)
                self.send_response_only(response.status, response.reason)
                for key, value in response.getheaders():
                    if key.lower() == 'transfer-encoding' or (key.lower() == 'content-length' and inject):
                        continue
                    self.send_header(key, value)
                if inject:
                    self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            finally:
                con.close()

        def __getattr__(self, name):
            if name.startswith('do_'):
                return self.forward
            raise AttributeError(name)

    proxy = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Proxy)
    thread = threading.Thread(target=proxy.serve_forever, daemon=True)
    thread.start()
    return proxy, thread


def _dump_dom(exe, port, path, selectors):
    """One headless-browser load (through the click proxy when selectors are given): the DOM, or None
    if the browser did not finish in time."""
    import os
    import tempfile
    profile = tempfile.mkdtemp(prefix='axb-browser-')
    proxy, thread, proc = None, None, None
    try:
        if selectors:
            proxy, thread = _click_proxy(port, path, selectors)
            port = proxy.server_port
        budget = max(10000, len(selectors) * 5300 + 1000)
        proc = sandbox.start([exe, '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
                              '--disable-logging', '--log-level=3',
                              f'--user-data-dir={profile}', f'--virtual-time-budget={budget}', '--dump-dom',
                              f'http://127.0.0.1:{port}{path}'], profile, env=dict(os.environ), caps=False)
        if proc.wait(BROWSER_TIMEOUT) is None:
            return None
        return proc.output()
    finally:
        if proc is not None:
            proc.stop()
            proc.cleanup()
        if proxy is not None:
            proxy.shutdown()
            proxy.server_close()
            thread.join()


def _rendered(port, probe):
    """BROWSER probe: load the page in a real headless browser (scripts run, the page's own API calls
    happen) and check the RENDERED text — script source is stripped so code text cannot fake a match."""
    path = probe.get('http_path') or '/'
    step = {'name': probe['name'], 'request': f'BROWSER {path}'}
    exe = browser()
    if exe is None:
        step.update(ok=False, problems=['no headless browser available on this PC (Edge/Chrome)'])
        return step
    selectors = [s.strip() for s in (probe.get('http_body') or '').split('||') if s.strip()]
    # One retry, only when the browser itself did not finish: headless Edge occasionally hangs under
    # heavy load (seen once in a full test run; the same probe then took 3 s). A page that really
    # hangs the browser fails both attempts; a content mismatch is never retried.
    for attempt in (1, 2):
        dom = _dump_dom(exe, port, path, selectors)
        if dom is not None:
            break
    step['attempts'] = attempt
    if dom is None:
        step.update(ok=False, problems=[f'browser did not finish within {BROWSER_TIMEOUT}s (2 attempts)'])
        return step
    text = re.sub(r'<script\b.*?</script>', ' ', dom, flags=re.S | re.I)
    text = re.sub(r'<style\b.*?</style>', ' ', text, flags=re.S | re.I)
    missing = _contains(text, probe.get('expect_contains', []))
    absent = _present(text, probe)
    step.update(ok=not missing and not absent, problems=([f'rendered page lacks {missing}'] if missing else []) + absent,
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
        problems += _present(text, probe)
    except (ConnectionResetError, ConnectionAbortedError, http.client.RemoteDisconnected, BrokenPipeError) as e:
        problems.append(f'connection lost: {type(e).__name__}: {e}')
    except (OSError, http.client.HTTPException) as e:
        problems.append(f'request failed: {type(e).__name__}: {e}')
    step.update(ok=not problems, problems=problems)
    return step
