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
import hashlib
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
from pathlib import Path

from . import sandbox

INT = {'type': 'integer'}
STR = {'type': 'string'}
_ARR = lambda item: {'type': 'array', 'items': item}


def _obj(**props):
    return {'type': 'object', 'additionalProperties': False, 'properties': props, 'required': list(props)}


HTTP_METHODS = ('GET', 'POST', 'PUT', 'PATCH', 'DELETE')
PROBE = _obj(name=STR, args=_ARR(STR), stdin=STR,
             http_method={'type': 'string', 'enum': ['', *HTTP_METHODS, 'BROWSER', 'RESTART']},
             http_path=STR, http_body=STR, http_headers=_ARR(STR), expect_exit=INT, expect_status=INT,
             expect_contains=_ARR(STR), expect_absent=_ARR(STR))
# Exact request headers ("Name: value") for direct HTTP probes, e.g. a hostile Origin that the app must refuse.
# Framing headers stay the client's: a probe must not be able to desynchronise the request it is judged on.
_HEADER_NAME = re.compile(r'^[A-Za-z0-9!#$%&\'*+.^_`|~-]{1,64}$')
_FRAMING = {'content-length', 'transfer-encoding', 'connection', 'upgrade', 'expect', 'te', 'trailer'}
MAX_HEADERS, MAX_HEADER_VALUE = 20, 1000


def parse_headers(lines):
    """[(name, value)] from "Name: value" strings, or raise ValueError naming the invalid one."""
    out = []
    for line in list(lines or [])[:MAX_HEADERS + 1]:
        name, sep, value = str(line).partition(':')
        name, value = name.strip(), value.strip()
        if not sep or not _HEADER_NAME.match(name) or any(c in value for c in '\r\n\0') or len(value) > MAX_HEADER_VALUE:
            raise ValueError(f'invalid header {str(line)[:80]!r}')
        try:
            value.encode('latin-1')                 # what http.client sends; anything else is not a valid header
        except UnicodeEncodeError:
            raise ValueError(f'header {name} value is not Latin-1 (percent-encode it)') from None
        if name.lower() in _FRAMING:
            raise ValueError(f'header {name} is set by the client, not by a probe')
        out.append((name, value))
    if len(out) > MAX_HEADERS:
        raise ValueError(f'more than {MAX_HEADERS} headers')
    return out
SPEC = _obj(mode={'type': 'string', 'enum': ['none', 'cli', 'web', 'gui']}, owner_launch=STR,
            launch_args=_ARR(STR), probes=_ARR(PROBE))

# Plans made before 0.1.8 carry no spec: judge them by the Owner's realistic launch (double-click).
DEFAULT = {'mode': 'cli', 'owner_launch': 'double-click the file (python <file>, no arguments)',
           'launch_args': [], 'probes': []}

START_TIMEOUT, PROBE_TIMEOUT, CLI_TIMEOUT, GUI_ALIVE, BROWSER_TIMEOUT = 25, 15, 60, 6, 90
OBSERVE_SECONDS = 10            # the exact Owner launch must still serve this long after it started
SETTLE_MS, CLICK_WAIT_MS = 10000, 500   # after each BROWSER click: the page's requests complete, then 500 ms

