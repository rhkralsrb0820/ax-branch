"""Knowledge Intelligence foundation (KI-0): a DERIVED, rebuildable retrieval index and an offline evaluation harness.

Standard library only (SQLite FTS5). K0 = knowledge.retrieve stays the CEO's retriever: nothing here changes what the
CEO sees. Sources are only read: the Obsidian notes and the runtime DB opened read-only. Challengers (K1 = BM25 over
section chunks and experience cards, S = failure-signature match, RRF fusion) are judged against K0 on situations
rebuilt from history, with deterministic labels (never the CEO's ADOPTED claims) and a time/project split. Below the
size gate the verdict is HOLD whatever the scores say."""
import hashlib
import json
import math
import random
import re
import sqlite3
import time
from pathlib import Path

from . import knowledge, runtime

INDEX_VERSION = 1
MIN_LABELED = 50            # labeled situations needed before any promotion verdict
MIN_PROJECTS = 20           # ...from at least this many DIFFERENT projects: situations of one project are not
                            # independent evidence (one project's repeated FAILs share one cause)

# Pre-registered product rubric; never generated from the observed answers or promoted by two tasks.
PRODUCT_RUBRIC = {'evidence_accuracy': '0 incorrect/unsupported; 1 partially grounded; 2 every material claim traceable',
                 'requirements': '0 missing core requirements; 1 partly met; 2 all required sections and decisions met',
                 'specificity': '0 vague/unexecutable; 1 partial concrete next steps; 2 bounded actionable MVP and experiments',
                 'cost_accuracy': '0 incorrect; 1 incomplete assumptions; 2 correct scenarios with currency/period/assumptions',
                 'fact_assumption_separation': '0 misleading validation claims; 1 mixed labels; 2 facts/estimates/unknowns explicit'}


def product_rubric_hash():
    return hashlib.sha256(json.dumps(PRODUCT_RUBRIC, sort_keys=True).encode()).hexdigest()


def compare_product_evaluations(control, treatment):
    """A bounded local comparison, never an automatic department change or general improvement claim."""
    matched = ('task_sha256', 'input_sha256', 'department_specs', 'budget', 'rubric_sha256')
    reasons = [f'mismatched {k}' for k in matched if control.get(k) != treatment.get(k) or k not in control]
    if control.get('rubric_sha256') != product_rubric_hash():
        reasons.append('rubric not pre-registered')
    for result in (control, treatment):
        if result.get('execution_mode') != 'subscription_cli' or not result.get('verification_ref') or any(
                not isinstance(result.get(k), str) or not re.fullmatch(r'[a-f0-9]{64}', result[k])
                for k in ('artifact_sha256', 'task_sha256', 'input_sha256')):
            reasons.append('no real-model artifact provenance')
        scores = result.get('scores', {})
        if not isinstance(scores, dict) or set(scores) != set(PRODUCT_RUBRIC) or any(not isinstance(s, dict) or type(s.get('score')) is not int
                or s['score'] not in (0, 1, 2) or not isinstance(s.get('evidence'), list) or not s['evidence']
                or not all(isinstance(e, str) and e.strip() for e in s['evidence']) for s in scores.values()):
            reasons.append('missing score/evidence')
        metrics = result.get('metrics') or {}
        if not metrics.get('token_usage_complete') or not metrics.get('agent_turns_completed') or not isinstance(metrics.get('provider_seconds'), (int, float)):
            reasons.append('measured usage/time incomplete')
        if not result.get('independent_evaluator'):
            reasons.append('evaluator independence not established')
    delta = None if reasons else sum(s['score'] for s in treatment['scores'].values()) - sum(s['score'] for s in control['scores'].values())
    return {'rubric_sha256': product_rubric_hash(), 'paired_tasks': 1 if not reasons else 0,
            'local_score_delta': delta, 'comparison_valid': not reasons, 'limitations': reasons + [
                'one paired B task; order/provider variance uncontrolled; no general quality improvement established',
                'retrieval and evaluation scores do not authorize changing permissions or acceptance criteria'],
            'quality_improvement': 'UNPROVEN', 'recommendation': 'HOLD', 'department_update_applied': False,
            'control_metrics': control.get('metrics'), 'treatment_metrics': treatment.get('metrics')}
