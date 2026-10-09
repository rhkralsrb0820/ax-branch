"""Long-term knowledge: the Obsidian vault (read + Owner-authorized archive) and
Global AI Intelligence's library (read-only). Only relevant excerpts ever reach a
model; the vault is never injected whole."""
import hashlib
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
        text = path.read_text(encoding='utf-8', errors='replace')
        reusable = _section(text, REUSABLE)
        if reusable:
            title = text.split('\n', 1)[0]
            body = f"{title}\n\n## {REUSABLE}\n{reusable}\n\n## {SUMMARY}\n{_section(text, SUMMARY)}"
        else:
            body = text
        score = len(q & terms(path.stem + ' ' + body))
        if score >= 2:
            project = re.search(r'project: `(P-[\w-]+)`', text)
            scored.append((score, path, body, project and project.group(1), bool(reusable)))
    scored.sort(key=lambda s: -s[0])
    return [{'note': str(p.relative_to(vault)), 'project': pid, 'matched_terms': score,
             'evidence': f"{p.relative_to(vault)} § {EVIDENCE}" if structured else str(p.relative_to(vault)),
             'excerpt': b[:chars]} for score, p, b, pid, structured in scored[:limit]]


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


def _slug(text, n=50):
    return re.sub(r'[\\/:*?"<>|#^\[\]\s]+', ' ', text).strip()[:n].strip() or 'project'


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
