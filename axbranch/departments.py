"""Department packages: shared, versioned function packages (departments/<id>/department.json) that a project
attaches. Attachment is per project and recorded as events (persisted, auditable, never mixed between projects).
淸月 CEO delegates pipeline stages only to attached departments; a stage without one is a visibly recorded
temporary agent. Attaching connects functions; it never approves payments, credentials, publishing or contact."""
import json
import sys
from pathlib import Path

from . import capabilities
from .state import Rejected

# Source checkout: <repo>/departments; packaged exe: bundled next to the code (PyInstaller --add-data).
ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1])) / 'departments'
FIELDS = {'id': str, 'version': str, 'name': str, 'role': str, 'provides': list, 'agent': dict, 'tools': list,
          'inputs': list, 'outputs': list, 'knowledge': list, 'permissions': dict, 'acceptance_criteria': list}


def validate(spec, folder=None):
    """Problems with one department spec ([] = valid). Unknown tools, a shell grant or network use without the
    network permission are refused at load time, never discovered mid-project."""
    if not isinstance(spec, dict):
        return ['not a JSON object']
    problems = [f'missing or wrong type: {k}' for k, t in FIELDS.items() if not isinstance(spec.get(k), t)]
    if problems:
        return problems
    if folder is not None and spec['id'] != folder:
        problems.append(f"id {spec['id']!r} does not match its folder {folder!r}")
    if not spec['provides'] or not all(isinstance(x, str) and x.strip() for x in spec['provides']):
        problems.append('provides must list at least one function')
    if not str(spec['agent'].get('role', '')).strip() or not str(spec['agent'].get('instructions', '')).strip():
        problems.append('agent needs a role and instructions')
    unknown = [t for t in spec['tools'] if t not in capabilities.AGENT]
    if unknown:
        problems.append(f'unknown tools {unknown} (available: {sorted(capabilities.AGENT)})')
    perm = spec['permissions']
    if perm.get('shell') is not False:
        problems.append('permissions.shell must be false (agents never get a shell)')
    if not isinstance(perm.get('network'), bool):
        problems.append('permissions.network must be true or false')
    if 'web_research' in spec['tools'] and not perm.get('network'):
        problems.append('web_research needs permissions.network = true')
    for key in ('read', 'write'):
        if not isinstance(perm.get(key), list):
            problems.append(f'permissions.{key} must be a list of paths')
    if not spec['acceptance_criteria']:
        problems.append('acceptance_criteria must not be empty')
    problems += _contract_problems(spec.get('contract'))
    return problems


WORK_FIELDS = ('output', 'key_points', 'evidence', 'counterpoints')
INPUT_KINDS = ('owner_inputs', 'previous_stages')
MAX_CONTRACT_FAILURES = 2          # per stage and plan version: the first failure gets one rework, then the Owner
FOREIGN_PROJECT = __import__('re').compile(r'P-\d{8}-[0-9a-f]{6}')


def _contract_problems(c):
    """An optional machine-checked contract (absent = a legacy spec: only the universal checks apply)."""
    if c is None:
        return []
    if not isinstance(c, dict) or not isinstance(c.get('version'), int):
        return ['contract must be an object with an integer version']
    out, inp = c.get('output', {}), c.get('input', {})
    problems = []
    if not isinstance(out, dict) or not isinstance(inp, dict):
        return ['contract.output and contract.input must be objects']
    if not set(out.get('require', [])) <= set(WORK_FIELDS):
        problems.append(f'contract.output.require must be among {WORK_FIELDS}')
    for key in ('min_evidence', 'min_output_chars'):
        if not isinstance(out.get(key, 0), int) or out.get(key, 0) < 0:
            problems.append(f'contract.output.{key} must be a non-negative integer')
    if not set(inp.get('require', [])) <= set(INPUT_KINDS):
        problems.append(f'contract.input.require must be among {INPUT_KINDS}')
    return problems


def check_input(spec, has_owner_inputs, has_previous):
    """Required inputs of a department stage that are missing (checked before any model call)."""
    need = ((spec or {}).get('contract') or {}).get('input', {}).get('require', [])
    have = {'owner_inputs': has_owner_inputs, 'previous_stages': has_previous}
    return [f'필수 입력 없음: {k}' for k in need if not have[k]]


