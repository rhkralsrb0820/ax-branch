"""KI-0 knowledge index + evaluation harness, on temporary stores and vaults only."""
import hashlib
import shutil
import tempfile
import unittest
from pathlib import Path

from axbranch import kindex as KI, knowledge
from axbranch.state import Store

HARNESS = {'name': 'add log', 'ok': False, 'status': 201, 'probe_misconfigured': True,
           'problems': ["status 201, expected -1 for 'add log'"]}


def _checks(*steps):
    return {'ok': not steps, 'runtime': {'ok': not steps, 'steps': list(steps)}}


class KnowledgeIndexTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.vault = self.tmp / 'vault'
        (self.vault / 'Projects').mkdir(parents=True)
        self.db = self.tmp / 'axbranch.sqlite3'
        self.index = self.tmp / 'knowledge' / 'index.sqlite3'
        store = Store(self.db)
        try:
            # A met the harness failure, then passed; B later meets the same failure; C shares goal words only.
            self.a = store.new_project('회의록 관리 웹 도구를 만들어')
            store.add_verification(self.a, 'F-a1', 1, 'FAIL', {'findings': [{'severity': 'major', 'issue': 'add log failed'}]},
                                   _checks(HARNESS), 'claude')
            store.add_verification(self.a, 'F-a2', 2, 'PASS', {'findings': []}, _checks(), 'claude')
            self.c = store.new_project('회의록 요약 문서를 작성해')
            self.b = store.new_project('업무 일지 웹 도구를 만들어')
            store.add_verification(self.b, 'F-b1', 1, 'FAIL', {'findings': [{'severity': 'major', 'issue': 'add log failed'}]},
                                   _checks({**HARNESS, 'status': 200, 'problems': ["status 200, expected -1 for 'x'"]}),
                                   'claude')
            store.add_feedback(self.b, 1, 'problem', '저장이 안 돼요')
            # explicit, increasing times (Windows clock resolution can tie consecutive inserts)
            for i, (table, key, value) in enumerate([('projects', 'id', self.a), ('projects', 'id', self.c),
                                                     ('projects', 'id', self.b)]):
                store.db.execute(f'UPDATE {table} SET created=? WHERE {key}=?', (1000 + 100 * i, value))
            for vid, t in zip([v['id'] for v in store.verifications(self.a)] + [v['id'] for v in store.verifications(self.b)],
                              (1010, 1020, 1210)):
                store.db.execute('UPDATE verifications SET created=? WHERE id=?', (t, vid))
            store.db.execute('UPDATE owner_feedback SET created=1220')
            store.db.commit()
        finally:
            store.close()
        (self.vault / 'Projects' / '2026-10-01 회의록.md').write_text(
            f'# 회의록 관리\n\n- project: `{self.a}`\n\n## 재사용 지식 (Reusable Knowledge)\n'
            '- 회의록 저장 기능은 HTTP 상태를 정확히 지정해 점검한다\n\n## Evidence (원본 기록)\nraw log 회의록 회의록\n',
            encoding='utf-8')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def rows(self, sql):
        con = KI._open(self.index)
        try:
            return sorted(tuple(r) for r in con.execute(sql))
        finally:
            con.close()

    def digest(self):
        return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in [self.db, *self.vault.rglob('*.md')]}

    def test_signature_ignores_product_specific_values(self):
        same = {**HARNESS, 'status': 200, 'problems': ["status 200, expected -1 for 'other probe'"]}
        self.assertEqual(KI.signature(HARNESS), KI.signature(same))
        self.assertTrue(KI.signature(HARNESS).startswith('harness:'))
        self.assertNotEqual(KI.signature(HARNESS), KI.signature({'name': 'x', 'ok': False, 'exit': 1,
                                                                  'problems': ['crashed (exit 1)']}))

    def test_index_is_derived_rebuildable_and_sources_stay_untouched(self):
        before = self.digest()
        n = KI.build(self.index, self.vault, self.db)
        first = self.rows('SELECT id, sha FROM units')
        self.index.unlink()
        self.assertEqual(KI.build(self.index, self.vault, self.db), n)
        self.assertEqual(self.rows('SELECT id, sha FROM units'), first)
        KI.evaluate(self.db, self.index, self.vault)
        self.assertEqual(self.digest(), before)                       # runtime DB and vault byte-identical
        texts = [r[0] for r in self.rows('SELECT text FROM units')]
        self.assertFalse(any('raw log' in t for t in texts))          # Evidence (raw logs) is not indexed

    def test_korean_particles_match_and_time_and_project_filters_hold(self):
        KI.build(self.index, self.vault, self.db)
        hits = KI.search_k1(self.index, '회의록을 저장하는 기능')
        self.assertIn(self.a, KI.projects_of(hits))
        self.assertEqual(KI.search_k1(self.index, '회의록을', exclude_project=self.a), [])
        note_day_end = KI._note_time(self.vault, 'Projects/2026-10-01 회의록.md')
        self.assertFalse([h for h in KI.search_k1(self.index, '회의록을', before=note_day_end - 1) if h['kind'] == 'note'])

    def test_labels_are_deterministic_and_ignore_ceo_adoption_claims(self):
        KI.build(self.index, self.vault, self.db)
        sits = KI.situations(self.db, self.index)
        failure = next(s for s in sits if s['kind'] == 'failure' and s['project'] == self.b)
        self.assertEqual(failure['labels'], {self.a: 2})              # same signature, resolved before
        own = next(s for s in sits if s['kind'] == 'failure' and s['project'] == self.a)
        self.assertEqual(own['labels'], {})                           # nothing earlier: no label invented
        planning = next(s for s in sits if s['kind'] == 'planning' and s['project'] == self.b)
        self.assertEqual(planning['labels'], {self.a: 1})
        self.assertEqual(planning['hard_negatives'], [])
        store = Store(self.db)
        try:                                                          # a CEO claim of adopting C changes nothing
            store.event(self.b, 'knowledge_trace', phase='ADOPTED', retrieval='R-x', decision=1, reason='c is great')
        finally:
            store.close()
        self.assertEqual(KI.situations(self.db, self.index), sits)

    def test_metrics_match_hand_computed_values(self):
        m = KI.metrics(['x', 'a', 'b'], {'a': 2, 'b': 1, 'c': 1}, k=3)
        self.assertAlmostEqual(m['recall'], 2 / 3)
        self.assertAlmostEqual(m['precision'], 2 / 3)
        self.assertAlmostEqual(m['mrr'], 1 / 2)
        dcg = 3 / KI.math.log2(3) + 1 / KI.math.log2(4)
        ideal = 3 / KI.math.log2(2) + 1 / KI.math.log2(3) + 1 / KI.math.log2(4)
        self.assertAlmostEqual(m['ndcg'], dcg / ideal)
        self.assertAlmostEqual(m['noise'], 1 / 3)
        self.assertEqual(KI.metrics([], {}, 3), {'recall': None, 'precision': None, 'mrr': None, 'ndcg': None,
                                                 'noise': 0.0})          # nothing relevant, nothing returned: correct
        self.assertEqual(KI.metrics(['x'], {}, 3)['noise'], 1.0)

    def test_size_and_promotion_gates_count_independent_projects(self):
        def row(project, base, chal, noise=0.0):
            return {'situation': {'project': project}, 'K0': {'recall': base, 'ndcg': base, 'noise': 0.0},
                    'C': {'recall': chal, 'ndcg': chal, 'noise': noise}}
        many = lambda n_projects, per, *args: [row(f'P{i}', *args) for i in range(n_projects) for _ in range(per)]
        self.assertEqual(KI.verdict(many(10, 1, 0.0, 1.0), 'K0', 'C')['verdict'], 'HOLD')        # too few situations
        one = KI.verdict(many(1, 500, 0.0, 1.0), 'K0', 'C')                                      # 500 from ONE project
        self.assertEqual((one['verdict'], one['labeled'], one['labeled_projects']), ('HOLD', 500, 1))
        self.assertEqual(KI.verdict(many(19, 10, 0.0, 1.0), 'K0', 'C')['verdict'], 'HOLD')        # 190 from 19 projects
        self.assertEqual(KI.verdict(many(60, 1, 0.0, 1.0), 'K0', 'C')['verdict'], 'ADOPT')
        self.assertEqual(KI.verdict(many(60, 1, 0.0, 1.0, 1.0), 'K0', 'C')['verdict'], 'REJECT')   # more noise
        self.assertEqual(KI.verdict(many(60, 1, 1.0, 1.0), 'K0', 'C')['verdict'], 'REJECT')        # no gain

    def test_one_dominant_project_cannot_carry_the_confidence_interval(self):
        # 25 projects: one with 500 big wins, 24 with small losses. Per-situation resampling would call it a win;
        # project-clustered resampling must not.
        rows = [{'situation': {'project': 'BIG'}, 'K0': {'recall': 0.0, 'ndcg': 0.0, 'noise': 0.0},
                 'C': {'recall': 1.0, 'ndcg': 1.0, 'noise': 0.0}} for _ in range(500)]
        rows += [{'situation': {'project': f'P{i}'}, 'K0': {'recall': 0.5, 'ndcg': 0.5, 'noise': 0.0},
                  'C': {'recall': 0.4, 'ndcg': 0.4, 'noise': 0.0}} for i in range(24)]
        v = KI.verdict(rows, 'K0', 'C')
        self.assertEqual((v['verdict'], v['labeled_projects'], v['resampling']), ('REJECT', 25, 'project-clustered bootstrap'))
        self.assertLessEqual(v['ci']['recall'][0], 0)

    def test_rrf_is_deterministic_and_single_list_ablation_keeps_order(self):
        a = [{'id': 'u1', 'project': 'P1'}, {'id': 'u2', 'project': 'P2'}]
        b = [{'id': 'u2', 'project': 'P2'}, {'id': 'u3', 'project': 'P3'}]
        self.assertEqual([u['id'] for u in KI.rrf(a, b)], ['u2', 'u1', 'u3'])
        self.assertEqual(KI.rrf(a), a)

    def test_k0_is_unchanged_by_the_index(self):
        before = knowledge.retrieve(self.vault, '회의록 관리 도구')
        KI.build(self.index, self.vault, self.db)
        self.assertEqual(knowledge.retrieve(self.vault, '회의록 관리 도구'), before)


if __name__ == '__main__':
    unittest.main()
