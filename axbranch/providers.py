"""Execution providers. An Agent is role + goal + context + permissions + tools; a
provider is only the engine that runs one turn, so either CLI can serve any agent.

Quota-detection and paid-API guards are cheongwol's (ceo/cheongwol/connectors.py), imported
rather than re-derived: they encode CLI failure wordings observed live. Only subscription
logins are used; a paid API key in the environment stops the call (governance).

Each CLI runs inside a Job Object (sandbox.start, no caps): on timeout or Owner stop the
WHOLE tree dies. Terminating only the process we started was not enough on Windows — that
is npm's cmd.exe wrapper, and the real node/codex.exe/claude kept running (proven 2026-10-04).
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

_CHEONGWOL = Path(__file__).resolve().parents[2] / 'cheongwol' / 'ceo'
if _CHEONGWOL.is_dir() and str(_CHEONGWOL) not in sys.path:
    sys.path.append(str(_CHEONGWOL))     # append: never shadow our own modules (e.g. tests) with cheongwol's
from cheongwol.connectors import (RateLimited, _check_rate_limit, _claude_failure_text,  # noqa: E402
                                  _codex_failure_text, _subscription_env)
from cheongwol.policy import Rejected, canonical  # noqa: E402

from . import sandbox  # noqa: E402
from .governance import PROVIDERS  # noqa: E402
from .state import Busy, run_lock  # noqa: E402

TIMEOUT = 1800   # a full-file build+review turn measured >15 min live (2026-10-03)
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)   # the windowed exe must not flash consoles
LABEL = {'claude': 'Claude Code', 'codex': 'Codex'}
# Resource-aware autonomy: provider CLIs are heavy (node + CLI, often hundreds of MB). Machine-wide —
# every AX Branch process on this PC (window, CLI, Codex session) shares these slots.
MAX_PARALLEL_CLI = 2
SLOT_DIR = Path(tempfile.gettempdir()) / 'axbranch-provider-slots'
MIN_FREE_MB, MEMORY_WAIT = 1024, 300
SLEEP_GAP = 30          # a poll gap longer than this means the PC slept / the process was suspended


def free_memory_mb():
    """Available physical memory in MB (None if unknown on this OS)."""
    if os.name != 'nt':
        try:
            return os.sysconf('SC_AVPHYS_PAGES') * os.sysconf('SC_PAGE_SIZE') // 2**20
        except (ValueError, OSError, AttributeError):
            return None
    import ctypes

    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [('dwLength', ctypes.c_ulong), ('dwMemoryLoad', ctypes.c_ulong),
                    ('ullTotalPhys', ctypes.c_ulonglong), ('ullAvailPhys', ctypes.c_ulonglong),
                    ('ullTotalPageFile', ctypes.c_ulonglong), ('ullAvailPageFile', ctypes.c_ulonglong),
                    ('ullTotalVirtual', ctypes.c_ulonglong), ('ullAvailVirtual', ctypes.c_ulonglong),
                    ('ullAvailExtendedVirtual', ctypes.c_ulonglong)]
    status = MEMORYSTATUSEX()
    status.dwLength = ctypes.sizeof(status)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
    return status.ullAvailPhys // 2**20


def _acquire_slot(name, cancel, on_tick):
    """Hold one of MAX_PARALLEL_CLI machine-wide slots (OS file locks: a crashed holder frees its slot)."""
    started = time.monotonic()
    while True:
        for i in range(MAX_PARALLEL_CLI):
            lock = run_lock(SLOT_DIR / f'slot-{i}.lock')
            try:
                lock.__enter__()
                return lock
            except Busy:
                continue
        if cancel is not None and cancel.is_set():
            raise Rejected(f'{LABEL[name]}: 오너가 중단했습니다.')
        _tick(on_tick, {'provider': name, 'waiting': f'all {MAX_PARALLEL_CLI} provider slots busy',
                        'elapsed': round(time.monotonic() - started), 'output_bytes': 0, 'idle': 0})
        time.sleep(2)


def _ensure_memory(name, cancel, on_tick):
    started = time.monotonic()
    while True:
        free = free_memory_mb()
        if free is None or free >= MIN_FREE_MB:
            return free
        if time.monotonic() - started > MEMORY_WAIT:
            raise Rejected(f'{LABEL[name]}: 사용 가능한 메모리가 {free} MB로 부족해 실행하지 않았습니다 '
                           f'(최소 {MIN_FREE_MB} MB). PC를 보호하기 위해 일시 정지합니다.')
        if cancel is not None and cancel.is_set():
            raise Rejected(f'{LABEL[name]}: 오너가 중단했습니다.')
        _tick(on_tick, {'provider': name, 'waiting': f'low memory: {free} MB free (< {MIN_FREE_MB} MB)',
                        'elapsed': round(time.monotonic() - started), 'output_bytes': 0, 'idle': 0})
        time.sleep(5)


def _tick(on_tick, info):
    if on_tick is not None:
        try:
            on_tick(info)
        except Exception:
            pass      # visibility must never break the call


def available():
    return [name for name in PROVIDERS if shutil.which(name)]


def _contained(name, args, prompt, cwd, cancel, on_tick):
    """Run one CLI turn with whole-tree kill and live activity. Returns (exit code, stdout+stderr).
    Waits for a free machine-wide slot and enough memory first; time the PC spends asleep is not
    counted against the timeout (2026-10-04: 13.7 h of sleep turned into a false timeout)."""
    slot = _acquire_slot(name, cancel, on_tick)
    try:
        free = _ensure_memory(name, cancel, on_tick)
        if cancel is not None and cancel.is_set():
            raise Rejected(f'{LABEL[name]}: 오너가 중단했습니다.')
        proc = sandbox.start(args, cwd, prompt, env=_subscription_env(), caps=False)
        started = last_change = prev = time.monotonic()
        size, slept = 0, 0.0
        try:
            while True:
                code = proc.wait(1)
                now = time.monotonic()
                if now - prev > SLEEP_GAP:
                    slept += now - prev - 1
                    last_change += now - prev - 1       # asleep is not 'no output' either
                prev = now
                grown = proc.log.stat().st_size
                if grown != size:
                    size, last_change = grown, now
                _tick(on_tick, {'provider': name, 'pid': proc.proc.pid, 'elapsed': round(now - started - slept),
                                'output_bytes': size, 'idle': round(now - last_change), 'slept': round(slept),
                                'free_memory_mb': free})
                if code is not None:
                    return code, proc.output()
                if cancel is not None and cancel.is_set():
                    raise Rejected(f'{LABEL[name]}: 오너가 중단했습니다. 프로세스 트리 전체를 종료했습니다.')
                if now - started - slept > TIMEOUT:
                    raise Rejected(f'{LABEL[name]}: 시간 초과({TIMEOUT}초). 프로세스 트리 전체를 종료했습니다. '
                                   '자동 재시도하지 않습니다.')
        finally:
            proc.stop()          # whole tree, every exit path
            proc.cleanup()
    finally:
        slot.__exit__(None, None, None)


def _claude_result(stream):
    """The final 'result' event of a stream-json run, as JSON text; the raw tail if there is none
    (CLI noise / errors), so failure classification still sees what happened."""
    for line in reversed(stream.strip().splitlines()):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get('type') == 'result':
            return line
    return stream.strip()[-4000:]


def run_claude(prompt, schema, web=False, cancel=None, on_tick=None):
    binary = shutil.which('claude')
    tools = 'WebSearch,WebFetch' if web else ''
    blocked = 'Bash,Write,Edit,NotebookEdit,Task' + ('' if web else ',WebFetch,WebSearch')
    # stream-json + partial messages: output grows while Claude generates, so the Owner's activity view
    # shows real progress (plain json printed nothing until the very end). The final 'result' event is
    # the same envelope the plain json mode returned.
    args = [binary, '-p', '--output-format', 'stream-json', '--verbose', '--include-partial-messages',
            '--restricted', '--disallowedTools', blocked,
            '--permission-mode', 'dontAsk', '--tools', tools, *(['--allowedTools', tools] if tools else []),
            '--json-schema', canonical(schema), '--setting-sources', '', '--strict-mcp-config',
            '--mcp-config', '{"mcpServers":{}}', '--no-session-persistence']
    scratch = Path(tempfile.mkdtemp(prefix='axb-claude-'))
    try:
        code, stream = _contained('claude', args, prompt, str(scratch), cancel, on_tick)
        raw = _claude_result(stream)
        if code != 0:
            _check_rate_limit(_claude_failure_text(raw))
            raise Rejected(f'Claude Code exited {code}: {raw[-300:]}')
        try:
            envelope = json.loads(raw)
        except json.JSONDecodeError:
            raise Rejected('Claude Code output is not JSON.') from None
        if envelope.get('is_error'):
            _check_rate_limit(str(envelope.get('result')))
            raise Rejected('Claude Code error: ' + str(envelope.get('result'))[:300])
        result = envelope.get('structured_output')
        if not isinstance(result, dict):
            try:
                result = json.loads(envelope.get('result') or '')
            except json.JSONDecodeError:
                raise Rejected('Claude Code reply is not one JSON object.') from None
        return result
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def run_codex(prompt, schema, web=False, cancel=None, on_tick=None):
    binary = shutil.which('codex')
    scratch = Path(tempfile.mkdtemp(prefix='axb-codex-'))
    try:
        (scratch / 'schema.json').write_text(canonical(schema), encoding='utf-8')
        out = scratch / 'final.txt'
        args = [binary, 'exec', '--json', '--sandbox', 'read-only', '--skip-git-repo-check',
                '--ignore-user-config', '--ephemeral', '--output-schema', str(scratch / 'schema.json'),
                '-c', 'forced_login_method="chatgpt"', '-c', f'web_search="{"live" if web else "disabled"}"',
                '-c', 'features.shell_tool=false', '-c', 'features.unified_exec=false', '-o', str(out)]
        code, events = _contained('codex', args, prompt, str(scratch), cancel, on_tick)
        if code != 0 or not out.exists():
            _check_rate_limit(_codex_failure_text(events))
            raise Rejected(f'Codex exited {code}: {_codex_failure_text(events)[-300:]}')
        try:
            result = json.loads(out.read_text(encoding='utf-8').strip())
        except json.JSONDecodeError:
            raise Rejected('Codex reply is not one JSON object.') from None
        if not isinstance(result, dict):
            raise Rejected('Codex reply must be a JSON object.')
        return result
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


RUN = {'claude': run_claude, 'codex': run_codex}


def authority(name, web):
    """The authority one turn on `name` actually has, as its adapter flags above enforce it (tests tie this to the
    flags). Any other provider name has no known enforcement: None (fail closed, recorded as unknown)."""
    if name not in RUN:
        return None
    return {'web_research': bool(web), 'shell': False, 'file_write': False, 'mcp_servers': False,
            'session_persistence': False, 'workdir': 'empty temp dir, deleted after the turn',
            'enforced_by': {'claude': '--restricted, --tools/--disallowedTools, empty MCP config, no session persistence',
                            'codex': '--sandbox read-only, shell_tool/unified_exec off, --ephemeral, web_search flag'}[name]}


def call(prompt, schema, prefer='claude', web=False, cancel=None, on_tick=None):
    """One agent turn. Tries `prefer` first, then the other provider ONLY on an
    observed quota refusal (or a missing CLI). Returns (result, provider_used, notes).
    Preferred is retried every call, so work moves back automatically once its quota
    returns — no reset time is ever guessed."""
    order = [prefer] + [p for p in PROVIDERS if p != prefer]
    notes = []
    for name in order:
        if not shutil.which(name):
            notes.append(f'{name}: CLI not installed')
            continue
        try:
            return RUN[name](prompt, schema, web, cancel, on_tick), name, notes
        except RateLimited as e:
            notes.append(f'{name}: {e}')
        except Rejected as e:
            e.notes = notes
            if notes:
                e.args = (str(e) + ' / ' + ' / '.join(notes), *e.args[1:])
            raise
    error = RateLimited('No provider available: ' + ' / '.join(notes))
    error.notes = notes
    raise error