def check_output(spec, out, pid, known_ids=()):
    """FORMAT problems of a stage result before it may be handed to the next stage ([] = format passed).
    Passing says nothing about whether the content is right: that stays with independent verification."""
    problems = []
    text = str(out.get('output') or '').strip()
    if not text:
        problems.append('결과(output)가 비어 있음')
    c = (spec or {}).get('contract') or {}
    rules = c.get('output', {})
    for field in rules.get('require', []):
        if not out.get(field):
            problems.append(f'필수 항목 없음: {field}')
    if len(text) < rules.get('min_output_chars', 0):
        problems.append(f"결과가 너무 짧음 ({len(text)}자 < {rules['min_output_chars']}자)")
    if len(out.get('evidence') or []) < rules.get('min_evidence', 0):
        problems.append(f"근거 부족 ({len(out.get('evidence') or [])}개 < {rules['min_evidence']}개)")
    blob = json.dumps(out, ensure_ascii=False)
    foreign = sorted(set(FOREIGN_PROJECT.findall(blob)) - {pid} - set(known_ids))   # ids in this project's own data are fine
    if foreign:
        problems.append(f'다른 프로젝트 참조: {foreign}')
    return problems


def catalog(root=None):
    """({id: spec} valid departments, {folder: problems} refused ones)."""
    root = Path(root) if root else ROOT
    valid, refused = {}, {}
    for f in sorted(root.glob('*/department.json')) if root.is_dir() else []:
        try:
            spec = json.loads(f.read_text(encoding='utf-8'))
        except (OSError, ValueError) as e:
            refused[f.parent.name] = [f'unreadable: {e}']
            continue
        problems = validate(spec, f.parent.name)
        if problems:
            refused[f.parent.name] = problems
        else:
            valid[spec['id']] = spec
    return valid, refused


def attached(store, pid):
    """[{id, version}] attached to this project now, in attach order (replayed from its own events)."""
    current = {}
    for e in store.events(pid, {'department_attached', 'department_detached'}):
        if e['kind'] == 'department_attached':
            current[e['detail']['department']] = e['detail']['version']
        else:
            current.pop(e['detail']['department'], None)
    return [{'id': k, 'version': v} for k, v in current.items()]


def attach(store, pid, dep_id, specs):
    if dep_id not in specs:
        raise Rejected(f'부서 {dep_id!r}는 라이브러리에 없거나 명세 검증에 실패했습니다.')
    if any(d['id'] == dep_id for d in attached(store, pid)):
        raise Rejected(f"이미 연결된 부서입니다: {specs[dep_id]['name']}")
    store.event(pid, 'department_attached', department=dep_id, version=specs[dep_id]['version'],
                note='function connection only; Owner approvals (payment, credentials, publishing, contact) unchanged')


def detach(store, pid, dep_id):
    if not any(d['id'] == dep_id for d in attached(store, pid)):
        raise Rejected(f'연결되지 않은 부서입니다: {dep_id}')
    store.event(pid, 'department_detached', department=dep_id,
                applies='from the next delegation; a stage already running finishes; results and records are kept')


def summary(spec):
    """What 淸月 CEO needs to plan with a department (not its prompt text)."""
    return {k: spec[k] for k in ('id', 'version', 'name', 'role', 'provides', 'tools', 'inputs', 'outputs',
                                 'acceptance_criteria')} | {'agent_role': spec['agent']['role'],
                                                            'network': spec['permissions']['network']}


def check_stage(stage, attached_specs, library=None, final=False):
    """None if this stage may run as planned; otherwise why it is refused. A temporary agent (department "") is
    bound by the attached departments too: it cannot use tools or web research none of them grants, nor take
    the agent role of a library department that is not attached (that would bypass the attachment). The final stage
    may declare code_generation either way: producing the deliverable is the engine's build contract."""
    build = {'reasoning', 'code_generation'} if final else {'reasoning'}
    dep = stage.get('department') or ''
    if not dep:
        if not attached_specs:
            return None                                      # no departments: the pre-department rules apply
        name = stage.get('name')
        allowed = build | {t for s in attached_specs.values() for t in s['tools']}
        extra = sorted(set(stage.get('capabilities', [])) - allowed)
        if extra:
            return (f"temporary agent for stage {name!r} asks {extra}, which no attached department provides; "
                    'attach a department that provides it')
        if stage.get('web') and not any(s['permissions']['network'] for s in attached_specs.values()):
            return f"temporary agent for stage {name!r} needs web access but no attached department has network permission"
        role = str(stage.get('agent_role', '')).strip().lower()
        for other, spec in (library or {}).items():
            if other not in attached_specs and spec['agent']['role'].strip().lower() == role:
                return (f"temporary agent for stage {name!r} takes the agent role of department {other!r}, "
                        'which is not attached')
        return None
    spec = attached_specs.get(dep)
    if spec is None:
        return f"stage {stage.get('name')!r} was delegated to department {dep!r}, which is not attached to this project"
    extra = sorted(set(stage.get('capabilities', [])) - set(spec['tools']) - build)
    if extra:
        return f"stage {stage.get('name')!r} asks {extra} beyond department {dep!r}'s tools {spec['tools']}"
    if stage.get('web') and not spec['permissions']['network']:
        return f"stage {stage.get('name')!r} needs web access but department {dep!r} has no network permission"
    return None
