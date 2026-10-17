"""Bounded capability discovery and per-operation leases; no plugins or ambient grants.

A lease selects existing adapters/harnesses. It cannot install software, change
governance, or grant OS isolation. Provider flags and contained processes enforce
the authority; events alone are never claimed as enforcement.
"""
import re
from contextlib import contextmanager

from .state import Rejected


REGISTRY = {
    'reasoning': 'Structured LLM analysis; no execution evidence',
    'code_generation': 'Return code as JSON; no shell or direct file writes',
    'web_research': 'Public web search/read through the subscription adapter',
    'python_checks': 'Contained compile and self-test of generated Python',
    'runtime_cli': 'Contained CLI launch with input/output assertions',
    'runtime_web': 'Local HTTP flow with exact verbs, headers and assertions',
    'runtime_browser': 'Headless rendered-text and bounded browser actions',
    'runtime_restart': 'Kill/relaunch web app, then check persisted data',
    'runtime_gui_startup': 'Desktop process startup/survival only; no interaction',
}
AGENT = frozenset(('reasoning', 'code_generation', 'web_research'))
LIMITS = [
    'ML/LLM research and code generation are available; model training/GPU execution is not.',
    'No desktop GUI interaction, uploads, downloads, drag/drop or multi-tab harness.',
    'No clean-Windows/no-Python test machine or native installer verification adapter: an owner_launch that runs '
    'a native .exe/.msi is a capability gap (the deliverable is Python source the Owner runs with Python).',
    'Generated code runs under the current OS account; no OS file/network isolation.',
    'An installed external program is not an executable specialist capability.',
]


def inventory(browser_available=True):
    from . import runtime
    return {'available': {k: v for k, v in REGISTRY.items()
                          if k != 'runtime_browser' or browser_available},
            'limits': list(LIMITS),
            'execution_limits': {'cli_probe_seconds': runtime.CLI_TIMEOUT,
                                 'gui_startup_seconds': runtime.GUI_ALIVE,
                                 'owner_web_observation_seconds': runtime.OBSERVE_SECONDS,
                                 'direct_http_methods': list(runtime.HTTP_METHODS),
                                 'forbidden_http_headers': sorted(runtime._FRAMING)}}


def agent_requests(required=(), web=False, coding=False):
    if not isinstance(required, (list, tuple)) or any(not isinstance(k, str) for k in required):
        raise Rejected('CAPABILITY_GAP: capabilities must be a list of names')
    return sorted(set(['reasoning', *required] + (['web_research'] if web else [])
                      + (['code_generation'] if coding else [])))


# The Owner launches a native program the harness cannot build or run: its "exact Owner launch" would test
# `python <entry>` instead and pass a path the Owner never takes (P-20261016-5fb8d6: '.exe' declared, Owner saw
# 'service unreachable' three times while the Python launch passed).
# A whole file-name token (not part of a URL, a longer name like report.exe.config, or Python's own interpreter).
_NATIVE_LAUNCH = re.compile(r'(?<![\w.-])(?!(?:python|pythonw|py)\.exe(?![\w.-]))[\w-]+\.(?:exe|msi|msix|appx)(?![\w.-])', re.I)
_URL = re.compile(r'\w+://\S+')


def harness_requests(spec):
    mode = (spec or {}).get('mode', 'cli')
    names = [] if mode == 'none' else [{'cli': 'runtime_cli', 'web': 'runtime_web',
                                       'gui': 'runtime_gui_startup'}.get(mode, 'unsupported_runtime:' + str(mode))]
    if mode != 'none' and _NATIVE_LAUNCH.search(_URL.sub(' ', str((spec or {}).get('owner_launch', '')))):
        names.append('native_executable_launch')
    for probe in (spec or {}).get('probes', []):
        method = probe.get('http_method')
        if method == 'BROWSER':
            names.append('runtime_browser')
        elif method == 'RESTART':
            names.append('runtime_restart')
    return sorted(set(names))


def gaps(plan, browser_available=True):
    """Validate new and legacy plans before production spends a provider call."""
    missing = []
    for stage in plan['pipeline']:
        names = agent_requests(stage.get('capabilities', []), stage.get('web', False))
        missing.extend(k for k in names if k not in AGENT)
    available = inventory(browser_available)['available']
    missing.extend(k for k in harness_requests(plan.get('runtime')) if k not in available)
    return sorted(set(missing))


@contextmanager
def lease(store, pid, who, requested, *, kind='agent', web=False, browser_available=True):
    """Process-local authority, always revoked; crash residue is audit only, never a reusable grant."""
    allowed = AGENT if kind == 'agent' else set(inventory(browser_available)['available']) - AGENT
    missing = sorted(set(requested) - allowed)
    if kind == 'agent' and 'web_research' in requested and not web:
        missing.append('web_research: adapter web flag disabled')
    if missing:
        store.event(pid, 'capability_gap', who=who, requested=requested, missing=missing)
        raise Rejected('CAPABILITY_GAP: ' + ', '.join(missing))
    grant = store.event(pid, 'capability_attached', who=who, operation_kind=kind, capabilities=requested,
                        scope='one operation; never reusable',
                        authority={'web_research': bool(web), 'shell': False, 'file_write': False}
                        if kind == 'agent' else {'contained_execution': True, 'os_isolation': False})
    outcome = 'interrupted'
    try:
        yield grant
        outcome = 'completed'
    finally:
        store.event(pid, 'capability_revoked', grant=grant, outcome=outcome)


def recover(store, pid):
    """Called only while holding the project lock; never race a live operation."""
    ended = {e['detail']['grant'] for e in store.events(pid, {'capability_revoked'})}
    for event in store.events(pid, {'capability_attached'}):
        if event['id'] not in ended:
            store.event(pid, 'capability_revoked', grant=event['id'], outcome='worker interrupted; not reattached')
