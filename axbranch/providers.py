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

TIMEOUT = 1800   # a full-file build+review turn measured >15 min live (2026-10-03)
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)   # the windowed exe must not flash consoles
LABEL = {'claude': 'Claude Code', 'codex': 'Codex'}


def available():
    return [name for name in PROVIDERS if shutil.which(name)]


def _contained(name, args, prompt, cwd, cancel, on_tick):
    """Run one CLI turn with whole-tree kill and live activity. Returns (exit code, stdout+stderr)."""
    proc = sandbox.start(args, cwd, prompt, env=_subscription_env(), caps=False)
    started = last_change = time.monotonic()
    size = 0
    try:
        while True:
            code = proc.wait(1)
            now = time.monotonic()
            grown = proc.log.stat().st_size
            if grown != size:
                size, last_change = grown, now
            if on_tick is not None:
                try:
                    on_tick({'provider': name, 'pid': proc.proc.pid, 'elapsed': round(now - started),
                             'output_bytes': size, 'idle': round(now - last_change)})
                except Exception:
                    pass      # visibility must never break the call
            if code is not None:
                return code, proc.output()
            if cancel is not None and cancel.is_set():
                raise Rejected(f'{LABEL[name]}: 오너가 중단했습니다. 프로세스 트리 전체를 종료했습니다.')
            if now - started > TIMEOUT:
                raise Rejected(f'{LABEL[name]}: 시간 초과({TIMEOUT}초). 프로세스 트리 전체를 종료했습니다. '
                               '자동 재시도하지 않습니다.')
    finally:
        proc.stop()          # whole tree, every exit path
        proc.cleanup()


def run_claude(prompt, schema, web=False, cancel=None, on_tick=None):
    binary = shutil.which('claude')
    tools = 'WebSearch,WebFetch' if web else ''
    blocked = 'Bash,Write,Edit,NotebookEdit,Task' + ('' if web else ',WebFetch,WebSearch')
    args = [binary, '-p', '--output-format', 'json', '--restricted', '--disallowedTools', blocked,
            '--permission-mode', 'dontAsk', '--tools', tools, *(['--allowedTools', tools] if tools else []),
            '--json-schema', canonical(schema), '--setting-sources', '', '--strict-mcp-config',
            '--mcp-config', '{"mcpServers":{}}', '--no-session-persistence']
    scratch = Path(tempfile.mkdtemp(prefix='axb-claude-'))
    try:
        code, raw = _contained('claude', args, prompt, str(scratch), cancel, on_tick)
        raw = raw.strip()
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
    raise RateLimited('No provider available: ' + ' / '.join(notes))
