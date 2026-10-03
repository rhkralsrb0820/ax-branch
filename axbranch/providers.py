"""Execution providers. An Agent is role + goal + context + permissions + tools; a
provider is only the engine that runs one turn, so either CLI can serve any agent.

The subprocess, quota-detection and paid-API guards are cheongwol's
(ceo/cheongwol/connectors.py), imported rather than re-derived: they encode CLI
failure wordings observed live. Only subscription logins are used; a paid API
key in the environment stops the call (governance).
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_CHEONGWOL = Path(__file__).resolve().parents[2] / 'cheongwol' / 'ceo'
if _CHEONGWOL.is_dir() and str(_CHEONGWOL) not in sys.path:
    sys.path.insert(0, str(_CHEONGWOL))
from cheongwol.connectors import (RateLimited, _check_rate_limit, _claude_failure_text,  # noqa: E402
                                  _codex_failure_text, _subscription_env, _wait_with_cancel)
from cheongwol.policy import Rejected, canonical  # noqa: E402

from .governance import PROVIDERS  # noqa: E402

TIMEOUT = 1800   # a full-file build+review turn measured >15 min live (2026-10-03)
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)   # the windowed exe must not flash consoles


def available():
    return [name for name in PROVIDERS if shutil.which(name)]


def _scratch(prefix, prompt):
    scratch = Path(tempfile.mkdtemp(prefix=prefix))
    (scratch / 'prompt.txt').write_text(prompt, encoding='utf-8')
    return scratch


def run_claude(prompt, schema, web=False, cancel=None):
    binary = shutil.which('claude')
    tools = 'WebSearch,WebFetch' if web else ''
    blocked = 'Bash,Write,Edit,NotebookEdit,Task' + ('' if web else ',WebFetch,WebSearch')
    args = [binary, '-p', '--output-format', 'json', '--restricted', '--disallowedTools', blocked,
            '--permission-mode', 'dontAsk', '--tools', tools, *(['--allowedTools', tools] if tools else []),
            '--json-schema', canonical(schema), '--setting-sources', '', '--strict-mcp-config',
            '--mcp-config', '{"mcpServers":{}}', '--no-session-persistence']
    scratch = _scratch('axb-claude-', prompt)
    try:
        out = scratch / 'out.json'
        with (scratch / 'prompt.txt').open('rb') as stdin, out.open('w', encoding='utf-8') as stdout:
            popen = subprocess.Popen(args, stdin=stdin, stdout=stdout, stderr=subprocess.STDOUT,
                                     cwd=scratch, env=_subscription_env(), creationflags=NO_WINDOW)
            _wait_with_cancel(popen, TIMEOUT, cancel, 'Claude Code')
        raw = out.read_text(encoding='utf-8', errors='replace').strip()
        if popen.returncode != 0:
            _check_rate_limit(_claude_failure_text(raw))
            raise Rejected(f'Claude Code exited {popen.returncode}: {raw[-300:]}')
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


def run_codex(prompt, schema, web=False, cancel=None):
    binary = shutil.which('codex')
    scratch = _scratch('axb-codex-', prompt)
    try:
        (scratch / 'schema.json').write_text(canonical(schema), encoding='utf-8')
        out, log = scratch / 'final.txt', scratch / 'events.jsonl'
        args = [binary, 'exec', '--json', '--sandbox', 'read-only', '--skip-git-repo-check',
                '--ignore-user-config', '--ephemeral', '--output-schema', str(scratch / 'schema.json'),
                '-c', 'forced_login_method="chatgpt"', '-c', f'web_search="{"live" if web else "disabled"}"',
                '-c', 'features.shell_tool=false', '-c', 'features.unified_exec=false', '-o', str(out)]
        with (scratch / 'prompt.txt').open('rb') as stdin, log.open('w', encoding='utf-8') as stdout:
            popen = subprocess.Popen(args, stdin=stdin, stdout=stdout, stderr=subprocess.STDOUT,
                                     cwd=scratch, env=_subscription_env(), creationflags=NO_WINDOW)
            _wait_with_cancel(popen, TIMEOUT, cancel, 'Codex')
        events = log.read_text(encoding='utf-8', errors='replace')
        if popen.returncode != 0 or not out.exists():
            _check_rate_limit(_codex_failure_text(events))
            raise Rejected(f'Codex exited {popen.returncode}: {_codex_failure_text(events)[-300:]}')
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


def call(prompt, schema, prefer='claude', web=False, cancel=None):
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
            return RUN[name](prompt, schema, web, cancel), name, notes
        except RateLimited as e:
            notes.append(f'{name}: {e}')
    raise RateLimited('No provider available: ' + ' / '.join(notes))
