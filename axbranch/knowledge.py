"""Long-term knowledge: the Obsidian vault (read + Owner-authorized archive) and
Global AI Intelligence's library (read-only). Only relevant excerpts ever reach a
model; the vault is never injected whole."""
import hashlib
import json
import re
import sqlite3
import time
from pathlib import Path

_WORD = re.compile(r'[a-z0-9_]{3,}|[^\W\x00-\x7f]{2,}')
_STOP = {'the', 'and', 'for', 'with', 'that', 'this', 'from', 'into', 'are', 'will', 'can', 'should',
         # Korean request words every goal has: they matched unrelated projects
         '만들어줘', '만들어', '만들기', '해줘', '해주세요', '주세요', '해서', '하는', '있는', '프로그램', '도구'}
_PARTICLE = re.compile(r'(으로|에서|에게|까지|부터|를|을|이|가|은|는|의|에|로|와|과|도)$')


def terms(text):
    """Search terms: lower-cased words; a Korean word loses one trailing particle (데이터를 -> 데이터)."""
    out = set()
    for word in _WORD.findall((text or '').lower()):
        if not word.isascii() and len(word) > 2:
            word = _PARTICLE.sub('', word)
        out.add(word)
    return out - _STOP


def _section(text, heading):
    """The body of '## heading' (up to the next '## '), or ''."""
    m = re.search(rf'^## {re.escape(heading)}[^\n]*\n(.*?)(?=^## |\Z)', text, flags=re.M | re.S)
    return m.group(1).strip() if m else ''


def retrieve(vault, query, limit=3, chars=6000):
    """Vault notes ranked by term overlap with the query, for the CEO's context before planning.
    A structured project archive is matched and excerpted by its title, summary and reusable knowledge (not
    by a 200 KB verification log), and every hit names its note, project and evidence location."""
    # ponytail: full scan per call; add an FTS5 index when the vault outgrows a few thousand notes.
    q, scored = terms(query), []
    for path in Path(vault).rglob('*.md') if Path(vault).is_dir() else ():
        if '.obsidian' in path.parts or '.trash' in path.parts:
            continue
        raw = path.read_bytes()      # hashed as read: provenance of exactly what this retrieval saw
        text = raw.decode('utf-8', errors='replace').replace('\r\n', '\n').replace('\r', '\n')   # = text mode
        reusable = _section(text, REUSABLE)
        if reusable:
            title = text.split('\n', 1)[0]
            body = f"{title}\n\n## {REUSABLE}\n{reusable}\n\n## {SUMMARY}\n{_section(text, SUMMARY)}"
        else:
            body = text
        score = len(q & terms(path.stem + ' ' + body))
        if score >= 2:
            project = re.search(r'project: `(P-[\w-]+)`', text)
            scored.append((score, path, body, project and project.group(1), bool(reusable),
                           hashlib.sha256(raw).hexdigest()))
    scored.sort(key=lambda s: -s[0])
    # '_source_sha256' is private provenance: the engine moves it out of the item before any prompt.
    return [{'note': str(p.relative_to(vault)), 'project': pid, 'matched_terms': score,
             'evidence': f"{p.relative_to(vault)} § {EVIDENCE}" if structured else str(p.relative_to(vault)),
             'excerpt': b[:chars], '_source_sha256': sha} for score, p, b, pid, structured, sha in scored[:limit]]