SKIP_SECTIONS = (knowledge.EVIDENCE,)       # raw logs: noise for retrieval (still in the note for humans)
_DATE = re.compile(r'^(\d{4}-\d{2}-\d{2})')
_PROJECT = re.compile(r'project: `(P-[\w-]+)`')


# ---- failure signatures
def _norm(text):
    text = re.sub(r"'[^']*'|\"[^\"]*\"", 'Q', str(text).lower())
    text = re.sub(r'-?\d+(\.\d+)?', 'N', text)
    return ' '.join(text.split())[:80]


def signature(step):
    """A failed runtime step's signature: its evidence class + normalized problems (product names, numbers and
    quoted values removed), so the same failure in another project matches."""
    return f"{runtime.classify_step(step) or 'ok'}:{' | '.join(sorted(_norm(p) for p in step.get('problems', [])))}"[:200]


# ---- sources -> units (section chunks, experience cards)
def _unit(source, kind, project, created, title, text, sig=''):
    text = text.strip()[:4000]
    sha = hashlib.sha256(f'{source}\n{title}\n{text}'.encode('utf-8')).hexdigest()
    return {'id': sha[:16], 'source': source, 'kind': kind, 'project': project or '', 'created': created,
            'signature': sig, 'title': title, 'text': text, 'sha': sha}


def note_chunks(vault):
    """One unit per '## ' section of each vault note. A note counts as known from the END of the day in its name
    (the archive is written during that day), so a situation earlier that day never sees it."""
    units = []
    for path in sorted(Path(vault).rglob('*.md')) if Path(vault).is_dir() else ():
        if '.obsidian' in path.parts or '.trash' in path.parts:
            continue
        text = path.read_text(encoding='utf-8', errors='replace')
        m = _DATE.match(path.name)
        created = time.mktime(time.strptime(m.group(1), '%Y-%m-%d')) + 86400 if m else path.stat().st_mtime
        project = (_PROJECT.search(text) or [None, None])[1]
        rel = path.relative_to(vault).as_posix()
        title = text.split('\n', 1)[0].lstrip('# ').strip()
        for part in re.split(r'^(?=## )', text, flags=re.M):
            heading = part.split('\n', 1)[0][3:].strip() if part.startswith('## ') else ''
            if any(heading.startswith(s) for s in SKIP_SECTIONS) or not part.strip():
                continue
            units.append(_unit(rel, 'note', project, created, f'{title} / {heading or "intro"}', part))
    return units


def experience_cards(db_path):
    """Deterministic cards from the runtime DB (read-only): one per (project, failure signature) and one per Owner
    feedback. A card is known only from the time of the LAST fact it states (a resolution is hindsight)."""
    con = sqlite3.connect(f'{Path(db_path).resolve().as_uri()}?mode=ro', uri=True)
    con.row_factory = sqlite3.Row
    try:
        goals = {r['id']: r['goal'] for r in con.execute('SELECT id, goal FROM projects')}
        cards, seen = [], {}
        for v in con.execute('SELECT project_id, iteration, verdict, checks, created FROM verifications ORDER BY created'):
            steps = (json.loads(v['checks']).get('runtime') or {}).get('steps', [])
            for st in steps:
                if not st.get('ok'):
                    key = (v['project_id'], signature(st))
                    c = seen.setdefault(key, {'first': v['created'], 'last': v['created'], 'count': 0, 'steps': set(),
                                              'problems': st.get('problems', [])[:2], 'resolved': None})
                    c['count'] += 1
                    c['last'] = v['created']
                    c['steps'].add(st.get('name', ''))
            if v['verdict'] == 'PASS':
                for (pid, _), c in seen.items():
                    if pid == v['project_id'] and c['resolved'] is None:
                        c['resolved'] = (v['iteration'], v['created'])
        for (pid, sig), c in sorted(seen.items(), key=lambda kv: kv[1]['first']):
            resolved = f"resolved: later PASS v{c['resolved'][0]}" if c['resolved'] else 'resolved: no PASS after it'
            known = c['resolved'][1] if c['resolved'] else c['last']
            text = (f"[failure experience] {goals.get(pid, '')}\nsignature: {sig}\nsteps: {', '.join(sorted(c['steps']))}"
                    f"\nproblems: {' | '.join(map(str, c['problems']))}\nseen {c['count']}x; {resolved}")
            cards.append(_unit(f'db:{pid}', 'failure', pid, known, f'{pid} failure', text, sig))
        for f in con.execute('SELECT id, project_id, verdict, text, created FROM owner_feedback ORDER BY id'):
            if f['verdict'] in ('problem', 'request'):
                cards.append(_unit(f"db:{f['project_id']}", 'feedback', f['project_id'], f['created'],
                                   f"{f['project_id']} owner feedback {f['id']}",
                                   f"[owner feedback] {goals.get(f['project_id'], '')}\n{f['text']}"))
        return cards
    finally:
        con.close()


