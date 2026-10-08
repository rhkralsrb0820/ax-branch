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
import html
import http.client
import http.server
import json
import re
import os
import shutil
import socket
import tempfile
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
OBSERVE_SECONDS = 10            # the exact Owner launch must still serve this long after it started

# Every launch of the artifact goes through this wrapper: an audit hook records what the program does
# outside itself (connections, name lookups, subprocesses, browser opens) to AXB_AUDIT_LOG, then the
# entry file runs as __main__ exactly as `python <entry> args` would. Evidence for "zero external
# connections" (P-bbad3c v31: no outbound log existed at all).
AUDIT = r'''import json, os, runpy, sys, time
_log = os.environ.get('AXB_AUDIT_LOG')
_kinds = ('socket.connect', 'socket.sendto', 'socket.getaddrinfo', 'subprocess.Popen', 'os.system',
          'os.startfile', 'webbrowser.open')
def _clip(v):
    if v is None or isinstance(v, (bool, int, float)):
        return v
    if isinstance(v, (tuple, list)):
        return [_clip(x) for x in v[:20]]
    return str(v)[:500]
def _hook(event, args):
    if _log and event in _kinds:
        try:
            line = json.dumps({'t': time.time(), 'pid': os.getpid(), 'event': event, 'args': _clip(args)})
            with open(_log, 'a', encoding='utf-8') as f:
                f.write(line + '\n')
        except Exception:
            pass
sys.addaudithook(_hook)
# As `python <entry> args`: argv[0] as given, the script's folder first on sys.path, absolute __file__.
sys.argv = sys.argv[1:]
_entry = os.path.abspath(sys.argv[0])
sys.path[0] = os.path.dirname(_entry)
runpy.run_path(_entry, run_name='__main__')
'''
AUDIT_NOTE = ('every artifact process was started through a Python audit hook (socket.connect/sendto/getaddrinfo, '
              'subprocess.Popen, os.system, os.startfile, webbrowser.open) that logs to a file; child processes '
              'are logged as subprocess events, not intercepted themselves')


def _local(host):
    """True for loopback/unspecified addresses (incl. IPv4-mapped IPv6) and the name localhost."""
    import ipaddress
    if host in (None, '', 'None'):
        return True
    try:
        ip = ipaddress.ip_address(str(host).split('%')[0])
    except ValueError:
        name = str(host).lower().rstrip('.')
        return name == 'localhost' or name.endswith('.localhost')
    ip = getattr(ip, 'ipv4_mapped', None) or ip
    return ip.is_loopback or ip.is_unspecified
RESPONSE_LIMIT = 5_000_000      # bytes of an HTTP probe response that are checked
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
        probes = []
        for p in spec.get('probes', []):
            method = p.get('http_method') or ''
            if method != 'BROWSER' and not p.get('http_path'):
                if method:     # no path: it runs as a subprocess of the program, so its method is meaningless
                    notes.append(f"probe {p.get('name')!r}: http_method {method} dropped (no http_path: subprocess probe)")
                method = ''
            else:
                method = method or 'GET'
            probes.append({**p, 'http_method': method})
        spec['probes'] = probes
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
    ev = {'mode': mode, 'owner_launch': spec.get('owner_launch', ''), 'steps': [], 'notes': corrections,
          'launch_args': spec.get('launch_args', [])}
    if mode == 'none':
        ev.update(ok=True, notes=corrections + ['no runtime surface declared (document or library)'])
        return ev
    audit_dir = tempfile.mkdtemp(prefix='axb-net-')
    audit_log = os.path.join(audit_dir, 'audit.jsonl')
    base = Launch([python, '-E', '-s', '-X', 'utf8', '-c', AUDIT, entry_path], {'AXB_AUDIT_LOG': audit_log}, cwd)
    try:
        _check(spec, mode, base, cwd, ev, on_step)
        ev['network'] = network_summary(audit_log)
    finally:
        shutil.rmtree(audit_dir, ignore_errors=True)
    return ev


class Launch:
    """How the artifact is started (the audit wrapper + the clean environment), and its record."""

    def __init__(self, argv, env, cwd):
        self.argv, self.env, self.cwd = argv, env, cwd

    def start(self, args, stdin_text='', split=False):
        return sandbox.start(self.argv + list(args), self.cwd, stdin_text, extra_env=self.env, split=split)

    def record(self, args):
        return {'executable': self.argv[0], 'command': [*self.argv[:-3], '-c', '<AUDIT wrapper>', *self.argv[-1:], *args],
                'cwd': str(self.cwd), 'env_keys': sorted({*sandbox.clean_env('.'), *self.env}),
                'launcher': 'runpy.run_path(entry, run_name="__main__") under the audit hook'}