# Every launch of the artifact goes through this wrapper: an audit hook records what the program does
# outside itself (connections, name lookups, subprocesses, browser opens) to AXB_AUDIT_LOG, then the
# entry file runs as __main__ exactly as `python <entry> args` would. Evidence for "zero external
# connections" (P-bbad3c v31: no outbound log existed at all).
AUDIT = r'''import ipaddress, json, os, runpy, socket, sys, time
_log = os.environ.get('AXB_AUDIT_LOG')
_allow = {h.strip().lower().rstrip('.') for h in os.environ.get('AXB_ALLOW_HOSTS', '').split(',') if h.strip()}
_allowed_ips, _resolving = set(), []
def _approved(host):
    """An approved domain (or its subdomain), or an address one of them resolved to in this process."""
    if host is None:
        return False
    h = (host.decode() if isinstance(host, bytes) else str(host)).lower().rstrip('.')
    if h in _allowed_ips:
        return True
    if any(h == a or h.endswith('.' + a) for a in _allow):
        if not _resolving:                     # learn its addresses so the following connect() is allowed
            _resolving.append(1)
            try:
                _allowed_ips.update(i[4][0] for i in socket.getaddrinfo(h, None))
            except OSError:
                pass
            finally:
                _resolving.pop()
        return True
    return False
def _local(host):
    if host is None or host in ('', b''):
        return True
    host = host.decode() if isinstance(host, bytes) else str(host)
    try:
        ip = ipaddress.ip_address(host.split('%')[0])
    except ValueError:
        return host.lower().rstrip('.') in ('localhost',) or host.lower().rstrip('.').endswith('.localhost')
    ip = getattr(ip, 'ipv4_mapped', None) or ip
    return ip.is_loopback or ip.is_unspecified
_kinds = ('socket.connect', 'socket.sendto', 'socket.sendmsg', 'socket.getaddrinfo', 'socket.gethostbyname',
          'socket.gethostbyaddr', 'socket.getnameinfo', 'subprocess.Popen', 'os.system', 'os.startfile',
          'webbrowser.open')
def _clip(v):
    if v is None or isinstance(v, (bool, int, float)):
        return v
    if isinstance(v, (bytes, bytearray)):
        return bytes(v[:500]).decode('latin-1')
    if isinstance(v, (tuple, list)):
        return [_clip(x) for x in v[:20]]
    return str(v)[:500]
def _hook(event, args):
    if event not in _kinds:
        return
    host = None
    if event in ('socket.connect', 'socket.sendto', 'socket.sendmsg') and len(args) > 1 and isinstance(args[1], tuple):
        host = args[1][0]
    elif event in ('socket.getaddrinfo', 'socket.gethostbyname', 'socket.gethostbyaddr'):
        host = args[0]
    elif event == 'socket.getnameinfo':
        host = args[0][0] if args and isinstance(args[0], tuple) else None
    blocked = event.startswith('socket.') and not _local(host) and not _approved(host)
    if _log:
        try:
            line = json.dumps({'t': time.time(), 'pid': os.getpid(), 'event': event, 'args': _clip(args),
                               'blocked': blocked})
            with open(_log, 'a', encoding='utf-8') as f:
                f.write(line + '\n')
        except Exception:
            pass
    if blocked:      # verification never reaches the internet; the Owner's run only approved domains
        raise PermissionError(f'AX Branch: external network refused ({host}): not an approved domain'
                              if _allow else f'AX Branch verification: external network refused ({host})')
sys.addaudithook(_hook)
# As `python <entry> args`: argv[0] as given, the script's folder first on sys.path, absolute __file__.
sys.argv = sys.argv[1:]
_entry = os.path.abspath(sys.argv[0])
sys.path[0] = os.path.dirname(_entry)
runpy.run_path(_entry, run_name='__main__')
'''
AUDIT_NOTE = ('every artifact process was started through a Python audit hook (socket.connect/sendto/getaddrinfo, '
              'sendmsg/gethostbyname/gethostbyaddr/getnameinfo, subprocess.Popen, os.system, os.startfile, '
              'webbrowser.open) that logs to a file and REFUSES every non-local connection or name lookup '
              '(PermissionError). Best effort, not an OS firewall: child processes (logged as subprocess events), '
              'native code and the Windows asyncio Proactor connect path are not intercepted, and a connect() to a '
              'host NAME resolves it before the refusal')


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


def browser_candidates():
    """Installed browsers in preference order, including Windows Chrome outside PATH."""
    import os
    import shutil
    paths = [*EDGE_PATHS, r'C:\Program Files\Google\Chrome\Application\chrome.exe',
             r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
             shutil.which('msedge'), shutil.which('chrome')]
    return list(dict.fromkeys(p for p in paths if p and os.path.isfile(p)))


def browser():
    return next(iter(browser_candidates()), None)


def canonical_probe(probe):
    """One meaning for every consumer (planner contract, runtime check, strategy preservation):
    expect_status <= 0 means "any status" (canonical 0) except a server error (5xx fails unless expected
    explicitly); expect_exit < 0 means "any exit" (canonical -1).
    Test #3: the CEO wrote expect_status -1 ("any", as documented for expect_exit) and the check demanded status -1."""
    probe = dict(probe)
    try:
        status = int(probe.get('expect_status') or 0)
    except (TypeError, ValueError):
        status = 0
    probe['expect_status'] = status if status > 0 else 0
    try:
        code = int(probe.get('expect_exit', -1))
    except (TypeError, ValueError):
        code = -1
    probe['expect_exit'] = code if code >= 0 else -1
    return probe


_QUOTES_PROBE = ('output lacks', 'response lacks', 'rendered page lacks', 'browser action', 'harness:')