# ---- the derived index
def build(index_path, vault, db_path):
    """(Re)build the index from scratch into a temp file, then swap it in: deleting it loses nothing."""
    units = note_chunks(vault) + (experience_cards(db_path) if Path(db_path).is_file() else [])
    index_path = Path(index_path)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = index_path.with_suffix('.building')
    tmp.unlink(missing_ok=True)
    con = sqlite3.connect(tmp)
    try:
        con.executescript('CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);'
                          'CREATE TABLE units(id TEXT PRIMARY KEY, source TEXT, kind TEXT, project TEXT, created REAL,'
                          ' signature TEXT, title TEXT, text TEXT, sha TEXT);'
                          "CREATE VIRTUAL TABLE units_fts USING fts5(id UNINDEXED, tokens);")
        for u in sorted({u['id']: u for u in units}.values(), key=lambda u: u['id']):
            con.execute('INSERT INTO units VALUES(:id,:source,:kind,:project,:created,:signature,:title,:text,:sha)', u)
            # Korean-aware tokens (knowledge.terms strips a trailing particle), so FTS5 matches like K0 does
            con.execute('INSERT INTO units_fts VALUES(?,?)', (u['id'], ' '.join(sorted(knowledge.terms(u['text'])))))
        con.executemany('INSERT INTO meta VALUES(?,?)', [('index_version', str(INDEX_VERSION)),
                                                         ('units', str(len(units)))])
        con.commit()
    finally:
        con.close()
    tmp.replace(index_path)
    return len(units)


def _open(index_path):
    con = sqlite3.connect(f'{Path(index_path).resolve().as_uri()}?mode=ro', uri=True)
    con.row_factory = sqlite3.Row
    return con


def _visible(row, before, exclude_project):
    return (before is None or row['created'] <= before) and (not exclude_project or row['project'] != exclude_project)


def search_k1(index_path, query, k=20, before=None, exclude_project=None):
    """K1: BM25 over Korean-aware tokens of section chunks and experience cards."""
    toks = sorted(knowledge.terms(query))
    if not toks:
        return []
    con = _open(index_path)
    try:
        rows = con.execute('SELECT u.*, bm25(units_fts) AS score FROM units_fts JOIN units u ON u.id = units_fts.id '
                           'WHERE units_fts MATCH ? ORDER BY score, u.id', (' OR '.join(f'"{t}"' for t in toks),))
        return [dict(r) for r in rows if _visible(r, before, exclude_project)][:k]
    finally:
        con.close()


def search_signature(index_path, signatures, k=20, before=None, exclude_project=None):
    """S: experience cards with the same failure signature (resolved ones first)."""
    if not signatures:
        return []
    con = _open(index_path)
    try:
        rows = con.execute(f"SELECT * FROM units WHERE kind='failure' AND signature IN "
                           f"({','.join('?' * len(signatures))}) ORDER BY created, id", list(signatures))
        hits = [dict(r) for r in rows if _visible(r, before, exclude_project)]
        hits.sort(key=lambda r: ('resolved: later PASS' not in r['text'], r['created'], r['id']))
        return hits[:k]
    finally:
        con.close()


def rrf(*rankings, k=60):
    """Reciprocal Rank Fusion of ranked unit lists (rank-based: retriever scores need no calibration)."""
    score, units = {}, {}
    for ranking in rankings:
        for rank, u in enumerate(ranking, 1):
            score[u['id']] = score.get(u['id'], 0) + 1 / (k + rank)
            units[u['id']] = u
    return [units[i] for i in sorted(score, key=lambda i: (-score[i], i))]


def projects_of(units):
    """Ranked distinct source projects: the unit of relevance (an experience is a project's lesson)."""
    out = []
    for u in units:
        if u.get('project') and u['project'] not in out:
            out.append(u['project'])
    return out