def network_summary(path):
    """What the artifact processes did outside themselves during this check, from the audit log."""
    events, malformed = [], 0
    try:
        with open(path, encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    try:
                        events.append(json.loads(line))
                    except ValueError:
                        malformed += 1
    except OSError:
        pass
    external, loopback, ipc, opens, children = [], 0, 0, [], []
    for e in events:
        args = e.get('args') or []
        if e['event'] in ('socket.connect', 'socket.sendto'):
            sock, address = (args + [None, None])[:2]
            if 'AF_UNIX' in str(sock) or not isinstance(address, list):
                ipc += 1                                   # local socket file, not a network peer
                continue
            host, target = address[0] if address else None, address
        elif e['event'] == 'socket.getaddrinfo':
            host, target = (args[0] if args else None), args[:2]
        else:
            host = target = None
        if e['event'].startswith('socket.'):
            if _local(host):
                loopback += 1
            else:
                external.append({'event': e['event'], 'target': target, 'pid': e['pid']})
        elif e['event'] in ('webbrowser.open', 'os.startfile'):
            url = args[0] if args else ''
            # one webbrowser.open() raises nested audit events (open -> open_new_tab -> controller)
            if not (opens and opens[-1]['url'] == url and opens[-1]['pid'] == e['pid'] and e['t'] - opens[-1]['t'] < 1):
                opens.append({'url': url, 'pid': e['pid'], 't': e['t']})
        else:
            children.append({'event': e['event'], 'args': str(args)[:300], 'pid': e['pid']})
    return {'interception': AUDIT_NOTE, 'log_events': len(events), 'malformed_log_lines': malformed,
            'processes': len({e['pid'] for e in events}), 'local_ipc_events': ipc,
            'external_connections': external[:50], 'external_count': len(external), 'loopback_events': loopback,
            'browser_open_requests': opens[:20], 'subprocesses': children[:20],
            'browser_traffic': 'the headless verification browser is a separate process; its requests to the app '
                               'go through the loopback click proxy and are listed per BROWSER step'}


def _check(spec, mode, base, cwd, ev, on_step):
    if mode == 'cli':
        launch = {'name': 'owner launch', 'args': spec.get('launch_args', []), 'stdin': '', 'expect_exit': -1,
                  'expect_contains': []}
        for probe in [launch, *spec.get('probes', [])]:
            ev['steps'].append(_cli(base, probe))
            if on_step:
                on_step(f"runtime: {probe['name']}")
        ev['ok'] = all(s['ok'] for s in ev['steps'])
        return
    port = free_port()
    args = [a.replace('{port}', str(port)) for a in spec.get('launch_args', [])]
    proc = base.start(args)
    ev['server_launch'] = base.record(args)
    try:
        if mode == 'gui':
            code = proc.wait(GUI_ALIVE)
            ok = code is None
            ev['steps'].append({'name': 'owner launch (window)', 'args': args, 'ok': ok,
                                'problems': [] if ok else [f'exited after <{GUI_ALIVE}s with code {code}'],
                                'output_tail': proc.output()[-1200:]})
            ev['notes'].append('window content was not exercised; only startup and survival were checked')
            ev['ok'] = ok
            return
        ev['port'] = port
        up, waited = _wait_port(proc, port)
        ev['steps'].append({'name': 'server start', 'args': args, 'ok': up, 'seconds': waited,
                            'problems': [] if up else [('process exited with code %s before listening' % proc.proc.poll())
                                                       if not proc.alive() else f'port {port} not listening after {START_TIMEOUT}s']})
        if up:
            probes = spec.get('probes', [])
            for probe in probes:
                if probe.get('http_method') == 'BROWSER':
                    ev['steps'].append({**_rendered(port, probe), 'dispatch': 'browser'})
                elif _is_http(probe):
                    ev['steps'].append({**_http(port, probe), 'dispatch': 'http'})
                else:                       # a command-line check of the same program (e.g. its self-test)
                    ev['steps'].append({**_cli(base, probe), 'dispatch': 'subprocess'})
                if on_step:
                    on_step(f"runtime: {probe['name']}")
            first_http = next((pr for pr in probes if _is_http(pr) and pr.get('http_method') != 'BROWSER'), None)
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
        ev['steps'].append(_exact_owner_launch(base, spec))
    ev['ok'] = all(s['ok'] for s in ev['steps'])


_URL = re.compile(r'https?://(?:127\.0\.0\.1|localhost):(\d+)')


def _is_http(probe):
    """A probe talks to the running server when it names a path (or is a BROWSER probe); otherwise it is a
    command-line run of the program. Plans mix both in web mode (P-bbad3c v21: a self-test probe was sent
    to the server as GET '' and judged as a product failure, and reused for two follow-up checks)."""
    return probe.get('http_method') == 'BROWSER' or bool(probe.get('http_path'))


def _cli(base, probe):
    started, at = time.monotonic(), time.strftime('%Y-%m-%d %H:%M:%S')
    args = list(probe.get('args') or [])
    proc = base.start(args, probe.get('stdin', ''), split=True)
    try:
        code = proc.wait(CLI_TIMEOUT)
        proc.stop()
        stdout, stderr = proc.streams()
    finally:
        proc.stop()
        proc.cleanup()
    out = stdout + stderr
    step = {'name': probe['name'], 'args': args, **base.record(args), 'started_at': at,
            'stdin_bytes': len((probe.get('stdin') or '').encode('utf-8')), 'exit': code,
            'seconds': round(time.monotonic() - started, 2), 'output_tail': out[-1200:],
            'stdout_tail': stdout[-2000:], 'stderr_tail': stderr[-2000:]}
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
    return step


def _announced(proc, hinted=None):
    """The port the program announced (or the one the Owner was told), or None."""
    started = time.monotonic()
    while time.monotonic() - started < START_TIMEOUT and proc.alive():
        found = _URL.search(proc.output())
        if found:
            return int(found.group(1))
        time.sleep(0.25)
    return int(hinted.group(1)) if hinted and proc.alive() else None


def _exact_owner_launch(base, spec):
    """The Owner's double-click: no arguments, default port, browser. Recorded: the full command, the
    browser-open request (audit hook; the clean environment makes it a no-op), the server still serving
    OBSERVE_SECONDS after start and after the whole HTTP flow on this same process, and a second launch
    while the first one holds the port (fallback observation)."""
    step = {'name': 'exact Owner launch (no arguments)', 'args': [], **base.record([]),
            'started_at': time.strftime('%Y-%m-%d %H:%M:%S')}
    t0 = time.time()
    proc = base.start([], split=True)
    try:
        hinted = _URL.search(spec.get('owner_launch', ''))
        port = _announced(proc, hinted)
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
        http_probes = [pr for pr in spec.get('probes', []) if _is_http(pr) and pr.get('http_method') != 'BROWSER']
        probes = http_probes or [
            {'name': 'page', 'http_method': 'GET', 'http_path': '/', 'expect_status': 200, 'expect_contains': []}]
        first = _http(port, {**probes[0], 'name': 'first page'})
        problems = list(first['problems'])
        # Same process: the whole HTTP flow (e.g. its self-test endpoint), then still serving.
        flow = [{k: s.get(k) for k in ('name', 'request', 'status', 'ok', 'problems')}
                for s in (_http(port, pr) for pr in http_probes[1:])]
        problems += [f"flow {s['name']}: {p}" for s in flow if not s['ok'] for p in s['problems']]
        time.sleep(max(0.0, OBSERVE_SECONDS - (time.time() - t0)))
        again = _http(port, {**probes[0], 'name': f'first page after {OBSERVE_SECONDS}s and the flow'})
        if not again['ok']:
            problems += [f'after the flow: {p}' for p in again['problems']]
        if not proc.alive():
            problems.append(f'server exited (code {proc.proc.poll()})')
        step.update(status=first.get('status'), observed_seconds=round(time.time() - t0, 1),
                    alive_after_observation=proc.alive(), same_process_flow=flow,
                    browser_open_requests=_opens(base, proc.proc.pid),
                    busy_port_second_launch=_second_launch(base, port, hinted))
        stdout, stderr = proc.streams()
        step.update(stdout_tail=stdout[-1500:], stderr_tail=stderr[-1500:], ok=not problems, problems=problems)
        return step
    finally:
        proc.stop()
        proc.cleanup()


def _opens(base, pid):
    log = base.env.get('AXB_AUDIT_LOG')
    return [o for o in network_summary(log)['browser_open_requests'] if o['pid'] == pid] if log else []


def _second_launch(base, busy_port, hinted):
    """Observation only (no verdict): what a second double-click does while the default port is taken."""
    proc = base.start([], split=True)
    try:
        port = _announced(proc, None)
        rec = {'announced_port': port, 'differs_from_busy_port': port is not None and port != busy_port,
               'alive': proc.alive()}
        if port is not None and port != busy_port and _wait_port(proc, port)[0]:
            rec['first_page_status'] = _http(port, {'name': 'second launch page', 'http_method': 'GET',
                                                    'http_path': '/'}).get('status')
        rec['output_tail'] = proc.output()[-600:]
        return rec
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


def _click_proxy(port, path, selectors, needles=(), budget=10000):
    """Forward the app through loopback, injecting clicks and a visible-text report only into the requested
    HTML page. The report (JSON in #axb-report) is what the page SHOWS: document.body.innerText after the
    clicks (closed <details> content and hidden elements are not in it), with click records, every
    <details> open state, page loads in this tab, and for each must-not-contain text the elements that hold
    it with their visibility. P-bbad3c v31: --dump-dom serialized collapsed content as if it were shown."""
    # Escape '<' so a selector can never terminate the injected script element.
    encoded = json.dumps(selectors).replace('<', r'\u003c')
    wanted = json.dumps([n for n in needles if n]).replace('<', r'\u003c')
    script = ('''<script>document.addEventListener('DOMContentLoaded', async () => {
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
let loads = 0;
try { loads = Number(sessionStorage.getItem('axb-loads') || 0) + 1; sessionStorage.setItem('axb-loads', loads); } catch (e) {}
const report = {href: location.href, userAgent: navigator.userAgent, page_loads_in_tab: loads,
                navigation: (performance.getEntriesByType('navigation')[0] || {}).type || null, clicks: []};
const finish = () => {
    report.innerText = document.body.innerText;
    report.details = [...document.querySelectorAll('details')].map(d => ({id: d.id || null, open: d.open,
        summary: (d.querySelector('summary') || {}).textContent || ''}));
    report.offending = [];
    for (const needle of NEEDLES) {
        const holders = [...document.body.querySelectorAll('*')].filter(el => !['SCRIPT', 'STYLE'].includes(el.tagName)
            && el.textContent.includes(needle) && ![...el.children].some(c => c.textContent.includes(needle)));
        for (const el of holders.slice(0, 5)) {
            const d = el.closest('details');
            report.offending.push({text: needle, tag: el.tagName.toLowerCase(), id: el.id || null,
                visible: typeof el.checkVisibility === 'function' ? el.checkVisibility() : null,
                in_inner_text: report.innerText.includes(needle),
                inside_details: d ? {id: d.id || null, open: d.open} : null});
        }
    }
    const out = document.createElement('script');
    out.type = 'application/json'; out.id = 'axb-report';
    out.textContent = JSON.stringify(report).replace(/</g, '\\\\u003c');
    document.body.appendChild(out);
};
for (const selector of SELECTORS) {
    const deadline = performance.now() + 5000;
    let element;
    try {
        while (!(element = document.querySelector(selector)) && performance.now() < deadline)
            await sleep(50);
    } catch (e) { report.clicks.push({selector, problem: 'invalid'}); return finish(); }
    if (!element) { report.clicks.push({selector, problem: 'missing'}); return finish(); }
    element.click();
    report.clicks.push({selector, clicked: true, tag: element.tagName.toLowerCase(), id: element.id || null,
                        at_ms: Math.round(performance.now())});
    await sleep(300);
}
// The visible text is taken at the end of the browser's time budget, not right after load: content
// that appears late (results) or is added late (forbidden text) must be what is judged.
await sleep(Math.max(300, BUDGET_MS - 1500 - performance.now()));
finish();
});</script>''')
    values = {'SELECTORS': encoded, 'NEEDLES': wanted, 'BUDGET_MS': str(int(budget))}
    script = re.sub('SELECTORS|NEEDLES|BUDGET_MS', lambda m: values[m.group()], script).encode('ascii')
    requests = []

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
                requests.append(f'{self.command} {self.path} -> {response.status}')
                content_type = response.getheader('Content-Type', '').lower()
                inject = (self.command == 'GET' and self.path == path
                          and ('text/html' in content_type or (not content_type and body.lstrip().startswith(b'<'))))
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
                        injected = re.sub(b'</body\\s*>', lambda m: script + m.group(), body, count=1, flags=re.I)
                        body = injected if injected != body else body + script      # a page without </body>
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
    proxy.requests = requests
    thread = threading.Thread(target=proxy.serve_forever, daemon=True)
    thread.start()
    return proxy, thread


def _dump_dom(exe, port, path, selectors, needles=(), record=None):
    """One headless-browser load through the click proxy: the DOM (stdout only), or None if the browser did
    not finish in time. record (dict) receives the proxied requests and the browser's stderr."""
    profile = tempfile.mkdtemp(prefix='axb-browser-')
    proxy, thread, proc = None, None, None
    record = {} if record is None else record
    try:
        budget = max(10000, len(selectors) * 5300 + 2000)
        proxy, thread = _click_proxy(port, path, selectors, needles, budget)
        proc = sandbox.start([exe, '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
                              '--disable-logging', '--log-level=3',
                              f'--user-data-dir={profile}', f'--virtual-time-budget={budget}', '--dump-dom',
                              f'http://127.0.0.1:{proxy.server_port}{path}'], profile, env=dict(os.environ), caps=False,
                             split=True)
        finished = proc.wait(BROWSER_TIMEOUT) is not None
        dom, err = proc.streams()
        record.update(browser_requests=list(proxy.requests), browser_stderr_tail=err[-600:])
        return dom if finished else None
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
    step['browser'] = exe
    # One retry, only when the browser itself did not finish: headless Edge occasionally hangs under
    # heavy load (seen once in a full test run; the same probe then took 3 s). A page that really
    # hangs the browser fails both attempts; a content mismatch is never retried.
    for attempt in (1, 2):
        record = {}
        dom = _dump_dom(exe, port, path, selectors, probe.get('expect_absent', []), record)
        if dom is not None:
            break
    step.update(attempts=attempt, **record)
    if dom is None:
        step.update(ok=False, problems=[f'browser did not finish within {BROWSER_TIMEOUT}s (2 attempts)'])
        return step
    found = re.findall(r'<script type="application/json" id="axb-report">(.*?)</script>', dom, flags=re.S)
    try:
        report = json.loads(found[-1]) if found else None
        if not isinstance(report, dict) or not {'innerText', 'clicks', 'details', 'offending'} <= report.keys():
            report = None
    except ValueError:
        report = None
    if report is None:
        step.update(ok=False, harness_error=True,
                    problems=['harness: no visible-text report (the page never reached DOMContentLoaded with a <body>, '
                              'or the browser dumped it before the report was written)'],
                    dom_tail=re.sub(r'\s+', ' ', dom)[-600:])
        return step
    bad = next((c for c in report['clicks'] if c.get('problem')), None)
    if bad:
        what = 'is not a CSS selector' if bad['problem'] == 'invalid' else 'matched nothing on the page'
        ids = sorted(set(re.findall(r'\bid="([^"]+)"', dom)) - {'axb-report'})[:60]
        step.update(ok=False, probe_misconfigured=True, clicks=report['clicks'],
                    problems=[f"probe misconfigured: click selector {bad['selector'][:120]!r} {what} "
                              "(http_body of a BROWSER probe = CSS selectors separated by '||'); "
                              f"element ids on the page: {', '.join('#' + i for i in ids) or 'none'}"])
        return step
    text = report['innerText']
    missing = _contains(text, probe.get('expect_contains', []))
    absent = _present(text, probe)
    step.update(ok=not missing and not absent, problems=([f'rendered page lacks {missing}'] if missing else []) + absent,
                text_source='document.body.innerText after the clicks (what the page shows)',
                user_agent=report['userAgent'], href=report['href'], navigation=report['navigation'],
                page_loads_in_tab=report['page_loads_in_tab'], clicks=report['clicks'], details=report['details'][:20],
                offending=report['offending'][:20], rendered_tail=re.sub(r'\s+', ' ', text)[-800:])
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
        raw = resp.read(RESPONSE_LIMIT + 1)
        text = raw[:RESPONSE_LIMIT].decode('utf-8', errors='replace')
        if len(raw) > RESPONSE_LIMIT:
            problems.append(f'response larger than {RESPONSE_LIMIT} bytes; checked only the first part')
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