def classify_step(step):
    """What a failed runtime step shows, from its own evidence only:
    product   = the program itself misbehaved (crash, lost connection, server error, did not start/stop);
    harness   = the probe configuration is demonstrably invalid;
    infra     = the machine/browser failed;
    ambiguous = a mismatch between the probe's expectation and the response (could be either side)."""
    if step.get('ok'):
        return None
    # A message quoting what the probe EXPECTED (its own wording) is not evidence of what the program did:
    # "expect:connection lost" missing from a healthy page must not read as a lost connection (Codex E1).
    problems = ' '.join(p for p in step.get('problems', []) if not p.startswith(_QUOTES_PROBE))
    output = str(step.get('stderr_tail', '')) + str(step.get('output_tail', ''))
    code = step.get('exit')
    crashed = code not in (None, 0) and ('Traceback (most recent call last)' in output
                                       or code < 0 or code >= 0x80000000)
    # server_errors: every 5xx the step observed (e.g. inside the exact Owner launch's flow), as structured evidence:
    # never inferred from message text, which can quote what a probe wrote (Codex E3/E4).
    if crashed or (step.get('status') or 0) >= 500 or step.get('server_errors'):
        return 'product'
    if 'no headless browser' in problems:
        return 'infra'
    if 'browser did not finish' in problems:
        return 'ambiguous'
    if step.get('probe_misconfigured') and 'matched nothing' not in problems and not any(
            c.get('problem') == 'missing' for c in step.get('clicks', [])):
        return 'harness'                 # invalid probe (e.g. selector syntax): its quoted text is not product evidence
    if any(k in problems for k in ('crashed', 'connection lost', 'request failed',
            'did not finish within', 'exited', 'not listening', 'nothing listening', 'before serving', "'Traceback'")):
        return 'product'
    return 'ambiguous'


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
            if method == 'RESTART':          # a step of the flow, not a request: no path
                probes.append({**p, 'http_path': ''})
                continue
            if method != 'BROWSER' and not p.get('http_path'):
                if method:     # no path: it runs as a subprocess of the program, so its method is meaningless
                    notes.append(f"probe {p.get('name')!r}: http_method {method} dropped (no http_path: subprocess probe)")
                method = ''
            else:
                method = method or 'GET'
            if p.get('http_headers') and method in ('', 'BROWSER'):
                notes.append(f"probe {p.get('name')!r}: http_headers apply only to direct HTTP probes (ignored)")
            probes.append({**p, 'http_method': method})
        spec['probes'] = probes
    else:
        dropped = [p.get('name') for p in spec.get('probes', []) if p.get('http_method') == 'RESTART']
        if dropped:
            notes.append(f'RESTART probes {dropped} dropped: only a web server is restarted within one check')
        spec['probes'] = [p for p in spec.get('probes', []) if p.get('http_method') != 'RESTART']
    spec['probes'] = [canonical_probe(p) for p in spec.get('probes', [])]
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


def check(spec, entry_path, python, cwd, on_step=None, executable=None):
    """Run the spec against the artifact copied in cwd. Returns an evidence dict with 'ok'.
    executable: the file name (in cwd) of a built native program: every launch runs IT, never `python <entry>`."""
    spec, corrections = normalize(spec)
    mode = spec.get('mode', 'cli')
    ev = {'mode': mode, 'owner_launch': spec.get('owner_launch', ''), 'steps': [], 'notes': corrections,
          'launch_args': spec.get('launch_args', [])}
    if mode == 'none':
        ev.update(ok=True, notes=corrections + ['no runtime surface declared (document or library)'])
        return ev
    audit_dir = tempfile.mkdtemp(prefix='axb-net-')
    audit_log = os.path.join(audit_dir, 'audit.jsonl')
    if executable:
        # The Owner's real launch target. The audit hook cannot be injected into a frozen program: network evidence
        # for it is unknown, stated rather than implied. The clean environment keeps Python off its PATH.
        base = Launch([str(Path(cwd) / executable)], {}, cwd, native=True)
        ev['native_executable'] = executable
        # The delivery judgment asks for these (P-20261019-32a79d asked three times): which bytes ran, and that no
        # Python was reachable on the PATH they ran with. Measured here, not asserted.
        path = sandbox.clean_env('.')['PATH']
        ev['native_executable_sha256'] = hashlib.sha256((Path(cwd) / executable).read_bytes()).hexdigest()
        ev['execution_environment'] = {
            'PATH': path, 'python_on_path': [str(Path(d) / n) for d in path.split(os.pathsep) if d
                                             for n in ('python.exe', 'python3.exe', 'py.exe', 'python')
                                             if (Path(d) / n).is_file()]}
        ev['notes'] = ev['notes'] + [f'every launch ran the built {executable}, not the Python source; verified on '
                                     'this PC with a clean environment, NOT on a clean Windows machine']
    else:
        base = Launch([python, '-E', '-s', '-X', 'utf8', '-c', AUDIT, entry_path], {'AXB_AUDIT_LOG': audit_log}, cwd)
    try:
        _check(spec, mode, base, cwd, ev, on_step)
        ev['network'] = network_summary(audit_log) if not executable else {
            'unknown': 'native executable: the in-process network audit hook cannot be injected'}
    finally:
        shutil.rmtree(audit_dir, ignore_errors=True)
    return ev


