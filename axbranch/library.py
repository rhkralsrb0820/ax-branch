"""Artifact Library: what the Owner made, separate from the projects that made it.

Project   = the record of the work (SQLite projects/events/verifications).
Artifact  = the result the Owner uses: a project's latest VERIFIED version (artifacts table, files on disk).
Knowledge = the vault notes written at close.

The library is an index computed from those tables; no file is copied. A project started with Develop records
one immutable `develop_from` event naming the project it builds on, so an artifact's versions are its lineage:
v1 <- the root project, v2 <- the first Develop, v3 <- the next, and so on.
"""
import re
from pathlib import Path

from . import artifacts

TYPES = ('Apps', 'Reports', 'Documents', 'Research', 'Data', 'Other')
_ASK = re.compile(r'\s*(?:을|를)?\s*(?:만들어\s*(?:줘|봐|주세요|주십시오)|해\s*(?:줘|봐|주세요)|부탁(?:해|합니다)?)[.!?\s]*$')
_RESEARCH = re.compile(r'연구|가설|증명|논문|research|hypothesis|study|proof', re.I)
DOCS = ('.md', '.txt', '.html', '.htm', '.pdf')
DATA = ('.csv', '.json', '.xlsx', '.xls', '.parquet', '.sqlite', '.db', '.tsv')


def project_title(p):
    """The CEO's title from planning; for older projects a short title derived from the goal (the goal is unchanged)."""
    title = ((p.get('plan') or {}).get('title') or '').strip()
    if not title:
        goal = re.sub(r'^\s*\[[^\]]*\]\s*', '', p['goal'].splitlines()[0] if p['goal'] else '')
        title = _ASK.sub('', re.split(r'[:.(]', goal, 1)[0]).strip() or goal.strip()
    return title


def verified_artifact(store, pid):
    """The project's latest artifact that passed verification, or None."""
    passed = [v for v in store.verifications(pid) if v['verdict'] == 'PASS']
    return next((a for a in store.artifacts(pid) if passed and a['id'] == passed[-1]['artifact_id']), None)


def classify(project, artifact):
    """Owner-facing type, from what the result is (deterministic; no AI call)."""
    files = [Path(rel) for rel, _, _ in artifacts.files_of(artifact)]
    suffixes = {f.suffix.lower() for f in files}
    mode = ((project.get('plan') or {}).get('runtime') or {}).get('mode', 'cli')
    text = f"{project['goal']} {project_title(project)}"
    if artifact['kind'] in ('python', 'bundle') and mode in ('web', 'gui'):
        return 'Apps'
    if _RESEARCH.search(text) or any('research' in f.name.lower() for f in files):
        return 'Research'
    if suffixes & set(DATA) and not suffixes & {'.py'}:
        return 'Data'
    if any(re.search(r'report|보고', f.name, re.I) for f in files):
        return 'Reports'
    if artifact['kind'] == 'markdown' or (suffixes and suffixes <= set(DOCS)):
        return 'Documents'
    if artifact['kind'] in ('python', 'bundle'):
        return 'Apps'
    return 'Other'


def _links(store):
    """{project: develop_from detail} for every developed project, in one query."""
    import json
    return {pid: json.loads(d) for pid, d in store.db.execute(
        "SELECT project_id, detail FROM events WHERE kind='develop_from' ORDER BY id")}


def develops(store, pid):
    """The project this one was developed from (its develop_from event), or None."""
    return (_links(store).get(pid) or {}).get('base_project')


def ancestry(links, pid):
    """[root, ..., pid] following develop_from links (a cycle can never loop)."""
    chain = [pid]
    while (base := (links.get(chain[0]) or {}).get('base_project')) and base not in chain:
        chain.insert(0, base)
    return chain


def root(store, pid):
    return ancestry(_links(store), pid)[0]


