"""Bounded capability discovery and per-operation leases; no plugins or ambient grants.

A lease selects existing adapters/harnesses. It cannot install software, change
governance, or grant OS isolation. Provider flags and contained processes enforce
the authority; events alone are never claimed as enforcement.
"""
import re
import shutil
import time
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
    'native_build_pyinstaller': 'One-file Windows .exe from the Python source; PyInstaller pinned, acquired into the project',
    'runtime_native_exe': 'Runtime checks and the exact Owner launch run the built .exe itself',
    'source_fetch': 'Read-only GET of the public pages a document cites (no credentials; private addresses refused)',
    'model_training': 'Real weight/LoRA training of small public models on CPU in a project-local pinned stack '
                      '(only after the resolver proved it works here; no GPU on this PC)',
}
# A capability a plan asks for that is not attached yet but may be obtainable: options are tried in order, every
# attempt and the final decision are recorded, and nothing that needs the Owner (sign-in, payment) is done.
TRAINING_NAMES = frozenset(('model_training', 'ml_training', 'lora_training', 'fine_tuning', 'gpu_training'))
AGENT = frozenset(('reasoning', 'code_generation', 'web_research'))
LIMITS = [
    'ML/LLM research and code generation are available. Model training: declare model_training; the engine tries '
    'free options (local CPU LoRA of small public models first) and records the decision. No GPU on this PC; a free '
    'cloud GPU needs the Owner to sign in.',
    'No desktop GUI interaction, uploads, downloads, drag/drop or multi-tab harness.',
    'A native .exe is available only through native_build pyinstaller (Python source -> one .exe); other '
    'packagers, installers (.msi) and languages are capability gaps. No clean-Windows machine: a built .exe is '
    'verified on this PC with a clean environment (no Python on PATH), and that limit is stated.',
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


def harness_requests(spec, native_build=None):
    """Harness capabilities a runtime spec needs. A native .exe Owner launch is supported only when native_build
    packages exactly that .exe."""
    mode = (spec or {}).get('mode', 'cli')
    names = [] if mode == 'none' else [{'cli': 'runtime_cli', 'web': 'runtime_web',
                                       'gui': 'runtime_gui_startup'}.get(mode, 'unsupported_runtime:' + str(mode))]
    if mode != 'none' and _NATIVE_LAUNCH.search(_URL.sub(' ', str((spec or {}).get('owner_launch', '')))):
        nb = native_build or {}
        names += (['native_build_pyinstaller', 'runtime_native_exe']
                  if nb.get('tool') == 'pyinstaller' and _launches_exe(spec, nb.get('exe_name', ''))
                  else ['native_executable_launch'])
    for probe in (spec or {}).get('probes', []):
        method = probe.get('http_method')
        if method == 'BROWSER':
            names.append('runtime_browser')
        elif method == 'RESTART':
            names.append('runtime_restart')
    return sorted(set(names))


def _launches_exe(spec, exe_name):
    """Every native target the owner_launch names is the .exe this plan builds."""
    names = {m.group(0).lower() for m in _NATIVE_LAUNCH.finditer(_URL.sub(' ', str((spec or {}).get('owner_launch', ''))))}
    return bool(exe_name) and names == {f'{exe_name}.exe'.lower()}


def probe_browser(project_dir):
    """Free option for runtime_browser: an installed Chrome/Edge (found on disk, never installed by AX Branch)."""
    from . import runtime
    path = runtime.browser()
    if path:
        return {'ok': True, 'evidence': {'browser': path}}
    return {'ok': False, 'why': 'no installed Chrome or Edge was found on this PC',
            'minimal_approval': 'Owner installs Google Chrome or Microsoft Edge (free); AX Branch never installs software itself',
            'cost': '0'}


def options(capability, training=None):
    """(name, attempt) pairs in the order they are tried for a resolvable capability; () if none is known."""
    if capability == 'runtime_browser':
        return (('installed_browser', probe_browser),)
    if capability not in TRAINING_NAMES:
        return ()
    if training is None:
        from . import training
    return (('local_cpu_lora', training.probe_cpu), ('free_cloud_gpu', training.probe_cloud_gpu))


# Installed programs a capability name may refer to. Finding one is recorded, but an installed program is not an
# execution adapter here (LIMITS): it is never leased to an agent, so it never resolves the capability by itself.
TOOL_HINTS = {'ocr': ('tesseract',), 'pdf': ('pdftotext', 'qpdf'), 'video': ('ffmpeg',), 'audio': ('ffmpeg',),
              'image': ('magick',), 'office': ('soffice',), 'docker': ('docker',), 'node': ('node',),
              'java': ('java',), 'dotnet': ('dotnet',), 'rust': ('cargo',), 'go': ('go',)}


def static_checks(capability):
    """Attempts that need no run: installed-tool lookup and the known free alternative or reason. Each is a record of
    what was checked, never a claim that the capability was obtained."""
    out = []
    low = capability.lower()
    found = sorted({f'{t} ({shutil.which(t)})' for k, tools in TOOL_HINTS.items() if k in low
                    for t in tools if shutil.which(t)})
    hinted = [t for k, tools in TOOL_HINTS.items() if k in low for t in tools]
    if hinted:
        out.append({'option': 'installed_tool', 'ok': False, 'seconds': 0,
                    'why': (f"installed: {', '.join(found)}; but an installed program is not an execution adapter in "
                            'AX Branch, so no agent or check can use it' if found else
                            f"no installed program found ({', '.join(sorted(set(hinted)))})")})
    if capability == 'native_executable_launch':
        out.append({'option': 'pyinstaller_native_build', 'ok': False, 'seconds': 0, 'replan': True,
                    'why': 'free supported alternative: the CEO re-plans with native_build pyinstaller (Python source -> '
                           'one .exe that verification builds and launches); other packagers/installers are unsupported'})
    elif capability.startswith('unsupported_runtime:'):
        out.append({'option': 'supported_runtime_modes', 'ok': False, 'seconds': 0, 'replan': True,
                    'why': 'supported program modes are cli, web, gui (startup only) and none; the CEO re-plans with one'})
    return out


def resolve(store, pid, capability, project_dir, tried_options=None):
    """Identify -> check installed tools -> try the allowed free options (real small runs, not declarations) -> record
    every attempt and ONE decision: resolved / needs_owner (minimal approval) / needs_replan (a supported free
    alternative) / unsupported. Only a successful real attempt resolves a capability."""
    tried = []
    for rec in static_checks(capability):
        store.event(pid, 'capability_attempt', capability=capability, **rec)
        tried.append(rec)
    for name, attempt in tried_options if tried_options is not None else options(capability):
        started = time.monotonic()
        try:
            r = attempt(project_dir)
        except Exception as e:                     # an option that crashes is a failed option, never a crash
            r = {'ok': False, 'why': f'{type(e).__name__}: {e}'[:600]}
        rec = {'option': name, 'ok': bool(r.get('ok')), 'seconds': round(time.monotonic() - started),
               **{k: r[k] for k in ('why', 'evidence', 'environment', 'cost', 'minimal_approval') if k in r}}
        store.event(pid, 'capability_attempt', capability=capability, **rec)
        tried.append(rec)
        if rec['ok']:
            decision = {'capability': capability, 'status': 'resolved', 'chosen': name, 'tried': tried}
            break
    else:
        approvals = [t['minimal_approval'] for t in tried if t.get('minimal_approval')]
        replan = [t['why'] for t in tried if t.get('replan')]
        if not approvals and replan:
            decision = {'capability': capability, 'status': 'needs_replan', 'tried': tried, 'alternative': replan,
                        'cost': ['0'], 'minimal_approval': [],
                        'next_action': 'the CEO re-plans with the supported alternative ([수정 요청 / 계속]); nothing was obtained'}
            store.event(pid, 'capability_decision', **decision)
            return decision
        if not approvals and not any(t['option'] != 'installed_tool' for t in tried):
            decision = {'capability': capability, 'status': 'unsupported', 'tried': tried, 'cost': [],
                        'minimal_approval': ['no free option exists here: change the requirement, or approve developing '
                                             'a new AX Branch capability (development work, not a runtime grant)'],
                        'next_action': 'Owner changes the requirement; the quality bar is not lowered silently'}
            store.event(pid, 'capability_decision', **decision)
            return decision
        decision = {'capability': capability, 'status': 'needs_owner', 'tried': tried,
                    'cost': [t.get('cost', 'UNKNOWN') for t in tried],
                    'minimal_approval': approvals or ['UNKNOWN: no option works here; the Owner decides whether to '
                                                      'change the requirement'],
                    'next_action': 'Owner approves one listed action or changes the requirement; the quality bar is '
                                   'not lowered silently'}
    store.event(pid, 'capability_decision', **decision)
    return decision


def gaps(plan, browser_available=True):
    """Validate new and legacy plans before production spends a provider call."""
    missing = []
    for stage in plan['pipeline']:
        names = agent_requests(stage.get('capabilities', []), stage.get('web', False))
        missing.extend(k for k in names if k not in AGENT and k not in plan.get('harness_capabilities', ()))
    available = inventory(browser_available)['available']
    missing.extend(k for k in harness_requests(plan.get('runtime'), plan.get('native_build')) if k not in available)
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
