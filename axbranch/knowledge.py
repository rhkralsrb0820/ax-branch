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
    scored = sorted(((len(q & terms(f'{r[0]} {r[1]}')), r) for r in rows), key=lambda s: -s[0])
    return [{'title': r[0], 'summary': (r[1] or '')[:400], 'source': r[2], 'published_at': r[3],
             'url': r[4], 'verification_status': r[5]} for score, r in scored[:limit] if score >= 2]


def _slug(text, n=50):
    return re.sub(r'[\\/:*?"<>|#^\[\]\s]+', ' ', text).strip()[:n].strip() or 'project'


def archive(vault, project, verifications, decisions, artifact_text, artifact):
    """Write the project's durable knowledge note, then read it back to verify.
    Returns (path, sha256). Raises OSError/ValueError if the archive is not intact."""
    plan, report = project['plan'] or {}, project['report'] or {}
    lessons = [f"- Round {v['iteration']} FAIL — [{f['severity']}] {f['issue']} (evidence: {f['evidence']})"
               for v in verifications if v['verdict'] == 'FAIL' for f in v['result'].get('findings', [])]
    lines = [
        f"# {_slug(project['goal'], 80)}", '',
        f"- project: `{project['id']}`  closed: {time.strftime('%Y-%m-%d')}  rounds: {len(verifications)}",
        '- tags: #ax-branch #project-archive', '',
        '## Goal', project['goal'], '',
        '## CEO Interpretation', plan.get('interpretation', ''), '',
        '## Acceptance Criteria', *[f'- {c}' for c in plan.get('acceptance_criteria', [])], '',
        '## Pipeline', *[f"- {s['name']} — {s['agent_role']} ({s['provider']})" for s in plan.get('pipeline', [])], '',
        '## Decisions', *[f"- {d.get('what')}: {d.get('why', '')}" for d in decisions], '',
        '## Verification Knowledge / Failed Approaches', *(lessons or ['- Passed first round.']), '',
        '## CEO Report', report.get('summary', ''), '', f"Judgment: {report.get('judgment', '')}", '',
        *[f'- {s}' for s in report.get('next_steps', [])], '',
        '## Artifact', f"`{artifact['path']}`  sha256 `{artifact['sha256']}`", '',
        '```', artifact_text[:4000], '```', '',
    ]
    text = '\n'.join(lines)
    folder = Path(vault) / 'Projects'
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{time.strftime('%Y-%m-%d')} {_slug(project['goal'])} {project['id'][-6:]}.md"
    path.write_text(text, encoding='utf-8')
    sha = hashlib.sha256(text.encode('utf-8')).hexdigest()
    back = path.read_text(encoding='utf-8')
    if hashlib.sha256(back.encode('utf-8')).hexdigest() != sha or '## Verification Knowledge' not in back:
        raise ValueError(f'Archive verification failed for {path}')
    return path, sha