# ---- evaluation dataset (deterministic labels only)
def situations(db_path, index_path):
    """Retrieval situations rebuilt from history, labeled without any model or CEO claim:
    - failure: a FAIL with failed runtime steps (the strategy query: goal + blocking issues). Another project is
      relevant (2) if it already had a card with the same signature RESOLVED before this moment, (1) if same
      signature but unresolved then.
    - planning: a new goal. Another earlier project is relevant (1) if a signature it had already met later
      occurred in THIS project (experience that would have helped). Hard negatives share goal words but no signature."""
    con = sqlite3.connect(f'{Path(db_path).resolve().as_uri()}?mode=ro', uri=True)
    con.row_factory = sqlite3.Row
    idx = _open(index_path)
    try:
        cards = [dict(r) for r in idx.execute("SELECT * FROM units WHERE kind='failure'")]
        projects = [dict(r) for r in con.execute('SELECT id, goal, created FROM projects ORDER BY created')]
        sigs_of = {}
        out = []
        for v in con.execute('SELECT project_id, result, checks, created FROM verifications ORDER BY created'):
            steps = [st for st in (json.loads(v['checks']).get('runtime') or {}).get('steps', []) if not st.get('ok')]
            sigs = sorted({signature(st) for st in steps})
            sigs_of.setdefault(v['project_id'], set()).update(sigs)
            if not sigs:
                continue
            goal = next(p['goal'] for p in projects if p['id'] == v['project_id'])
            issues = ' '.join(f.get('issue', '') for f in json.loads(v['result']).get('findings', [])
                              if f.get('severity') in ('critical', 'major'))[:900]
            labels = {}
            for c in cards:
                if c['project'] != v['project_id'] and c['signature'] in sigs and c['created'] <= v['created']:
                    labels[c['project']] = max(labels.get(c['project'], 0),
                                               2 if 'resolved: later PASS' in c['text'] else 1)
            out.append({'kind': 'failure', 'project': v['project_id'], 'at': v['created'], 'query': f'{goal} {issues}',
                        'signatures': sigs, 'labels': labels})
        for p in projects:
            mine = sigs_of.get(p['id'], set())
            labels = {c['project']: 1 for c in cards if c['project'] != p['id'] and c['created'] <= p['created']
                      and c['signature'] in mine}
            negatives = sorted({q['id'] for q in projects if q['id'] != p['id'] and q['created'] <= p['created']
                                and q['id'] not in labels
                                and len(knowledge.terms(q['goal']) & knowledge.terms(p['goal'])) >= 2})
            out.append({'kind': 'planning', 'project': p['id'], 'at': p['created'], 'query': p['goal'],
                        'signatures': [], 'labels': labels, 'hard_negatives': negatives})
        return out
    finally:
        con.close()
        idx.close()


# ---- metrics
def metrics(ranked, labels, k=3):
    """Graded relevance metrics for one ranked project list. Recall/MRR/nDCG are None when nothing is relevant
    (then only noise counts: returning nothing is correct)."""
    top = ranked[:k]
    rel = {p: g for p, g in labels.items() if g > 0}
    noise = (sum(1 for p in top if p not in rel) / len(top)) if top else 0.0
    if not rel:
        return {'recall': None, 'precision': None, 'mrr': None, 'ndcg': None, 'noise': noise}
    hits = [p for p in top if p in rel]
    first = next((i for i, p in enumerate(ranked, 1) if p in rel), None)
    dcg = sum((2 ** rel[p] - 1) / math.log2(i + 1) for i, p in enumerate(top, 1) if p in rel)
    ideal = sum((2 ** g - 1) / math.log2(i + 1) for i, g in enumerate(sorted(rel.values(), reverse=True)[:k], 1))
    return {'recall': len(hits) / len(rel), 'precision': len(hits) / k, 'mrr': 1 / first if first else 0.0,
            'ndcg': dcg / ideal if ideal else 0.0, 'noise': noise}



def cluster_ci(groups, rounds=2000, seed=7):
    """95% CI of the mean per-PROJECT difference, by resampling projects (cluster bootstrap): every project weighs
    the same however many situations it produced. groups = {project: [challenger - baseline, ...]}."""
    means = [sum(d) / len(d) for d in groups.values() if d]
    if not means:
        return None
    rnd = random.Random(seed)
    boot = sorted(sum(rnd.choice(means) for _ in means) / len(means) for _ in range(rounds))
    return [boot[int(0.025 * rounds)], boot[int(0.975 * rounds) - 1]]