def intel(db_path, query, limit=5):
    """Recent Global AI Intelligence items relevant to the query. Read-only URI: AX
    Branch can never alter that library."""
    if not Path(db_path).is_file():
        return []
    q = terms(query)
    try:
        con = sqlite3.connect(f'{Path(db_path).resolve().as_uri()}?mode=ro', uri=True)
        try:
            rows = con.execute('SELECT title,summary,source,published_at,original_url,verification_status '
                               'FROM items ORDER BY id DESC LIMIT 1000').fetchall()
        finally:
            con.close()
    except sqlite3.Error:
        return []
    # Off-topic news in the CEO's context is noise: require a real share of the query, not 2 stray words.
    need = max(2, -(-len(q) * 3 // 10))
    scored = sorted(((len(q & terms(f'{r[0]} {r[1]}')), r) for r in rows), key=lambda s: -s[0])
    return [{'title': r[0], 'summary': (r[1] or '')[:400], 'source': r[2], 'published_at': r[3],
             'url': r[4], 'verification_status': r[5]} for score, r in scored[:limit] if score >= need]


PROVISIONAL = 'PROVISIONAL: derived from recorded runs, not Owner-approved knowledge; an observation, not a lesson'
# Fixed failure categories: a card never carries a check's name or problem text (free text of another project).
_CATEGORIES = (('check itself was invalid', ('is not a css selector', 'invalid header', 'invalid request target',
                                              'must start with /', 'not a valid action')),
               ('browser unavailable', ('no headless browser',)),
               ('program crashed or exited', ('crashed', 'traceback', 'exited')),
               ('server stopped answering', ('connection lost', 'request failed', 'not listening', 'before serving')),
               ('timed out', ('did not finish',)),
               ('HTTP status differed from the expected one', ('status ',)),
               ('exit code differed from the expected one', ('exit ',)),
               ('forbidden text was shown', ('must not contain',)),
               ('page element or flow step not found', ('matched nothing', 'browser action', 'not shown on the page')),
               ('expected text missing', ('lacks',)))


def _category(step):
    text = ' '.join(step.get('problems', [])).lower()
    return next((name for name, keys in _CATEGORIES if any(k in text for k in keys)), 'other failure')


def experience(store, query, exclude_project=None, signatures=(), limit=3, before=None, per_project=2):
    """Runtime experience from other projects' recorded verifications, available without an Owner archive.
    Derived at query time (nothing cached, so a source that becomes ineligible is gone at once) from structured
    fields only: no findings text, no Owner feedback, no artifact content. Each card states its cause with the
    attribution status (VERIFIED / ESTIMATED / UNKNOWN) and whether a later version passed THE SAME check (a later
    PASS is not proof of the cause). Projects the Owner closed without saving are excluded. before (a timestamp)
    limits it to facts recorded by then (offline evaluation; live use is always now)."""
    from . import attribution, kindex
    q, wanted, cards = terms(query), set(signatures), []
    for row in store.projects():
        p = store.project(row['id'])
        if p['id'] == exclude_project or p['closed_mode'] == 'discard':
            continue
        # The CEO's short project name; never the Owner's goal text; unknown for a historical query (titles change).
        title = '' if before is not None else str((p['plan'] or {}).get('title') or '')[:20]
        vs = [v for v in store.verifications(p['id']) if before is None or v['created'] <= before]
        latest = {}
        for v in vs:
            if v['verdict'] != 'FAIL':
                continue
            for st in ((v['checks'] or {}).get('runtime') or {}).get('steps', []):
                if not st.get('ok'):
                    latest[kindex.signature(st)] = (v, st)            # the latest FAIL with this signature
        for sig, (v, st) in latest.items():
            later = [w for w in vs if w['verdict'] == 'PASS' and w['created'] > v['created']]
            passed = [w for w in later if any(s.get('name') == st.get('name') and s.get('ok')
                                              for s in ((w['checks'] or {}).get('runtime') or {}).get('steps', []))]
            # Re-verifying the SAME version (harness repair, retry) is not a later version passing.
            outcome = ('a later version passed this same check' if any(w['artifact_id'] != v['artifact_id'] for w in passed)
                       else 'the same version passed this check when re-verified' if passed
                       else 'a later run passed verification, but this check was not re-run' if later
                       else 'nothing passed verification after it')
            try:
                cause = attribution.verification_causes(store, p['id'], v)
                cause = f"{cause['primary']} ({cause['primary_status']})"
            except Exception:                       # observational: a rules error never blocks retrieval
                cause = 'UNKNOWN (UNKNOWN)'
            name = str(st.get('name', ''))[:80]
            score = (10 if sig in wanted else 0) + len(q & terms(f'{p["goal"]} {title} {name} {sig}'))   # goal matched, not shown
            if sig in wanted or score >= 2:
                cards.append((score, v['created'], {
                    'kind': 'runtime_experience', 'status': PROVISIONAL, 'project': p['id'], 'title': title,
                    'observation': f"a runtime check failed: {_category(st)} (evidence class {sig.split(':', 1)[0]})",
                    'cause': cause, 'outcome': outcome, 'evidence': f"verification {v['id']} (v{v['iteration']})",
                    'matched_terms': score}))
    cards.sort(key=lambda c: (-c[0], -c[1]))
    out, seen = [], {}
    for _, _, c in cards:
        if seen.get(c['project'], 0) < per_project:          # one project's many failures do not crowd out others
            seen[c['project']] = seen.get(c['project'], 0) + 1
            out.append(c)
    return out[:limit]


def _slug(text, n=50):
    return re.sub(r'[\\/:*?"<>|#^\[\]\s]+', ' ', text).strip()[:n].strip() or 'project'


# Department experience is a projection into the EXISTING event store, never a second knowledge database.
# Free text (goals, feedback, source content, decisions, provider errors) stays at its original reference.
EXPERIENCE_VERSION = 3   # 3: bounded event-derived lessons, never inferred causal explanations
EXPERIENCE_DAYS = 180
TOKEN_FIELDS = ('input_tokens', 'output_tokens', 'cached_input_tokens', 'cache_creation_input_tokens',
                'cache_read_input_tokens', 'reasoning_output_tokens')


def usage_summary(events):
    """Agent turns and reported usage only; retries/hidden usage are not guessed or counted as zero."""
    calls = [e for e in events if e['kind'] == 'call']
    usage = []
    for e in calls:
        raw = e['detail'].get('tokens')
        usage.append({k: raw[k] for k in TOKEN_FIELDS if isinstance(raw.get(k), (int, float)) and not isinstance(raw[k], bool)}
                     if isinstance(raw, dict) else {})
    return {'agent_turn_attempts': sum(e['kind'] == 'call_start' for e in events), 'agent_turns_completed': len(calls),
            'failed_turns': sum(e['kind'] == 'call_failed' for e in events),
            'provider_seconds': sum(e['detail'].get('seconds', 0) for e in events if e['kind'] in ('call', 'call_failed')),
            'call_event_ids': [e['id'] for e in calls][-32:], 'call_usage_truncated': len(calls) > 32,
            'reported_total_tokens': reported_tokens(events),
            'token_usage_by_call': usage[-32:], 'token_usage_complete': bool(calls) and reported_tokens(events) is not None,
            'physical_cli_attempts': 'UNKNOWN',
            'owner_actions': sum(e['kind'] == 'owner_action' for e in events),
            'developer_test_inputs': sum(e['kind'] == 'feedback_provenance' and e['detail'].get('actor') == 'owner_delegated_test'
                                         for e in events)}


def call_tokens(detail):
    """One completed turn's reported tokens (input + output, plus Claude cache tokens); None if not reported."""
    u = detail.get('tokens')
    if not isinstance(u, dict) or any(not isinstance(u.get(k), (int, float)) or isinstance(u.get(k), bool)
                                      or u[k] < 0 for k in ('input_tokens', 'output_tokens')):
        return None
    total = u['input_tokens'] + u['output_tokens']
    if str(u.get('source', '')).lower().startswith('claude'):
        total += sum(u.get(k) or 0 for k in ('cache_creation_input_tokens', 'cache_read_input_tokens'))
    return total


def reported_tokens(events):
    """None if any completed turn lacks input/output usage. Cached/reasoning subsets are not double-counted."""
    total = 0
    for e in events:
        if e['kind'] != 'call':
            continue
        n = call_tokens(e['detail'])
        if n is None:
            return None
        total += n
    return total


def verification_level(v):
    """A PASS's independence as RECORDED: a different provider than the producer, the same provider in a separate
    verification role (fallback), or unknown provenance (older records, unrecorded producer). None if not a PASS."""
    if not v or v.get('verdict') != 'PASS' or not (v.get('checks') or {}).get('ok'):
        return None
    prov = (v.get('checks') or {}).get('verifier_provenance') or {}
    producer, verifier = prov.get('producer'), prov.get('verifier')
    if not producer or not verifier or prov.get('producer_source') != 'recorded':
        return 'PASS_PROVENANCE_UNKNOWN'
    return 'CROSS_PROVIDER_PASS' if producer != verifier else 'SAME_PROVIDER_ROLE_SEPARATED_PASS'


def department_lessons(events, department, delegations):
    """Project-local observations mapped to fixed advice, without copying private source text.

    A candidate describes an observed event, not its unproven root cause or a learned skill.
    Department events must match this verification's delegated plan versions and stages.
    """
    versions = {e['detail'].get('plan_version') for e in delegations
                if e['detail'].get('plan_version') is not None}
    stages = {e['detail'].get('stage') for e in delegations if e['detail'].get('stage')}
    rules = (
        ('contract_format', '부서 출력 형식 오류',
         '이 부서의 출력 계약 검사에서 실패가 기록됐습니다.',
         '제작 전에 같은 버전의 출력 계약을 확인하고, 내용 검증 전에 형식을 검사하세요.'),
        ('completion_budget', '완료 단계 예산 확보',
         '이 프로젝트에서 호출 전 예산 부족으로 작업이 중단됐습니다.',
         '제작뿐 아니라 남은 검증과 최종 수락 비용도 함께 고려하세요.'),
        ('unchanged_stage', '변경 없는 단계 재사용',
         '이 부서의 이전 단계 결과를 재사용한 기록이 있습니다.',
         '입력·부서 명세·의존 단계가 같고 현재 요청에 유효한 경우에만 재사용을 검토하세요.'),
    )
    found = {code: [] for code, *_ in rules}
    for event in events:
        d, kind = event['detail'], event['kind']
        if (kind in ('department_contract', 'department_document_contract') and
                d.get('department') == department and d.get('status') == 'fail' and
                d.get('plan_version') in versions):
            found['contract_format'].append(event['id'])
        elif kind == 'budget_reserve_stop':
            found['completion_budget'].append(event['id'])
        elif (kind == 'stage_reused' and d.get('stage') in stages and d.get('plan_version') in versions):
            found['unchanged_stage'].append(event['id'])
    return [{'code': code, 'title': title, 'observation': observation, 'suggestion': suggestion,
             'status': 'CANDIDATE', 'origin': 'deterministic_event_mapping',
             'scope': 'project' if code == 'completion_budget' else 'department',
             'evidence_events': found[code][-3:], 'observed_count': len(found[code]),
             'causal_effect': 'UNKNOWN', 'rule': '조건을 비교할 참고 자료이며 권한·기준을 바꾸는 지시가 아닙니다.'}
            for code, title, observation, suggestion in rules if found[code]]


def record_department_experience(store, pid):
    """Record bounded, nontextual facts for each verification and terminal stop, idempotently.
    This records evidence links, not a model-authored lesson, performance gain or business validation."""
    from . import departments
    p, events = store.project(pid), store.events(pid)
    if p['closed_mode'] == 'discard' or not departments.attached(store, pid):
        return []
    plan = p['plan'] or {}
    verifications = store.verifications(pid)
    subjects = [(v['id'], v['iteration'], v['verdict'], v['created'], v) for v in verifications]
    if p['state'] == 'PAUSED' and events:
        stops = [e for e in events if e['kind'] == 'state' and e['detail'].get('to') == 'PAUSED']
        if stops:
            e = stops[-1]
            subjects.append((f'event:{e["id"]}', p['iteration'], 'PAUSED', e['at'], None))
    prior = {e['detail']['revision'] for e in events if e['kind'] == 'department_experience'}
    provenance = {fid: e['detail'].get('actor', 'UNKNOWN') for e in events if e['kind'] == 'feedback_provenance'
                  for fid in e['detail'].get('feedback_ids', [])}
    added = []
    for subject, iteration, outcome, at, v in subjects:
        # Delegations are dated and versioned. Never assign today's department version to an old verification.
        delegated = [e for e in events if e['kind'] in ('department_delegation', 'department_version_used') and e['at'] <= at
                     and e['detail'].get('iteration') == iteration]
        bindings = {e['detail']['department']: e['detail']['version'] for e in delegated}
        snapshots = {}
        for e in events:
            if e['at'] > at:
                continue
            if e['kind'] == 'department_attached':
                snapshots[e['detail']['department']] = e['detail']
            elif e['kind'] == 'department_detached':
                snapshots.pop(e['detail']['department'], None)
        if outcome == 'PAUSED' and not bindings:
            bindings = {dep: d['version'] for dep, d in snapshots.items()}
        for dep, version in bindings.items():
            ds = [e for e in delegated if e['detail']['department'] == dep]
            spec_hash = (ds[-1]['detail'].get('spec_sha256') if ds else None) or (
                snapshots.get(dep, {}).get('spec_sha256') if snapshots.get(dep, {}).get('version') == version else None) or 'UNKNOWN'
            identity = 'E-' + hashlib.sha256(f'{pid}:{dep}:{version}:{subject}'.encode()).hexdigest()[:16]
            artifact = next((a for a in store.artifacts(pid) if v and a['id'] == v['artifact_id']), None)
            feedback = [{'id': f['id'], 'iteration': f['iteration'], 'verdict': f['verdict'],
                         'actor': provenance.get(f['id'], 'UNKNOWN')}
                        for f in store.feedback(pid) if f['iteration'] == iteration][-20:]
            relevant = [e for e in events if e['at'] <= at]
            sessions = [e for e in relevant if e['kind'] == 'session']
            mode = sessions[-1]['detail'].get('execution_mode', 'UNKNOWN') if sessions else 'UNKNOWN'
            contract = [e for e in relevant if e['kind'] in ('department_contract', 'department_document_contract')
                        and e['detail'].get('department') == dep]
            d = {'experience_id': identity, 'schema': EXPERIENCE_VERSION, 'project': pid, 'department': dep,
                 'department_version': version, 'iteration': iteration, 'recorded_at': at, 'outcome': outcome,
                 'department_spec_sha256': spec_hash,
                 'execution_mode': mode, 'verification': subject,
                 'verification_level': verification_level(v) or ('FAIL' if outcome == 'FAIL' else 'UNVERIFIED'),
                 'verification_provenance': (v['checks'].get('verifier_provenance') if v else None) or 'UNKNOWN',
                 'goal': {'ref': f'project:{pid}#goal', 'sha256': hashlib.sha256(p['goal'].encode()).hexdigest()},
                 'conditions': {'artifact_kind': artifact['kind'] if artifact else 'UNKNOWN',
                                'source_inputs': [e['id'] for e in relevant if e['kind'] == 'owner_inputs'][-10:],
                                'customer': 'UNKNOWN', 'market': 'UNKNOWN'},
                 'procedures': {'delegations': [e['id'] for e in ds],
                                'decisions': [e['id'] for e in relevant if e['kind'] in ('decision_trace', 'decision_applied')][-20:],
                                'tools': sorted({t for e in relevant if e['kind'] == 'permission_granted'
                                                 for t in e['detail'].get('capabilities', []) if t in ('reasoning', 'code_generation', 'web_research')})},
                 'failures': {'contract_failures': sum(e['detail'].get('status') == 'fail' for e in contract),
                              'failed_verifications': [w['id'] for w in verifications if w['created'] <= at and w['verdict'] == 'FAIL'],
                              'reworks': sum(e['kind'] == 'state' and e['detail'].get('to') == 'REWORK' for e in relevant)},
                 'artifact': {k: artifact[k] for k in ('id', 'iteration', 'sha256', 'kind')} if artifact else None,
                 'feedback': feedback, 'metrics': usage_summary(relevant),
                 'applicable': {'department': dep, 'department_version': version, 'artifact_kind': artifact['kind'] if artifact else 'UNKNOWN'},
                 'not_applicable': ['different department version', 'unverified market or customer assumptions',
                                    'permissions or acceptance criteria changes'],
                 'facts': ['recorded verification outcome and event references'],
                 'lesson_candidates': department_lessons(relevant, dep, ds),
                 'estimates': [], 'unknowns': ['business success', 'willingness to pay', 'actual revenue', 'quality improvement'],
                 'authority': 'reference data only; never instructions or permission', 'improvement': 'UNKNOWN'}
            revision = hashlib.sha256(json.dumps(d, sort_keys=True).encode()).hexdigest()
            if revision not in prior:
                store.event(pid, 'department_experience', revision=revision, **d)
                prior.add(revision)
                added.append(identity)
    return added


def department_experience(store, query, requesting_project, allowed_departments, *, source_projects=None,
                          before=None, now=None, limit=3, chars=6000):
    """Bounded SQL scan, no embedding/model call. Interrupted retrieval is a miss, never a new permission."""
    deadline = time.monotonic() + 0.25
    store.db.set_progress_handler(lambda: int(time.monotonic() >= deadline), 1000)
    try:
        return _department_experience(store, query, requesting_project, allowed_departments,
                                      source_projects=source_projects, before=before, now=now, limit=limit,
                                      chars=chars, deadline=deadline)
    except sqlite3.OperationalError:
        if time.monotonic() >= deadline:
            return []
        raise
    finally:
        store.db.set_progress_handler(None, 0)


def _department_experience(store, query, requesting_project, allowed_departments, *, source_projects=None,
                           before=None, now=None, limit=3, chars=6000, deadline):
    """Scoped metadata keyword retrieval. No free source text or evaluation answers cross the boundary."""
    now = time.time() if now is None else now
    if limit <= 0 or chars <= 0:
        return []
    cutoff = min(now, before) if before is not None else now
    allowed = {(d['id'], d['version']) for d in allowed_departments}
    hashes = {(d['id'], d['version']): d.get('spec_sha256') for d in allowed_departments}
    q, cards = terms(query), []
    for row in store.db.execute('SELECT id FROM projects ORDER BY updated DESC LIMIT 200').fetchall():
        if time.monotonic() >= deadline:
            break
        p = store.project(row['id'])
        if p['id'] == requesting_project or p['closed_mode'] == 'discard' or (source_projects is not None and p['id'] not in source_projects):
            continue
        # Match source goal locally; never export the goal, tokens, feedback text or private source material.
        score = len(q & terms(p['goal']))
        if score < 2:
            continue
        latest = {}
        rows = store.db.execute("SELECT at,detail FROM events WHERE project_id=? AND kind='department_experience' "
                                'AND at<=? ORDER BY id DESC LIMIT 128', (p['id'], cutoff)).fetchall()
        for row_ in rows:
            if time.monotonic() >= deadline:
                break
            d = json.loads(row_['detail'])
            latest.setdefault(d['experience_id'], {'at': row_['at'], 'detail': d})
        for e in latest.values():
            d = e['detail']
            if (d['department'], d['department_version']) not in allowed or d['execution_mode'] != 'subscription_cli':
                continue
            expected_hash = hashes.get((d['department'], d['department_version']))
            if expected_hash and expected_hash != d.get('department_spec_sha256'):
                continue
            if not (0 <= cutoff - d['recorded_at'] <= EXPERIENCE_DAYS * 86400):
                continue
            card = {k: d[k] for k in ('experience_id', 'project', 'department', 'department_version', 'iteration',
                                      'outcome', 'verification_level', 'verification', 'artifact', 'failures',
                                      'applicable', 'not_applicable', 'facts', 'estimates', 'unknowns', 'authority', 'improvement')}
            card.update(kind='department_experience', evidence=d['verification'], recorded_at=d['recorded_at'],
                        lesson_candidates=d.get('lesson_candidates', []),
                        _source_sha256=e['detail']['revision'],
                        matched_terms=score, selection_reason='same pinned department version and matching goal terms',
                        difference_required='customer/market are UNKNOWN; compare current conditions before any adoption')
            cards.append((score, d['recorded_at'], card))
    cards.sort(key=lambda r: (-r[0], -r[1]))
    out, used, seen = [], 0, set()
    for _, _, card in cards:
        if card['project'] in seen:
            continue
        size = len(json.dumps(card, ensure_ascii=False))
        if used + size <= min(chars, 6000):
            out.append(card); used += size; seen.add(card['project'])
        if len(out) >= min(limit, 3):
            break
    return out


def experience_view(store, pid):
    events, records, retrieved, uses = store.events(pid), {}, {}, []
    changes = {(e['detail'].get('retrieval'), e['detail'].get('decision')): e['detail'] for e in events
               if e['kind'] == 'knowledge_trace' and e['detail'].get('phase') == 'DECISION_CHANGE'}
    for e in events:
        d = e['detail']
        if e['kind'] == 'department_experience':
            records[d['experience_id']] = d
        if e['kind'] == 'knowledge_trace' and d.get('phase') == 'RETRIEVED':
            hit = d.get('presented') or {}
            if hit.get('kind') == 'department_experience':
                retrieved[d['retrieval']] = hit
        if e['kind'] == 'knowledge_trace' and d.get('phase') in ('ADOPTED', 'REJECTED', 'UNASSESSED') and d['retrieval'] in retrieved:
            hit = retrieved[d['retrieval']]
            change = changes.get((d['retrieval'], d.get('decision')), {})
            uses.append({'retrieval': d['retrieval'], 'experience': hit['experience_id'],
                         'source_project': hit['project'], 'disposition': d['phase'], 'reason': d.get('reason', ''),
                         'difference': d.get('difference', ''), 'verification': hit['verification_level'],
                         'lesson_candidates': hit.get('lesson_candidates', []),
                         'claimed_change': change.get('claimed_change', ''),
                         'applied_action': change.get('applied_action', ''),
                         'attribution': change.get('attribution', 'NONE'), 'improvement': 'UNKNOWN'})
    return {'records': list(records.values())[-10:], 'uses': uses[-15:],
            'errors': [e['detail'] for e in events if e['kind'] == 'experience_record_error'][-3:],
            'searches': [e['detail'] for e in events if e['kind'] == 'experience_search'][-5:],
            'improvement': 'UNKNOWN', 'rule': '기록·검색·채택은 품질 개선의 증거가 아닙니다. 비교 평가 전에는 개선 미확인.'}


SUMMARY, RESULT, PROBLEMS, LESSONS = '요약 (Summary)', '최종 결과 (Final Result)', '문제 → 원인 → 해결', 'Verification Lessons'
FEEDBACK, OPEN, REUSABLE, EVIDENCE = 'Owner Feedback', '남은 과제', '재사용 지식 (Reusable Knowledge)', 'Evidence (원본 기록)'
SECTIONS = tuple(f'## {h}' for h in (SUMMARY, RESULT, PROBLEMS, LESSONS, FEEDBACK, OPEN, REUSABLE, EVIDENCE)) + (
    '### Goal', '### Decisions', '### Lessons', '### Verification Findings', '### Evidence', '### CEO Report',
    '### Artifacts')


def _clip(text, n=400):
    text = re.sub(r'\s+', ' ', str(text or '')).strip()
    return text if len(text) <= n else text[:n] + ' …'


def archive(vault, project, verifications, decisions, evidence, artifacts, feedback=(), effort=None,
            satisfaction_note='', approvals=(), rulings=(), path=None, closed_at=None):
    """Write the project's durable knowledge note, then read it back to verify.
    Readable first (Korean): summary, final result, problem → cause → resolution, verification lessons, Owner
    feedback, open issues, reusable knowledge (each line names its source). Then, unchanged, every original
    record under Evidence: goal, decisions, lessons, every verification finding, evidence, the CEO report and
    artifact references (path + sha256). Raw artifact content and agent working context are NOT archived.
    path: rewrite this existing note (restructure) instead of a new dated one.
    Returns (path, sha256). Raises ValueError if the archive is not intact."""
    plan, report = project['plan'] or {}, project['report'] or {}
    rounds, lessons = [], []
    for v in verifications:
        r, ch = v['result'], v['checks']
        rounds += [f"### Round {v['iteration']} — {v['verdict']} (verifier: {v['provider']})",
                   f"- deterministic checks: {'pass' if ch.get('ok') else 'FAIL'} ({', '.join(ch.get('ran', []))})"
                   + ('' if ch.get('ok') else f" — {str(ch.get('output', ''))[:300]}"),
                   f"- criteria met: {sum(c['met'] for c in r.get('criteria', []))}/{len(r.get('criteria', []))}",
                   *[f"- [{c.get('met') and 'met' or 'UNMET'}] {c['criterion']}" for c in r.get('criteria', []) if not c['met']],
                   *[f"- [{f['severity']}] {f['issue']} — evidence: {f['evidence']}" for f in r.get('findings', [])], '']
        if v['verdict'] == 'FAIL':
            lessons += [f"- Round {v['iteration']} failed: [{f['severity']}] {f['issue']}" for f in r.get('findings', [])]
    passed = [v for v in verifications if v['verdict'] == 'PASS']
    final = next((a for a in artifacts if passed and a['id'] == passed[-1].get('artifact_id')), None)
    kinds, steps = {}, {}
    for v in verifications:
        if v['verdict'] != 'FAIL':
            continue
        for f in v['result'].get('findings', []):
            if f.get('severity') in ('critical', 'major'):
                kinds[f.get('kind', '미분류')] = kinds.get(f.get('kind', '미분류'), 0) + 1
        for st in (v['checks'].get('runtime') or {}).get('steps', []):
            if not st.get('ok'):
                steps[st['name']] = steps.get(st['name'], 0) + 1
    top_steps = sorted(steps.items(), key=lambda kv: -kv[1])[:5]
    diagnoses = [d for d in decisions if d.get('what') == 'owner feedback diagnosis']
    owner_said = [f for f in feedback if f['verdict'] in ('problem', 'request')]
    fails = [v for v in verifications if v['verdict'] == 'FAIL']
    last = verifications[-1] if verifications else None
    recs = [f for f in ((last or {}).get('result') or {}).get('findings', []) if f.get('criterion', 0) == -1]
    effort = effort or {}
    sat = project.get('satisfaction')
    readable = [
        f"# {_slug(project['goal'], 80)}", '',
        f"- project: `{project['id']}`  closed: {time.strftime('%Y-%m-%d', time.localtime(closed_at or time.time()))}  "
        f"verification rounds: {len(verifications)}" + (f"  (구조 재작성: {time.strftime('%Y-%m-%d')})" if closed_at else ''),
        '- tags: #ax-branch #project-archive', '',
        f'## {SUMMARY}',
        f"- 목표: {project['goal']}",
        f"- 결과: {'검증 통과 v' + str(final['iteration']) if final else '검증 통과 버전 없음'} · 검증 {len(verifications)}회 "
        f"(PASS {len(passed)} / FAIL {len(fails)}) · Owner 피드백 {len(owner_said)}회",
        f"- Owner 만족도: {sat if sat is not None else 'UNKNOWN'}/100" + (f" — {satisfaction_note}" if satisfaction_note else ''),
        f"- CEO 판단: {_clip(report.get('judgment'), 600) or '기록 없음'}", '',
        f'## {RESULT}',
        *([f"- 최종 검증 버전: v{final['iteration']} `{final['path']}`", f"- sha256: `{final['sha256']}`"] if final
          else ['- 검증을 통과한 버전이 없습니다.']),
        *([f"- 실행 방법: {_clip(report.get('how_to_test'), 500)}"] if report.get('how_to_test') else []),
        f"- CEO 보고: {_clip(report.get('summary'), 1200) or '기록 없음'}", '',
        f'## {PROBLEMS}',
        *([f"- 문제/진단: {_clip(d.get('why', '').split(' | root cause: ')[0], 500)}\n"
           f"  - 원인: {_clip(d.get('why', '').split(' | root cause: ')[-1], 400) if ' | root cause: ' in d.get('why', '') else '기록 없음'}\n"
           f"  - 해결: 같은 프로젝트에서 계획 수정 → 재작업 → 재검증"
           for d in diagnoses] or ['- Owner가 보고한 문제가 없습니다.']),
        *([f"- 최종 해결: v{final['iteration']}이 승인 기준 검증을 통과했습니다."] if final else []), '',
        f'## {LESSONS}',
        f"- FAIL {len(fails)}회의 주요 finding 종류: " + (', '.join(f'{k} {n}회' for k, n in sorted(kinds.items())) or '없음'),
        *[f"- 반복 실패한 실행 점검: {name} — {n}회" for name, n in top_steps],
        *[f"- 같은 실패 반복으로 접근을 바꾼 결정: {_clip(d.get('why'), 200)}" for d in decisions
          if d.get('what') == 'repeated failure signature'], '',
        f'## {FEEDBACK}',
        *([f"- {f['iteration']}회차 ({f['verdict']}): {_clip(f['text'], 600)}" for f in feedback] or ['- 기록 없음']),
        f"- 만족도: {sat if sat is not None else 'UNKNOWN'}/100" + (f" — 이유: {satisfaction_note}" if satisfaction_note else ''), '',
        f'## {OPEN}',
        *([f'- {s}' for s in report.get('next_steps', [])] or ['- CEO 다음 단계 기록 없음']),
        *[f"- 검증 권고 (판정 밖): {_clip(f['issue'], 300)}" for f in recs], '',
        f'## {REUSABLE}',
        *[f"- [Owner {f['iteration']}회차 {f['verdict']}] {_clip(f['text'], 500)}" for f in owner_said],
        *[f"- [원인 진단] {_clip(d.get('why', '').split(' | root cause: ')[-1], 400)}" for d in diagnoses
          if ' | root cause: ' in d.get('why', '')],
        *[f"- [Owner ruling, 기준 {r.get('criterion')}] {_clip(r.get('ruling'), 400)}" for r in rulings],
        *[f"- [검증 교훈] '{name}' 점검이 {n}회 실패: 같은 유형의 프로젝트는 이 점검을 처음부터 계획에 넣는다"
          for name, n in top_steps[:3]],
        *[f"- [승인된 외부 연결] {a['subject']}: {_clip(a.get('purpose'), 200)}" for a in approvals
          if a.get('status') == 'approved'], '',
        '### Owner Effort', *([f"- {k}: {v}" for k, v in effort.items()] or ['- 기록 없음']), '',
        f'## {EVIDENCE}', '아래는 종료 시점의 원본 기록입니다 (내용 변경 없음).', '',
    ]
    lines = readable + [
        '### Goal', project['goal'], '', '#### CEO interpretation', plan.get('interpretation', ''), '',
        '#### Acceptance criteria', *[f'- {c}' for c in plan.get('acceptance_criteria', [])], '',
        '#### Pipeline', *[f"- {s['name']} — {s['agent_role']} ({s['provider']})" for s in plan.get('pipeline', [])], '',
        '### Decisions', *([f"- {d.get('what')}: {d.get('why', '')}" for d in decisions] or ['- none recorded']), '',
        '### Lessons', *(lessons or ['- No failed rounds. See verification findings for residual issues.']), '',
        '### Verification Findings', *[r.replace('### Round', '#### Round', 1) for r in rounds],
        '### Evidence', *([f"- {e}" for e in evidence] or ['- none recorded']), '',
        '### CEO Report', report.get('summary', ''), '', f"Judgment: {report.get('judgment', '')}", '',
        *[f'- {s}' for s in report.get('next_steps', [])], '',
        '### Artifacts', *[f"- v{a['iteration']}: `{a['path']}` sha256 `{a['sha256']}`" for a in artifacts], '',
        '### Owner Rulings', *([f"- 기준 {r.get('criterion')} ({r.get('criterion_text', '')}): {r.get('ruling')}"
                                for r in rulings] or ['- none recorded']), '',
        '### Approvals', *([f"- {a['subject']} [{a['status']}]: {a.get('purpose')}" for a in approvals]
                           or ['- none recorded']), '',
    ]
    data = '\n'.join(lines).encode('utf-8')
    folder = Path(vault) / 'Projects'
    folder.mkdir(parents=True, exist_ok=True)
    path = Path(path) if path else folder / f"{time.strftime('%Y-%m-%d')} {_slug(project['goal'])} {project['id'][-6:]}.md"
    path.write_bytes(data)                      # exact bytes, so the sha256 matches the file on disk
    sha = hashlib.sha256(data).hexdigest()
    back = path.read_bytes()
    missing = [s for s in SECTIONS if s.encode('utf-8') not in back]
    if hashlib.sha256(back).hexdigest() != sha or missing:
        raise ValueError(f'Archive verification failed for {path}: {missing or "hash mismatch"}')
    return path, sha