class Launch:
    """How the artifact is started (the audit wrapper + the clean environment), and its record."""

    def __init__(self, argv, env, cwd, native=False):
        self.argv, self.env, self.cwd, self.native = argv, env, cwd, native

    def at(self, cwd):
        """The same launch from another folder (a native program runs ITS copy there)."""
        argv = [str(Path(cwd) / Path(self.argv[0]).name)] if self.native else self.argv
        return Launch(argv, self.env, cwd, self.native)

    def start(self, args, stdin_text='', split=False):
        return sandbox.start(self.argv + list(args), self.cwd, stdin_text, extra_env=self.env, split=split)

    def record(self, args):
        if self.native:
            return {'executable': self.argv[0], 'command': [*self.argv, *args], 'cwd': str(self.cwd),
                    'env_keys': sorted({*sandbox.clean_env('.'), *self.env}), 'launcher': 'native executable'}
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
        if e['event'] in ('socket.connect', 'socket.sendto', 'socket.sendmsg'):
            sock, address = (args + [None, None])[:2]
            if 'AF_UNIX' in str(sock) or not isinstance(address, list):
                ipc += 1                                   # local socket file, not a network peer
                continue
            host, target = address[0] if address else None, address
        elif e['event'] in ('socket.getaddrinfo', 'socket.gethostbyname', 'socket.gethostbyaddr'):
            host, target = (args[0] if args else None), args[:2]
        elif e['event'] == 'socket.getnameinfo':
            host = args[0][0] if args and isinstance(args[0], list) and args[0] else None
            target = args[:1]
        else:
            host = target = None
        if e['event'].startswith('socket.'):
            if _local(host):
                loopback += 1
            else:
                external.append({'event': e['event'], 'target': target, 'pid': e['pid'],
                                 'blocked': e.get('blocked', False)})
        elif e['event'] in ('webbrowser.open', 'os.startfile'):
            url = args[0] if args else ''
            # one webbrowser.open() raises nested audit events (open -> open_new_tab -> controller)
            if not (opens and opens[-1]['url'] == url and opens[-1]['pid'] == e['pid'] and e['t'] - opens[-1]['t'] < 1):
                opens.append({'url': url, 'pid': e['pid'], 't': e['t']})
        else:
            children.append({'event': e['event'], 'args': str(args)[:300], 'pid': e['pid']})
    return {'interception': AUDIT_NOTE, 'log_events': len(events), 'malformed_log_lines': malformed,
            'processes': len({e['pid'] for e in events}), 'local_ipc_events': ipc,
            'external_connections': external[:50], 'external_count': len(external),
            'external_unblocked': sum(not x['blocked'] for x in external), 'loopback_events': loopback,
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
    # The exact Owner launch gets the folder AS BUILT (copied before any launch writes data) and its own fresh
    # profile: what the Owner's first double-click sees, so its first page can be judged on content (Codex R2).
    pristine, home = Path(tempfile.mkdtemp(prefix='axb-owner-')), None
    try:
        shutil.copytree(base.cwd, pristine / 'app')
        owner = base.at(str(pristine / 'app'))
        if any(p.get('http_method') == 'RESTART' for p in spec.get('probes', [])):
            # The clean environment gives each process its own temp HOME/USERPROFILE; data a program keeps in the
            # user's profile would vanish on relaunch here but not on the Owner's PC: one profile for the flow.
            home = Path(tempfile.mkdtemp(prefix='axb-home-'))
            for sub in ('AppData/Roaming', 'AppData/Local'):
                (home / sub).mkdir(parents=True, exist_ok=True)
            base = Launch(base.argv, {**base.env, 'HOME': str(home), 'USERPROFILE': str(home),
                                      'APPDATA': str(home / 'AppData' / 'Roaming'),
                                      'LOCALAPPDATA': str(home / 'AppData' / 'Local')}, base.cwd, base.native)
        _launches(spec, mode, base, owner, ev, on_step)
    finally:
        shutil.rmtree(pristine, ignore_errors=True)
        if home is not None:
            shutil.rmtree(home, ignore_errors=True)


def _launches(spec, mode, base, owner, ev, on_step):
    """The verification launch (probes in order, RESTARTs included), then the exact Owner launch (`owner`)."""
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
        ev['steps'].append({'name': 'server start', 'args': args, 'ok': up, 'seconds': waited, 'pid': proc.proc.pid,
                            'problems': [] if up else [('process exited with code %s before listening' % proc.proc.poll())
                                                       if not proc.alive() else f'port {port} not listening after {START_TIMEOUT}s']})
        if up:
            probes = spec.get('probes', [])
            for probe in probes:
                if probe.get('http_method') == 'RESTART':
                    # Like the Owner closing the window and opening the program again: the whole tree is killed (no
                    # graceful shutdown), then the same program starts in the same folder and profile.
                    proc.stop()
                    proc.cleanup()
                    port = free_port()
                    args = [a.replace('{port}', str(port)) for a in spec.get('launch_args', [])]
                    proc = base.start(args)
                    up, waited = _wait_port(proc, port)
                    ev['port'] = port
                    ev['steps'].append({'name': probe['name'], 'request': 'RESTART', 'dispatch': 'restart', 'ok': up,
                                        'seconds': waited, 'port': port, 'pid': proc.proc.pid, 'problems': [] if up else [
                                            ('process exited with code %s before listening' % proc.proc.poll())
                                            if not proc.alive() else f'port {port} not listening after {START_TIMEOUT}s']})
                    if on_step:
                        on_step(f"runtime: {probe['name']}")
                    if not up:
                        break
                    continue
                if probe.get('http_method') == 'BROWSER':
                    ev['steps'].append({**_rendered(port, probe), 'dispatch': 'browser'})
                elif _is_http(probe):
                    ev['steps'].append({**_http(port, probe), 'dispatch': 'http'})
                else:                       # a command-line check of the same program (e.g. its self-test)
                    ev['steps'].append({**_cli(base, probe), 'dispatch': 'subprocess'})
                if on_step:
                    on_step(f"runtime: {probe['name']}")
            # Replaying a POST/PUT/DELETE would mutate the app's data a second time and judge a different state.
            first_http = next((pr for pr in probes if _is_http(pr) and (pr.get('http_method') or 'GET') == 'GET'), None)
            if first_http:   # still serving after the flow, and the first page still answers
                # Only "it answers without a server error": the flow may have changed the data the first probe saw.
                again = _http(port, {**first_http, 'name': f"{first_http['name']} (again after flow)",
                                     'expect_status': 0, 'expect_contains': [], 'expect_absent': []})
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
        ev['steps'].append(_exact_owner_launch(owner, spec))      # the folder as built, a fresh profile
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
        # The page that is loaded first and again: a GET (replaying a POST/PUT/DELETE would mutate twice).
        page = next((pr for pr in http_probes if (pr.get('http_method') or 'GET') == 'GET'), None) or {
            'name': 'page', 'http_method': 'GET', 'http_path': '/', 'expect_status': 0 if http_probes else 200,
            'expect_contains': []}
        # Fresh state (the folder as built): the first page is judged on content when it IS the first probe; a later
        # GET may depend on the flow's earlier mutations, so it must only answer without a server error.
        # "First" in the WHOLE ordered flow: a subprocess or BROWSER step before it may have prepared its state (R3).
        everything = spec.get('probes', [])
        lenient = {} if not http_probes or (everything and page is everything[0]) else {
            'expect_status': 0, 'expect_contains': [], 'expect_absent': []}
        first = _http(port, {**page, 'name': 'first page', **lenient})
        problems = list(first['problems'])
        # Same process: the whole HTTP flow (e.g. its self-test endpoint), then still serving.
        # The probes were written for the verification launch (launch_args, e.g. --offline): their content
        # expectations are judged there. Here the same process must still answer every request: a lost
        # connection or a server error fails the Owner launch; content differences are recorded only.
        flow = [{k: s.get(k) for k in ('name', 'request', 'status', 'ok', 'problems')}
                for s in (_http(port, pr) for pr in http_probes if pr is not page)]
        problems += [f"flow {s['name']}: {p}" for s in flow for p in s['problems']
                     if p.startswith(('connection lost', 'request failed')) or (s.get('status') or 0) >= 500]
        time.sleep(max(0.0, OBSERVE_SECONDS - (time.time() - t0)))
        again = _http(port, {**page, 'name': f'first page after {OBSERVE_SECONDS}s and the flow', 'expect_status': 0,
                             'expect_contains': [], 'expect_absent': []})      # the flow may have changed the data
        if not again['ok']:
            problems += [f'after the flow: {p}' for p in again['problems']]
        if not proc.alive():
            problems.append(f'server exited (code {proc.proc.poll()})')
        step['server_errors'] = [s.get('status') for s in (first, *flow, again) if (s.get('status') or 0) >= 500]
        step.update(status=first.get('status'), observed_seconds=round(time.time() - t0, 1),
                    alive_after_observation=proc.alive(), same_process_flow=flow,
                    same_process_flow_note='transport errors and 5xx are judged; content expectations target the '
                                           'verification launch arguments and are recorded only',
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


def _click_proxy(port, path, selectors, needles=(), budget=10000, order=()):
    """Forward the app through loopback, injecting clicks and a visible-text report only into the requested
    HTML page. The report (JSON in #axb-report) is what the page SHOWS: document.body.innerText after the
    clicks (closed <details> content and hidden elements are not in it), with click records, every
    <details> open state, page loads in this tab, and for each must-not-contain text the elements that hold
    it with their visibility. P-bbad3c v31: --dump-dom serialized collapsed content as if it were shown."""
    # Escape '<' so a selector can never terminate the injected script element.
    encoded = json.dumps(selectors).replace('<', r'\u003c')
    wanted = json.dumps([n for n in needles if n]).replace('<', r'\u003c')
    ordered = json.dumps([n for n in order if n]).replace('<', r'\u003c')
    # Installed right after <head> (before the page's own scripts): counts the page's fetch/XHR requests and
    # when they last changed, so a click is followed by "requests completed + CLICK_WAIT_MS quiet".
    early = b'''<script>(() => { if (window.__axb) return;
const s = window.__axb = {pending: 0, last: performance.now()};
const bump = d => { s.pending += d; s.last = performance.now(); };
const realFetch = window.fetch;
if (realFetch) window.fetch = function (...args) {
    bump(1); let p;
    try { p = realFetch.apply(this, args); } catch (e) { bump(-1); throw e; }
    return p.finally(() => bump(-1));
};
const realSend = XMLHttpRequest.prototype.send;
XMLHttpRequest.prototype.send = function (...args) {
    let done = false; const end = () => { if (!done) { done = true; bump(-1); } };
    bump(1); this.addEventListener('loadend', end, {once: true});
    try { return realSend.apply(this, args); } catch (e) { this.removeEventListener('loadend', end); end(); throw e; }
};
})();</script>'''
    script = ('''<script>document.addEventListener('DOMContentLoaded', async () => {
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const net = window.__axb || {pending: 0, last: 0};
const detailsState = () => [...document.querySelectorAll('details')].map(d => ({id: d.id || null, open: d.open}));
let loads = 0;
try { loads = Number(sessionStorage.getItem('axb-loads') || 0) + 1; sessionStorage.setItem('axb-loads', loads); } catch (e) {}
const report = {href: location.href, userAgent: navigator.userAgent, page_loads_in_tab: loads,
                navigation: (performance.getEntriesByType('navigation')[0] || {}).type || null, clicks: []};
const finish = () => {
    report.innerText = document.body.innerText;
    report.details = [...document.querySelectorAll('details')].map(d => ({id: d.id || null, open: d.open,
        summary: (d.querySelector('summary') || {}).textContent || ''}));
    const all = [...document.body.getElementsByTagName('*')];
    const holdersOf = text => all.filter(el => !['SCRIPT', 'STYLE'].includes(el.tagName) && el.textContent.includes(text)
        && ![...el.children].some(c => c.textContent.includes(text)));
    report.order = ORDER_NEEDLES.map(text => {
        const shown = holdersOf(text).filter(el => typeof el.checkVisibility !== 'function' || el.checkVisibility());
        const el = shown[0];
        return {text, visible_matches: shown.length, tag: el ? el.tagName.toLowerCase() : null, id: el ? el.id || null : null,
                dom_index: el ? all.indexOf(el) : null, top: el ? Math.round(el.getBoundingClientRect().top + scrollY) : null};
    });
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
for (const item of SELECTORS) {
    // Actions: "fill:SEL=>TEXT", "select:SEL=>VALUE", "wait:SEL", "expect:TEXT", "dialog:accept|dismiss"; else a click.
    const m = /^(fill|select|wait|expect|dialog):([\\s\\S]*)$/.exec(item);
    const op = m ? m[1] : 'click';
    let selector = m ? m[2] : item, value = null;
    if (op === 'fill' || op === 'select') {
        const cut = selector.indexOf('=>');
        if (cut < 0) { report.clicks.push({selector: item, op, problem: 'bad_action'}); return finish(); }
        value = selector.slice(cut + 2); selector = selector.slice(0, cut).trim();
    }
    if (op === 'dialog') {
        if (!['accept', 'dismiss'].includes(selector.trim())) { report.clicks.push({selector: item, op, problem: 'bad_action'}); return finish(); }
        const yes = selector.trim() === 'accept';
        window.confirm = () => yes; window.alert = () => {}; window.prompt = () => (yes ? '' : null);
        report.clicks.push({selector: item, op, dialog: selector.trim()});
        continue;
    }
    if (op === 'expect') {
        const shown = document.body.innerText.includes(selector);
        report.clicks.push(shown ? {selector: item, op, shown: true} : {selector: item, op, problem: 'expect_missing'});
        if (!shown) return finish();
        continue;
    }
    const deadline = performance.now() + 5000;
    let element;
    try {
        while (!(element = document.querySelector(selector)) && performance.now() < deadline)
            await sleep(50);
    } catch (e) { report.clicks.push({selector, op, problem: 'invalid'}); return finish(); }
    if (!element) { report.clicks.push({selector, op, problem: 'missing'}); return finish(); }
    if (op === 'wait') { report.clicks.push({selector, op, found: true}); continue; }
    const before = detailsState();
    const clickedAt = performance.now();
    if (op === 'click') element.click();
    else {
        const proto = [HTMLInputElement, HTMLTextAreaElement, HTMLSelectElement].find(c => element instanceof c);
        if (!proto || (op === 'select') !== (proto === HTMLSelectElement)) {
            report.clicks.push({selector, op, problem: 'not_fillable', tag: element.tagName.toLowerCase()}); return finish();
        }
        if (element.matches(':disabled') || element.readOnly) {   // incl. a disabled <fieldset>: the Owner could not type
            report.clicks.push({selector, op, problem: 'not_editable'}); return finish();
        }
        // The native setter + input/change events: what typing does, so frameworks that track input see it.
        element.focus();
        Object.getOwnPropertyDescriptor(proto.prototype, 'value').set.call(element, value);
        element.dispatchEvent(new Event('input', {bubbles: true}));
        element.dispatchEvent(new Event('change', {bubbles: true}));
        if (op === 'select' && element.value !== value) {
            report.clicks.push({selector, op, problem: 'no_such_option', value}); return finish();
        }
    }
    let timedOut = false;
    while (true) {
        const now = performance.now();
        if (net.pending === 0 && now - Math.max(net.last, clickedAt) >= CLICK_WAIT_MS) break;
        if (now - clickedAt > SETTLE_MS) { timedOut = true; break; }
        await sleep(50);
    }
    report.clicks.push({selector, op, clicked: op === 'click', filled: op !== 'click' ? value : undefined,
                        tag: element.tagName.toLowerCase(), id: element.id || null,
                        at_ms: Math.round(clickedAt), requests_settled: !timedOut, pending_at_end: net.pending,
                        settle_ms: Math.round(performance.now() - clickedAt), quiet_ms_required: CLICK_WAIT_MS,
                        details_before: before, details_after: detailsState()});
    if (timedOut) { report.clicks.push({selector, problem: 'settle_timeout'}); return finish(); }
}
// The visible text is taken at the end of the browser's time budget, not right after load: content
// that appears late (results) or is added late (forbidden text) must be what is judged.
await sleep(Math.max(300, BUDGET_MS - 1500 - performance.now()));
finish();
});</script>''')
    values = {'SELECTORS': encoded, 'NEEDLES': wanted, 'BUDGET_MS': str(int(budget)), 'ORDER_NEEDLES': ordered,
              'SETTLE_MS': str(SETTLE_MS), 'CLICK_WAIT_MS': str(CLICK_WAIT_MS)}
    script = re.sub('ORDER_NEEDLES|SELECTORS|NEEDLES|BUDGET_MS|SETTLE_MS|CLICK_WAIT_MS', lambda m: values[m.group()],
                    script).encode('ascii')
    requests, times = [], []

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
                times.append(time.monotonic())
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
                        head = re.search(br'<head\b[^>]*>', body, flags=re.I) or re.search(br'<html\b[^>]*>', body, flags=re.I)
                        body = body[:head.end()] + early + body[head.end():] if head else early + body
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
    proxy.requests, proxy.times = requests, times
    thread = threading.Thread(target=proxy.serve_forever, daemon=True)
    thread.start()
    return proxy, thread


def _dump_dom(exe, port, path, selectors, needles=(), record=None, order=()):
    """One headless-browser load through the click proxy: the DOM (stdout only), or None if the browser did
    not finish in time. record (dict) receives the proxied requests and the browser's stderr."""
    profile = tempfile.mkdtemp(prefix='axb-browser-')
    proxy, thread, proc = None, None, None
    record = {} if record is None else record
    try:
        budget = max(10000, len(selectors) * (5000 + SETTLE_MS + CLICK_WAIT_MS + 100) + 2000)
        proxy, thread = _click_proxy(port, path, selectors, needles, budget, order)
        started = time.monotonic()
        proc = sandbox.start([exe, '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
                              '--disable-logging', '--log-level=3',
                              f'--user-data-dir={profile}', f'--virtual-time-budget={budget}', '--dump-dom',
                              f'http://127.0.0.1:{proxy.server_port}{path}'], profile, env=dict(os.environ), caps=False,
                             split=True)
        # The page script runs to the end of its virtual-time budget; when the browser does not fast-forward (load),
        # that takes real time. A fixed limit killed correct long action flows (6 actions = 95 s budget > 90 s).
        record['timeout_s'] = max(BROWSER_TIMEOUT, budget // 1000 + 30)
        record['browser_exit_code'] = proc.wait(record['timeout_s'])
        finished = record['browser_exit_code'] is not None
        record['phases'] = phases(started, list(proxy.times), time.monotonic(), finished, len(selectors))
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


def phases(started, request_times, ended, finished, actions):
    """Where a headless-browser load spent its time (ms from launch): first page request (browser start +
    navigation), last app request (page scripts and actions), end (exit or the time limit), and where it stalled."""
    ms = lambda t: round((t - started) * 1000)
    first = ms(request_times[0]) if request_times else None
    last = ms(request_times[-1]) if request_times else None
    stalled = None
    if not finished:
        stalled = ('browser start / navigation: no page request reached the app' if first is None else
                   'page scripts / actions / virtual-time budget: requests seen, the browser never exited')
    return {'first_request_ms': first, 'last_request_ms': last, 'end_ms': ms(ended), 'requests': len(request_times),
            'actions': actions, 'outcome': 'exited' if finished else 'time limit', 'stalled_at': stalled}


def _rendered(port, probe):
    """BROWSER probe: load the page in a real headless browser (scripts run, the page's own API calls
    happen) and check the RENDERED text — script source is stripped so code text cannot fake a match."""
    path = probe.get('http_path') or '/'
    step = {'name': probe['name'], 'request': f'BROWSER {path}'}
    if not path.startswith('/'):        # '@host:port/' after the proxy address would leave the app (Codex E1)
        step.update(ok=False, probe_misconfigured=True, problems=['http_path must start with /'])
        return step
    exe = browser()
    if exe is None:
        step.update(ok=False, problems=['no headless browser available on this PC (Edge/Chrome)'])
        return step
    selectors = [s.strip() for s in (probe.get('http_body') or '').split('||') if s.strip()]
    step['browser'] = exe
    # Retry only before any app request: a timed-out page may already have changed application state.
    for attempt in (1, 2):
        record = {}
        dom = _dump_dom(exe, port, path, selectors, probe.get('expect_absent', []), record, probe.get('expect_contains', []))
        if dom is not None or record.get('browser_requests'):
            break
    # Retry another installed browser only before any app request: never repeat an executed user action.
    alternative = next((p for p in browser_candidates() if p != exe), None)
    if dom == '' and not record.get('browser_requests') and alternative:
        step['browser_fallback'] = {'from': exe, 'reason': 'empty output before any app request', **record}
        record = {}
        dom = _dump_dom(alternative, port, path, selectors, probe.get('expect_absent', []), record,
                        probe.get('expect_contains', []))
        step['browser'] = alternative
        attempt += 1
    step.update(attempts=attempt, **record)
    if dom is None:
        step.update(ok=False, problems=[f"browser did not finish within {record.get('timeout_s', BROWSER_TIMEOUT)}s ({attempt} attempts)"])
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
    if bad and bad['problem'] == 'settle_timeout':
        step.update(ok=False, harness_error=True, clicks=report['clicks'],
                    problems=[f"harness: the page's requests after clicking {bad['selector'][:120]!r} did not settle "
                              f'within {SETTLE_MS} ms; later clicks were not run (evidence incomplete)'])
        return step
    if bad:
        what = {'invalid': 'is not a CSS selector', 'missing': 'matched nothing on the page',
                'bad_action': "is not a valid action (fill:SEL=>TEXT, select:SEL=>VALUE, wait:SEL, expect:TEXT, "
                              "dialog:accept|dismiss)",
                'not_fillable': f"is a <{bad.get('tag')}>, not a field that action can fill",
                'no_such_option': f"has no option {bad.get('value')!r}",
                'expect_missing': 'was not shown on the page at that point of the flow',
                'not_editable': 'targets a disabled or read-only field the Owner cannot type into'}[bad['problem']]
        ids = sorted(set(re.findall(r'\bid="([^"]+)"', dom)) - {'axb-report'})[:60]
        step.update(ok=False, probe_misconfigured=bad['problem'] in ('invalid', 'bad_action'), clicks=report['clicks'],
                    problems=[f"browser action {bad['selector'][:120]!r} {what} "
                              "(http_body of a BROWSER probe = actions separated by '||'); "
                              f"element ids on the page: {', '.join('#' + i for i in ids) or 'none'}"])
        return step
    text = report['innerText']
    # The rendered order of the result areas: the visible element holding each expected text, by DOM position
    # (and its rendered top). A text held by several visible elements, or sharing one element with another
    # expected text, is ambiguous and reported as such instead of being taken as a section.
    order = [o for o in report.get('order', []) if o['dom_index'] is not None]
    shared = {o['dom_index'] for o in order if sum(x['dom_index'] == o['dom_index'] for x in order) > 1}
    step.update(visible_order=[o['text'] for o in sorted(order, key=lambda o: o['dom_index'])],
                visible_order_elements=[{k: o[k] for k in ('text', 'tag', 'id', 'dom_index', 'top', 'visible_matches')}
                                        for o in sorted(order, key=lambda o: o['dom_index'])][:30],
                visible_order_ambiguous=[o['text'] for o in order if o['visible_matches'] > 1 or o['dom_index'] in shared],
                visible_excerpts={n: re.sub(r'\s+', ' ', text[max(0, i - 40):i + 140])
                                  for i, n in sorted((text.find(n), n) for n in probe.get('expect_contains', [])
                                                     if n and n in text)[:20]},
                wait_rule=f'after each click: the page fetch/XHR requests completed and {CLICK_WAIT_MS} ms without '
                          f'request activity (max {SETTLE_MS} ms, else the step is incomplete)')
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
        explicit = parse_headers(probe.get('http_headers'))
    except ValueError as e:
        step.update(ok=False, probe_misconfigured=True, problems=[str(e)])
        return step
    if method not in HTTP_METHODS:
        step.update(ok=False, probe_misconfigured=True, problems=[f'unsupported http_method {method!r}'])
        return step
    if not (probe.get('http_path') or '/').startswith('/'):
        step.update(ok=False, probe_misconfigured=True, problems=['http_path must start with /'])
        return step
    for name, value in explicit:            # an explicit header replaces the inferred one of the same name
        headers = {k: v for k, v in headers.items() if k.lower() != name.lower()}
        headers[name] = value
    if explicit:
        step['headers'] = [f'{n}: {v[:200]}' for n, v in explicit]
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
        if canonical_probe(probe)['expect_status'] and resp.status != canonical_probe(probe)['expect_status']:
            problems.append(f"status {resp.status}, expected {probe['expect_status']}")
        elif not canonical_probe(probe)['expect_status'] and resp.status >= 500:
            problems.append(f'status {resp.status} (server error; "any status" never includes one)')
        missing = _contains(text, probe.get('expect_contains', []))
        if missing:
            problems.append(f'response lacks {missing}')
        problems += _present(text, probe)
    except http.client.InvalidURL as e:
        step['probe_misconfigured'] = True
        problems.append(f'invalid request target: {e}')
    except (ConnectionResetError, ConnectionAbortedError, http.client.RemoteDisconnected, BrokenPipeError) as e:
        problems.append(f'connection lost: {type(e).__name__}: {e}')
    except (OSError, http.client.HTTPException) as e:
        problems.append(f'request failed: {type(e).__name__}: {e}')
    step.update(ok=not problems, problems=problems)
    return step