def _project(row):
    return (row.get('situation') or {}).get('project')


def verdict(per_situation, baseline, challenger):
    """ADOPT only with enough labeled situations from enough DIFFERENT projects AND a project-clustered CI above 0
    on recall@3 and nDCG@3 AND no extra noise. Repeated situations of one project never satisfy the gate alone."""
    labeled = [s for s in per_situation if s[baseline]['recall'] is not None]
    projects = {_project(s) for s in labeled}
    counts = {'situations': len(per_situation), 'labeled': len(labeled), 'labeled_projects': len(projects)}
    if len(labeled) < MIN_LABELED or len(projects) < MIN_PROJECTS:
        return {'verdict': 'HOLD', 'reason': f'{len(labeled)} labeled situations (need {MIN_LABELED}) from '
                                             f'{len(projects)} projects (need {MIN_PROJECTS})', **counts}

    def groups(rows, metric):
        out = {}
        for s in rows:
            out.setdefault(_project(s), []).append(s[challenger][metric] - s[baseline][metric])
        return out
    cis = {m: cluster_ci(groups(labeled, m)) for m in ('recall', 'ndcg')}
    noise = cluster_ci(groups(per_situation, 'noise'))
    better = all(ci[0] > 0 for ci in cis.values())
    return {'verdict': 'ADOPT' if better and noise[1] <= 0 else 'REJECT', 'ci': cis, 'noise_ci': noise,
            'resampling': 'project-clustered bootstrap', **counts}


def evaluate(db_path, index_path, vault, k=3):
    """K0 (as the CEO gets it: top 3, post-filtered to what existed then) vs K1, S, K1+S. Read-only throughout."""
    rows = []
    for s in situations(db_path, index_path):
        k0 = [h for h in knowledge.retrieve(vault, s['query']) if h.get('project') != s['project']]
        k0 = [h for h in k0 if _note_time(vault, h['note']) <= s['at']]
        k1 = search_k1(index_path, s['query'], 20, s['at'], s['project'])
        sig = search_signature(index_path, s['signatures'], 20, s['at'], s['project'])
        ranked = {'K0': [h['project'] for h in k0 if h.get('project')], 'K1': projects_of(k1),
                  'S': projects_of(sig), 'K1+S': projects_of(rrf(k1, sig))}
        rows.append({'situation': {k: s[k] for k in ('kind', 'project', 'at', 'labels')},
                     **{name: metrics(r, s['labels'], k) for name, r in ranked.items()}})
    summary = {}
    for name in ('K0', 'K1', 'S', 'K1+S'):
        vals = {m: [r[name][m] for r in rows if r[name][m] is not None]
                for m in ('recall', 'precision', 'mrr', 'ndcg', 'noise')}
        summary[name] = {m: (sum(v) / len(v) if v else None) for m, v in vals.items()}
    labeled = [r for r in rows if r['K0']['recall'] is not None]
    return {'index_version': INDEX_VERSION, 'situations': len(rows), 'projects': len({_project(r) for r in rows}),
            'labeled': len(labeled), 'labeled_projects': len({_project(r) for r in labeled}), 'summary': summary,
            'verdicts': {c: verdict(rows, 'K0', c) for c in ('K1', 'S', 'K1+S')}, 'rows': rows}


def _note_time(vault, note):
    m = _DATE.match(Path(note).name)
    return time.mktime(time.strptime(m.group(1), '%Y-%m-%d')) + 86400 if m else (Path(vault) / note).stat().st_mtime


if __name__ == '__main__':
    import sys
    from . import DB_PATH, VAULT, WORKSPACE
    index = WORKSPACE / 'knowledge' / 'index.sqlite3'
    if sys.argv[1:2] == ['build']:
        print(build(index, VAULT, DB_PATH), 'units')
    elif sys.argv[1:2] == ['eval']:
        report = evaluate(DB_PATH, index, VAULT)
        out = WORKSPACE / 'knowledge' / f"eval-{time.strftime('%Y%m%d-%H%M%S')}.json"
        out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
        print(json.dumps({k: report[k] for k in ('situations', 'projects', 'labeled', 'labeled_projects', 'summary',
                                                 'verdicts')}, ensure_ascii=False, indent=1))
        print('report:', out)
    else:
        print('usage: python -m axbranch.kindex build|eval')