def base_artifact(store, pid):
    """The exact verified artifact a developed project was started from (pinned in its develop_from event), checked
    against its recorded sha256. None for a project that is not a Develop."""
    link = _links(store).get(pid)
    if not link:
        return None
    art = next((a for a in store.artifacts(link['base_project']) if a['id'] == link['base_artifact']), None)
    problems = artifacts.problems(art) if art else ['missing']
    if problems:
        from .state import Rejected
        raise Rejected(f"The artifact this project develops ({link['base_project']}) changed or is missing: "
                       + '; '.join(problems))
    return art


def entries(store):
    """Library items: one per lineage, newest first. A version number is the depth in the lineage (v1 = the root
    project), so a hidden (discarded) ancestor or a sibling branch never renumbers the others."""
    links, items = _links(store), {}
    for row in store.projects():
        p = store.project(row['id'])
        if p['closed_mode'] == 'discard':
            continue                                  # the Owner dropped it
        art = verified_artifact(store, p['id'])
        if art is None:
            continue                                  # not a completed artifact (yet)
        chain = ancestry(links, p['id'])
        items.setdefault(chain[0], []).append((p, art, len(chain)))
    out = []
    for lineage_root, versions in items.items():
        versions.sort(key=lambda pav: (pav[2], pav[0]['created']))
        p, art, depth = max(versions, key=lambda pav: pav[0]['created'])
        out.append({
            'id': lineage_root, 'title': project_title(p), 'type': classify(p, art),
            'version': depth, 'path': art['path'], 'artifact_id': art['id'], 'kind': art['kind'],
            'project': p['id'], 'state': p['state'], 'verification': 'PASS',
            'created': min(vp['created'] for vp, _, _ in versions), 'updated': max(a['created'] for _, a, _ in versions),
            'versions': [{'version': d, 'project': vp['id'], 'artifact_iteration': va['iteration'],
                          'path': va['path'], 'state': vp['state'], 'goal': vp['goal'],
                          'from': (links.get(vp['id']) or {}).get('base_project')}
                         for vp, va, d in versions],
        })
    out.sort(key=lambda e: -e['updated'])
    return out


def develop_context(store, base_pid, retrieve=None, artifact=None):
    """What the CEO gets when the Owner develops an artifact further: the version being developed (`artifact`, the
    pinned one), its project's plan, verification lessons, Owner feedback and lineage; vault knowledge via `retrieve`."""
    base = store.project(base_pid)
    art = artifact or verified_artifact(store, base_pid)
    lineage = ancestry(_links(store), base_pid)
    fails = [v for v in store.verifications(base_pid) if v['verdict'] == 'FAIL']
    plan = base['plan'] or {}
    return {
        'rule': ('Develop: build a NEW version of this existing artifact for the new Owner goal. Start from '
                 'current_version (keep what works, change what the goal needs), keep every still-valid acceptance '
                 'criterion of the base plan, and use the lessons and Owner feedback below. The earlier project and '
                 'its versions are never changed.'),
        'artifact_title': project_title(base), 'library_version': len(lineage),
        'lineage_projects': lineage,
        'current_version': {'project': base_pid, 'iteration': art and art['iteration'], 'kind': art and art['kind'],
                            'files': [rel for rel, _, _ in artifacts.files_of(art)] if art else [],
                            # the CEO plans from an excerpt; the producer gets the whole version as its baseline
                            'content_excerpt': artifacts.text_of(art)[:20000] if art else ''},
        'base_plan': {k: plan.get(k) for k in ('interpretation', 'acceptance_criteria', 'runtime', 'network_access',
                                                'artifact_kind', 'artifact_filename')},
        'owner_feedback': [{'round': f['iteration'], 'verdict': f['verdict'], 'text': f['text'][:1500]}
                           for f in store.feedback(base_pid)],
        'verification_lessons': [f['issue'][:300] for v in fails[-3:] for f in v['result'].get('findings', [])
                                 if f.get('severity') in ('critical', 'major')][:12],
        'knowledge': retrieve(f"{base['goal']} {project_title(base)}") if retrieve else [],
    }
