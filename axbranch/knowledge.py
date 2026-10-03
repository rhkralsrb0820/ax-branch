"""Long-term knowledge: the Obsidian vault (read + Owner-authorized archive) and
Global AI Intelligence's library (read-only). Only relevant excerpts ever reach a
model; the vault is never injected whole."""
import hashlib
import re
import sqlite3
import time
from pathlib import Path

_WORD = re.compile(r'[a-z0-9_]{3,}|[^\W\x00-\x7f]{2,}')
_STOP = {'the', 'and', 'for', 'with', 'that', 'this', 'from', 'into', 'are', 'will', 'can', 'should'}


def terms(text):
    return set(_WORD.findall((text or '').lower())) - _STOP


def retrieve(vault, query, limit=3, chars=1500):
    """Vault notes ranked by term overlap with the query."""
    # ponytail: full scan per call; add an FTS5 index when the vault outgrows a few thousand notes.
    q, scored = terms(query), []
    for path in Path(vault).rglob('*.md') if Path(vault).is_dir() else ():
        if '.obsidian' in path.parts or '.trash' in path.parts:
            continue
        text = path.read_text(encoding='utf-8', errors='replace')
        score = len(q & terms(path.stem + ' ' + text))
        if score >= 2:
            scored.append((score, path, text))
    scored.sort(key=lambda s: -s[0])
    return [{'note': str(p.relative_to(vault)), 'excerpt': t[:chars]} for _, p, t in scored[:limit]]


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


SECTIONS = ('## Goal', '## Decisions', '## Lessons', '## Verification Findings', '## Evidence', '## CEO Report', '## Artifacts')


def archive(vault, project, verifications, decisions, evidence, artifacts):
    """Write the project's durable knowledge note, then read it back to verify.
    Durable = goal, decisions, lessons, every verification finding, evidence, the CEO report and
    artifact references (path + sha256). Raw artifact content and agent working context are NOT
    archived: artifacts stay in the workspace, addressed by hash.
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
    lines = [
        f"# {_slug(project['goal'], 80)}", '',
        f"- project: `{project['id']}`  closed: {time.strftime('%Y-%m-%d')}  verification rounds: {len(verifications)}",
        '- tags: #ax-branch #project-archive', '',
        '## Goal', project['goal'], '', '### CEO interpretation', plan.get('interpretation', ''), '',
        '### Acceptance criteria', *[f'- {c}' for c in plan.get('acceptance_criteria', [])], '',
        '### Pipeline', *[f"- {s['name']} — {s['agent_role']} ({s['provider']})" for s in plan.get('pipeline', [])], '',
        '## Decisions', *([f"- {d.get('what')}: {d.get('why', '')}" for d in decisions] or ['- none recorded']), '',
        '## Lessons', *(lessons or ['- No failed rounds. See verification findings for residual issues.']), '',
        '## Verification Findings', *rounds,
        '## Evidence', *([f"- {e}" for e in evidence] or ['- none recorded']), '',
        '## CEO Report', report.get('summary', ''), '', f"Judgment: {report.get('judgment', '')}", '',
        *[f'- {s}' for s in report.get('next_steps', [])], '',
        '## Artifacts', *[f"- v{a['iteration']}: `{a['path']}` sha256 `{a['sha256']}`" for a in artifacts], '',
    ]
    data = '\n'.join(lines).encode('utf-8')
    folder = Path(vault) / 'Projects'
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{time.strftime('%Y-%m-%d')} {_slug(project['goal'])} {project['id'][-6:]}.md"
    path.write_bytes(data)                      # exact bytes, so the sha256 matches the file on disk
    sha = hashlib.sha256(data).hexdigest()
    back = path.read_bytes()
    missing = [s for s in SECTIONS if s.encode('utf-8') not in back]
    if hashlib.sha256(back).hexdigest() != sha or missing:
        raise ValueError(f'Archive verification failed for {path}: {missing or "hash mismatch"}')
    return path, sha
