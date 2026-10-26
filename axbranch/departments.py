"""Department packages: shared, versioned function packages (departments/<id>/department.json) that a project
attaches. Attachment is per project and recorded as events (persisted, auditable, never mixed between projects).
淸月 CEO delegates pipeline stages only to attached departments; a stage without one is a visibly recorded
temporary agent. Attaching connects functions; it never approves payments, credentials, publishing or contact."""
import json
import hashlib
import re
from decimal import Decimal, InvalidOperation, ROUND_CEILING
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
    if not isinstance(spec.get('workflow', []), list) or not all(isinstance(s, str) and s.strip() for s in spec.get('workflow', [])):
        problems.append('workflow must be a list of nonempty steps')
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
    if not isinstance(c.get('document_sections', []), list) or not all(
            isinstance(s, str) and s.strip() for s in c.get('document_sections', [])):
        problems.append('contract.document_sections must be nonempty strings')
    if 'product_plan' in c and not isinstance(c['product_plan'], bool):
        problems.append('contract.product_plan must be boolean')
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
    return problems + check_document(spec, text)


def check_document(spec, text):
    """Structure and arithmetic only. Independent verification still judges evidence and decisions."""
    contract = (spec or {}).get('contract') or {}
    headings = {s.strip() for s in re.findall(r'^#{1,6}\s+(.+?)\s*$', text, re.M)}
    problems = [f'필수 문서 항목 없음: {s}' for s in contract.get('document_sections', []) if s not in headings]
    if not contract.get('product_plan'):
        return problems
    plans = []
    for raw in re.findall(r'```json\s*\n(.*?)\n```', text, re.S):
        try:
            data = json.loads(raw)
            if isinstance(data, dict) and 'product_plan' in data:
                plans.append(data['product_plan'])
        except ValueError:
            continue
    if len(plans) != 1 or not isinstance(plans[0], dict):
        return problems + ['product_plan JSON 객체가 정확히 한 개 필요합니다']
    plan = plans[0]
    for key in ('claims', 'mvp', 'excluded', 'experiments'):
        if not isinstance(plan.get(key), list) or not plan[key]:
            problems.append(f'product_plan.{key} 목록이 필요합니다')
    for key in ('mvp', 'excluded'):
        if isinstance(plan.get(key), list) and not all(isinstance(s, str) and s.strip() for s in plan[key]):
            problems.append(f'product_plan.{key}에 비어 있지 않은 설명이 필요합니다')
    for claim in plan.get('claims', []) if isinstance(plan.get('claims'), list) else []:
        if not isinstance(claim, dict) or not str(claim.get('statement', '')).strip() or claim.get('status') not in (
                'VERIFIED', 'ESTIMATED', 'UNKNOWN'):
            problems.append('주장에 내용과 사실/추정/미확인 구분이 필요합니다')
        elif claim['status'] == 'VERIFIED' and (not isinstance(claim.get('evidence'), list) or
                not any(isinstance(e, str) and e.strip() for e in claim['evidence'])):
            problems.append('확인 사실에 근거 참조가 없습니다')
    for experiment in plan.get('experiments', []) if isinstance(plan.get('experiments'), list) else []:
        if not isinstance(experiment, dict) or not all(str(experiment.get(k, '')).strip() for k in ('metric', 'threshold', 'method')):
            problems.append('실험에 지표·기준·방법이 필요합니다')
    if plan.get('market_validation') != {'willingness_to_pay': 'UNKNOWN', 'revenue': 'UNKNOWN'}:
        problems.append('고객 접촉·거래 없는 지불 의사와 실제 매출은 UNKNOWN이어야 합니다')
    scenarios = plan.get('scenarios')
    if not isinstance(scenarios, list) or len(scenarios) != 3:
        return problems + ['손익 시나리오 세 개가 필요합니다']
    names = [s.get('name') for s in scenarios if isinstance(s, dict)]
    if (len(names) != 3 or not all(isinstance(name, str) for name in names)
            or set(names) != {'downside', 'base', 'upside'}):
        problems.append('시나리오 이름은 downside/base/upside여야 합니다')
    for s in scenarios:
        try:
            nums = []
            for key in ('price', 'unit_cost', 'quantity', 'fixed_cost', 'revenue', 'profit'):
                if isinstance(s[key], bool) or not isinstance(s[key], (int, float)):
                    raise ValueError('수치 형식')
                value = Decimal(str(s[key]))
                if not value.is_finite():
                    raise ValueError('유한 수치')
                nums.append(value)
            price, cost, quantity, fixed, revenue, profit = nums
            if min(price, cost, quantity, fixed) < 0 or quantity != quantity.to_integral_value():
                raise ValueError('비음수 금액과 정수 수량')
            margin = price - cost
            breakeven = int((fixed / margin).to_integral_value(rounding=ROUND_CEILING)) if margin > 0 else None
            if abs(revenue - price * quantity) > Decimal('0.01') or abs(profit - (margin * quantity - fixed)) > Decimal('0.01'):
                raise ValueError('매출/손익 산식')
            if isinstance(s.get('break_even_units'), bool) or s.get('break_even_units') != breakeven:
                raise ValueError('손익분기 수량')
        except (KeyError, TypeError, ValueError, InvalidOperation, OverflowError) as e:
            problems.append(f'손익 시나리오 오류: {e}')
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


# Registry lifecycle (H1). Kept beside the package (departments/<id>/lifecycle.json), never inside department.json:
# a status change must not alter the spec digest that projects pinned. A packaged build reads its bundled files.
STATUSES = ('candidate', 'verified', 'quarantined', 'retired')
USABLE = ('verified', 'legacy')               # may be newly attached and receive new delegation
LEGACY = {'status': 'legacy', 'validation': 'schema_valid',
          'reason': 'lifecycle 도입 전 부서: 명세 형식 검증만 통과했고 행동 검증은 판정되지 않았습니다. 기존처럼 연결할 수 있습니다.',
          'provenance': {'source': 'ax-native'}, 'evidence': [], 'history': []}
MIN_VERIFIED_EVIDENCE = 2                      # one favourable result is never a verified capability


def lifecycle(dep_id, root=None):
    """Registry state, read fresh each time. Absent = legacy; unreadable or invalid = quarantined (fail closed)."""
    f = (Path(root) if root else ROOT) / dep_id / 'lifecycle.json'
    try:
        data = json.loads(f.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return dict(LEGACY)
    except (OSError, ValueError) as e:
        return {'status': 'quarantined', 'reason': f'lifecycle.json을 읽을 수 없습니다: {e}', 'evidence': [], 'history': []}
    if not isinstance(data, dict) or data.get('status') not in STATUSES:
        return {'status': 'quarantined', 'reason': 'lifecycle.json 상태가 올바르지 않습니다', 'evidence': [], 'history': []}
    return data


def blocked(dep_id, root=None):
    """Why new delegation to this department is refused now (None = allowed). Checked at every boundary."""
    if not dep_id:
        return None
    state = lifecycle(dep_id, root)
    if state['status'] in USABLE:
        return None
    return f"department {dep_id!r} is {state['status']}: Owner decision needed ({state.get('reason', '')})"


def set_lifecycle(dep_id, status, reason, evidence=(), by='owner-cli', root=None, when=None):
    """Owner-only recorded transition (the CLI; agents have no shell). Verified needs independent evidence."""
    import time
    if status not in STATUSES:
        raise Rejected(f'알 수 없는 상태: {status} ({", ".join(STATUSES)})')
    if not str(reason).strip():
        raise Rejected('상태 변경에는 이유가 필요합니다')
    evidence = [str(e) for e in evidence if str(e).strip()]
    if status == 'verified' and len(evidence) < MIN_VERIFIED_EVIDENCE:
        raise Rejected(f'verified에는 근거가 {MIN_VERIFIED_EVIDENCE}개 이상 필요합니다 (형식 검증이나 한 번의 성공만으로는 부족)')
    f = (Path(root) if root else ROOT) / dep_id / 'department.json'
    if not f.is_file():
        raise Rejected(f'라이브러리에 없는 부서입니다: {dep_id}')
    spec = json.loads(f.read_text(encoding='utf-8'))
    old = lifecycle(dep_id, root)
    entry = {'at': when or time.strftime('%Y-%m-%d %H:%M:%S'), 'from': old['status'], 'to': status, 'reason': reason,
             'evidence': evidence, 'by': by, 'version': spec.get('version'), 'spec_sha256': spec_digest(spec)}
    new = {'status': status, 'reason': reason, 'evidence': evidence, 'version': spec.get('version'),
           'provenance': old.get('provenance') or {'source': 'ax-native'}, 'history': [*old.get('history', []), entry]}
    f.with_name('lifecycle.json').write_text(json.dumps(new, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    return new


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
    state = lifecycle(dep_id)
    if state['status'] not in USABLE:
        raise Rejected(f"{specs[dep_id]['name']} 부서는 {state['status']} 상태라 새로 연결할 수 없습니다: {state.get('reason', '')}")
    spec = specs[dep_id]
    store.event(pid, 'department_attached', department=dep_id, version=spec['version'],
                spec=spec, spec_sha256=spec_digest(spec),
                note='function connection only; Owner approvals (payment, credentials, publishing, contact) unchanged')


def spec_digest(spec):
    return hashlib.sha256(json.dumps(spec, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()


def resolve(store, pid, library):
    """Use the exact attached snapshot. A legacy version mismatch stops instead of silently upgrading."""
    current = {}
    for e in store.events(pid, {'department_attached', 'department_detached'}):
        d = e['detail']
        if e['kind'] == 'department_detached':
            current.pop(d['department'], None)
        else:
            current[d['department']] = d
    out = {}
    for dep, d in current.items():
        spec = d.get('spec') or library.get(dep)
        if not spec or validate(spec, dep) or spec.get('version') != d['version'] or (
                d.get('spec') and d.get('spec_sha256') != spec_digest(spec)):
            raise Rejected(f'연결한 부서 {dep}@{d["version"]} 명세를 확인할 수 없습니다. 자동 업그레이드하지 않습니다.')
        out[dep] = spec
    return out


def detach(store, pid, dep_id):
    if not any(d['id'] == dep_id for d in attached(store, pid)):
        raise Rejected(f'연결되지 않은 부서입니다: {dep_id}')
    store.event(pid, 'department_detached', department=dep_id,
                applies='from the next delegation; a stage already running finishes; results and records are kept')


DOCUMENT_RULE = ('The deliverable must be a markdown document containing each required heading line exactly as given '
                 '(any heading level; the text unchanged: no translation, numbering or additions) and, when '
                 'product_plan_json is true, exactly one ```json fenced block whose top-level key is product_plan. '
                 'This is a department contract checked deterministically at verification; it takes precedence over '
                 'differing section names in stage instructions, and any length limit must leave room for it.')


def document_contracts(specs, delegated=None):
    """The document structure each (delegated) department requires, in the form planner, producer and verifier
    all see: the same headings check_document enforces."""
    out = []
    for dep, spec in specs.items():
        c = spec.get('contract') or {}
        if c.get('document_sections') and (delegated is None or dep in delegated):
            out.append({'department': dep, 'version': spec['version'],
                        'headings': [f'## {s}' for s in c['document_sections']],
                        'product_plan_json': bool(c.get('product_plan'))})
    return out


def preflight(plan, specs):
    """Conflicts between a plan and its delegated departments' contracts, found before any agent is called."""
    delegated = {s.get('department') for s in plan.get('pipeline', [])}
    return [f"department {d['department']!r} requires a markdown document with its headings, but the plan delivers "
            f"artifact_kind {plan.get('artifact_kind')!r}; re-plan as markdown or detach the department"
            for d in document_contracts(specs, delegated) if plan.get('artifact_kind') != 'markdown']


def summary(spec):
    """What 淸月 CEO needs to plan with a department (not its prompt text)."""
    out = {k: spec[k] for k in ('id', 'version', 'name', 'role', 'provides', 'tools', 'inputs', 'outputs',
                                'acceptance_criteria')} | {'agent_role': spec['agent']['role'],
                                                           'network': spec['permissions']['network'],
                                                           'workflow': spec.get('workflow', [])}
    contract = document_contracts({spec['id']: spec})
    if contract:
        out['document_contract'] = {**contract[0], 'rule': DOCUMENT_RULE}
    return out


def check_stage(stage, attached_specs, library=None, final=False):
    """None if this stage may run as planned; otherwise why it is refused. A temporary agent (department "") is
    bound by the attached departments too: it cannot use tools or web research none of them grants, nor take
    the agent role of a library department that is not attached (that would bypass the attachment). The final stage
    may declare code_generation either way: producing the deliverable is the engine's build contract."""
    build = {'reasoning', 'code_generation'} if final else {'reasoning'}
    dep = stage.get('department') or ''
    usable = {d: s for d, s in attached_specs.items() if not blocked(d)}   # quarantined/retired lend nothing
    if not dep:
        if not attached_specs:
            return None                                      # no departments: the pre-department rules apply
        name = stage.get('name')
        if not usable:
            return (f"temporary agent for stage {name!r}: no attached department is usable (candidate, quarantined or retired) "
                    '(Owner decision needed)')
        allowed = build | {t for s in usable.values() for t in s['tools']}
        extra = sorted(set(stage.get('capabilities', [])) - allowed)
        if extra:
            return (f"temporary agent for stage {name!r} asks {extra}, which no attached department provides; "
                    'attach a department that provides it')
        if stage.get('web') and not any(s['permissions']['network'] for s in usable.values()):
            return f"temporary agent for stage {name!r} needs web access but no attached department has network permission"
        requested = set(stage.get('capabilities', [])) - build
        if not any(requested <= set(s['tools']) and (not stage.get('web') or s['permissions']['network'])
                   for s in usable.values()):
            return f"temporary agent for stage {name!r} combines tools/permissions from different departments"
        role = str(stage.get('agent_role', '')).strip().lower()
        for other, spec in {**(library or {}), **attached_specs}.items():
            if other not in usable and spec['agent']['role'].strip().lower() == role:
                return (f"temporary agent for stage {name!r} takes the agent role of department {other!r}, "
                        'which is not attached or not usable')
        return None
    spec = attached_specs.get(dep)
    if spec is None:
        return f"stage {stage.get('name')!r} was delegated to department {dep!r}, which is not attached to this project"
    if dep not in usable:
        return f"stage {stage.get('name')!r}: {blocked(dep)}"
    extra = sorted(set(stage.get('capabilities', [])) - set(spec['tools']) - build)
    if extra:
        return f"stage {stage.get('name')!r} asks {extra} beyond department {dep!r}'s tools {spec['tools']}"
    if stage.get('web') and not spec['permissions']['network']:
        return f"stage {stage.get('name')!r} needs web access but department {dep!r} has no network permission"
    return None
